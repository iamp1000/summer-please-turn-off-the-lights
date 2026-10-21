from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Sequence


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def music_is_genuinely_active(state: Any) -> bool:
    """Conservative gate that excludes analyzed silence and low-level noise."""
    if state is None or bool(getattr(state, "silent", True)):
        return False
    if getattr(getattr(state, "section", None), "value", getattr(state, "section", None)) == "SILENT":
        return False
    try:
        energy = float(getattr(state, "energy", 0.0))
    except (TypeError, ValueError):
        return False
    return energy >= 0.035


def effective_send_rate(controller: Any, fallback_rate: float = 5.0) -> float:
    """Read current sender protection rate; does not modify or raise the cap."""
    sender = getattr(controller, "frame_sender", None) if controller is not None else None
    if sender is None:
        return max(0.5, float(fallback_rate))
    try:
        configured = float(getattr(sender, "max_updates_per_s", fallback_rate))
        aimd_cap = float(getattr(sender, "_aimd_rate_cap", configured))
        return max(0.5, min(configured, aimd_cap))
    except (TypeError, ValueError):
        return max(0.5, float(fallback_rate))


def silence_fade_duration(controller: Any, fallback_rate: float = 5.0) -> float:
    """Fade over at least ~0.75s and stretch under the sender's 1Hz protection mode."""
    rate = effective_send_rate(controller, fallback_rate)
    return max(0.75, 1.15 / rate)


def fade_hsv(hsv: Sequence[int], factor: float) -> tuple[int, int, int]:
    h, s, v = (int(hsv[0]) % 360, max(0, min(100, int(hsv[1]))), max(0, min(100, int(hsv[2]))))
    scale = clamp01(factor)
    if scale <= 0.0 or v <= 0:
        return (0, 0, 0)
    return (h, s, int(round(v * scale)))


def fade_segments(segments: Iterable[Sequence[int]], factor: float) -> list[list[int]]:
    scale = clamp01(factor)
    if scale <= 0.0:
        return [[0, 0, 0] for _ in segments]
    result: list[list[int]] = []
    for zone in segments:
        h, s, v = int(zone[0]) % 360, max(0, min(100, int(zone[1]))), max(0, min(100, int(zone[2])))
        result.append([h, s, int(round(v * scale))] if v > 0 else [0, 0, 0])
    return result


@dataclass
class MusicBrightnessFloor:
    """Small, temporary active-signal floor with asymmetric attack/release."""
    floor_percent: float = 5.5
    attack_tau: float = 0.18
    release_tau: float = 0.55
    level: float = 0.0

    def reset(self):
        self.level = 0.0

    def update(
        self,
        state: Any,
        dt: float,
        master_ceiling: float = 1.0,
        enabled: bool = True,
        force_inactive: bool = False,
    ) -> float:
        active = enabled and not force_inactive and music_is_genuinely_active(state)
        target = self.floor_percent * clamp01(master_ceiling) if active else 0.0
        tau = max(0.01, self.attack_tau if target > self.level else self.release_tau)
        alpha = 1.0 - math.exp(-max(0.0, float(dt)) / tau)
        self.level += alpha * (target - self.level)
        if self.level < 0.05:
            self.level = 0.0
        return self.level

    @staticmethod
    def apply_l900(hsv: Sequence[int], floor: float) -> tuple[int, int, int]:
        h, s, b = int(hsv[0]) % 360, max(0, min(100, int(hsv[1]))), max(0, min(100, int(hsv[2])))
        # A floor never turns a true-black renderer output on.
        return (h, s, max(b, int(round(floor)))) if b > 0 else (0, 0, 0)

    @staticmethod
    def apply_l930(segments: Iterable[Sequence[int]], floor: float) -> list[list[int]]:
        result = []
        floor_int = max(0, min(100, int(round(floor))))
        for zone in segments:
            h, s, v = int(zone[0]) % 360, max(0, min(100, int(zone[1]))), max(0, min(100, int(zone[2])))
            result.append([h, s, max(v, floor_int)] if v > 0 else [0, 0, 0])
        return result
