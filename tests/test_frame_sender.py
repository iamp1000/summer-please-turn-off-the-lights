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


@pytest.mark.asyncio
async def test_frame_sender_varying_rtt_interval_integrity():
    """
    Verifies that when network round-trip time varies dynamically (e.g. 20ms, 80ms, 120ms),
    the pacing interval between transmission starts (t_start[k+1] - t_start[k]) is strictly
    measured from the beginning of each transmission, ensuring no short-cycling.
    """
    diag = DeviceDiagnostics(dev_id="test_strip")
    rtt_durations = [0.020, 0.080, 0.120, 0.030]
    call_index = 0
    transmit_starts = []

    async def variable_rtt_transmit(frame):
        nonlocal call_index
        transmit_starts.append(time.perf_counter())
        dur = rtt_durations[min(call_index, len(rtt_durations) - 1)]
        call_index += 1
        await asyncio.sleep(dur)
        return True

    loop = asyncio.get_running_loop()
    # 5.0 updates/sec -> target_interval = 0.200s (200ms)
    sender = LatestFrameSender(
        dev_id="test_strip",
        transmit_fn=variable_rtt_transmit,
        diagnostics=diag,
        loop=loop,
        max_updates_per_s=5.0,
    )
    sender.start()

    # Submit 4 frames
    for i in range(4):
        sender.submit_frame({"seq": i})
        await asyncio.sleep(0.220)

    sender.stop()

    assert len(transmit_starts) >= 3
    for k in range(1, len(transmit_starts)):
        delta = transmit_starts[k] - transmit_starts[k - 1]
        assert delta >= 0.190, f"Transmission {k} short-cycled: started only {delta*1000:.1f}ms after prior frame"


@pytest.mark.asyncio
async def test_frame_sender_no_early_wakeup_under_pending_flood():
    """
    Verifies that rapidly submitting frames while the worker is in its pacing delay
    does not prematurely awaken or truncate the sleep interval.
    """
    diag = DeviceDiagnostics(dev_id="test_strip")
    transmit_starts = []

    async def mock_transmit(frame):
        transmit_starts.append(time.perf_counter())
        await asyncio.sleep(0.030)
        return True

    loop = asyncio.get_running_loop()
    # 2.0 updates/sec -> target_interval = 0.500s (500ms)
    sender = LatestFrameSender(
        dev_id="test_strip",
        transmit_fn=mock_transmit,
        diagnostics=diag,
        loop=loop,
        max_updates_per_s=2.0,
    )
    sender.start()

    # Initial frame starts immediately
    sender.submit_frame({"flood": 0})
    await asyncio.sleep(0.040)  # Frame 0 finishing transmission, entering 470ms pacing delay

    # Rapidly submit 20 frames while pacing delay is active
    for f in range(1, 21):
        sender.submit_frame({"flood": f})
        await asyncio.sleep(0.010)

    # Wait until past the 500ms interval for frame 2 to transmit
    await asyncio.sleep(0.350)
    sender.stop()

    assert len(transmit_starts) >= 2
    measured_gap = transmit_starts[1] - transmit_starts[0]
    assert measured_gap >= 0.480, f"Flood caused early wakeup: gap was {measured_gap*1000:.1f}ms (expected >= 480ms)"

