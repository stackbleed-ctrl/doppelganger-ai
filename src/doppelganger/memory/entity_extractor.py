"""
Entity Extractor
Pulls named entities from conversation text using Grok.
Feeds the Graphiti KG with structured entity data.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..graphiti_kg import GraphitiKG, Entity

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    name: str
    type: str           # person | place | project | technology | organization | concept | date | emotion
    context: str        # sentence it appeared in
    confidence: float = 0.8
    aliases: list[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)


@dataclass
class ExtractedRelationship:
    source: str         # entity name
    target: str         # entity name
    relation: str       # works_on | knows | uses | located_at | causes | etc.
    context: str
    confidence: float = 0.7


class EntityExtractor:
    """
    Dual-mode entity extraction:
    1. Fast heuristic: regex + capitalization patterns (no LLM cost)
    2. Deep extraction: Grok NER for complex text (on-demand)
    """

    def __init__(self) -> None:
        self._grok = None
        self._entity_cache: dict[str, ExtractedEntity] = {}

    async def _get_grok(self):
        if not self._grok:
            from ...agents.grok_client import get_grok
            self._grok = get_grok()
        return self._grok

    # ─── Fast heuristic extraction ────────────────────────────────────────────

    def extract_fast(self, text: str) -> list[ExtractedEntity]:
        """Regex-based extraction — zero latency, lower accuracy."""
        entities = []
        seen = set()

        # People / Proper nouns: Title Case sequences
        for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', text):
            name = match.group(1)
            if name not in seen and len(name) > 3:
                entities.append(ExtractedEntity(
                    name=name, type="person",
                    context=text[max(0, match.start()-30):match.end()+30],
                    confidence=0.6,
                ))
                seen.add(name)

        # Technologies: camelCase, ALL_CAPS, known patterns
        tech_pattern = r'\b(Python|Rust|React|Docker|Kubernetes|PostgreSQL|Redis|Neo4j|Grok|GPT|LLM|API|REST|GraphQL|TypeScript|FastAPI|Tauri)\b'
        for match in re.finditer(tech_pattern, text, re.IGNORECASE):
            name = match.group(1)
            if name not in seen:
                entities.append(ExtractedEntity(
                    name=name, type="technology",
                    context=text[max(0, match.start()-20):match.end()+20],
                    confidence=0.9,
                ))
                seen.add(name)

        # Dates and times
        date_pattern = r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|today|tomorrow|yesterday|next week|last week|\d{1,2}/\d{1,2}/\d{2,4})\b'
        for match in re.finditer(date_pattern, text, re.IGNORECASE):
            name = match.group(1)
            if name not in seen:
                entities.append(ExtractedEntity(
                    name=name, type="date",
                    context=text[max(0, match.start()-20):match.end()+20],
                    confidence=0.85,
                ))
                seen.add(name)

        # Projects: "the X project", "working on X", "building X"
        project_pattern = r'(?:project|building|working on|developing)\s+([A-Z][a-zA-Z0-9]+)'
        for match in re.finditer(project_pattern, text):
            name = match.group(1)
            if name not in seen:
                entities.append(ExtractedEntity(
                    name=name, type="project",
                    context=text[max(0, match.start()-10):match.end()+30],
                    confidence=0.75,
                ))
                seen.add(name)

        return entities

    # ─── Deep extraction ─────────────────────────────────────────────────────

    async def extract_deep(self, text: str) -> tuple[list[ExtractedEntity], list[ExtractedRelationship]]:
        """
        Grok-powered NER + relationship extraction.
        Use for important long-form text (agent responses, stored memories).
        """
        if len(text) < 30:
            return [], []

        grok = await self._get_grok()

        prompt = f"""\
Extract entities and relationships from this text.

Text: {text[:1000]}

Return JSON with this exact structure:
{{
  "entities": [
    {{"name": "...", "type": "person|place|project|technology|organization|concept|emotion", "confidence": 0.0-1.0, "properties": {{}}}}
  ],
  "relationships": [
    {{"source": "entity_name", "target": "entity_name", "relation": "verb_phrase", "confidence": 0.0-1.0}}
  ]
}}

Only include entities with confidence > 0.6. Max 8 entities, 5 relationships."""

        try:
            from pydantic import BaseModel

            class EntityOut(BaseModel):
                name: str
                type: str = "concept"
                confidence: float = 0.7
                properties: dict = {}

            class RelOut(BaseModel):
                source: str
                target: str
                relation: str
                confidence: float = 0.7

            class ExtractionOut(BaseModel):
                entities: list[EntityOut] = []
                relationships: list[RelOut] = []

            result = await grok.chat_json(
                [{"role": "user", "content": prompt}],
                schema=ExtractionOut,
                temperature=0.1,
                max_tokens=400,
            )

            entities = [
                ExtractedEntity(
                    name=e.name, type=e.type,
                    context=text[:100],
                    confidence=e.confidence,
                    properties=e.properties,
                )
                for e in result.entities
            ]

            rels = [
                ExtractedRelationship(
                    source=r.source, target=r.target,
                    relation=r.relation, context=text[:100],
                    confidence=r.confidence,
                )
                for r in result.relationships
            ]

            return entities, rels

        except Exception as e:
            logger.warning("Deep extraction failed: %s — falling back to fast", e)
            return self.extract_fast(text), []

    # ─── KG integration ──────────────────────────────────────────────────────

    async def extract_and_store(
        self,
        text: str,
        graphiti: GraphitiKG,
        deep: bool = False,
    ) -> list[ExtractedEntity]:
        """Extract entities from text and write them to the KG."""
        if deep:
            entities, relationships = await self.extract_deep(text)
        else:
            entities = self.extract_fast(text)
            relationships = []

        from ..graphiti_kg import Entity, Relationship
        stored_map: dict[str, str] = {}  # name → entity id

        for ext in entities:
            if ext.confidence < 0.6:
                continue
            # Check cache first
            cached = self._entity_cache.get(ext.name.lower())
            if cached:
                stored_map[ext.name] = cached.name
                continue

            entity = Entity(
                name=ext.name,
                type=ext.type,
                properties={**ext.properties, "confidence": ext.confidence},
            )
            await graphiti.upsert_entity(entity)
            stored_map[ext.name] = entity.id
            self._entity_cache[ext.name.lower()] = ext

        # Store relationships
        for rel in relationships:
            if rel.source in stored_map and rel.target in stored_map:
                r = Relationship(
                    source_id=stored_map[rel.source],
                    target_id=stored_map[rel.target],
                    relation=rel.relation,
                    weight=rel.confidence,
                )
                try:
                    await graphiti.add_relationship(r)
                except Exception:
                    pass

        return entities
