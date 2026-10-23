from __future__ import annotations

import pytest
from src.effects_l930 import L930EffectsEngine, CREATIVE_EFFECTS, SPATIAL_EXPERIMENTS, ACTIVE_EFFECTS, EFFECT_CATALOG


@pytest.fixture
def engine():
    return L930EffectsEngine(controller=None, loop_runner=None, app_state={})


def test_creative_effects_registered_and_configured(engine):
    """The visible shelf is curated around distinct WLED-inspired motion models."""
    assert len(CREATIVE_EFFECTS) == 10
    expected = {"juggle", "colortwinkles", "meteor_shower", "radial_ripple", "fireworks_1d", "dancing_shadows", "bioluminescent_tide", "dissolve_random", "bouncing_balls", "fire_2012"}
    assert set(CREATIVE_EFFECTS) == expected

    for eff in CREATIVE_EFFECTS:
        meta = EFFECT_CATALOG[eff]
        assert meta["kind"] == "streamed_slow"
        assert meta["group"] == "Motion"
        assert "speed" in meta["supported_controls"]
        assert "brightness" in meta["supported_controls"]


def test_visible_effect_shelf_uses_procedural_renderers(engine):
    """Visible designs use their 50-zone renderer rather than a firmware colour sequence."""
    assert set(ACTIVE_EFFECTS) == set(CREATIVE_EFFECTS)
    assert len(ACTIVE_EFFECTS) == 10
    for name in ACTIVE_EFFECTS:
        assert EFFECT_CATALOG[name]["kind"] == "streamed_slow", name
        frame = engine._compute(name, t=1.37)
        assert len(frame) == 50, name
        assert frame != engine._render_rainbow(t=1.37), f"{name} is falling back to Rainbow"
        assert len({tuple(zone) for zone in frame}) > 1, f"{name} is spatially uniform"


def test_creative_effects_generate_valid_smooth_zones(engine):
    """Verify each creative effect produces valid 50-zone addressable HSV frames across cadence steps."""
    time_cadence_steps = [0.0, 0.5, 1.0, 1.5, 2.0, 3.5, 5.0]

    for eff in CREATIVE_EFFECTS:
        for t in time_cadence_steps:
            frame = engine._compute(eff, t=t)
            assert len(frame) == 50, f"{eff} did not generate 50 zones at t={t}"
            for i, (h, s, v) in enumerate(frame):
                assert 0 <= h <= 360, f"{eff} zone {i} invalid hue: {h}"
                assert 0 <= s <= 100, f"{eff} zone {i} invalid sat: {s}"
                assert 0 <= v <= 100, f"{eff} zone {i} invalid val: {v}"


def test_oil_slick_petrol_iridescence_hues(engine):
    """Verify Oil Slick spans a wide petrol palette (cyan, violet, rose, amber) without jarring jumps."""
    frame = engine._compute("oil_slick", t=1.2)
    hues = [h for h, _, _ in frame]
    # Check that diverse petrol spectrum angles are present
    has_cyan = any(170 <= h <= 210 for h in hues)
    has_violet = any(260 <= h <= 300 for h in hues)
    assert has_cyan, "Oil Slick missing cyan interference band"
    assert has_violet, "Oil Slick missing violet interference band"
    assert len(set(hues)) >= 12, "Oil Slick should produce continuous intermediate hues"


def test_silk_ribbons_continuous_blending(engine):
    """Verify Silk Ribbons produce soft Gaussian profiles and smooth multi-color blending."""
    f1 = engine._compute("silk_ribbons", t=0.5)
    f2 = engine._compute("silk_ribbons", t=1.5)
    assert f1 != f2, "Silk Ribbons should animate over time"
    # Ensure brightness has soft gradient, not uniform block
    vals = [v for _, _, v in f1]
    assert max(vals) > min(vals) + 30, "Silk ribbons should have clear peaks and valleys"


def test_nebula_bloom_preserves_negative_space(engine):
    """Verify Nebula Bloom preserves dark negative space rather than washing out the whole strip."""
    frame = engine._compute("nebula_bloom", t=2.0)
    vals = [v for _, _, v in frame]
    dark_zones = [v for v in vals if v < 20]
    # Vast majority of zones should remain subtle and atmospheric
    assert len(dark_zones) >= 15, "Nebula Bloom should maintain dark negative space"


