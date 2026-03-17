"""
Speaker Diarization
Identifies and tracks multiple speakers in audio.
Uses pyannote.audio for state-of-the-art local diarization.
Falls back to energy-based segmentation without pyannote.

Use cases:
  - Multi-person household: "who said what"
  - Meeting transcription with speaker labels
  - Household member profiles
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    speaker_id: str           # "SPEAKER_00", "SPEAKER_01", or custom name
    speaker_name: str = ""    # user-assigned name (e.g. "Steve", "Alex")
    start_sec: float = 0.0
    end_sec: float = 0.0
    text: str = ""            # transcript for this segment
    confidence: float = 0.5
    embedding: list[float] | None = None


@dataclass
class DiarizationResult:
    segments: list[SpeakerSegment]
    speakers: list[str]       # unique speaker IDs found
    duration_sec: float = 0.0
    ts: float = field(default_factory=time.time)


class SpeakerDiarizer:
    """
    Multi-speaker diarization with optional speaker naming.
    
    Workflow:
      1. Diarize audio into speaker segments
      2. Transcribe each segment with Whisper
      3. Map speaker IDs to known profiles (if trained)
      4. Return labelled transcript
    """

    def __init__(self, profiles_dir: Path | None = None) -> None:
        self._pipeline = None          # pyannote pipeline
        self._whisper = None
        self._profiles_dir = profiles_dir or Path.home() / ".doppelganger" / "speaker_profiles"
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._speaker_names: dict[str, str] = {}  # speaker_id → name
        self._load_speaker_names()

    async def load_models(self) -> None:
        loop = asyncio.get_event_loop()
        # Load pyannote
        try:
            self._pipeline = await loop.run_in_executor(None, self._load_pyannote)
            logger.info("pyannote diarization pipeline loaded")
        except ImportError:
            logger.warning("pyannote.audio not installed — using energy-based segmentation")
        except Exception as e:
            logger.warning("pyannote failed (%s) — using energy segmentation", e)

        # Load Whisper
        try:
            self._whisper = await loop.run_in_executor(None, self._load_whisper)
            logger.info("Whisper loaded for diarization transcription")
        except Exception as e:
            logger.warning("Whisper for diarization failed: %s", e)

    def _load_pyannote(self):
        import torch
        from pyannote.audio import Pipeline
        hf_token = __import__('os').environ.get("HF_TOKEN", "")
        if not hf_token:
            raise ValueError("HF_TOKEN env var required for pyannote (free at huggingface.co)")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        if torch.cuda.is_available():
            pipeline = pipeline.to(torch.device("cuda"))
        return pipeline

    def _load_whisper(self):
        from faster_whisper import WhisperModel
        return WhisperModel("base", device="auto", compute_type="int8")

    # ─── Main diarization ────────────────────────────────────────────────────

    async def diarize(
        self,
        audio_path: str | Path,
        num_speakers: int | None = None,
        min_speakers: int = 1,
        max_speakers: int = 6,
        language: str | None = None,
    ) -> DiarizationResult:
        """
        Diarize and transcribe an audio file.
        Returns DiarizationResult with labelled segments.
        """
        loop = asyncio.get_event_loop()
        path = Path(audio_path)

        if self._pipeline:
            segments = await loop.run_in_executor(
                None,
                self._run_pyannote,
                str(path),
                num_speakers,
                min_speakers,
                max_speakers,
            )
        else:
            segments = await loop.run_in_executor(
                None,
                self._energy_segmentation,
                str(path),
            )

        # Transcribe each segment
        if self._whisper:
            segments = await loop.run_in_executor(
                None,
                self._transcribe_segments,
                segments,
                str(path),
                language,
            )

        # Map speaker IDs to names
        for seg in segments:
            if seg.speaker_id in self._speaker_names:
                seg.speaker_name = self._speaker_names[seg.speaker_id]

        speakers = list({s.speaker_id for s in segments})
        duration = max((s.end_sec for s in segments), default=0.0)

        return DiarizationResult(
            segments=segments,
            speakers=speakers,
            duration_sec=duration,
        )

    def _run_pyannote(
        self,
        audio_path: str,
        num_speakers: int | None,
        min_speakers: int,
        max_speakers: int,
    ) -> list[SpeakerSegment]:
        kwargs = {}
        if num_speakers:
            kwargs["num_speakers"] = num_speakers
        else:
            kwargs["min_speakers"] = min_speakers
            kwargs["max_speakers"] = max_speakers

        diarization = self._pipeline(audio_path, **kwargs)
        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(SpeakerSegment(
                speaker_id=speaker,
                start_sec=turn.start,
                end_sec=turn.end,
                confidence=0.9,
            ))
        return segments

    def _energy_segmentation(self, audio_path: str) -> list[SpeakerSegment]:
        """
        Simple energy-based segmentation as fallback.
        Cannot distinguish speakers, labels all as SPEAKER_00.
        """
        import wave
        try:
            with wave.open(audio_path, 'rb') as wf:
                n_frames = wf.getnframes()
                rate     = wf.getframerate()
                raw      = wf.readframes(n_frames)
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        except Exception:
            return []

        # 200ms windows
        win = int(rate * 0.2)
        energies = [
            np.sqrt(np.mean(audio[i:i+win]**2))
            for i in range(0, len(audio)-win, win//2)
        ]
        threshold = np.mean(energies) * 0.5
        segments, in_speech, start = [], False, 0.0

        for i, e in enumerate(energies):
            t = i * 0.1
            if not in_speech and e > threshold:
                in_speech = True
                start = t
            elif in_speech and e <= threshold:
                in_speech = False
                segments.append(SpeakerSegment(
                    speaker_id="SPEAKER_00",
                    start_sec=start,
                    end_sec=t,
                    confidence=0.4,
                ))
        return segments

    def _transcribe_segments(
        self,
        segments: list[SpeakerSegment],
        audio_path: str,
        language: str | None,
    ) -> list[SpeakerSegment]:
        """Transcribe audio for each speaker segment."""
        if not self._whisper:
            return segments

        try:
            import tempfile
            import wave
            # Load full audio
            with wave.open(audio_path, 'rb') as wf:
                rate     = wf.getframerate()
                n_frames = wf.getnframes()
                sampwidth = wf.getsampwidth()
                raw      = wf.readframes(n_frames)
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

            for seg in segments:
                start_i = int(seg.start_sec * rate)
                end_i   = int(seg.end_sec * rate)
                chunk   = audio[start_i:end_i]
                if len(chunk) < rate * 0.2:
                    continue

                # Write chunk to temp file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    tmp_path = tf.name
                with wave.open(tmp_path, 'wb') as wf_out:
                    wf_out.setnchannels(1)
                    wf_out.setsampwidth(2)
                    wf_out.setframerate(rate)
                    wf_out.writeframes((chunk * 32768).astype(np.int16).tobytes())

                whisper_segs, _ = self._whisper.transcribe(
                    tmp_path,
                    beam_size=3,
                    language=language,
                    vad_filter=True,
                )
                seg.text = " ".join(s.text.strip() for s in whisper_segs)
                import os
                try: os.unlink(tmp_path)
                except: pass

        except Exception as e:
            logger.error("Transcription error: %s", e)

        return segments

    # ─── Speaker naming ──────────────────────────────────────────────────────

    def name_speaker(self, speaker_id: str, name: str) -> None:
        """Assign a human name to a speaker ID."""
        self._speaker_names[speaker_id] = name
        self._save_speaker_names()
        logger.info("Speaker %s named: %s", speaker_id, name)

    def _load_speaker_names(self) -> None:
        names_file = self._profiles_dir / "names.json"
        if names_file.exists():
            import json
            self._speaker_names = json.loads(names_file.read_text())

    def _save_speaker_names(self) -> None:
        import json
        names_file = self._profiles_dir / "names.json"
        names_file.write_text(json.dumps(self._speaker_names, indent=2))

    def format_transcript(self, result: DiarizationResult) -> str:
        """Format diarization result as readable transcript."""
        lines = []
        for seg in result.segments:
            name = seg.speaker_name or seg.speaker_id
            if seg.text.strip():
                timestamp = f"[{seg.start_sec:.1f}s]"
                lines.append(f"{timestamp} {name}: {seg.text.strip()}")
        return "\n".join(lines)
