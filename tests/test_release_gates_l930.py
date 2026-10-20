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
