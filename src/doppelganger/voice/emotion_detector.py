"""
Voice Emotion Detector
Analyzes prosodic features (pitch, energy, rate, MFCCs) to detect emotion.
Uses SpeechBrain or librosa for feature extraction.
Falls back to rule-based prosody analysis without ML models.

Detected emotions: neutral | happy | sad | angry | anxious | excited | tired
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class Emotion(Enum):
    NEUTRAL  = "neutral"
    HAPPY    = "happy"
    SAD      = "sad"
    ANGRY    = "angry"
    ANXIOUS  = "anxious"
    EXCITED  = "excited"
    TIRED    = "tired"
    UNKNOWN  = "unknown"


@dataclass
class ProsodyFeatures:
    pitch_mean_hz: float = 0.0
    pitch_std_hz: float = 0.0
    pitch_range_hz: float = 0.0
    energy_mean: float = 0.0
    energy_std: float = 0.0
    speech_rate_syllables: float = 0.0   # syllables per second
    pause_ratio: float = 0.0             # fraction of time silent
    jitter: float = 0.0                  # pitch variation cycle-to-cycle
    shimmer: float = 0.0                 # amplitude variation


@dataclass
class EmotionEstimate:
    primary: Emotion = Emotion.UNKNOWN
    scores: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    arousal: float = 0.0       # 0=calm → 1=excited
    valence: float = 0.5       # 0=negative → 1=positive
    features: ProsodyFeatures | None = None
    ts: float = field(default_factory=time.time)


class VoiceEmotionDetector:
    """
    Two-level emotion detection:
    1. SpeechBrain IEMOCAP model (if available) — deep learning
    2. Prosodic rule-based analysis (always available)
    """

    def __init__(self) -> None:
        self._sb_model = None
        self._sample_rate = 16000

    async def load_models(self) -> None:
        loop = asyncio.get_event_loop()
        try:
            self._sb_model = await loop.run_in_executor(None, self._load_speechbrain)
            logger.info("SpeechBrain emotion model loaded")
        except ImportError:
            logger.warning("SpeechBrain not installed — using prosodic analysis")
        except Exception as e:
            logger.warning("SpeechBrain load failed (%s) — using prosody", e)

    def _load_speechbrain(self):
        from speechbrain.pretrained import EncoderClassifier
        return EncoderClassifier.from_hparams(
            source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
            savedir="models/speechbrain_emotion",
        )

    # ─── Main analysis ────────────────────────────────────────────────────────

    async def analyze(
        self,
        audio: np.ndarray | None = None,
        audio_path: str | None = None,
        sample_rate: int = 16000,
    ) -> EmotionEstimate:
        """
        Analyze emotion from audio array or file path.
        Returns EmotionEstimate with primary emotion and continuous scores.
        """
        if audio is None and audio_path:
            audio = await self._load_audio(audio_path, sample_rate)
        if audio is None or len(audio) < sample_rate * 0.3:
            return EmotionEstimate(primary=Emotion.UNKNOWN, confidence=0.0)

        self._sample_rate = sample_rate

        # Try SpeechBrain first
        if self._sb_model:
            try:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self._speechbrain_analyze, audio
                )
            except Exception as e:
                logger.debug("SpeechBrain analysis failed: %s", e)

        # Fall back to prosodic analysis
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._prosodic_analyze, audio)

    def _speechbrain_analyze(self, audio: np.ndarray) -> EmotionEstimate:
        import torch
        tensor = torch.tensor(audio.astype(np.float32)).unsqueeze(0)
        with torch.no_grad():
            out = self._sb_model.classify_batch(tensor)

        labels = self._sb_model.hparams.label_encoder.decode_ndim(out[3])
        scores_raw = out[1][0].exp().tolist()
        all_labels = self._sb_model.hparams.label_encoder.ind2lab

        # Map IEMOCAP labels to our emotions
        label_map = {
            "neu": Emotion.NEUTRAL, "hap": Emotion.HAPPY,
            "sad": Emotion.SAD,     "ang": Emotion.ANGRY,
            "fea": Emotion.ANXIOUS, "exc": Emotion.EXCITED,
            "dis": Emotion.SAD,     "sur": Emotion.EXCITED,
        }

        scores: dict[str, float] = {}
        for label, score in zip(all_labels.values(), scores_raw):
            emotion = label_map.get(label[:3], Emotion.UNKNOWN)
            scores[emotion.value] = max(scores.get(emotion.value, 0.0), score)

        primary_str = max(scores, key=lambda k: scores[k])
        primary = Emotion(primary_str)
        confidence = scores[primary_str]

        # Arousal/valence from emotion
        arousal_map = {
            Emotion.ANGRY: 0.9, Emotion.EXCITED: 0.85, Emotion.HAPPY: 0.7,
            Emotion.ANXIOUS: 0.75, Emotion.NEUTRAL: 0.4,
            Emotion.TIRED: 0.2, Emotion.SAD: 0.25,
        }
        valence_map = {
            Emotion.HAPPY: 0.85, Emotion.EXCITED: 0.8, Emotion.NEUTRAL: 0.5,
            Emotion.ANXIOUS: 0.3, Emotion.SAD: 0.15,
            Emotion.ANGRY: 0.1, Emotion.TIRED: 0.35,
        }

        return EmotionEstimate(
            primary=primary,
            scores=scores,
            confidence=confidence,
            arousal=arousal_map.get(primary, 0.5),
            valence=valence_map.get(primary, 0.5),
        )

    def _prosodic_analyze(self, audio: np.ndarray) -> EmotionEstimate:
        """Rule-based emotion from prosodic features — no ML needed."""
        features = self._extract_prosody(audio)
        return self._classify_from_prosody(features)

    def _extract_prosody(self, audio: np.ndarray) -> ProsodyFeatures:
        """Extract prosodic features using librosa or numpy fallback."""
        try:
            import librosa
            f = ProsodyFeatures()
            # Pitch via YIN algorithm
            f0 = librosa.yin(audio, fmin=50, fmax=500, sr=self._sample_rate)
            voiced = f0[f0 > 0]
            if len(voiced) > 0:
                f.pitch_mean_hz  = float(np.mean(voiced))
                f.pitch_std_hz   = float(np.std(voiced))
                f.pitch_range_hz = float(np.max(voiced) - np.min(voiced))

            # Energy
            rms = librosa.feature.rms(y=audio)[0]
            f.energy_mean = float(np.mean(rms))
            f.energy_std  = float(np.std(rms))

            # Speech rate (zero-crossing as syllable proxy)
            zcr = librosa.feature.zero_crossing_rate(audio)[0]
            f.speech_rate_syllables = float(np.mean(zcr) * self._sample_rate / 100)

            # Pause ratio
            silence_threshold = f.energy_mean * 0.1
            f.pause_ratio = float(np.mean(rms < silence_threshold))

            return f
        except ImportError:
            pass

        # Numpy-only fallback
        f = ProsodyFeatures()
        rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
        f.energy_mean = float(rms)

        # Zero-crossing rate as pitch proxy
        zcr = np.mean(np.abs(np.diff(np.sign(audio)))) / 2
        f.pitch_mean_hz = float(zcr * self._sample_rate / 2)

        silence = float(np.mean(np.abs(audio) < rms * 0.1))
        f.pause_ratio = silence

        return f

    def _classify_from_prosody(self, f: ProsodyFeatures) -> EmotionEstimate:
        """Rule-based emotion classification from prosodic features."""
        scores: dict[str, float] = {e.value: 0.0 for e in Emotion}

        # High pitch + high energy + high rate → excited/angry
        if f.pitch_mean_hz > 220 and f.energy_mean > 0.05:
            if f.pitch_std_hz > 50:
                scores[Emotion.EXCITED.value] += 0.4
            else:
                scores[Emotion.ANGRY.value] += 0.35

        # High pitch range + moderate energy → happy
        if f.pitch_range_hz > 100 and 0.02 < f.energy_mean < 0.08:
            scores[Emotion.HAPPY.value] += 0.4

        # Low pitch + low energy + high pause → sad/tired
        if f.pitch_mean_hz < 120 and f.energy_mean < 0.02:
            scores[Emotion.SAD.value] += 0.35
            scores[Emotion.TIRED.value] += 0.3

        # High pitch std + high pause ratio → anxious
        if f.pitch_std_hz > 60 and f.pause_ratio > 0.4:
            scores[Emotion.ANXIOUS.value] += 0.4

        # Moderate everything → neutral
        if all(v < 0.2 for v in scores.values()):
            scores[Emotion.NEUTRAL.value] = 0.6

        # Normalize
        total = sum(scores.values()) or 1.0
        scores = {k: round(v / total, 3) for k, v in scores.items()}

        primary_str = max(scores, key=lambda k: scores[k])
        primary = Emotion(primary_str)
        confidence = min(scores[primary_str] * 1.5, 0.85)

        # Arousal: energy + pitch
        arousal = min((f.energy_mean * 5 + f.speech_rate_syllables / 10) / 2, 1.0)
        # Valence: positive emotions
        positive = scores.get(Emotion.HAPPY.value, 0) + scores.get(Emotion.EXCITED.value, 0)
        negative = scores.get(Emotion.SAD.value, 0) + scores.get(Emotion.ANGRY.value, 0) + scores.get(Emotion.ANXIOUS.value, 0)
        valence  = 0.5 + (positive - negative) * 0.5

        return EmotionEstimate(
            primary=primary,
            scores=scores,
            confidence=confidence,
            arousal=round(float(arousal), 3),
            valence=round(float(valence), 3),
            features=f,
        )

    async def _load_audio(self, path: str, sr: int) -> np.ndarray | None:
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._read_wav, path)
        except Exception as e:
            logger.error("Audio load error: %s", e)
            return None

    def _read_wav(self, path: str) -> np.ndarray:
        import wave
        with wave.open(path, 'rb') as wf:
            raw = wf.readframes(wf.getnframes())
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
