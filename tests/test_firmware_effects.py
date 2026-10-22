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
    for effect in (
        "drift", "deep_ocean", "tide", "fireflies", "prism_sparks", "flicker",
        "bioluminescent_abyss", "campfire_hearth", "dual_wipe", "infinite_prism",
    ):
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
    fx2 = make_50_zone_effect(
        frame2, master_brightness=80, transition=0, pre_corrected=True, init_states=fx1.sequence
    )

    assert fx2.id == fx1.id, 'Effect ID must remain strictly identical across frames to prevent firmware re-init'
    assert fx2.custom == 1
    assert fx2.type == 'static'
    assert fx2.transition == 0
    assert fx2.segments == fx1.segments
    assert fx2.init_states == fx1.sequence
    assert fx2.init_states is not fx1.sequence

def test_l930_explicit_zero_transition_is_not_replaced_by_music_fade():
    from src.device_l930 import L930Controller

    controller = L930Controller(
        "127.0.0.1", "test@example.invalid", "not-a-real-password",
        calibration={"transition_ms": 0, "music_transition_ms": 120},
    )
    assert controller.default_transition_ms == 0
    assert controller.music_transition_ms == 120


def test_original_effects_use_procedural_playback_not_firmware_colour_sequences():
    from src.effects_l930 import EFFECT_CATALOG, CREATIVE_EFFECTS, CUSTOM_EFFECTS

    expected = {"oil_slick", "silk_ribbons", "nebula_bloom", "holographic_moire", "ember_drift"}
    spatial = {"spiral_vortex", "gravity_slosh", "lissajous_orbit", "planar_wind", "vaporwave_neon"}
    assert set(CREATIVE_EFFECTS) == expected
    assert expected | spatial <= set(CUSTOM_EFFECTS)
    for name in expected | spatial:
        assert EFFECT_CATALOG[name]["kind"] == "streamed_slow"


def test_effect_switch_clears_old_frames_and_bypasses_slider_throttle():
    """Explicit selections replace stale output immediately, even inside the throttle window."""
    import asyncio

    events = []

    class FakeController:
        def clear_frames(self):
            events.append("clear")

        async def set_native_effect(self, effect, priority=0):
            events.append(("set", effect.name))

    class FakeLoopRunner:
        def run(self, awaitable):
            return asyncio.run(awaitable)

    engine = L930EffectsEngine(
        controller=FakeController(),
        loop_runner=FakeLoopRunner(),
        app_state={},
    )

    assert engine.start("drift") is True
    assert events[0] == "clear"
    assert events[1][0] == "set"

    # A second explicit choice within two seconds must deploy now rather than
    # leave the previous firmware animation running while a timer waits.
    before = len(events)
    assert engine.start("fireflies") is True
    assert events[before] == "clear"
    assert events[before + 1][0] == "set"
    assert engine._pending_fw_timer is None


def test_effect_start_rejects_unknown_name_without_claiming_success():
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    assert engine.start("not-a-real-l930-effect") is False
    assert "Unknown L930 effect" in engine._last_error


def test_native_effect_aliases_resolve_to_catalog_entries():
    import asyncio

    class FakeController:
        async def set_native_effect(self, effect, priority=0):
            return None

    class FakeLoopRunner:
        def run(self, awaitable):
            return asyncio.run(awaitable)

    engine = L930EffectsEngine(FakeController(), FakeLoopRunner(), app_state={})
    assert engine.start("aurora_native") is True
    assert engine._active_effect_name == "aurora"


def test_firmware_deployment_failure_is_returned_to_caller():
    import asyncio

    class FakeController:
        async def set_native_effect(self, effect, priority=0):
            return False

    class FakeLoopRunner:
        def run(self, awaitable):
            return asyncio.run(awaitable)

    engine = L930EffectsEngine(FakeController(), FakeLoopRunner(), app_state={})
    assert engine.start("drift") is False
    assert "Controller rejected firmware effect 'drift'" in engine._last_error
    assert engine._active_effect_name is None
    assert engine._active_kind is None


