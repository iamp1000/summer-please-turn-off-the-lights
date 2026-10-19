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


def test_l900_fireplace_irregular_surges():
    """Verify fireplace has irregular thermal warmth changes and flame surges (not a simple sine wave)."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "fireplace"}

    samples = [engine._compute_hsv("fireplace", cfg, t=i * 0.15) for i in range(80)]
    hues = [s[0] for s in samples]
    brightnesses = [s[2] for s in samples]

    # Color shifts with flame heat: deep crimson-orange (12-16) to hot yellow (35-42)
    assert min(hues) <= 22, f"Expected deep ember hue, got min {min(hues)}"
    assert max(hues) >= 32, f"Expected hot flame surge hue, got max {max(hues)}"

    # Dynamic flame surges: reaches high peaks (>70) and low simmer (<45)
    assert max(brightnesses) >= 70, f"Expected flame surge peak, got max {max(brightnesses)}"
    assert min(brightnesses) <= 45, f"Expected low ember simmer, got min {min(brightnesses)}"

    # Non-linear / asymmetric: flame rises and falls with thermal turbulence
    deltas = [brightnesses[i+1] - brightnesses[i] for i in range(len(brightnesses) - 1)]
    assert any(d > 10 for d in deltas), "Expected rapid flame flare surge"


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


def test_l900_ocean_waves_asymmetric_swell_and_recession():
    """Verify ocean waves has distinct swell and recession envelopes (non-linear surf)."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "ocean_waves"}

    # Period is 7.5s
    # Sample swell phase (t=0.0 to 3.0) and recession phase (t=3.5 to 7.0)
    swell_samples = [engine._compute_hsv("ocean_waves", cfg, t=t) for t in [0.0, 1.5, 3.2]]
    recession_samples = [engine._compute_hsv("ocean_waves", cfg, t=t) for t in [3.8, 5.0, 7.0]]

    # At start of swell: deep ocean navy (hue ~215)
    assert swell_samples[0][0] >= 195
    assert swell_samples[0][2] <= 35  # calm deep water

    # Near peak of swell: bright coastal teal/seafoam (hue ~170, high brightness)
    peak_sample = swell_samples[-1]
    assert peak_sample[0] <= 185
    assert peak_sample[2] >= 70  # breaking wave crest

    # Recession returns smoothly back to deeper calmer indigo
    end_sample = recession_samples[-1]
    assert end_sample[0] >= 195
    assert end_sample[2] <= 40


def test_l900_color_breath_respiratory_curve():
    """Verify color breath holds hue and focuses strictly on physiological inhale/exhale."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "color_breath"}

    # Sample across 10-second respiratory cycle
    # Inhale: t = 0 to 4s (expands)
    # Hold: t = 4 to 5s (peak)
    # Exhale: t = 5 to 10s (relaxes)
    t_start = engine._compute_hsv("color_breath", cfg, t=0.0)
    t_peak = engine._compute_hsv("color_breath", cfg, t=4.5)
    t_exhale = engine._compute_hsv("color_breath", cfg, t=9.5)

    # Hue is held constant without distracting color changes
    assert t_start[0] == t_peak[0] == t_exhale[0]
    assert t_start[1] == t_peak[1] == t_exhale[1]

    # Brightness follows respiratory expansion and relaxation
    assert t_start[2] <= 20, f"Expected quiet baseline at start of inhale, got {t_start[2]}"
    assert t_peak[2] >= 80, f"Expected full expansion at peak, got {t_peak[2]}"
    assert t_exhale[2] <= 25, f"Expected calm baseline at end of exhale, got {t_exhale[2]}"


def test_l900_candle_flicker_fast_irregular_drafts():
    """Verify candle flicker exhibits fast irregular micro-drops and color-temp shifts."""
    engine = AnimationEngine(controller=None, loop_runner=None, app_state={})
    cfg = {"name": "candle_flicker"}

    # Rapid high-frequency sampling (every 50ms)
    samples = [engine._compute_hsv("candle_flicker", cfg, t=i * 0.05) for i in range(50)]
    hues = [s[0] for s in samples]
    brightnesses = [s[2] for s in samples]

    # Valid bounds
    assert all(20 <= h <= 45 for h in hues)
    assert all(15 <= b <= 100 for b in brightnesses)

    # Verify high irregularity: significant variance in brightness across short intervals
    diffs = [abs(brightnesses[i+1] - brightnesses[i]) for i in range(len(brightnesses) - 1)]
    assert max(diffs) >= 10, "Candle flicker must have sudden drafting flutter jumps"
