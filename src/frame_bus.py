from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Sequence, Tuple
import threading
import time

class OutputProducer:
    IDLE = "idle"
    STATIC = "static"
    EFFECT = "effect"
    AUDIO = "audio"
    SCREEN_SYNC = "screen_sync"
    COMPOSITE_FOLLOWER = "composite_follower"

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
    generation: Optional[int] = None
    producer_id: Optional[str] = None

class FrameBus:
    """Authoritative route for rendered frames. One physical consumer is allowed per device."""
    def __init__(self, arbiter: Optional["OutputArbiter"] = None):
        self._arbiter = arbiter
        self._latest_frames: Dict[str, FramePacket] = {}
        self._subscribers: Dict[str, List[Callable[[FramePacket], None]]] = {}
        self._consumers: Dict[str, Callable[[FramePacket], None]] = {}
        self._controllers: Dict[str, Any] = {}
        self._lock = threading.RLock()
        if self._arbiter:
            self._arbiter.subscribe_ownership_change(self._on_ownership_changed)

    def set_arbiter(self, arbiter: "OutputArbiter"):
        with self._lock:
            if self._arbiter is arbiter:
                return
            if self._arbiter:
                self._arbiter.unsubscribe_ownership_change(self._on_ownership_changed)
            self._arbiter = arbiter
            arbiter.subscribe_ownership_change(self._on_ownership_changed)

    def bind_device(self, dev_id: str, controller: Any):
        """Bind the sole hardware consumer for a device; rebinding is rejected."""
        with self._lock:
            existing = self._controllers.get(dev_id)
            if existing is not None and existing is not controller:
                raise ValueError(f"A hardware consumer is already bound for {dev_id}")
            if existing is controller:
                return
            self._controllers[dev_id] = controller
            self._consumers[dev_id] = lambda packet, c=controller: self._deliver(c, packet)
            sender = getattr(controller, "frame_sender", None)
            if sender and hasattr(sender, "set_frame_authorizer"):
                sender.set_frame_authorizer(lambda frame, d=dev_id: self.is_frame_current(d, frame))
            if hasattr(controller, "set_output_token_authorizer"):
                controller.set_output_token_authorizer(
                    lambda producer, generation, producer_id, d=dev_id:
                    self.is_token_current(d, producer, generation, producer_id)
                )

    @staticmethod
    def _packet_frame(packet: FramePacket) -> dict:
        extra = packet.metadata.get("_frame_fields", {})
        frame = dict(extra) if isinstance(extra, dict) else {}
        if packet.segments is not None:
            frame.update({"segments": [list(zone) for zone in packet.segments],
                          "brightness": int(packet.brightness), "transition": int(packet.transition)})
        elif packet.hsv is not None:
            h, s, b = packet.hsv[:3]
            frame.update({"h": int(h), "s": int(s), "b": int(b),
                          "brightness": int(packet.brightness), "transition": int(packet.transition)})
        frame["_dev_id"] = packet.dev_id
        frame["_producer"] = packet.producer
        frame["_generation"] = packet.generation
        frame["_producer_id"] = packet.producer_id
        if packet.pre_corrected:
            frame["_pre_corrected"] = True
        return frame

    def _deliver(self, controller: Any, packet: FramePacket):
        if not self.is_packet_current(packet):
            return
        submit = getattr(controller, "submit_frame", None)
        if submit:
            submit(self._packet_frame(packet))

    def _on_ownership_changed(self, dev_id: str, old_owner: str, new_owner: str,
                              generation: int, producer_id: str):
        # Clear the latest snapshot and physical pending slot before the next producer starts.
        with self._lock:
            self._latest_frames.pop(dev_id, None)
            controller = self._controllers.get(dev_id)
        if controller and hasattr(controller, "clear_frames"):
            try:
                controller.clear_frames()
            except Exception:
                pass

    def capture_token(self, dev_id: str, producer: str) -> Optional[Tuple[int, str]]:
        """Capture a producer session token at start and retain it for that run's lifetime."""
        if not self._arbiter:
            return (0, f"{dev_id}:{producer}:unmanaged")
        owner, generation, producer_id = self._arbiter.get_token(dev_id)
        if owner != producer:
            return None
        return generation, producer_id

    def publish_frame(self, dev_id: str, producer: str, frame: Any,
                      generation: Optional[int] = None, producer_id: Optional[str] = None) -> bool:
        """Publish an existing controller-frame dict through the authoritative route."""
        if isinstance(frame, dict) and "segments" in frame:
            segments, hsv = frame["segments"], None
            brightness = int(frame.get("brightness", 100))
        elif isinstance(frame, dict) and all(k in frame for k in ("h", "s", "b")):
            segments, hsv = None, (int(frame["h"]), int(frame["s"]), int(frame["b"]))
            brightness = int(frame.get("brightness", frame["b"]))
        elif isinstance(frame, (tuple, list)) and len(frame) >= 3 and not (
            isinstance(frame[0], (tuple, list)) and len(frame[0]) >= 3
        ):
            segments, hsv = None, (int(frame[0]), int(frame[1]), int(frame[2]))
            brightness = int(frame[2])
        elif isinstance(frame, list):
            segments, hsv = [list(zone) for zone in frame], None
            brightness = max((int(zone[2]) for zone in segments if len(zone) >= 3), default=0)
        else:
            return False
        preserved = {}
        if isinstance(frame, dict):
            for key, value in frame.items():
                if key not in {"segments", "h", "s", "b", "brightness", "transition",
                               "_dev_id", "_producer", "_generation", "_producer_id"}:
                    preserved[key] = value
        packet = FramePacket(
            dev_id=dev_id, producer=producer, segments=segments, hsv=hsv,
            brightness=brightness, transition=int(frame.get("transition", 0)) if isinstance(frame, dict) else 0,
            pre_corrected=bool(frame.get("_pre_corrected", False)) if isinstance(frame, dict) else False,
            metadata={"_frame_fields": preserved}, generation=generation, producer_id=producer_id,
        )
        return self.publish(packet)

    def publish(self, packet: FramePacket) -> bool:
        """Validate ownership, deliver once to hardware, and notify read-only observers."""
        with self._lock:
            arbiter = self._arbiter
            if arbiter:
                owner, generation, producer_id = arbiter.get_token(packet.dev_id)
                # One-shot packets may omit a token; stamp only if their producer owns the strip.
                # Long-running workers pass their captured token explicitly.
                if packet.generation is None and packet.producer_id is None:
                    if owner != packet.producer:
                        return False
                    packet.generation, packet.producer_id = generation, producer_id
                if not arbiter.is_token_current(packet.dev_id, packet.producer, packet.generation, packet.producer_id):
                    return False
            else:
                if packet.generation is None:
                    packet.generation = 0
                if packet.producer_id is None:
                    packet.producer_id = f"{packet.dev_id}:{packet.producer}:unmanaged"
            self._latest_frames[packet.dev_id] = packet
            consumer = self._consumers.get(packet.dev_id)
            callbacks = list(self._subscribers.get(packet.dev_id, []))
            global_callbacks = list(self._subscribers.get("*", []))
        if consumer:
            try:
                consumer(packet)
            except Exception:
                pass
        for callback in callbacks + global_callbacks:
            try:
                callback(packet)
            except Exception:
                pass
        return True

    def subscribe(self, dev_id: str, callback: Callable[[FramePacket], None]):
        """Subscribe as a read-only observer for a device or '*' for all devices."""
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
            packet = self._latest_frames.get(dev_id)
            if packet and not self.is_packet_current(packet):
                return None
            return packet

    def is_token_current(self, dev_id: str, producer: Optional[str],
                         generation: Optional[int], producer_id: Optional[str]) -> bool:
        """Validate a producer token for non-frame device commands as well."""
        if not self._arbiter:
            return bool(producer and generation is not None and producer_id)
        return self._arbiter.is_token_current(dev_id, producer, generation, producer_id)

    def is_packet_current(self, packet: FramePacket) -> bool:
        if not self._arbiter:
            return True
        return self._arbiter.is_token_current(packet.dev_id, packet.producer, packet.generation, packet.producer_id)

    def is_frame_current(self, dev_id: str, frame: Any) -> bool:
        if not isinstance(frame, dict) or frame.get("_dev_id") != dev_id:
            return False
        if not self._arbiter:
            return True
        return self._arbiter.is_token_current(
            dev_id, frame.get("_producer"), frame.get("_generation"), frame.get("_producer_id")
        )