def test_effect_catalog_curation_structure():
    """Keep the user-facing shelf limited to five original designs and five spatial experiments."""
    from src.effects_l930 import (
        CORE_EFFECTS, ADVANCED_EFFECTS, SEASONAL_EFFECTS, NOVELTY_EFFECTS,
        OCCASIONAL_EFFECTS, CREATIVE_EFFECTS, ACTIVE_EFFECTS, EFFECT_CATALOG
    )

    assert len(EFFECT_CATALOG) == 53, f"Expected 53 internal definitions, got {len(EFFECT_CATALOG)}"
    assert CORE_EFFECTS == [], "Stock/core effects should not be exposed in the curated UI"
    assert len(ADVANCED_EFFECTS) == 5
    assert SEASONAL_EFFECTS == []
    assert NOVELTY_EFFECTS == []
    assert len(CREATIVE_EFFECTS) == 5
    assert OCCASIONAL_EFFECTS == []
    assert len(ACTIVE_EFFECTS) == 10

    expected_creative = {
        "oil_slick", "silk_ribbons", "nebula_bloom", "holographic_moire", "ember_drift"
    }
    assert set(CREATIVE_EFFECTS) == expected_creative

    expected_advanced = {
        "spiral_vortex", "gravity_slosh", "lissajous_orbit", "planar_wind", "vaporwave_neon"
    }
    assert set(ADVANCED_EFFECTS) == expected_advanced
    assert "warning" in EFFECT_CATALOG["police"]
    assert "Rapid flashing" in EFFECT_CATALOG["police"]["warning"]

    aliases = {k: v for k, v in EFFECT_CATALOG.items() if v.get("category") == "alias"}
    assert len(aliases) == 10
    for alias_name, meta in aliases.items():
        assert meta.get("deprecated") is True
        target = meta.get("alias_of")
        assert target in EFFECT_CATALOG, f"Alias {alias_name} points to invalid target {target}"
        assert EFFECT_CATALOG[target].get("category") in ("core", "advanced"), f"Alias target {target} should be core or advanced"

    assert EFFECT_CATALOG["bpm_resonator"]["category"] == "reactive"


def test_transparent_alias_resolution_in_engine():
    """Verify engine resolves aliases and automatically injects default parameter presets."""
    import asyncio
    from src.effects_l930 import L930EffectsEngine

    class FakeController:
        async def set_native_effect(self, effect, priority=0):
            return None

    class FakeLoopRunner:
        def run(self, awaitable):
            return asyncio.run(awaitable)

    engine = L930EffectsEngine(FakeController(), FakeLoopRunner(), app_state={})

    # 1. dusk -> golden_hour with dusk palette
    assert engine.start("dusk") is True
    assert engine._active_effect_name == "golden_hour"
    assert engine._palette_name == "dusk"
    assert engine._active_kind == "streamed_slow"
    engine.stop()

    # 2. ocean -> tide
    assert engine.start("ocean") is True
    assert engine._active_effect_name == "tide"
    assert engine._active_kind == "firmware"
    engine.stop()

    # 3. confetti -> prism_sparks with particle_density 2.0
    assert engine.start("confetti") is True
    assert engine._active_effect_name == "prism_sparks"
    assert engine._particle_density == 2.0
    assert engine._active_kind == "firmware"
    engine.stop()

    # 4. hearth -> campfire_hearth with fire palette
    assert engine.start("hearth") is True
    assert engine._active_effect_name == "campfire_hearth"
    assert engine._palette_name == "fire"
    engine.stop()

    # 5. sonar_sweep -> radar_sweep with tail_length 2.0
    assert engine.start("sonar_sweep") is True
    assert engine._active_effect_name == "radar_sweep"
    assert engine._tail_length == 2.0
    engine.stop()

    # 6. coordinated_lightning -> lightning with flash_strength 2.0
    assert engine.start("coordinated_lightning") is True
    assert engine._active_effect_name == "lightning"
    assert engine._flash_strength == 2.0
    engine.stop()

    # 7. infinite_prism -> rainbow with speed 1.5
    assert engine.start("infinite_prism") is True
    assert engine._active_effect_name == "rainbow"
    assert engine._speed == 1.5
    engine.stop()


