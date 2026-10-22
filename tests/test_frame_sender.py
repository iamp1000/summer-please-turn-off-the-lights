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



@pytest.mark.asyncio
async def test_sender_rejects_frame_that_is_unauthorized_at_send_boundary():
    """A frame already popped from the latest-wins slot must still be reauthorized."""
    diag = DeviceDiagnostics(dev_id="owned_strip")
    sent = []

    async def mock_transmit(frame):
        sent.append(frame)
        return True

    sender = LatestFrameSender(
        dev_id="owned_strip",
        transmit_fn=mock_transmit,
        diagnostics=diag,
        loop=asyncio.get_running_loop(),
        max_updates_per_s=8.0,
    )
    sender.set_frame_authorizer(lambda _frame: False)
    sender.start()
    sender.submit_frame({"segments": [[200, 90, 60]] * 50, "brightness": 60})
    await asyncio.sleep(0.08)
    sender.stop()

    assert sent == []
    assert diag.frames_dropped >= 1


@pytest.mark.asyncio
async def test_saturation_only_changes_are_significant_for_both_frame_shapes():
    """Saturation changes alone can alter color and must bypass the unchanged-frame filter."""
    diag = DeviceDiagnostics(dev_id="saturation_strip")

    async def mock_transmit(_frame):
        return True

    sender = LatestFrameSender(
        dev_id="saturation_strip",
        transmit_fn=mock_transmit,
        diagnostics=diag,
        loop=asyncio.get_running_loop(),
        max_updates_per_s=8.0,
        min_zone_delta=2.0,
    )

    sender._last_sent_segments = [[120, 10, 50] for _ in range(50)]
    sender._last_sent_hsb = None
    assert sender._is_change_significant([[120, 16, 50] for _ in range(50)])

    sender._last_sent_segments = None
    sender._last_sent_hsb = (120, 10, 50)
    assert sender._is_change_significant({"h": 120, "s": 16, "b": 50})


@pytest.mark.asyncio
async def test_frame_popped_before_handoff_is_dropped_by_live_arbiter_check():
    """An ownership switch during the final send authorization must suppress the old frame."""
    import threading
    from src.frame_bus import FrameBus, OutputArbiter, OutputProducer

    diag = DeviceDiagnostics(dev_id="handoff_strip")
    sent = []
    auth_entered = threading.Event()
    allow_auth_to_finish = threading.Event()

    async def mock_transmit(frame):
        sent.append(frame)
        return True

    loop = asyncio.get_running_loop()
    sender = LatestFrameSender(
        dev_id="handoff_strip",
        transmit_fn=mock_transmit,
        diagnostics=diag,
        loop=loop,
        max_updates_per_s=8.0,
    )

    class Controller:
        frame_sender = sender

        def submit_frame(self, frame):
            sender.submit_frame(frame)

        def clear_frames(self):
            sender.clear()

    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    bus.bind_device("handoff_strip", Controller())
    arbiter.claim_output("handoff_strip", OutputProducer.EFFECT)
    token = bus.capture_token("handoff_strip", OutputProducer.EFFECT)
    assert token is not None

    def gated_authorizer(frame):
        auth_entered.set()
        # The test thread changes the owner after this frame is popped, but before
        # the authorization decision is made.
        allow_auth_to_finish.wait(timeout=1.0)
        return bus.is_frame_current("handoff_strip", frame)

    sender.set_frame_authorizer(gated_authorizer)

    def handoff():
        assert auth_entered.wait(timeout=1.0)
        arbiter.claim_output("handoff_strip", OutputProducer.AUDIO, renew=True)
        allow_auth_to_finish.set()

    handoff_thread = threading.Thread(target=handoff, daemon=True)
    handoff_thread.start()
    sender.start()
    assert bus.publish_frame(
        "handoff_strip",
        OutputProducer.EFFECT,
        {"segments": [[220, 90, 65]] * 50, "brightness": 65, "transition": 500},
        generation=token[0],
        producer_id=token[1],
    )

    await asyncio.sleep(0.08)
    handoff_thread.join(timeout=1.0)
    sender.stop()

    assert not handoff_thread.is_alive()
    assert sent == []
    assert diag.frames_dropped >= 1


def test_framebus_rejects_untagged_live_stream_and_stale_generation():
    """Bound live devices reject tokenless streams and never accept a prior owner token."""
    from src.frame_bus import FrameBus, OutputArbiter, OutputProducer, FramePacket

    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)

    class Sink:
        def __init__(self):
            self.frames = []
        def submit_frame(self, frame):
            self.frames.append(frame)
        def clear_frames(self):
            # Test sink keeps a history; physical sender clears only its pending slot.
            pass

    sink = Sink()
    bus.bind_device("strip1", sink)
    arbiter.claim_output("strip1", OutputProducer.EFFECT, renew=True)
    token = bus.capture_token("strip1", OutputProducer.EFFECT)
    assert token is not None

    tokenless = FramePacket(
        dev_id="strip1",
        producer=OutputProducer.EFFECT,
        segments=[[210, 80, 50]] * 50,
        brightness=50,
    )
    assert bus.publish(tokenless) is False
    assert sink.frames == []

    generation, producer_id = token
    assert bus.publish(FramePacket(
        dev_id="strip1",
        producer=OutputProducer.EFFECT,
        segments=[[210, 80, 50]] * 50,
        brightness=50,
        generation=generation,
        producer_id=producer_id,
    )) is True
    assert len(sink.frames) == 1

    arbiter.claim_output("strip1", OutputProducer.AUDIO, renew=True)
    stale = FramePacket(
        dev_id="strip1",
        producer=OutputProducer.EFFECT,
        segments=[[25, 100, 100]] * 50,
        brightness=100,
        generation=generation,
        producer_id=producer_id,
    )
    assert bus.publish(stale) is False
    assert len(sink.frames) == 1
    assert bus.get_latest_frame("strip1") is None


def test_framebus_allows_only_one_physical_consumer_per_device():
    from src.frame_bus import FrameBus, OutputArbiter

    bus = FrameBus(OutputArbiter())

    class Sink:
        def submit_frame(self, _frame):
            pass

    bus.bind_device("strip1", Sink())
    with pytest.raises(ValueError, match="already bound"):
        bus.bind_device("strip1", Sink())
