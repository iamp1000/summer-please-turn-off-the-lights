from __future__ import annotations

import asyncio
from types import SimpleNamespace

from src.device_l930 import (
    L930Controller,
    _STATIC_EFFECT_ID,
    make_50_zone_segment_payload,
)


def test_segment_payload_uses_l930_per_zone_protocol_shape():
    colors = [[(i * 7) % 360, 82, 55 + (i % 35)] for i in range(50)]

    payload = make_50_zone_segment_payload(colors, pre_corrected=True)

    assert payload["type"] == "none"
    assert payload["custom"] == 1
    assert payload["enable"] == 1
    assert payload["deviceType"] == "strip"
    assert payload["id"] == _STATIC_EFFECT_ID
    assert payload["segments"] == list(range(50))
    assert len(payload["states"]) == 50
    assert len(payload["display_colors"]) <= 4
    assert payload["brightness"] == 100  # HSV levels are already master-corrected.
    assert payload["states"] == [color + [0] for color in colors]
    assert payload["states"][0] != payload["states"][-1]


class _SuccessfulTry:
    @staticmethod
    def is_success():
        return True


class _RawClient:
    def __init__(self):
        self.request = None

    async def execute_raw_request(self, request):
        self.request = request
        return _SuccessfulTry()


def test_l930_controller_sends_frames_via_segment_effect_endpoint():
    client = _RawClient()
    controller = object.__new__(L930Controller)
    controller._device = SimpleNamespace(client=client)
    payload = make_50_zone_segment_payload(
        [[i * 5 % 360, 100, 70] for i in range(50)],
        pre_corrected=True,
    )

    accepted = asyncio.run(controller._apply_segment_effect_rule(payload))

    assert accepted is True
    assert client.request is not None
    assert client.request.method == "apply_segment_effect_rule"
    assert client.request.params == payload


class _RecordingRawClient:
    def __init__(self):
        self.requests = []

    async def execute_raw_request(self, request):
        self.requests.append(request)
        return _SuccessfulTry()


def test_first_zone_frame_primes_custom_effect_with_black_before_colored_frame():
    client = _RecordingRawClient()
    controller = object.__new__(L930Controller)
    controller._device = SimpleNamespace(client=client)
    controller._is_on = True
    controller._lock = asyncio.Lock()
    controller._segment_effect_initialized = False
    controller._failure_streak = 0
    controller._last_successful_response = 0.0
    controller.last_b = 50
    controller.last_segments = [[0, 0, 0] for _ in range(50)]
    controller.music_transition_ms = 120
    controller.default_transition_ms = 0

    desired = [[(i * 7) % 360, 90, 65] for i in range(50)]
    frame = {"segments": desired, "brightness": 100, "_pre_corrected": True}
    first_result = asyncio.run(controller.transmit_frame(frame))

    assert first_result is True
    assert len(client.requests) == 2
    init_payload = client.requests[0].params
    frame_payload = client.requests[1].params
    assert init_payload["id"] == frame_payload["id"] == _STATIC_EFFECT_ID
    assert all(state == [0, 0, 0, 0] for state in init_payload["states"])
    assert frame_payload["states"] == [zone + [0] for zone in desired]
    assert controller._segment_effect_initialized is True

    next_frame = [[(i * 9) % 360, 82, 50] for i in range(50)]
    second_result = asyncio.run(controller.transmit_frame({
        "segments": next_frame, "brightness": 100, "_pre_corrected": True
    }))
    assert second_result is True
    assert len(client.requests) == 3
    assert client.requests[-1].params["states"] == [zone + [0] for zone in next_frame]
