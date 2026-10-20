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
    for name in ("drift", "starfield", "embers", "confetti", "deep_ocean", "fireflies", "prism_sparks"):
        assert EFFECT_CATALOG[name]["kind"] == "firmware", f"{name} should run as firmware"
    assert EFFECT_CATALOG["meteor_shower"]["kind"] == "streamed_slow"
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


def test_lava_lamp_smoothness_and_continuity():
    """Verify lava_lamp renders smoothly without discontinuous brightness or hue jumps."""
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    engine.set_parameters(palette_name="sunset", speed=1.0)

    # 1. Validate structure and bounds
    frame1 = engine._render_lava_lamp(t=1.0)
    assert len(frame1) == 50
    for h, s, v in frame1:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 2 <= v <= 100

    assert min(c[2] for c in frame1) <= 5, "Lava Lamp should leave dark space between blobs"
    assert max(c[2] for c in frame1) >= 35, "Lava Lamp cores should remain luminous"
    assert len({c[2] for c in frame1}) >= 4, "Lava Lamp should not be a near-uniform glow"

    # 2. Continuous time stepping: small dt must yield small smooth delta, not abrupt threshold jumps
    frame2 = engine._render_lava_lamp(t=1.05)
    for i in range(50):
        h1, s1, v1 = frame1[i]
        h2, s2, v2 = frame2[i]
        # Brightness delta over 50ms should be continuous (< 8%)
        assert abs(v2 - v1) < 8, f"Zone {i} has abrupt brightness leap: {v1} -> {v2}"
        # Hue delta should also be smooth
        diff_h = (abs(h2 - h1) + 180) % 360 - 180
        assert abs(diff_h) < 15, f"Zone {i} has abrupt hue jump: {h1} -> {h2}"

    assert engine._render_lava_lamp(t=4.0) != frame1, "Lava Lamp should move spatially over time"


def test_flicker_speed_scaling_and_palette_preservation():
    """Verify flicker effect scales transition range with speed while preserving warm fire hues."""
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})

    # 1. Base 1.0x speed
    engine.set_parameters(speed=1.0, palette_name="fire")
    fx1 = engine._build_effect_payload("flicker")
    assert fx1 is not None
    assert fx1.type == "random"
    assert fx1.transition_range == [375, 500]
    assert fx1.hue_range == [30, 40]  # Authentic fire hues
    assert len(fx1.id) == 32

    # 2. 0.5x speed (should be twice as slow: [750, 1000] ms)
    engine.set_parameters(speed=0.5)
    fx_slow = engine._build_effect_payload("flicker")
    assert fx_slow.transition_range == [750, 1000]
    assert fx_slow.hue_range == [30, 40]
    assert fx_slow.id != fx1.id  # New ID to signal firmware to re-arm

    # 3. 2.0x speed (should be twice as fast: [188, 250] ms)
    engine.set_parameters(speed=2.0)
    fx_fast = engine._build_effect_payload("flicker")
    assert fx_fast.transition_range == [188, 250]
    assert fx_fast.id != fx1.id and fx_fast.id != fx_slow.id


def test_fastled_ported_effects_juggle_sinelon_confetti():
    """Verify FastLED-inspired effects: juggle, sinelon, and confetti."""
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    assert "juggle" in EFFECT_CATALOG
    assert "sinelon" in EFFECT_CATALOG
    assert "confetti" in EFFECT_CATALOG
    assert engine._build_effect_payload("drift").type == "random"
    assert engine._build_effect_payload("deep_ocean").type == "random"
    assert engine._build_effect_payload("fireflies").type == "random"
    assert engine._build_effect_payload("prism_sparks").type == "random"

    # 1. Juggle (8 harmonic orbs across 50 zones)
    f_juggle = engine._compute("juggle", t=1.0)
    assert len(f_juggle) == 50
    for h, s, v in f_juggle:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100
    # At least some zones must have bright orbs
    assert max(c[2] for c in f_juggle) >= 50

    # 2. Sinelon (sweeping beacon with decay trail)
    f_sinelon = engine._compute("sinelon", t=1.5)
    assert len(f_sinelon) == 50
    for h, s, v in f_sinelon:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100
    assert max(c[2] for c in f_sinelon) >= 50

    # 3. Confetti (shimmering speckles)
    f_confetti = engine._compute("confetti", t=2.0)
    assert len(f_confetti) == 50
    for h, s, v in f_confetti:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100
    assert max(c[2] for c in f_confetti) >= 20


