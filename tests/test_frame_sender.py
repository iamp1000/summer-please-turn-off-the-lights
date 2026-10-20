from __future__ import annotations
import asyncio
import time
import pytest
from src.diagnostics import DeviceDiagnostics
from src.frame_sender import LatestFrameSender

@pytest.mark.asyncio
async def test_frame_sender_latest_frame_wins():
    diag = DeviceDiagnostics(dev_id="test_strip")
    transmitted_frames = []

    async def fake_transmit(frame):
        # Simulate 50ms network round-trip time
        await asyncio.sleep(0.050)
        transmitted_frames.append(frame)
        return True

    loop = asyncio.get_running_loop()
    sender = LatestFrameSender(
        dev_id="test_strip",
        transmit_fn=fake_transmit,
        diagnostics=diag,
        loop=loop,
    )
    sender.start()

    # Submit initial frame #1
    sender.submit_frame({"id": 1})
    await asyncio.sleep(0.010)

    # While frame #1 is transmitting, submit frames 2, 3, 4, 5 in rapid succession
    sender.submit_frame({"id": 2})
    sender.submit_frame({"id": 3})
    sender.submit_frame({"id": 4})
    sender.submit_frame({"id": 5})

    # Wait for sender to finish transmission cycle (frame 1 at 50ms + 200ms target interval + frame 5 at 50ms = ~300ms)
    await asyncio.sleep(0.350)
    sender.stop()

    snap = diag.snapshot()
    # Frames 1 and 5 should have been transmitted; frames 2, 3, 4 were dropped!
    transmitted_ids = [f["id"] for f in transmitted_frames]
    assert 1 in transmitted_ids
    assert 5 in transmitted_ids
    assert 2 not in transmitted_ids
    assert 3 not in transmitted_ids
    assert 4 not in transmitted_ids
    assert snap["frames_dropped"] >= 3
    assert snap["frames_generated"] == 5

@pytest.mark.asyncio
async def test_frame_sender_clear_on_power_off():
    diag = DeviceDiagnostics(dev_id="test_strip")
    transmitted_frames = []

    async def fake_transmit(frame):
        await asyncio.sleep(0.050)
        transmitted_frames.append(frame)
        return True

    loop = asyncio.get_running_loop()
    sender = LatestFrameSender(
        dev_id="test_strip",
        transmit_fn=fake_transmit,
        diagnostics=diag,
        loop=loop,
    )
    sender.start()

    # Submit frame and immediately clear (simulate immediate turn-off)
    sender.submit_frame({"id": 99})
    sender.clear()

    await asyncio.sleep(0.060)
    sender.stop()

    # Nothing should be transmitted because clear() purged the single-slot buffer
    assert {"id": 99} not in transmitted_frames


@pytest.mark.asyncio
async def test_frame_sender_true_interval_rate_limiting():
    """
    Verifies that LatestFrameSender enforces the exact target_interval based on elapsed
    time since transmission started, rather than waking up early under slow fallback rates (e.g. 1 update/s).
    """
    diag = DeviceDiagnostics(dev_id="test_strip")
    transmit_timestamps = []

    async def mock_transmit(frame):
        transmit_timestamps.append(time.perf_counter())
        await asyncio.sleep(0.040)  # 40ms transmission RTT
        return True

    loop = asyncio.get_running_loop()
    # Configure 4 updates/sec -> target_interval = 250ms
    sender = LatestFrameSender(
        dev_id="test_strip",
        transmit_fn=mock_transmit,
        diagnostics=diag,
        loop=loop,
        max_updates_per_s=4.0,
    )
    sender.start()

    # Submit 3 frames with pending frame always available
    sender.submit_frame({"f": 1})
    await asyncio.sleep(0.010)
    sender.submit_frame({"f": 2})

    # Wait 300ms so frame 2 has transmitted after the 250ms interval
    await asyncio.sleep(0.300)
    sender.submit_frame({"f": 3})
    await asyncio.sleep(0.300)
    sender.stop()

    assert len(transmit_timestamps) >= 3
    # Verify spacing between consecutive transmission starts is at least target_interval (~250ms)
    diff1 = transmit_timestamps[1] - transmit_timestamps[0]
    diff2 = transmit_timestamps[2] - transmit_timestamps[1]
    assert diff1 >= 0.240, f"Expected >= 240ms between frame 1 and 2, got {diff1*1000:.1f}ms"
    assert diff2 >= 0.240, f"Expected >= 240ms between frame 2 and 3, got {diff2*1000:.1f}ms"


@pytest.mark.asyncio
async def test_frame_sender_aimd_one_ups_fallback_pacing():
    """
    Verifies that when AIMD drops rate cap to 1 update/s (on slow network or failure),
    the sender does not wake early on pending frames and strictly respects the 1.0s interval.
    """
    diag = DeviceDiagnostics(dev_id="test_strip")
    transmit_timestamps = []

    async def slow_mock_transmit(frame):
        transmit_timestamps.append(time.perf_counter())
        await asyncio.sleep(0.420)  # > 400ms triggers AIMD drop to 1 update/s
        return True

    loop = asyncio.get_running_loop()
    sender = LatestFrameSender(
        dev_id="test_strip",
        transmit_fn=slow_mock_transmit,
        diagnostics=diag,
        loop=loop,
        max_updates_per_s=5.0,
    )
    sender.start()

    # Frame 1 triggers AIMD rate drop
    sender.submit_frame({"id": "slow1"})
    await asyncio.sleep(0.050)
    sender.submit_frame({"id": "pending_rapid"})

    # Wait long enough for frame 1 to finish (420ms) and frame 2 to wait for 1.0s interval
    await asyncio.sleep(1.550)
    sender.stop()

    assert len(transmit_timestamps) == 2
    interval = transmit_timestamps[1] - transmit_timestamps[0]
    # Spacing must respect the 1.0s interval (>= 0.95s), never waking early at 100ms
    assert interval >= 0.950, f"Expected >= 950ms under 1 update/s AIMD cap, got {interval*1000:.1f}ms"
