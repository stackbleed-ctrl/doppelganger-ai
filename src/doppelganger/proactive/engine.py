"""
Proactive Suggestions Engine
Background reasoning loop that watches context, memory, and time
to surface insights and suggestions without the user asking.

Triggers:
  - Time-based: morning brief, end-of-day summary, weekly review
  - Context-based: presence detected, activity changed
  - Pattern-based: recurring memory patterns, anomalies
  - Goal-based: outstanding tasks, deadlines approaching
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..core.event_bus import Event, EventBus, EventPriority
from ..core.config import Settings
from ..agents.grok_client import get_grok

logger = logging.getLogger(__name__)


class SuggestionType(Enum):
    MORNING_BRIEF    = "morning_brief"
    EVENING_SUMMARY  = "evening_summary"
    WEEKLY_REVIEW    = "weekly_review"
    TASK_REMINDER    = "task_reminder"
    PATTERN_INSIGHT  = "pattern_insight"
    ANOMALY_ALERT    = "anomaly_alert"
    CONTEXT_TIP      = "context_tip"
    GOAL_NUDGE       = "goal_nudge"


@dataclass
class Suggestion:
    id: str = field(default_factory=lambda: __import__('uuid').uuid4().__str__())
    type: SuggestionType = SuggestionType.CONTEXT_TIP
    text: str = ""
    confidence: float = 0.5
    persona_id: str = "default"
    speak: bool = True          # auto-speak via TTS
    ts: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)
    dismissed: bool = False


class ProactiveEngine:
    """
    Background engine that generates unprompted suggestions.
    Uses a schedule + event-driven hybrid approach.
    """

    def __init__(self, bus: EventBus, settings: Settings) -> None:
        self.bus = bus
        self.settings = settings
        self.grok = get_grok()

        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._suggestions: list[Suggestion] = []
        self._memory_manager = None   # injected
        self._persona_manager = None  # injected
        self._last_triggers: dict[str, float] = {}

        # Cooldowns — don't repeat same type within N seconds
        self._cooldowns: dict[SuggestionType, float] = {
            SuggestionType.MORNING_BRIEF:   86400,   # once a day
            SuggestionType.EVENING_SUMMARY: 86400,
            SuggestionType.WEEKLY_REVIEW:   604800,  # once a week
            SuggestionType.TASK_REMINDER:   3600,    # once an hour
            SuggestionType.PATTERN_INSIGHT: 7200,
            SuggestionType.ANOMALY_ALERT:   1800,
            SuggestionType.CONTEXT_TIP:     900,     # 15 min
            SuggestionType.GOAL_NUDGE:      3600,
        }

    def inject(self, memory=None, personas=None) -> None:
        self._memory_manager = memory
        self._persona_manager = personas

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        self._tasks = [
            asyncio.create_task(self._schedule_loop(), name="proactive-schedule"),
            asyncio.create_task(self._pattern_loop(), name="proactive-patterns"),
        ]
        logger.info("ProactiveEngine started")

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def health(self) -> dict:
        return {
            "suggestions_generated": len(self._suggestions),
            "last_triggers": {k: round(time.time() - v) for k, v in self._last_triggers.items()},
        }

    # ─── Event handlers ──────────────────────────────────────────────────────

    async def on_presence_changed(self, event: Event) -> None:
        payload = event.payload or {}
        if not payload.get("detected"):
            return

        hour = datetime.now().hour
        activity = payload.get("activity", "")

        # Morning brief: first presence detection between 5am–10am
        if 5 <= hour <= 10:
            await self._maybe_trigger(SuggestionType.MORNING_BRIEF)

        # Evening summary: presence between 6pm–10pm
        elif 18 <= hour <= 22:
            await self._maybe_trigger(SuggestionType.EVENING_SUMMARY)

        # Context tip on activity change
        if activity in ("typing", "active"):
            await self._maybe_trigger(SuggestionType.CONTEXT_TIP)

    async def on_memory_updated(self, event: Event) -> None:
        """Check for patterns after new memory is stored."""
        tags = event.payload.get("tags", [])
        if "task" in tags or "deadline" in tags:
            await self._maybe_trigger(SuggestionType.TASK_REMINDER)

    # ─── Schedule loop ────────────────────────────────────────────────────────

    async def _schedule_loop(self) -> None:
        """Check time-based triggers every 5 minutes."""
        while self._running:
            try:
                now = datetime.now()
                hour = now.hour
                weekday = now.weekday()  # 0=Mon

                # Monday morning weekly review
                if weekday == 0 and 8 <= hour <= 9:
                    await self._maybe_trigger(SuggestionType.WEEKLY_REVIEW)

                # Daily goal nudge mid-afternoon
                if 14 <= hour <= 15:
                    await self._maybe_trigger(SuggestionType.GOAL_NUDGE)

            except Exception as e:
                logger.error("Schedule loop error: %s", e)

            await asyncio.sleep(300)  # check every 5 min

    # ─── Pattern loop ─────────────────────────────────────────────────────────

    async def _pattern_loop(self) -> None:
        """Analyze memory patterns every 2 hours."""
        while self._running:
            await asyncio.sleep(7200)
            try:
                await self._maybe_trigger(SuggestionType.PATTERN_INSIGHT)
            except Exception as e:
                logger.error("Pattern loop error: %s", e)

    # ─── Trigger logic ────────────────────────────────────────────────────────

    async def _maybe_trigger(self, suggestion_type: SuggestionType) -> None:
        """Fire a suggestion if cooldown has passed."""
        last = self._last_triggers.get(suggestion_type.value, 0)
        cooldown = self._cooldowns.get(suggestion_type, 900)

        if time.time() - last < cooldown:
            return

        self._last_triggers[suggestion_type.value] = time.time()
        asyncio.create_task(self._generate(suggestion_type))

    async def _generate(self, suggestion_type: SuggestionType) -> None:
        """Generate and publish a suggestion."""
        try:
            text = await self._build_suggestion(suggestion_type)
            if not text or len(text.strip()) < 10:
                return

            persona_id = "default"
            if self._persona_manager:
                persona_id = self._persona_manager.active_id

            suggestion = Suggestion(
                type=suggestion_type,
                text=text,
                confidence=0.8,
                persona_id=persona_id,
            )
            self._suggestions.append(suggestion)

            await self.bus.publish_simple(
                "proactive.suggestion",
                payload={
                    "id": suggestion.id,
                    "type": suggestion_type.value,
                    "text": text,
                    "speak": suggestion.speak,
                    "persona_id": persona_id,
                    "ts": suggestion.ts,
                },
                source="proactive",
                priority=EventPriority.NORMAL,
            )

            logger.info("Proactive [%s]: %s", suggestion_type.value, text[:80])

        except Exception as e:
            logger.error("Suggestion generation failed (%s): %s", suggestion_type.value, e)

    async def _build_suggestion(self, suggestion_type: SuggestionType) -> str:
        """Build suggestion text using Grok + memory context."""
        memories = []
        if self._memory_manager:
            memories = await self._memory_manager.get_context("recent activity", limit=8)
        mem_str = "\n".join(f"- {m}" for m in memories) or "No recent memories."

        persona_prompt = ""
        if self._persona_manager:
            p = self._persona_manager.active
            persona_prompt = f"You are in {p.name} mode. {p.description}."

        now = datetime.now().strftime("%A %B %d, %I:%M %p")

        prompts: dict[SuggestionType, str] = {
            SuggestionType.MORNING_BRIEF: f"""\
{persona_prompt}
Current time: {now}
Recent memory context:
{mem_str}

