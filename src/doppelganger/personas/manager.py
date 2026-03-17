"""
Persona System
Multi-persona support: work / personal / focus / custom.
Each persona has its own: system prompt, voice, memory scope,
reasoning style, and auto-switch triggers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.event_bus import Event, EventBus, EventPriority
from ..core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class Persona:
    id: str
    name: str
    description: str
    system_prompt: str
    voice_id: str = "af_sky"           # Kokoro voice
    voice_speed: float = 1.0
    temperature: float = 0.7
    color: str = "#00d4ff"             # UI accent color
    emoji: str = "🧬"
    auto_switch_triggers: list[str] = field(default_factory=list)
    memory_scope: str = "shared"        # shared | isolated
    reasoning_style: str = "balanced"  # analytical | creative | balanced | concise
    active: bool = True
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


# ─── Built-in personas ────────────────────────────────────────────────────────

DEFAULT_PERSONAS: list[Persona] = [
    Persona(
        id="default",
        name="Doppelganger",
        description="Your general-purpose AI twin",
        system_prompt="""\
You are Doppelganger — a private, local-first AI twin.
Direct and efficient. No filler. Proactively helpful.
Never preachy or sycophantic. Privacy-first always.""",
        voice_id="af_sky",
        temperature=0.7,
        color="#00d4ff",
        emoji="🧬",
        reasoning_style="balanced",
    ),
    Persona(
        id="work",
        name="Work Mode",
        description="Professional, focused, structured",
        system_prompt="""\
You are in Work Mode — professional, precise, and structured.
Prioritize: task completion, deadlines, clear action items.
Format responses with bullet points when listing items.
Skip small talk. Lead with the answer, then context.
Time is scarce. Be brief.""",
        voice_id="af_bella",
        temperature=0.3,
        color="#ffb800",
        emoji="💼",
        auto_switch_triggers=["9am", "standup", "meeting", "deadline", "work", "project"],
        memory_scope="isolated",
        reasoning_style="analytical",
    ),
    Persona(
        id="personal",
        name="Personal Mode",
        description="Casual, warm, conversational",
        system_prompt="""\
You are in Personal Mode — relaxed, warm, and conversational.
Talk like a trusted friend who happens to know everything about the user.
Use casual language. Ask follow-up questions. Show curiosity.
It's okay to be playful. No corporate speak.""",
        voice_id="af_sky",
        temperature=0.85,
        color="#a855f7",
        emoji="🏠",
        auto_switch_triggers=["evening", "weekend", "home", "family", "relax"],
        memory_scope="shared",
        reasoning_style="creative",
    ),
    Persona(
        id="focus",
        name="Focus Mode",
        description="Minimal, distraction-free, deep work",
        system_prompt="""\
You are in Focus Mode. Responses are minimal and surgical.
Answer only what is asked. No elaboration unless requested.
No questions back. No suggestions. Pure signal.
The user is in deep work. Protect their attention.""",
        voice_id="am_michael",
        voice_speed=0.9,
        temperature=0.2,
        color="#00ff94",
        emoji="🎯",
        auto_switch_triggers=["focus", "deep work", "pomodoro", "no interruptions", "coding"],
        memory_scope="isolated",
        reasoning_style="concise",
    ),
]


