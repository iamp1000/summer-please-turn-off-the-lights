from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Sequence
import threading
import time


class OutputProducer:
    IDLE = "idle"
    STATIC = "static"
    EFFECT = "effect"
    AUDIO = "audio"
    SCREEN_SYNC = "screen_sync"
    COMPOSITE_FOLLOWER = "composite_follower"
    AUTOMATION = "automation"


@dataclass
class FramePacket:
    dev_id: str
    producer: str
    timestamp: float = field(default_factory=time.time)
    segments: Optional[List[List[int]]] = None
    hsv: Optional[Sequence[int]] = None
    brightness: int = 100
    transition: int = 0
    pre_corrected: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    generation: int = -1


class OutputArbiter:
    """Serializes output ownership and gives every ownership epoch a generation."""

    def __init__(self):
        self._owners: Dict[str, str] = {}
        self._generations: Dict[str, int] = {}
        self._relinquish_cbs: Dict[str, Callable] = {}
        self._invalidators: Dict[str, List[Callable[[], None]]] = {}
        self._lock = threading.RLock()

    def register_invalidator(self, dev_id: str, callback: Callable[[], None]):
        with self._lock:
            callbacks = self._invalidators.setdefault(dev_id, [])
            if callback not in callbacks:
                callbacks.append(callback)

    def generation(self, dev_id: str) -> int:
        with self._lock:
            return self._generations.get(dev_id, 0)

    def claim_output(self, dev_id: str, producer: str, on_relinquish: Optional[Callable] = None) -> bool:
        callbacks = []
        with self._lock:
            old = self._owners.get(dev_id, OutputProducer.IDLE)
            if old == producer:
                self._relinquish_cbs[dev_id] = on_relinquish
                return True
            old_cb = self._relinquish_cbs.get(dev_id)
            # Advance generation and invalidate queued frames before a new owner can publish.
            self._generations[dev_id] = self._generations.get(dev_id, 0) + 1
            self._owners[dev_id] = producer
            self._relinquish_cbs[dev_id] = on_relinquish
            callbacks = list(self._invalidators.get(dev_id, ()))
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass
        if old_cb:
            try:
                old_cb()
            except Exception:
                pass
        return True

    def release_output(self, dev_id: str, producer: str):
        callbacks = []
        with self._lock:
            if self._owners.get(dev_id) != producer:
                return
            self._owners[dev_id] = OutputProducer.IDLE
            self._relinquish_cbs.pop(dev_id, None)
            self._generations[dev_id] = self._generations.get(dev_id, 0) + 1
            callbacks = list(self._invalidators.get(dev_id, ()))
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass

    def can_submit(self, dev_id: str, producer: str) -> bool:
        with self._lock:
            owner = self._owners.get(dev_id, OutputProducer.IDLE)
            if owner == producer:
                return True
            return owner == OutputProducer.IDLE and producer in (OutputProducer.STATIC, OutputProducer.IDLE)

    def is_current(self, dev_id: str, producer: str, generation: int) -> bool:
        with self._lock:
            return (
                (
                    self._owners.get(dev_id, OutputProducer.IDLE) == producer
                    or (self._owners.get(dev_id, OutputProducer.IDLE) == OutputProducer.IDLE
                        and producer in (OutputProducer.STATIC, OutputProducer.IDLE))
                )
                and self._generations.get(dev_id, 0) == generation
            )

    def run_if_current(self, dev_id: str, producer: str, generation: int, callback: Callable[[], None]) -> bool:
        """Run enqueue while holding the ownership lock, making check+enqueue atomic to handoff."""
        with self._lock:
            if not self.is_current(dev_id, producer, generation):
                return False
            callback()
            return True

    def get_owner(self, dev_id: str) -> str:
        with self._lock:
            return self._owners.get(dev_id, OutputProducer.IDLE)


