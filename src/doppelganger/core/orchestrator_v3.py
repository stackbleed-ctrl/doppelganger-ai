"""
Doppelganger Orchestrator v3
Full v0.3–v0.5 systems wired in.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from .event_bus import EventBus, EventPriority, bus
from .config import Settings, get_settings

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bus = bus
        self._layers: list[Any] = []
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        logger.info("🧬 Doppelganger booting — version %s", self.settings.version)
        await self.bus.start()

        from ..perception.pipeline import PerceptionPipeline
        from ..perception.typing_cadence import TypingCadenceMonitor
        from ..perception.calendar_integration import CalendarManager
        from ..memory.memory_manager import MemoryManager
        from ..memory.graphiti_kg import GraphitiKG
        from ..memory.compression.compressor import MemoryCompressor
        from ..memory.entity_extractor import EntityExtractor
        from ..reasoning.swarm import ReasoningSwarm
        from ..agents.runtime import AgentRuntime
        from ..voice.pipeline import VoicePipeline
        from ..personas.manager import PersonaManager
        from ..proactive.engine import ProactiveEngine

        # Graphiti KG
        self.graphiti = GraphitiKG(
            neo4j_url=self.settings.memory.graphiti_neo4j_url,
            user=self.settings.memory.graphiti_neo4j_user,
            password=self.settings.memory.graphiti_neo4j_password,
        )
        await self.graphiti.connect()

        # Core layers
        self.perception  = PerceptionPipeline(self.bus, self.settings)
        self.memory      = MemoryManager(self.bus, self.settings, graphiti=self.graphiti)
        self.reasoning   = ReasoningSwarm(self.bus, self.settings)
        self.agents      = AgentRuntime(self.bus, self.settings)
        self.voice       = VoicePipeline(self.bus, self.settings)
        self.personas    = PersonaManager(self.bus, self.settings)
        self.proactive   = ProactiveEngine(self.bus, self.settings)

        # v3 additions
        self.compressor  = MemoryCompressor(self.settings.data_dir / "memory")
        self.extractor   = EntityExtractor()
        self.calendar    = CalendarManager(bus=self.bus)
        self.typing_monitor = TypingCadenceMonitor()
        self.typing_monitor.set_bus(self.bus)

        # Inject references
        self.proactive.inject(memory=self.memory, personas=self.personas)
        self.agents.tool_executor.inject(
            memory=self.memory, skills=None, reasoning=self.reasoning
        )

        # Attach typing monitor to perception
        self.perception._typing_monitor = self.typing_monitor

        self._layers = [
            self.memory, self.perception, self.reasoning,
            self.agents, self.voice, self.personas, self.proactive,
            self.compressor, self.calendar,
        ]

        for layer in self._layers:
            await layer.start()
            logger.info("  ✓ %s", type(layer).__name__)

        # Start typing monitor as background task
        asyncio.create_task(
            self.typing_monitor.start_listening(),
            name="typing-monitor"
        )

        self._wire_events()
        logger.info("✅ All systems nominal — Doppelganger v3 alive.")

    async def stop(self) -> None:
        logger.info("🛑 Shutting down...")
        self.typing_monitor.stop()
        for layer in reversed(self._layers):
            try:
                await layer.stop()
            except Exception as e:
                logger.warning("Layer %s stop error: %s", type(layer).__name__, e)
        await self.graphiti.close()
        await self.bus.stop()

    async def run_forever(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)
        await self._shutdown_event.wait()
        await self.stop()

    def _wire_events(self) -> None:
        # Core data flow
        self.bus.subscribe("perception.*",                self.memory.on_perception_event)
        self.bus.subscribe("memory.updated",              self.reasoning.on_context_update)
        self.bus.subscribe("reasoning.plan_ready",        self.agents.on_plan)
        self.bus.subscribe("voice.transcript",            self.agents.on_voice_command)
        self.bus.subscribe("agent.response",              self.voice.on_speak_request)
        self.bus.subscribe("agent.response",              self.memory.on_agent_response)
        self.bus.subscribe("perception.presence_changed", self.reasoning.on_presence_change)

        # Entity extraction on agent responses
        self.bus.subscribe("agent.response",              self._on_agent_response_extract)

        # Persona wiring
        self.bus.subscribe("voice.transcript",            self.personas.on_message)
        self.bus.subscribe("persona.switched",            self.agents.on_persona_switch)

        # Proactive engine
        self.bus.subscribe("perception.presence_changed", self.proactive.on_presence_changed)
        self.bus.subscribe("memory.updated",              self.proactive.on_memory_updated)
        self.bus.subscribe("proactive.suggestion",        self.voice.on_speak_request)
        self.bus.subscribe("proactive.suggestion",        self.memory.on_agent_response)

        # Calendar → proactive context
        self.bus.subscribe("calendar.synced",             self._on_calendar_synced)

        # Stress → proactive
        self.bus.subscribe("perception.stress_estimate",  self._on_stress_update)

        # Emotion → memory
        self.bus.subscribe("voice.emotion_detected",      self._on_emotion_detected)

        logger.debug("Event wiring v3 complete.")

    async def _on_agent_response_extract(self, event) -> None:
        """Extract entities from agent responses into KG."""
        text = event.payload.get("text", "")
        if text and len(text) > 50:
            try:
                await self.extractor.extract_and_store(text, self.graphiti, deep=False)
            except Exception:
                pass

    async def _on_calendar_synced(self, event) -> None:
        """Inject calendar context into proactive engine."""
        context = self.calendar.context_string()
        if context:
            await self.memory.store(
                context,
                tags=["calendar", "context"],
                source="calendar",
            )

    async def _on_stress_update(self, event) -> None:
        """Store significant stress events in memory."""
        level = event.payload.get("level", "unknown")
        score = event.payload.get("score", 0)
        if score > 0.65:
            await self.memory.store(
                f"High stress detected: {level} (score={score:.2f})",
                tags=["stress", "perception", "wellbeing"],
                source="typing_monitor",
            )

    async def _on_emotion_detected(self, event) -> None:
        """Store non-neutral voice emotions in memory."""
        emotion = event.payload.get("emotion", "neutral")
        confidence = event.payload.get("confidence", 0)
        if emotion != "neutral" and confidence > 0.5:
            await self.memory.store(
                f"Voiced emotion: {emotion} (confidence={confidence:.2f})",
                tags=["emotion", "voice", "wellbeing"],
                source="voice",
            )

    async def health(self) -> dict:
        layer_health = {}
        for layer in self._layers:
            try:
                h = await layer.health() if hasattr(layer, "health") else "ok"
                layer_health[type(layer).__name__] = h
            except Exception:
                layer_health[type(layer).__name__] = "error"
        return {
            "status": "ok",
            "version": self.settings.version,
            "bus_stats": self.bus.stats,
            "layers": layer_health,
            "graphiti": await self.graphiti.stats(),
            "calendar": {
                "events": len(self.calendar.get_week()),
                "next_event": self.calendar.next_event().title if self.calendar.next_event() else None,
            },
        }
