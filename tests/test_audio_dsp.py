from __future__ import annotations
import numpy as np
import pytest
from src.audio_dsp import (
    SpectralFluxOnsetDetector,
    CombAutocorrTempoTracker,
    DynamicSongCalibrator,
    DynamicAudioCalibrator,
    BPMTracker,
    MusicAnalyzer,
    Section,
)
from src.audio_replay import SyntheticTrackGenerator, WavReplayer

def test_spectral_flux_scale_invariance():
    detector = SpectralFluxOnsetDetector(num_bins=10, threshold_mult=1.3)

    # 1. Warm-up running mean with quiet baseline
    for i in range(20):
        detector.process(np.full(10, 0.05, dtype=np.float32), now=i * 0.02, dt=0.02)

    # 2. Sudden burst at standard gain
    _, is_onset_std = detector.process(np.full(10, 0.60, dtype=np.float32), now=0.50, dt=0.02)
    assert is_onset_std

    # Reset with 4x gain (volume boosted)
    detector2 = SpectralFluxOnsetDetector(num_bins=10, threshold_mult=1.3)
    for i in range(20):
        detector2.process(np.full(10, 0.20, dtype=np.float32), now=i * 0.02, dt=0.02)

    # Relative burst at 4x gain
    _, is_onset_boosted = detector2.process(np.full(10, 2.40, dtype=np.float32), now=0.50, dt=0.02)
    assert is_onset_boosted, "Adaptive whitening must detect onsets scale-invariantly"


def test_comb_tempo_tracker_and_pll():
    tracker = CombAutocorrTempoTracker(min_bpm=70.0, max_bpm=180.0)

    # Simulate 128 BPM clicks (interval = 60 / 128 = 0.46875s)
    bpm_target = 128.0
    interval = 60.0 / bpm_target

    now = 0.0
    dt = 0.020
    next_click = 0.0

    while now < 6.0:
        is_click = False
        flux = 0.05
        if abs(now - next_click) < dt / 2.0 or now >= next_click:
            is_click = True
            flux = 2.5
            next_click += interval

        tracker.update(flux, is_click, now=now, dt=dt)
        now += dt

    # Assert tempo is within ±2 BPM of 128 BPM
    assert abs(tracker.estimated_bpm - bpm_target) <= 2.0
    assert tracker.bpm_confidence > 0.40

    # Test PLL phase continuity and bounds
    phase = tracker.get_phase(lookahead_sec=0.0)
    assert 0.0 <= phase <= 1.0


def test_dynamic_calibrator_silence_gate():
    calib = DynamicSongCalibrator(sensitivity=1.0)

    # Feed quiet line noise (below -54 dBFS gate)
    now = 0.0
    for _ in range(30):
        energy, trend, drop, is_silent = calib.update(rms=0.0005, kick=0.0, now=now, dt=0.025)
        now += 0.025

    assert is_silent, "Absolute silence gate must engage below -54 dBFS"
    assert energy == 0.0
    assert drop == 0.0

    # Feed loud audio burst
    for _ in range(40):
        energy, trend, drop, is_silent = calib.update(rms=0.15, kick=0.20, now=now, dt=0.025)
        now += 0.025

    assert not is_silent
    assert energy > 0.40


def test_synthetic_signals_suite():
    # 1. 128 BPM Click Track
    clicks = SyntheticTrackGenerator.generate_click_track(bpm=128.0, duration=6.0)
    assert len(clicks) == 6 * 44100

    replayer = WavReplayer(blocksize=1024)
    summary_click = replayer.replay_buffer(clicks, samplerate=44100, realtime=False)
    assert abs(summary_click.bpm - 128.0) <= 2.0

    # 2. Pure Digital Silence Handling
    silence = SyntheticTrackGenerator.generate_silence(duration=2.5)
    summary_silence = replayer.replay_buffer(silence, samplerate=44100, realtime=False)
    assert summary_silence.avg_energy < 0.02
    assert summary_silence.sections_detected[-1][1] == "SILENT"

    # 3. Half-Time Pattern (140 BPM)
    half_time = SyntheticTrackGenerator.generate_half_time_pattern(bpm=140.0, duration=6.0)
    summary_half = replayer.replay_buffer(half_time, samplerate=44100, realtime=False)
    assert summary_half.total_frames > 200

    # 4. Sine Sweep
    sweep = SyntheticTrackGenerator.generate_sine_sweep(f_start=40.0, f_end=4000.0, duration=3.0)
    assert len(sweep) == 3 * 44100

    # 5. White Noise Bursts
    noise = SyntheticTrackGenerator.generate_white_noise_bursts(duration=3.0, burst_interval=0.5)
    assert len(noise) == 3 * 44100
