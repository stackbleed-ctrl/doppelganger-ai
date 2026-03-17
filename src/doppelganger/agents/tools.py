"""
Agent Tools
Defines the built-in tool schemas for Grok function calling
and the ToolExecutor that dispatches them.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Tool schemas (OpenAI function-call format) ───────────────────────────────

BUILTIN_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Search the user's personal knowledge graph for relevant memories, facts, or past events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "limit": {"type": "integer", "description": "Max results", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_store",
            "description": "Store a new fact or observation in the user's knowledge graph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact or event to remember"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional categorization tags",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_skill",
            "description": "Execute an installed Doppelganger skill by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Name of the skill to run"},
                    "params": {"type": "object", "description": "Skill-specific parameters"},
                },
                "required": ["skill_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current date and time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_info",
            "description": "Get current system metrics: CPU, memory, network.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "world_sim",
            "description": "Run a 'what if' scenario simulation through the reasoning swarm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scenario": {"type": "string", "description": "Scenario description"},
                    "steps": {"type": "integer", "description": "Simulation depth", "default": 4},
                },
                "required": ["scenario"],
            },
        },
    },
]


# ─── Executor ─────────────────────────────────────────────────────────────────

class ToolExecutor:
    """
    Dispatches tool calls to their implementations.
    Memory + skill tools are injected at init time via the MemoryManager and SkillLoader.
    """

    def __init__(self) -> None:
        self._memory_manager = None   # injected after init
        self._skill_loader = None     # injected after init
        self._reasoning_swarm = None  # injected after init

    def inject(self, memory=None, skills=None, reasoning=None) -> None:
        self._memory_manager = memory
        self._skill_loader = skills
        self._reasoning_swarm = reasoning

    def skill_tools(self) -> list[dict]:
        """Dynamically built tool schemas from installed skills."""
        if not self._skill_loader:
            return []
        return self._skill_loader.get_tool_schemas()

    async def execute(self, tool_name: str, args: dict) -> Any:
        logger.debug("Executing tool: %s(%s)", tool_name, args)
        try:
            match tool_name:
                case "get_time":
                    return {"datetime": datetime.now().isoformat(), "timezone": "local"}

                case "system_info":
                    return await self._system_info()

                case "memory_search":
                    if self._memory_manager:
                        results = await self._memory_manager.search(args["query"], limit=args.get("limit", 5))
                        return {"results": results}
                    return {"results": [], "note": "Memory manager not available"}

                case "memory_store":
                    if self._memory_manager:
                        await self._memory_manager.store(args["content"], tags=args.get("tags", []))
                        return {"stored": True}
                    return {"stored": False, "note": "Memory manager not available"}

                case "run_skill":
                    if self._skill_loader:
                        return await self._skill_loader.run(
                            args["skill_name"],
                            args.get("params", {}),
                        )
                    return {"error": "Skill loader not available"}

                case "web_search":
                    return await self._web_search(args["query"])

                case "world_sim":
                    if self._reasoning_swarm:
                        result = await self._reasoning_swarm.simulate(
                            args["scenario"],
                            steps=args.get("steps", 4),
                        )
                        return result
                    return {"error": "Reasoning swarm not available"}

                case _:
                    # Try skill loader as fallback
                    if self._skill_loader:
                        return await self._skill_loader.run(tool_name, args)
                    return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return {"error": str(e)}

    async def _system_info(self) -> dict:
        try:
            import psutil
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_available_gb": round(psutil.virtual_memory().available / 1e9, 2),
                "disk_percent": psutil.disk_usage("/").percent,
                "load_avg": list(psutil.getloadavg()),
            }
        except ImportError:
            return {"error": "psutil not installed"}

    async def _web_search(self, query: str) -> dict:
        """
        Lightweight DuckDuckGo instant-answer search.
        For richer results, users can install the web_search skill.
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_redirect": 1},
                )
                data = resp.json()
                abstract = data.get("AbstractText", "")
                related = [r.get("Text", "") for r in data.get("RelatedTopics", [])[:3]]
                return {"abstract": abstract, "related": related, "query": query}
        except Exception as e:
            return {"error": str(e), "query": query}