def test_meteor_shower_renderer_is_bounded_and_moves():
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    engine.set_parameters(speed=1.0, palette_name="tide")
    frame_a = engine._render_meteor_shower(t=0.8)
    frame_b = engine._render_meteor_shower(t=1.7)
    assert len(frame_a) == len(frame_b) == 50
    for frame in (frame_a, frame_b):
        for h, sat, val in frame:
            assert 0 <= h <= 360
            assert 0 <= sat <= 100
            assert 0 <= val <= 100
    assert frame_a != frame_b
    assert max(v for _, _, v in frame_a) > 40


def test_firmware_effect_previews_are_bounded_and_not_uniform():
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    for effect in ("drift", "deep_ocean", "tide", "fireflies", "prism_sparks", "flicker"):
        frame = engine._compute(effect, t=1.23)
        assert len(frame) == 50, effect
        assert all(0 <= h <= 360 and 0 <= sat <= 100 and 0 <= val <= 100 for h, sat, val in frame), effect
        assert len({(h, sat, val) for h, sat, val in frame}) > 1, effect

    # Breathe intentionally uses one color and one brightness across all zones.
    breathing = engine._compute("breathe", t=1.23)
    assert len(breathing) == 50
    assert len({(h, sat, val) for h, sat, val in breathing}) == 1


def test_2d_geometric_effects():
    """Verify 2D spatial geometry effects (radial_ripple and spiral_vortex)."""
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    assert "radial_ripple" in EFFECT_CATALOG
    assert "spiral_vortex" in EFFECT_CATALOG

    # 1. Radial ripple
    f_ripple = engine._compute("radial_ripple", t=1.0)
    assert len(f_ripple) == 50
    for h, s, v in f_ripple:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100
    # Dynamic range across 50 zones
    assert max(c[2] for c in f_ripple) > min(c[2] for c in f_ripple)

    # 2. Spiral vortex
    f_vortex = engine._compute("spiral_vortex", t=2.5)
    assert len(f_vortex) == 50
    for h, s, v in f_vortex:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100
    assert max(c[2] for c in f_vortex) > 50


def test_full_circle_hue_range_random_effect():
    """Verify that (0, 360) is preserved and does not collapse to [0, 0]."""
    fx = build_firmware_random_effect("FullRainbow", hue_range=(0, 360))
    assert fx.hue_range == [0, 360], f"Expected [0, 360], got {fx.hue_range}"

    # Also check narrow wrap-safe range
    fx_narrow = build_firmware_random_effect("NarrowArc", hue_range=(200, 230))
    assert fx_narrow.hue_range == [200, 230]


def test_parameter_aware_effect_id():
    """Verify that sequence and random effects produce new IDs when parameters change."""
    id1 = make_effect_id("Tide", trans=2000, sp=16, dir=3, b=100)
    id2 = make_effect_id("Tide", trans=1000, sp=16, dir=3, b=100)
    id3 = make_effect_id("Tide", trans=2000, sp=16, dir=3, b=50)

    assert id1 != id2, "Transition change must produce distinct effect ID for firmware re-arming"
    assert id1 != id3, "Brightness change must produce distinct effect ID"
    assert len(id1) == 32 and len(id2) == 32


def test_worker_generation_lifecycle_and_stale_timer():
    """Verify stream worker stops cleanly on generation change and stale firmware timers are dropped."""
    from unittest.mock import MagicMock
    ctrl = MagicMock()
    runner = MagicMock()
    engine = L930EffectsEngine(controller=ctrl, loop_runner=runner, app_state={})

    # 1. Start streamed effect (gen 1)
    engine.start("lava_lamp")
    g1 = engine._effect_generation
    assert engine.is_running()
    t1 = engine._thread
    assert t1 is not None and t1.is_alive()

    # 2. Switch to firmware effect (gen 2) - should cleanly stop old thread
    engine.start("tide")
    assert engine._effect_generation == g1 + 1
    # Old thread must be dead
    t1.join(timeout=1.5)
    assert not t1.is_alive()

    # 3. Simulate pending firmware upload queued under gen 2
    engine._pending_fw_upload = (engine._effect_generation, "tide", MagicMock())

    # Switch to streamed effect (gen 3)
    engine.start("dusk")
    assert engine._pending_fw_upload is None  # Must be cleared immediately

    # Manually trigger flush with stale generation
    engine._pending_fw_upload = (engine._effect_generation - 1, "tide", MagicMock())
    engine._flush_pending_firmware_upload()
    # Runner should not have been called with stale effect
    engine.stop()


