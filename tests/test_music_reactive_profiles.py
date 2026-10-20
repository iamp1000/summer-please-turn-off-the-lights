from __future__ import annotations
import math
import time
import numpy as np
import pytest
from unittest.mock import MagicMock

from src.music_reactive import MusicReactive
from src.music_reactive_l930 import MusicReactiveL930, NUM_SEGMENTS
from src.audio_dsp import MusicState, Section


class MockDiagnostics:
    rtt_ms = 25.0


class MockController:
    def __init__(self):
        self.diagnostics = MockDiagnostics()
        self.submitted_frames = []
        self.cleared_count = 0

    def submit_frame(self, frame):
        self.submitted_frames.append(frame)

    def clear_frames(self):
        self.cleared_count += 1


def generate_tone(freq: float, duration_samples: int = 1024, sr: int = 44100, amp: float = 0.5) -> np.ndarray:
    t = np.arange(duration_samples) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_l900_silence_strict_off():
    ctrl = MockController()
    app_state = {"brightness": 100}
    engine = MusicReactive(controller=ctrl, loop_runner=None, app_state=app_state, blocksize=1024)

    # Feed silence repeatedly
    silence = np.zeros(1024, dtype=np.float32)
    for _ in range(15):
        engine._process_samples(silence)

    assert engine._target_state == (0, 0, 0)
    assert len(ctrl.submitted_frames) > 0
    last_frame = ctrl.submitted_frames[-1]
    assert last_frame["b"] == 0


def test_l900_edm_drop_white_flash_and_color_cascade():
    ctrl = MockController()
    app_state = {"brightness": 100}
    engine = MusicReactive(controller=ctrl, loop_runner=None, app_state=app_state, blocksize=1024)
    engine.set_mode("edm_drop")

    # Prime calibrator with moderate baseline
    for _ in range(25):
        engine._process_samples(generate_tone(440.0, amp=0.15))

    # Massive 60Hz sub-bass transient (drop strike)
    drop_kick = generate_tone(60.0, amp=0.95)
    engine._process_samples(drop_kick)

    assert engine._white_punch > 60.0
    b, h, s = engine._target_state
    assert b >= 80
    # Saturation collapses to near 0 for pure white flash on extreme drop
    assert s <= 20

    # Let drop release over a few ticks (tempo decay)
    for _ in range(8):
        engine._process_samples(generate_tone(440.0, amp=0.20))

    # Saturation should recover as drop cascades down
    b_decay, h_decay, s_decay = engine._target_state
    assert s_decay > 70


def test_l900_classical_acoustic_mode():
    ctrl = MockController()
    app_state = {"brightness": 100}
    engine = MusicReactive(controller=ctrl, loop_runner=None, app_state=app_state, blocksize=1024)
    engine.set_mode("classical")

    # Prime AGC
    for _ in range(25):
        engine._process_samples(generate_tone(440.0, amp=0.10))

    # Soft passage (e.g. violin / acoustic guitar solo at 800Hz, low amplitude)
    soft_sample = generate_tone(800.0, amp=0.04)
    engine._process_samples(soft_sample)

    b, h, s = engine._target_state
    # Wide dynamic range expansion should keep soft classical passages gently illuminated
    assert b > 0
    # Gentle non-saturated concert hall ambiance
    assert s <= 90


def test_l900_movie_dialogue_and_rumble():
    ctrl = MockController()
    app_state = {"brightness": 100}
    engine = MusicReactive(controller=ctrl, loop_runner=None, app_state=app_state, blocksize=1024)
    engine.set_mode("movie")

    # Prime AGC
    for _ in range(25):
        engine._process_samples(generate_tone(500.0, amp=0.10))

    # 1. Dialogue formant frequency (1000 Hz, speech level)
    speech_sample = generate_tone(1000.0, amp=0.08)
    engine._process_samples(speech_sample)
    b, h, s = engine._target_state
    assert b >= 8
    # 2700K warm tungsten dialogue hue
    assert h == 26
    assert s == 75

    # 2. Dramatic sub-bass explosion rumble (35 Hz burst)
    explosion_sample = generate_tone(35.0, amp=0.90)
    engine._process_samples(explosion_sample)
    b_exp, h_exp, s_exp = engine._target_state
    assert b_exp > b
    # Fiery action cinematic orange/crimson
    assert h_exp == 16
    assert s_exp == 95


def test_l930_silence_strict_off():
    ctrl = MockController()
    app_state = {"brightness": 100}
    engine = MusicReactiveL930(controller=ctrl, loop_runner=None, app_state=app_state, blocksize=1024)

    silence = np.zeros(1024, dtype=np.float32)
    for _ in range(20):
        engine._process(silence, rms=0.0)

    assert engine._target_segs == [[0, 0, 0]] * NUM_SEGMENTS
    assert len(ctrl.submitted_frames) > 0
    last_frame = ctrl.submitted_frames[-1]
    assert last_frame["brightness"] == 0
    assert all(seg == [0, 0, 0] for seg in last_frame["segments"])


