from __future__ import annotations
import asyncio
import threading
import time
from typing import Any, Callable, Coroutine, Optional, List, Tuple
from src.diagnostics import DeviceDiagnostics
from src.logger import log

class LatestFrameSender:
    """
    Decoupled "Latest Frame Wins" transmitter with Phase R Board Safety:
    - Send budget: max_updates_per_s (default 5 for music, 2 for movie).
    - Rate control (AIMD): if response time > 400 ms or failure occurs, drops to 1 update/s
      for 30 s and then gradually ramps back up.
    - Frame delta gating: skips frame if max per-zone change is below min_zone_delta.
    - Idle protection: drops stale frames and prevents board queue overflow.
    """

    def __init__(
        self,
        dev_id: str,
        transmit_fn: Callable[[Any], Coroutine[Any, Any, bool]],
        diagnostics: DeviceDiagnostics,
        loop: asyncio.AbstractEventLoop,
        max_updates_per_s: float = 5.0,
        min_zone_delta: int = 3,
    ):
        self.dev_id = dev_id
        self._transmit_fn = transmit_fn
        self.diagnostics = diagnostics
        self._loop = loop

        self.max_updates_per_s = float(max_updates_per_s)
        self.min_zone_delta = int(min_zone_delta)

        self._lock = threading.Lock()
        self._pending_frame: Any | None = None
        self._event = asyncio.Event()

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._pacing_delay: float = 0.005  # Initial cooldown

        # AIMD Rate Control
        self._aimd_rate_cap: float = self.max_updates_per_s
        self._aimd_drop_until: float = 0.0

        # Frame delta tracking
        self._last_sent_segments: Optional[List[List[int]]] = None
        self._last_sent_hsb: Optional[Tuple[int, int, int]] = None
        # L930 frames have per-zone HSV plus an independent master-brightness field.
        self._last_sent_master_brightness: Optional[int] = None
        self._last_transmit_start: float = 0.0
        self._frame_authorizer: Optional[Callable[[Any], bool]] = None

    def set_frame_authorizer(self, authorizer: Optional[Callable[[Any], bool]]):
        """Install final ownership validation immediately before transmission."""
        self._frame_authorizer = authorizer

    def set_send_budget(self, max_updates_per_s: float):
        """Dynamically adjusts max updates per second (e.g. 5 for music, 2 for movie)."""
        self.max_updates_per_s = max(0.5, float(max_updates_per_s))
        if time.time() > self._aimd_drop_until:
            self._aimd_rate_cap = self.max_updates_per_s

    def start(self):
        """Starts the background sender worker task on the event loop."""
        if self._running:
            return
        self._running = True

        try:
            cur_loop = asyncio.get_running_loop()
        except RuntimeError:
            cur_loop = None

        if cur_loop == self._loop:
            self._task = self._loop.create_task(self._worker_loop(), name=f"FrameSender-{self.dev_id}")
        else:
            self._loop.call_soon_threadsafe(
                lambda: setattr(self, "_task", self._loop.create_task(self._worker_loop(), name=f"FrameSender-{self.dev_id}"))
            )

    def stop(self):
        """Stops the worker and purges any pending frames."""
        self._running = False
        self.clear()
        if self._task and not self._task.done():
            self._loop.call_soon_threadsafe(self._task.cancel)

    def submit_frame(self, frame: Any):
        """
        Thread-safe frame submission from any render worker thread.
        Latest frame overwrites pending frame. Stale frames are dropped immediately.
        """
        if not self._running:
            return

        submit_time = time.perf_counter()
        if isinstance(frame, dict):
            frame.setdefault("t_frame_submitted", submit_time)

        with self._lock:
            if self._pending_frame is not None:
                self.diagnostics.record_frame_dropped()
            self._pending_frame = (frame, submit_time)
            self.diagnostics.record_frame_generated()

        # Signal the event loop to wake up the transmitter
        try:
            cur_loop = asyncio.get_running_loop()
        except RuntimeError:
            cur_loop = None

        if cur_loop == self._loop:
            self._event.set()
        else:
            self._loop.call_soon_threadsafe(self._event.set)

    def clear(self):
        """Immediately flushes pending frame so nothing is transmitted after power-off."""
        with self._lock:
            self._pending_frame = None
            self._last_sent_segments = None
            self._last_sent_hsb = None
            self._last_sent_master_brightness = None

        try:
            cur_loop = asyncio.get_running_loop()
        except RuntimeError:
            cur_loop = None

        if cur_loop == self._loop:
            self._event.clear()
        else:
            self._loop.call_soon_threadsafe(self._event.clear)

    def _is_change_significant(self, frame: Any) -> bool:
        """Checks if frame differs significantly (> min_zone_delta) from last sent frame."""
        if self._last_sent_segments is None and self._last_sent_hsb is None:
            return True

        # 50-zone dictionary or list format
        segs = None
        if isinstance(frame, dict) and "segments" in frame:
            segs = frame["segments"]
        elif isinstance(frame, list):
            segs = frame

        if segs is not None:
            if self._last_sent_segments is None or len(self._last_sent_segments) != len(segs):
                return True
            # A dimmer movement can leave each zone HSV unchanged because the
            # controller also applies this independent master brightness value.
            if (isinstance(frame, dict) and "segments" in frame
                    and frame.get("brightness") is not None
                    and frame.get("brightness") != self._last_sent_master_brightness):
                return True
            max_delta = 0
            for i in range(min(len(segs), len(self._last_sent_segments))):
                s_new = segs[i]
                s_old = self._last_sent_segments[i]
                diff_v = abs(int(s_new[2]) - int(s_old[2]))
                diff_s = abs(int(s_new[1]) - int(s_old[1]))
                diff_h = (abs(int(s_new[0]) - int(s_old[0])) + 180) % 360 - 180
                max_delta = max(max_delta, diff_v, diff_s, abs(diff_h))
                if max_delta >= self.min_zone_delta:
                    return True
            return False

        # Single-zone (h, s, b)
        if isinstance(frame, dict) and "h" in frame:
            hsb = (frame.get("h", 0), frame.get("s", 0), frame.get("b", 0))
        elif isinstance(frame, (tuple, list)) and len(frame) >= 3:
            hsb = (frame[0], frame[1], frame[2])
        else:
            return True

        if self._last_sent_hsb is None:
            return True
        diff_v = abs(hsb[2] - self._last_sent_hsb[2])
        diff_s = abs(hsb[1] - self._last_sent_hsb[1])
        diff_h = (abs(hsb[0] - self._last_sent_hsb[0]) + 180) % 360 - 180
        return max(diff_v, diff_s, abs(diff_h)) >= self.min_zone_delta

    async def _worker_loop(self):
        """Main sender loop running strictly inside the asyncio event loop."""
        while self._running:
            # Sleep until a new frame is submitted
            await self._event.wait()
            if not self._running:
                break

            self._event.clear()
            # Atomically pop newest frame and submit timestamp
            with self._lock:
                item = self._pending_frame
                self._pending_frame = None

            if item is None:
                continue

            if isinstance(item, tuple) and len(item) == 2:
                frame, submit_time = item
                frame_age = time.perf_counter() - submit_time
            else:
                frame = item
                submit_time = time.perf_counter()
                frame_age = 0.0

            # Skip frame if max per-zone change is below threshold (unless power-off/zero frame, or latency test frame with timestamps)
            is_zero_frame = False
            is_timestamped = isinstance(frame, dict) and "t_audio_recv" in frame
            if isinstance(frame, dict) and frame.get("brightness", 100) == 0:
                is_zero_frame = True
            elif isinstance(frame, list) and all(x[2] == 0 for x in frame if len(x) >= 3):
                is_zero_frame = True

            if not is_zero_frame and not is_timestamped and not self._is_change_significant(frame):
                self.diagnostics.record_frame_dropped()
                continue

            # Revalidate after popping the queue: ownership can change before this send.
            authorizer = self._frame_authorizer
            if authorizer is not None:
                try:
                    authorized = bool(authorizer(frame))
                except Exception:
                    authorized = False
                if not authorized:
                    self.diagnostics.record_frame_dropped()
                    continue

            # Transmit frame and measure latency
            t_http_sent = time.perf_counter()
            self._last_transmit_start = t_http_sent
            success = False
            try:
                success = await self._transmit_fn(frame)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.diagnostics.record_error(f"Transmission error: {e}")
                log.error(f"[{self.dev_id}] Sender transmission error: {e}")

            t_http_resp = time.perf_counter()
            dt = t_http_resp - t_http_sent
            now = time.time()

            # Record last sent state
            if success:
                if isinstance(frame, dict) and "segments" in frame:
                    self._last_sent_segments = [list(x) for x in frame["segments"]]
                    if frame.get("brightness") is not None:
                        self._last_sent_master_brightness = int(frame["brightness"])
                elif isinstance(frame, list):
                    self._last_sent_segments = [list(x) for x in frame]
                elif isinstance(frame, dict) and "h" in frame:
                    self._last_sent_hsb = (frame["h"], frame["s"], frame["b"])
                elif isinstance(frame, (tuple, list)) and len(frame) >= 3:
                    self._last_sent_hsb = (frame[0], frame[1], frame[2])

            # ── Phase R: AIMD Rate Control ──
            if not success or dt > 0.400:
                # Drop to 1 update/s for 30 s on slow response or failure
                self._aimd_rate_cap = 1.0
                self._aimd_drop_until = now + 30.0
                log.warning(
                    f"[{self.dev_id}] AIMD triggered (rtt={dt*1000:.0f}ms, success={success}). "
                    f"Dropped to 1 update/s for 30s."
                )
            else:
                if now > self._aimd_drop_until and self._aimd_rate_cap < self.max_updates_per_s:
                    # Gradually ramp back up (+0.5 update/s per second)
                    self._aimd_rate_cap = min(self.max_updates_per_s, self._aimd_rate_cap + 0.5)

            if success:
                # Minimum 2ms pacing delay
                self._pacing_delay = max(0.002, min(0.025, dt * 0.08))
                self.diagnostics.record_frame_sent(dt, self._pacing_delay, frame_age_seconds=frame_age)

                # Record per-stage latency breakdown if timestamps are present
                if isinstance(frame, dict) and "t_audio_recv" in frame:
                    self.diagnostics.record_stage_timing(
                        t_audio_recv=frame["t_audio_recv"],
                        t_analysis_done=frame.get("t_analysis_done", frame["t_audio_recv"]),
                        t_frame_rendered=frame.get("t_frame_rendered", frame["t_audio_recv"]),
                        t_frame_submitted=submit_time,
                        t_http_sent=t_http_sent,
                        t_http_resp=t_http_resp,
                    )
            else:
                self._pacing_delay = min(0.100, self._pacing_delay * 1.5)

            # ── Enforce True Frame-Rate Cap based on elapsed time since transmission started ──
            if self.max_updates_per_s > 0:
                target_interval = 1.0 / max(0.5, self._aimd_rate_cap)
                elapsed_since_start = time.perf_counter() - self._last_transmit_start
                remaining = target_interval - elapsed_since_start
                wait_time = max(self._pacing_delay, remaining)
            else:
                wait_time = self._pacing_delay

            if wait_time > 0:
                await asyncio.sleep(wait_time)
