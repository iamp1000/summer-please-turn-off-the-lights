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


def test_onset_pre_update_statistics_and_sensitivity():
    """
    Verifies that onset strength uses pre-update statistics, preventing self-masking,
    and accurately distinguishes true transient bursts from steady-state loudness without false triggers.
    """
    detector = SpectralFluxOnsetDetector(num_bins=20, threshold_mult=1.4)

    # 1. Steady background tone should not trigger onsets once adapted
    steady_spectrum = np.full(20, 0.40, dtype=np.float32)
    for i in range(40):
        flux, is_onset = detector.process(steady_spectrum, now=i * 0.02, dt=0.02)

    # After adaptation, steady state must not be flagged as onset
    assert not is_onset
    assert detector.normalized_onset < 0.15, "Steady tone should have near-zero normalized onset"

    # 2. Sudden sharp transient burst (3x jump in high bands)
    transient_spectrum = steady_spectrum.copy()
    transient_spectrum[10:] = 1.80
    flux, is_onset = detector.process(transient_spectrum, now=40 * 0.02, dt=0.02)

    assert is_onset, "Sharp transient burst must reliably trigger onset"
    assert detector.normalized_onset > 0.40, "Normalized onset must respond with strong positive value"


def test_subband_absolute_calibration():
    """
    Verifies that bass and mid signals represent calibrated absolute physical sub-band energies,
    rather than purely relative ratios of the frame's peak band.
    """
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=512)

    # Synthetic low-frequency bass tone (60 Hz sine wave)
    t = np.linspace(0, 512 / 44100.0, 512, endpoint=False)
    bass_samples = (0.50 * np.sin(2.0 * np.pi * 60.0 * t)).astype(np.float32)

    # Process blocks with continuous phase to settle filter and envelope state
    for i in range(35):
        t_block = (i * 512 + np.arange(512)) / 44100.0
        bass_samples = (0.50 * np.sin(2.0 * np.pi * 60.0 * t_block)).astype(np.float32)
        state = analyzer.process_samples(bass_samples, now=i * (512 / 44100.0))

    assert state.bass > 0.40, f"Expected strong bass signal for 60Hz tone, got {state.bass}"
    assert state.mid < 0.20, f"Expected low mid signal for pure 60Hz bass tone, got {state.mid}"

    # Synthetic mid-frequency tone (500 Hz vocal/instrument tone) with continuous phase
    for i in range(35):
        t_block = ((35 + i) * 512 + np.arange(512)) / 44100.0
        mid_samples = (0.50 * np.sin(2.0 * np.pi * 500.0 * t_block)).astype(np.float32)
        state = analyzer.process_samples(mid_samples, now=(35 + i) * (512 / 44100.0))

    assert state.mid > 0.30, f"Expected strong mid signal for 500Hz tone, got {state.mid}"
    assert state.bass < 0.25, f"Expected lower bass signal for 500Hz tone, got {state.bass}"


def test_music_state_fields_contracts_and_transient_dynamics():
    """
    Explicitly tests MusicState field contracts asserting:
    - raw_flux, bass, mid, transient, and onset are populated and bounded.
    - Zero/silence gating completely zeroes onset, transient, and energy.
    - Sharp percussive bursts elevate raw_flux, transient, and onset.
    - Sustained tones preserve energy while onset decays to prevent continuous false triggering.
    """
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=512)

    # 1. Digital silence
    silence = np.zeros(512, dtype=np.float32)
    state = None
    for i in range(25):
        state = analyzer.process_samples(silence, now=i * (512 / 44100.0))

    assert state is not None
    assert state.silent is True
    assert state.energy == 0.0
    assert state.onset == 0.0
    assert state.transient == 0.0
    assert state.raw_flux == 0.0
    assert 0.0 <= state.bass <= 1.0
    assert 0.0 <= state.mid <= 1.0

    # 2. Sudden sharp transient attack (percussive burst)
    rng = np.random.default_rng(42)
    burst = (rng.uniform(-0.8, 0.8, 512)).astype(np.float32)
    state_burst = analyzer.process_samples(burst, now=25 * (512 / 44100.0))

    assert not state_burst.silent
    assert state_burst.raw_flux > 0.0
    assert state_burst.transient > 0.15
    assert state_burst.onset > 0.15

    # 3. Sustained tone adaptation (onset decays, energy stays active)
    for i in range(26, 65):
        t_block = (i * 512 + np.arange(512)) / 44100.0
        tone = (0.50 * np.sin(2.0 * np.pi * 440.0 * t_block)).astype(np.float32)
        state_sustained = analyzer.process_samples(tone, now=i * (512 / 44100.0))

    assert state_sustained.energy > 0.30, "Sustained tone must maintain calibrated energy"
    assert state_sustained.onset < 0.20, "Normalized onset must decay during sustained steady tones"

    # 4. Sudden high-frequency snare/hat transient over sustained background
    spike = tone.copy()
    spike += (rng.uniform(-0.9, 0.9, 512)).astype(np.float32)
    state_spike = analyzer.process_samples(spike, now=65 * (512 / 44100.0))

    assert state_spike.raw_flux > state_sustained.raw_flux
    assert state_spike.onset > 0.30, "Transient spike on top of sustained tone must re-trigger onset"
    assert state_spike.transient > state_sustained.transient

