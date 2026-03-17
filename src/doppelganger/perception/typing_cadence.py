"""
Typing Cadence Stress Estimator
Monitors keyboard typing rhythm to infer cognitive load and stress.

Metrics:
  - Inter-keystroke interval (IKI) variance → higher variance = more stress
  - Typing speed (WPM) → very fast or very slow both indicate arousal
  - Error rate (backspace frequency) → proxy for cognitive load
  - Burst patterns → focused flow vs scattered attention
  - Dwell time → how long keys are held (stress = shorter dwell)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60      # Rolling 60-second analysis window
MIN_KEYSTROKES = 20      # Minimum keystrokes before estimating


class StressLevel(Enum):
    CALM      = "calm"
    FOCUSED   = "focused"
    ELEVATED  = "elevated"
    HIGH      = "high"
    UNKNOWN   = "unknown"


@dataclass
class KeyEvent:
    key: str
    ts: float              # press timestamp
    dwell_ms: float = 0.0  # how long key was held (if available)
    is_error: bool = False  # backspace/delete


@dataclass
class StressEstimate:
    level: StressLevel = StressLevel.UNKNOWN
    score: float = 0.0             # 0–1, higher = more stressed
    wpm: float = 0.0
    iki_mean_ms: float = 0.0       # mean inter-keystroke interval
    iki_cv: float = 0.0            # coefficient of variation (variance proxy)
    error_rate: float = 0.0        # backspace fraction
    burst_ratio: float = 0.0       # fraction of time in bursts vs pauses
    confidence: float = 0.0
    ts: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)


class TypingCadenceMonitor:
    """
    Passively monitors typing events and estimates stress/cognitive load.
    
    Integration: hook into OS-level key events via pynput (see daemon below).
    All data stays local — only stress scores are shared with the event bus.
    """

    def __init__(self) -> None:
        self._events: deque[KeyEvent] = deque(maxlen=500)
        self._last_estimate: StressEstimate = StressEstimate()
        self._running = False
        self._listener = None
        self._bus = None

    def set_bus(self, bus: Any) -> None:
        self._bus = bus

    # ─── Key event ingestion ─────────────────────────────────────────────────

    def on_key_press(self, key: str, ts: float | None = None) -> None:
        t = ts or time.time()
        is_error = key in ("backspace", "delete", "Key.backspace", "Key.delete")
        self._events.append(KeyEvent(key=key, ts=t, is_error=is_error))

    def on_key_release(self, key: str, press_ts: float, release_ts: float | None = None) -> None:
        rt = release_ts or time.time()
        dwell = (rt - press_ts) * 1000
        for evt in reversed(self._events):
            if evt.key == key and evt.dwell_ms == 0.0:
                evt.dwell_ms = dwell
                break

    # ─── Analysis ────────────────────────────────────────────────────────────

    def estimate(self) -> StressEstimate:
        """Compute current stress estimate from the rolling window."""
        now = time.time()
        window_start = now - WINDOW_SECONDS
        window_events = [e for e in self._events if e.ts >= window_start]

        if len(window_events) < MIN_KEYSTROKES:
            return StressEstimate(
                level=StressLevel.UNKNOWN,
                confidence=0.0,
                ts=now,
            )

        # ── Inter-keystroke intervals ────────────────────────────────────────
        timestamps = [e.ts for e in window_events]
        ikis_ms = [(timestamps[i+1] - timestamps[i]) * 1000
                   for i in range(len(timestamps)-1)
                   if 0 < (timestamps[i+1] - timestamps[i]) * 1000 < 2000]  # filter pauses

        if not ikis_ms:
            return StressEstimate(level=StressLevel.UNKNOWN, confidence=0.0)

        import statistics
        iki_mean = statistics.mean(ikis_ms)
        iki_std  = statistics.stdev(ikis_ms) if len(ikis_ms) > 1 else 0
        iki_cv   = iki_std / iki_mean if iki_mean > 0 else 0

        # ── WPM (approximate: 5 chars per word) ─────────────────────────────
        char_events = [e for e in window_events if not e.is_error and len(e.key) == 1]
        wpm = (len(char_events) / 5) / (WINDOW_SECONDS / 60)

        # ── Error rate ───────────────────────────────────────────────────────
        error_events = [e for e in window_events if e.is_error]
        error_rate = len(error_events) / max(len(window_events), 1)

        # ── Burst analysis ───────────────────────────────────────────────────
        burst_threshold_ms = 300  # pauses longer than 300ms = gap between bursts
        in_burst_count = sum(1 for iki in ikis_ms if iki < burst_threshold_ms)
        burst_ratio = in_burst_count / max(len(ikis_ms), 1)

        # ── Dwell time ───────────────────────────────────────────────────────
        dwell_times = [e.dwell_ms for e in window_events if 10 < e.dwell_ms < 500]
        mean_dwell = statistics.mean(dwell_times) if dwell_times else 80.0

        # ── Stress score computation ─────────────────────────────────────────
        # Components (each 0–1, higher = more stress)
        iki_stress    = min(iki_cv / 1.5, 1.0)           # high variance = stress
        speed_stress  = min(max(wpm - 60, 0) / 60, 1.0)  # very fast typing
        error_stress  = min(error_rate * 5, 1.0)          # errors = load
        dwell_stress  = max(0, 1 - mean_dwell / 120)      # short dwell = rush

        score = (
            iki_stress   * 0.35 +
            speed_stress * 0.25 +
            error_stress * 0.25 +
            dwell_stress * 0.15
        )
        score = round(min(score, 1.0), 3)

        # ── Level classification ─────────────────────────────────────────────
        if score < 0.25:
            level = StressLevel.CALM
        elif score < 0.45:
            level = StressLevel.FOCUSED
        elif score < 0.65:
            level = StressLevel.ELEVATED
        else:
            level = StressLevel.HIGH

        notes = []
        if iki_cv > 0.8:   notes.append("irregular rhythm")
        if wpm > 80:        notes.append("typing very fast")
        if error_rate > 0.1: notes.append("frequent corrections")
        if burst_ratio > 0.8: notes.append("sustained burst mode")

        est = StressEstimate(
            level=level,
            score=score,
            wpm=round(wpm, 1),
            iki_mean_ms=round(iki_mean, 1),
            iki_cv=round(iki_cv, 3),
            error_rate=round(error_rate, 3),
            burst_ratio=round(burst_ratio, 3),
            confidence=min(len(window_events) / 100, 1.0),
            ts=now,
            notes=notes,
        )
        self._last_estimate = est
        return est

    @property
    def last_estimate(self) -> StressEstimate:
        return self._last_estimate

    # ─── OS-level keyboard listener ──────────────────────────────────────────

    async def start_listening(self) -> None:
        """Start passive keyboard monitoring via pynput."""
        try:
            from pynput import keyboard
            press_times: dict[str, float] = {}

            def on_press(key):
                key_str = str(key)
                ts = time.time()
                press_times[key_str] = ts
                self.on_key_press(key_str, ts)

            def on_release(key):
                key_str = str(key)
                press_ts = press_times.pop(key_str, time.time())
                self.on_key_release(key_str, press_ts)

            self._listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release,
                suppress=False,  # never suppress — passively observe only
            )
            self._listener.start()
            self._running = True
            logger.info("Typing cadence monitor active (pynput)")

            # Periodic stress publishing
            while self._running:
                await asyncio.sleep(30)
                est = self.estimate()
                if self._bus and est.confidence > 0.3:
                    await self._bus.publish_simple(
                        "perception.stress_estimate",
                        payload={
                            "level": est.level.value,
                            "score": est.score,
                            "wpm": est.wpm,
                            "confidence": est.confidence,
                            "notes": est.notes,
                            "ts": est.ts,
                        },
                        source="typing_monitor",
                    )

        except ImportError:
            logger.warning("pynput not installed — typing cadence monitoring disabled")
        except Exception as e:
            logger.error("Keyboard listener error: %s", e)

    def stop(self) -> None:
        self._running = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
