"""
Obsidian Vault Importer
Recursively reads an Obsidian vault, parses markdown + frontmatter,
extracts wiki-links as relationships, and imports into Doppelganger memory.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..memory_manager import MemoryManager

logger = logging.getLogger(__name__)


@dataclass
class ObsidianNote:
    title: str
    content: str
    path: str
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)       # [[wiki links]]
    frontmatter: dict = field(default_factory=dict)
    modified_at: float = field(default_factory=time.time)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown."""
    if not text.startswith("---"):
        return {}, text
    try:
        end = text.index("---", 3)
        fm_block = text[3:end].strip()
        body = text[end+3:].strip()
        fm: dict = {}
        for line in fm_block.split("\n"):
            if ":" in line:
                key, _, val = line.partition(":")
                fm[key.strip()] = val.strip()
        return fm, body
    except ValueError:
        return {}, text


def _extract_wiki_links(text: str) -> list[str]:
    return re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', text)


def _extract_tags(text: str, frontmatter: dict) -> list[str]:
    tags = []
    # From frontmatter tags field
    if "tags" in frontmatter:
        raw = frontmatter["tags"]
        tags.extend(t.strip().lstrip("#") for t in raw.replace(",", " ").split())
    # Inline #tags
    tags.extend(re.findall(r'#([a-zA-Z][a-zA-Z0-9_-]+)', text))
    return list(set(tags))


def scan_vault(vault_path: str) -> list[ObsidianNote]:
    """Recursively scan an Obsidian vault directory."""
    vault = Path(vault_path)
    if not vault.exists():
        raise FileNotFoundError(f"Vault not found: {vault_path}")

    notes = []
    for md_file in vault.rglob("*.md"):
        try:
            raw = md_file.read_text(encoding="utf-8")
            fm, body = _parse_frontmatter(raw)
            title = fm.get("title", md_file.stem)
            note = ObsidianNote(
                title=title,
                content=body,
                path=str(md_file.relative_to(vault)),
                tags=_extract_tags(body, fm),
                links=_extract_wiki_links(raw),
                frontmatter=fm,
                modified_at=md_file.stat().st_mtime,
            )
            notes.append(note)
        except Exception as e:
            logger.warning("Could not read %s: %s", md_file, e)

    logger.info("Scanned %d notes from vault: %s", len(notes), vault_path)
    return notes


async def import_vault(
    vault_path: str,
    memory: MemoryManager,
    batch_size: int = 20,
    skip_empty: bool = True,
) -> dict:
    """Import an Obsidian vault into Doppelganger memory."""
    notes = scan_vault(vault_path)
    imported = 0
    skipped = 0

    for i in range(0, len(notes), batch_size):
        batch = notes[i:i+batch_size]
        tasks = []
        for note in batch:
            content = note.content.strip()
            if skip_empty and len(content) < 20:
                skipped += 1
                continue
            # Use first 500 chars of content as memory
            summary = f"[Obsidian: {note.title}] {content[:500]}"
            tags = note.tags + ["obsidian", "imported"]
            if note.frontmatter.get("type"):
                tags.append(note.frontmatter["type"])

            tasks.append(memory.store(
                summary,
                tags=tags,
                source="obsidian",
                entity_type="note",
                metadata={
                    "vault_path": note.path,
                    "links": note.links,
                    "modified_at": note.modified_at,
                },
            ))

        await asyncio.gather(*tasks)
        imported += len(tasks)
        await asyncio.sleep(0.1)  # avoid hammering

    return {
        "total_notes": len(notes),
        "imported": imported,
        "skipped": skipped,
        "vault_path": vault_path,
    }
