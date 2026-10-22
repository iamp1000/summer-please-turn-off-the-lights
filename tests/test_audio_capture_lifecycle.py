from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from src.audio_dsp import AudioCaptureCoordinator, MusicState
from src.music_reactive import MusicReactive
from src.music_reactive_l930 import MusicReactiveL930


def _join_worker(coordinator: AudioCaptureCoordinator):
    thread = coordinator._thread
    if thread is not None:
        thread.join(timeout=1.5)
        assert not thread.is_alive(), "capture worker did not terminate"


def test_audio_coordinator_reports_missing_input_and_clears_running(monkeypatch):
    monkeypatch.setattr("src.music_reactive.get_audio_input_source", lambda *args, **kwargs: None)
    coordinator = AudioCaptureCoordinator(samplerate=8000, blocksize=128)

    coordinator.start()
    _join_worker(coordinator)

    assert coordinator.is_running() is False
    assert coordinator.status == "error"
    assert "No audio input source" in (coordinator.last_error or "")


def test_audio_coordinator_reports_recorder_exception(monkeypatch):
    class BrokenRecorder:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def record(self, numframes):
            raise RuntimeError("loopback disconnected")

    class FakeMic:
        name = "test loopback"
        id = "fake-loopback"

        def recorder(self, **kwargs):
            return BrokenRecorder()

    monkeypatch.setattr(
        "src.music_reactive.get_audio_input_source",
        lambda *args, **kwargs: FakeMic(),
    )
    monkeypatch.setattr(
        "src.master_volume.get_master_volume_probe",
        lambda: SimpleNamespace(compensate_samples=lambda samples: samples),
    )
    coordinator = AudioCaptureCoordinator(samplerate=8000, blocksize=128)

    coordinator.start()
    _join_worker(coordinator)

    assert coordinator.is_running() is False
    assert coordinator.status == "error"
    assert "Audio capture failed" in (coordinator.last_error or "")
    assert "loopback disconnected" in (coordinator.last_error or "")


class _FakeRecorder:
    def __init__(self, rms):
        self.rms = rms

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def record(self, numframes):
        import numpy as np
        return np.full((numframes, 1), self.rms, dtype=np.float32)


class _FakeLoopback:
    isloopback = True

    def __init__(self, name, rms):
        self.name = name
        self.id = name
        self.rms = rms

    def recorder(self, **kwargs):
        return _FakeRecorder(self.rms)


def test_audio_source_falls_back_when_selected_loopback_is_silent(monkeypatch):
    """A silent selected virtual input must not mask audio on another loopback."""
    import src.music_reactive as music_module

    silent_input = _FakeLoopback("Voicemeeter Input", 0.0)
    active_output = _FakeLoopback("Headphones loopback", 0.12)
    monkeypatch.setattr(music_module.sc, "all_microphones", lambda include_loopback=True: [
        silent_input, active_output
    ])
    monkeypatch.setattr(
        music_module.sc, "default_speaker",
        lambda: (_ for _ in ()).throw(RuntimeError("no default speaker")),
    )
    monkeypatch.setattr(music_module.sc, "get_microphone", lambda *args, **kwargs: None)

    selected = music_module.get_audio_input_source(
        samplerate=8000, blocksize=128, preferred_name="Voicemeeter Input"
    )
    assert selected is active_output


class FakeCoordinator:
    def __init__(self, status="active", last_error=None):
        self.status = status
        self.last_error = last_error
        self.new_frame_event = threading.Event()
        self.subscribers = set()
        now = time.perf_counter()
        self.state = (MusicState(), {"t_audio_recv": now, "t_analysis_done": now})

    def start(self):
        return None

    def register_subscriber(self, sub):
        self.subscribers.add(sub)

    def unregister_subscriber(self, sub):
        self.subscribers.discard(sub)

    def get_latest_state(self):
        return self.state


class FakeController:
    def __init__(self):
        self.frames = []
        self.clear_count = 0

    def submit_frame(self, frame):
        self.frames.append(frame)

    def clear_frames(self):
        self.clear_count += 1
        self.frames.clear()


@pytest.mark.parametrize("engine_cls", [MusicReactive, MusicReactiveL930])
def test_music_worker_stop_joins_before_restart(engine_cls):
    controller = FakeController()
    engine = engine_cls(controller=controller, loop_runner=None, app_state={"brightness": 50})
    engine.set_coordinator(FakeCoordinator())
    # Isolate lifecycle behavior from DSP/render details.
    engine._render_from_music_state = lambda *args, **kwargs: None

    engine.start()
    first = engine._thread
    assert first is not None and first.is_alive()

    engine.stop()
    assert first.is_alive() is False

    engine.start()
    second = engine._thread
    assert second is not None and second is not first and second.is_alive()

    engine.stop()
    assert second.is_alive() is False


@pytest.mark.parametrize("engine_cls", [MusicReactive, MusicReactiveL930])
def test_music_worker_exposes_shared_capture_error(engine_cls):
    state = {"brightness": 50, "active_label": "Audio Reactive"}
    controller = FakeController()
    engine = engine_cls(controller=controller, loop_runner=None, app_state=state)
    engine.set_coordinator(FakeCoordinator(status="error", last_error="No audio input source found"))

    engine.start()
    thread = engine._thread
    if thread is not None:
        thread.join(timeout=1.5)
        assert not thread.is_alive()

    assert engine.is_running() is False
    assert state["active_label"] == "Audio Error"
    assert "No audio input source found" in state["last_error"]


@pytest.mark.parametrize(
    ("engine_cls", "source_patch", "label"),
    [
        (MusicReactive, "src.music_reactive.get_audio_input_source", "Audio Reactive"),
        (MusicReactiveL930, "src.music_reactive_l930.get_audio_input_source", "Audio Spectrum (IC)"),
    ],
)
def test_standalone_music_worker_reports_missing_audio_device(monkeypatch, engine_cls, source_patch, label):
    monkeypatch.setattr(source_patch, lambda *args, **kwargs: None)
    state = {"brightness": 50, "active_label": label}
    controller = FakeController()
    engine = engine_cls(controller=controller, loop_runner=None, app_state=state)

    engine.start()
    thread = engine._thread
    assert thread is not None
    thread.join(timeout=1.5)
    assert not thread.is_alive()

    assert engine.is_running() is False
    assert state["active_label"] == "Audio Error"
    assert state["last_error"]
    assert "audio input" in state["last_error"].lower()
    assert controller.frames, "failure should publish a final black frame"
    assert controller.frames[-1].get("b", controller.frames[-1].get("brightness")) == 0


def test_audio_coordinator_can_retry_after_discovery_failure(monkeypatch):
    # A failed run must leave no phantom "running" state or live thread that blocks retry.
    monkeypatch.setattr("src.music_reactive.get_audio_input_source", lambda *args, **kwargs: None)
    coordinator = AudioCaptureCoordinator(samplerate=8000, blocksize=128)

    coordinator.start()
    first = coordinator._thread
    _join_worker(coordinator)
    assert coordinator.status == "error"
    assert coordinator.is_running() is False

    coordinator.start()
    second = coordinator._thread
    _join_worker(coordinator)

    assert second is not None and second is not first
    assert coordinator.status == "error"
    assert coordinator.is_running() is False
