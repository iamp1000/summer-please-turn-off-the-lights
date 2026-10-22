from __future__ import annotations

import pytest
from src.effects_l930 import L930EffectsEngine, ADVANCED_EFFECTS, EFFECT_CATALOG


@pytest.fixture
def engine():
    return L930EffectsEngine(controller=None, loop_runner=None, app_state={})


def test_advanced_effects_cadence_smoothness(engine):
    """
    Verify that all advanced effects are cadence-aware and do not strobe or flash
    abruptly at the physical 500ms hardware interval.
    """
    dt = 0.50  # Physical send interval: 500ms
    cadence_times = [i * dt for i in range(20)]  # 10 seconds of streaming

    for eff in ADVANCED_EFFECTS:
        frames = [engine._compute(eff, t=t) for t in cadence_times]

        # 1. Verify zone bounds
        for frame in frames:
            assert len(frame) == 50
            for h, s, v in frame:
                assert 0 <= h <= 360
                assert 0 <= s <= 100
                assert 0 <= v <= 100

        # 2. Verify no single-frame strobe spikes (sudden spike to 100 then back to <=10 in 1 frame)
        for i in range(1, len(frames) - 1):
            f_prev = frames[i - 1]
            f_curr = frames[i]
            f_next = frames[i + 1]

            for z in range(50):
                v_prev = f_prev[z][2]
                v_curr = f_curr[z][2]
                v_next = f_next[z][2]

                # A flash strobe is when a pixel is near dark, jumps up by >70, and collapses back down by >70
                is_strobe_spike = (v_curr - v_prev > 70) and (v_curr - v_next > 70)
                assert not is_strobe_spike, (
                    f"Effect '{eff}' exhibited single-frame strobe spike at zone {z}, "
                    f"t={cadence_times[i]}s: {v_prev} -> {v_curr} -> {v_next}"
                )


def test_advanced_effects_no_hard_black_cliffs(engine):
    """
    Verify that fluid and spatial effects (like gravity_slosh) do not drop abruptly
    to zero/black at boundary thresholds, preserving visual depth.
    """
    for t_step in [0.5, 1.5, 2.5, 3.5, 4.5]:
        frame = engine._compute("gravity_slosh", t=t_step)
        vals = [v for _, _, v in frame]
        # Fluid floor should be maintained, not snapped to 0 or 2
        assert min(vals) >= 8, f"gravity_slosh dropped below smooth fluid floor at t={t_step}"
        assert max(vals) >= 50, f"gravity_slosh peak too dim at t={t_step}"


def test_lightning_sheet_lightning_envelope(engine):
    """
    Verify that lightning uses continuous multi-frame blooming envelopes
    rather than sub-100ms blinks that get dropped by the hardware sender.
    """
    # Sample at 250ms across storm cycle
    times = [i * 0.25 for i in range(28)]
    frames = [engine._compute("lightning", t=t) for t in times]

    # Max brightness during discharge should hit high values
    all_peaks = [max(v for _, _, v in f) for f in frames]
    assert max(all_peaks) >= 80, "Lightning should hit high sheet brightness"

    # Thunder roll amber should appear in its designated window
    f_rumble = engine._compute("lightning", t=4.5)
    assert any(h == 28 for h, _, _ in f_rumble), "Thunder roll amber should be present"
