from __future__ import annotations
import time
import pytest
from src.diagnostics import DeviceDiagnostics

def test_diagnostics_initial_state():
    diag = DeviceDiagnostics(dev_id="test_strip")
    snap = diag.snapshot()
    assert snap["device_id"] == "test_strip"
    assert snap["frames_generated"] == 0
    assert snap["frames_sent"] == 0
    assert snap["frames_dropped"] == 0
    assert snap["drop_rate_pct"] == 0.0
    assert snap["send_fps"] == 0
    assert snap["render_fps"] == 0
    assert snap["rtt_ms"] == 0.0
    assert snap["error_count"] == 0
    assert snap["reconnect_count"] == 0

def test_diagnostics_frame_counters_and_drops():
    diag = DeviceDiagnostics(dev_id="test_strip")
    
    # Simulate generating 10 frames where 8 were dropped (latest frame wins) and 2 sent
    for _ in range(10):
        diag.record_frame_generated()
    for _ in range(8):
        diag.record_frame_dropped()
    diag.record_frame_sent(0.080, 0.010)
    diag.record_frame_sent(0.070, 0.010)

    snap = diag.snapshot()
    assert snap["frames_generated"] == 10
    assert snap["frames_sent"] == 2
    assert snap["frames_dropped"] == 8
    assert snap["drop_rate_pct"] == 80.0
    assert snap["send_fps"] == 2
    assert snap["render_fps"] == 10
    # Average of 80ms and 70ms = 75ms
    assert snap["rtt_ms"] == 75.0
    assert snap["min_rtt_ms"] == 70.0
    assert snap["max_rtt_ms"] == 80.0

def test_diagnostics_error_and_reconnect():
    diag = DeviceDiagnostics(dev_id="test_strip")
    diag.record_error("Network timeout", is_timeout=True)
    snap = diag.snapshot()
    assert snap["error_count"] == 1
    assert snap["timeout_count"] == 1
    assert snap["last_error"] == "Network timeout"
    assert snap["status"] == "timeout"

    diag.record_reconnect()
    snap2 = diag.snapshot()
    assert snap2["reconnect_count"] == 1
    assert snap2["status"] == "reconnecting"
