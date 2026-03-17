"""
Doppelganger Plugin SDK
The official toolkit for building, testing, and publishing skills.

Usage:
    from doppelganger.sdk import SkillBase, skill_input, skill_output, registry

    class MySkill(SkillBase):
        name = "my_skill"
        description = "Does something useful"
        version = "1.0.0"
        author = "your-handle"

        @skill_input({"query": str})
        @skill_output({"result": str})
        async def run(self, params: dict) -> dict:
            return {"result": f"processed: {params['query']}"}
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Type

logger = logging.getLogger(__name__)


# ─── Decorators ───────────────────────────────────────────────────────────────

def skill_input(schema: dict) -> Callable:
    """Decorator: declare and validate input parameters."""
    def decorator(fn: Callable) -> Callable:
        fn._input_schema = schema
        @wraps(fn)
        async def wrapper(self, params: dict, *args, **kwargs):
            # Type coercion + validation
            validated = {}
            for key, typ in schema.items():
                if key in params:
                    try:
                        validated[key] = typ(params[key])
                    except (TypeError, ValueError) as e:
                        return {"error": f"Invalid param '{key}': {e}"}
                elif hasattr(fn, '_required') and key in fn._required:
                    return {"error": f"Missing required param: {key}"}
            return await fn(self, {**params, **validated}, *args, **kwargs)
        return wrapper
    return decorator


def skill_output(schema: dict) -> Callable:
    """Decorator: declare output schema (documentation only, no enforcement)."""
    def decorator(fn: Callable) -> Callable:
        fn._output_schema = schema
        return fn
    return decorator


def requires_env(*env_vars: str) -> Callable:
    """Decorator: check required environment variables before running."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(self, params: dict, *args, **kwargs):
            import os
            missing = [v for v in env_vars if not os.environ.get(v)]
            if missing:
                return {"error": f"Missing environment variables: {', '.join(missing)}"}
            return await fn(self, params, *args, **kwargs)
        return wrapper
    return decorator


def cached(ttl_sec: float = 300) -> Callable:
    """Decorator: cache skill results for TTL seconds."""
    def decorator(fn: Callable) -> Callable:
        _cache: dict[str, tuple[float, Any]] = {}
        @wraps(fn)
        async def wrapper(self, params: dict, *args, **kwargs):
            key = json.dumps(params, sort_keys=True, default=str)
            if key in _cache:
                ts, result = _cache[key]
                if time.time() - ts < ttl_sec:
                    return result
            result = await fn(self, params, *args, **kwargs)
            _cache[key] = (time.time(), result)
            return result
        return wrapper
    return decorator


# ─── Base class ───────────────────────────────────────────────────────────────

class SkillBase:
    """
    Base class for all Doppelganger skills.
    Subclass this and implement `run()`.
    """

    # Class-level metadata — override in subclass
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    tags: list[str] = []
    timeout_sec: float = 30.0
    permissions: list[str] = []      # "network" | "filesystem" | "subprocess"
    min_sdk_version: str = "1.0.0"

    # Set by the loader at runtime
    _bus: Any = None
    _memory: Any = None
    _grok: Any = None

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            cls.name = cls.__name__.lower().replace("skill", "")

    async def run(self, params: dict) -> dict:
        """Override this method to implement your skill."""
        raise NotImplementedError(f"{self.__class__.__name__} must implement run()")

    # ─── SDK helpers available to all skills ─────────────────────────────────

    async def ask_grok(self, prompt: str, temperature: float = 0.7) -> str:
        """Ask Grok a question. Returns text response."""
        if not self._grok:
            from ..agents.grok_client import get_grok
            self._grok = get_grok()
        return await self._grok.chat(
            [{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=1000,
        )

    async def remember(self, content: str, tags: list[str] | None = None) -> None:
        """Store something in the user's memory."""
        if self._memory:
            await self._memory.store(content, tags=tags or [self.name], source=self.name)

    async def recall(self, query: str, limit: int = 5) -> list[str]:
        """Search the user's memory. Returns list of relevant content strings."""
        if not self._memory:
            return []
        results = await self._memory.search(query, limit=limit)
        return [r["content"] for r in results]

    async def emit(self, topic: str, payload: dict) -> None:
        """Publish an event to the Doppelganger event bus."""
        if self._bus:
            await self._bus.publish_simple(topic, payload=payload, source=self.name)

    def log(self, message: str) -> None:
        logger.info("[skill:%s] %s", self.name, message)

    def to_manifest(self) -> dict:
        """Generate manifest.json content from class definition."""
        # Collect parameter schema from run() type hints
        hints = {}
        try:
            sig = inspect.signature(self.run)
            for pname, param in sig.parameters.items():
                if pname in ("self", "params"):
                    continue
                if param.annotation != inspect.Parameter.empty:
                    hints[pname] = {"type": param.annotation.__name__}
        except Exception:
            pass

        # Also check _input_schema from decorator
        input_schema = getattr(self.run, '_input_schema', {})
        properties = {
            k: {"type": v.__name__ if isinstance(v, type) else str(v), "description": ""}
            for k, v in input_schema.items()
        }

        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "timeout_sec": self.timeout_sec,
            "permissions": self.permissions,
            "min_sdk_version": self.min_sdk_version,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(input_schema.keys()),
            },
        }


