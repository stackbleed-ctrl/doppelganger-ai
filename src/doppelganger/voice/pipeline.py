"""
Voice Pipeline
Real-time speech-to-text (faster-whisper) + text-to-speech (Kokoro/Piper).
VAD → chunk → transcribe → publish → speak responses.
"""

from __future__ import annotations

import asyncio
import io
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

from ..core.event_bus import Event, EventBus, EventPriority
from ..core.config import Settings

logger = logging.getLogger(__name__)


class VoicePipeline:
    """
    Real-time voice I/O.

    Listen path:  mic → VAD → chunks → faster-whisper → transcript event
    Speak path:   text event → Kokoro/Piper TTS → audio playback
    """

    def __init__(self, bus: EventBus, settings: Settings) -> None:
        self.bus = bus
        self.cfg = settings.voice
        self.data_dir = settings.data_dir / "voice"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._stt_model = None
        self._tts_engine = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self._speaking = False

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        await self._init_stt()
        await self._init_tts()

        if self.cfg.enable_microphone if hasattr(self.cfg, 'enable_microphone') else True:
            self._tasks.append(
                asyncio.create_task(self._listen_loop(), name="voice-listen")
            )

        logger.info("VoicePipeline started | stt=%s tts=%s", self._stt_model is not None, self._tts_engine is not None)

    async def stop(self) -> None:
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def health(self) -> dict:
        return {
            "stt_loaded": self._stt_model is not None,
            "tts_loaded": self._tts_engine is not None,
            "speaking": self._speaking,
        }

    # ─── Event handlers ──────────────────────────────────────────────────────

    async def on_speak_request(self, event: Event) -> None:
        text = event.payload.get("text", "")
        if text:
            asyncio.create_task(self.speak(text))

    # ─── Public API ──────────────────────────────────────────────────────────

    async def transcribe_file(self, audio_path: Path) -> str:
        """Transcribe an audio file. Returns text."""
        if not self._stt_model:
            return ""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._transcribe_sync, str(audio_path))

    async def speak(self, text: str) -> None:
        """Synthesize and play text."""
        if not self._tts_engine:
            logger.debug("TTS not available — skipping speech: %s", text[:40])
            return
        self._speaking = True
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._speak_sync, text)
        except Exception as e:
            logger.error("TTS failed: %s", e)
        finally:
            self._speaking = False

    # ─── STT init ────────────────────────────────────────────────────────────

    async def _init_stt(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            self._stt_model = await loop.run_in_executor(None, self._load_whisper)
            logger.info("faster-whisper loaded: %s/%s", self.cfg.stt_model, self.cfg.stt_compute_type)
        except ImportError:
            logger.warning("faster-whisper not installed — STT disabled")
        except Exception as e:
            logger.warning("STT init failed: %s", e)

    def _load_whisper(self):
        from faster_whisper import WhisperModel
        device = self.cfg.stt_device
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
        return WhisperModel(
            self.cfg.stt_model,
            device=device,
            compute_type=self.cfg.stt_compute_type,
        )

    def _transcribe_sync(self, audio_path: str) -> str:
        if not self._stt_model:
            return ""
        segments, info = self._stt_model.transcribe(
            audio_path,
            beam_size=5,
            language=None,  # auto-detect
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        return " ".join(seg.text.strip() for seg in segments)

    # ─── TTS init ────────────────────────────────────────────────────────────

    async def _init_tts(self) -> None:
        engine = self.cfg.tts_engine
        loop = asyncio.get_running_loop()
        try:
            if engine == "kokoro":
                self._tts_engine = await loop.run_in_executor(None, self._load_kokoro)
            elif engine == "piper":
                self._tts_engine = await loop.run_in_executor(None, self._load_piper)
            logger.info("TTS engine loaded: %s", engine)
        except ImportError:
            logger.warning("%s not installed — TTS disabled", engine)
        except Exception as e:
            logger.warning("TTS init failed: %s", e)

    def _load_kokoro(self):
        from kokoro import KPipeline
        return KPipeline(lang_code="a")  # American English

    def _load_piper(self):
        from piper import PiperVoice
        model_dir = Path("models/piper")
        voice_files = list(model_dir.glob("*.onnx"))
        if not voice_files:
            raise FileNotFoundError(f"No Piper .onnx models in {model_dir}")
        return PiperVoice.load(str(voice_files[0]))

    def _speak_sync(self, text: str) -> None:
        if not self._tts_engine:
            return
        try:
            import sounddevice as sd
            import numpy as np

            if self.cfg.tts_engine == "kokoro":
                generator = self._tts_engine(text, voice=self.cfg.tts_voice, speed=1.0)
                for _, _, audio in generator:
                    sd.play(audio.numpy(), samplerate=24000, blocking=True)
            elif self.cfg.tts_engine == "piper":
                audio_bytes = io.BytesIO()
                self._tts_engine.synthesize(text, audio_bytes)
                audio_bytes.seek(0)
                import soundfile as sf
                data, rate = sf.read(audio_bytes)
                sd.play(data, samplerate=rate, blocking=True)
        except Exception as e:
            logger.error("Speech synthesis error: %s", e)

    # ─── Listen loop ─────────────────────────────────────────────────────────

    async def _listen_loop(self) -> None:
        """
        Continuous VAD + transcription loop.
        Uses webrtcvad for voice activity detection → collects speech chunks
        → sends to Whisper → publishes transcript event.
        """
        try:
            import webrtcvad
            import pyaudio
            import numpy as np
        except ImportError:
            logger.warning("webrtcvad/pyaudio not installed — voice listening disabled")
            return

        vad = webrtcvad.Vad(2)  # aggressiveness 0-3
        pa = pyaudio.PyAudio()
        CHUNK = int(self.cfg.sample_rate * self.cfg.chunk_duration_ms / 1000)
        SILENCE_CHUNKS = 20   # ~600ms of silence to end utterance
        VOICED_CHUNKS = 4     # minimum voiced chunks to trigger transcription

        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.cfg.sample_rate,
                input=True,
                frames_per_buffer=CHUNK,
            )
        except Exception as e:
            logger.warning("Could not open microphone for listening: %s", e)
            pa.terminate()
            return

        logger.info("Voice listening active (VAD + Whisper)")
        voiced_frames: list[bytes] = []
        silence_count = 0
        in_utterance = False

        while self._running:
            try:
                frame = stream.read(CHUNK, exception_on_overflow=False)
                is_speech = False

                try:
                    is_speech = vad.is_speech(frame, self.cfg.sample_rate)
                except Exception:
                    pass

                if is_speech:
                    if not in_utterance:
                        in_utterance = True
                        logger.debug("Speech started")
                    voiced_frames.append(frame)
                    silence_count = 0
                elif in_utterance:
                    voiced_frames.append(frame)
                    silence_count += 1

                    if silence_count >= SILENCE_CHUNKS and len(voiced_frames) >= VOICED_CHUNKS:
                        # End of utterance — transcribe
                        audio_data = b"".join(voiced_frames)
                        asyncio.create_task(
                            self._transcribe_and_publish(audio_data)
                        )
                        voiced_frames = []
                        silence_count = 0
                        in_utterance = False

                await asyncio.sleep(0)  # yield

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Listen loop error: %s", e)
                await asyncio.sleep(0.1)

        stream.stop_stream()
        stream.close()
        pa.terminate()

    async def _transcribe_and_publish(self, audio_bytes: bytes) -> None:
        """Write audio to temp file, transcribe, publish event."""
        import tempfile
        import wave

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        try:
            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.cfg.sample_rate)
                wf.writeframes(audio_bytes)

            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, self._transcribe_sync, tmp_path)

            if text.strip():
                logger.info("Transcript: %s", text[:80])
                await self.bus.publish_simple(
                    "voice.transcript",
                    payload={"text": text, "ts": time.time()},
                    source="voice",
                    priority=EventPriority.HIGH,
                )
        except Exception as e:
            logger.error("Transcription error: %s", e)
        finally:
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass
