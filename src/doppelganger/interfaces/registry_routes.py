"""
Registry API Routes
Public skill registry endpoints for browse, install, publish.
"""

from __future__ import annotations

from pathlib import Path
from fastapi import HTTPException
from pydantic import BaseModel


class InstallRequest(BaseModel):
    name: str


class PublishRequest(BaseModel):
    skill_dir: str
    api_key: str


class ScaffoldRequest(BaseModel):
    name: str
    description: str = ""
    author: str = ""
    output_dir: str = "skills"


def register_registry_routes(app, get_orchestrator):

    from doppelganger.sdk import SkillRegistry, SkillScaffolder
    _registry = SkillRegistry()

    @app.get("/registry/search")
    async def registry_search(q: str = "", tags: str = "", limit: int = 20):
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
        results = await _registry.search(query=q, tags=tag_list, limit=limit)
        return {
            "skills": [
                {
                    "name": e.name,
                    "version": e.version,
                    "description": e.description,
                    "author": e.author,
                    "tags": e.tags,
                    "stars": e.stars,
                    "downloads": e.downloads,
                    "verified": e.verified,
                }
                for e in results
            ]
        }

    @app.post("/registry/install")
    async def registry_install(req: InstallRequest):
        skills_dir = Path("skills")
        result = await _registry.install(req.name, skills_dir)
        if "error" in result:
            raise HTTPException(400, result["error"])
        # Reload skill loader
        orch = get_orchestrator()
        if orch:
            from doppelganger.actions.skill_loader import SkillLoader
            orch.agents.tool_executor._skill_loader = SkillLoader()
        return result

    @app.post("/registry/publish")
    async def registry_publish(req: PublishRequest):
        result = await _registry.publish(Path(req.skill_dir), req.api_key)
        return result

    @app.post("/registry/scaffold")
    async def scaffold_skill(req: ScaffoldRequest):
        result = SkillScaffolder.scaffold(
            name=req.name,
            description=req.description,
            author=req.author,
            output_dir=Path(req.output_dir),
        )
        return result

    @app.get("/registry/skill/{name}")
    async def get_skill_info(name: str):
        entry = await _registry.get(name)
        if not entry:
            raise HTTPException(404, f"Skill '{name}' not found")
        return {
            "name": entry.name,
            "version": entry.version,
            "description": entry.description,
            "author": entry.author,
            "tags": entry.tags,
            "stars": entry.stars,
            "downloads": entry.downloads,
            "verified": entry.verified,
            "manifest_url": entry.manifest_url,
        }