# ─── Skill Registry ───────────────────────────────────────────────────────────

@dataclass
class RegistryEntry:
    name: str
    version: str
    description: str
    author: str
    tags: list[str]
    download_url: str
    manifest_url: str
    stars: int = 0
    downloads: int = 0
    verified: bool = False
    published_at: float = field(default_factory=time.time)


class SkillRegistry:
    """
    Public skill registry client.
    Connects to the Doppelganger skill registry API (self-hostable).
    Falls back to GitHub-based discovery if registry unavailable.
    """

    REGISTRY_URL = "https://registry.doppelganger.ai/v1"
    GITHUB_TOPIC = "doppelganger-skill"

    def __init__(self, registry_url: str | None = None) -> None:
        self._url = registry_url or self.REGISTRY_URL
        self._cache: list[RegistryEntry] = []
        self._last_fetch: float = 0.0

    async def search(
        self,
        query: str = "",
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[RegistryEntry]:
        """Search the public skill registry."""
        await self._refresh()

        results = self._cache
        if query:
            q = query.lower()
            results = [
                e for e in results
                if q in e.name.lower() or q in e.description.lower()
            ]
        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]

        return sorted(results, key=lambda e: e.downloads, reverse=True)[:limit]

    async def get(self, name: str) -> RegistryEntry | None:
        """Get a specific skill by name."""
        await self._refresh()
        return next((e for e in self._cache if e.name == name), None)

    async def install(self, name: str, skills_dir: Path) -> dict:
        """
        Download and install a skill from the registry.
        Returns install result dict.
        """
        entry = await self.get(name)
        if not entry:
            return {"error": f"Skill '{name}' not found in registry"}

        import httpx
        skill_dir = skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Download manifest
                manifest_resp = await client.get(entry.manifest_url)
                manifest_resp.raise_for_status()
                (skill_dir / "manifest.json").write_text(manifest_resp.text)

                # Download skill.py
                skill_resp = await client.get(entry.download_url)
                skill_resp.raise_for_status()
                (skill_dir / "skill.py").write_text(skill_resp.text)

            return {
                "installed": True,
                "name": name,
                "version": entry.version,
                "path": str(skill_dir),
            }
        except Exception as e:
            return {"error": f"Install failed: {e}"}

    async def publish(
        self,
        skill_dir: Path,
        api_key: str,
    ) -> dict:
        """
        Publish a skill to the public registry.
        Requires an API key from registry.doppelganger.ai.
        """
        manifest_path = skill_dir / "manifest.json"
        skill_path    = skill_dir / "skill.py"

        if not manifest_path.exists():
            return {"error": "manifest.json not found"}
        if not skill_path.exists():
            return {"error": "skill.py not found"}

        manifest = json.loads(manifest_path.read_text())
        skill_code = skill_path.read_text()

        import httpx
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._url}/skills",
                    json={
                        "manifest": manifest,
                        "skill_code": skill_code,
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"Registry error: {e.response.status_code}"}
        except Exception as e:
            # If registry unavailable, guide to GitHub submission
            return {
                "error": str(e),
                "fallback": "Registry unavailable. Submit via GitHub: "
                           "https://github.com/doppelganger-ai/skills/pulls",
            }

    async def _refresh(self) -> None:
        """Refresh registry cache if stale (TTL: 10 minutes)."""
        if time.time() - self._last_fetch < 600 and self._cache:
            return
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self._url}/skills?limit=200")
                if resp.status_code == 200:
                    data = resp.json()
                    self._cache = [RegistryEntry(**e) for e in data.get("skills", [])]
                    self._last_fetch = time.time()
                    return
        except Exception:
            pass

        # GitHub fallback: search repos with doppelganger-skill topic
        await self._github_discovery()

    async def _github_discovery(self) -> None:
        """Discover skills from GitHub repos tagged with doppelganger-skill."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    params={
                        "q": f"topic:{self.GITHUB_TOPIC}",
                        "sort": "stars",
                        "per_page": 50,
                    },
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code != 200:
                    return
                items = resp.json().get("items", [])
                self._cache = [
                    RegistryEntry(
                        name=item["name"].replace("doppelganger-skill-", ""),
                        version="unknown",
                        description=item.get("description", ""),
                        author=item["owner"]["login"],
                        tags=item.get("topics", []),
                        download_url=f"{item['html_url']}/raw/main/skill.py",
                        manifest_url=f"{item['html_url']}/raw/main/manifest.json",
                        stars=item.get("stargazers_count", 0),
                    )
                    for item in items
                ]
                self._last_fetch = time.time()
        except Exception as e:
            logger.warning("GitHub discovery failed: %s", e)


# ─── SDK CLI tools ────────────────────────────────────────────────────────────

class SkillScaffolder:
    """Generate skill boilerplate from template."""

    TEMPLATE_MANIFEST = """{
  "name": "{name}",
  "version": "1.0.0",
  "description": "{description}",
  "author": "{author}",
  "timeout_sec": 30,
  "parameters": {{
    "type": "object",
    "properties": {{
      "input": {{
        "type": "string",
        "description": "Primary input for this skill"
      }}
    }},
    "required": ["input"]
  }},
  "permissions": []
}}
"""

    TEMPLATE_SKILL = '''"""
{name} Skill
{description}
"""

from doppelganger.sdk import SkillBase, skill_input, skill_output


class {class_name}(SkillBase):
    name = "{name}"
    version = "1.0.0"
    description = "{description}"
    author = "{author}"

    @skill_input({{"input": str}})
    @skill_output({{"result": str}})
    async def run(self, params: dict) -> dict:
        input_val = params.get("input", "")
        
        # Your skill logic here
        # Use self.ask_grok(), self.remember(), self.recall()
        
        result = f"Processed: {{input_val}}"
        return {{"result": result}}


# Doppelganger discovers this automatically
skill = {class_name}()
'''

    TEMPLATE_TEST = '''"""