Generate a brief, energizing morning brief for the user.
Cover: what's likely on their plate today based on memory, one focus recommendation, one thing to be aware of.
Max 3 sentences. Warm but efficient.""",

            SuggestionType.EVENING_SUMMARY: f"""\
{persona_prompt}
Current time: {now}
Recent memory context:
{mem_str}

Generate a brief evening summary.
Cover: what was accomplished today (infer from memories), one thing to carry to tomorrow, one positive observation.
Max 3 sentences. Calm and reflective.""",

            SuggestionType.WEEKLY_REVIEW: f"""\
{persona_prompt}
Current time: {now}
Recent memory context (past week):
{mem_str}

Generate a concise weekly review.
Cover: key themes this week, one win to acknowledge, one thing to improve next week.
Max 4 sentences.""",

            SuggestionType.TASK_REMINDER: f"""\
{persona_prompt}
Memory context:
{mem_str}

Identify any outstanding tasks, deadlines, or follow-ups from the user's memories.
Generate a gentle, specific reminder. If nothing actionable found, return empty string.
Max 2 sentences.""",

            SuggestionType.PATTERN_INSIGHT: f"""\
{persona_prompt}
Memory context:
{mem_str}

Identify a non-obvious pattern in the user's recent behavior, interests, or concerns.
Frame it as an interesting observation, not a critique. Be specific.
Max 2 sentences. Start with "I've noticed...".""",

            SuggestionType.GOAL_NUDGE: f"""\
{persona_prompt}
Memory context:
{mem_str}

Identify the user's most likely current goal or priority from memory context.
Generate a brief mid-afternoon nudge to keep them on track.
Max 1-2 sentences. Motivating but not pushy.""",

            SuggestionType.CONTEXT_TIP: f"""\
{persona_prompt}
Memory context:
{mem_str}
Current time: {now}

Generate one small, immediately useful tip based on what the user is likely doing right now.
Be specific, practical, and brief. Max 1 sentence.""",

            SuggestionType.ANOMALY_ALERT: f"""\
{persona_prompt}
Memory context:
{mem_str}

Identify anything unusual or worth flagging based on the user's recent patterns.
If nothing anomalous, return empty string.
Max 1 sentence.""",
        }

        prompt = prompts.get(suggestion_type, "")
        if not prompt:
            return ""

        return await self.grok.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=150,
        )

    # ─── Query ────────────────────────────────────────────────────────────────

    def get_recent(self, limit: int = 10) -> list[Suggestion]:
        return sorted(
            [s for s in self._suggestions if not s.dismissed],
            key=lambda s: s.ts,
            reverse=True,
        )[:limit]

    def dismiss(self, suggestion_id: str) -> None:
        for s in self._suggestions:
            if s.id == suggestion_id:
                s.dismissed = True