def test_hub_full_state_includes_curated_categories(monkeypatch):
    """Verify hub full state exposes curated lists."""
    from src.hub import LightHub
    from src.event_loop import BackgroundLoop

    monkeypatch.setenv("TAPO_EMAIL", "test@domain.com")
    monkeypatch.setenv("TAPO_PASSWORD", "secret123")
    loop_runner = BackgroundLoop()
    loop_runner.start()
    try:
        hub = LightHub({}, loop_runner)
        st = hub.get_full_state()
        assert "core_effects" in st
        assert "advanced_effects" in st
        assert "seasonal_effects" in st
        assert "novelty_effects" in st
        assert "occasional_effects" in st
        assert "creative_effects" in st
        assert "active_effects" in st
        assert len(st["core_effects"]) == 0
        assert len(st["advanced_effects"]) == 5
        assert len(st["seasonal_effects"]) == 0
        assert len(st["novelty_effects"]) == 0
        assert len(st["occasional_effects"]) == 0
        assert len(st["creative_effects"]) == 5
        assert len(st["active_effects"]) == 10
        # Ensure bpm_resonator is exposed in visualizer styles
        assert any(s["id"] == "bpm_resonator" for s in st.get("visualizer_styles", []))
    finally:
        loop_runner.stop()


def test_merged_effect_behavior_preservation():
    """Verify that retained effects absorbed full behaviors from merged/retired effects."""
    from src.effects_l930 import L930EffectsEngine

    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})

    # 1. dusk absorbed into golden_hour: dusk palette produces twilight progression
    engine.set_parameters(palette_name="dusk")
    f_dusk = engine._render_standing_wave_golden_hour(t=1.0)
    assert len(f_dusk) == 50
    assert engine._compute("dusk", t=1.0) == f_dusk

    # 2. ocean absorbed into tide: returns Pacifica multi-wave rendering
    f_ocean = engine._compute("ocean", t=1.5)
    f_tide = engine._render_tide(t=1.5)
    assert f_ocean == f_tide

    # 3. bioluminescent_abyss absorbed into deep_ocean: returns deep ocean with cyan sparks
    f_bio = engine._compute("bioluminescent_abyss", t=1.2)
    f_deep = engine._render_deep_ocean(t=1.2)
    assert f_bio == f_deep
    # Cyan or teal highlights present
    assert any(160 <= h <= 195 for h, s, v in f_deep)

    # 4. hearth absorbed into campfire_hearth: returns Fire2012 heat diffusion
    f_hearth = engine._compute("hearth", t=1.0)
    f_camp = engine._compute("campfire_hearth", t=1.0)
    assert len(f_camp) == 50
    assert max(c[2] for c in f_camp) >= 20

    # 5. glitter_cascade absorbed into starfield: particle_density & flash_strength scaling
    engine.set_parameters(particle_density=2.5, flash_strength=2.0)
    f_glitter = engine._render_autonomous_starfield(t=2.0)
    assert any(v == 100 for _, _, v in f_glitter), "Glitter pops should hit 100 brightness"
    assert engine._compute("glitter_cascade", t=2.0) == engine._render_glitter_cascade(t=2.0)

    # 6. confetti absorbed into prism_sparks: particle_density > 1.5 triggers burst mode
    engine.set_parameters(particle_density=2.0)
    f_burst = engine._render_prism_sparks(t=2.5)
    assert len(f_burst) == 50
    assert max(c[2] for c in f_burst) >= 20
    assert engine._compute("confetti", t=2.5) == engine._render_confetti_burst(t=2.5)

    # 7. dual_wipe absorbed into cyber_chase: bi-directional dual-end collision
    f_dual = engine._compute("dual_wipe", t=1.5)
    f_cyber = engine._render_collider_chase(t=1.5)
    assert f_dual == f_cyber

    # 8. sonar_sweep absorbed into radar_sweep: tail_length & palette scaling
    engine.set_parameters(tail_length=2.0, palette_name="forest")
    f_radar = engine._render_radar_sweep(t=1.0)
    assert len(f_radar) == 50
    assert engine._compute("sonar_sweep", t=1.0) == engine._render_multi_pod_sonar(t=1.0)

    # 9. coordinated_lightning absorbed into lightning: flash_strength & thunder rumble
    engine.set_parameters(flash_strength=2.0)
    # Rumble window (4.5s into 7.0s cycle)
    f_rumble = engine._render_lightning(t=4.5)
    assert any(h == 28 for h, s, v in f_rumble), "Thunder rumble warm amber should be present"
    assert engine._compute("coordinated_lightning", t=1.2) == engine._render_coordinated_lightning(t=1.2)

    # 10. infinite_prism absorbed into rainbow: seamless circulating spectral cycle
    f_prism = engine._compute("infinite_prism", t=1.0)
    f_rainbow = engine._render_rainbow(t=1.0)
    assert f_prism == f_rainbow


