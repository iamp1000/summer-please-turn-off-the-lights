from __future__ import annotations

import time
from types import SimpleNamespace

from src.screen_sync import SCREEN_PROFILES, ScreenSync


class FakeScreenController:
    def __init__(self, aimd_rate=1.0, configured_rate=5.0):
        self.frames = []
        self._max_updates_per_s = configured_rate
        self.music_transition_ms = 120
        self.movie_transition_ms = 800
        self.frame_sender = SimpleNamespace(
            max_updates_per_s=configured_rate,
            _aimd_rate_cap=aimd_rate,
        )

    def submit_frame(self, frame):
        self.frames.append(frame)

    def clear_frames(self):
        self.frames.clear()


def _hue_delta(a, b):
    return abs((int(a) - int(b) + 180) % 360 - 180)


def _dispatch_l930(sync, hue, value=70, saturation=90):
    zones = [[hue, saturation, value] for _ in range(50)]
    sync._dispatch(zones, (hue, saturation, value), True, SCREEN_PROFILES["video"])


def test_movie_screen_color_cut_is_damped_and_smoothed_for_movie_style():
    controller = FakeScreenController()
    sync = ScreenSync(controller, None, {"brightness": 100}, frame_bus=None, dev_id="test")
    _dispatch_l930(sync, hue=8, value=70)
    initial_hue = sync.latest_screen_data.global_hsv[0]

    # Abrupt cut with essentially constant luminance must still trigger damping.
    time.sleep(0.035)
    _dispatch_l930(sync, hue=232, value=70)
    first_cut_hue = sync.latest_screen_data.global_hsv[0]
    assert sync._last_scene_cut is True
    assert _hue_delta(initial_hue, first_cut_hue) < 20, (
        "a scene with similar brightness but a different dominant hue must not jump instantly"
    )
    assert _hue_delta(sync.latest_screen_data.column_hsvs[0][0], 232) > 100
    assert _hue_delta(controller.frames[-1]["segments"][0][0], 232) > 100, (
        "the physical L930 frame must use the smoothed columns, not raw cut colors"
    )

    # As frames continue arriving, the same target is approached progressively.
    distances = [_hue_delta(first_cut_hue, 232)]
    for _ in range(24):
        time.sleep(0.035)
        _dispatch_l930(sync, hue=232, value=70)
        distances.append(_hue_delta(sync.latest_screen_data.global_hsv[0], 232))
    assert distances[-1] < distances[0]
    assert all(0 <= h <= 360 for h, _, _ in sync.latest_screen_data.column_hsvs)


def test_l900_screen_sync_uses_smoothed_dominant_color_not_raw_scene_color():
    controller = FakeScreenController()
    sync = ScreenSync(controller, None, {"brightness": 80}, frame_bus=None, dev_id="test_l900")
    sync._dispatch(None, (350, 90, 65), False, SCREEN_PROFILES["video"])
    first = controller.frames[-1]
    assert first["h"] == 350

    time.sleep(0.035)
    sync._dispatch(None, (130, 90, 95), False, SCREEN_PROFILES["video"])
    second = controller.frames[-1]

    assert _hue_delta(first["h"], second["h"]) < 20, "L900 ambient color should be smoothed across scene cuts"
    assert sync.latest_screen_data.global_hsv[0] == second["h"]
    assert 65 < sync.latest_screen_data.global_hsv[2] < 95, "brightness should also reflect the smoothed scene state"


def test_l930_scene_cut_transition_respects_aimd_protection_without_changing_rate():
    controller = FakeScreenController(aimd_rate=1.0, configured_rate=5.0)
    sync = ScreenSync(controller, None, {"brightness": 100}, frame_bus=None, dev_id="test_l930")
    rates_before = (controller.frame_sender.max_updates_per_s, controller.frame_sender._aimd_rate_cap)

    _dispatch_l930(sync, hue=20, value=70)
    time.sleep(0.035)
    _dispatch_l930(sync, hue=210, value=70)
    frame = controller.frames[-1]

    assert frame["transition"] >= 980, "scene-cut transition should span most of the protected 1 Hz send period"
    assert rates_before == (controller.frame_sender.max_updates_per_s, controller.frame_sender._aimd_rate_cap)
    assert len(frame["segments"]) == 50