class FrameBus:
    """The sole authorized route from frame producers to each physical device."""

    def __init__(self, arbiter: Optional[OutputArbiter] = None):
        self._arbiter = arbiter
        self._latest_frames: Dict[str, FramePacket] = {}
        self._subscribers: Dict[str, List[Callable[[FramePacket], None]]] = {}
        self._controllers: Dict[str, Any] = {}
        self._tokens: Dict[str, object] = {}
        self._lock = threading.RLock()

    def set_arbiter(self, arbiter: OutputArbiter):
        with self._lock:
            self._arbiter = arbiter

    def attach_device(self, dev_id: str, controller: Any):
        """Attach the one physical output consumer for a device."""
        token = object()
        with self._lock:
            self._controllers[dev_id] = controller
            self._tokens[dev_id] = token
        if hasattr(controller, "bind_frame_bus"):
            controller.bind_frame_bus(
                token,
                lambda frame, d=dev_id: self.is_frame_current(d, frame),
                lambda frame, d=dev_id: self.publish_frame_dict(d, OutputProducer.STATIC, frame),
            )
        if self._arbiter:
            self._arbiter.register_invalidator(dev_id, lambda d=dev_id: self.clear_device(d))

    def is_frame_current(self, dev_id: str, frame: Any) -> bool:
        if not isinstance(frame, dict) or self._arbiter is None:
            return True
        producer = frame.get("_producer")
        generation = frame.get("_generation")
        return producer is not None and generation is not None and self._arbiter.is_current(dev_id, producer, int(generation))

    def clear_device(self, dev_id: str):
        with self._lock:
            self._latest_frames.pop(dev_id, None)
            controller = self._controllers.get(dev_id)
        if controller and hasattr(controller, "clear_frames"):
            controller.clear_frames()

    def publish_frame_dict(self, dev_id: str, producer: str, frame: dict) -> bool:
        """Compatibility adapter: translate legacy frame dictionaries into the single bus route."""
        packet = FramePacket(
            dev_id=dev_id,
            producer=producer,
            segments=frame.get("segments"),
            hsv=(frame.get("h", 0), frame.get("s", 0), frame.get("b", 0))
                if all(k in frame for k in ("h", "s", "b")) else None,
            brightness=int(frame.get("brightness", frame.get("b", 100))),
            transition=int(frame.get("transition", 0)),
            pre_corrected=bool(frame.get("_pre_corrected", False)),
            metadata={k: v for k, v in frame.items() if k not in {
                "segments", "h", "s", "b", "brightness", "transition", "_pre_corrected",
                "_producer", "_generation"
            }},
        )
        return self.publish(packet)

    def publish(self, packet: FramePacket) -> bool:
        with self._lock:
            arbiter = self._arbiter
            controller = self._controllers.get(packet.dev_id)
            token = self._tokens.get(packet.dev_id)
            if arbiter:
                if not arbiter.can_submit(packet.dev_id, packet.producer):
                    return False
                packet.generation = arbiter.generation(packet.dev_id)
            else:
                packet.generation = max(0, packet.generation)
            previous = self._latest_frames.get(packet.dev_id)
            if (
                previous is not None
                and previous.producer == packet.producer
                and previous.generation == packet.generation
                and previous.segments == packet.segments
                and previous.hsv == packet.hsv
                and previous.brightness == packet.brightness
                and previous.transition == packet.transition
            ):
                # Legacy adapters can follow an explicit publish with the same frame.
                return True
            self._latest_frames[packet.dev_id] = packet
            callbacks = list(self._subscribers.get(packet.dev_id, ())) + list(self._subscribers.get("*", ()))

        # One authoritative physical enqueue. Generation is checked again at the boundary.
        if controller is not None and token is not None:
            frame = self._to_frame(packet)
            def enqueue():
                controller.submit_frame(frame, _frame_bus_token=token)
            if arbiter:
                accepted = arbiter.run_if_current(packet.dev_id, packet.producer, packet.generation, enqueue)
                if not accepted:
                    return False
            else:
                enqueue()

        for callback in callbacks:
            try:
                callback(packet)
            except Exception:
                pass
        return True

    @staticmethod
    def _to_frame(packet: FramePacket) -> dict:
        frame: dict = {
            "_producer": packet.producer,
            "_generation": packet.generation,
            "brightness": packet.brightness,
            "transition": packet.transition,
            "_pre_corrected": packet.pre_corrected,
        }
        if packet.segments is not None:
            frame["segments"] = [list(x) for x in packet.segments]
        if packet.hsv is not None:
            h, s, v = packet.hsv
            frame.update({"h": int(h), "s": int(s), "b": int(v)})
        frame.update(packet.metadata or {})
        return frame

    def subscribe(self, dev_id: str, callback: Callable[[FramePacket], None]):
        with self._lock:
            callbacks = self._subscribers.setdefault(dev_id, [])
            if callback not in callbacks:
                callbacks.append(callback)

    def unsubscribe(self, dev_id: str, callback: Callable[[FramePacket], None]):
        with self._lock:
            callbacks = self._subscribers.get(dev_id, [])
            if callback in callbacks:
                callbacks.remove(callback)

    def get_latest_frame(self, dev_id: str) -> Optional[FramePacket]:
        with self._lock:
            return self._latest_frames.get(dev_id)
