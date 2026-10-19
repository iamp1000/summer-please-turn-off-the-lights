"""
Windows Master Volume Probe & Audio Compensation Engine (ported from LumiSync).

WASAPI loopback captures audio *after* the Windows endpoint (master/speaker) fader,
so turning down system volume diminishes the capture level and dims the lights.
This probe reads the hardware endpoint volume in dB via Core Audio (pycaw)
and computes 1.0 / gain to make the visualizer completely invariant to system volume.
"""

from __future__ import annotations
import math
import sys
from typing import Optional, Tuple
import numpy as np


class MasterVolumeProbe:
    """Reads the Windows master-volume fader in dB so audio reactive lighting is invariant to speaker volume."""

    def __init__(self) -> None:
        self._endpoint = None
        self._available = False
        self._last_gain = 1.0

        if sys.platform == "win32":
            try:
                from pycaw.pycaw import AudioUtilities
                speakers = AudioUtilities.GetSpeakers()
                endpoint = getattr(speakers, "EndpointVolume", None)
                if endpoint is None and hasattr(speakers, "Activate"):
                    from ctypes import POINTER, cast
                    from comtypes import CLSCTX_ALL
                    from pycaw.pycaw import IAudioEndpointVolume
                    interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    endpoint = cast(interface, POINTER(IAudioEndpointVolume))
                if endpoint is not None:
                    # Probe once to test endpoint validity
                    endpoint.GetMasterVolumeLevel()
                    self._endpoint = endpoint
                    self._available = True
            except Exception:
                self._endpoint = None
                self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def linear_gain(self) -> Optional[float]:
        """
        Returns linear amplitude in range [0.0, 1.0], or None if unreadable.
        Uses dB level: gain = 10^(dB / 20).
        """
        if not self._available or self._endpoint is None:
            return None
        try:
            if self._endpoint.GetMute():
                self._last_gain = 0.0
                return 0.0
            decibels = float(self._endpoint.GetMasterVolumeLevel())
            gain = 10.0 ** (decibels / 20.0)
            self._last_gain = max(0.0, min(1.0, gain))
            return self._last_gain
        except Exception:
            return self._last_gain

    def compensate_samples(self, samples: np.ndarray, max_boost: float = 40.0) -> np.ndarray:
        """Scales incoming PCM samples to invert master-volume attenuation."""
        gain = self.linear_gain()
        if gain is None or gain <= 1e-4:
            return samples
        boost = min(max_boost, 1.0 / gain)
        if abs(boost - 1.0) < 0.05:
            return samples
        return samples * boost


# Global singleton
_master_volume_probe: Optional[MasterVolumeProbe] = None


def get_master_volume_probe() -> MasterVolumeProbe:
    global _master_volume_probe
    if _master_volume_probe is None:
        _master_volume_probe = MasterVolumeProbe()
    return _master_volume_probe
