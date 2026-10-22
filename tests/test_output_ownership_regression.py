from src.frame_bus import FrameBus, FramePacket, OutputArbiter, OutputProducer


class FakeController:
    def __init__(self):
        self.token = None
        self.validator = None
        self.frames = []
        self.clears = 0

    def bind_frame_bus(self, token, validator=None, publisher=None):
        self.token = token
        self.validator = validator
        self.publisher = publisher

    def submit_frame(self, frame, *, _frame_bus_token=None):
        if _frame_bus_token is not self.token:
            return False
        if self.validator and not self.validator(frame):
            return False
        self.frames.append(frame)
        return True

    def clear_frames(self):
        self.clears += 1


def test_bus_is_only_authorized_physical_route_and_stamps_generation():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = FakeController()
    bus.attach_device("strip2", controller)
    arbiter.claim_output("strip2", OutputProducer.EFFECT)

    assert bus.publish(FramePacket(
        dev_id="strip2",
        producer=OutputProducer.EFFECT,
        segments=[[210, 80, 60]] * 50,
    ))
    assert len(controller.frames) == 1
    frame = controller.frames[0]
    assert frame["_producer"] == OutputProducer.EFFECT
    assert frame["_generation"] == arbiter.generation("strip2")

    # A direct producer call without the private bus token cannot enqueue.
    assert controller.submit_frame({"segments": [[0, 100, 100]] * 50}) is False
    assert len(controller.frames) == 1


def test_ownership_change_invalidates_pending_and_old_generation():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = FakeController()
    bus.attach_device("strip2", controller)
    arbiter.claim_output("strip2", OutputProducer.AUDIO)
    packet = FramePacket(dev_id="strip2", producer=OutputProducer.AUDIO, segments=[[30, 90, 40]] * 50)
    assert bus.publish(packet)
    old_frame = controller.frames[-1]
    old_generation = old_frame["_generation"]

    arbiter.claim_output("strip2", OutputProducer.EFFECT)
    assert controller.clears >= 1
    assert bus.get_latest_frame("strip2") is None
    assert not bus.is_frame_current("strip2", old_frame)
    assert not arbiter.is_current("strip2", OutputProducer.AUDIO, old_generation)


def test_static_scene_can_publish_while_device_is_idle():
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)
    controller = FakeController()
    bus.attach_device("strip1", controller)
    assert bus.publish(FramePacket(dev_id="strip1", producer=OutputProducer.STATIC, hsv=(210, 60, 35)))
    assert len(controller.frames) == 1
    assert controller.frames[0]["h"] == 210
