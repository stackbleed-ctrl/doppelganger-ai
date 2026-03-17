"""
Doppelganger Orchestrator v2
Adds: Graphiti KG, PersonaManager, ProactiveEngine to the layer stack.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from .config import Settings, get_settings
from .event_bus import bus

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

        from ..agents.runtime import AgentRuntime
        from ..memory.graphiti_kg import GraphitiKG
        from ..memory.memory_manager import MemoryManager
        from ..perception.pipeline import PerceptionPipeline
        from ..personas.manager import PersonaManager
        from ..proactive.engine import ProactiveEngine
        from ..reasoning.swarm import ReasoningSwarm
        from ..voice.pipeline import VoicePipeline

        self.graphiti = GraphitiKG(
            neo4j_url=self.settings.memory.graphiti_neo4j_url,
            user=self.settings.memory.graphiti_neo4j_user,
            password=self.settings.memory.graphiti_neo4j_password,
        )
        await self.graphiti.connect()

        self.perception  = PerceptionPipeline(self.bus, self.settings)
        self.memory      = MemoryManager(self.bus, self.settings, graphiti=self.graphiti)
        self.reasoning   = ReasoningSwarm(self.bus, self.settings)
        self.agents      = AgentRuntime(self.bus, self.settings)
        self.voice       = VoicePipeline(self.bus, self.settings)
        self.personas    = PersonaManager(self.bus, self.settings)
        self.proactive   = ProactiveEngine(self.bus, self.settings)

        self.proactive.inject(memory=self.memory, personas=self.personas)
        self.agents.tool_executor.inject(memory=self.memory, skills=None, reasoning=self.reasoning)

        self._layers = [
            self.memory, self.perception, self.reasoning,
            self.agents, self.voice, self.personas, self.proactive,
        ]

        for layer in self._layers:
            await layer.start()
            logger.info("  ✓ %s", type(layer).__name__)

        self._wire_events()
        logger.info("✅ All systems nominal.")

    async def stop(self) -> None:
        logger.info("🛑 Shutting down...")
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
        self.bus.subscribe("perception.*",                self.memory.on_perception_event)
        self.bus.subscribe("memory.updated",              self.reasoning.on_context_update)
        self.bus.subscribe("reasoning.plan_ready",        self.agents.on_plan)
        self.bus.subscribe("voice.transcript",            self.agents.on_voice_command)
        self.bus.subscribe("agent.response",              self.voice.on_speak_request)
        self.bus.subscribe("agent.response",              self.memory.on_agent_response)
        self.bus.subscribe("perception.presence_changed", self.reasoning.on_presence_change)
        self.bus.subscribe("voice.transcript",            self.personas.on_message)
        self.bus.subscribe("persona.switched",            self.agents.on_persona_switch)
        self.bus.subscribe("perception.presence_changed", self.proactive.on_presence_changed)
        self.bus.subscribe("memory.updated",              self.proactive.on_memory_updated)
        self.bus.subscribe("proactive.suggestion",        self.voice.on_speak_request)
        self.bus.subscribe("proactive.suggestion",        self.memory.on_agent_response)
        logger.debug("Event wiring complete.")

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
            "bus_stats": self.bus.stats,
            "layers": layer_health,
            "graphiti": await self.graphiti.stats(),
        }
