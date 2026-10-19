"""
Unit tests for L930 firmware effect builders and hardware constraints.

Validates:
1. Max 16 colors in sequence effects (truncation / clamping).
2. Transition clamping in [0, 6000] ms.
3. Random seed clamping in [1, 600].
4. Display colors icon array <= 4.
5. All 9 curated palettes (sunset, forest, fire, pastel, tide, dusk, ember, warm_mono, auto).
6. Firmware effect definitions generate valid LightEffect objects accepted by plugp100.
"""
from __future__ import annotations

import pytest
from src.firmware_effects import (
    PALETTES,
    get_palette_hsv,
    build_firmware_sequence_effect,
    build_firmware_random_effect,
    make_effect_id,
)
from src.effects_l930 import L930EffectsEngine, EFFECT_CATALOG


def test_firmware_sequence_builder_limits():
    """Verify sequence effect builder clamps to hardware constraints."""
    # 1. 20 colors provided -> must clamp to <= 16 colors
    long_seq = [[i * 15, 100, 100] for i in range(20)]
    fx = build_firmware_sequence_effect(
        name="LongSeq",
        sequence=long_seq,
        spread=10,
        direction=1,
        transition=7500,  # exceeds 6000 limit
    )
    assert len(fx.sequence) == 16, f"Expected 16 colors, got {len(fx.sequence)}"
    assert fx.transition == 6000, f"Expected transition clamped to 6000, got {fx.transition}"
    assert len(fx.display_colors) <= 4, f"Display colors must be <= 4, got {len(fx.display_colors)}"
    assert len(fx.id) == 32, f"Effect ID must be exactly 32 hex chars, got {len(fx.id)}"

    # 2. Negative transition and direction clamping
    fx2 = build_firmware_sequence_effect(
        name="ClampedSeq",
        sequence=[[0, 100, 100], [120, 100, 100]],
        spread=0,       # invalid spread
        direction=9,    # invalid direction
        transition=-50, # invalid transition
    )
    assert fx2.spread >= 1
    assert 1 <= fx2.direction <= 4
    assert fx2.transition >= 0


def test_firmware_random_builder_limits():
    """Verify random effect builder clamps to hardware constraints."""
    fx_rnd = build_firmware_random_effect(
        name="RndStars",
        hue_range=(180, 240),
        saturation_range=(-10, 150),
        brightness_range=(-20, 120),
        transition_range=(-100, 8000),
        random_seed=999,  # exceeds 600 limit
    )
    assert fx_rnd.random_seed == 600, f"Expected seed clamped to 600, got {fx_rnd.random_seed}"
    assert fx_rnd.saturation_range[0] == 0
    assert fx_rnd.saturation_range[1] == 100
    assert fx_rnd.brightness_range[0] == 0
    assert fx_rnd.brightness_range[1] == 100
    assert fx_rnd.transition_range[0] == 0
    assert fx_rnd.transition_range[1] == 6000
    assert fx_rnd.type == "random"


def test_curated_palettes_presence_and_no_neon():
    """Verify Neon and Cyberpunk are removed, and curated palettes are available."""
    assert "neon" not in PALETTES
    assert "cyberpunk" not in PALETTES

    required_palettes = ["sunset", "forest", "fire", "pastel", "tide", "dusk", "ember", "warm_mono", "auto"]
    for p in required_palettes:
        assert p in PALETTES, f"Missing required palette '{p}'"
        hsv_list = get_palette_hsv(p)
        assert len(hsv_list) >= 2
        for h, s, v in hsv_list:
            assert 0 <= h <= 360
            assert 0 <= s <= 100
            assert 0 <= v <= 100


def test_effects_catalog_classification():
    """Verify every effect is classified into firmware, streamed_slow, or live."""
    assert len(EFFECT_CATALOG) >= 15
    for name, meta in EFFECT_CATALOG.items():
        assert meta["kind"] in ("firmware", "streamed_slow", "live"), f"{name} has invalid kind: {meta['kind']}"
        assert meta["group"] in ("Ambient", "Motion", "Seasonal & Novelty"), f"{name} has invalid group: {meta['group']}"


def test_firmware_payload_generation():
    """Verify L930EffectsEngine builds valid LightEffects for all firmware catalog items."""
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    firmware_effects = [k for k, v in EFFECT_CATALOG.items() if v["kind"] == "firmware"]

    for eff_name in firmware_effects:
        fx = engine._build_effect_payload(eff_name)
        assert fx is not None, f"Failed to build firmware payload for '{eff_name}'"
        assert isinstance(fx, type(engine._build_effect_payload("tide")))
        assert len(fx.id) == 32 or fx.id.startswith("TapoStrip_")
        assert fx.type in ("sequence", "random", "pulse", "static")