def test_bpm_resonator_music_reactive_style_synchronization():
    """Verify BpmResonatorStyle timing is driven by musical tempo, beat phase, bar downbeats, and audio transients."""
    from src.visual_styles import create_style_instances, BpmResonatorStyle
    from src.audio_dsp import MusicState

    styles = create_style_instances()
    assert "bpm_resonator" in styles
    style = styles["bpm_resonator"]
    assert isinstance(style, BpmResonatorStyle)

    # 1. Base tempo response at 120 BPM on Beat 0, phase 0.0
    st_beat0 = MusicState(bpm=120.0, bpm_confidence=0.8, beat_phase=0.0, bar_pos=0, energy=0.7, kick=0.9)
    frame0 = style.render(st_beat0, dt=0.033, num_zones=50)
    assert len(frame0) == 50
    for h, s, v in frame0:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100

    # Downbeat accent on bar_pos 0 should make frame luminous
    assert max(v for _, _, v in frame0) >= 60

    # 2. Phase progression at half-beat (phase 0.5) should change standing wave patterns
    st_beat_half = MusicState(bpm=120.0, bpm_confidence=0.8, beat_phase=0.5, bar_pos=0, energy=0.7, kick=0.1)
    frame_half = style.render(st_beat_half, dt=0.033, num_zones=50)
    assert frame0 != frame_half

    # 3. Bar position shift (bar_pos 2 vs 0) modulates the downbeat envelope
    st_bar2 = MusicState(bpm=120.0, bpm_confidence=0.8, beat_phase=0.0, bar_pos=2, energy=0.7, kick=0.1)
    frame_bar2 = style.render(st_bar2, dt=0.033, num_zones=50)
    assert frame0 != frame_bar2


def test_comprehensive_native_aliases_resolution():
    from src.effects_l930 import NATIVE_ALIASES, resolve_effect_alias, EFFECT_CATALOG
    for alias, target in NATIVE_ALIASES.items():
        resolved = resolve_effect_alias(alias)
        assert resolved in EFFECT_CATALOG, f"Alias {alias} resolved to {resolved} which is not in EFFECT_CATALOG"
    assert resolve_effect_alias("rainbow_native") == "rainbow"
    assert resolve_effect_alias("aurora_native") == "aurora"
    assert resolve_effect_alias("ocean_native") == "ocean"
    assert resolve_effect_alias("candy_cane_native") == "candy_cane"
    assert resolve_effect_alias("haunted_mansion_native") == "haunted_mansion"
    assert resolve_effect_alias("candle_native") == "candle_native"


