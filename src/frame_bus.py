from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Sequence
import time
import threading


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
    color_temp: Optional[int] = None
    brightness: int = 100
    transition: int = 0
    pre_corrected: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Captured by FrameBus at acceptance time; carried all the way to the send boundary.
    generation: int = 0
    producer_id: Optional[str] = None

    def __post_init__(self):
        if self.producer_id is None:
            self.producer_id = self.producer
        elif self.producer_id != self.producer:
            raise ValueError("FramePacket producer and producer_id must match")


class FrameBus:
    """
    Authoritative frame route for each physical device.

    Producers publish here only. A single per-device consumer converts accepted packets
    into sender frames. Consumer packets include producer identity and ownership generation,
    and the sender re-validates both immediately before transmission.
    """

    def __init__(self, arbiter: Optional["OutputArbiter"] = None):
        self._arbiter = arbiter
        self._latest_frames: Dict[str, FramePacket] = {}
        self._subscribers: Dict[str, List[Callable[[FramePacket], None]]] = {}
        self._consumers: Dict[str, Callable[[FramePacket], None]] = {}
        self._lock = threading.RLock()

    def set_arbiter(self, arbiter: "OutputArbiter"):
        with self._lock:
            self._arbiter = arbiter

    def set_consumer(self, dev_id: str, callback: Callable[[FramePacket], None]):
        """Install the one authoritative hardware consumer for a device."""
        with self._lock:
            existing = self._consumers.get(dev_id)
            if existing is not None and existing is not callback:
                raise RuntimeError(f"FrameBus already has a hardware consumer for {dev_id}")
            self._consumers[dev_id] = callback

    def clear_device(self, dev_id: str):
        """Forget the latest preview frame after ownership changes."""
        with self._lock:
            self._latest_frames.pop(dev_id, None)

    def current_generation(self, dev_id: str, producer: str) -> int:
        arbiter = self._arbiter
        if arbiter is None:
            return 1
        if not arbiter.can_submit(dev_id, producer):
            return 0
        return arbiter.get_generation(dev_id)

    def publish(self, packet: FramePacket) -> bool:
        """Accept only the current owner, stamp its generation, and enqueue once."""
        with self._lock:
            arbiter = self._arbiter
            if arbiter is not None:
                if not arbiter.can_submit(packet.dev_id, packet.producer_id or packet.producer):
                    return False
                current_generation = arbiter.get_generation(packet.dev_id)
                if packet.generation not in (0, current_generation):
                    return False
                packet.generation = current_generation
                # Re-check the exact token before accepting the packet.
                if not arbiter.is_authorized(
                    packet.dev_id, packet.producer_id or packet.producer, packet.generation
                ):
                    return False
            elif packet.generation <= 0:
                packet.generation = 1

            if packet.segments is None and packet.hsv is None and packet.color_temp is None:
                return False
            self._latest_frames[packet.dev_id] = packet
            consumer = self._consumers.get(packet.dev_id)
            callbacks = list(self._subscribers.get(packet.dev_id, []))
            global_callbacks = list(self._subscribers.get("*", []))

        # The one consumer is the only bus-controlled route to the physical sender.
        if consumer is not None:
            try:
                consumer(packet)
            except Exception:
                # A consumer failure must not break telemetry subscribers or render threads.
                pass

        for cb in callbacks + global_callbacks:
            try:
                cb(packet)
            except Exception:
                pass
        return True

    def subscribe(self, dev_id: str, callback: Callable[[FramePacket], None]):
        """Subscribe to frame publications for preview, composite reads, or telemetry."""
        with self._lock:
            subscribers = self._subscribers.setdefault(dev_id, [])
            if callback not in subscribers:
                subscribers.append(callback)

    def unsubscribe(self, dev_id: str, callback: Callable[[FramePacket], None]):
        with self._lock:
            if dev_id in self._subscribers and callback in self._subscribers[dev_id]:
                self._subscribers[dev_id].remove(callback)

    def get_latest_frame(self, dev_id: str) -> Optional[FramePacket]:
        with self._lock:
            packet = self._latest_frames.get(dev_id)
            if packet is None:
                return None
            arbiter = self._arbiter
            if arbiter is not None and not arbiter.is_authorized(
                dev_id, packet.producer_id or packet.producer, packet.generation
            ):
                return None
            return packet


class OutputArbiter:
    """Strict single-owner arbiter with monotonic per-device ownership generations."""

    def __init__(self):
        self._owners: Dict[str, str] = {}
        self._generations: Dict[str, int] = {}
        self._relinquish_cbs: Dict[str, Callable] = {}
        self._owner_change_cbs: List[Callable[[str, str, str, int], None]] = []
        self._lock = threading.RLock()

    def add_owner_change_callback(self, callback: Callable[[str, str, str, int], None]):
        with self._lock:
            if callback not in self._owner_change_cbs:
                self._owner_change_cbs.append(callback)

    def claim_output(self, dev_id: str, producer: str, on_relinquish: Optional[Callable] = None) -> bool:
        old_cb = None
        listeners = []
        old_producer = OutputProducer.IDLE
        with self._lock:
            old_producer = self._owners.get(dev_id, OutputProducer.IDLE)
            if old_producer == producer:
                self._relinquish_cbs[dev_id] = on_relinquish
                return True

            old_cb = self._relinquish_cbs.get(dev_id)
            self._owners[dev_id] = producer
            generation = self._generations.get(dev_id, 0) + 1
            self._generations[dev_id] = generation
            self._relinquish_cbs[dev_id] = on_relinquish
            listeners = list(self._owner_change_cbs)

        # Owner/token changes are visible before shutdown callbacks run: any late publish
        # from the old producer is rejected, then pending queues are purged.
        if old_cb:
            try:
                old_cb()
            except Exception:
                pass
        for callback in listeners:
            try:
                callback(dev_id, old_producer, producer, generation)
            except Exception:
                pass
        return True

    def release_output(self, dev_id: str, producer: str):
        listeners = []
        generation = 0
        with self._lock:
            if self._owners.get(dev_id) != producer:
                return
            old_producer = producer
            self._owners[dev_id] = OutputProducer.IDLE
            generation = self._generations.get(dev_id, 0) + 1
            self._generations[dev_id] = generation
            self._relinquish_cbs.pop(dev_id, None)
            listeners = list(self._owner_change_cbs)

        for callback in listeners:
            try:
                callback(dev_id, old_producer, OutputProducer.IDLE, generation)
            except Exception:
                pass

    def can_submit(self, dev_id: str, producer: str, generation: Optional[int] = None) -> bool:
        with self._lock:
            if self._owners.get(dev_id, OutputProducer.IDLE) != producer:
                return False
            if generation is not None and generation != self._generations.get(dev_id, 0):
                return False
            return True

    def is_authorized(self, dev_id: str, producer: str, generation: int) -> bool:
        return self.can_submit(dev_id, producer, generation)

    def get_generation(self, dev_id: str) -> int:
        with self._lock:
            return self._generations.get(dev_id, 0)

    def get_owner(self, dev_id: str) -> str:
        with self._lock:
            return self._owners.get(dev_id, OutputProducer.IDLE)