class PersonaManager:
    """
    Manages persona lifecycle: switching, auto-detection, persistence.
    Publishes persona.switched events for all layers to react to.
    """

    def __init__(self, bus: EventBus, settings: Settings) -> None:
        self.bus = bus
        self.settings = settings
        self.data_dir = settings.data_dir / "personas"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._personas: dict[str, Persona] = {}
        self._active_id: str = "default"
        self._switch_history: list[dict] = []
        self._running = False

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        await self._load_personas()
        logger.info(
            "PersonaManager started | active=%s | total=%d",
            self._active_id, len(self._personas)
        )

    async def stop(self) -> None:
        self._running = False
        await self._save_personas()

    async def health(self) -> dict:
        return {
            "active": self._active_id,
            "personas": list(self._personas.keys()),
        }

    # ─── Active persona ───────────────────────────────────────────────────────

    @property
    def active(self) -> Persona:
        return self._personas.get(self._active_id, self._personas["default"])

    @property
    def active_id(self) -> str:
        return self._active_id

    def get(self, persona_id: str) -> Persona | None:
        return self._personas.get(persona_id)

    def list_all(self) -> list[Persona]:
        return [p for p in self._personas.values() if p.active]

    # ─── Switching ───────────────────────────────────────────────────────────

    async def switch(self, persona_id: str, reason: str = "manual") -> Persona:
        if persona_id not in self._personas:
            raise ValueError(f"Persona '{persona_id}' not found")

        prev = self._active_id
        self._active_id = persona_id
        persona = self._personas[persona_id]

        self._switch_history.append({
            "from": prev,
            "to": persona_id,
            "reason": reason,
            "ts": time.time(),
        })

        await self.bus.publish_simple(
            "persona.switched",
            payload={
                "from": prev,
                "to": persona_id,
                "persona": {
                    "id": persona.id,
                    "name": persona.name,
                    "system_prompt": persona.system_prompt,
                    "voice_id": persona.voice_id,
                    "color": persona.color,
                    "temperature": persona.temperature,
                },
                "reason": reason,
            },
            source="persona_manager",
            priority=EventPriority.HIGH,
        )

        logger.info("Persona switched: %s → %s (%s)", prev, persona_id, reason)
        return persona

    async def auto_detect_and_switch(self, context: str) -> Persona | None:
        """
        Scan context for trigger keywords and auto-switch if confident.
        Returns the new persona if switched, None otherwise.
        """
        context_lower = context.lower()
        scores: dict[str, int] = {}

        for pid, persona in self._personas.items():
            if pid == self._active_id or not persona.auto_switch_triggers:
                continue
            hits = sum(1 for t in persona.auto_switch_triggers if t in context_lower)
            if hits > 0:
                scores[pid] = hits

        if not scores:
            return None

        best = max(scores, key=lambda k: scores[k])
        if scores[best] >= 2:  # need at least 2 trigger hits for auto-switch
            return await self.switch(best, reason="auto-detect")
        return None

    # ─── CRUD ────────────────────────────────────────────────────────────────

    async def create(self, persona: Persona) -> Persona:
        self._personas[persona.id] = persona
        await self._save_personas()
        await self.bus.publish_simple(
            "persona.created",
            payload={"id": persona.id, "name": persona.name},
            source="persona_manager",
        )
        return persona

    async def update(self, persona_id: str, updates: dict) -> Persona:
        if persona_id not in self._personas:
            raise ValueError(f"Persona '{persona_id}' not found")
        persona = self._personas[persona_id]
        for key, val in updates.items():
            if hasattr(persona, key):
                setattr(persona, key, val)
        await self._save_personas()
        return persona

    async def delete(self, persona_id: str) -> None:
        if persona_id in ("default",):
            raise ValueError("Cannot delete the default persona")
        if persona_id == self._active_id:
            await self.switch("default", reason="deleted")
        self._personas.pop(persona_id, None)
        await self._save_personas()

    # ─── Event handler ───────────────────────────────────────────────────────

    async def on_message(self, event: Event) -> None:
        """Check incoming messages for auto-switch triggers."""
        text = ""
        if event.topic == "voice.transcript":
            text = event.payload.get("text", "")
        elif event.topic == "agent.response":
            text = event.payload.get("text", "")
        if text:
            await self.auto_detect_and_switch(text)

    # ─── Persistence ─────────────────────────────────────────────────────────

    async def _load_personas(self) -> None:
        # Load defaults first
        for p in DEFAULT_PERSONAS:
            self._personas[p.id] = p

        # Load user-created personas from disk
        persona_file = self.data_dir / "personas.json"
        if persona_file.exists():
            try:
                data = json.loads(persona_file.read_text())
                for pd in data.get("custom", []):
                    p = Persona(**pd)
                    self._personas[p.id] = p
                self._active_id = data.get("active_id", "default")
                logger.info("Loaded %d personas from disk", len(data.get("custom", [])))
            except Exception as e:
                logger.warning("Could not load personas: %s", e)

    async def _save_personas(self) -> None:
        try:
            # Only save custom (non-default) personas
            default_ids = {p.id for p in DEFAULT_PERSONAS}
            custom = [
                {
                    "id": p.id, "name": p.name, "description": p.description,
                    "system_prompt": p.system_prompt, "voice_id": p.voice_id,
                    "voice_speed": p.voice_speed, "temperature": p.temperature,
                    "color": p.color, "emoji": p.emoji,
                    "auto_switch_triggers": p.auto_switch_triggers,
                    "memory_scope": p.memory_scope,
                    "reasoning_style": p.reasoning_style,
                    "created_at": p.created_at,
                }
                for p in self._personas.values()
                if p.id not in default_ids
            ]
            data = {"active_id": self._active_id, "custom": custom}
            (self.data_dir / "personas.json").write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error("Failed to save personas: %s", e)
