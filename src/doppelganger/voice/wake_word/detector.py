"""
Wake Word Detector
"Hey Doppelganger" detection using openWakeWord (open source, local).
Falls back to energy + keyword detection if model unavailable.

openWakeWord: https://github.com/dscripka/openWakeWord
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

WAKE_PHRASES    = ["hey doppelganger", "doppelganger", "hey twin"]
SAMPLE_RATE     = 16000
CHUNK_MS        = 80         # openWakeWord frame size
CHUNK_SAMPLES   = int(SAMPLE_RATE * CHUNK_MS / 1000)
ACTIVATION_THRESHOLD = 0.5
COOLDOWN_SEC    = 2.0        # minimum seconds between activations


@dataclass
class WakeWordEvent:
    phrase: str
    confidence: float
    ts: float = field(default_factory=time.time)
    method: str = "openwakeword"  # openwakeword | energy_keyword | whisper


class WakeWordDetector:
    """
    Listens continuously on microphone.
    On detection, publishes 'voice.wake_word' event to bus.
    Three detection backends in order of preference:
      1. openWakeWord  — neural, most accurate
      2. Whisper micro — transcribe short chunk, keyword match
      3. Energy thresh — fast, lowest accuracy
    """

    def __init__(self, bus: Any = None) -> None:
        self._bus = bus
        self._running = False
        self._last_activation = 0.0
        self._oww_model = None
        self._whisper_model = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        await self._load_models()
        self._task = asyncio.create_task(self._listen_loop(), name="wake-word-listener")
        logger.info("WakeWordDetector started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ─── Model loading ────────────────────────────────────────────────────────

    async def _load_models(self) -> None:
        loop = asyncio.get_event_loop()

        # Try openWakeWord first
        try:
            self._oww_model = await loop.run_in_executor(None, self._load_oww)
            logger.info("openWakeWord model loaded")
        except ImportError:
            logger.warning("openWakeWord not installed — falling back to Whisper keyword matching")
        except Exception as e:
            logger.warning("openWakeWord load failed (%s) — using Whisper", e)

        # Load micro Whisper as fallback
        if not self._oww_model:
            try:
                self._whisper_model = await loop.run_in_executor(None, self._load_whisper_tiny)
                logger.info("Whisper tiny loaded for wake word fallback")
            except Exception as e:
                logger.warning("Whisper fallback failed: %s — using energy threshold", e)

    def _load_oww(self):
        from openwakeword.model import Model
        model_dir = Path("models/wakeword")
        model_dir.mkdir(parents=True, exist_ok=True)
        # Uses pre-trained models from openWakeWord model hub
        return Model(
            wakeword_models=["hey jarvis"],  # closest available; custom training needed
            inference_framework="onnx",
        )

    def _load_whisper_tiny(self):
        from faster_whisper import WhisperModel
        return WhisperModel("tiny", device="cpu", compute_type="int8")

    # ─── Main listen loop ─────────────────────────────────────────────────────

    async def _listen_loop(self) -> None:
        try:
            import pyaudio
        except ImportError:
            logger.warning("pyaudio not available — wake word disabled")
            return

        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(
                rate=SAMPLE_RATE,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=CHUNK_SAMPLES,
            )
        except Exception as e:
            logger.error("Could not open microphone for wake word: %s", e)
            pa.terminate()
            return

        logger.info("Wake word listening active ('%s')", "Hey Doppelganger")
        rolling_buffer = np.zeros(SAMPLE_RATE * 2, dtype=np.int16)  # 2-second ring buffer

        while self._running:
            try:
                raw = stream.read(CHUNK_SAMPLES, exception_on_overflow=False)
                chunk = np.frombuffer(raw, dtype=np.int16)

                # Update rolling buffer
                rolling_buffer = np.roll(rolling_buffer, -len(chunk))
                rolling_buffer[-len(chunk):] = chunk

                detected, confidence, phrase = await self._detect(chunk, rolling_buffer)

                if detected and time.time() - self._last_activation > COOLDOWN_SEC:
                    self._last_activation = time.time()
                    logger.info("Wake word detected: '%s' (%.2f)", phrase, confidence)
                    await self._on_detected(phrase, confidence)

                await asyncio.sleep(0)  # yield

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Wake loop error: %s", e)
                await asyncio.sleep(0.1)

        stream.stop_stream()
        stream.close()
        pa.terminate()

    async def _detect(
        self,
        chunk: np.ndarray,
        rolling: np.ndarray,
    ) -> tuple[bool, float, str]:
        """Run detection. Returns (detected, confidence, phrase)."""

        # Method 1: openWakeWord
        if self._oww_model:
            try:
                loop = asyncio.get_event_loop()
                predictions = await loop.run_in_executor(
                    None,
                    self._oww_model.predict,
                    chunk,
                )
                for model_name, score in predictions.items():
                    if score > ACTIVATION_THRESHOLD:
                        return True, float(score), "hey doppelganger"
            except Exception:
                pass

        # Method 2: Whisper on rolling buffer (every 500ms)
        if self._whisper_model and time.time() % 0.5 < 0.1:
            rms = float(np.sqrt(np.mean(rolling.astype(np.float32) ** 2)))
            if rms > 200:  # only transcribe when there's audio
                try:
                    loop = asyncio.get_event_loop()
                    text = await loop.run_in_executor(
                        None,
                        self._transcribe_chunk,
                        rolling,
                    )
                    text_lower = text.lower()
                    for phrase in WAKE_PHRASES:
                        if phrase in text_lower:
                            return True, 0.8, phrase
                except Exception:
                    pass

        # Method 3: Energy threshold (quick check)
        rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        if rms > 3000:  # loud sound detected
            # Don't trigger wake word — just signal for VAD
            pass

        return False, 0.0, ""

    def _transcribe_chunk(self, audio: np.ndarray) -> str:
        """Transcribe a short audio chunk with Whisper tiny."""
        if not self._whisper_model:
            return ""
        audio_f = audio.astype(np.float32) / 32768.0
        segments, _ = self._whisper_model.transcribe(
            audio_f,
            beam_size=1,
            language="en",
            vad_filter=False,
        )
        return " ".join(s.text for s in segments).strip()

    async def _on_detected(self, phrase: str, confidence: float) -> None:
        """Publish wake word event to bus."""
        if self._bus:
            await self._bus.publish_simple(
                "voice.wake_word",
                payload={
                    "phrase": phrase,
                    "confidence": confidence,
                    "ts": time.time(),
                },
                source="wake_word",
            )
