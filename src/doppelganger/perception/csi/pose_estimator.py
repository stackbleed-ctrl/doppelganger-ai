"""
CSI Pose Estimator
Estimates body pose and activity from WiFi CSI amplitude/phase patterns.
Based on research from WiPose, RF-Pose, and CrossSense papers.

Outputs:
  - pose: standing | sitting | lying | walking | away
  - gesture: arms_raised | typing | phone | unknown
  - body_location: rough 2D position relative to router (if multi-antenna)
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ..wifi_csi import CSIFrame

logger = logging.getLogger(__name__)

N_FRAMES_BUFFER = 90   # ~3 seconds at 30fps
BREATHING_RANGE  = (0.15, 0.6)   # Hz: 9–36 bpm
MOVEMENT_THRESH  = 0.08


@dataclass
class PoseEstimate:
    pose: str = "unknown"           # standing | sitting | lying | walking | away
    gesture: str = "unknown"        # typing | phone | arms_raised | still
    confidence: float = 0.0
    breathing_bpm: float | None = None
    heart_rate_bpm: float | None = None   # experimental — high noise
    micro_movement: float = 0.0
    macro_movement: float = 0.0
    body_direction: str = "unknown"       # facing_router | facing_away | sideways
    ts: float = field(default_factory=time.time)


class CSIPoseEstimator:
    """
    Stateful pose estimator that accumulates CSI frames and
    runs feature extraction + rule-based classification.

    Future work: replace rule-based classifier with a lightweight
    CNN trained on labeled CSI data (WiAR dataset compatible).
    """

    def __init__(self) -> None:
        self._amp_buffer: deque = deque(maxlen=N_FRAMES_BUFFER)
        self._phase_buffer: deque = deque(maxlen=N_FRAMES_BUFFER)
        self._ts_buffer: deque = deque(maxlen=N_FRAMES_BUFFER)
        self._fps_estimate = 30.0
        self._last_estimate: PoseEstimate = PoseEstimate()

    def ingest(self, frame: CSIFrame) -> None:
        """Feed a CSI frame into the buffer."""
        self._amp_buffer.append(frame.amplitude.flatten())
        self._phase_buffer.append(frame.phase.flatten())
        self._ts_buffer.append(frame.timestamp)

        # Estimate FPS from timestamps
        if len(self._ts_buffer) >= 2:
            dts = np.diff(list(self._ts_buffer)[-10:])
            if len(dts) > 0:
                self._fps_estimate = float(1.0 / np.mean(dts[dts > 0])) if np.any(dts > 0) else 30.0

    def estimate(self) -> PoseEstimate:
        """Run pose estimation on current buffer. Returns PoseEstimate."""
        if len(self._amp_buffer) < 10:
            return PoseEstimate(confidence=0.0)

        amps  = np.array(list(self._amp_buffer))    # (N, n_subcarriers)
        phases = np.array(list(self._phase_buffer))

        est = PoseEstimate(ts=time.time())

        # ── Macro movement (walking detection) ──────────────────────────────
        amp_std_over_time = np.std(amps, axis=0)
        amp_mean_std = float(np.mean(amp_std_over_time))
        est.macro_movement = round(min(amp_mean_std / 0.5, 1.0), 3)

        # ── Micro movement (breathing/heartbeat) ────────────────────────────
        amp_diff = np.diff(amps, axis=0)
        est.micro_movement = round(float(np.mean(np.abs(amp_diff))), 4)

        # ── Breathing rate via FFT on dominant subcarrier ───────────────────
        est.breathing_bpm = self._estimate_breathing(phases)

        # ── Experimental: heart rate (very noisy without filtering) ─────────
        est.heart_rate_bpm = self._estimate_heart_rate(phases)

        # ── Pose classification (rule-based) ────────────────────────────────
        est.pose, est.confidence = self._classify_pose(
            est.macro_movement, est.micro_movement, est.breathing_bpm
        )

        # ── Gesture classification ───────────────────────────────────────────
        est.gesture = self._classify_gesture(amps, phases, est.macro_movement)

        # ── Body direction from phase asymmetry ─────────────────────────────
        if amps.shape[1] > 1:
            left_mean  = float(np.mean(amps[:, :amps.shape[1]//2]))
            right_mean = float(np.mean(amps[:, amps.shape[1]//2:]))
            asymmetry  = abs(left_mean - right_mean) / (left_mean + right_mean + 1e-6)
            est.body_direction = (
                "facing_router" if asymmetry < 0.1
                else "sideways"  if asymmetry < 0.25
                else "facing_away"
            )

        self._last_estimate = est
        return est

    def _estimate_breathing(self, phases: np.ndarray) -> float | None:
        """FFT-based breathing rate from phase time series."""
        try:
            mean_phase = np.mean(phases, axis=1)
            if len(mean_phase) < 20:
                return None
            # Detrend
            mean_phase -= np.mean(mean_phase)
            fft_vals = np.abs(np.fft.rfft(mean_phase))
            freqs    = np.fft.rfftfreq(len(mean_phase), d=1.0/self._fps_estimate)
            mask = (freqs >= BREATHING_RANGE[0]) & (freqs <= BREATHING_RANGE[1])
            if not mask.any():
                return None
            peak_freq = freqs[mask][np.argmax(fft_vals[mask])]
            bpm = peak_freq * 60
            return round(float(bpm), 1) if 8 < bpm < 40 else None
        except Exception:
            return None

    def _estimate_heart_rate(self, phases: np.ndarray) -> float | None:
        """Experimental: heart rate from high-frequency phase variations."""
        try:
            mean_phase = np.mean(phases, axis=1)
            if len(mean_phase) < 60:
                return None
            mean_phase -= np.mean(mean_phase)
            fft_vals = np.abs(np.fft.rfft(mean_phase))
            freqs    = np.fft.rfftfreq(len(mean_phase), d=1.0/self._fps_estimate)
            # Heart rate: 0.8–3.0 Hz (48–180 bpm)
            mask = (freqs >= 0.8) & (freqs <= 3.0)
            if not mask.any():
                return None
            peak_freq = freqs[mask][np.argmax(fft_vals[mask])]
            bpm = peak_freq * 60
            return round(float(bpm), 1) if 45 < bpm < 180 else None
        except Exception:
            return None

    def _classify_pose(
        self,
        macro: float,
        micro: float,
        breathing_bpm: float | None,
    ) -> tuple[str, float]:
        """Rule-based pose classification."""
        if macro > 0.6:
            return "walking", 0.85

        if macro < 0.05 and micro < 0.002:
            return "away", 0.75

        if breathing_bpm is None:
            if micro > 0.02:
                return "sitting", 0.55
            return "unknown", 0.3

        # Lying down: very low breathing frequency, minimal movement
        if breathing_bpm < 14 and macro < 0.1:
            return "lying", 0.7

        # Standing: moderate micro-movement (postural sway)
        if micro > 0.015 and macro < 0.15:
            return "standing", 0.72

        # Sitting: low micro, present breathing
        if micro < 0.015 and macro < 0.3:
            return "sitting", 0.78

        return "unknown", 0.4

    def _classify_gesture(
        self,
        amps: np.ndarray,
        phases: np.ndarray,
        macro: float,
    ) -> str:
        """Gesture classification from amplitude variance patterns."""
        if macro > 0.5:
            return "walking"

        # Typing: periodic fast arm micro-movements (4–8 Hz)
        try:
            mean_amp = np.mean(amps, axis=1)
            mean_amp -= np.mean(mean_amp)
            fft_vals = np.abs(np.fft.rfft(mean_amp))
            freqs    = np.fft.rfftfreq(len(mean_amp), d=1.0/self._fps_estimate)
            typing_mask = (freqs >= 3.0) & (freqs <= 9.0)
            typing_power = float(np.sum(fft_vals[typing_mask])) if typing_mask.any() else 0
            total_power  = float(np.sum(fft_vals)) + 1e-6
            if typing_power / total_power > 0.3:
                return "typing"
        except Exception:
            pass

        return "still"