Tests for {name} skill.
Run: pytest tests/test_{name}.py
"""

import asyncio
import pytest
from skill import skill


@pytest.mark.asyncio
async def test_basic_run():
    result = await skill.run({{"input": "test input"}})
    assert "result" in result
    assert "error" not in result


@pytest.mark.asyncio  
async def test_missing_input():
    result = await skill.run({{}})
    # Should handle gracefully
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_empty_input():
    result = await skill.run({{"input": ""}})
    assert isinstance(result, dict)
'''

    @classmethod
    def scaffold(cls, name: str, description: str, author: str, output_dir: Path) -> dict:
        skill_dir = output_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)

        class_name = "".join(w.capitalize() for w in name.split("_")) + "Skill"

        (skill_dir / "manifest.json").write_text(
            cls.TEMPLATE_MANIFEST.format(name=name, description=description, author=author)
        )
        (skill_dir / "skill.py").write_text(
            cls.TEMPLATE_SKILL.format(
                name=name, description=description,
                author=author, class_name=class_name,
            )
        )
        (skill_dir / f"test_{name}.py").write_text(
            cls.TEMPLATE_TEST.format(name=name)
        )
        (skill_dir / "README.md").write_text(
            f"# {name}\n\n{description}\n\n## Install\n\n"
            f"```bash\ndoppelganger registry install {name}\n```\n"
        )

        return {
            "created": str(skill_dir),
            "files": ["manifest.json", "skill.py", f"test_{name}.py", "README.md"],
        }


# ─── Convenience exports ──────────────────────────────────────────────────────

registry = SkillRegistry()

__all__ = [
    "SkillBase",
    "SkillRegistry",
    "SkillScaffolder",
    "skill_input",
    "skill_output",
    "requires_env",
    "cached",
    "registry",
]
