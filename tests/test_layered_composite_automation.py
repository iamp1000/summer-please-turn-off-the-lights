from __future__ import annotations
import math
import pytest
from src.layered_effects import (
    ValueNoise1D,
    sample_palette,
    HeatDiffusionSimulation,
    composite_layers,
    LayeredAuroraGenerator,
    LayeredFireGenerator,
    LayeredLavaGenerator,
    NUM_SEGMENTS,
    PALETTES,
)
from src.composite_sync import CompositeSystemManager
from src.automation import PresetManager, CircadianLightingEngine, WindowsPowerGuardian

def test_value_noise_continuity():
    noise_gen = ValueNoise1D(seed=42)
    val1 = noise_gen.noise(1.0)
    val2 = noise_gen.noise(1.01)
    # Output should be continuous and bounded in [0, 1]
    assert 0.0 <= val1 <= 1.0
    assert 0.0 <= val2 <= 1.0
    assert abs(val2 - val1) < 0.05

def test_palette_sampling():
    for name in PALETTES.keys():
        col0 = sample_palette(name, 0.0)
        col_mid = sample_palette(name, 0.5)
        col1 = sample_palette(name, 1.0)
        for c in (col0, col_mid, col1):
            assert len(c) == 3
            assert all(0.0 <= ch <= 1.0 for ch in c)

def test_heat_diffusion_physics():
    sim = HeatDiffusionSimulation(num_zones=50, cooling=0.05, spark_prob=1.0)
    # Step simulation multiple times
    for _ in range(10):
        heat = sim.tick()
        assert len(heat) == 50
        assert all(0.0 <= h <= 1.0 for h in heat)
    # Base zones should be hotter than tip zones on average
    assert float(heat[:10].mean()) >= float(heat[-10:].mean())

def test_composite_layers_blending():
    base = [(0.2, 0.2, 0.2)] * NUM_SEGMENTS
    effect = [(0.5, 0.0, 0.0)] * NUM_SEGMENTS
    overlay = [(0.0, 0.0, 0.8)] * NUM_SEGMENTS

    blended = composite_layers(
        base, effect, overlay,
        effect_opacity=1.0, overlay_opacity=1.0,
        effect_mode="add", overlay_mode="screen"
    )
    assert len(blended) == NUM_SEGMENTS
    for r, g, b in blended:
        assert 0.65 <= r <= 0.75  # 0.2 + 0.5 = 0.7
        assert 0.15 <= g <= 0.25
        assert b > 0.7            # screen blend with 0.8

def test_layered_generators_output():
    aurora = LayeredAuroraGenerator()
    fire = LayeredFireGenerator()
    lava = LayeredLavaGenerator()

    for gen in (aurora, fire, lava):
        frame = gen.render_frame(1.5)
        assert len(frame) == NUM_SEGMENTS
        for h, s, v in frame:
            assert 0 <= h <= 360
            assert 0 <= s <= 100
            assert 0 <= v <= 100

def test_l930_atmospheric_effects():
    from src.effects_l930 import L930EffectsEngine
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    effects = ["ambient_drift", "northern_lights", "fireplace", "sakura", "golden_hour", "deep_ocean"]
    for eff in effects:
        frame = engine._compute(eff, t=2.0)
        assert len(frame) == 50
        for h, s, v in frame:
            assert 0 <= h <= 360
            assert 0 <= s <= 100
            assert 0 <= v <= 100


def test_circadian_solar_schedule():
    circ = CircadianLightingEngine(hub=None)
    
    # Morning (07:30)
    h_morn, s_morn, b_morn = circ.get_solar_target(7.5)
    assert 25 <= h_morn <= 45
    assert b_morn > 40

    # Noon (13:00)
    h_noon, s_noon, b_noon = circ.get_solar_target(13.0)
    assert b_noon == 100
    assert s_noon <= 25  # Daylight crisp white

    # Evening (19:00)
    h_eve, s_eve, b_eve = circ.get_solar_target(19.0)
    assert b_eve < 80
    assert s_eve > 40    # Sunset warm amber

    # Night (02:00)
    h_night, s_night, b_night = circ.get_solar_target(2.0)
    assert b_night <= 15 # Melatonin protecting deep nightlight

def test_preset_manager_memory(tmp_path):
    p_file = tmp_path / "test_presets.json"
    mgr = PresetManager(filepath=p_file)

    presets = mgr.list_presets()
    assert len(presets) >= 3

    # Add custom preset
    mgr.presets["Test Scene"] = {"devices": {"strip1": {"brightness": 88}}}
    mgr.save_to_disk()

    # Re-read
    mgr2 = PresetManager(filepath=p_file)
    assert "Test Scene" in mgr2.list_presets()
    assert mgr2.delete_preset("Test Scene")
    assert "Test Scene" not in mgr2.list_presets()
