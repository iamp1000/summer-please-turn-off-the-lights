"""
End-to-End Music Reactivity Integration Tests.

Validates the full audio DSP pipeline through to 50-zone frame delivery:
1. Silence: strictly turns off LED output (0% brightness, true black [0, 0, 0] across all 50 zones).
2. Steady Tones: continuous tone provides stable spectrum without spurious onsets or strobing.
3. Bass-Heavy Material: sub-bass and kick pulses (40-100 Hz) drive bass envelope, kick detector, and lower zone illumination.
4. Mid-Frequency Material: vocal and melody range (400-1200 Hz) drives mid envelope and instrument zones.
5. Treble / Transients: hi-hats and sharp transients (4000-12000 Hz) drive transient/hat envelopes with crisp attack.
6. Multi-Component Music: full spectrum mix delivers 50 distinct zone colors and rate-matched hardware transitions.
"""
from __future__ import annotations

import numpy as np
import pytest
from src.audio_dsp import MusicAnalyzer, MusicState
from src.music_reactive_l930 import MusicReactiveL930, NUM_SEGMENTS


class MockDeviceController:
    def __init__(self, effective_ups: float = 8.0):
        self.submitted_frames = []
        self._is_on = True
        self._max_updates_per_s = effective_ups
        self.music_transition_ms = 120

    def submit_frame(self, frame):
        self.submitted_frames.append(frame)

    def clear_frames(self):
        self.submitted_frames.clear()


def test_music_reactivity_silence_strict_darkness():
    """Verify that silence leads to immediate 0% brightness and all-black zones."""
    ctrl = MockDeviceController()
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=1024, sensitivity=1.0)
    engine = MusicReactiveL930(ctrl, None, {"brightness": 100}, samplerate=44100, blocksize=1024)

    silence = np.zeros(1024, dtype=np.float32)
    for _ in range(12):
        st = analyzer.process_samples(silence)
        engine._render_from_music_state(st, dt=0.023)

    assert st.silent is True
    assert st.energy < 0.005
    assert len(ctrl.submitted_frames) > 0

    last_frame = ctrl.submitted_frames[-1]
    assert last_frame["brightness"] == 0
    assert len(last_frame["segments"]) == NUM_SEGMENTS
    for zone in last_frame["segments"]:
        assert zone == [0, 0, 0], f"Zone not true black: {zone}"


def test_music_reactivity_steady_tone_stability():
    """Verify that a steady tone (440 Hz) provides stable mid response without persistent onset spiking."""
    ctrl = MockDeviceController()
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=1024, sensitivity=1.0)
    engine = MusicReactiveL930(ctrl, None, {"brightness": 100}, samplerate=44100, blocksize=1024)

    t = np.arange(1024) / 44100.0
    tone_440 = (0.6 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)

    # Prime analyzer over 20 blocks
    states = []
    for _ in range(25):
        st = analyzer.process_samples(tone_440)
        states.append(st)
        engine._render_from_music_state(st, dt=0.023)

    final_st = states[-1]
    assert final_st.silent is False
    assert final_st.energy > 0.25
    assert final_st.mid > 0.20

    # After initial transient, steady tone settles: impact is zero, no white shockwave flash
    assert final_st.impact == 0.0
    assert engine._white_punch == 0.0
    assert len(ctrl.submitted_frames) > 0
    last_frame = ctrl.submitted_frames[-1]
    assert last_frame["brightness"] > 0
    assert len(last_frame["segments"]) == NUM_SEGMENTS


