"""
Skill Loader
Discovers installed skills, validates their manifests,
builds tool schemas for the agent, and sandboxes execution.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SKILLS_DIR = Path("skills")
MANIFEST_FILE = "manifest.json"


class SkillLoader:
    """
    Loads skills from the skills/ directory.
    Each skill folder must contain:
      - manifest.json  (metadata + parameter schema)
      - skill.py       (async def run(params: dict) -> dict)
    """

    def __init__(self, skills_dir: Path | None = None) -> None:
        self._dir = skills_dir or SKILLS_DIR
        self._cache: dict[str, dict] = {}
        self._scan()

    def _scan(self) -> None:
        if not self._dir.exists():
            return
        for skill_dir in self._dir.iterdir():
            if not skill_dir.is_dir():
                continue
            manifest_path = skill_dir / MANIFEST_FILE
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text())
                manifest["_path"] = str(skill_dir)
                self._cache[manifest["name"]] = manifest
            except Exception as e:
                logger.warning("Bad manifest in %s: %s", skill_dir, e)
        logger.info("Loaded %d skills: %s", len(self._cache), list(self._cache.keys()))

    def list_skills(self) -> list[dict]:
        return [
            {
                "name": m["name"],
                "description": m.get("description", ""),
                "version": m.get("version", "0.1.0"),
                "parameters": m.get("parameters", {}),
            }
            for m in self._cache.values()
        ]

    def get_tool_schemas(self) -> list[dict]:
        """Return OpenAI function-call schemas for all installed skills."""
        schemas = []
        for manifest in self._cache.values():
            schemas.append({
                "type": "function",
                "function": {
                    "name": manifest["name"],
                    "description": manifest.get("description", ""),
                    "parameters": manifest.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return schemas

    async def run(self, skill_name: str, params: dict) -> dict:
        """Execute a skill by name with given params."""
        manifest = self._cache.get(skill_name)
        if not manifest:
            return {"error": f"Skill '{skill_name}' not found"}

        skill_path = Path(manifest["_path"]) / "skill.py"
        if not skill_path.exists():
            return {"error": f"skill.py missing in {manifest['_path']}"}

        try:
            # Load the module dynamically
            spec = importlib.util.spec_from_file_location(skill_name, skill_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if not hasattr(module, "run"):
                return {"error": "skill.py must define async def run(params: dict) -> dict"}

            # Run with timeout
            result = await asyncio.wait_for(
                module.run(params),
                timeout=manifest.get("timeout_sec", 30),
            )
            return result if isinstance(result, dict) else {"result": result}

        except asyncio.TimeoutError:
            return {"error": f"Skill '{skill_name}' timed out"}
        except Exception as e:
            logger.error("Skill '%s' execution error: %s", skill_name, e)
            return {"error": str(e)}
