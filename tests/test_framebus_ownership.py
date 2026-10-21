from __future__ import annotations

import asyncio

from src.diagnostics import DeviceDiagnostics
from src.frame_bus import FrameBus, FramePacket, OutputArbiter, OutputProducer
from src.frame_sender import LatestFrameSender


def test_frame_bus_stamps_owner_generation_and_rejects_superseded_packet():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    delivered = []
    cleared = []

    bus.set_consumer("strip1", delivered.append)
    arbiter.add_owner_change_callback(
        lambda dev_id, old, new, generation: (
            bus.clear_device(dev_id),
            cleared.append((dev_id, old, new, generation)),
        )
    )

    arbiter.claim_output("strip1", OutputProducer.STATIC)
    first = FramePacket(
        dev_id="strip1",
        producer=OutputProducer.STATIC,
        hsv=(280, 80, 45),
        brightness=45,
    )
    assert bus.publish(first) is True
    assert first.producer_id == OutputProducer.STATIC
    assert first.generation == arbiter.get_generation("strip1")
    assert delivered == [first]
    assert bus.get_latest_frame("strip1") is first

    stale_generation = first.generation
    arbiter.claim_output("strip1", OutputProducer.AUDIO)
    assert bus.get_latest_frame("strip1") is None
    assert cleared[-1][1:3] == (OutputProducer.STATIC, OutputProducer.AUDIO)

    stale = FramePacket(
        dev_id="strip1",
        producer=OutputProducer.STATIC,
        generation=stale_generation,
        hsv=(10, 90, 70),
        brightness=70,
    )
    assert bus.publish(stale) is False
    assert delivered == [first]


def test_frame_bus_has_one_hardware_consumer_per_device():
    bus = FrameBus()
    first_consumer = lambda packet: None
    second_consumer = lambda packet: None
    bus.set_consumer("strip1", first_consumer)
    try:
        bus.set_consumer("strip1", second_consumer)
    except RuntimeError as exc:
        assert "already has a hardware consumer" in str(exc)
    else:
        raise AssertionError("FrameBus accepted two hardware consumers for one device")


async def _run_sender_ownership_test():
    arbiter = OutputArbiter()
    arbiter.claim_output("strip1", OutputProducer.AUDIO)
    sent = []

    async def transmit(frame):
        sent.append(frame)
        return True

    sender = LatestFrameSender(
        dev_id="strip1",
        transmit_fn=transmit,
        diagnostics=DeviceDiagnostics(dev_id="strip1"),
        loop=asyncio.get_running_loop(),
    )
    sender.set_frame_authorizer(
        lambda frame: arbiter.is_authorized(
            "strip1", frame.get("_producer_id", ""), frame.get("_generation", -1)
        )
    )
    sender.start()
    old_generation = arbiter.get_generation("strip1")
    sender.submit_frame({
        "h": 220,
        "s": 80,
        "b": 60,
        "_producer_id": OutputProducer.AUDIO,
        "_generation": old_generation,
    })

    # No event-loop yield occurs between enqueue and ownership change, so the worker
    # sees only the newer owner when it reaches the final send-time check.
    arbiter.claim_output("strip1", OutputProducer.EFFECT)
    await asyncio.sleep(0.03)
    sender.stop()
    await asyncio.sleep(0)
    assert sent == []


def test_frame_sender_drops_stale_owner_frame_before_transmission():
    asyncio.run(_run_sender_ownership_test())


def test_frame_sender_counts_saturation_only_changes_for_hsv_and_segments():
    sender = LatestFrameSender(
        dev_id="strip1",
        transmit_fn=None,
        diagnostics=DeviceDiagnostics(dev_id="strip1"),
        loop=asyncio.new_event_loop(),
        min_zone_delta=3,
    )
    sender._last_sent_hsb = (210, 10, 60)
    assert sender._is_change_significant({"h": 210, "s": 20, "b": 60}) is True
    assert sender._is_change_significant({"h": 210, "s": 11, "b": 60}) is False

    sender._last_sent_segments = [[210, 10, 60] for _ in range(50)]
    new_frame = [[210, 20, 60] for _ in range(50)]
    assert sender._is_change_significant({"segments": new_frame}) is True
    small_change = [[210, 11, 60] for _ in range(50)]
    assert sender._is_change_significant({"segments": small_change}) is False



