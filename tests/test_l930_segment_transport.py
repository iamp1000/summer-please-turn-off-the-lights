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
