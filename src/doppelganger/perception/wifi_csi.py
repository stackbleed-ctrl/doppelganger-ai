"""
WiFi CSI Sensor
RuView-fork: reads 802.11 Channel State Information for passive presence detection.
Requires: monitor-mode NIC + nexmon_csi or Linux CSI Tool kernel module.
Gracefully stubs out if hardware is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# CSI subcarrier count (varies by NIC/standard — 56 for HT20, 114 for HT40)
N_SUBCARRIERS = 56
CSI_PIPE = Path("/dev/csi0")  # nexmon_csi virtual device


@dataclass
class CSIFrame:
    timestamp: float
    rssi: int
    noise_floor: int
    channel: int
    # Complex CSI matrix: shape (n_rx, n_tx, n_subcarriers)
    csi: np.ndarray
    amplitude: np.ndarray
    phase: np.ndarray


class WiFiCSISensor:
    """
    Reads raw CSI from the kernel pipe and computes presence/pose features.

    Features extracted:
    - Amplitude variance → movement detection
    - Phase difference → breathing rate estimation
    - Doppler shift → activity classification
    """

    def __init__(self, interface: str = "wlan0") -> None:
        self.interface = interface
        self._pipe_fd = None
        self._frame_buffer: list[CSIFrame] = []
        self._buffer_size = 30  # ~1 second at 30 fps

        self._open_pipe()

    def _open_pipe(self) -> None:
        if CSI_PIPE.exists():
            try:
                self._pipe_fd = open(CSI_PIPE, "rb")
                logger.info("CSI pipe opened at %s", CSI_PIPE)
            except PermissionError:
                logger.warning(
                    "Cannot open %s — run with --privileged or grant CAP_NET_RAW", CSI_PIPE
                )
        else:
            logger.warning(
                "CSI pipe %s not found. Install nexmon_csi or Linux-CSI-Tool. "
                "Falling back to simulated data.",
                CSI_PIPE,
            )

    async def read_frame(self) -> CSIFrame | None:
        """Read one CSI frame. Falls back to simulation if hardware unavailable."""
        if self._pipe_fd:
            return await asyncio.get_event_loop().run_in_executor(None, self._read_real_frame)
        return self._simulate_frame()

    def _read_real_frame(self) -> CSIFrame | None:
        """
        Parse a nexmon_csi UDP packet.
        Packet format: [4B magic][2B rssi][2B noise][2B chan][N*8B complex CSI]
        """
        try:
            header = self._pipe_fd.read(10)
            if len(header) < 10:
                return None
            magic, rssi, noise, chan = struct.unpack_from("<IHHH", header)
            if magic != 0x11111111:
                return None

            raw_csi = self._pipe_fd.read(N_SUBCARRIERS * 8)
            if len(raw_csi) < N_SUBCARRIERS * 8:
                return None

            csi_complex = np.frombuffer(raw_csi, dtype=np.complex64).reshape(1, 1, N_SUBCARRIERS)
            amp = np.abs(csi_complex)
            phase = np.angle(csi_complex)

            return CSIFrame(
                timestamp=time.time(),
                rssi=rssi,
                noise_floor=noise,
                channel=chan,
                csi=csi_complex,
                amplitude=amp,
                phase=phase,
            )
        except Exception as e:
            logger.debug("CSI read error: %s", e)
            return None

    def _simulate_frame(self) -> CSIFrame:
        """Synthetic CSI for development/testing without hardware."""
        t = time.time()
        # Simulate breathing (0.3 Hz) + micro-movement noise
        breathing = 0.15 * np.sin(2 * np.pi * 0.3 * t)
        noise = 0.02 * np.random.randn(1, 1, N_SUBCARRIERS)
        phase = breathing + noise
        amp = 1.0 + 0.1 * np.abs(phase) + 0.05 * np.random.randn(1, 1, N_SUBCARRIERS)
        csi = amp * np.exp(1j * phase)

        return CSIFrame(
            timestamp=t,
            rssi=-60,
            noise_floor=-90,
            channel=6,
            csi=csi.astype(np.complex64),
            amplitude=amp,
            phase=phase,
        )

    def infer_presence(self, frame: CSIFrame) -> dict:
        """
        Compute presence/activity from the latest frame + buffer.
        Returns dict with confidence, activity, breathing_bpm.
        """
        self._frame_buffer.append(frame)
        if len(self._frame_buffer) > self._buffer_size:
            self._frame_buffer.pop(0)

        if len(self._frame_buffer) < 5:
            return {"confidence": 0.0, "activity": "unknown", "breathing_bpm": None}

        # Amplitude variance across time → movement detection
        amps = np.stack([f.amplitude for f in self._frame_buffer])
        amp_variance = float(np.var(amps))

        # Phase difference series → breathing detection
        phases = np.stack([f.phase for f in self._frame_buffer])
        phase_diff = np.diff(phases, axis=0)
        phase_variance = float(np.var(phase_diff))

        # Breathing rate estimation via FFT on phase differences
        breathing_bpm = self._estimate_breathing_rate(phases)

        # Activity classification
        if amp_variance > 0.5:
            activity = "walking"
            confidence = min(0.95, 0.6 + amp_variance * 0.1)
        elif amp_variance > 0.05:
            activity = "typing"
            confidence = min(0.85, 0.5 + amp_variance * 0.5)
        elif phase_variance > 0.001:
            activity = "idle"  # present but still
            confidence = 0.75
        else:
            activity = "away"
            confidence = 0.4

        return {
            "confidence": round(confidence, 3),
            "activity": activity,
            "breathing_bpm": breathing_bpm,
            "amp_variance": round(amp_variance, 4),
            "phase_variance": round(phase_variance, 6),
            "ts": frame.timestamp,
        }

    def _estimate_breathing_rate(self, phase_series: np.ndarray) -> float | None:
        """FFT-based breathing rate estimation from phase time series."""
        try:
            # Average across subcarriers
            mean_phase = phase_series[:, 0, 0, :].mean(axis=-1)
            if len(mean_phase) < 10:
                return None
            fft = np.abs(np.fft.rfft(mean_phase))
            freqs = np.fft.rfftfreq(len(mean_phase), d=1 / 30)  # 30 fps assumed
            # Breathing range: 0.1 – 0.6 Hz (6–36 bpm)
            mask = (freqs >= 0.1) & (freqs <= 0.6)
            if not mask.any():
                return None
            peak_freq = freqs[mask][np.argmax(fft[mask])]
            return round(peak_freq * 60, 1)
        except Exception:
            return None