def test_effect_status_lifecycle_and_failure_exposure():
    import asyncio

    state = {}
    class FakeRejectController:
        async def set_native_effect(self, effect, priority=0):
            return False

    class FakeAcceptController:
        def __init__(self):
            self.frames = []
        async def set_native_effect(self, effect, priority=0):
            return True
        def submit_frame(self, frame):
            self.frames.append(frame)
        def clear_frames(self):
            pass

    class FakeLoopRunner:
        def run(self, awaitable):
            return asyncio.run(awaitable)

    # 1. Unknown effect -> fails immediately
    engine = L930EffectsEngine(FakeAcceptController(), FakeLoopRunner(), app_state=state)
    assert engine.start("completely_unknown_xyz") is False
    assert state["effect_status"] == "failed"
    assert "Unknown L930 effect" in state["last_error"]

    # 2. Firmware rejection -> sets failed state
    reject_engine = L930EffectsEngine(FakeRejectController(), FakeLoopRunner(), app_state=state)
    assert reject_engine.start("drift") is False
    assert state["effect_status"] == "failed"
    assert "rejected firmware effect" in state["last_error"]

    # 3. Successful firmware deployment -> sets accepted state
    accept_engine = L930EffectsEngine(FakeAcceptController(), FakeLoopRunner(), app_state=state)
    assert accept_engine.start("drift") is True
    assert state["effect_status"] == "accepted"
    assert state["last_error"] is None


def test_streamed_effects_pacing_and_adaptive_transitions():
    import threading
    import time

    class MockController:
        def __init__(self, interval=0.5):
            self.submitted_frames = []
            self.current_interval = interval
        def submit_frame(self, frame):
            self.submitted_frames.append(frame)
        def clear_frames(self):
            pass

    # Test standard <= 2 FPS pacing (interval >= 0.50, transition >= 500)
    ctrl = MockController(interval=0.5)
    state = {}
    engine = L930EffectsEngine(ctrl, None, app_state=state)
    stop_event = threading.Event()

    engine._active_effect_name = "lava_lamp"
    engine._active_kind = "streamed_slow"
    engine._effect_generation = 1
    engine._start_time = time.monotonic()

    t = threading.Thread(target=engine._stream_run, args=(stop_event, 1))
    t.start()
    time.sleep(0.1)
    stop_event.set()
    t.join(timeout=1.0)

    assert len(ctrl.submitted_frames) >= 1
    frame = ctrl.submitted_frames[0]
    assert frame["transition"] >= 500, f"Expected transition >= 500ms, got {frame['transition']}"
    assert state.get("effect_status") == "accepted"

    # Test adaptive transition lengthening under network fallback (interval = 1.0 -> transition >= 1000)
    ctrl_fallback = MockController(interval=1.0)
    engine_fallback = L930EffectsEngine(ctrl_fallback, None, app_state={})
    stop_event_fb = threading.Event()
    engine_fallback._active_effect_name = "golden_hour"
    engine_fallback._active_kind = "streamed_slow"
    engine_fallback._effect_generation = 2
    engine_fallback._start_time = time.monotonic()

    t_fb = threading.Thread(target=engine_fallback._stream_run, args=(stop_event_fb, 2))
    t_fb.start()
    time.sleep(0.1)
    stop_event_fb.set()
    t_fb.join(timeout=1.0)

    assert len(ctrl_fallback.submitted_frames) >= 1
    frame_fb = ctrl_fallback.submitted_frames[0]
    assert frame_fb["transition"] >= 1000, f"Expected transition >= 1000ms under AIMD fallback, got {frame_fb['transition']}"


def test_stale_stream_frames_discarded_on_generation_bump():
    import threading
    import time

    class MockController:
        def __init__(self):
            self.submitted = []
        def submit_frame(self, frame):
            self.submitted.append(frame)
        def clear_frames(self):
            pass

    ctrl = MockController()
    engine = L930EffectsEngine(ctrl, None, app_state={})
    stop_event = threading.Event()
    engine._active_effect_name = "cyber_chase"
    engine._active_kind = "streamed_slow"
    engine._effect_generation = 5

    # If generation changes immediately, worker must exit without submitting
    engine._effect_generation = 6
    engine._stream_run(stop_event, generation=5)
    assert len(ctrl.submitted) == 0


