import math
import pytest
from unittest.mock import MagicMock
from src.effects_l930 import (
    EFFECT_CATALOG,
    L930EffectsEngine,
    resolve_effect_alias,
    PALETTES,
)
from src.audio_dsp import MusicState, Section
from src.visual_styles import ReactiveAuroraStyle


def test_gate_loading_and_alias_resolution():
    """
    Release Gate 1 - Loading:
    - Native and merged aliases resolve to valid catalog entries.
    - Repeated effect changes correctly transition through status states.
    - Deployments track requested -> sent -> accepted or failed.
    """
    app_state = {}
    mock_ctrl = MagicMock()
    mock_ctrl.set_native_effect.return_value = True
    mock_ctrl.clear_frames.return_value = None
    mock_runner = MagicMock()
    mock_runner.run.side_effect = lambda coro: MagicMock(result=lambda timeout: True)

    engine = L930EffectsEngine(controller=mock_ctrl, loop_runner=mock_runner, app_state=app_state)

    # 1. Alias and merged effect resolution
    assert resolve_effect_alias("ocean_native") == "ocean"
    assert resolve_effect_alias("aurora_native") == "aurora"
    assert resolve_effect_alias("rainbow_native") == "rainbow"
    assert EFFECT_CATALOG["dusk"]["alias_of"] == "golden_hour"
    assert EFFECT_CATALOG["ocean"]["alias_of"] == "tide"
    assert EFFECT_CATALOG["bioluminescent_abyss"]["alias_of"] == "deep_ocean"
    assert EFFECT_CATALOG["hearth"]["alias_of"] == "campfire_hearth"
    assert EFFECT_CATALOG["glitter_cascade"]["alias_of"] == "starfield"
    assert EFFECT_CATALOG["confetti"]["alias_of"] == "prism_sparks"
    assert EFFECT_CATALOG["dual_wipe"]["alias_of"] == "cyber_chase"
    assert EFFECT_CATALOG["sonar_sweep"]["alias_of"] == "radar_sweep"
    assert EFFECT_CATALOG["coordinated_lightning"]["alias_of"] == "lightning"
    assert EFFECT_CATALOG["infinite_prism"]["alias_of"] == "rainbow"

    # 2. Unknown effect fails cleanly without silent failure
    ok = engine.start("completely_unknown_effect_xyz")
    assert not ok
    assert app_state.get("effect_status") == "failed"
    assert "Unknown L930 effect" in app_state.get("last_error", "")

    # 3. Successful firmware start marks accepted
    ok = engine.start("starfield")
    assert ok
    assert app_state.get("effect_status") == "accepted"
    assert app_state.get("last_error") is None

    # 4. Clean shutdown when switching
    prev_gen = engine._effect_generation
    ok = engine.start("golden_hour")
    assert ok
    assert engine._effect_generation > prev_gen
    engine.stop()
    assert not engine.is_running()


def test_gate_visual_identity_no_flat_fallbacks():
    """
    Release Gate 3 - Visual Identity:
    Every retained effect must have a distinctive motion pattern and palette.
    No flat fallback previews masquerading as real animations.
    """
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})
    
    for eff_id in EFFECT_CATALOG:
        # Evaluate multiple time steps across active cycle
        frames = [engine._compute(eff_id, t=t_step) for t_step in [0.2, 0.85, 1.4, 3.45, 5.0]]
        
        # Verify 50 physical zones per frame
        for f in frames:
            assert len(f) == 50, f"Effect {eff_id} did not yield 50 zones"
            for h, s, v in f:
                assert 0 <= h <= 360
                assert 0 <= s <= 100
                assert 0 <= v <= 100

        # Verify not completely frozen: at least one zone changes over time
        has_motion = any(frames[0] != f for f in frames[1:])
        assert has_motion, f"Effect {eff_id} has no motion over time"


