from __future__ import annotations

import math
import random
from types import SimpleNamespace

from src.effects import AnimationEngine


class FakeL900Controller:
    def __init__(self, send_rate=5.0, aimd_rate=None):
        self.last_h = 30
        self.last_s = 70
        self.last_b = 45
        self._app_state = {"brightness": 100}
        effective = send_rate if aimd_rate is None else aimd_rate
        self.frame_sender = SimpleNamespace(
            max_updates_per_s=send_rate,
            _aimd_rate_cap=effective,
        )
        self.frames = []

    def submit_frame(self, frame):
        self.frames.append(frame)

    def clear_frames(self):
        self.frames.clear()


def _hue_delta(a, b):
    return abs((int(a) - int(b) + 180) % 360 - 180)


def test_l900_ambient_intervals_and_advisory_transition_metadata():
    engine = AnimationEngine(FakeL900Controller(), None, {"brightness": 100})

    candle, candle_meta = engine._timing_for_effect("candle_flicker", 1.0)
    fire, fire_meta = engine._timing_for_effect("fireplace", 1.0)
    breath, breath_meta = engine._timing_for_effect("color_breath", 1.0)
    ocean, ocean_meta = engine._timing_for_effect("ocean_waves", 1.0)

    assert 0.48 <= candle <= 0.62
    assert fire >= 0.66
    assert breath >= 0.75
    assert ocean >= 0.95
    for interval, metadata_ms in (
        (candle, candle_meta), (fire, fire_meta), (breath, breath_meta), (ocean, ocean_meta)
    ):
        # This documents pacing intent only; device.py's L900 transport does not
        # submit a native transition parameter.
        assert metadata_ms == round(interval * 1000)


def test_l900_ambient_respects_aimd_one_hertz_without_changing_sender_budget():
    controller = FakeL900Controller(send_rate=5.0, aimd_rate=1.0)
    engine = AnimationEngine(controller, None, {"brightness": 100})
    configured = (controller.frame_sender.max_updates_per_s, controller.frame_sender._aimd_rate_cap)

    for effect in ("candle_flicker", "fireplace", "color_breath", "ocean_waves"):
        interval, _ = engine._timing_for_effect(effect, 1.0)
        assert interval >= 1.0, f"{effect} would generate targets faster than the 1 Hz protected send rate"

    assert (controller.frame_sender.max_updates_per_s, controller.frame_sender._aimd_rate_cap) == configured


def test_l900_candle_flicker_is_a_low_amplitude_warm_flutter(monkeypatch):
    controller = FakeL900Controller()
    engine = AnimationEngine(controller, None, {"brightness": 100})
    monkeypatch.setattr("src.effects.random.uniform", lambda _a, _b: 0.0)

    samples = [engine._compute_hsv("candle_flicker", {"name": "candle_flicker"}, t)
               for t in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5)]
    assert all(25 <= b <= 62 for _, _, b in samples)
    assert all(26 <= h <= 34 for h, _, _ in samples)
    assert max(abs(a[2] - b[2]) for a, b in zip(samples, samples[1:])) <= 15
    assert max(_hue_delta(a[0], b[0]) for a, b in zip(samples, samples[1:])) <= 4


def test_l900_fireplace_breath_and_ocean_use_slow_bounded_target_changes():
    controller = FakeL900Controller()
    engine = AnimationEngine(controller, None, {"brightness": 100})
    random.seed(1)

    sample_times = {
        "fireplace": (0.0, 0.66, 1.32, 1.98, 2.64, 3.30, 3.96),
        "color_breath": (0.0, 0.75, 1.50, 2.25, 3.0, 3.75, 4.50),
        "ocean_waves": (0.0, 0.95, 1.90, 2.85, 3.80, 4.75, 5.70),
    }
    limits = {
        "fireplace": (14, 10),
        "color_breath": (13, 1),
        "ocean_waves": (16, 14),
    }
    for name, times in sample_times.items():
        samples = [engine._compute_hsv(name, {"name": name}, t) for t in times]
        max_v_step, max_h_step = limits[name]
        assert max(abs(a[2] - b[2]) for a, b in zip(samples, samples[1:])) <= max_v_step, (
            f"{name} brightness targets should move gently at their send cadence"
        )
        assert max(_hue_delta(a[0], b[0]) for a, b in zip(samples, samples[1:])) <= max_h_step, (
            f"{name} hue targets should not jump between L900 updates"
        )