def test_bioluminescent_tide_wave_dynamics(engine):
    """Verify Bioluminescent Tide exhibits rolling oceanic swells with localized crest highlights."""
    f = engine._compute("bioluminescent_tide", t=1.0)
    hues = [h for h, _, _ in f]
    vals = [v for _, _, v in f]
    # Base oceanic tones (navy to cyan)
    assert any(200 <= h <= 240 for h in hues), "Missing abyssal navy tones"
    assert any(170 <= h <= 190 for h in hues), "Missing turquoise crest highlights"
    assert max(vals) >= 40, "Wave crests should be clearly brighter than the trough floor"


def test_ember_drift_thermal_convection(engine):
    """Verify Ember Drift stays within warm copper/amber heat ranges without flashing."""
    for t in [0.0, 1.0, 2.5, 4.0]:
        frame = engine._compute("ember_drift", t=t)
        for h, s, v in frame:
            # Heat hues: Red (0) to Amber (45)
            assert h <= 55 or h >= 350, f"Ember Drift hue out of thermal range: {h}"
            assert s >= 70, f"Ember coals should remain rich and saturated: {s}"


def test_haunted_mansion_never_full_strip_flashes(engine):
    """Verify Haunted Mansion never produces an abrupt full-strip flash at any sampled moment."""
    # Sample every 100ms over a 10-second span
    for step in range(100):
        t = step * 0.10
        frame = engine._compute("haunted_mansion", t=t)
        vals = [v for _, _, v in frame]
        # Full-strip flash would have average brightness > 75 across all 50 zones
        avg_v = sum(vals) / len(vals)
        assert avg_v < 60, f"Haunted Mansion produced unexpected whole-strip flash at t={t}: avg={avg_v}"


def test_candy_cane_soft_antialiased_edges(engine):
    """Verify Candy Cane bands transition smoothly between peppermint red and ivory cream."""
    frame = engine._compute("candy_cane", t=0.5)
    # Check that there are intermediate transition zones, not only binary red/white
    red_count = sum(1 for h, s, v in frame if h >= 340 and s > 80)
    cream_count = sum(1 for h, s, v in frame if 25 <= h <= 50 and s < 40)
    transition_count = len(frame) - (red_count + cream_count)
    assert transition_count >= 4, "Candy Cane should have softened antialiased transition zones"


def test_cyberpunk_synthwave_composition(engine):
    """Verify Cyberpunk composition showcases electric cyan, neon magenta, and ultraviolet."""
    frame = engine._compute("cyberpunk", t=1.0)
    hues = [h for h, _, _ in frame]
    has_cyan = any(170 <= h <= 200 for h in hues)
    has_magenta_violet = any(270 <= h <= 345 for h in hues)
    assert has_cyan, "Cyberpunk missing electric cyan"
    assert has_magenta_violet, "Cyberpunk missing neon magenta / ultraviolet"


def test_new_original_effects_are_dispatched_by_live_stream_worker(engine):
    """New catalog effects must render real frames, never the old flat-color fallback."""
    import threading
    from types import SimpleNamespace

    for name in ("prism_tunnel", "chromatic_undertow", "velvet_aurora"):
        stop = threading.Event()
        submitted = []

        def submit(frame):
            submitted.append(frame)
            stop.set()

        engine._ctrl = SimpleNamespace(submit_frame=submit)
        engine._frame_bus = None
        engine._active_effect_name = name
        engine._active_kind = "streamed_slow"
        engine._effect_generation += 1
        generation = engine._effect_generation
        engine._start_time = __import__("time").monotonic()
        engine._stream_run(stop, generation)

        assert submitted, f"{name} did not submit a live frame"
        frame = submitted[0]
        assert len(frame["segments"]) == 50
        assert len({tuple(zone) for zone in frame["segments"]}) > 5, (
            f"{name} fell back to a uniform frame"
        )
        assert frame["transition"] <= 500, "smooth frames should not be forced to half-second transitions"
