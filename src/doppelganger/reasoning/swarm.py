"""
Reasoning Swarm
LangGraph-style parallel world simulation engine.
Spins up N "world" agents simultaneously, each exploring a different
branch of a scenario, then merges results into a ranked plan.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..core.event_bus import Event, EventBus, EventPriority
from ..core.config import Settings
from ..agents.grok_client import get_grok

logger = logging.getLogger(__name__)


@dataclass
class WorldState:
    """A single simulated world branch."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    scenario: str = ""
    step: int = 0
    history: list[dict] = field(default_factory=list)
    outcome: str = ""
    probability: float = 0.5
    utility_score: float = 0.0
    terminal: bool = False


@dataclass
class SimResult:
    scenario: str
    worlds: list[WorldState]
    best_action: str
    synthesis: str
    confidence: float
    elapsed_sec: float


class ReasoningSwarm:
    """
    Parallel simulation engine.

    Usage:
      result = await swarm.simulate("What if I quit my job?", steps=6)
      result.synthesis → natural-language recommendation
      result.worlds    → all explored branches with scores
    """

    def __init__(self, bus: EventBus, settings: Settings) -> None:
        self.bus = bus
        self.cfg = settings.reasoning
        self.grok = get_grok()
        self._running = False
        self._context: dict = {}

    async def start(self) -> None:
        self._running = True
        logger.info(
            "ReasoningSwarm started | worlds=%d steps=%d",
            self.cfg.max_parallel_worlds,
            self.cfg.world_sim_steps,
        )

    async def stop(self) -> None:
        self._running = False

    async def health(self) -> dict:
        return {"status": "ok", "context_keys": list(self._context.keys())}

    # ─── Event handlers ──────────────────────────────────────────────────────

    async def on_context_update(self, event: Event) -> None:
        """Update the shared context when memory changes."""
        payload = event.payload or {}
        self._context.update({
            "recent_memory": payload.get("content", ""),
            "memory_tags": payload.get("tags", []),
        })

    async def on_presence_change(self, event: Event) -> None:
        """When user appears, proactively generate a morning brief."""
        payload = event.payload or {}
        if payload.get("detected") and payload.get("activity") == "idle":
            await self.bus.publish_simple(
                "reasoning.plan_ready",
                payload={
                    "instruction": "Generate a brief morning/arrival summary for the user.",
                    "context": self._context,
                },
                source="reasoning",
            )

    # ─── Core simulation ─────────────────────────────────────────────────────

    async def simulate(
        self,
        scenario: str,
        *,
        steps: int | None = None,
        n_worlds: int | None = None,
        context: dict | None = None,
    ) -> SimResult:
        """
        Run parallel world simulation.
        Returns ranked outcomes + synthesis + best action recommendation.
        """
        t0 = time.time()
        n_worlds = n_worlds or self.cfg.max_parallel_worlds
        steps = steps or self.cfg.world_sim_steps
        ctx = {**self._context, **(context or {})}

        # Seed each world with a different initial assumption
        seeds = await self._generate_seeds(scenario, n_worlds, ctx)
        worlds = [WorldState(scenario=scenario) for _ in range(n_worlds)]
        for i, w in enumerate(worlds):
            if i < len(seeds):
                w.history.append({"role": "system", "content": seeds[i]})

        # Run all worlds in parallel
        sim_tasks = [
            asyncio.create_task(self._run_world(w, steps, ctx))
            for w in worlds
        ]
        completed = await asyncio.gather(*sim_tasks, return_exceptions=True)
        valid_worlds = [w for w in completed if isinstance(w, WorldState)]

        if not valid_worlds:
            return SimResult(
                scenario=scenario,
                worlds=[],
                best_action="Unable to simulate — no valid worlds",
                synthesis="Simulation failed.",
                confidence=0.0,
                elapsed_sec=time.time() - t0,
            )

        # Score and rank
        scored = sorted(valid_worlds, key=lambda w: w.utility_score, reverse=True)

        # Synthesize across worlds
        synthesis = await self._synthesize(scenario, scored, ctx)
        best_action = scored[0].outcome if scored else "No clear recommendation"
        confidence = float(sum(w.utility_score for w in scored[:2]) / max(len(scored), 1))

        result = SimResult(
            scenario=scenario,
            worlds=scored,
            best_action=best_action,
            synthesis=synthesis,
            confidence=min(confidence, 1.0),
            elapsed_sec=round(time.time() - t0, 2),
        )

        await self.bus.publish_simple(
            "reasoning.simulation_complete",
            payload={
                "scenario": scenario,
                "best_action": best_action,
                "confidence": result.confidence,
            },
            source="reasoning",
        )

        return result

    async def plan(self, goal: str, context: dict | None = None) -> dict:
        """
        High-level planning: decompose a goal into actionable steps.
        """
        ctx = {**self._context, **(context or {})}
        memories = ctx.get("memories", [])
        mem_str = "\n".join(f"- {m}" for m in memories[:5]) if memories else "None"

        prompt = f"""\
Goal: {goal}

Relevant context:
{mem_str}

Decompose this goal into a concrete action plan. For each step specify:
1. The action to take
2. Which skill or tool to use
3. Expected outcome

Be specific and actionable. 3-5 steps maximum."""

        plan_text = await self.grok.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )

        await self.bus.publish_simple(
            "reasoning.plan_ready",
            payload={"instruction": plan_text, "goal": goal, "context": ctx},
            source="reasoning",
        )

        return {"goal": goal, "plan": plan_text, "context": ctx}

    # ─── World simulation internals ───────────────────────────────────────────

    async def _generate_seeds(
        self, scenario: str, n: int, context: dict
    ) -> list[str]:
        """Generate N diverse initial assumptions for world branching."""
        prompt = f"""\
Scenario: {scenario}

Generate {n} distinct assumptions or framings for exploring this scenario.
Each should represent a genuinely different perspective or starting condition.
Return as a JSON array of strings. No prose."""

        try:
            raw = await self.grok.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.9,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            import json
            data = json.loads(raw)
            seeds = data if isinstance(data, list) else data.get("assumptions", [])
            return seeds[:n]
        except Exception as e:
            logger.warning("Seed generation failed: %s", e)
            return [f"Assumption {i+1} for: {scenario}" for i in range(n)]

    async def _run_world(
        self, world: WorldState, steps: int, context: dict
    ) -> WorldState:
        """Step a single world forward for N iterations."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a scenario simulator. Model this world branch step by step. "
                    "Be concise — one step per response. After the final step, "
                    "output 'OUTCOME: <result>' and 'SCORE: <0.0-1.0>'."
                ),
            },
            *world.history,
            {"role": "user", "content": f"Simulate: {world.scenario}. Go step by step."},
        ]

        for step in range(steps):
            try:
                response = await self.grok.chat(messages, temperature=0.7, max_tokens=300)
                messages.append({"role": "assistant", "content": response})
                world.history.append({"role": "assistant", "content": response, "step": step})

                if "OUTCOME:" in response:
                    # Parse terminal state
                    for line in response.split("\n"):
                        if line.startswith("OUTCOME:"):
                            world.outcome = line[8:].strip()
                        elif line.startswith("SCORE:"):
                            try:
                                world.utility_score = float(line[6:].strip())
                            except ValueError:
                                world.utility_score = 0.5
                    world.terminal = True
                    break
            except Exception as e:
                logger.debug("World %s step %d error: %s", world.id[:8], step, e)
                break

        world.step = steps
        if not world.outcome:
            world.outcome = world.history[-1]["content"][:200] if world.history else "No outcome"
        if world.utility_score == 0.0:
            world.utility_score = 0.3  # default low score for incomplete worlds

        return world

    async def _synthesize(
        self, scenario: str, worlds: list[WorldState], context: dict
    ) -> str:
        """Synthesize across all world outcomes into a recommendation."""
        outcomes_text = "\n".join(
            f"World {i+1} (score={w.utility_score:.2f}): {w.outcome}"
            for i, w in enumerate(worlds[:4])
        )

        prompt = f"""\
Scenario: {scenario}

Simulated outcomes across {len(worlds)} parallel worlds:
{outcomes_text}

Synthesize these outcomes into a single, actionable recommendation.
Be direct. State the best path and why. Max 3 sentences."""

        try:
            return await self.grok.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=250,
            )
        except Exception as e:
            logger.warning("Synthesis failed: %s", e)
            return worlds[0].outcome if worlds else "Unable to synthesize."
