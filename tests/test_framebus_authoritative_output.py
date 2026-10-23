from __future__ import annotations

import pytest

from src.frame_bus import FrameBus, FramePacket, OutputArbiter, OutputProducer


class FakeSender:
    def __init__(self):
        self.authorizer = None

    def set_frame_authorizer(self, callback):
        self.authorizer = callback


class FakeController:
    def __init__(self):
        self.frame_sender = FakeSender()
        self.frames = []
        self.clear_count = 0

    def submit_frame(self, frame):
        self.frames.append(frame)

    def clear_frames(self):
        self.clear_count += 1
        self.frames.clear()


def test_frame_bus_binds_only_one_physical_consumer_per_device():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    first, second = FakeController(), FakeController()

    bus.bind_device("strip", first)
    assert first.frame_sender.authorizer is not None

    with pytest.raises(ValueError, match="already bound"):
        bus.bind_device("strip", second)


def test_frame_bus_delivers_authorized_frame_once_with_session_token():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = FakeController()
    bus.bind_device("strip", controller)
    arbiter.claim_output("strip", OutputProducer.STATIC)

    packet = FramePacket(
        dev_id="strip",
        producer=OutputProducer.STATIC,
        hsv=(205, 72, 44),
        brightness=44,
        transition=600,
    )
    assert bus.publish(packet) is True
    assert len(controller.frames) == 1
    frame = controller.frames[0]
    assert (frame["h"], frame["s"], frame["b"]) == (205, 72, 44)
    assert frame["_producer"] == OutputProducer.STATIC
    assert frame["_generation"] == packet.generation
    assert frame["_producer_id"] == packet.producer_id
    assert bus.get_latest_frame("strip") is packet


def test_stale_session_is_rejected_even_if_same_producer_reclaims_device():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = FakeController()
    bus.bind_device("strip", controller)

    arbiter.claim_output("strip", OutputProducer.EFFECT)
    stale_token = bus.capture_token("strip", OutputProducer.EFFECT)
    assert stale_token is not None

    arbiter.claim_output("strip", OutputProducer.AUDIO)
    arbiter.claim_output("strip", OutputProducer.EFFECT)

    generation, producer_id = stale_token
    accepted = bus.publish_frame(
        "strip",
        OutputProducer.EFFECT,
        {"segments": [[210, 80, 60]] * 50, "brightness": 60, "transition": 500},
        generation=generation,
        producer_id=producer_id,
    )
    assert accepted is False
    assert controller.frames == []
    assert bus.get_latest_frame("strip") is None


def test_ownership_change_clears_latest_snapshot_and_pending_frames():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = FakeController()
    bus.bind_device("strip", controller)

    arbiter.claim_output("strip", OutputProducer.STATIC)
    assert bus.publish(FramePacket(
        dev_id="strip", producer=OutputProducer.STATIC, hsv=(220, 80, 55), brightness=55
    ))
    assert bus.get_latest_frame("strip") is not None
    assert controller.frames

    arbiter.claim_output("strip", OutputProducer.AUDIO)
    assert bus.get_latest_frame("strip") is None
    assert controller.frames == []
    assert controller.clear_count >= 2  # first owner claim + ownership switch

def test_new_scene_generation_rejects_previous_session_of_same_producer():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = FakeController()
    bus.bind_device("strip", controller)

    arbiter.claim_output("strip", OutputProducer.EFFECT)
    old_generation, old_producer_id = bus.capture_token("strip", OutputProducer.EFFECT)

    arbiter.claim_output("strip", OutputProducer.EFFECT, renew=True)

    assert bus.publish_frame(
        "strip",
        OutputProducer.EFFECT,
        {"segments": [[130, 90, 65]] * 50, "brightness": 65},
        generation=old_generation,
        producer_id=old_producer_id,
    ) is False
    assert controller.frames == []
    assert bus.get_latest_frame("strip") is None


def test_hub_static_brightness_update_republishes_through_frame_bus():
    """Static brightness changes must not issue a second controller-level write."""
    from types import SimpleNamespace
    from src.hub import LightHub

    class Controller(FakeController):
        last_h = 205
        last_s = 72
        last_b = 44

        async def set_brightness(self, _value, priority=1):
            raise AssertionError("brightness bypassed the authoritative FrameBus path")

    class RejectDirectWrites:
        def run(self, awaitable):
            close = getattr(awaitable, "close", None)
            if close:
                close()
            raise AssertionError("a direct device write was attempted")

    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = Controller()
    bus.bind_device("strip", controller)
    arbiter.claim_output("strip", OutputProducer.STATIC)
    assert bus.publish(FramePacket(
        dev_id="strip",
        producer=OutputProducer.STATIC,
        hsv=(205, 72, 44),
        brightness=44,
    ))

    ctx = SimpleNamespace(
        dev_id="strip",
        model="L900",
        state={"brightness": 44, "active_label": "Custom Wheel"},
        controller=controller,
        fx_engine=None,
    )
    hub = LightHub.__new__(LightHub)
    hub.devices = {"strip": ctx}
    hub.arbiter = arbiter
    hub.frame_bus = bus
    hub.loop_runner = RejectDirectWrites()
    hub.notify_change = lambda: None

    hub.set_brightness("strip", 75)

    latest = bus.get_latest_frame("strip")
    assert latest is not None
    assert latest.producer == OutputProducer.STATIC
    assert tuple(latest.hsv) == (205, 72, 75)
    assert latest.generation is not None
    assert latest.producer_id is not None
    assert controller.frames[-1]["b"] == 75
    assert controller.frames[-1]["_producer"] == OutputProducer.STATIC


def test_hub_static_l930_brightness_scales_precorrected_zones():
    """The GUI dimmer must scale pre-corrected 50-zone frames before Tapo serialization."""
    from types import SimpleNamespace
    from src.hub import LightHub

    class RejectDirectWrites:
        def run(self, awaitable):
            close = getattr(awaitable, "close", None)
            if close:
                close()
            raise AssertionError("brightness bypassed the authoritative FrameBus path")

    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = FakeController()
    bus.bind_device("strip", controller)
    arbiter.claim_output("strip", OutputProducer.STATIC)
    initial_zones = [[210, 80, 40] for _ in range(50)]
    assert bus.publish(FramePacket(
        dev_id="strip",
        producer=OutputProducer.STATIC,
        segments=initial_zones,
        brightness=50,
        pre_corrected=True,
    ))

    ctx = SimpleNamespace(
        dev_id="strip",
        model="L930",
        state={"brightness": 50, "active_label": "Custom Wheel"},
        controller=controller,
        fx_engine=None,
    )
    hub = LightHub.__new__(LightHub)
    hub.devices = {"strip": ctx}
    hub.arbiter = arbiter
    hub.frame_bus = bus
    hub.loop_runner = RejectDirectWrites()
    hub.notify_change = lambda: None

    hub.set_brightness("strip", 75)

    latest = bus.get_latest_frame("strip")
    assert latest is not None
    assert latest.producer == OutputProducer.STATIC
    assert latest.pre_corrected is True
    assert latest.brightness == 75
    assert latest.segments[0][2] == 60
    assert controller.frames[-1]["segments"][0][2] == 60