def test_advertised_controls_consumed_by_firmware_and_renderers():
    """Verify that all advertised controls (particle_density, tail_length, wave_width, flash_strength) actually alter behavior."""
    engine = L930EffectsEngine(None, None, {})

    # 1. particle_density: embers, fireflies, prism_sparks, starfield, raindrop
    engine.set_parameters(particle_density=0.5)
    fw_embers_low = engine._build_effect_payload("embers")
    rd_low = engine._render_raindrop(1.0)

    engine.set_parameters(particle_density=2.5)
    fw_embers_high = engine._build_effect_payload("embers")
    rd_high = engine._render_raindrop(1.0)

    assert fw_embers_low.id != fw_embers_high.id, "particle_density must change firmware effect ID"
    assert fw_embers_low.fadeoff != fw_embers_high.fadeoff, "particle_density must change firmware fadeoff"
    assert rd_low != rd_high, "particle_density must change raindrop render output"

    # 2. tail_length: lantern_sweep, sinelon, comet
    engine.set_parameters(tail_length=0.5)
    fw_lantern_short = engine._build_effect_payload("lantern_sweep")
    ls_short = engine._render_lantern_sweep(1.0)

    engine.set_parameters(tail_length=2.5)
    fw_lantern_long = engine._build_effect_payload("lantern_sweep")
    ls_long = engine._render_lantern_sweep(1.0)

    assert fw_lantern_short.id != fw_lantern_long.id, "tail_length must change lantern_sweep effect ID"
    assert fw_lantern_short.spread != fw_lantern_long.spread, "tail_length must change lantern_sweep spread"
    assert ls_short != ls_long, "tail_length must change lantern_sweep render output"

    # 3. wave_width: aurora, gravity_slosh, planar_wind, bpm_resonator
    engine.set_parameters(wave_width=0.5)
    aurora_narrow = engine._render_aurora(1.0)
    wind_narrow = engine._render_planar_wind(1.0)

    engine.set_parameters(wave_width=2.5)
    aurora_wide = engine._render_aurora(1.0)
    wind_wide = engine._render_planar_wind(1.0)

    assert aurora_narrow != aurora_wide, "wave_width must change aurora render output"
    assert wind_narrow != wind_wide, "wave_width must change planar_wind render output"

    # 4. flash_strength: cyber_chase, lightning, neon_heartbeat
    engine.set_parameters(flash_strength=0.5)
    hb_soft = engine._render_anatomical_heartbeat(0.12)
    fw_chase_soft = engine._build_effect_payload("cyber_chase")

    engine.set_parameters(flash_strength=2.5)
    hb_hard = engine._render_anatomical_heartbeat(0.12)
    fw_chase_hard = engine._build_effect_payload("cyber_chase")

    assert hb_soft != hb_hard, "flash_strength must change heartbeat render output"
    assert fw_chase_soft.id != fw_chase_hard.id, "flash_strength must change cyber_chase effect ID"


def test_all_catalog_effects_and_aliases_have_distinct_non_flat_previews():
    """Verify that every single catalog effect and native alias produces a non-flat, realistic preview."""
    from src.effects_l930 import EFFECT_CATALOG, NATIVE_ALIASES
    engine = L930EffectsEngine(None, None, {})
    flat_fallback = [[30, 80, 60]] * 50

    all_names = list(EFFECT_CATALOG.keys()) + list(NATIVE_ALIASES.keys())
    for name in all_names:
        frame = engine._compute(name, t=1.2)
        assert len(frame) == 50, f"Preview for {name} does not have 50 zones"
        assert frame != flat_fallback, f"Preview for {name} fell back to flat default frame"
        # Verify valid HSV values
        for h, s, v in frame:
            assert 0 <= h <= 360, f"Invalid hue in {name}: {h}"
            assert 0 <= s <= 100, f"Invalid sat in {name}: {s}"
            assert 0 <= v <= 100, f"Invalid val in {name}: {v}"

    # Specific check for previously missing preview branches
    bio_frame = engine._compute("bioluminescent_abyss", t=1.0)
    hearth_frame = engine._compute("campfire_hearth", t=1.0)
    dual_frame = engine._compute("dual_wipe", t=1.0)
    prism_frame = engine._compute("infinite_prism", t=1.0)

    assert bio_frame != flat_fallback
    assert hearth_frame != flat_fallback
    assert dual_frame != flat_fallback
    assert prism_frame != flat_fallback