def test_owner_switch_blocks_new_publications_until_pending_frame_clear_finishes():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    delivered = []
    bus.set_consumer("strip1", delivered.append)
    attempted_during_relinquish = []

    def old_owner_relinquishes():
        # New owner exists internally by now, but must not publish before queue clearing.
        attempted_during_relinquish.append(bus.publish(FramePacket(
            dev_id="strip1",
            producer=OutputProducer.AUDIO,
            hsv=(200, 90, 65),
            brightness=65,
        )))

    arbiter.claim_output("strip1", OutputProducer.STATIC, on_relinquish=old_owner_relinquishes)
    assert bus.publish(FramePacket(
        dev_id="strip1",
        producer=OutputProducer.STATIC,
        hsv=(30, 80, 45),
        brightness=45,
    )) is True

    cleared = []
    arbiter.add_owner_change_callback(
        lambda dev_id, old, new, generation: (bus.clear_device(dev_id), cleared.append(generation))
    )
    arbiter.claim_output("strip1", OutputProducer.AUDIO)
    assert attempted_during_relinquish == [False]
    assert bus.get_latest_frame("strip1") is None
    assert cleared

    # The new owner becomes eligible only after callbacks have purged stale state.
    assert bus.publish(FramePacket(
        dev_id="strip1",
        producer=OutputProducer.AUDIO,
        hsv=(200, 90, 65),
        brightness=65,
    )) is True
    assert len(delivered) == 2
    assert delivered[-1].producer == OutputProducer.AUDIO



def test_same_owner_reselection_renews_generation_and_rejects_old_frame():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    bus.set_consumer("strip1", lambda packet: True)
    arbiter.claim_output("strip1", OutputProducer.STATIC)
    old_generation = arbiter.get_generation("strip1")
    old_packet = FramePacket(
        dev_id="strip1",
        producer=OutputProducer.STATIC,
        generation=old_generation,
        hsv=(30, 80, 50),
        brightness=50,
    )
    assert bus.publish(old_packet) is True

    # Selecting a different static scene while STATIC still owns output creates a
    # fresh generation, so an in-flight frame from the previous scene is no longer valid.
    arbiter.claim_output("strip1", OutputProducer.STATIC, force_new_generation=True)
    assert arbiter.get_generation("strip1") > old_generation
    assert bus.publish(old_packet) is False

    current = FramePacket(
        dev_id="strip1",
        producer=OutputProducer.STATIC,
        generation=arbiter.get_generation("strip1"),
        hsv=(210, 80, 50),
        brightness=50,
    )
    assert bus.publish(current) is True


def test_native_firmware_scene_uses_consumer_without_replacing_visual_snapshot():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    seen = []
    bus.set_consumer("strip1", seen.append)

    arbiter.claim_output("strip1", OutputProducer.STATIC)
    visual = FramePacket(
        dev_id="strip1",
        producer=OutputProducer.STATIC,
        hsv=(275, 90, 50),
        brightness=50,
    )
    assert bus.publish(visual) is True
    assert bus.get_latest_frame("strip1") is visual

    arbiter.claim_output("strip1", OutputProducer.EFFECT)
    native_effect = object()
    command = FramePacket(
        dev_id="strip1",
        producer=OutputProducer.EFFECT,
        native_effect=native_effect,
        generation=arbiter.get_generation("strip1"),
    )
    assert bus.publish(command) is True
    assert seen[-1] is command
    # Native commands are routed to the consumer but are not frame previews.
    assert bus.get_latest_frame("strip1") is None


async def _run_native_effect_authorization_test():
    from src.device_l930 import L930Controller

    arbiter = OutputArbiter()
    arbiter.claim_output("strip1", OutputProducer.EFFECT)
    generation = arbiter.get_generation("strip1")
    sent = []

    class FakeResponse:
        def is_success(self):
            return True

    class FakeDevice:
        async def set_light_effect(self, effect):
            sent.append(effect)
            return FakeResponse()

    ctrl = L930Controller.__new__(L930Controller)
    ctrl.dev_id = "strip1"
    ctrl._framebus_managed = True
    ctrl._frame_authorizer = lambda token: (
        isinstance(token, dict)
        and arbiter.is_authorized(
            "strip1", token.get("_producer_id", ""), token.get("_generation", -1)
        )
    )
    ctrl._lock = asyncio.Lock()
    ctrl._device = FakeDevice()
    ctrl._is_on = True
    ctrl._last_successful_response = 0.0
    ctrl.clear_frames = lambda: None
    async def ensure_connected():
        return None
    ctrl._ensure_connected = ensure_connected

    # Hold the device lock so a command is queued behind it.
    await ctrl._lock.acquire()
    token = {"_producer_id": OutputProducer.EFFECT, "_generation": generation}
    task = asyncio.create_task(ctrl.set_native_effect(object(), priority=0, frame_token=token))
    await asyncio.sleep(0)
    arbiter.claim_output("strip1", OutputProducer.STATIC)
    ctrl._lock.release()

    accepted = await task
    assert accepted is False
    assert sent == []


def test_native_effect_waiting_for_device_lock_is_dropped_after_owner_switch():
    asyncio.run(_run_native_effect_authorization_test())
