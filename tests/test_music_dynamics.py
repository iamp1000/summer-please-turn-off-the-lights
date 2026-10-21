from __future__ import annotations

import numpy as np

from src.audio_dsp import MusicState, Section
from src.music_dynamics import MusicBrightnessFloor, music_is_genuinely_active
from src.music_reactive import MusicReactive
from src.music_reactive_l930 import MusicReactiveL930, NUM_SEGMENTS
from src.visual_styles import EdmModeStyle


class _FakeController:
    def __init__(self):
        self.frames = []
        self._max_updates_per_s = 5.0
        self.music_transition_ms = 120
        self.movie_transition_ms = 800
        self.diagnostics = type("Diagnostics", (), {"total_latency_ms": 0.0})()

    def submit_frame(self, frame):
        self.frames.append(frame)

    def clear_frames(self):
        self.frames.clear()


class _FixedColorStyle:
    def set_params(self, **kwargs):
        self.params = kwargs

    def render(self, state, dt, num_zones, **kwargs):
        if num_zones == 1:
            return [(215, 85, 30)]
        return [(215, 85, 30) for _ in range(num_zones)]


def _active_state(**kwargs):
    values = dict(
        bands=np.full(50, 0.25, dtype=np.float32),
        energy=0.45,
        energy_trend=0.02,
        tension=0.2,
        onset=0.2,
        kick=0.15,
        bass=0.2,
        mid=0.25,
        hat=0.18,
        section=Section.VERSE,
        silent=False,
        palette=[(215, 85, 75), (180, 90, 80), (280, 80, 70), (45, 95, 85)],
    )
    values.update(kwargs)
    return MusicState(**values)


def _output_brightness(frame):
    if "segments" in frame:
        return max((int(zone[2]) for zone in frame["segments"]), default=0)
    return int(frame.get("b", 0))


def test_brightness_floor_is_active_signal_only_and_returns_to_zero():
    floor = MusicBrightnessFloor(floor_percent=5.5, attack_tau=0.18, release_tau=0.55)
    active = _active_state()
    assert music_is_genuinely_active(active)

    level = floor.update(active, dt=0.4, master_ceiling=0.5)
    assert 1.0 <= level <= 2.75

    # The helper must not illuminate a true-black frame.
    assert floor.apply_l900((215, 85, 0), level) == (0, 0, 0)
    assert floor.apply_l900((215, 85, 1), level)[2] >= 1

    silence = MusicState(silent=True, energy=0.0, section=Section.SILENT)
    assert not music_is_genuinely_active(silence)
    for _ in range(30):
        level = floor.update(silence, dt=0.1, master_ceiling=0.5)
    assert level == 0.0, "temporary floor must release fully after sustained silence"


def test_l900_analyzer_path_fades_cached_active_color_to_true_black():
    controller = _FakeController()
    engine = MusicReactive(controller=controller, loop_runner=None, app_state={"brightness": 100})
    engine.style_name = "fixed_test"
    engine._styles["fixed_test"] = _FixedColorStyle()
    if hasattr(engine, "_compositor"):
        del engine._compositor

    engine._render_from_music_state(_active_state(), dt=0.05)
    assert controller.frames
    first_brightness = _output_brightness(controller.frames[-1])
    assert first_brightness > 0

    silence = MusicState(bands=np.zeros(50), energy=0.0, silent=True, section=Section.SILENT)
    observed = []
    for _ in range(20):
        engine._render_from_music_state(silence, dt=0.1)
        observed.append(_output_brightness(controller.frames[-1]))

    assert observed[-1] == 0
    # After its short hold, the release is monotonic; no brightness spikes or permanent floor.
    release = observed[1:]
    assert all(b <= a for a, b in zip(release, release[1:]))
    assert first_brightness > observed[0] >= observed[-1]


def test_l930_analyzer_path_fades_cached_zones_to_true_black():
    controller = _FakeController()
    engine = MusicReactiveL930(controller=controller, loop_runner=None, app_state={"brightness": 100})
    engine.style_name = "fixed_test"
    engine._styles["fixed_test"] = _FixedColorStyle()
    if hasattr(engine, "_compositor"):
        del engine._compositor

    engine._render_from_music_state(_active_state(), dt=0.05)
    assert controller.frames
    assert _output_brightness(controller.frames[-1]) > 0

    silence = MusicState(bands=np.zeros(50), energy=0.0, silent=True, section=Section.SILENT)
    observed = []
    for _ in range(20):
        engine._render_from_music_state(silence, dt=0.1)
        frame = controller.frames[-1]
        assert len(frame["segments"]) == NUM_SEGMENTS
        observed.append(_output_brightness(frame))

    assert observed[-1] == 0
    assert all(b <= a for a, b in zip(observed[1:], observed[2:]))
    assert any(b > 0 for b in observed[:-1])


def test_edm_melodic_drop_stays_colored_without_bass_qualified_flash():
    style = EdmModeStyle()
    melodic_bands = np.concatenate([
        np.full(10, 0.08),
        np.full(25, 0.82),
        np.full(15, 0.88),
    ]).astype(np.float32)
    melodic_drop = _active_state(
        bands=melodic_bands,
        section=Section.DROP,
        silent=False,
        energy=0.85,
        energy_trend=0.12,
        tension=0.75,
        kick=0.82,
        bass=0.08,
        impact=0.98,
        drop_strength=0.98,
        centroid_norm=0.85,
    )
    frames = [style.render(melodic_drop, dt=0.1, num_zones=50) for _ in range(4)]
    assert all(len(frame) == 50 for frame in frames)
    assert all(not any(s == 0 and v >= 90 for _, s, v in frame) for frame in frames), (
        "melodic/high-frequency drops must not trigger white strikes without bass evidence"
    )
    assert len({h for h, _, _ in frames[-1]}) >= 8