def test_gate_controls_responsiveness():
    """
    Release Gate 4 - Controls:
    Every advertised control must demonstrably affect the corresponding effect.
    """
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})

    for eff_id, meta in sorted(EFFECT_CATALOG.items()):
        controls = meta.get("supported_controls", [])

        # 1. Speed control
        if "speed" in controls:
            engine.set_parameters(speed=0.2)
            f_slow = [engine._compute(eff_id, t=t_step) for t_step in [0.2, 0.6, 1.2, 2.0]]
            engine.set_parameters(speed=2.5)
            f_fast = [engine._compute(eff_id, t=t_step) for t_step in [0.2, 0.6, 1.2, 2.0]]
            assert f_slow != f_fast, f"Speed control has no effect on {eff_id}"

        # 2. Palette control
        if "palette" in controls:
            engine.set_parameters(palette_name="sunset")
            f_sunset = engine._compute(eff_id, t=1.0)
            engine.set_parameters(palette_name="forest")
            f_forest = engine._compute(eff_id, t=1.0)
            assert f_sunset != f_forest, f"Palette control has no effect on {eff_id}"

        # 3. Particle density control
        if "particle_density" in controls:
            engine.set_parameters(particle_density=0.3)
            f_low_dens = engine._compute(eff_id, t=1.0)
            engine.set_parameters(particle_density=2.5)
            f_high_dens = engine._compute(eff_id, t=1.0)
            assert f_low_dens != f_high_dens, f"Particle density has no effect on {eff_id}"

        # 4. Tail length control
        if "tail_length" in controls:
            engine.set_parameters(tail_length=0.3)
            f_short = engine._compute(eff_id, t=1.0)
            engine.set_parameters(tail_length=2.5)
            f_long = engine._compute(eff_id, t=1.0)
            assert f_short != f_long, f"Tail length has no effect on {eff_id}"

        # 5. Wave width control
        if "wave_width" in controls:
            engine.set_parameters(wave_width=0.3)
            f_narrow = engine._compute(eff_id, t=1.0)
            engine.set_parameters(wave_width=2.5)
            f_wide = engine._compute(eff_id, t=1.0)
            assert f_narrow != f_wide, f"Wave width has no effect on {eff_id}"

        # 6. Brightness control
        if "brightness" in controls:
            engine.set_parameters(brightness=20)
            f_dim = engine._compute(eff_id, t=1.0, apply_brightness=True)
            engine.set_parameters(brightness=100)
            f_bright = engine._compute(eff_id, t=1.0, apply_brightness=True)
            assert f_dim != f_bright, f"Brightness control has no effect on {eff_id}"
            assert max(v for _, _, v in f_dim) < max(v for _, _, v in f_bright), f"Brightness does not scale values for {eff_id}"
            if meta.get("kind") == "firmware":
                engine.set_parameters(brightness=35)
                fx = engine._build_effect_payload(eff_id)
                assert fx.brightness == 35, f"Firmware payload does not reflect brightness for {eff_id}"

        # 7. Flash strength control
        if "flash_strength" in controls:
            engine.set_parameters(flash_strength=0.2)
            f_low = [engine._compute(eff_id, t=step / 10.0) for step in range(70)]
            engine.set_parameters(flash_strength=2.5)
            f_high = [engine._compute(eff_id, t=step / 10.0) for step in range(70)]
            assert f_low != f_high, f"Flash strength control has no effect on {eff_id}"


def test_gate_effects_are_mutually_distinctive():
    """
    Release Gate 3 - Mutual Visual Distinctiveness:
    Every retained effect must produce a unique visual trajectory.
    Compare every pair of distinct (non-alias) catalog effects to ensure
    no two effects produce identical animations or share a flat fallback.
    """
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})

    # Collect all primary non-alias effects
    primary_effects = [
        eff_id for eff_id, meta in EFFECT_CATALOG.items()
        if "alias_of" not in meta
    ]

    # Compute multi-point visual signatures across time
    time_steps = [0.2, 0.8, 1.5, 2.3, 3.2]
    signatures = {}
    for eff_id in primary_effects:
        sig = tuple(
            tuple(tuple(col) for col in engine._compute(eff_id, t=t_step))
            for t_step in time_steps
        )
        signatures[eff_id] = sig

    # Pairwise comparison: every pair of primary effects must have distinct signatures
    for i, eff_a in enumerate(primary_effects):
        for j in range(i + 1, len(primary_effects)):
            eff_b = primary_effects[j]
            assert signatures[eff_a] != signatures[eff_b], (
                f"Visual identity violation: {eff_a} and {eff_b} produce identical visual output!"
            )


