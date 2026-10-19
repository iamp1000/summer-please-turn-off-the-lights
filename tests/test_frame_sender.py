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

    # Wait for sender to finish transmission cycle
    await asyncio.sleep(0.200)
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