def test_edm_confirmed_bass_drop_keeps_a_qualified_white_accent():
    style = EdmModeStyle()
    bass_bands = np.concatenate([
        np.full(10, 0.90),
        np.full(25, 0.35),
        np.full(15, 0.20),
    ]).astype(np.float32)
    bass_drop = _active_state(
        bands=bass_bands,
        section=Section.DROP,
        silent=False,
        energy=0.88,
        kick=0.95,
        bass=0.90,
        impact=0.98,
        drop_strength=0.98,
    )
    frame = style.render(bass_drop, dt=0.03, num_zones=50)
    assert any(s < 15 and v >= 88 for _, s, v in frame), (
        "a confident bass-led drop should retain its intentionally dramatic accent"
    )


def test_edm_build_grows_gradually_as_energy_and_section_progress_rise():
    style = EdmModeStyle()
    frames = []
    for energy, progress in ((0.20, 0.10), (0.38, 0.45), (0.60, 0.85)):
        state = _active_state(
            bands=np.concatenate([
                np.full(10, 0.20),
                np.full(25, energy * 0.80),
                np.full(15, energy * 0.65),
            ]).astype(np.float32),
            section=Section.BUILD,
            silent=False,
            energy=energy,
            energy_trend=0.06,
            tension=progress,
            section_progress=progress,
            kick=0.05,
            impact=0.12,
            drop_strength=0.15,
        )
        frames.append(style.render(state, dt=0.10, num_zones=50))

    means = [sum(v for _, _, v in frame) / len(frame) for frame in frames]
    assert means[0] < means[1] < means[2], means
    assert all(all(s > 0 for _, s, _ in frame) for frame in frames), "builds should rise in color, not whiten"



def test_pulse_ripple_survives_protected_one_hertz_send_cadence():
    from src.visual_styles import PulseStyle

    style = PulseStyle()
    style.set_params(output_interval_s=1.0)
    state = _active_state(kick=0.95, onset=0.65, impact=0.65, energy=0.70)

    style.render(state, dt=0.05, num_zones=50)
    assert style.ripples, "a strong kick should launch a Pulse wave"
    original_life = style.ripples[0]["life"]
    assert style.ripples[0]["lifetime"] >= 2.0

    decay_state = _active_state(kick=0.05, onset=0.0, impact=0.0, energy=0.45)
    for _ in range(10):
        frame = style.render(decay_state, dt=0.10, num_zones=50)

    assert style.ripples, "Pulse wave must span multiple 1 Hz hardware sends"
    assert style.ripples[0]["life"] < original_life
    assert max(v for _, _, v in frame) > 0


def test_spectrum_peak_markers_hold_for_multiple_device_send_periods():
    from src.visual_styles import SpectrumStyle

    style = SpectrumStyle()
    style.set_params(output_interval_s=1.0)
    hot_bands = np.full(50, 0.01, dtype=np.float32)
    hot_bands[0:8] = 0.95
    hot_state = _active_state(bands=hot_bands, energy=0.65)

    style.render(hot_state, dt=0.10, num_zones=50)
    initial_peak = max(style.peaks)
    assert initial_peak > 50

    quiet_bands = np.zeros(50, dtype=np.float32)
    quiet_state = _active_state(bands=quiet_bands, energy=0.15, kick=0.0, onset=0.0)
    for _ in range(10):
        frame = style.render(quiet_state, dt=0.10, num_zones=50)

    assert max(style.peak_hold_timers) > 0.2, "marker should remain held across a 1 Hz send period"
    assert max(style.peaks) >= initial_peak * 0.95, "peak marker should not vanish between hardware sends"
    assert len(frame) == 50


def test_center_burst_ripple_survives_protected_one_hertz_send_cadence():
    from src.visual_styles import CenterBurstStyle

    style = CenterBurstStyle()
    style.set_params(output_interval_s=1.0)
    hit = _active_state(kick=0.85, onset=0.90, impact=0.75, energy=0.70)
    style.render(hit, dt=0.05, num_zones=50)

    assert style._ripples, "kick/onset should launch Center Burst"
    assert style._ripples[0]["lifetime"] >= 1.9

    decay_state = _active_state(kick=0.05, onset=0.02, impact=0.0, energy=0.40)
    for _ in range(10):
        frame = style.render(decay_state, dt=0.10, num_zones=50)

    assert style._ripples, "burst should persist across more than one physical frame"
    assert max(v for _, _, v in frame) > 0


def test_spectrum_uses_smooth_multishade_palette_with_distinct_band_energy():
    from src.visual_styles import SpectrumStyle

    style = SpectrumStyle()
    bands = np.linspace(0.05, 0.95, 50, dtype=np.float32)
    state = _active_state(bands=bands, energy=0.55, bass=0.75, mid=0.50, hat=0.35)
    frame = style.render(state, dt=0.10, num_zones=50)

    hues = [h for h, _, _ in frame]
    assert len(set(hues)) >= 8, "spectrum should retain smooth intermediate palette shades"
    assert max(v for _, _, v in frame) > min(v for _, _, v in frame)