@pytest.mark.asyncio
async def test_l930_native_effect_rechecks_output_token_after_connection_wait():
    """A firmware command that loses ownership while connecting must never reach the device."""
    import asyncio
    from src.device_l930 import L930Controller
    from src.frame_bus import OutputArbiter, OutputProducer

    arbiter = OutputArbiter()
    arbiter.claim_output("strip", OutputProducer.EFFECT)
    _, generation, producer_id = arbiter.get_token("strip")
    sent = []

    class FakeDevice:
        async def set_light_effect(self, effect):
            sent.append(effect)
            return True

    ctrl = L930Controller.__new__(L930Controller)
    ctrl._lock = asyncio.Lock()
    ctrl.frame_sender = None
    ctrl._device = FakeDevice()
    ctrl._is_on = True
    ctrl._last_successful_response = 0.0
    ctrl._output_token_authorizer = lambda producer, gen, pid: arbiter.is_token_current(
        "strip", producer, gen, pid
    )

    async def handoff_during_connect():
        arbiter.claim_output("strip", OutputProducer.AUDIO, renew=True)

    ctrl._ensure_connected = handoff_during_connect
    result = await ctrl.set_native_effect(
        object(), priority=0,
        output_token=(OutputProducer.EFFECT, generation, producer_id),
    )

    assert result is False
    assert sent == []



def _hue_delta(a, b):
    return abs((int(a) - int(b) + 180) % 360 - 180)


def _frame_rgb(frame):
    from src.pipeline import tapo_hsv_to_rgb
    return [tapo_hsv_to_rgb(*zone) for zone in frame]


def _max_rgb_step(left, right):
    return max(
        max(abs(a[c] - b[c]) for c in range(3))
        for a, b in zip(left, right)
    )


def test_aurora_blends_curtain_colors_without_winner_takes_all():
    engine = L930EffectsEngine(None, None, {})
    first = engine._render_aurora(1.23)
    next_frame = engine._render_aurora(1.25)

    assert len(first) == 50
    assert len({h for h, _, _ in first}) >= 10, "Aurora should blend intermediate hues, not only three fixed hues"
    assert _max_rgb_step(_frame_rgb(first), _frame_rgb(next_frame)) < 0.12
    assert all(10 <= v <= 90 for _, _, v in first)


def test_raindrops_have_long_soft_wakes_and_respond_to_cadence():
    from types import SimpleNamespace

    engine = L930EffectsEngine(None, None, {})
    engine._ctrl = SimpleNamespace(
        current_interval=0.0,
        frame_sender=SimpleNamespace(max_updates_per_s=5.0, _aimd_rate_cap=1.0),
    )
    slow_frame = engine._render_raindrop(1.0)
    later_frame = engine._render_raindrop(1.4)

    assert slow_frame != later_frame
    assert max(v for _, _, v in slow_frame) <= 82
    active_zones = [i for i, (_, _, v) in enumerate(slow_frame) if v >= 20]
    assert 2 <= len(active_zones) <= 25
    assert engine._effective_render_interval() >= 1.0


def test_police_is_a_slow_siren_not_a_strobe_and_keeps_warning():
    from types import SimpleNamespace
    from src.effects_l930 import EFFECT_CATALOG

    engine = L930EffectsEngine(None, None, {})
    engine._ctrl = SimpleNamespace(
        current_interval=0.0,
        frame_sender=SimpleNamespace(max_updates_per_s=5.0, _aimd_rate_cap=1.0),
    )

    red_peak = engine._render_police(1.0)
    transition = engine._render_police(2.0)
    blue_peak = engine._render_police(3.0)

    assert all(h == 0 for h, _, _ in red_peak[:25])
    assert all(h == 240 for h, _, _ in red_peak[25:])
    assert all(h == 0 for h, _, _ in blue_peak[:25])
    assert all(h == 240 for h, _, _ in blue_peak[25:])
    assert min(v for _, _, v in red_peak[:25]) > 70
    assert min(v for _, _, v in blue_peak[25:]) > 70
    assert max(v for _, _, v in transition) <= 10
    assert max(v for _, _, v in red_peak + blue_peak) < 100
    assert "warning" in EFFECT_CATALOG["police"]
    assert "strobe warning" in EFFECT_CATALOG["police"]["warning"].lower()