class OutputArbiter:
    """Generation-based, exclusive output ownership for each physical strip."""
    def __init__(self):
        self._owners: Dict[str, str] = {}
        self._generations: Dict[str, int] = {}
        self._producer_ids: Dict[str, str] = {}
        self._relinquish_cbs: Dict[str, Callable] = {}
        self._ownership_callbacks: List[Callable[[str, str, str, int, str], None]] = []
        self._lock = threading.RLock()
        self._transition_lock = threading.RLock()

    def subscribe_ownership_change(self, callback: Callable[[str, str, str, int, str], None]):
        with self._lock:
            if callback not in self._ownership_callbacks:
                self._ownership_callbacks.append(callback)

    def unsubscribe_ownership_change(self, callback: Callable):
        with self._lock:
            if callback in self._ownership_callbacks:
                self._ownership_callbacks.remove(callback)

    def claim_output(self, dev_id: str, producer: str, on_relinquish: Optional[Callable] = None,
                     *, renew: bool = False) -> bool:
        with self._transition_lock:
            with self._lock:
                old_owner = self._owners.get(dev_id, OutputProducer.IDLE)
                old_cb = self._relinquish_cbs.get(dev_id)
                if old_owner == producer and not renew:
                    self._relinquish_cbs[dev_id] = on_relinquish
                    return True
                # renew=True starts a fresh session even when the logical producer
                # category is unchanged, invalidating frames from the previous scene.
                generation = self._generations.get(dev_id, 0) + 1
                producer_id = f"{dev_id}:{producer}:{generation}"
                self._generations[dev_id] = generation
                self._owners[dev_id] = producer
                self._producer_ids[dev_id] = producer_id
                self._relinquish_cbs[dev_id] = on_relinquish
                callbacks = list(self._ownership_callbacks)
            for callback in callbacks:
                try:
                    callback(dev_id, old_owner, producer, generation, producer_id)
                except Exception:
                    pass
            if old_cb:
                try:
                    old_cb()
                except Exception:
                    pass
            return True

    def release_output(self, dev_id: str, producer: str):
        with self._transition_lock:
            with self._lock:
                if self._owners.get(dev_id) != producer:
                    return
                old_owner = producer
                generation = self._generations.get(dev_id, 0) + 1
                producer_id = f"{dev_id}:{OutputProducer.IDLE}:{generation}"
                self._generations[dev_id] = generation
                self._owners[dev_id] = OutputProducer.IDLE
                self._producer_ids[dev_id] = producer_id
                self._relinquish_cbs.pop(dev_id, None)
                callbacks = list(self._ownership_callbacks)
            for callback in callbacks:
                try:
                    callback(dev_id, old_owner, OutputProducer.IDLE, generation, producer_id)
                except Exception:
                    pass

    def get_token(self, dev_id: str) -> Tuple[str, int, str]:
        with self._lock:
            owner = self._owners.get(dev_id, OutputProducer.IDLE)
            generation = self._generations.get(dev_id, 0)
            producer_id = self._producer_ids.get(dev_id, f"{dev_id}:{owner}:{generation}")
            return owner, generation, producer_id

    def is_token_current(self, dev_id: str, producer: Optional[str], generation: Optional[int],
                         producer_id: Optional[str]) -> bool:
        if not producer or generation is None or not producer_id:
            return False
        with self._lock:
            owner = self._owners.get(dev_id, OutputProducer.IDLE)
            current_generation = self._generations.get(dev_id, 0)
            current_id = self._producer_ids.get(dev_id, f"{dev_id}:{owner}:{current_generation}")
            return owner == producer and current_generation == generation and current_id == producer_id

    def can_submit(self, dev_id: str, producer: str) -> bool:
        """Compatibility preflight: an idle strip may be claimed by STATIC or IDLE."""
        with self._lock:
            owner = self._owners.get(dev_id, OutputProducer.IDLE)
            if owner == OutputProducer.IDLE:
                return producer in (OutputProducer.IDLE, OutputProducer.STATIC)
            return owner == producer

    def get_owner(self, dev_id: str) -> str:
        with self._lock:
            return self._owners.get(dev_id, OutputProducer.IDLE)
