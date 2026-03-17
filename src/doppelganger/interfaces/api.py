"""
Doppelganger API
FastAPI backend: REST endpoints + WebSocket real-time stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.config import get_settings
from ..core.event_bus import bus, Event
from ..core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# ─── Models ──────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str
    stream: bool = False
    context: dict = {}


class ChatResponse(BaseModel):
    task_id: str
    response: str
    source: str = "agent"


class SimulateRequest(BaseModel):
    scenario: str
    steps: int = 4
    n_worlds: int = 3


class MemorySearchRequest(BaseModel):
    query: str
    limit: int = 5
    tags: list[str] | None = None


class StoreMemoryRequest(BaseModel):
    content: str
    tags: list[str] = []
    entity_type: str = "fact"


class HealthResponse(BaseModel):
    status: str
    uptime_sec: float
    layers: dict


# ─── App factory ─────────────────────────────────────────────────────────────

_orchestrator: Orchestrator | None = None
_start_time = time.time()
_ws_manager = None


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _orchestrator, _ws_manager
        _orchestrator = Orchestrator(settings)
        await _orchestrator.start()
        _ws_manager = WebSocketManager()
        # Wire WS manager to event bus
        bus.subscribe("*", _ws_manager.broadcast_event)
        yield
        await _orchestrator.stop()

    app = FastAPI(
        title="Doppelganger AI",
        description="Your local AI twin — perception, memory, reasoning, voice.",
        version=settings.version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.interface.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── Health ───────────────────────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse)
    async def health():
        if not _orchestrator:
            return HealthResponse(status="booting", uptime_sec=0, layers={})
        h = await _orchestrator.health()
        return HealthResponse(
            status=h["status"],
            uptime_sec=round(time.time() - _start_time, 1),
            layers=h.get("layers", {}),
        )

    # ─── Chat ─────────────────────────────────────────────────────────────────

    @app.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest):
        if not _orchestrator:
            raise HTTPException(503, "System not ready")

        from ..agents.runtime import AgentTask
        task = AgentTask(
            prompt=req.message,
            context=req.context,
            source="api",
        )
        task_id = await _orchestrator.agents.submit(task)

        # Wait for result (with timeout)
        deadline = time.time() + 30
        while time.time() < deadline:
            t = _orchestrator.agents.get_task(task_id)
            if t and t.status.value in ("done", "failed"):
                if t.status.value == "failed":
                    raise HTTPException(500, t.error or "Task failed")
                return ChatResponse(task_id=task_id, response=t.result or "", source="agent")
            await asyncio.sleep(0.1)

        raise HTTPException(504, "Task timeout")

    @app.post("/chat/stream")
    async def chat_stream(req: ChatRequest):
        """SSE streaming chat."""
        if not _orchestrator:
            raise HTTPException(503, "System not ready")

        grok = _orchestrator.agents.grok
        messages = [
            {
                "role": "system",
                "content": "You are Doppelganger, the user's AI twin. Be concise and direct.",
            },
            {"role": "user", "content": req.message},
        ]

        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                stream = await grok.chat(messages, stream=True)
                async for chunk in stream:
                    if chunk.text:
                        data = json.dumps({"text": chunk.text, "done": False})
                        yield f"data: {data}\n\n"
                    if chunk.finish_reason:
                        yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"
                        break
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ─── Memory ───────────────────────────────────────────────────────────────

    @app.post("/memory/search")
    async def memory_search(req: MemorySearchRequest):
        if not _orchestrator:
            raise HTTPException(503, "System not ready")
        results = await _orchestrator.memory.search(req.query, limit=req.limit, tags=req.tags)
        return {"results": results, "query": req.query}

    @app.post("/memory/store")
    async def memory_store(req: StoreMemoryRequest):
        if not _orchestrator:
            raise HTTPException(503, "System not ready")
        node = await _orchestrator.memory.store(
            req.content,
            tags=req.tags,
            entity_type=req.entity_type,
            source="api",
        )
        return {"id": node.id, "stored": True}

    @app.get("/memory/timeline")
    async def memory_timeline(hours: int = 24):
        if not _orchestrator:
            raise HTTPException(503, "System not ready")
        nodes = await _orchestrator.memory.get_timeline(hours=hours)
        return {
            "nodes": [
                {
                    "id": n.id,
                    "content": n.content,
                    "tags": n.tags,
                    "source": n.source,
                    "created_at": n.created_at,
                }
                for n in nodes
            ]
        }

    # ─── Reasoning ────────────────────────────────────────────────────────────

    @app.post("/reasoning/simulate")
    async def simulate(req: SimulateRequest):
        if not _orchestrator:
            raise HTTPException(503, "System not ready")
        result = await _orchestrator.reasoning.simulate(
            req.scenario,
            steps=req.steps,
            n_worlds=req.n_worlds,
        )
        return {
            "scenario": result.scenario,
            "best_action": result.best_action,
            "synthesis": result.synthesis,
            "confidence": result.confidence,
            "elapsed_sec": result.elapsed_sec,
            "worlds": [
                {
                    "outcome": w.outcome,
                    "utility_score": w.utility_score,
                    "steps": w.step,
                }
                for w in result.worlds
            ],
        }

    @app.post("/reasoning/plan")
    async def plan(goal: str):
        if not _orchestrator:
            raise HTTPException(503, "System not ready")
        result = await _orchestrator.reasoning.plan(goal)
        return result

    # ─── Perception ───────────────────────────────────────────────────────────

    @app.get("/perception/presence")
    async def get_presence():
        if not _orchestrator:
            raise HTTPException(503, "System not ready")
        p = _orchestrator.perception.presence
        return {
            "detected": p.detected,
            "activity": p.activity,
            "confidence": p.confidence,
            "last_seen": p.last_seen,
        }

    # ─── Skills ───────────────────────────────────────────────────────────────

    @app.get("/skills")
    async def list_skills():
        from ..actions.skill_loader import SkillLoader
        loader = SkillLoader()
        return {"skills": loader.list_skills()}

    @app.post("/skills/{skill_name}/run")
    async def run_skill(skill_name: str, params: dict = {}):
        if not _orchestrator:
            raise HTTPException(503, "System not ready")
        from ..actions.skill_loader import SkillLoader
        loader = SkillLoader()
        result = await loader.run(skill_name, params)
        return result

    # ─── Voice ────────────────────────────────────────────────────────────────

    @app.post("/voice/speak")
    async def speak(text: str):
        if not _orchestrator:
            raise HTTPException(503, "System not ready")
        asyncio.create_task(_orchestrator.voice.speak(text))
        return {"queued": True, "text": text}

    # ─── WebSocket ────────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        client_id = str(uuid.uuid4())
        if _ws_manager:
            _ws_manager.connect(client_id, ws)
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)
                await _handle_ws_message(ws, msg, client_id)
        except WebSocketDisconnect:
            if _ws_manager:
                _ws_manager.disconnect(client_id)
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            if _ws_manager:
                _ws_manager.disconnect(client_id)

    return app


async def _handle_ws_message(ws: WebSocket, msg: dict, client_id: str) -> None:
    """Handle incoming WebSocket messages from frontend."""
    msg_type = msg.get("type", "")

    if msg_type == "chat":
        text = msg.get("text", "")
        if _orchestrator and text:
            from ..agents.runtime import AgentTask
            task = AgentTask(prompt=text, source="websocket")
            await _orchestrator.agents.submit(task)
            await ws.send_json({"type": "chat_ack", "task_id": task.id})

    elif msg_type == "simulate":
        scenario = msg.get("scenario", "")
        if _orchestrator and scenario:
            result = await _orchestrator.reasoning.simulate(scenario)
            await ws.send_json({
                "type": "simulation_result",
                "best_action": result.best_action,
                "synthesis": result.synthesis,
                "confidence": result.confidence,
            })

    elif msg_type == "ping":
        await ws.send_json({"type": "pong", "ts": time.time()})

    elif msg_type == "memory_search":
        query = msg.get("query", "")
        if _orchestrator and query:
            results = await _orchestrator.memory.search(query)
            await ws.send_json({"type": "memory_results", "results": results})


class WebSocketManager:
    """Manages connected WebSocket clients and broadcasts events."""

    def __init__(self) -> None:
        self._clients: dict[str, WebSocket] = {}

    def connect(self, client_id: str, ws: WebSocket) -> None:
        self._clients[client_id] = ws
        logger.debug("WS client connected: %s (total=%d)", client_id[:8], len(self._clients))

    def disconnect(self, client_id: str) -> None:
        self._clients.pop(client_id, None)
        logger.debug("WS client disconnected: %s", client_id[:8])

    async def broadcast_event(self, event: Event) -> None:
        """Forward bus events to all connected WebSocket clients."""
        if not self._clients:
            return

        # Only forward events relevant to the frontend
        relevant_topics = {
            "agent.response", "voice.transcript", "perception.presence_changed",
            "reasoning.simulation_complete", "memory.updated", "agent.error",
        }
        if event.topic not in relevant_topics:
            return

        payload = {
            "type": "event",
            "topic": event.topic,
            "payload": event.payload,
            "ts": event.ts,
        }
        dead = []
        for cid, ws in self._clients.items():
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.disconnect(cid)


# Entrypoint
def get_app() -> FastAPI:
    return create_app()
