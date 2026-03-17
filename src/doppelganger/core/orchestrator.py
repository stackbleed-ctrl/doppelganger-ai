"""
Doppelganger Orchestrator
Wires every layer together. Start here.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import TYPE_CHECKING

from .event_bus import EventBus, EventPriority, bus
from .config import Settings, get_settings

if TYPE_CHECKING:
    from ..perception.pipeline import PerceptionPipeline
    from ..memory.memory_manager import MemoryManager
    from ..reasoning.swarm import ReasoningSwarm
    from ..agents.runtime import AgentRuntime
    from ..voice.pipeline import VoicePipeline
    from ..interfaces.api import create_app

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Top-level coordinator.
    Boots every subsystem in the correct order, wires cross-layer events,
    and provides a clean shutdown path.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.bus = bus
        self._layers: list[Any] = []
        self._shutdown_event = asyncio.Event()

    # ─── Boot sequence ───────────────────────────────────────────────────────

    async def start(self) -> None:
        logger.info("🧬 Doppelganger booting — version %s", self.settings.version)

        await self.bus.start()

        # Import lazily so cold-start is fast even if optional deps missing
        from ..perception.pipeline import PerceptionPipeline
        from ..memory.memory_manager import MemoryManager
        from ..reasoning.swarm import ReasoningSwarm
        from ..agents.runtime import AgentRuntime
        from ..voice.pipeline import VoicePipeline

        self.perception = PerceptionPipeline(self.bus, self.settings)
        self.memory     = MemoryManager(self.bus, self.settings)
        self.reasoning  = ReasoningSwarm(self.bus, self.settings)
        self.agents     = AgentRuntime(self.bus, self.settings)
        self.voice      = VoicePipeline(self.bus, self.settings)

        self._layers = [
            self.memory,
            self.perception,
            self.reasoning,
            self.agents,
            self.voice,
        ]

        for layer in self._layers:
            await layer.start()
            logger.info("  ✓ %s", type(layer).__name__)

        self._wire_cross_layer_events()

        logger.info("✅ All systems nominal. Doppelganger is alive.")

    async def stop(self) -> None:
        logger.info("🛑 Shutting down...")
        for layer in reversed(self._layers):
            try:
                await layer.stop()
            except Exception as e:
                logger.warning("Layer %s failed to stop cleanly: %s", type(layer).__name__, e)
        await self.bus.stop()
        logger.info("Goodbye.")

    async def run_forever(self) -> None:
        """Block until SIGINT/SIGTERM."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown_event.set)
        await self._shutdown_event.wait()
        await self.stop()

    # ─── Cross-layer event wiring ────────────────────────────────────────────

    def _wire_cross_layer_events(self) -> None:
        """
        Declare the data-flow contracts between layers.
        Keep this as the single source of truth for event topology.
        """
        # Perception → Memory: everything sensed gets stored
        self.bus.subscribe("perception.*", self.memory.on_perception_event)

        # Memory → Reasoning: context updates trigger re-evaluation
        self.bus.subscribe("memory.updated", self.reasoning.on_context_update)

        # Reasoning → Agents: plans become tasks
        self.bus.subscribe("reasoning.plan_ready", self.agents.on_plan)

        # Voice transcript → Agents: spoken commands become agent tasks
        self.bus.subscribe("voice.transcript", self.agents.on_voice_command)

        # Agents → Voice: responses get spoken
        self.bus.subscribe("agent.response", self.voice.on_speak_request)

        # Agents → Memory: agent outputs enrich the knowledge graph
        self.bus.subscribe("agent.response", self.memory.on_agent_response)

        # Perception: presence change → reasoning re-trigger
        self.bus.subscribe("perception.presence_changed", self.reasoning.on_presence_change)

        logger.debug("Cross-layer event wiring complete.")

    # ─── Health ──────────────────────────────────────────────────────────────

    async def health(self) -> dict:
        return {
            "status": "ok",
            "bus_stats": self.bus.stats,
            "layers": {
                type(l).__name__: await l.health() if hasattr(l, "health") else "ok"
                for l in self._layers
            },
        }


# Allow `python -m doppelganger.core.orchestrator` for quick test boot
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def main():
        orch = Orchestrator()
        await orch.start()
        await orch.run_forever()

    asyncio.run(main())
