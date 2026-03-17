"""
Notion Importer
Imports pages and databases from Notion via the official API.
Set NOTION_API_KEY env var.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from ..memory_manager import MemoryManager

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _get_headers() -> dict:
    token = os.environ.get("NOTION_API_KEY", "")
    if not token:
        raise ValueError("NOTION_API_KEY environment variable not set")
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _extract_rich_text(rt_list: list) -> str:
    """Flatten Notion rich text array to plain string."""
    return "".join(item.get("plain_text", "") for item in rt_list)


def _extract_block_text(block: dict) -> str:
    """Extract text from a Notion block."""
    btype = block.get("type", "")
    data = block.get(btype, {})
    rt = data.get("rich_text", [])
    text = _extract_rich_text(rt)

    prefix = {
        "heading_1": "# ", "heading_2": "## ", "heading_3": "### ",
        "bulleted_list_item": "• ", "numbered_list_item": "1. ",
        "to_do": "☐ " if not data.get("checked") else "☑ ",
        "quote": "> ", "code": "```\n", "callout": "💡 ",
    }.get(btype, "")

    suffix = "\n```" if btype == "code" else ""
    return f"{prefix}{text}{suffix}" if text else ""


async def _get_block_children(client: httpx.AsyncClient, block_id: str) -> str:
    """Recursively fetch block children and return as markdown."""
    parts = []
    cursor = None

    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        resp = await client.get(
            f"{NOTION_API}/blocks/{block_id}/children",
            params=params,
            headers=_get_headers(),
        )
        if resp.status_code != 200:
            break

        data = resp.json()
        for block in data.get("results", []):
            text = _extract_block_text(block)
            if text:
                parts.append(text)
            if block.get("has_children"):
                child_text = await _get_block_children(client, block["id"])
                if child_text:
                    parts.append(child_text)

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return "\n".join(parts)


async def import_notion(
    memory: MemoryManager,
    page_ids: list[str] | None = None,
    import_all: bool = False,
    limit: int = 50,
) -> dict:
    """
    Import Notion pages into Doppelganger memory.
    Args:
        page_ids: specific page IDs to import
        import_all: search all accessible pages
        limit: max pages to import
    """
    headers = _get_headers()
    imported = 0
    errors = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Discover pages
        if import_all or not page_ids:
            resp = await client.post(
                f"{NOTION_API}/search",
                json={"filter": {"value": "page", "property": "object"}, "page_size": limit},
                headers=headers,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            page_ids = [r["id"] for r in results]

        # Import each page
        for page_id in page_ids[:limit]:
            try:
                # Get page metadata
                page_resp = await client.get(f"{NOTION_API}/pages/{page_id}", headers=headers)
                if page_resp.status_code != 200:
                    continue
                page = page_resp.json()

                # Extract title
                props = page.get("properties", {})
                title = ""
                for prop in props.values():
                    if prop.get("type") == "title":
                        title = _extract_rich_text(prop.get("title", []))
                        break
                title = title or "Untitled"

                # Get page content
                content = await _get_block_children(client, page_id)
                if not content.strip():
                    continue

                # Store in memory
                summary = f"[Notion: {title}]\n{content[:800]}"
                tags = ["notion", "imported"]

                # Extract Notion tags if available
                for prop_name, prop in props.items():
                    if prop.get("type") == "multi_select":
                        for opt in prop.get("multi_select", []):
                            tags.append(opt.get("name", "").lower())

                await memory.store(
                    summary,
                    tags=list(set(tags)),
                    source="notion",
                    entity_type="note",
                    metadata={
                        "notion_page_id": page_id,
                        "notion_title": title,
                        "notion_url": page.get("url", ""),
                    },
                )
                imported += 1
                await asyncio.sleep(0.2)  # Notion rate limit

            except Exception as e:
                logger.error("Failed to import page %s: %s", page_id, e)
                errors += 1

    return {"imported": imported, "errors": errors, "total_attempted": len(page_ids or [])}
