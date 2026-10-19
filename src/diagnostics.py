from __future__ import annotations
import threading
import time
from collections import deque
from typing import Dict, Any, List

class DeviceDiagnostics:
    """Thread-safe performance instrumentation and telemetry for a Tapo light strip."""

    def __init__(self, dev_id: str):
        self.dev_id = dev_id
        self._lock = threading.Lock()

        # Timestamps
        self._start_time = time.time()
        self._last_send_time = 0.0
        self._session_start_time = time.time()

        # Frame counters
        self.frames_generated: int = 0
        self.frames_sent: int = 0
        self.frames_dropped: int = 0

        # Rolling 1-second timestamps for FPS calculations
        self._sent_timestamps: deque[float] = deque()
        self._gen_timestamps: deque[float] = deque()

        # RTT & Latency Tracking
        self.rtt_ms: float = 0.0
        self._rtt_samples: deque[float] = deque(maxlen=60)
        self.min_rtt_ms: float = 0.0
        self.max_rtt_ms: float = 0.0

        # End-to-End Latency Tracking (Render submission -> HTTP response + 0.5*pacing)
        self.frame_age_ms: float = 0.0
        self.total_latency_ms: float = 0.0
        self._latency_samples: deque[float] = deque(maxlen=60)
        self.median_latency_ms: float = 0.0
        self.p95_latency_ms: float = 0.0
        self.resume_latency_ms: float = 0.0

        # Reliability & Errors
        self.error_count: int = 0
        self.timeout_count: int = 0
        self.reconnect_count: int = 0
        self._error_timestamps: deque[float] = deque()
        self._handshake_timestamps: deque[float] = deque()
        self.handshakes_per_min: float = 0.0
        self.errors_per_min: float = 0.0
        self.handshake_warning: bool = False
        self.last_error: str | None = None
        self.status: str = "disconnected"
        self.pacing_delay_ms: float = 0.0

        # Per-Stage Instrumentation (Phase 0)
        self._stage_samples: Dict[str, deque[float]] = {
            "analysis": deque(maxlen=60),
            "render": deque(maxlen=60),
            "queue": deque(maxlen=60),
            "http": deque(maxlen=60),
            "e2e": deque(maxlen=60),
        }
        self.stage_stats: Dict[str, Dict[str, float]] = {
            k: {"median_ms": 0.0, "p95_ms": 0.0} for k in self._stage_samples
        }
        self.backlog_warnings: int = 0
        self.last_backlog_warning: str | None = None

    def record_frame_generated(self):
        now = time.time()
        with self._lock:
            self.frames_generated += 1
            self._gen_timestamps.append(now)
            cutoff = now - 1.0
            while self._gen_timestamps and self._gen_timestamps[0] < cutoff:
                self._gen_timestamps.popleft()

    def record_frame_dropped(self):
        with self._lock:
            self.frames_dropped += 1

    def record_frame_sent(self, rtt_seconds: float, pacing_delay_seconds: float = 0.0, frame_age_seconds: float = 0.0):
        now = time.time()
        rtt_ms = max(0.1, rtt_seconds * 1000.0)
        pacing_ms = pacing_delay_seconds * 1000.0
        frame_age_ms = max(0.0, frame_age_seconds * 1000.0)
        # End-to-end latency: frame age + HTTP RTT + half the pacing cooldown
        total_lat = frame_age_ms + rtt_ms + (0.5 * pacing_ms)

        with self._lock:
            self.frames_sent += 1
            self._last_send_time = now
            self._sent_timestamps.append(now)
            cutoff = now - 1.0
            while self._sent_timestamps and self._sent_timestamps[0] < cutoff:
                self._sent_timestamps.popleft()

            self._rtt_samples.append(rtt_ms)
            self.rtt_ms = sum(self._rtt_samples) / len(self._rtt_samples)
            if self.min_rtt_ms == 0.0 or rtt_ms < self.min_rtt_ms:
                self.min_rtt_ms = rtt_ms
            if rtt_ms > self.max_rtt_ms:
                self.max_rtt_ms = rtt_ms

            self.frame_age_ms = frame_age_ms
            self.pacing_delay_ms = pacing_ms
            self.total_latency_ms = total_lat
            self._latency_samples.append(total_lat)

            # Compute median and p95
            sorted_lat = sorted(self._latency_samples)
            n = len(sorted_lat)
            mid = n // 2
            self.median_latency_ms = sorted_lat[mid] if n % 2 != 0 else (sorted_lat[mid - 1] + sorted_lat[mid]) / 2.0
            p95_idx = min(n - 1, int(round(0.95 * (n - 1))))
            self.p95_latency_ms = sorted_lat[p95_idx]

            self.status = "connected"

    def record_resume_latency(self, latency_ms: float):
        with self._lock:
            self.resume_latency_ms = max(0.0, float(latency_ms))

    def record_error(self, message: str, is_timeout: bool = False):
        now = time.time()
        with self._lock:
            self.error_count += 1
            if is_timeout:
                self.timeout_count += 1
            self.last_error = message
            self.status = "error" if not is_timeout else "timeout"
            self._error_timestamps.append(now)
            cutoff = now - 60.0
            while self._error_timestamps and self._error_timestamps[0] < cutoff:
                self._error_timestamps.popleft()
            self.errors_per_min = float(len(self._error_timestamps))

    def record_reconnect(self):
        now = time.time()
        with self._lock:
            self.reconnect_count += 1
            self._session_start_time = now
            self.status = "reconnecting"
            self._handshake_timestamps.append(now)
            cutoff = now - 60.0
            while self._handshake_timestamps and self._handshake_timestamps[0] < cutoff:
                self._handshake_timestamps.popleft()
            self.handshakes_per_min = float(len(self._handshake_timestamps))
            if self.handshakes_per_min > 2.0:
                self.handshake_warning = True
                from src.logger import log
                log.warning(f"[{self.dev_id}] Warning: handshakes exceed 2/min ({self.handshakes_per_min:.1f}/min)!")

    def record_stage_timing(
        self,
        t_audio_recv: float,
        t_analysis_done: float,
        t_frame_rendered: float,
        t_frame_submitted: float,
        t_http_sent: float,
        t_http_resp: float,
    ):
        """
        Records per-stage latency across the pipeline:
          t_audio_recv -> t_analysis_done -> t_frame_rendered -> t_frame_submitted -> t_http_sent -> t_http_resp
        """
        analysis_ms = max(0.0, (t_analysis_done - t_audio_recv) * 1000.0)
        render_ms = max(0.0, (t_frame_rendered - t_analysis_done) * 1000.0)
        queue_ms = max(0.0, (t_http_sent - t_frame_submitted) * 1000.0)
        http_ms = max(0.0, (t_http_resp - t_http_sent) * 1000.0)
        e2e_ms = max(0.0, (t_http_resp - t_audio_recv) * 1000.0)

        with self._lock:
            self._stage_samples["analysis"].append(analysis_ms)
            self._stage_samples["render"].append(render_ms)
            self._stage_samples["queue"].append(queue_ms)
            self._stage_samples["http"].append(http_ms)
            self._stage_samples["e2e"].append(e2e_ms)

            for stage_name, samples in self._stage_samples.items():
                if samples:
                    sorted_s = sorted(samples)
                    n = len(sorted_s)
                    mid = n // 2
                    med = sorted_s[mid] if n % 2 != 0 else (sorted_s[mid - 1] + sorted_s[mid]) / 2.0
                    p95_idx = min(n - 1, int(round(0.95 * (n - 1))))
                    self.stage_stats[stage_name] = {
                        "median_ms": round(med, 2),
                        "p95_ms": round(sorted_s[p95_idx], 2),
                    }

    def record_backlog_warning(self, analysis_ms: float, block_dur_ms: float):
        with self._lock:
            self.backlog_warnings += 1
            self.last_backlog_warning = (
                f"Analysis time {analysis_ms:.2f}ms exceeded 80% of block {block_dur_ms:.2f}ms"
            )

    def set_status(self, status: str):
        with self._lock:
            self.status = status

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            # Purge older than 1s
            cutoff = now - 1.0
            while self._sent_timestamps and self._sent_timestamps[0] < cutoff:
                self._sent_timestamps.popleft()
            while self._gen_timestamps and self._gen_timestamps[0] < cutoff:
                self._gen_timestamps.popleft()

            send_fps = len(self._sent_timestamps)
            render_fps = len(self._gen_timestamps)

            drop_rate = 0.0
            if self.frames_generated > 0:
                drop_rate = round((self.frames_dropped / self.frames_generated) * 100.0, 1)

            return {
                "device_id": self.dev_id,
                "status": self.status,
                "send_fps": send_fps,
                "render_fps": render_fps,
                "rtt_ms": round(self.rtt_ms, 1),
                "min_rtt_ms": round(self.min_rtt_ms, 1),
                "max_rtt_ms": round(self.max_rtt_ms, 1),
                "frame_age_ms": round(self.frame_age_ms, 1),
                "total_latency_ms": round(self.total_latency_ms, 1),
                "median_latency_ms": round(self.median_latency_ms, 1),
                "p95_latency_ms": round(self.p95_latency_ms, 1),
                "resume_latency_ms": round(self.resume_latency_ms, 1),
                "pacing_delay_ms": round(self.pacing_delay_ms, 1),
                "frames_generated": self.frames_generated,
                "frames_sent": self.frames_sent,
                "frames_dropped": self.frames_dropped,
                "drop_rate_pct": drop_rate,
                "error_count": self.error_count,
                "timeout_count": self.timeout_count,
                "reconnect_count": self.reconnect_count,
                "handshakes_per_min": round(self.handshakes_per_min, 2),
                "errors_per_min": round(self.errors_per_min, 2),
                "mean_response_time_ms": round(self.rtt_ms, 1),
                "p95_response_time_ms": round(self.p95_latency_ms, 1),
                "handshake_warning": self.handshake_warning,
                "last_error": self.last_error,
                "session_age_s": int(now - self._session_start_time),
                "uptime_s": int(now - self._start_time),
                "stages": {k: dict(v) for k, v in self.stage_stats.items()},
                "stage_latencies": {k: dict(v) for k, v in self.stage_stats.items()},
                "backlog_warnings": self.backlog_warnings,
                "last_backlog_warning": self.last_backlog_warning,
            }
