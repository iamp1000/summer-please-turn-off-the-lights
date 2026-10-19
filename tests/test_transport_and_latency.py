from __future__ import annotations
import asyncio
import time
import pytest
import numpy as np

from src.diagnostics import DeviceDiagnostics
from src.pipeline import RenderPipeline
from src.device import LightController
from src.device_l930 import L930Controller, make_50_zone_effect
from src.visual_styles import (
    ShockwaveStyle,
    AuroraStyle,
    CometStyle,
    PlasmaStyle,
    BeatFlashAccent,
    HatSparkleAccent,
)
from src.audio_dsp import MusicAnalyzer, MusicState, Section
from src.audio_replay import SyntheticTrackGenerator
from src.frame_sender import LatestFrameSender


# ─────────────────────────────────────────────────────────────────────────────
# 1. L900 Combined Single Request Verification
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_l900_single_combined_request():
    """Verify L900 sends Hue, Saturation, and Brightness in ONE request."""
    loop = asyncio.get_running_loop()
    ctrl = LightController("127.0.0.1", "test@test.com", "secret", dev_id="mock_l900", loop=loop)

    combined_calls = []
    legacy_calls = []

    class MockClient:
        async def set_device_info(self, params):
            combined_calls.append(params)
            class SuccessRes:
                def is_success(self):
                    return True
            return SuccessRes()

    class FakeDeviceWithClient:
        is_on = True
        client = MockClient()

        async def update(self):
            pass

        async def set_hue_saturation(self, h, s):
            legacy_calls.append(("hs", h, s))

        async def set_brightness(self, b):
            legacy_calls.append(("b", b))

    async def fake_connect(config):
        return FakeDeviceWithClient()

    import src.device as dev_mod
    orig_connect = dev_mod.connect
    dev_mod.connect = fake_connect

    try:
        await ctrl.connect()
        # Transmit pre-corrected frame
        success = await ctrl.transmit_frame({"h": 210, "s": 85, "b": 70, "_pre_corrected": True})
        assert success is True
        # Combined setter must be called exactly once
        assert len(combined_calls) == 1
        assert combined_calls[0].hue == 210
        assert combined_calls[0].saturation == 85
        assert combined_calls[0].brightness == 70
        assert combined_calls[0].color_temp == 0
        # No legacy 2-round-trip calls
        assert len(legacy_calls) == 0
    finally:
        dev_mod.connect = orig_connect


# ─────────────────────────────────────────────────────────────────────────────
# 2. Lock Hygiene & Immediate Re-Auth on First Timeout
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_immediate_reauth_and_lock_hygiene():
    """Verify session timeout triggers immediate 0s re-auth without holding lock."""
    loop = asyncio.get_running_loop()
    ctrl = LightController("127.0.0.1", "test@test.com", "secret", dev_id="mock_l900", loop=loop)

    attempts = 0
    lock_was_held_during_reauth = False

    class MockClient:
        async def set_device_info(self, params):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise Exception("SESSION_TIMEOUT -1003")
            class SuccessRes:
                def is_success(self):
                    return True
            return SuccessRes()

    class FakeDevice:
        is_on = True
        client = MockClient()

        async def update(self):
            pass

    async def fake_connect(config):
        nonlocal lock_was_held_during_reauth
        # If lock was held by transmit_frame, locked() would be True
        if ctrl._lock.locked():
            lock_was_held_during_reauth = True
        return FakeDevice()

    import src.device as dev_mod
    orig_connect = dev_mod.connect
    dev_mod.connect = fake_connect

    try:
        t0 = time.perf_counter()
        await ctrl.connect()
        # Transmit frame: attempt 1 fails with SESSION_TIMEOUT, auto-reauth immediately, retry succeeds
        success = await ctrl.transmit_frame({"h": 180, "s": 90, "b": 60, "_pre_corrected": True})
        t1 = time.perf_counter()

        assert success is True
        assert attempts == 2
        # Ensure reauth did NOT sleep (elapsed time should be < 0.2s, not 0.5s or 1.0s backoff)
        assert (t1 - t0) < 0.3
        # Device lock was released before reauth
        assert lock_was_held_during_reauth is False
        # Retry passed exact same values
        assert ctrl.last_h == 180
        assert ctrl.last_s == 90
        assert ctrl.last_b == 60
    finally:
        dev_mod.connect = orig_connect


# ─────────────────────────────────────────────────────────────────────────────
# 3. Vectorized RenderPipeline True Black & Gamma 2.2 Benchmarks
# ─────────────────────────────────────────────────────────────────────────────

