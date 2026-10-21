"""
Unit tests for L900 single-zone ambient light effects engine.

Validates that all six L900 ambient effects:
1. Ambient Drift
2. Fireplace
3. Golden Hour
4. Ocean Waves
5. Color Breath
6. Candle Flicker
are genuinely distinguished by their temporal dynamics, color evolution,
and brightness envelopes rather than sharing identical sine-wave loops.
"""
from __future__ import annotations

import math
import pytest
from src.effects import AnimationEngine


def test_l900_ambient_drift_subtle_migration():
    """Verify ambient drift has subtle palette migration and low-amplitude brightness variation."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "ambient_drift"}

    samples = [engine._compute_hsv("ambient_drift", cfg, t=i * 2.0) for i in range(20)]
    hues = [s[0] for s in samples]
    brightnesses = [s[2] for s in samples]

    # Verify subtle low-amplitude variation (around 48-62%, never pumping wildly)
    assert min(brightnesses) >= 45, f"Brightness dropped too low: {min(brightnesses)}"
    assert max(brightnesses) <= 65, f"Brightness pumped too high: {max(brightnesses)}"
    assert max(brightnesses) - min(brightnesses) <= 15, "Ambient drift brightness variation should be low-amplitude"

    # Verify smooth hue migration
    for i in range(len(hues) - 1):
        diff = (abs(hues[i+1] - hues[i]) + 180) % 360 - 180
        assert abs(diff) < 35, f"Discontinuous hue jump in ambient drift: {hues[i]} -> {hues[i+1]}"


def test_l900_fireplace_soft_ember_variation():
    """Fireplace should breathe with slow, bounded warmth, not sharp bright surges."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "fireplace"}
    samples = [engine._compute_hsv("fireplace", cfg, t=i * 0.15) for i in range(80)]
    hues = [sample[0] for sample in samples]
    brightnesses = [sample[2] for sample in samples]
    assert min(hues) >= 18
    assert max(hues) <= 34
    assert min(brightnesses) >= 24
    assert max(brightnesses) <= 72
    assert max(brightnesses) - min(brightnesses) >= 8, "subtle fire variation should remain perceptible"
    steps = [abs(b - a) for a, b in zip(brightnesses, brightnesses[1:])]
    assert max(steps) <= 8, f"Fireplace target change should be gentle, got max step {max(steps)}"

def test_l900_golden_hour_sunlit_and_stable():
    """Verify golden hour provides stable, sunlit radiance with slow amber-to-rose shifts."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "golden_hour"}

    samples = [engine._compute_hsv("golden_hour", cfg, t=i * 5.0) for i in range(20)]
    hues = [s[0] for s in samples]
    brightnesses = [s[2] for s in samples]

    # Stable sunlit brightness (always luminous >= 70%)
    assert min(brightnesses) >= 70, f"Golden hour should remain sunlit and luminous, got {min(brightnesses)}"
    assert max(brightnesses) <= 95, f"Brightness exceeded ceiling: {max(brightnesses)}"

    # Hues stay within warm honey amber and soft coral rose (10° to 45°)
    for h in hues:
        assert 10 <= h <= 50, f"Hue {h} outside warm golden hour spectrum"


def test_l900_ocean_waves_slow_swell_and_recession():
    """Ocean Waves should have a long, restrained swell and recession."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "ocean_waves"}
    # Revised 12s cycle: calm start, soft crest around 5.5s, gradual recession by 11s.
    swell_samples = [engine._compute_hsv("ocean_waves", cfg, t=t) for t in [0.0, 3.0, 5.5]]
    recession_samples = [engine._compute_hsv("ocean_waves", cfg, t=t) for t in [6.0, 8.5, 11.0]]
    assert swell_samples[0][0] >= 195
    assert swell_samples[0][2] <= 35
    peak_sample = swell_samples[-1]
    assert peak_sample[0] <= 190
    assert 60 <= peak_sample[2] <= 72
    end_sample = recession_samples[-1]
    assert end_sample[0] >= 195
    assert end_sample[2] <= 40

def test_l900_color_breath_slow_respiratory_curve():
    """Color Breath uses a long, soft inhale/hold/exhale without high brightness pumping."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "color_breath"}
    t_start = engine._compute_hsv("color_breath", cfg, t=0.0)
    t_peak = engine._compute_hsv("color_breath", cfg, t=6.8)
    t_exhale = engine._compute_hsv("color_breath", cfg, t=13.5)
    assert t_start[0] == t_peak[0] == t_exhale[0]
    assert t_start[1] == t_peak[1] == t_exhale[1]
    assert 20 <= t_start[2] <= 25
    assert 60 <= t_peak[2] <= 68
    assert 20 <= t_exhale[2] <= 27
    assert t_peak[2] - t_start[2] <= 46, "breathing amplitude should remain intentionally restrained"

def test_l900_candle_flicker_low_amplitude_warm_flutter():
    """Candle Flicker should feel like a gentle flame, not fast drafting stutters."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "candle_flicker"}
    # Approximate physical sample cadence rather than evaluating every 50ms.
    samples = [engine._compute_hsv("candle_flicker", cfg, t=i * 0.5) for i in range(15)]
    hues = [sample[0] for sample in samples]
    brightnesses = [sample[2] for sample in samples]
    assert all(25 <= h <= 34 for h in hues)
    assert all(25 <= b <= 62 for b in brightnesses)
    assert max(brightnesses) - min(brightnesses) >= 8, "slow flame variation should remain visible"
    diffs = [abs(b - a) for a, b in zip(brightnesses, brightnesses[1:])]
    assert max(diffs) <= 12, "Candle targets should not have sudden full-brightness drafting jumps"
