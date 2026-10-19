from __future__ import annotations
import math
import pytest
from src.pipeline import (
    rgb_to_oklab,
    oklab_to_rgb,
    rgb_to_oklch,
    oklch_to_rgb,
    lerp_oklab,
    lerp_oklch,
    rgb_to_tapo_hsv,
    tapo_hsv_to_rgb,
    RenderPipeline,
    AsymmetricSmoother,
    ZoneAsymmetricSmoother,
)

def test_oklab_roundtrip():
    colors = [
        (1.0, 0.0, 0.0), # Pure Red
        (0.0, 1.0, 0.0), # Pure Green
        (0.0, 0.0, 1.0), # Pure Blue
        (1.0, 1.0, 0.0), # Yellow
        (0.0, 1.0, 1.0), # Cyan
        (0.5, 0.5, 0.5), # Grey
        (1.0, 1.0, 1.0), # White
        (0.0, 0.0, 0.0), # Black
    ]
    for r, g, b in colors:
        L, a, b_val = rgb_to_oklab(r, g, b)
        r2, g2, b2 = oklab_to_rgb(L, a, b_val)
        assert abs(r - r2) < 0.01
        assert abs(g - g2) < 0.01
        assert abs(b - b2) < 0.01

def test_oklab_interpolation_preserves_vibrancy():
    # In naive RGB, halfway between Red (1,0,0) and Green (0,1,0) is muddy Dark Olive (0.5, 0.5, 0).
    # In OKLab, halfway between Red and Green retains perceptual brightness.
    c_red = (1.0, 0.0, 0.0)
    c_green = (0.0, 1.0, 0.0)
    mid_oklab = lerp_oklab(c_red, c_green, 0.5)

    # In OKLab, mid brightness (perceptual L) is higher than naive RGB mid
    L_mid, _, _ = rgb_to_oklab(*mid_oklab)
    L_naive, _, _ = rgb_to_oklab(0.5, 0.5, 0.0)
    assert L_mid >= L_naive

def test_tapo_hsv_roundtrip():
    # Test red hue 0, 100 sat, 100 val
    r, g, b = tapo_hsv_to_rgb(0, 100, 100)
    assert abs(r - 1.0) < 0.02 and g < 0.02 and b < 0.02

    h, s, v = rgb_to_tapo_hsv(r, g, b)
    assert h == 0
    assert s == 100
    assert v == 100

def test_render_pipeline_gamma_and_calibration():
    pipeline = RenderPipeline(gamma=2.2, r_calib=1.0, g_calib=0.9, b_calib=0.8, master_ceiling=0.5)
    r, g, b = pipeline.calibrate_and_correct(1.0, 1.0, 1.0)

    # Full white should be scaled down by ceiling 0.5 and calibration multipliers
    assert r <= 0.50
    assert g <= 0.45
    assert b <= 0.40

    # Low brightness should be non-linear (gamma curve: 0.1 ** 2.2 ≈ 0.006)
    r_dim, _, _ = pipeline.calibrate_and_correct(0.1, 0.1, 0.1)
    assert r_dim < 0.01

def test_asymmetric_smoother():
    # Attack = 0.8 (fast), Decay = 0.1 (slow)
    smoother = AsymmetricSmoother(attack_rate=0.80, decay_rate=0.10)
    smoother.reset(0.0)

    # Rise from 0 to 100 should jump by 80 on first step
    val1 = smoother.update(100.0)
    assert val1 == 80.0

    # Fall from 80 to 0 should only decay by 10% on first step
    val2 = smoother.update(0.0)
    assert round(val2, 1) == 72.0  # 80 - (80 * 0.1) = 72

def test_zone_asymmetric_smoother_50_zones():
    smoother = ZoneAsymmetricSmoother(num_zones=50, attack_rate=0.9, decay_rate=0.1)
    targets = [[180, 100, 100] for _ in range(50)]

    res1 = smoother.update(targets)
    assert len(res1) == 50
    # Values should jump close to 90 on attack
    assert res1[0][2] >= 85

    # Fall to 0
    dark_targets = [[180, 100, 0] for _ in range(50)]
    res2 = smoother.update(dark_targets)
    # Values should decay slowly (not drop to 0 instantly)
    assert res2[0][2] >= 65
