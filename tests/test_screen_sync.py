from __future__ import annotations
import numpy as np
import pytest
from src.screen_sync import detect_letterbox_bounds, extract_dominant_color_weighted, SCREEN_PROFILES

def test_letterbox_detection():
    # Create 100x100 image with 20px black bars on top and bottom, and bright red in middle
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[20:80, :, 2] = 255  # Red in center

    left, top, right, bottom = detect_letterbox_bounds(img, black_thresh=10)
    assert top >= 16 and top <= 24
    assert bottom >= 76 and bottom <= 84
    assert left == 0
    assert right == 100

def test_saturation_weighted_dominant_color():
    # Create pixels where 90% are dull grey (128, 128, 128) and 10% are vivid cyan (255, 255, 0 in BGR)
    pixels = np.full((100, 3), 128, dtype=np.uint8)
    pixels[:10] = [255, 255, 0]  # Cyan

    # A plain average gives saturation around ~8%
    # But saturation-weighted extraction should heavily favor the vivid cyan
    h, s, v = extract_dominant_color_weighted(pixels, sat_boost=1.3)
    # Cyan hue is ~180
    assert 160 <= h <= 200
    assert s > 40  # Saturated, not washed out grey!

def test_screen_profiles():
    assert "video" in SCREEN_PROFILES
    assert "gaming" in SCREEN_PROFILES
    assert "desktop" in SCREEN_PROFILES
    assert SCREEN_PROFILES["gaming"]["attack_rate"] > SCREEN_PROFILES["desktop"]["attack_rate"]