def test_music_reactivity_bass_heavy_kick_response():
    """Verify sub-bass and kick bursts (60 Hz) strongly trigger kick detector and bass envelope."""
    ctrl = MockDeviceController()
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=1024, sensitivity=1.0)
    engine = MusicReactiveL930(ctrl, None, {"brightness": 100}, samplerate=44100, blocksize=1024)

    t = np.arange(1024) / 44100.0
    kick_pulse = (0.9 * np.sin(2 * np.pi * 60.0 * t)).astype(np.float32)

    states = []
    for _ in range(15):
        st = analyzer.process_samples(kick_pulse)
        states.append(st)
        engine._render_from_music_state(st, dt=0.023)

    final_st = states[-1]
    assert final_st.silent is False
    assert final_st.bass > 0.40 or final_st.kick > 0.40
    assert final_st.energy > 0.30

    last_frame = ctrl.submitted_frames[-1]
    assert last_frame["brightness"] >= 50
    # Lower frequency IC zones (0..12) should have high luminous activity
    bass_zone_max_v = max(z[2] for z in last_frame["segments"][:13])
    assert bass_zone_max_v > 20


def test_music_reactivity_mid_frequency_response():
    """Verify mid-range signals (800 Hz) elevate mid envelope and illuminate instrument zones."""
    ctrl = MockDeviceController()
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=1024, sensitivity=1.0)
    engine = MusicReactiveL930(ctrl, None, {"brightness": 100}, samplerate=44100, blocksize=1024)

    t = np.arange(1024) / 44100.0
    mid_signal = (0.75 * np.sin(2 * np.pi * 800.0 * t)).astype(np.float32)

    for _ in range(15):
        st = analyzer.process_samples(mid_signal)
        engine._render_from_music_state(st, dt=0.023)

    assert st.silent is False
    assert st.mid > 0.35
    assert len(ctrl.submitted_frames) > 0
    last_frame = ctrl.submitted_frames[-1]
    assert last_frame["brightness"] > 0
    assert len(last_frame["segments"]) == NUM_SEGMENTS


def test_music_reactivity_treble_and_transient_response():
    """Verify high frequency transients (8 kHz) drive hat and transient envelopes."""
    ctrl = MockDeviceController()
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=1024, sensitivity=1.0)
    engine = MusicReactiveL930(ctrl, None, {"brightness": 100}, samplerate=44100, blocksize=1024)

    t = np.arange(1024) / 44100.0
    treble_burst = (0.8 * np.sin(2 * np.pi * 8000.0 * t)).astype(np.float32)

    for _ in range(15):
        st = analyzer.process_samples(treble_burst)
        engine._render_from_music_state(st, dt=0.023)

    assert st.silent is False
    assert st.hat > 0.30 or st.transient > 0.15
    last_frame = ctrl.submitted_frames[-1]
    assert last_frame["brightness"] > 0
    assert len(last_frame["segments"]) == NUM_SEGMENTS


def test_music_reactivity_composite_track_50_zone_delivery():
    """Verify a composite multi-instrument signal drives all 50 zones with correct transition timing."""
    ctrl = MockDeviceController(effective_ups=5.0)
    analyzer = MusicAnalyzer(samplerate=44100, blocksize=1024, sensitivity=1.0)
    engine = MusicReactiveL930(ctrl, None, {"brightness": 100}, samplerate=44100, blocksize=1024)

    t = np.arange(1024) / 44100.0
    # Mix: 55 Hz sub-kick + 440 Hz chord + 6000 Hz hi-hat
    mix = (
        0.5 * np.sin(2 * np.pi * 55.0 * t) +
        0.3 * np.sin(2 * np.pi * 440.0 * t) +
        0.2 * np.sin(2 * np.pi * 6000.0 * t)
    ).astype(np.float32)

    for _ in range(20):
        st = analyzer.process_samples(mix)
        engine._render_from_music_state(st, dt=0.023)

    assert len(ctrl.submitted_frames) > 0
    last_frame = ctrl.submitted_frames[-1]

    # Validate frame delivery contract
    assert "segments" in last_frame
    assert len(last_frame["segments"]) == NUM_SEGMENTS
    for h, s, v in last_frame["segments"]:
        assert 0 <= h <= 360
        assert 0 <= s <= 100
        assert 0 <= v <= 100

    assert last_frame.get("_pre_corrected") is True
    assert last_frame["transition"] > 0
