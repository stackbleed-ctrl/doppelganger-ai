"""
Graphiti Temporal Knowledge Graph
Full Neo4j-backed temporal KG replacing the flat JSON store.
Tracks entity relationships over time with bi-temporal versioning.

Schema:
  (Entity)-[:RELATES_TO {since, until, weight}]->(Entity)
  (Entity)-[:HAS_EPISODE]->(Episode)
  (Episode)-[:CONTAINS]->(Fact)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    type: str = "concept"          # person | place | project | concept | preference | emotion
    properties: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Relationship:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str = ""
    target_id: str = ""
    relation: str = ""             # causes | precedes | relates_to | contradicts | part_of
    weight: float = 1.0
    valid_from: float = field(default_factory=time.time)
    valid_until: float | None = None   # None = still valid
    properties: dict = field(default_factory=dict)


@dataclass
class Episode:
    """A discrete memory episode — a moment in time with context."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    source: str = "agent"
    persona_id: str = "default"
    entities: list[str] = field(default_factory=list)  # entity IDs
    embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class GraphitiKG:
    """
    Temporal knowledge graph with Neo4j backend.
    Falls back to in-memory graph if Neo4j is unavailable.
    """

    def __init__(self, neo4j_url: str, user: str, password: str) -> None:
        self.neo4j_url = neo4j_url
        self.user = user
        self.password = password
        self._driver = None
        self._fallback: dict[str, Any] = {
            "entities": {},
            "relationships": [],
            "episodes": [],
        }
        self._using_fallback = False

    async def connect(self) -> None:
        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                self.neo4j_url,
                auth=(self.user, self.password),
            )
            await self._driver.verify_connectivity()
            await self._init_schema()
            logger.info("Graphiti KG connected to Neo4j at %s", self.neo4j_url)
        except Exception as e:
            logger.warning("Neo4j unavailable (%s) — using in-memory graph", e)
            self._using_fallback = True

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()

    # ─── Schema init ─────────────────────────────────────────────────────────

    async def _init_schema(self) -> None:
        async with self._driver.session() as session:
            await session.run("CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
            await session.run("CREATE CONSTRAINT episode_id IF NOT EXISTS FOR (ep:Episode) REQUIRE ep.id IS UNIQUE")
            await session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)")
            await session.run("CREATE INDEX episode_created IF NOT EXISTS FOR (ep:Episode) ON (ep.created_at)")
            await session.run("CREATE INDEX episode_persona IF NOT EXISTS FOR (ep:Episode) ON (ep.persona_id)")

    # ─── Entity operations ────────────────────────────────────────────────────

    async def upsert_entity(self, entity: Entity) -> Entity:
        if self._using_fallback:
            self._fallback["entities"][entity.id] = entity
            return entity

        async with self._driver.session() as session:
            await session.run("""
                MERGE (e:Entity {id: $id})
                SET e.name = $name,
                    e.type = $type,
                    e.properties = $properties,
                    e.updated_at = $updated_at
                ON CREATE SET e.created_at = $created_at
            """, id=entity.id, name=entity.name, type=entity.type,
                properties=str(entity.properties), updated_at=entity.updated_at,
                created_at=entity.created_at)
        return entity

    async def get_entity(self, name: str) -> Entity | None:
        if self._using_fallback:
            for e in self._fallback["entities"].values():
                if e.name.lower() == name.lower():
                    return e
            return None

        async with self._driver.session() as session:
            result = await session.run(
                "MATCH (e:Entity {name: $name}) RETURN e LIMIT 1", name=name
            )
            record = await result.single()
            if record:
                n = record["e"]
                return Entity(id=n["id"], name=n["name"], type=n["type"],
                               created_at=n["created_at"], updated_at=n["updated_at"])
        return None

    async def find_entities(self, query: str, limit: int = 10) -> list[Entity]:
        if self._using_fallback:
            q = query.lower()
            return [e for e in self._fallback["entities"].values()
                    if q in e.name.lower() or q in str(e.properties).lower()][:limit]

        async with self._driver.session() as session:
            result = await session.run("""
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower($query)
                RETURN e LIMIT $limit
            """, query=query, limit=limit)
            entities = []
            async for record in result:
                n = record["e"]
                entities.append(Entity(id=n["id"], name=n["name"], type=n.get("type", "concept")))
            return entities

    # ─── Relationship operations ──────────────────────────────────────────────

    async def add_relationship(self, rel: Relationship) -> Relationship:
        if self._using_fallback:
            self._fallback["relationships"].append(rel)
            return rel

        async with self._driver.session() as session:
            await session.run("""
                MATCH (a:Entity {id: $source_id}), (b:Entity {id: $target_id})
                CREATE (a)-[r:RELATES_TO {
                    id: $id,
                    relation: $relation,
                    weight: $weight,
                    valid_from: $valid_from,
                    valid_until: $valid_until
                }]->(b)
            """, id=rel.id, source_id=rel.source_id, target_id=rel.target_id,
                relation=rel.relation, weight=rel.weight,
                valid_from=rel.valid_from, valid_until=rel.valid_until)
        return rel

    async def expire_relationship(self, rel_id: str) -> None:
        """Mark a relationship as no longer valid (temporal invalidation)."""
        now = time.time()
        if self._using_fallback:
            for r in self._fallback["relationships"]:
                if r.id == rel_id:
                    r.valid_until = now
            return

        async with self._driver.session() as session:
            await session.run(
                "MATCH ()-[r:RELATES_TO {id: $id}]-() SET r.valid_until = $now",
                id=rel_id, now=now
            )

    async def get_relationships(
        self, entity_id: str, at_time: float | None = None
    ) -> list[Relationship]:
        t = at_time or time.time()
        if self._using_fallback:
            return [
                r for r in self._fallback["relationships"]
                if (r.source_id == entity_id or r.target_id == entity_id)
                and r.valid_from <= t
                and (r.valid_until is None or r.valid_until > t)
            ]

        async with self._driver.session() as session:
            result = await session.run("""
                MATCH (e:Entity {id: $id})-[r:RELATES_TO]-(other:Entity)
                WHERE r.valid_from <= $t AND (r.valid_until IS NULL OR r.valid_until > $t)
                RETURN r, other
            """, id=entity_id, t=t)
            rels = []
            async for record in result:
                r = record["r"]
                rels.append(Relationship(
                    id=r["id"], source_id=entity_id,
                    target_id=record["other"]["id"],
                    relation=r["relation"], weight=r["weight"],
                    valid_from=r["valid_from"], valid_until=r.get("valid_until"),
                ))
            return rels

    # ─── Episode operations ───────────────────────────────────────────────────

    async def add_episode(self, episode: Episode) -> Episode:
        # Extract entities from content
        extracted = await self._extract_entities(episode.content)
        for entity in extracted:
            await self.upsert_entity(entity)
            episode.entities.append(entity.id)

        if self._using_fallback:
            self._fallback["episodes"].append(episode)
            return episode

        async with self._driver.session() as session:
            await session.run("""
                CREATE (ep:Episode {
                    id: $id,
                    content: $content,
                    source: $source,
                    persona_id: $persona_id,
                    created_at: $created_at,
                    tags: $tags
                })
            """, id=episode.id, content=episode.content, source=episode.source,
                persona_id=episode.persona_id, created_at=episode.created_at,
                tags=episode.tags)

            # Link to entities
            for entity_id in episode.entities:
                await session.run("""
                    MATCH (ep:Episode {id: $ep_id}), (e:Entity {id: $e_id})
                    CREATE (ep)-[:MENTIONS]->(e)
                """, ep_id=episode.id, e_id=entity_id)

        return episode

    async def search_episodes(
        self,
        query: str,
        persona_id: str | None = None,
        limit: int = 10,
        since: float | None = None,
    ) -> list[Episode]:
        if self._using_fallback:
            q = query.lower()
            results = [
                ep for ep in self._fallback["episodes"]
                if q in ep.content.lower()
                and (persona_id is None or ep.persona_id == persona_id)
                and (since is None or ep.created_at >= since)
            ]
            return sorted(results, key=lambda e: e.created_at, reverse=True)[:limit]

        async with self._driver.session() as session:
            cypher = """
                MATCH (ep:Episode)
                WHERE toLower(ep.content) CONTAINS toLower($query)
                AND ($persona_id IS NULL OR ep.persona_id = $persona_id)
                AND ($since IS NULL OR ep.created_at >= $since)
                RETURN ep ORDER BY ep.created_at DESC LIMIT $limit
            """
            result = await session.run(cypher, query=query, persona_id=persona_id,
                                        since=since, limit=limit)
            episodes = []
            async for record in result:
                ep = record["ep"]
                episodes.append(Episode(
                    id=ep["id"], content=ep["content"],
                    source=ep["source"], persona_id=ep["persona_id"],
                    created_at=ep["created_at"], tags=list(ep.get("tags", [])),
                ))
            return episodes

    async def get_timeline(
        self, hours: int = 24, persona_id: str | None = None
    ) -> list[Episode]:
        since = time.time() - hours * 3600
        return await self.search_episodes("", persona_id=persona_id, since=since, limit=200)

    async def get_entity_history(self, entity_name: str) -> list[Episode]:
        """All episodes mentioning a specific entity."""
        entity = await self.get_entity(entity_name)
        if not entity:
            return []

        if self._using_fallback:
            return [ep for ep in self._fallback["episodes"] if entity.id in ep.entities]

        async with self._driver.session() as session:
            result = await session.run("""
                MATCH (ep:Episode)-[:MENTIONS]->(e:Entity {id: $id})
                RETURN ep ORDER BY ep.created_at DESC LIMIT 50
            """, id=entity.id)
            episodes = []
            async for record in result:
                ep = record["ep"]
                episodes.append(Episode(
                    id=ep["id"], content=ep["content"],
                    source=ep.get("source", "agent"),
                    persona_id=ep.get("persona_id", "default"),
                    created_at=ep["created_at"],
                ))
            return episodes

    # ─── Entity extraction ────────────────────────────────────────────────────

    async def _extract_entities(self, text: str) -> list[Entity]:
        """Heuristic entity extraction — proper NER via Grok optional."""
        import re
        entities = []
        # Capitalized multi-word phrases as person/project names
        matches = re.findall(r'\b([A-Z][a-z]+ (?:[A-Z][a-z]+ )*[A-Z][a-z]+)\b', text)
        for match in set(matches):
            existing = await self.get_entity(match)
            if not existing:
                entities.append(Entity(name=match, type="person"))
        # Single capitalized words that aren't sentence starters
        words = text.split()
        for i, word in enumerate(words):
            if i > 0 and word[0].isupper() and len(word) > 3:
                clean = word.strip('.,!?;:')
                existing = await self.get_entity(clean)
                if not existing and clean.isalpha():
                    entities.append(Entity(name=clean, type="concept"))
        return entities[:5]  # cap to avoid noise

    # ─── Stats ────────────────────────────────────────────────────────────────

    async def stats(self) -> dict:
        if self._using_fallback:
            return {
                "backend": "in-memory",
                "entities": len(self._fallback["entities"]),
                "relationships": len(self._fallback["relationships"]),
                "episodes": len(self._fallback["episodes"]),
            }
        async with self._driver.session() as session:
            r = await session.run("""
                MATCH (e:Entity) WITH count(e) as entities
                MATCH (ep:Episode) WITH entities, count(ep) as episodes
                RETURN entities, episodes
            """)
            rec = await r.single()
            return {
                "backend": "neo4j",
                "entities": rec["entities"] if rec else 0,
                "episodes": rec["episodes"] if rec else 0,
            }
