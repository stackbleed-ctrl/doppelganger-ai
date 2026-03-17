"""
Persona API Routes
Mounted at /personas in the main FastAPI app.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/personas", tags=["personas"])


class CreatePersonaRequest(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    voice_id: str = "af_sky"
    temperature: float = 0.7
    color: str = "#00d4ff"
    emoji: str = "🧬"
    auto_switch_triggers: list[str] = []
    memory_scope: str = "shared"
    reasoning_style: str = "balanced"


class UpdatePersonaRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    voice_id: str | None = None
    temperature: float | None = None
    color: str | None = None
    auto_switch_triggers: list[str] | None = None


def _persona_dict(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "voice_id": p.voice_id,
        "temperature": p.temperature,
        "color": p.color,
        "emoji": p.emoji,
        "auto_switch_triggers": p.auto_switch_triggers,
        "memory_scope": p.memory_scope,
        "reasoning_style": p.reasoning_style,
        "active": p.active,
    }


def register_persona_routes(app, get_orchestrator):
    """Register persona routes on the FastAPI app."""

    @app.get("/personas")
    async def list_personas():
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        personas = orch.personas.list_all()
        active_id = orch.personas.active_id
        return {
            "personas": [_persona_dict(p) for p in personas],
            "active_id": active_id,
        }

    @app.get("/personas/active")
    async def get_active_persona():
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        p = orch.personas.active
        return {"persona": _persona_dict(p)}

    @app.post("/personas/{persona_id}/activate")
    async def activate_persona(persona_id: str):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        try:
            p = await orch.personas.switch(persona_id, reason="api")
            return {"switched_to": _persona_dict(p)}
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.post("/personas")
    async def create_persona(req: CreatePersonaRequest):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        from doppelganger.personas.manager import Persona
        p = Persona(**req.dict())
        created = await orch.personas.create(p)
        return {"persona": _persona_dict(created)}

    @app.patch("/personas/{persona_id}")
    async def update_persona(persona_id: str, req: UpdatePersonaRequest):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        updates = {k: v for k, v in req.dict().items() if v is not None}
        try:
            p = await orch.personas.update(persona_id, updates)
            return {"persona": _persona_dict(p)}
        except ValueError as e:
            raise HTTPException(404, str(e))

    @app.delete("/personas/{persona_id}")
    async def delete_persona(persona_id: str):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        try:
            await orch.personas.delete(persona_id)
            return {"deleted": persona_id}
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/proactive/suggestions")
    async def get_suggestions(limit: int = 10):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        suggestions = orch.proactive.get_recent(limit=limit)
        return {
            "suggestions": [
                {
                    "id": s.id,
                    "type": s.type.value,
                    "text": s.text,
                    "confidence": s.confidence,
                    "ts": s.ts,
                    "persona_id": s.persona_id,
                }
                for s in suggestions
            ]
        }

    @app.post("/proactive/suggestions/{suggestion_id}/dismiss")
    async def dismiss_suggestion(suggestion_id: str):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        orch.proactive.dismiss(suggestion_id)
        return {"dismissed": suggestion_id}

    @app.get("/memory/graph/entity/{name}")
    async def entity_history(name: str):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        episodes = await orch.graphiti.get_entity_history(name)
        return {
            "entity": name,
            "episodes": [
                {"id": ep.id, "content": ep.content, "created_at": ep.created_at}
                for ep in episodes
            ],
        }

    @app.get("/memory/graph/stats")
    async def graph_stats():
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        return await orch.graphiti.stats()