def test_l930_edm_drop_center_white_shockwave():
    ctrl = MockController()
    app_state = {"brightness": 100}
    engine = MusicReactiveL930(controller=ctrl, loop_runner=None, app_state=app_state, blocksize=1024)
    engine.set_mode("edm_drop")

    # Prime baseline
    for _ in range(25):
        sample = generate_tone(440.0, amp=0.15)
        engine._process(sample, rms=float(np.sqrt(np.mean(sample ** 2))))

    # Extreme sub-bass drop strike (50 Hz burst)
    drop_sample = generate_tone(50.0, amp=0.95)
    rms = float(np.sqrt(np.mean(drop_sample ** 2)))
    engine._process(drop_sample, rms=rms)

    assert engine._white_punch > 60.0
    # Verify center zones (e.g. index 24, 25) strike pure white (sat = 0)
    center_seg = engine._target_segs[25]
    assert center_seg[1] == 0  # Saturation = 0 -> PURE WHITE
    assert center_seg[2] == 100  # Brightness = 100%


def test_l930_classical_orchestral_stage_layout():
    ctrl = MockController()
    app_state = {"brightness": 100}
    engine = MusicReactiveL930(controller=ctrl, loop_runner=None, app_state=app_state, blocksize=1024)
    engine.set_mode("classical")

    # Mixed orchestra audio (bass + mid + treble)
    t = np.arange(1024) / 44100
    orchestra = 0.3 * np.sin(2 * np.pi * 100 * t) + 0.3 * np.sin(2 * np.pi * 800 * t) + 0.2 * np.sin(2 * np.pi * 4000 * t)
    orchestra = orchestra.astype(np.float32)
    rms = float(np.sqrt(np.mean(orchestra ** 2)))

    for _ in range(5):
        engine._process(orchestra, rms=rms)

    segs = engine._target_segs
    # Stage Left (zones 0-14): Cellos/Bass -> Mahogany / warm amber (24° - 38°)
    left_seg = segs[5]
    if left_seg[2] > 0:
        assert 24 <= left_seg[0] <= 40

    # Center Stage (zones 15-34): Piano / Woodwinds -> Concert gold (45° - 85°)
    center_seg = segs[25]
    if center_seg[2] > 0:
        assert 45 <= center_seg[0] <= 85

    # Stage Right (zones 35-49): Violins / Flutes -> Concert sapphire/cyan (180° - 220°)
    right_seg = segs[42]
    if right_seg[2] > 0:
        assert 180 <= right_seg[0] <= 220

    # Individual IC addressability: zones have distinct colors
    assert left_seg[0] != right_seg[0]


def test_l930_movie_dialogue_center_bias():
    ctrl = MockController()
    app_state = {"brightness": 100}
    engine = MusicReactiveL930(controller=ctrl, loop_runner=None, app_state=app_state, blocksize=1024)
    engine.set_mode("movie")

    speech = generate_tone(1000.0, amp=0.12)
    rms = float(np.sqrt(np.mean(speech ** 2)))

    for _ in range(5):
        engine._process(speech, rms=rms)

    segs = engine._target_segs
    # Center zones (18-31) hold dialogue 2700K tungsten bias
    center_seg = segs[25]
    assert center_seg[0] == 26
    assert center_seg[1] == 75
    assert center_seg[2] > 0


def test_stop_purges_and_turns_off():
    ctrl_l900 = MockController()
    engine_l900 = MusicReactive(controller=ctrl_l900, loop_runner=None, app_state={"brightness": 100})
    engine_l900.stop()
    assert ctrl_l900.cleared_count >= 1
    assert ctrl_l900.submitted_frames[-1]["b"] == 0

    ctrl_l930 = MockController()
    engine_l930 = MusicReactiveL930(controller=ctrl_l930, loop_runner=None, app_state={"brightness": 100})
    engine_l930.stop()
    assert ctrl_l930.cleared_count >= 1
    assert ctrl_l930.submitted_frames[-1]["brightness"] == 0
    assert all(s == [0, 0, 0] for s in ctrl_l930.submitted_frames[-1]["segments"])


def test_l930_music_transition_matches_aimd_rate_cap():
    ctrl = MockController()
    ctrl._max_updates_per_s = 8.0
    ctrl.music_transition_ms = 120

    class FakeFrameSender:
        max_updates_per_s = 8.0
        _aimd_rate_cap = 1.0  # Simulate a slow device forced to 1 FPS.

        def set_send_budget(self, max_updates_per_s):
            self.max_updates_per_s = max_updates_per_s

    ctrl.frame_sender = FakeFrameSender()
    engine = MusicReactiveL930(controller=ctrl, loop_runner=None, app_state={"brightness": 100})
    state = MusicState(
        bands=np.linspace(0.1, 1.0, NUM_SEGMENTS, dtype=np.float32),
        energy=0.55,
        intensity=0.6,
        section=Section.VERSE,
        silent=False,
    )

    engine._render_from_music_state(state, dt=1.0 / 60.0)
    assert ctrl.submitted_frames[-1]["transition"] == 980

    # At the nominal 8 FPS cap, the transition should remain near one frame.
    ctrl.frame_sender._aimd_rate_cap = 8.0
    engine._render_from_music_state(state, dt=1.0 / 60.0)
    assert 120 <= ctrl.submitted_frames[-1]["transition"] <= 130