def test_haunted_mansion_uses_localized_smooth_glows_not_full_strip_flashes():
    engine = L930EffectsEngine(None, None, {})
    # Adjacent 250 ms samples are tighter than the physical send period and
    # catch abrupt glow attacks without incorrectly treating long elapsed-time
    # changes as if they were consecutive hardware frames.
    samples = [
        engine._render_haunted_mansion(t)
        for t in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75)
    ]

    for frame in samples:
        assert len(frame) == 50
        assert max(v for _, _, v in frame) <= 64, "Haunted Mansion must not produce the old V95 full-strip flash"
        assert sum(v >= 50 for _, _, v in frame) < 20, "glow should remain spatially localized"
        assert sum(v <= 8 for _, _, v in frame) >= 10, "most zones should retain a near-black base"

    for left, right in zip(samples, samples[1:]):
        assert _max_rgb_step(_frame_rgb(left), _frame_rgb(right)) < 0.12


def test_candy_cane_uses_soft_band_boundaries_and_moves():
    engine = L930EffectsEngine(None, None, {})
    first = engine._render_candy_cane(0.37)
    later = engine._render_candy_cane(0.92)
    rgb = _frame_rgb(first)

    assert first != later
    # The strip is a line, not a ring: compare only physical adjacent zones.
    assert _max_rgb_step(rgb[:-1], rgb[1:]) < 0.50
    assert all(0 <= h <= 360 and 0 <= sat <= 100 and 0 <= val <= 100 for h, sat, val in first)
    assert max(sat for _, sat, _ in first) < 100, "warm-white bands should not be encoded as fully saturated primaries"


def test_cyber_chase_reversal_is_smoothed_at_measured_cadence():
    from types import SimpleNamespace

    engine = L930EffectsEngine(None, None, {})
    engine._ctrl = SimpleNamespace(
        current_interval=0.0,
        frame_sender=SimpleNamespace(max_updates_per_s=5.0, _aimd_rate_cap=2.0),
    )
    at_reversal = engine._render_collider_chase(0.001)
    just_after = engine._render_collider_chase(0.02)

    assert len(at_reversal) == 50
    assert at_reversal != just_after
    assert _max_rgb_step(_frame_rgb(at_reversal), _frame_rgb(just_after)) < 0.12
    assert engine._effective_render_interval() >= 0.5


def test_rainbow_spatial_and_temporal_hue_cycles_remain_continuous():
    engine = L930EffectsEngine(None, None, {})
    first = engine._render_rainbow(0.0)
    later = engine._render_rainbow(0.5)

    for frame in (first, later):
        for i in range(50):
            assert _hue_delta(frame[i][0], frame[(i + 1) % 50][0]) <= 9
    temporal_deltas = [_hue_delta(a[0], b[0]) for a, b in zip(first, later)]
    assert max(temporal_deltas) - min(temporal_deltas) <= 1
    assert later != first


def test_cadence_helper_respects_aimd_without_changing_sender_rate():
    from types import SimpleNamespace

    sender = SimpleNamespace(max_updates_per_s=5.0, _aimd_rate_cap=1.0)
    controller = SimpleNamespace(current_interval=0.75, frame_sender=sender)
    engine = L930EffectsEngine(controller, None, {})
    before = (sender.max_updates_per_s, sender._aimd_rate_cap)

    interval = engine._effective_render_interval()

    assert interval >= 1.0, "renderer should respect 1 Hz device-protection fallback"
    assert (sender.max_updates_per_s, sender._aimd_rate_cap) == before, (
        "cadence-aware rendering must not raise or reset the sender rate cap"
    )
