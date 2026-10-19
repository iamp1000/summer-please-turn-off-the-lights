from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Sequence
import time
import threading

# ── 1. Frame Bus Packet & Producers ──────────────────────────────────────────

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
    segments: Optional[List[List[int]]] = None      # 50 zones for L930: [[h, s, v], ...]
    hsv: Optional[Sequence[int]] = None             # 1 zone for L900: (h, s, v)
    brightness: int = 100
    transition: int = 0
    pre_corrected: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── 2. Decoupled Frame Bus ────────────────────────────────────────────────────

class FrameBus:
    """
    Decoupled publish-subscribe message bus for lighting frames.
    Every active producer (audio, screen sync, effects, static scenes, composite follower)
    publishes its rendered frames here.
    Consumers (hardware senders, web zone preview, composite sync, telemetry) read exclusively
    from the bus, eliminating all private attribute access (_rendered_segs, last_submitted_frame).
    """

    def __init__(self, arbiter: Optional[OutputArbiter] = None):
        self._arbiter = arbiter
        self._latest_frames: Dict[str, FramePacket] = {}
        self._subscribers: Dict[str, List[Callable[[FramePacket], None]]] = {}
        self._lock = threading.RLock()

    def set_arbiter(self, arbiter: OutputArbiter):
        with self._lock:
            self._arbiter = arbiter

    def publish(self, packet: FramePacket) -> bool:
        """
        Publishes a frame packet for a device.
        If an OutputArbiter is attached, verifies that the publishing producer has active ownership.
        """
        with self._lock:
            if self._arbiter and not self._arbiter.can_submit(packet.dev_id, packet.producer):
                # Unauthorized submission from inactive or superseded producer
                return False

            self._latest_frames[packet.dev_id] = packet
            callbacks = list(self._subscribers.get(packet.dev_id, []))
            global_callbacks = list(self._subscribers.get("*", []))

        # Notify subscribers outside the lock to prevent re-entrant deadlocks
        for cb in callbacks + global_callbacks:
            try:
                cb(packet)
            except Exception:
                pass

        return True

    def subscribe(self, dev_id: str, callback: Callable[[FramePacket], None]):
        """Subscribe to frame publications for a specific device ('strip1', 'strip2', or '*' for all)."""
        with self._lock:
            if dev_id not in self._subscribers:
                self._subscribers[dev_id] = []
            if callback not in self._subscribers[dev_id]:
                self._subscribers[dev_id].append(callback)

    def unsubscribe(self, dev_id: str, callback: Callable[[FramePacket], None]):
        with self._lock:
            if dev_id in self._subscribers and callback in self._subscribers[dev_id]:
                self._subscribers[dev_id].remove(callback)

    def get_latest_frame(self, dev_id: str) -> Optional[FramePacket]:
        """Returns the most recent FramePacket published for dev_id."""
        with self._lock:
            return self._latest_frames.get(dev_id)


# ── 3. Output Arbiter ─────────────────────────────────────────────────────────

class OutputArbiter:
    """
    Guarantees strict single-producer output ownership per light strip.
    Each strip has exactly one active producer (static, effect, audio, screen_sync, composite_follower).
    Starting a producer cleanly stops or pauses the previous one.
    No two producers may submit to the same strip simultaneously.
    """

    def __init__(self):
        self._owners: Dict[str, str] = {}               # dev_id -> active producer name
        self._relinquish_cbs: Dict[str, Callable] = {}  # dev_id -> callback to stop old producer
        self._lock = threading.RLock()

    def claim_output(self, dev_id: str, producer: str, on_relinquish: Optional[Callable] = None) -> bool:
        """
        Claims exclusive output ownership for dev_id under producer.
        If a different producer was active, cleanly executes its on_relinquish callback.
        """
        with self._lock:
            old_producer = self._owners.get(dev_id, OutputProducer.IDLE)
            old_cb = self._relinquish_cbs.get(dev_id)

            if old_producer == producer:
                # Same producer refreshing ownership
                self._relinquish_cbs[dev_id] = on_relinquish
                return True

            # Stop the previous producer cleanly
            if old_cb:
                try:
                    old_cb()
                except Exception:
                    pass

            self._owners[dev_id] = producer
            self._relinquish_cbs[dev_id] = on_relinquish
            return True

    def release_output(self, dev_id: str, producer: str):
        """Releases output ownership if currently held by producer."""
        with self._lock:
            if self._owners.get(dev_id) == producer:
                self._owners[dev_id] = OutputProducer.IDLE
                self._relinquish_cbs.pop(dev_id, None)

    def can_submit(self, dev_id: str, producer: str) -> bool:
        """Checks if producer is authorized to submit frames to dev_id."""
        with self._lock:
            owner = self._owners.get(dev_id, OutputProducer.IDLE)
            if owner == producer:
                return True
            # When IDLE, only permit static scenes or idle release packets, never competing stream loops
            if owner == OutputProducer.IDLE and producer in (OutputProducer.STATIC, OutputProducer.IDLE):
                return True
            return False

    def get_owner(self, dev_id: str) -> str:
        """Returns the name of the active producer for dev_id."""
        with self._lock:
            return self._owners.get(dev_id, OutputProducer.IDLE)