def test_render_pipeline_vectorized_true_black_and_speed():
    pipeline = RenderPipeline(gamma=2.2, r_calib=1.0, g_calib=0.96, b_calib=0.90, master_ceiling=1.0)

    # 1. Strict True Black Test: V=0 must result in exactly V=0 (no permanent 1% glow)
    zero_input = [[180, 100, 0] for _ in range(50)]
    corrected_zero = pipeline.correct_hsv_sequence(zero_input)
    assert len(corrected_zero) == 50
    for zone in corrected_zero:
        assert zone[2] == 0, f"Expected zone V=0, got {zone[2]}"

    # 2. Gamma 2.2 Transfer Curve: V=50% -> (0.50)^2.2 = ~21.76%
    mid_input = [[0, 100, 50] for _ in range(50)]
    corrected_mid = pipeline.correct_hsv_sequence(mid_input)
    assert 20 <= corrected_mid[0][2] <= 24, f"Gamma 2.2 mid-point expected ~22, got {corrected_mid[0][2]}"

    # 3. Full Brightness: V=100% -> V=100%
    full_input = [[0, 100, 100] for _ in range(50)]
    corrected_full = pipeline.correct_hsv_sequence(full_input)
    assert corrected_full[0][2] == 100

    # 4. Benchmarking Speed: 50 zones processed in < 0.5 ms
    test_zones = [[i * 7 % 360, 90, 80] for i in range(50)]
    iterations = 500
    t0 = time.perf_counter()
    for _ in range(iterations):
        _ = pipeline.correct_hsv_sequence(test_zones)
    t1 = time.perf_counter()
    per_frame_ms = ((t1 - t0) / iterations) * 1000.0
    print(f"\nVectorized 50-zone RenderPipeline latency: {per_frame_ms:.4f} ms per frame")
    assert per_frame_ms < 0.5, f"Vectorized color pipeline took {per_frame_ms:.3f} ms (> 0.5ms limit)"


# ─────────────────────────────────────────────────────────────────────────────
# 4. L930 Transition Parameter & Mode Dispatch Verification
# ─────────────────────────────────────────────────────────────────────────────

def test_l930_transition_parameter_and_mode_dispatch():
    # Verify make_50_zone_effect handles transitions: 0, 50, 80, 100, 150 ms
    for trans in [0, 50, 80, 100, 150]:
        dummy_zones = [[120, 80, 50]] * 50
        effect = make_50_zone_effect(dummy_zones, master_brightness=100, transition=trans, pre_corrected=True)
        assert effect.transition == trans
        assert len(effect.sequence) == 50
        assert effect.sequence[0] == [120, 80, 50]

    # Verify true black in make_50_zone_effect without max(1, vc)
    zero_zones = [[200, 100, 0]] * 50
    black_effect = make_50_zone_effect(zero_zones, master_brightness=100, transition=0, pre_corrected=True)
    assert black_effect.sequence[0][2] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Sustained Silence Power-Down & Resume Latency Measurement
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sustained_silence_power_down_and_resume():
    """Verify >3s of silence triggers turn_off(), and audio resume cleanly turns on with latency measurement."""
    from src.music_reactive_l930 import MusicReactiveL930

    power_calls = []

    class MockL930Ctrl:
        dev_id = "test_l930"
        diagnostics = DeviceDiagnostics("test_l930")
        is_on = True

        async def turn_off(self, priority=0):
            power_calls.append("off")
            self.is_on = False

        async def turn_on(self, priority=0):
            power_calls.append("on")
            self.is_on = True

        def submit_frame(self, frame):
            pass

    mock_ctrl = MockL930Ctrl()
    engine = MusicReactiveL930(
        controller=mock_ctrl,
        loop_runner=None,
        app_state={"brightness": 100},
        blocksize=1024,
    )

    # 1. Active tone
    tone = (np.sin(np.linspace(0, 100, 1024)) * 0.5).astype(np.float32)
    engine._process(tone, rms=0.35)
    assert engine._powered_down_for_silence is False

    # 2. Feed silence for >3 seconds (at 1024 samples / 44100Hz = 0.0232s per block; 160 blocks = 3.71s)
    silence = np.zeros(1024, dtype=np.float32)
    for _ in range(160):
        engine._process(silence, rms=0.0)
    await asyncio.sleep(0.01)

    assert engine._powered_down_for_silence is True
    assert "off" in power_calls

    # 3. Resume audio
    engine._process(tone, rms=0.35)
    await asyncio.sleep(0.01)
    assert engine._powered_down_for_silence is False
    assert "on" in power_calls
    assert mock_ctrl.diagnostics.resume_latency_ms >= 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 6. Render-Ahead Forward Evaluation in Visual Styles
# ─────────────────────────────────────────────────────────────────────────────