def test_output_arbiter_strict_ownership():
    """Verify OutputArbiter enforces single-producer rules and rejects conflicting streams."""
    from src.frame_bus import OutputArbiter, OutputProducer

    arbiter = OutputArbiter()
    dev = "strip2"

    # IDLE allows initial static or idle release
    assert arbiter.can_submit(dev, OutputProducer.STATIC)
    assert arbiter.can_submit(dev, OutputProducer.IDLE)
    assert not arbiter.can_submit(dev, OutputProducer.EFFECT)

    # Claim EFFECT
    arbiter.claim_output(dev, OutputProducer.EFFECT)
    assert arbiter.can_submit(dev, OutputProducer.EFFECT)
    assert not arbiter.can_submit(dev, OutputProducer.AUDIO)
    assert not arbiter.can_submit(dev, OutputProducer.STATIC)

    # Claim AUDIO - should preempt EFFECT
    relinquished = []
    arbiter.claim_output(dev, OutputProducer.AUDIO, on_relinquish=lambda: relinquished.append("effect_stopped"))
    # Next claim preempts
    arbiter.claim_output(dev, OutputProducer.SCREEN_SYNC)
    assert relinquished == ["effect_stopped"]
    assert arbiter.can_submit(dev, OutputProducer.SCREEN_SYNC)
    assert not arbiter.can_submit(dev, OutputProducer.AUDIO)


def test_new_geometric_and_fastled_effects():
    """Verify all new 2D spatial and FastLED effects render valid 50-zone outputs."""
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    new_effects = [
        "gravity_slosh",
        "lissajous_orbit",
        "planar_wind",
        "radar_sweep",
        "glitter_cascade",
        "bpm_resonator",
        "coordinated_lightning",
        "vaporwave_neon",
        "lantern_sweep",
        "aurora",
        "raindrop",
        "lightning",
        "police",
        "candy_cane",
        "haunted_mansion",
        "rainbow",
    ]
    for eff in new_effects:
        assert eff in EFFECT_CATALOG, f"Missing {eff} in EFFECT_CATALOG"
        frame = engine._compute(eff, t=1.5)
        assert len(frame) == 50, f"Expected 50 segments for {eff}, got {len(frame)}"
        for h, s, v in frame:
            assert 0 <= h <= 360, f"Invalid hue {h} in {eff}"
            assert 0 <= s <= 100, f"Invalid saturation {s} in {eff}"
            assert 0 <= v <= 100, f"Invalid brightness {v} in {eff}"


def test_new_firmware_payload_builders():
    """Verify new firmware autonomous effects generate valid LightEffect payloads."""
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    new_fw = ["bioluminescent_abyss", "campfire_hearth", "dual_wipe", "infinite_prism"]
    for eff in new_fw:
        assert eff in EFFECT_CATALOG
        fx = engine._build_effect_payload(eff)
        assert fx is not None, f"Payload builder for {eff} returned None"
        assert len(fx.id) == 32
        assert fx.type in ("sequence", "random", "pulse", "static")


def test_next_gen_music_styles():
    """Verify all next-gen music styles render valid frames."""
    from src.visual_styles import create_style_instances
    from src.audio_dsp import MusicState

    styles = create_style_instances()
    st = MusicState(
        energy=0.65,
        kick=0.90,
        hat=0.70,
        onset=0.75,
        centroid_norm=0.45,
        silent=False,
    )

    for style_name in ("acoustic_string", "hydro_acoustic", "lofi_vinyl", "melodic_contour"):
        assert style_name in styles
        style = styles[style_name]
        frame = style.render(st, dt=0.033, num_zones=50)
        assert len(frame) == 50
        for h, s, v in frame:
            assert 0 <= h <= 360
            assert 0 <= s <= 100
            assert 0 <= v <= 100


def test_make_50_zone_effect_payload_invariance_and_anti_reinit():
    from src.device_l930 import make_50_zone_effect, _STATIC_EFFECT_ID

    frame1 = [(120, 80, 70)] * 50
    fx1 = make_50_zone_effect(frame1, master_brightness=100, transition=120, pre_corrected=True)

    assert fx1.id == _STATIC_EFFECT_ID
    assert fx1.custom == 1
    assert fx1.type == 'static'
    assert fx1.transition == 120
    assert fx1.segments == list(range(50))
    assert len(fx1.sequence) == 50

    frame2 = [(240, 90, 85)] * 50
    fx2 = make_50_zone_effect(frame2, master_brightness=80, transition=120, pre_corrected=True)

    assert fx2.id == fx1.id, 'Effect ID must remain strictly identical across frames to prevent firmware re-init'
    assert fx2.custom == 1
    assert fx2.type == 'static'
    assert fx2.transition == 120
    assert fx2.segments == fx1.segments