def test_gate_music_reactivity_end_to_end():
    """
    Release Gate 5 - Music:
    - Silent input stays dark.
    - Sustained notes do not repeatedly trigger false beats.
    - Real transients produce visible reactions that survive the cadence.
    """
    aurora = ReactiveAuroraStyle()

    # 1. Silence check -> strictly dark
    silent_state = MusicState(section=Section.SILENT, energy=0.0)
    silent_frame = aurora.render(silent_state, dt=0.05, num_zones=50)
    assert all(v == 0 for h, s, v in silent_frame), "Silent music must stay dark"

    # 2. Sustained notes do not produce repeated full-strip strobe
    sustained_state = MusicState(section=Section.VERSE, silent=False, energy=0.45, bass=0.3, transient=0.0, onset=0.0)
    frames_sustained = [aurora.render(sustained_state, dt=0.1, num_zones=50) for _ in range(5)]
    # Verify values remain stable without chaotic flash jumps
    max_diff_between_frames = max(
        abs(frames_sustained[i][25][2] - frames_sustained[i - 1][25][2])
        for i in range(1, len(frames_sustained))
    )
    assert max_diff_between_frames < 10, "Sustained note must produce smooth ambient movement without strobe jumps"

    # 3. Real transient produces localized crest highlight
    transient_state = MusicState(section=Section.VERSE, silent=False, energy=0.5, transient=0.9, onset=0.9)
    f_trans = aurora.render(transient_state, dt=0.05, num_zones=50)
    v_values = [v for h, s, v in f_trans]
    assert max(v_values) > min(v_values) + 20, "Transient must create visible crest peak"
    assert min(v_values) < 50, "Valleys must remain dark so the whole strip does not flash"


def test_gate_alias_variations_preserve_intended_differences():
    """
    Release Gate 3 - Alias Fidelity:
    Alias variations must preserve their intended differences and not produce
    identical outputs to their base effects under default settings.
    """
    mock_ctrl = MagicMock()
    mock_ctrl.set_native_effect.return_value = True
    mock_runner = MagicMock()
    mock_runner.run.side_effect = lambda coro: MagicMock(result=lambda timeout: True)
    engine = L930EffectsEngine(controller=mock_ctrl, loop_runner=mock_runner, app_state={})

    alias_pairs = [
        ("dusk", "golden_hour"),
        ("glitter_cascade", "starfield"),
        ("confetti", "prism_sparks"),
        ("dual_wipe", "cyber_chase"),
        ("sonar_sweep", "radar_sweep"),
        ("coordinated_lightning", "lightning"),
        ("infinite_prism", "rainbow"),
    ]

    time_steps = [0.4, 0.85, 1.6, 3.45, 4.8]

    for alias, base in alias_pairs:
        engine.start(alias)
        alias_sig = tuple(tuple(tuple(c) for c in engine._compute(alias, t=t)) for t in time_steps)
        engine.start(base)
        base_sig = tuple(tuple(tuple(c) for c in engine._compute(base, t=t)) for t in time_steps)

        assert alias_sig != base_sig, (
            f"Alias fidelity failure: {alias} produces identical trajectory to base {base}!"
        )


def test_gate_invalid_effect_requests_fail_cleanly():
    """
    Release Gate 1 - Error Handling & Edge Cases:
    Invalid effect requests must fail cleanly without unhandled exceptions,
    setting appropriate error status and returning explicit dark frames.
    """
    app_state = {}
    mock_ctrl = MagicMock()
    mock_runner = MagicMock()
    engine = L930EffectsEngine(controller=mock_ctrl, loop_runner=mock_runner, app_state=app_state)

    invalid_names = ["completely_fake_effect_xyz", "", "   ", "nonexistent_effect_999"]
    for bad_name in invalid_names:
        ok = engine.start(bad_name)
        assert not ok, f"Expected start({bad_name!r}) to return False"
        assert app_state.get("effect_status") == "failed"
        assert "Unknown L930 effect" in app_state.get("last_error", "")

    # In _compute(): invalid effect returns explicit dark state [0, 0, 0] * 50
    dark_frame = engine._compute("unknown_xyz")
    assert len(dark_frame) == 50
    assert all(c == [0, 0, 0] for c in dark_frame), "Unrecognized effect must return explicit dark zones [0, 0, 0]"


