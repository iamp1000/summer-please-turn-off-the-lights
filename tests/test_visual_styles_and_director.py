from __future__ import annotations
import math
import time
from pathlib import Path
from typing import List, Tuple, Dict
import numpy as np
import pytest
from PIL import Image

from src.audio_dsp import MusicAnalyzer, MusicState, Section
from src.audio_replay import SyntheticTrackGenerator
from src.pipeline import tapo_hsv_to_rgb
from src.screen_sync import ScreenData
from src.visual_styles import (
    create_style_instances,
    MovieStyle,
    PulseStyle,
    SpectrumStyle,
    FlowStyle,
    DropBloomAccent,
    BuildTensionAccent,
    sample_palette_oklab,
)

ARTIFACT_DIR = Path("tests/artifacts/heatmaps")


def save_heatmap_png(
    frames: List[List[Tuple[int, int, int]]],
    output_path: Path,
    zone_scale: int = 4
):
    """
    Saves a zone-vs-time visualizer heatmap strip as PNG.
    X axis: Strip zones (0 to 49, scaled horizontally).
    Y axis: Time frames (0 to N-1 down).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = len(frames)
    if n_frames == 0:
        return

    num_zones = len(frames[0])
    raw_img = Image.new("RGB", (num_zones, n_frames))

    for y, frame in enumerate(frames):
        for x, (h, s, v) in enumerate(frame):
            r, g, b = tapo_hsv_to_rgb(h, s, v)
            rgb_255 = (int(r * 255.0), int(g * 255.0), int(b * 255.0))
            raw_img.putpixel((x, y), rgb_255)

    scaled_img = raw_img.resize((num_zones * zone_scale, n_frames), Image.Resampling.NEAREST)
    scaled_img.save(str(output_path))


def replay_samples_through_analyzer(
    samples: np.ndarray,
    samplerate: int = 44100,
    blocksize: int = 1024
) -> List[MusicState]:
    """Processes audio samples in blocksize chunks, returning list of MusicState snapshots."""
    analyzer = MusicAnalyzer(samplerate=samplerate, blocksize=blocksize, sensitivity=1.0)
    states = []
    n_blocks = len(samples) // blocksize
    for i in range(n_blocks):
        block = samples[i * blocksize : (i + 1) * blocksize]
        cur_time = (i * blocksize) / float(samplerate)
        st = analyzer.process_samples(block, now=cur_time)
        states.append(st)
    return states


# ── 1. Benchmark & Replay Across All 6 Tracks + Screen Clip ─────────────────

def test_four_modes_benchmarks_and_heatmaps():
    """
    Replays 6 synthetic audio tracks + a synthetic screen clip across the four modes:
    Movie, Pulse, Spectrum, Flow.
    Verifies:
      1. Render execution speed < 3.5 ms per frame.
      2. No black frames while energetic music is playing.
      3. Strict 100% OFF during silence track for music modes (Pulse, Spectrum, Flow).
      4. Movie never drops below room_level (floor ~18%) even during silence.
      5. Generates PNG heatmap strips in test artifacts.
    """
    sr = 44100
    bs = 1024
    dt = bs / sr

    tracks = {
        "build_and_drop": SyntheticTrackGenerator.generate_build_and_drop(duration=12.0, samplerate=sr),
        "classical": SyntheticTrackGenerator.generate_classical_track(duration=8.0, samplerate=sr),
        "halftime": SyntheticTrackGenerator.generate_half_time_pattern(bpm=85.0, duration=6.0, samplerate=sr),
        "click": SyntheticTrackGenerator.generate_click_track(bpm=120.0, duration=4.0, samplerate=sr),
        "sweep": SyntheticTrackGenerator.generate_sine_sweep(f_start=40.0, f_end=8000.0, duration=4.0, samplerate=sr),
        "silence": SyntheticTrackGenerator.generate_silence(duration=3.0, samplerate=sr),
    }

    # Synthetic screen clip data (slowly drifting color)
    synthetic_screen = ScreenData(
        global_hsv=(210, 60, 65),
        column_hsvs=[(int((200 + i * 2) % 360), 55, 60) for i in range(50)],
        is_static=False,
        timestamp=time.time(),
    )

    modes_to_test = ["movie", "pulse", "spectrum", "flow"]

    for track_name, audio_samples in tracks.items():
        states = replay_samples_through_analyzer(audio_samples, samplerate=sr, blocksize=bs)
        assert len(states) > 0

        for mode_name in modes_to_test:
            styles = create_style_instances()
            style = styles[mode_name]

            # Warmup
            if states:
                style.render(states[0], dt=dt, num_zones=50, screen_data=synthetic_screen)

            rendered_frames: List[List[Tuple[int, int, int]]] = []
            render_times: List[float] = []

            for st in states:
                t0 = time.perf_counter()
                frame = style.render(st, dt=dt, num_zones=50, screen_data=synthetic_screen)
                t1 = time.perf_counter()

                render_times.append((t1 - t0) * 1000.0)
                rendered_frames.append(frame)

            avg_render_ms = sum(render_times) / len(render_times)
            assert avg_render_ms < 3.5, f"{mode_name} exceeded 3.5ms budget: {avg_render_ms:.3f}ms"

            # Save PNG heatmap strip
            png_path = ARTIFACT_DIR / f"{track_name}_{mode_name}.png"
            save_heatmap_png(rendered_frames, png_path)
            assert png_path.exists()

            # Silence track assertions
            if track_name == "silence":
                if mode_name == "movie":
                    # Movie never drops below room floor (~18%)
                    for f in rendered_frames:
                        for h, s, v in f:
                            assert v >= 15, f"Movie mode dropped below room level during silence: {v}"
                else:
                    # Music modes are strictly 100% OFF during silence
                    for f in rendered_frames:
                        for h, s, v in f:
                            assert v == 0, f"Expected 0% brightness during silence in {mode_name}, got {v}"

            # Music playing assertion: no black frames when music has energy
            if track_name in ("build_and_drop", "classical"):
                high_energy_frames = [
                    f for i, f in enumerate(rendered_frames)
                    if states[i].energy > 0.25 and states[i].section not in (Section.SILENT, Section.BREAKDOWN)
                ]
                for f in high_energy_frames:
                    max_b = max(v for _, _, v in f)
                    assert max_b > 0, f"{mode_name} produced black frame while music was energetic"


# ── 2. Distinct Visual Signatures Across Exactly Four Modes ─────────────────

def test_distinct_outputs_across_four_modes():
    """
    Asserts that Movie, Pulse, Spectrum, and Flow generate distinctly different visual outputs
    when presented with the exact same energetic music state.
    """
    state = MusicState(
        bands=np.full(50, 0.6, dtype=np.float32),
        onset=0.8,
        kick=0.9,
        snare=0.3,
        hat=0.7,
        bpm=128.0,
        beat_phase=0.4,
        bar_pos=1,
        energy=0.80,
        energy_trend=0.05,
        centroid=1800.0,
        intensity=0.75,
        tension=0.5,
        impact=0.85,
        section=Section.VERSE,
        palette=[(215, 85, 75), (180, 90, 80), (280, 80, 70), (45, 95, 85)],
        harmonic_ratio=0.65
    )

    screen = ScreenData(
        global_hsv=(200, 60, 70),
        column_hsvs=[(200, 60, 70)] * 50,
        is_static=False,
    )

    styles = create_style_instances()
    four_modes = ["movie", "pulse", "spectrum", "flow"]

    rendered_snapshots = {}
    for name in four_modes:
        style = styles[name]
        for _ in range(5):
            f = style.render(state, dt=0.025, num_zones=50, screen_data=screen)
        rendered_snapshots[name] = [v for _, _, v in f]

    # Pairwise comparison: brightness profiles must differ significantly across modes
    for i in range(len(four_modes)):
        for j in range(i + 1, len(four_modes)):
            name_a = four_modes[i]
            name_b = four_modes[j]
            arr_a = np.array(rendered_snapshots[name_a], dtype=np.float32)
            arr_b = np.array(rendered_snapshots[name_b], dtype=np.float32)
            mad = float(np.mean(np.abs(arr_a - arr_b)))
            assert mad > 3.0, f"{name_a} and {name_b} outputs are too similar (MAD={mad:.2f})"


# ── 3. Persistent Envelopes (>= 2 Send Periods, > 400 ms) ───────────────────

def test_persistent_envelopes_on_transients():
    """
    Verifies that instantaneous clicks/transients produce envelopes lasting
    at least 2 send periods (> 400 ms at 5 updates/s).
    """
    sr = 44100
    bs = 1024
    dt = bs / sr  # ~23.2 ms per frame

    styles = create_style_instances()
    pulse = styles["pulse"]

    # 1. Steady low baseline
    low_state = MusicState(energy=0.10, kick=0.0, onset=0.0, section=Section.VERSE)
    for _ in range(5):
        pulse.render(low_state, dt=dt, num_zones=50)

    # 2. Instantaneous single-frame transient kick
    hit_state = MusicState(energy=0.85, kick=1.0, impact=1.0, section=Section.VERSE)
    frame_hit = pulse.render(hit_state, dt=dt, num_zones=50)
    hit_max_b = max(v for _, _, v in frame_hit)
    assert hit_max_b > 40

    # 3. Audio immediately low again
    decay_states = [low_state] * 20  # ~460 ms of decay
    decay_frames = [pulse.render(st, dt=dt, num_zones=50) for st in decay_states]

    # After 10 frames (~230 ms): must still have elevated brightness
    b_frame10 = max(v for _, _, v in decay_frames[9])
    assert b_frame10 >= 20, f"Envelope collapsed too fast at +230ms (b={b_frame10})"

    # After 18 frames (~415 ms, > 400 ms): envelope must still be active (> 2 send periods)
    b_frame18 = max(v for _, _, v in decay_frames[17])
    assert b_frame18 >= 8, f"Envelope collapsed before 400ms (b={b_frame18})"


# ── 4. White Flash Exclusively Restricted to Drop Bloom ───────────────────────

def test_white_flash_exclusively_on_drop_bloom():
    """
    Verifies that:
      1. Base modes never produce saturation = 0 (pure white) during normal kicks.
      2. Drop Bloom produces pure white (saturation = 0) ONLY during Section.DROP with drop_strength > 0.8.
      3. Strict 8-second cooldown prevents repeated white blinding.
    """
    styles = create_style_instances()
    four_modes = ["movie", "pulse", "spectrum", "flow"]

    # Normal heavy kick in Verse
    verse_kick = MusicState(
        energy=0.95, kick=1.0, impact=1.0, section=Section.VERSE, drop_strength=0.9,
        palette=[(215, 85, 75)]
    )

    for name in four_modes:
        style = styles[name]
        frame = style.render(verse_kick, dt=0.03, num_zones=50)
        for h, s, v in frame:
            if v > 30:
                assert s > 15, f"{name} produced pure white flash (s={s}) during normal Verse kick!"

    # Test DropBloomAccent
    bloom = DropBloomAccent()

    # Precondition: must observe BUILD or BREAKDOWN first
    build_state = MusicState(section=Section.BUILD, tension=0.9, energy=0.85)
    bloom.render_accent(build_state, dt=0.03, num_zones=50, frame=[(215, 85, 50)] * 50)

    # True drop hit
    drop_state = MusicState(
        section=Section.DROP,
        drop_strength=0.92,
        energy=0.98,
        palette=[(215, 85, 75)]
    )
    base_frame = [(215, 85, 60)] * 50
    # Attack -> Hold
    for _ in range(4):
        f = bloom.render_accent(drop_state, dt=0.02, num_zones=50, frame=base_frame)

    # Pure laser white: saturation must collapse to 0 and brightness must be 100
    assert f[25][1] == 0, f"Expected saturation 0 on drop bloom, got {f[25][1]}"
    assert f[25][2] == 100, f"Expected brightness 100 on drop bloom, got {f[25][2]}"

    # Advance through hold and decay stages so the first bloom completes (total ~0.65s)
    for _ in range(16):
        bloom.render_accent(drop_state, dt=0.045, num_zones=50, frame=base_frame)
    assert bloom.stage == "IDLE"

    # Immediate second drop hit: 8s cooldown prevents re-blooming
    f_cooldown = bloom.render_accent(drop_state, dt=0.03, num_zones=50, frame=base_frame)
    # Saturation recovered! Pure white is blocked
    assert f_cooldown[25][1] > 0, "Drop bloom fired again without enforcing 8-second cooldown"


# ── 5. Dedicated Single-Zone (L900) Behavior ──────────────────────────────────

def test_dedicated_single_zone_l900_rendering():
    """
    Verifies that num_zones=1 triggers dedicated single-zone behaviors
    for all four modes without errors, returning valid 0-100 ranges.
    """
    styles = create_style_instances()
    state = MusicState(
        energy=0.75, kick=0.85, hat=0.6, bpm=120.0, beat_phase=0.5,
        section=Section.VERSE, harmonic_ratio=0.70,
        palette=[(180, 90, 80), (280, 85, 75)]
    )
    screen = ScreenData(global_hsv=(200, 60, 70), column_hsvs=[(200, 60, 70)] * 50)

    for mode_name in ["movie", "pulse", "spectrum", "flow"]:
        style = styles[mode_name]
        frame_1 = style.render(state, dt=0.03, num_zones=1, screen_data=screen)
        assert len(frame_1) == 1, f"{mode_name} did not return 1 zone for L900"
        h, s, v = frame_1[0]
        assert 0 <= h <= 360, f"{mode_name} invalid hue: {h}"
        assert 0 <= s <= 100, f"{mode_name} invalid saturation: {s}"
        assert 0 <= v <= 100, f"{mode_name} invalid brightness: {v}"


# ── 6. Segmented VU Visualizer Mode ──────────────────────────────────────────

def test_segmented_vu_visualizer_breaks_and_peaks():
    """
    Verifies that SegmentedVUStyle:
      1. Returns strictly all-zeros on silence.
      2. Renders unidirectional fill with staccato breaks (dark gap zones).
      3. Modulates break offsets on transient/hat impacts.
      4. SpectrumStyle delegates to SegmentedVUStyle when layout='segmented'.
      5. Handles single-zone L900 correctly.
    """
    from src.visual_styles import SegmentedVUStyle

    vu = SegmentedVUStyle()

    # 1. Silence check
    silent_st = MusicState(energy=0.0, section=Section.SILENT)
    f_silent = vu.render(silent_st, dt=0.03, num_zones=50)
    assert all(v == 0 for _, _, v in f_silent), "Silent state must return 100% true black"

    # 2. Active fill check
    active_st = MusicState(energy=0.75, kick=0.8, hat=0.1, section=Section.VERSE)
    f_active = vu.render(active_st, dt=0.03, num_zones=50)
    assert len(f_active) == 50

    # Must have some lit zones and some break/dark zones
    lit_zones = [i for i, (_, _, v) in enumerate(f_active) if v > 0]
    dark_zones = [i for i, (_, _, v) in enumerate(f_active) if v == 0]
    assert len(lit_zones) > 10, "Expected at least 10 lit zones during active music"
    assert len(dark_zones) > 0, "Expected dark break gaps in between clusters"

    # 3. Transient shift test
    init_offset = vu.break_offset
    transient_st = MusicState(energy=0.8, kick=0.9, hat=0.8, impact=0.85, section=Section.VERSE)
    time.sleep(0.15) # Ensure impact interval threshold passes
    vu.render(transient_st, dt=0.03, num_zones=50)
    assert vu.break_offset != init_offset, "Break offset should dynamically shift on transient impact"

    # 4. SpectrumStyle layout toggle
    spec = SpectrumStyle(layout="segmented")
    f_spec = spec.render(active_st, dt=0.03, num_zones=50)
    assert len(f_spec) == 50
    # Must have breaks
    assert any(v == 0 for _, _, v in f_spec[:20]), "SpectrumStyle layout='segmented' should contain break gaps"

    # 5. Single zone L900
    f_1 = vu.render(active_st, dt=0.03, num_zones=1)
    assert len(f_1) == 1
    assert 0 <= f_1[0][0] <= 360
    assert 0 <= f_1[0][1] <= 100
    assert 0 <= f_1[0][2] <= 100


def test_non_linear_mode_builder():
    """Verify build_mode_segments handles explicit segments, region slices, and gradient stops."""
    from src.modes import build_mode_segments

    # 1. Explicit segments
    m_segs = {"segments": [[100, 80, 60]] * 50}
    res_segs = build_mode_segments(m_segs, 50)
    assert len(res_segs) == 50
    assert res_segs[0] == [100, 80, 60]

    # 2. Region slices
    m_reg = {
        "brightness": 70,
        "regions": [
            {"range": [0, 15], "hsv": [320, 100, 75]},
            {"range": [15, 35], "hsv": [180, 90, 80]},
            {"range": [35, 50], "hsv": [280, 85, 70]},
        ]
    }
    res_reg = build_mode_segments(m_reg, 50)
    assert len(res_reg) == 50
    assert res_reg[5] == [320, 100, 75]
    assert res_reg[25] == [180, 90, 80]
    assert res_reg[45] == [280, 85, 70]

    # 3. Stops center_out layout (symmetrical around center IC)
    m_stops = {
        "brightness": 80,
        "layout": "center_out",
        "stops": [[320, 95, 80], [185, 100, 90]],
    }
    res_stops = build_mode_segments(m_stops, 50)
    assert len(res_stops) == 50
    # Outer edges (0 and 49) should match each other closely
    assert abs(res_stops[0][0] - res_stops[49][0]) <= 5

    # 4. Fallback subtle depth curve (center slightly brighter than ends)
    m_single = {"hue": 200, "saturation": 80, "brightness": 60}
    res_single = build_mode_segments(m_single, 50)
    assert len(res_single) == 50
    assert res_single[25][2] > res_single[0][2]  # center halo


def test_non_linear_procedural_effects():
    """Verify L930EffectsEngine non-linear procedural models generate valid 50-IC frames."""
    from src.effects_l930 import L930EffectsEngine

    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state={"brightness": 100})

    effects = ["cyber_chase", "hearth", "neon_heartbeat", "golden_hour", "dusk", "starfield", "embers", "comet", "sonar_sweep"]
    for eff in effects:
        frame = engine._compute(eff, t=1.5)
        assert len(frame) == 50, f"Effect {eff} failed to produce 50 segments"
        for i, (h, s, v) in enumerate(frame):
            assert 0 <= h <= 360, f"{eff} zone {i} invalid hue: {h}"
            assert 0 <= s <= 100, f"{eff} zone {i} invalid saturation: {s}"
            assert 0 <= v <= 100, f"{eff} zone {i} invalid brightness: {v}"


def test_pulse_multi_origin_and_percussion_accents():
    """Verify PulseStyle spawns ripples from different bar-locked origins and applies snare/hat accents."""
    from src.visual_styles import PulseStyle

    pulse = PulseStyle()

    # Bar 0: Center origin (24.5)
    st_bar0 = MusicState(energy=0.8, kick=0.9, bar_pos=0, section=Section.VERSE)
    f0 = pulse.render(st_bar0, dt=0.03, num_zones=50)
    assert len(pulse.ripples) >= 1
    assert pulse.ripples[-1]["origin"] == 24.5

    # Clear and test Bar 1: Left-third origin (12.0)
    pulse.ripples.clear()
    pulse._spawn_cooldown = 0.0
    st_bar1 = MusicState(energy=0.8, kick=0.9, bar_pos=1, section=Section.VERSE)
    f1 = pulse.render(st_bar1, dt=0.03, num_zones=50)
    assert len(pulse.ripples) >= 1
    assert pulse.ripples[-1]["origin"] == 12.0

    # Snare accent check: high snare activates pockets
    st_snare = MusicState(energy=0.5, kick=0.0, snare=0.9, bar_pos=0, section=Section.VERSE)
    f_snare = pulse.render(st_snare, dt=0.03, num_zones=50)
    # Zone 12, 25, or 37 should have flash boost
    assert f_snare[12][2] > 0 or f_snare[25][2] > 0


def test_movie_5_tap_gaussian_spatial_convolution():
    """Verify MovieStyle convolves 50-column screen data preserving localized hot spots."""
    from src.visual_styles import MovieStyle
    from src.screen_sync import ScreenData

    movie = MovieStyle()

    # Create screen data with one bright green explosion at column 15, rest dark/neutral
    cols = [[30, 45, 18] for _ in range(50)]
    cols[15] = [120, 100, 95]
    cols[16] = [120, 100, 90]

    sd = ScreenData(column_hsvs=cols, global_hsv=(30, 45, 18))
    st = MusicState(energy=0.2, section=Section.VERSE)

    f = movie.render(st, dt=0.03, num_zones=50, screen_data=sd)
    assert len(f) == 50

    # IC 15 should reflect the localized bright green explosion distinctly over baseline
    assert f[15][0] >= 65
    assert f[15][0] > f[45][0] + 30
    # Far-away IC (e.g. 45) should remain near the warm room baseline (30)
    assert f[45][0] <= 35


def test_flow_polyphonic_circle_of_fifths_constellation():
    """Verify FlowStyle maps active chords in polyphonic spatial triads via Circle of Fifths."""
    from src.visual_styles import FlowStyle

    flow = FlowStyle()

    # Active chord with high harmonic ratio and chroma energy at C (0), E (4), G (7)
    chroma = np.zeros(12, dtype=np.float32)
    chroma[0] = 0.90  # C
    chroma[4] = 0.85  # E
    chroma[7] = 0.80  # G

    st = MusicState(energy=0.6, harmonic_ratio=0.85, chroma=chroma, section=Section.VERSE)
    f = flow.render(st, dt=0.03, num_zones=50)
    assert len(f) == 50

    # Harmonic boosts should illuminate zones across the strip without blackouts
    lit = [v for _, _, v in f if v > 20]
    assert len(lit) >= 30


def test_party_style_micro_bursts_and_staccato():
    """Verify PartyStyle generates staccato sparks on hat/onset triggers and adheres to silence."""
    from src.visual_styles import PartyStyle

    party = PartyStyle()

    # 1. Silence: 100% off
    st_silent = MusicState(energy=0.001, section=Section.SILENT)
    f_silent = party.render(st_silent, dt=0.03, num_zones=50)
    assert all(v == 0 for _, _, v in f_silent)

    # 2. Active audio with hi-hat transient: triggers sparks and bright pops
    st_hat = MusicState(energy=0.75, onset=0.85, hat=0.90, section=Section.VERSE)
    f_hat = party.render(st_hat, dt=0.03, num_zones=50)
    assert len(f_hat) == 50
    assert len(party._spark_positions) > 0
    # Zones in spark positions hit peak brightness 100
    for p in party._spark_positions:
        assert f_hat[p][2] == 100

    # 3. Single-zone L900 safety
    f_single = party.render(st_hat, dt=0.03, num_zones=1)
    assert len(f_single) == 1


def test_chill_style_smooth_breathing_envelope():
    """Verify ChillStyle provides velvety tau=1.2s relaxation in warm amber spectrum."""
    from src.visual_styles import ChillStyle

    chill = ChillStyle()

    # 1. Silence: 100% off
    st_silent = MusicState(energy=0.001, section=Section.SILENT)
    f_silent = chill.render(st_silent, dt=0.03, num_zones=50)
    assert all(v == 0 for _, _, v in f_silent)

    # 2. Active lofi groove: warm golden palette and center-out gradient
    st_groove = MusicState(energy=0.55, section=Section.VERSE)
    f_groove = chill.render(st_groove, dt=0.05, num_zones=50)
    assert len(f_groove) == 50
    # Center zone (24, 25) should be brighter or equal to outer edges (0, 49)
    assert f_groove[25][2] >= f_groove[0][2]
    # Warm amber hues in auto mode: hues should be in warm spectrum (20 to 50 or 340 to 360)
    for h, s, v in f_groove:
        assert (0 <= h <= 60) or (330 <= h <= 360)

    # 3. Single-zone L900 safety
    f_single = chill.render(st_groove, dt=0.05, num_zones=1)
    assert len(f_single) == 1


def test_edm_mode_drop_strike_and_shockwave():
    """Verify EdmModeStyle collapses saturation on drop hits and emits expanding neon ripples."""
    from src.visual_styles import EdmModeStyle

    edm = EdmModeStyle()

    # 1. Silence: 100% off
    st_silent = MusicState(energy=0.001, section=Section.SILENT)
    f_silent = edm.render(st_silent, dt=0.03, num_zones=50)
    assert all(v == 0 for _, _, v in f_silent)

    # 2. Massive drop hit: drop_strength > 0.8 -> saturation collapses to 0 (blinding white flash)
    st_drop = MusicState(energy=0.95, kick=0.88, drop_strength=0.92, impact=0.85, section=Section.DROP)
    f_drop = edm.render(st_drop, dt=0.02, num_zones=50)
    assert len(f_drop) == 50
    assert len(edm.ripples) >= 1

    # Center zone (24) is within core flash radius (<12) -> saturation must be 0 (pure white)
    assert f_drop[24][1] == 0  # S = 0
    assert f_drop[24][2] == 100  # V = 100

    # 3. Expanding ripple propagation over successive frames
    for _ in range(5):
        f_wave = edm.render(st_drop, dt=0.05, num_zones=50)
    assert len(f_wave) == 50

    # 4. Single-zone L900 safety
    f_single = edm.render(st_drop, dt=0.02, num_zones=1)
    assert len(f_single) == 1


def test_create_style_instances_custom_vibes():
    """Verify party, chill, and edm are registered in style instances and aliases."""
    instances = create_style_instances()
    assert "party" in instances
    assert "club" in instances
    assert "chill" in instances
    assert "lofi" in instances
    assert "edm" in instances
    assert "drop" in instances
    assert "edm_drop" in instances

    assert instances["party"].name == "Party"
    assert instances["chill"].name == "Chill"
    assert instances["edm"].name == "EDM"
    assert "aurora" in instances
    assert "reactive_aurora" in instances
    assert instances["aurora"].name == "Reactive Aurora"


def test_reactive_aurora_style():
    """Verify Reactive Aurora responds to bass, mids, transients, and respects quiet passages."""
    from src.visual_styles import ReactiveAuroraStyle, get_visual_style
    from src.audio_dsp import MusicState, Section

    aurora = ReactiveAuroraStyle()

    # 1. Silence check -> returns all black
    silent_state = MusicState(section=Section.SILENT, energy=0.0)
    silent_frame = aurora.render(silent_state, dt=0.05, num_zones=50)
    assert all(v == 0 for h, s, v in silent_frame), "Silent music must remain atmospheric and dark"

    # 2. Bass drives curtain movement
    aurora1 = ReactiveAuroraStyle()
    aurora2 = ReactiveAuroraStyle()
    low_bass_state = MusicState(section=Section.VERSE, silent=False, energy=0.4, bass=0.05, mid=0.3)
    high_bass_state = MusicState(section=Section.VERSE, silent=False, energy=0.4, bass=0.90, mid=0.3)

    aurora1.render(low_bass_state, dt=0.5, num_zones=50)
    aurora2.render(high_bass_state, dt=0.5, num_zones=50)
    assert aurora2._phase1 > aurora1._phase1, "Bass must accelerate curtain movement"

    # 3. Mids influence body and color (emerald vs violet shift)
    aurora_low_mid = ReactiveAuroraStyle()
    aurora_high_mid = ReactiveAuroraStyle()
    state_emerald = MusicState(section=Section.VERSE, silent=False, energy=0.5, mid=0.05)
    state_violet = MusicState(section=Section.VERSE, silent=False, energy=0.5, mid=0.95)

    f_emerald = aurora_low_mid.render(state_emerald, dt=0.5, num_zones=50)
    f_violet = aurora_high_mid.render(state_violet, dt=0.5, num_zones=50)

    avg_h_emerald = sum(h for h, s, v in f_emerald) / 50.0
    avg_h_violet = sum(h for h, s, v in f_violet) / 50.0
    assert avg_h_emerald != avg_h_violet, "Mids must shift color balance"

    # 4. Transients create localized crest highlights without flashing the entire strip
    aurora_trans = ReactiveAuroraStyle()
    trans_state = MusicState(section=Section.VERSE, silent=False, energy=0.5, transient=0.9, onset=0.9)
    f_trans = aurora_trans.render(trans_state, dt=0.05, num_zones=50)
    v_values = [v for h, s, v in f_trans]

    assert max(v_values) > min(v_values) + 20, "Transient must create distinct peak highlights"
    assert min(v_values) < 50, "Quiet/valley zones must not flash when transients hit"