def test_visual_styles_render_ahead():
    """Verify motion modes (Comet, Aurora, Plasma, Shockwave) evaluate animation ahead by measured latency."""
    state = MusicState(
        energy=0.7,
        intensity=0.7,
        bpm=120.0,
        beat_phase=0.2,
        bar_pos=1,
        kick=1.0,
        section=Section.VERSE,
        silent=False,
    )

    # 1. Comet Style render-ahead
    comet = CometStyle()
    comet.set_params(measured_latency_s=0.0)
    segs_now = comet.render(state, dt=0.05, num_zones=50)

    # With 100ms measured latency
    comet.set_params(measured_latency_s=0.100)
    segs_ahead = comet.render(state, dt=0.05, num_zones=50)

    # Forward-evaluated positions must advance
    brightest_now = np.argmax([s[2] for s in segs_now])
    brightest_ahead = np.argmax([s[2] for s in segs_ahead])
    assert brightest_ahead >= brightest_now

    # 2. Aurora Style phase render-ahead
    aurora = AuroraStyle()
    aurora.set_params(measured_latency_s=0.0)
    a_now = aurora.render(state, dt=0.05, num_zones=50)

    aurora.set_params(measured_latency_s=0.150)
    a_ahead = aurora.render(state, dt=0.05, num_zones=50)
    assert a_now != a_ahead, "Aurora with latency lookahead must advance continuous noise curtains"

    # 3. Minimum event envelope duration >= 2 update frames (~120ms)
    beat_flash = BeatFlashAccent()
    beat_flash.render_accent(state, dt=0.016, num_zones=50, frame=[(0, 0, 0)] * 50)
    assert beat_flash.flash_env > 0.0
    # Decay over 100ms should still be active (>0)
    beat_flash.render_accent(MusicState(energy=0.5, kick=0.0, section=Section.VERSE, silent=False), dt=0.100, num_zones=50, frame=[(0, 0, 0)] * 50)
    assert beat_flash.flash_env > 0.05, f"Envelope died too fast: {beat_flash.flash_env}"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Latency Model & Diagnostics Rolling Metrics
# ─────────────────────────────────────────────────────────────────────────────

def test_latency_model_and_percentiles():
    diag = DeviceDiagnostics(dev_id="test_diag")

    # Record 60 frames with realistic RTT and frame age
    # Frame age = 15ms, RTT = 80ms, Pacing = 10ms -> Total = 15 + 80 + 5 = 100ms
    for i in range(60):
        rtt = 0.080 + (i % 10) * 0.002  # 80ms to 98ms
        diag.record_frame_sent(rtt_seconds=rtt, pacing_delay_seconds=0.010, frame_age_seconds=0.015)

    snap = diag.snapshot()
    assert 95.0 <= snap["total_latency_ms"] <= 125.0
    assert 95.0 <= snap["median_latency_ms"] <= 120.0
    assert snap["p95_latency_ms"] >= snap["median_latency_ms"]
    assert snap["frame_age_ms"] == 15.0


# ─────────────────────────────────────────────────────────────────────────────
# 8. Synthetic Click-Track Latency Benchmark
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_synthetic_click_track_e2e_latency():
    """
    Synthetic click-track latency benchmark:
    - Generates 1.0s periodic clicks (bpm=60.0).
    - Feeds chunks through MusicAnalyzer with sample clock and t_audio_recv.
    - On onset/beat/click detection, measures submit latency (t_submit - t_audio_recv)
      and triggers LatestFrameSender with simulated HTTP RTT delay.
    - Asserts submission latency is < 50ms and stage telemetry is accurately captured.
    """
    loop = asyncio.get_running_loop()
    diag = DeviceDiagnostics(dev_id="click_latency_test")

    async def mock_transmit(frame):
        # Simulate network latency of 15ms
        await asyncio.sleep(0.015)
        return True

    sender = LatestFrameSender("click_latency_test", mock_transmit, diag, loop)
    sender.start()

    sr = 44100
    bs = 1024
    audio = SyntheticTrackGenerator.generate_click_track(bpm=60.0, duration=3.5, samplerate=sr)
    analyzer = MusicAnalyzer(samplerate=sr, blocksize=bs, sensitivity=1.0)

    n_blocks = len(audio) // bs
    click_submit_latencies = []

    try:
        for i in range(n_blocks):
            block = audio[i * bs : (i + 1) * bs]
            now_sec = (i * bs) / float(sr)
            t_recv = time.perf_counter()

            st = analyzer.process_samples(block, now=now_sec, t_recv=t_recv)
            t_analysis = time.perf_counter()

            if st.onset or st.kick > 0.4 or getattr(st, "beat", False):
                t_rendered = time.perf_counter()
                frame = {
                    "segments": [[200, 100, 100]] * 50,
                    "t_audio_recv": t_recv,
                    "t_analysis_done": t_analysis,
                    "t_frame_rendered": t_rendered,
                }
                sender.submit_frame(frame)
                t_submitted = time.perf_counter()
                submit_lat_ms = (t_submitted - t_recv) * 1000.0
                click_submit_latencies.append(submit_lat_ms)
                # Allow async sender worker to service queue
                await asyncio.sleep(0.025)

        # Allow final frame to flush through transmitter
        await asyncio.sleep(0.050)
    finally:
        sender.stop()

    assert len(click_submit_latencies) >= 2, f"Expected at least 2 click onsets detected, got {len(click_submit_latencies)}"
    for lat in click_submit_latencies:
        assert lat < 50.0, f"Submit latency {lat:.2f}ms exceeded 50ms budget"

    snap = diag.snapshot()
    stage_lat = snap.get("stage_latencies", {})
    assert "analysis" in stage_lat
    assert stage_lat["analysis"]["median_ms"] < 25.0
    assert "http" in stage_lat
    assert stage_lat["http"]["median_ms"] >= 10.0
    assert "e2e" in stage_lat
    assert stage_lat["e2e"]["median_ms"] < 100.0
    assert snap["frames_sent"] >= 2
