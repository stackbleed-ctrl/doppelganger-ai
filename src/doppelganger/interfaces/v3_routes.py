"""
v3–v5 API Routes
Registers all new endpoints for the v0.3–v0.5 feature set.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel


class ImportRequest(BaseModel):
    source: str           # obsidian | notion | browser
    vault_path: str = ""
    import_all: bool = False
    days_back: int = 30
    page_ids: list[str] = []


class DiarizeRequest(BaseModel):
    audio_path: str
    num_speakers: int | None = None
    language: str | None = None


class NameSpeakerRequest(BaseModel):
    speaker_id: str
    name: str


class CalendarRequest(BaseModel):
    action: str = "sync"   # sync | upcoming | today | week | context


def register_v3_routes(app, get_orchestrator):

    # ── Memory imports ────────────────────────────────────────────────────────

    @app.post("/memory/import")
    async def memory_import(req: ImportRequest):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")

        source = req.source.lower()

        if source == "obsidian":
            if not req.vault_path:
                raise HTTPException(400, "vault_path required for obsidian import")
            from doppelganger.memory.importers.obsidian import import_vault
            result = await import_vault(req.vault_path, orch.memory)
            return result

        elif source == "notion":
            from doppelganger.memory.importers.notion import import_notion
            result = await import_notion(
                orch.memory,
                page_ids=req.page_ids or None,
                import_all=req.import_all,
            )
            return result

        elif source == "browser":
            from doppelganger.memory.importers.browser_history import import_browser_history
            result = await import_browser_history(
                orch.memory,
                days_back=req.days_back,
            )
            return result

        else:
            raise HTTPException(400, f"Unknown import source: {source}")

    @app.get("/memory/summaries")
    async def get_summaries(tier: str | None = None, limit: int = 20):
        orch = get_orchestrator()
        if not orch or not hasattr(orch, 'compressor'):
            return {"summaries": []}
        sums = orch.compressor.get_summaries(tier=tier, limit=limit)
        return {
            "summaries": [
                {
                    "id": s.id,
                    "content": s.content,
                    "key_entities": s.key_entities,
                    "key_themes": s.key_themes,
                    "tier": s.tier,
                    "time_range_start": s.time_range_start,
                    "time_range_end": s.time_range_end,
                    "importance_score": s.importance_score,
                }
                for s in sums
            ]
        }

    # ── Calendar ─────────────────────────────────────────────────────────────

    @app.get("/calendar/upcoming")
    async def calendar_upcoming(hours: int = 24):
        orch = get_orchestrator()
        if not orch or not hasattr(orch, 'calendar'):
            return {"events": [], "message": "Calendar not configured"}
        events = orch.calendar.get_upcoming(hours=hours)
        return {"events": [_event_dict(e) for e in events]}

    @app.get("/calendar/today")
    async def calendar_today():
        orch = get_orchestrator()
        if not orch or not hasattr(orch, 'calendar'):
            return {"events": []}
        return {"events": [_event_dict(e) for e in orch.calendar.get_today()]}

    @app.get("/calendar/context")
    async def calendar_context():
        orch = get_orchestrator()
        if not orch or not hasattr(orch, 'calendar'):
            return {"context": "Calendar not available"}
        return {"context": orch.calendar.context_string()}

    @app.post("/calendar/sync")
    async def calendar_sync():
        orch = get_orchestrator()
        if not orch or not hasattr(orch, 'calendar'):
            raise HTTPException(503, "Calendar not configured")
        count = await orch.calendar.sync()
        return {"synced": count}

    # ── Voice v2 ─────────────────────────────────────────────────────────────

    @app.get("/voice/language")
    async def get_language():
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        ml = getattr(orch.voice, '_multilingual', None)
        if not ml:
            return {"language": "en", "supported": []}
        return {
            "language": ml.current_language,
            "supported": ml.list_supported(),
        }

    @app.post("/voice/language/{code}")
    async def set_language(code: str):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        ml = getattr(orch.voice, '_multilingual', None)
        if not ml:
            raise HTTPException(503, "Multilingual not initialized")
        cfg = ml.set_language(code)
        return {"language": code, "tts_engine": cfg.tts_engine, "tts_voice": cfg.tts_voice}

    @app.post("/voice/diarize")
    async def diarize_audio(req: DiarizeRequest):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        diarizer = getattr(orch.voice, '_diarizer', None)
        if not diarizer:
            raise HTTPException(503, "Diarizer not initialized")
        result = await diarizer.diarize(
            req.audio_path,
            num_speakers=req.num_speakers,
            language=req.language,
        )
        return {
            "speakers": result.speakers,
            "duration_sec": result.duration_sec,
            "transcript": diarizer.format_transcript(result),
            "segments": [
                {
                    "speaker_id": s.speaker_id,
                    "speaker_name": s.speaker_name or s.speaker_id,
                    "start_sec": s.start_sec,
                    "end_sec": s.end_sec,
                    "text": s.text,
                }
                for s in result.segments
            ],
        }

    @app.post("/voice/speakers/name")
    async def name_speaker(req: NameSpeakerRequest):
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        diarizer = getattr(orch.voice, '_diarizer', None)
        if not diarizer:
            raise HTTPException(503, "Diarizer not initialized")
        diarizer.name_speaker(req.speaker_id, req.name)
        return {"named": req.speaker_id, "as": req.name}

    # ── Perception v2 ─────────────────────────────────────────────────────────

    @app.get("/perception/stress")
    async def get_stress():
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        cadence = getattr(orch.perception, '_typing_monitor', None)
        if not cadence:
            return {"level": "unknown", "message": "Typing monitor not active"}
        est = cadence.last_estimate
        return {
            "level": est.level.value,
            "score": est.score,
            "wpm": est.wpm,
            "confidence": est.confidence,
            "notes": est.notes,
        }

    @app.get("/perception/pose")
    async def get_pose():
        orch = get_orchestrator()
        if not orch:
            raise HTTPException(503, "System not ready")
        pose_est = getattr(orch.perception, '_pose_estimator', None)
        if not pose_est:
            return {"pose": "unknown", "message": "CSI pose estimator not active"}
        est = pose_est.last_estimate if hasattr(pose_est, 'last_estimate') else None
        if not est:
            return {"pose": "unknown"}
        return {
            "pose": est.pose,
            "gesture": est.gesture,
            "confidence": est.confidence,
            "breathing_bpm": est.breathing_bpm,
            "body_direction": est.body_direction,
        }


def _event_dict(e) -> dict:
    return {
        "id": e.id,
        "title": e.title,
        "start": e.start,
        "end": e.end,
        "description": e.description,
        "location": e.location,
        "attendees": e.attendees,
        "calendar": e.calendar,
        "is_all_day": e.is_all_day,
    }
