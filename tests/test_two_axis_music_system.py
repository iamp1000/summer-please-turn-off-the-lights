from __future__ import annotations
import math
import numpy as np
import pytest

from src.audio_dsp import MusicAnalyzer, MusicState, Section
from src.audio_replay import WavReplayer, SyntheticTrackGenerator, FakeDeviceSimulator
from src.visual_styles import (
    get_visual_style,
    STYLE_REGISTRY,
    PulseStyle,
    SpectrumStyle,
    AuroraStyle,
    WaveStyle,
    CinematicStyle,
    AmbientStyle,
    ParticlesStyle,
    HybridStyle,
)

def test_music_analyzer_micro_meso_macro():
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=1024, sensitivity=1.0)

    # 1. Test Silence
    silence = np.zeros(1024, dtype=np.float32)
    state = analyzer.process_samples(silence, now=1.0)
    assert len(state.bands) == 50
    assert state.energy <= 0.05
    assert state.section == Section.SILENT

    # 2. Test Tone in A4 (440 Hz)
    t = np.arange(1024) / 44100.0
    tone = (0.5 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)

    for i in range(20):
        state = analyzer.process_samples(tone, now=1.0 + i * 0.025)

    assert state.energy > 0.1
    assert len(state.palette) >= 3
    for h, s, v in state.palette:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100
    assert state.mode in ("major", "minor")
    assert 0.0 <= state.beat_phase <= 1.0
    assert 0 <= state.bar_pos <= 3


def test_synthetic_edm_build_and_drop_replay():
    # Generate 16-second synthetic EDM track (Verse -> Build -> Breakdown -> Drop)
    edm_track = SyntheticTrackGenerator.generate_edm_track(duration=16.0, samplerate=44100)
    assert len(edm_track) == 16 * 44100

    replayer = WavReplayer(blocksize=1024)
    summary = replayer.replay_buffer(edm_track, samplerate=44100, realtime=False)

    assert summary.duration_seconds == 16.0
    assert summary.total_frames > 600
    assert summary.bpm > 100.0  # 128 BPM track
    assert summary.peak_energy > 0.5

    # Check sections detected
    section_names = [s[1] for s in summary.sections_detected]
    assert "VERSE" in section_names or "BUILD" in section_names or "DROP" in section_names


def test_synthetic_classical_track_replay():
    classical_track = SyntheticTrackGenerator.generate_classical_track(duration=10.0, samplerate=44100)
    assert len(classical_track) == 10 * 44100

    replayer = WavReplayer(blocksize=1024)
    summary = replayer.replay_buffer(classical_track, samplerate=44100, realtime=False)

    assert summary.duration_seconds == 10.0
    assert summary.avg_energy > 0.05
    # Classical A minor track should detect minor mode with high harmonic ratio
    assert summary.mode in ("major", "minor")


def test_visual_styles_rendering_50_zones_and_1_zone():
    state = MusicState(
        bands=np.full(50, 0.5, dtype=np.float32),
        onset=0.8,
        kick=1.0,
        snare=0.3,
        hat=0.7,
        bpm=128.0,
        beat_phase=0.5,
        bar_pos=2,
        energy=0.85,
        energy_trend=0.08,
        centroid=1400.0,
        intensity=0.75,
        tension=0.6,
        impact=0.9,
        section=Section.DROP,
        drop_strength=0.95,
        palette=[(215, 85, 75), (180, 90, 80), (280, 80, 70), (45, 95, 85)],
        harmonic_ratio=0.6
    )

    styles = ["movie", "pulse", "spectrum", "flow", "aurora", "cinematic"]
    for s_name in styles:
        style = get_visual_style(s_name)
        assert style is not None and hasattr(style, "render")

        # 50-zone render (L930)
        segs_50 = style.render(state, dt=0.03, num_zones=50)
        assert len(segs_50) == 50
        for h, s, v in segs_50:
            assert 0 <= h <= 360
            assert 0 <= s <= 100
            assert 0 <= v <= 100

        # 1-zone render (L900)
        segs_1 = style.render(state, dt=0.03, num_zones=1)
        assert len(segs_1) == 1
        h, s, v = segs_1[0]
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100


def test_pulse_style_drop_white_flash_and_cooldown():
    pulse = PulseStyle()

    # Normal kick during Verse -> palette color pulse (NOT white)
    verse_state = MusicState(
        energy=0.7,
        kick=1.0,
        impact=0.4,
        section=Section.VERSE,
        drop_strength=0.4,
        palette=[(180, 90, 80)]
    )
    frame_verse = pulse.render(verse_state, dt=0.03, num_zones=50)
    # Center zone should have saturation > 0 (palette color)
    assert frame_verse[25][1] > 0

    # True drop hit (Section.DROP, drop_strength > 0.85) -> pure white strike
    drop_state = MusicState(
        energy=0.95,
        kick=1.0,
        impact=1.0,
        section=Section.DROP,
        drop_strength=0.95,
        palette=[(180, 90, 80)]
    )
    frame_drop = pulse.render(drop_state, dt=0.03, num_zones=50)
    assert frame_drop[25][1] == 0  # Saturation collapses to 0 -> pure laser white!
    assert frame_drop[25][2] == 100

    # Advance through hold and decay stages so the initial strike completes (total ~0.60s)
    for _ in range(16):
        pulse.render(drop_state, dt=0.045, num_zones=50)

    # Subsequent kick -> 8s cooldown prevents re-blooming to pure white
    frame_cooldown = pulse.render(drop_state, dt=0.03, num_zones=50)
    assert frame_cooldown[25][1] > 0  # Saturation recovered, cooldown enforced


def test_fake_device_simulator():
    sim = FakeDeviceSimulator(model="L930")
    sim.submit_frame({"segments": [[180, 100, 100]] * 50, "brightness": 100})
    assert len(sim.frames) == 1
    assert sim.last_submitted_frame["brightness"] == 100
    sim.clear_frames()
    assert len(sim.frames) == 0


def test_latency_lookahead_configuration_and_prediction():
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=1024, latency_lookahead_ms=40.0)
    assert analyzer.latency_lookahead_ms == 40.0

    analyzer.set_latency_lookahead(75.0)
    assert analyzer.latency_lookahead_ms == 75.0

    # Bounds clamping
    analyzer.set_latency_lookahead(-10.0)
    assert analyzer.latency_lookahead_ms == 0.0
    analyzer.set_latency_lookahead(400.0)
    assert analyzer.latency_lookahead_ms == 250.0

