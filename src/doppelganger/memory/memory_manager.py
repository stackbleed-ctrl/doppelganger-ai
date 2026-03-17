"""
Memory Manager
Doppelganger's persistent memory:
  - Temporal knowledge graph (Graphiti-style entity + relationship tracking)
  - Vector store (Qdrant) for semantic search
  - Short-term episodic buffer → long-term consolidation

Everything stays local. No cloud calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field

from ..core.config import Settings
from ..core.event_bus import Event, EventBus, EventPriority

logger = logging.getLogger(__name__)


@dataclass
class MemoryNode:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    entity_type: str = "fact"   # fact | event | person | place | preference | emotion
    tags: list[str] = field(default_factory=list)
    source: str = "agent"       # agent | perception | user | voice
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    embedding: list[float] | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class MemoryEdge:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    relation: str = ""    # e.g. 'causes', 'precedes', 'relates_to', 'contradicts'
    weight: float = 1.0
    ts: float = field(default_factory=time.time)


class MemoryManager:
    """
    Unified memory layer.

    Write path:  event → episodic buffer → embed → vector store + KG
    Read path:   query → vector search + KG traversal → ranked results
    Consolidation: short-term episodic buffer → long-term KG (every hour)
    """

    def __init__(self, bus: EventBus, settings: Settings, graphiti=None) -> None:
        self.bus = bus
        self.cfg = settings.memory
        self.data_dir = settings.data_dir / "memory"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # In-memory stores (backed to disk)
        self._nodes: dict[str, MemoryNode] = {}
        self._edges: list[MemoryEdge] = []
        self._episodic_buffer: list[MemoryNode] = []

        # Optional backends
        self._qdrant = None
        self.graphiti = graphiti
        self._active_persona_id = "default"
        self._embedder = None

        self._tasks: list[asyncio.Task] = []
        self._running = False

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        await self._load_from_disk()
        await self._init_vector_store()
        self._tasks.append(
            asyncio.create_task(self._consolidation_loop(), name="memory-consolidation")
        )
        logger.info("MemoryManager started | nodes=%d", len(self._nodes))

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._save_to_disk()

    async def health(self) -> dict:
        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "episodic_buffer": len(self._episodic_buffer),
            "vector_store": "qdrant" if self._qdrant else "in-memory",
        }

    # ─── Event handlers ──────────────────────────────────────────────────────

    async def on_perception_event(self, event: Event) -> None:
        """Store significant perception events as memories."""
        if event.topic == "perception.presence_changed":
            content = (
                f"User {'appeared' if event.payload.get('detected') else 'left'} "
                f"({event.payload.get('activity', 'unknown')} activity)"
            )
            await self.store(content, tags=["presence", "perception"], source="perception")

        elif event.topic == "perception.system_metrics":
            # Only store anomalies
            cpu = event.payload.get("cpu_percent", 0)
            if cpu > 80:
                await self.store(
                    f"High CPU usage: {cpu:.0f}%",
                    tags=["system", "anomaly"],
                    source="perception",
                )

    async def on_agent_response(self, event: Event) -> None:
        """Store agent responses as memories for future context."""
        text = event.payload.get("text", "")
        if len(text) > 20:
            await self.store(
                text,
                tags=["agent_response", event.payload.get("source", "agent")],
                source="agent",
            )

    # ─── Core API ─────────────────────────────────────────────────────────────

    async def store(
        self,
        content: str,
        *,
        tags: list[str] | None = None,
        source: str = "user",
        entity_type: str = "fact",
        metadata: dict | None = None,
    ) -> MemoryNode:
        node = MemoryNode(
            content=content,
            entity_type=entity_type,
            tags=tags or [],
            source=source,
            metadata=metadata or {},
        )

        # Get embedding
        embedding = await self._embed(content)
        if embedding:
            node.embedding = embedding

        self._nodes[node.id] = node
        self._episodic_buffer.append(node)

        # Write to vector store
        if self._qdrant and embedding:
            await self._upsert_qdrant(node)

        # Infer relationships with recent nodes
        await self._infer_edges(node)

        await self.bus.publish_simple(
            "memory.updated",
            payload={"node_id": node.id, "content": content[:100], "tags": tags},
            source="memory",
            priority=EventPriority.LOW,
        )

        logger.debug("Stored memory: %s — %s", node.id[:8], content[:60])
        return node

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        tags: list[str] | None = None,
    ) -> list[dict]:
        """Semantic search over memory. Returns ranked results."""
        embedding = await self._embed(query)

        if self._qdrant and embedding:
            return await self._search_qdrant(embedding, limit=limit, tags=tags)
        return await self._search_in_memory(query, embedding, limit=limit, tags=tags)

    async def get_context(self, topic: str, limit: int = 10) -> list[str]:
        """Get recent relevant memories as plain text list for prompt injection."""
        results = await self.search(topic, limit=limit)
        return [r["content"] for r in results]

    async def get_timeline(self, hours: int = 24) -> list[MemoryNode]:
        """Get all memories from the last N hours, ordered by time."""
        cutoff = time.time() - hours * 3600
        nodes = [n for n in self._nodes.values() if n.created_at >= cutoff]
        return sorted(nodes, key=lambda n: n.created_at)

    # ─── Vector store ────────────────────────────────────────────────────────

    async def _init_vector_store(self) -> None:
        try:
            from qdrant_client import AsyncQdrantClient
            from qdrant_client.models import Distance, VectorParams

            self._qdrant = AsyncQdrantClient(url=self.cfg.qdrant_url)
            # Ensure collection exists
            collections = await self._qdrant.get_collections()
            names = [c.name for c in collections.collections]
            if self.cfg.qdrant_collection not in names:
                await self._qdrant.create_collection(
                    collection_name=self.cfg.qdrant_collection,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE),
                )
            logger.info("Qdrant vector store ready")
        except Exception as e:
            logger.warning("Qdrant unavailable (%s) — using in-memory search", e)
            self._qdrant = None

    async def _embed(self, text: str) -> list[float] | None:
        """Get embedding via local Ollama nomic-embed-text or fallback."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "http://ollama:11434/api/embeddings",
                    json={"model": self.cfg.embedding_model, "prompt": text},
                )
                if resp.status_code == 200:
                    return resp.json()["embedding"]
        except Exception:
            pass

        # Fallback: simple TF-IDF-style sparse embedding (no model needed)
        return None  # graceful degradation to keyword search

    async def _upsert_qdrant(self, node: MemoryNode) -> None:
        try:
            from qdrant_client.models import PointStruct
            await self._qdrant.upsert(
                collection_name=self.cfg.qdrant_collection,
                points=[PointStruct(
                    id=node.id,
                    vector=node.embedding,
                    payload={
                        "content": node.content,
                        "tags": node.tags,
                        "source": node.source,
                        "created_at": node.created_at,
                    },
                )],
            )
        except Exception as e:
            logger.debug("Qdrant upsert failed: %s", e)

    async def _search_qdrant(
        self, embedding: list[float], *, limit: int, tags: list[str] | None
    ) -> list[dict]:
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchAny
            flt = None
            if tags:
                flt = Filter(
                    must=[FieldCondition(key="tags", match=MatchAny(any=tags))]
                )
            results = await self._qdrant.search(
                collection_name=self.cfg.qdrant_collection,
                query_vector=embedding,
                limit=limit,
                query_filter=flt,
            )
            return [
                {"content": r.payload["content"], "score": r.score, "tags": r.payload.get("tags", [])}
                for r in results
            ]
        except Exception as e:
            logger.debug("Qdrant search failed: %s", e)
            return []

    async def _search_in_memory(
        self,
        query: str,
        embedding: list[float] | None,
        *,
        limit: int,
        tags: list[str] | None,
    ) -> list[dict]:
        """Keyword-based fallback search."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for node in self._nodes.values():
            if tags and not any(t in node.tags for t in tags):
                continue
            # Simple word overlap scoring
            content_words = set(node.content.lower().split())
            overlap = len(query_words & content_words) / max(len(query_words), 1)
            recency_bonus = 1.0 / (1.0 + (time.time() - node.created_at) / 86400)
            score = overlap * 0.8 + recency_bonus * 0.2
            if score > 0:
                scored.append((score, node))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"content": n.content, "score": round(s, 3), "tags": n.tags}
            for s, n in scored[:limit]
        ]

    # ─── Knowledge graph edges ───────────────────────────────────────────────

    async def _infer_edges(self, new_node: MemoryNode) -> None:
        """Auto-connect new node to recent related nodes."""
        recent = list(self._nodes.values())[-20:]  # last 20 nodes
        for existing in recent:
            if existing.id == new_node.id:
                continue
            # Tag overlap → relate
            overlap = set(new_node.tags) & set(existing.tags)
            if overlap:
                edge = MemoryEdge(
                    source_id=new_node.id,
                    target_id=existing.id,
                    relation="relates_to",
                    weight=len(overlap) / max(len(new_node.tags), 1),
                )
                self._edges.append(edge)

    # ─── Consolidation loop ──────────────────────────────────────────────────

    async def _consolidation_loop(self) -> None:
        """Periodically consolidate short-term episodic buffer."""
        while self._running:
            await asyncio.sleep(3600)  # every hour
            try:
                if len(self._episodic_buffer) >= self.cfg.short_term_capacity:
                    logger.info("Consolidating %d episodic memories", len(self._episodic_buffer))
                    self._episodic_buffer.clear()
                    await self._save_to_disk()
            except Exception as e:
                logger.error("Consolidation error: %s", e)

    # ─── Persistence ─────────────────────────────────────────────────────────

    async def _save_to_disk(self) -> None:
        try:
            nodes_path = self.data_dir / "nodes.json"
            edges_path = self.data_dir / "edges.json"
            nodes_path.write_text(
                json.dumps(
                    {k: {**v.__dict__, "embedding": None} for k, v in self._nodes.items()},
                    default=str,
                    indent=2,
                )
            )
            edges_path.write_text(
                json.dumps([e.__dict__ for e in self._edges], default=str, indent=2)
            )
        except Exception as e:
            logger.error("Failed to save memory to disk: %s", e)

    async def _load_from_disk(self) -> None:
        try:
            nodes_path = self.data_dir / "nodes.json"
            if nodes_path.exists():
                data = json.loads(nodes_path.read_text())
                self._nodes = {k: MemoryNode(**v) for k, v in data.items()}

            edges_path = self.data_dir / "edges.json"
            if edges_path.exists():
                data = json.loads(edges_path.read_text())
                self._edges = [MemoryEdge(**e) for e in data]

            logger.info("Loaded %d nodes, %d edges from disk", len(self._nodes), len(self._edges))
        except Exception as e:
            logger.warning("Could not load memory from disk: %s", e)