def test_gate_regression_parameter_limits_and_brightness():
    """
    Release Gate 4 - Parameter Bounds & Brightness Scaling:
    - Zero / minimum brightness scales down without zero division or errors.
    - Parameter inputs beyond nominal ranges clamp cleanly to safe bounds.
    - reset_parameters() restores all settings to clean baseline defaults.
    """
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={})

    # 1. Zero / low brightness
    engine.set_parameters(brightness=1)
    f_min = engine._compute("tide", t=1.0, apply_brightness=True)
    assert len(f_min) == 50
    assert all(1 <= v <= 100 for _, _, v in f_min)
    assert all(v <= 5 for _, _, v in f_min), "Minimum brightness (1%) should produce very dim values"

    # 2. Maximum brightness
    engine.set_parameters(brightness=100)
    f_max = engine._compute("tide", t=1.0, apply_brightness=True)
    assert any(v >= 40 for _, _, v in f_max)

    # 3. Parameter limits clamping
    engine.set_parameters(speed=-10.0)
    assert engine._speed == 0.2
    engine.set_parameters(speed=99.0)
    assert engine._speed == 3.0

    engine.set_parameters(particle_density=-5.0)
    assert engine._particle_density == 0.2
    engine.set_parameters(particle_density=50.0)
    assert engine._particle_density == 3.0

    engine.set_parameters(tail_length=-1.0)
    assert engine._tail_length == 0.2
    engine.set_parameters(tail_length=50.0)
    assert engine._tail_length == 3.0

    engine.set_parameters(wave_width=-0.5)
    assert engine._wave_width == 0.2
    engine.set_parameters(wave_width=25.0)
    assert engine._wave_width == 3.0

    engine.set_parameters(flash_strength=-1.0)
    assert engine._flash_strength == 0.2
    engine.set_parameters(flash_strength=10.0)
    assert engine._flash_strength == 3.0

    # 4. Clean reset
    engine.reset_parameters()
    assert engine._speed == 1.0
    assert engine._brightness == 50
    assert engine._palette_name == "sunset"
    assert engine._tail_length == 1.0
    assert engine._particle_density == 1.0
    assert engine._wave_width == 1.0
    assert engine._flash_strength == 1.0


def test_gate_rapid_effect_switching_and_stale_generations():
    """
    Release Gate 2 - Effect Switching & Pipeline Isolation:
    Rapid consecutive switching must advance generation counters, stop
    in-flight stream workers, and clear pending frame queues cleanly.
    """
    app_state = {}
    mock_ctrl = MagicMock()
    mock_ctrl.set_native_effect.return_value = True
    mock_ctrl.clear_frames.return_value = None
    mock_runner = MagicMock()
    mock_runner.run.side_effect = lambda coro: MagicMock(result=lambda timeout: True)

    engine = L930EffectsEngine(controller=mock_ctrl, loop_runner=mock_runner, app_state=app_state)

    effects_to_switch = [
        "tide", "cyber_chase", "golden_hour", "starfield", "comet",
        "glitter_cascade", "candy_cane", "police", "aurora", "sinelon"
    ]

    for eff in effects_to_switch:
        gen_before = engine._effect_generation
        ok = engine.start(eff)
        assert ok, f"Effect {eff} failed to start in rapid switch test"
        assert engine._effect_generation == gen_before + 1
        assert mock_ctrl.clear_frames.call_count > 0

    assert engine._active_effect_name == "sinelon"
    assert engine._effect_generation == len(effects_to_switch)


def test_gate_parameter_isolation_between_effects():
    """
    Release Gate 4 - Parameter Isolation:
    Alias parameter overrides (e.g. particle_density=1.8 on glitter_cascade)
    must NOT contaminate subsequent standard effect starts.
    """
    mock_ctrl = MagicMock()
    mock_ctrl.set_native_effect.return_value = True
    mock_runner = MagicMock()
    mock_runner.run.side_effect = lambda coro: MagicMock(result=lambda timeout: True)
    engine = L930EffectsEngine(controller=mock_ctrl, loop_runner=mock_runner, app_state={})

    # 1. Alias sets particle_density to 1.8
    engine.start("glitter_cascade")
    assert engine._particle_density == 1.8

    # 2. Starting standard starfield resets particle_density to 1.0
    engine.start("starfield")
    assert engine._particle_density == 1.0

    # 3. Alias sets flash_strength to 1.5
    engine.start("dual_wipe")
    assert engine._flash_strength == 1.5

    # 4. Starting cyber_chase resets flash_strength to 1.0
    engine.start("cyber_chase")
    assert engine._flash_strength == 1.0

    # 5. Alias sets tail_length to 2.0
    engine.start("sonar_sweep")
    assert engine._tail_length == 2.0

    # 6. Starting radar_sweep resets tail_length to 1.0
    engine.start("radar_sweep")
    assert engine._tail_length == 1.0
