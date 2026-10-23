from __future__ import annotations

import pytest

from src.effects_l930 import NUM_SEGMENTS, _build_wipe_segments


def test_wipe_reveals_target_zones_from_left_to_right():
    target = [[index, 80, 90] for index in range(NUM_SEGMENTS)]

    first = _build_wipe_segments(target, 1)
    middle = _build_wipe_segments(target, NUM_SEGMENTS // 2)
    final = _build_wipe_segments(target, NUM_SEGMENTS)

    assert len(first) == len(middle) == len(final) == NUM_SEGMENTS
    assert first[0] == target[0]
    assert all(zone == [0, 0, 0] for zone in first[1:])
    assert middle[:25] == target[:25]
    assert all(zone == [0, 0, 0] for zone in middle[25:])
    assert final == target


@pytest.mark.parametrize("visible_count", [-10, 0])
def test_wipe_clamps_empty_reveal_to_black(visible_count):
    target = [[index, 80, 90] for index in range(NUM_SEGMENTS)]

    assert _build_wipe_segments(target, visible_count) == [[0, 0, 0]] * NUM_SEGMENTS


@pytest.mark.parametrize("visible_count", [NUM_SEGMENTS, NUM_SEGMENTS + 10])
def test_wipe_clamps_complete_reveal_to_target(visible_count):
    target = [[index, 80, 90] for index in range(NUM_SEGMENTS)]

    assert _build_wipe_segments(target, visible_count) == target


def test_wipe_rejects_wrong_zone_count():
    with pytest.raises(ValueError, match="Expected 50 target zones"):
        _build_wipe_segments([[0, 0, 0]], 1)
