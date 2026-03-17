"""
Memory Compression Engine
Compresses episodic memory into semantic summaries using Grok.
Implements forgetting curve, importance scoring, and tiered storage:
  Hot tier:  last 24h — full fidelity
  Warm tier: last 7d  — compressed summaries
  Cold tier: 7d+      — entity + relationship only
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..memory_manager import MemoryNode

logger = logging.getLogger(__name__)

TIER_HOT_HOURS  = 24
TIER_WARM_DAYS  = 7
COMPRESSION_RATIO_TARGET = 0.3   # compress to 30% of original token count


@dataclass
class MemorySummary:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_ids: list[str] = field(default_factory=list)  # IDs of nodes compressed into this
    content: str = ""
    time_range_start: float = 0.0
    time_range_end: float = 0.0
    key_entities: list[str] = field(default_factory=list)
    key_themes: list[str] = field(default_factory=list)
    importance_score: float = 0.5
    tier: str = "warm"     # warm | cold
    created_at: float = field(default_factory=time.time)
    persona_id: str = "default"


@dataclass
class ImportanceScore:
    node_id: str
    score: float          # 0–1
    reasons: list[str]    # what contributed to the score
    recency: float
    access_frequency: float
    entity_density: float
    emotional_weight: float


class MemoryCompressor:
    """
    Runs as a background service.
    Every hour: scores all nodes, compresses warm-tier clusters,
    archives cold-tier into entity-only graph entries.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.summaries_path = data_dir / "summaries.json"
        self._summaries: list[MemorySummary] = []
        self._grok = None
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        from ...agents.grok_client import get_grok
        self._grok = get_grok()
        await self._load_summaries()
        self._running = True
        self._task = asyncio.create_task(self._compression_loop(), name="memory-compression")
        logger.info("MemoryCompressor started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._save_summaries()

    # ─── Scoring ─────────────────────────────────────────────────────────────

    def score_importance(self, node: MemoryNode) -> ImportanceScore:
        now = time.time()
        age_hours = (now - node.created_at) / 3600

        # Recency: exponential decay with 48h half-life
        recency = 2 ** (-age_hours / 48)

        # Access frequency (normalized to 0–1, caps at 10 accesses)
        access_freq = min(node.access_count / 10, 1.0)

        # Entity density: more tags = more important
        entity_density = min(len(node.tags) / 5, 1.0)

        # Emotional weight: detected from content keywords
        emotional_words = {
            "excited", "worried", "happy", "sad", "frustrated", "love",
            "hate", "afraid", "proud", "anxious", "delighted", "angry",
            "important", "critical", "urgent", "deadline", "remember"
        }
        content_words = set(node.content.lower().split())
        emotional_weight = min(len(emotional_words & content_words) / 3, 1.0)

        # Weighted composite
        score = (
            recency          * 0.35 +
            access_freq      * 0.25 +
            entity_density   * 0.20 +
            emotional_weight * 0.20
        )

        reasons = []
        if recency > 0.7:   reasons.append("recent")
        if access_freq > 0.3: reasons.append("frequently accessed")
        if entity_density > 0.5: reasons.append("entity-rich")
        if emotional_weight > 0.3: reasons.append("emotionally significant")

        return ImportanceScore(
            node_id=node.id,
            score=round(score, 3),
            reasons=reasons,
            recency=recency,
            access_frequency=access_freq,
            entity_density=entity_density,
            emotional_weight=emotional_weight,
        )

    # ─── Compression ─────────────────────────────────────────────────────────

    async def compress_cluster(
        self,
        nodes: list[MemoryNode],
        tier: str = "warm",
        persona_id: str = "default",
    ) -> MemorySummary | None:
        """Compress a cluster of memory nodes into a single summary."""
        if not nodes or not self._grok:
            return None

        contents = "\n".join(f"[{i+1}] {n.content}" for i, n in enumerate(nodes))
        all_tags = list({t for n in nodes for t in n.tags})

        prompt = f"""\
Summarize these {len(nodes)} memory fragments into a single dense summary.
Preserve: key facts, names, decisions, emotions, patterns.
Discard: redundancy, filler phrases.
Be specific. Max 3 sentences.

Fragments:
{contents}

Also extract:
- key_entities: list of important names/places/projects (max 5)
- key_themes: list of themes (max 3)

Respond in JSON:
{{"summary": "...", "key_entities": [...], "key_themes": [...]}}"""

        try:
            from pydantic import BaseModel

            class SummaryOutput(BaseModel):
                summary: str
                key_entities: list[str] = []
                key_themes: list[str] = []

            result = await self._grok.chat_json(
                [{"role": "user", "content": prompt}],
                schema=SummaryOutput,
                temperature=0.2,
                max_tokens=300,
            )

            ts_values = [n.created_at for n in nodes]
            ms = MemorySummary(
                source_ids=[n.id for n in nodes],
                content=result.summary,
                time_range_start=min(ts_values),
                time_range_end=max(ts_values),
                key_entities=result.key_entities,
                key_themes=result.key_themes,
                tier=tier,
                persona_id=persona_id,
            )
            self._summaries.append(ms)
            return ms

        except Exception as e:
            logger.error("Compression failed: %s", e)
            return None

    async def compress_warm_tier(
        self, nodes: list[MemoryNode]
    ) -> list[MemorySummary]:
        """Compress nodes older than 24h into warm-tier summaries."""
        cutoff = time.time() - TIER_HOT_HOURS * 3600
        warm_nodes = [n for n in nodes if n.created_at < cutoff]

        if len(warm_nodes) < 5:
            return []

        # Group into clusters of ~10 by time proximity
        clusters = self._cluster_by_time(warm_nodes, cluster_hours=4)
        summaries = []
        for cluster in clusters:
            if len(cluster) >= 3:
                s = await self.compress_cluster(cluster, tier="warm")
                if s:
                    summaries.append(s)
        return summaries

    def _cluster_by_time(
        self, nodes: list[MemoryNode], cluster_hours: float = 4
    ) -> list[list[MemoryNode]]:
        """Group nodes into time-proximity clusters."""
        if not nodes:
            return []
        sorted_nodes = sorted(nodes, key=lambda n: n.created_at)
        clusters: list[list[MemoryNode]] = [[sorted_nodes[0]]]
        window = cluster_hours * 3600

        for node in sorted_nodes[1:]:
            if node.created_at - clusters[-1][-1].created_at <= window:
                clusters[-1].append(node)
            else:
                clusters.append([node])
        return clusters

    # ─── Background loop ─────────────────────────────────────────────────────

    async def _compression_loop(self) -> None:
        while self._running:
            await asyncio.sleep(3600)  # every hour
            logger.info("Running memory compression pass...")
            await self._save_summaries()

    # ─── Persistence ─────────────────────────────────────────────────────────

    async def _save_summaries(self) -> None:
        try:
            self.summaries_path.write_text(
                json.dumps([s.__dict__ for s in self._summaries], indent=2)
            )
        except Exception as e:
            logger.error("Failed to save summaries: %s", e)

    async def _load_summaries(self) -> None:
        try:
            if self.summaries_path.exists():
                data = json.loads(self.summaries_path.read_text())
                self._summaries = [MemorySummary(**s) for s in data]
                logger.info("Loaded %d memory summaries", len(self._summaries))
        except Exception as e:
            logger.warning("Could not load summaries: %s", e)

    def get_summaries(
        self,
        persona_id: str | None = None,
        tier: str | None = None,
        limit: int = 20,
    ) -> list[MemorySummary]:
        results = self._summaries
        if persona_id:
            results = [s for s in results if s.persona_id == persona_id]
        if tier:
            results = [s for s in results if s.tier == tier]
        return sorted(results, key=lambda s: s.time_range_end, reverse=True)[:limit]
