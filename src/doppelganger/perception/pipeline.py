"""
Perception Pipeline
Aggregates all sensing modalities and publishes structured events.
Gracefully degrades: if WiFi CSI hardware is missing, falls back to mic + metrics only.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..core.event_bus import EventBus, EventPriority
from ..core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class PresenceState:
    detected: bool = False
    confidence: float = 0.0
    activity: str = "unknown"   # idle | typing | walking | away
    stress_level: float = 0.0   # 0-1, estimated from typing cadence + mic prosody
    last_seen: float = field(default_factory=time.time)


class PerceptionPipeline:
    """
    Coordinates all sensing modalities.
    Publishing cadence:
      - System metrics:  every N seconds (configurable)
      - Presence events: on change
      - Voice activity:  real-time via VoicePipeline (separate)
    """

    def __init__(self, bus: EventBus, settings: Settings) -> None:
        self.bus = bus
        self.cfg = settings.perception
        self.presence = PresenceState()
        self._tasks: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        self._running = True

        if self.cfg.enable_system_metrics:
            self._tasks.append(
                asyncio.create_task(self._metrics_loop(), name="perception-metrics")
            )

        if self.cfg.enable_wifi_csi:
            try:
                from .wifi_csi import WiFiCSISensor
                self._csi = WiFiCSISensor(self.cfg.csi_interface)
                self._tasks.append(
                    asyncio.create_task(self._csi_loop(), name="perception-csi")
                )
                logger.info("WiFi CSI sensing active on %s", self.cfg.csi_interface)
            except Exception as e:
                logger.warning("WiFi CSI unavailable (%s) — falling back to metrics only", e)

        if self.cfg.enable_microphone:
            self._tasks.append(
                asyncio.create_task(self._mic_activity_loop(), name="perception-mic-activity")
            )

        logger.info(
            "Perception started | csi=%s mic=%s metrics=%s",
            self.cfg.enable_wifi_csi,
            self.cfg.enable_microphone,
            self.cfg.enable_system_metrics,
        )

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def health(self) -> dict:
        return {
            "presence": self.presence.detected,
            "activity": self.presence.activity,
            "confidence": round(self.presence.confidence, 2),
        }

    # ─── System metrics loop ─────────────────────────────────────────────────

    async def _metrics_loop(self) -> None:
        while self._running:
            try:
                metrics = await self._collect_metrics()
                await self.bus.publish_simple(
                    "perception.system_metrics",
                    payload=metrics,
                    source="perception",
                    priority=EventPriority.LOW,
                )
                # Infer activity from CPU/typing patterns
                await self._update_presence_from_metrics(metrics)
            except Exception as e:
                logger.error("Metrics loop error: %s", e)
            await asyncio.sleep(self.cfg.metrics_interval_sec)

    async def _collect_metrics(self) -> dict:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            net = psutil.net_io_counters()
            battery = psutil.sensors_battery()
            return {
                "ts": time.time(),
                "cpu_percent": cpu,
                "mem_percent": mem.percent,
                "mem_available_mb": round(mem.available / 1e6),
                "net_bytes_sent": net.bytes_sent,
                "net_bytes_recv": net.bytes_recv,
                "battery_percent": battery.percent if battery else None,
                "plugged_in": battery.power_plugged if battery else None,
            }
        except ImportError:
            return {"ts": time.time(), "error": "psutil not installed"}

    async def _update_presence_from_metrics(self, metrics: dict) -> None:
        """Heuristic presence detection from CPU activity patterns."""
        cpu = metrics.get("cpu_percent", 0)
        was_detected = self.presence.detected

        # Simple heuristic: CPU > 5% → likely someone at keyboard
        if cpu > 5:
            self.presence.detected = True
            self.presence.confidence = min(0.5 + cpu / 200, 0.9)
            self.presence.last_seen = time.time()
            if cpu > 30:
                self.presence.activity = "active"
            elif cpu > 10:
                self.presence.activity = "typing"
            else:
                self.presence.activity = "idle"
        else:
            # No activity for 5 minutes → away
            if time.time() - self.presence.last_seen > 300:
                self.presence.detected = False
                self.presence.activity = "away"
                self.presence.confidence = 0.8

        if self.presence.detected != was_detected:
            await self.bus.publish_simple(
                "perception.presence_changed",
                payload={
                    "detected": self.presence.detected,
                    "activity": self.presence.activity,
                    "confidence": self.presence.confidence,
                    "ts": time.time(),
                },
                source="perception",
                priority=EventPriority.HIGH,
            )

    # ─── Mic activity loop (VAD, no transcription — that's in VoicePipeline) ─

    async def _mic_activity_loop(self) -> None:
        """
        Monitor microphone energy level for presence and activity detection.
        Actual speech transcription is handled by the VoicePipeline.
        """
        try:
            import pyaudio
            import numpy as np
        except ImportError:
            logger.warning("pyaudio/numpy not available — mic activity monitoring disabled")
            return

        CHUNK = 1024
        RATE = self.cfg.metrics_interval_sec  # reuse setting for simplicity
        pa = pyaudio.PyAudio()

        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=CHUNK,
            )
        except Exception as e:
            logger.warning("Could not open microphone: %s", e)
            pa.terminate()
            return

        while self._running:
            try:
                raw = stream.read(CHUNK, exception_on_overflow=False)
                audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                rms = float(np.sqrt(np.mean(audio ** 2)))
                normalized = min(rms / 32768.0, 1.0)

                if normalized > 0.02:  # voice activity threshold
                    await self.bus.publish_simple(
                        "perception.mic_activity",
                        payload={"rms": normalized, "ts": time.time()},
                        source="perception",
                        priority=EventPriority.NORMAL,
                    )
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.debug("Mic activity error: %s", e)
                await asyncio.sleep(1.0)

        stream.stop_stream()
        stream.close()
        pa.terminate()

    # ─── WiFi CSI loop ────────────────────────────────────────────────────────

    async def _csi_loop(self) -> None:
        """Read WiFi CSI frames and publish presence/pose estimates."""
        while self._running:
            try:
                frame = await self._csi.read_frame()
                if frame:
                    state = self._csi.infer_presence(frame)
                    was = self.presence.detected
                    self.presence.detected = state["confidence"] > self.cfg.presence_threshold
                    self.presence.confidence = state["confidence"]
                    self.presence.activity = state.get("activity", "unknown")

                    await self.bus.publish_simple(
                        "perception.csi_frame",
                        payload=state,
                        source="perception",
                        priority=EventPriority.HIGH,
                    )

                    if self.presence.detected != was:
                        await self.bus.publish_simple(
                            "perception.presence_changed",
                            payload=state,
                            source="perception",
                            priority=EventPriority.HIGH,
                        )
            except Exception as e:
                logger.error("CSI loop error: %s", e)
                await asyncio.sleep(1.0)
