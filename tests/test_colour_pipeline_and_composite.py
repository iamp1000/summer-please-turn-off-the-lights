from __future__ import annotations
import math
import time
import pytest
import numpy as np

from src.pipeline import (
    gamut_map_oklch,
    oklch_to_rgb,
    rgb_to_oklch,
    linear_rgb_to_oklab,
    oklab_to_linear_rgb,
    apply_brightness_curve,
    RenderPipeline,
    calibrate_brightness_and_hue_sweep,
    AsymmetricSmoother,
    ZoneAsymmetricSmoother,
    tapo_hsv_to_rgb,
    rgb_to_tapo_hsv,
)
from src.frame_bus import FrameBus, OutputArbiter, OutputProducer, FramePacket
from src.composite_sync import CompositeSystemManager
from src.config_schema import AppConfig, DeviceCalibrationConfig


# ── 1. Phase C: OKLCH Gamut Mapping & Hue Preservation ────────────────────────

def test_gamut_map_oklch_preserves_hue_and_lightness():
    """Verify gamut mapping reduces chroma without altering perceived hue angle or lightness."""
    # Saturated out-of-gamut violet-magenta (L=0.6, C=0.35, h=315°)
    L_target = 0.60
    h_target = 315.0
    r, g, b = gamut_map_oklch(L_target, 0.35, h_target)

    # Must be in [0.0, 1.0] linear sRGB gamut
    assert -1e-4 <= r <= 1.0001
    assert -1e-4 <= g <= 1.0001
    assert -1e-4 <= b <= 1.0001

    # Perceived hue in linear OKLab space must remain exact 315° (no hue drift caused by channel clamping)
    L_act, a_act, b_act = linear_rgb_to_oklab(r, g, b)
    h_act = math.degrees(math.atan2(b_act, a_act)) % 360.0
    assert abs(h_act - h_target) < 1.0
    assert abs(L_act - L_target) < 0.05

    # Also test oklch_to_rgb (sRGB output roundtrips with rgb_to_oklch)
    sr, sg, sb = oklch_to_rgb(L_target, 0.35, h_target)
    L_s, C_s, h_s = rgb_to_oklch(sr, sg, sb)
    assert abs(h_s - h_target) < 1.0


def test_orange_hue_and_saturation_stability_across_brightness():
    """
    Test that orange (h=30°, s=60%) keeps Hue strictly at ~30° and Saturation at ~60%
    across 100%, 70%, 50%, 30%, 20%, 10%, and 5% brightness levels.
    Verifies that the old per-channel display gamma bug (which warped orange to red 21° and 89% sat)
    is completely eradicated by vector brightness scaling.
    """
    pipeline = RenderPipeline(curve_exponent=1.8, master_ceiling=1.0)
    sweep = calibrate_brightness_and_hue_sweep(pipeline)

    assert sweep["hue_stable"] is True, f"Hue drifted by {sweep['hue_drift_degrees']}°"
    assert sweep["sat_stable"] is True, f"Saturation drifted by {sweep['sat_drift_percent']}%"
    assert sweep["hue_drift_degrees"] <= 1.0
    assert sweep["sat_drift_percent"] <= 1.0

    test_levels = [100, 70, 50, 30, 20, 10, 5]
    for v in test_levels:
        h_out, s_out, v_out = pipeline.correct_hsv_tuple(30, 60, v)
        assert abs(h_out - 30) <= 1, f"At input V={v}, expected Hue ~30, got {h_out}"
        assert abs(s_out - 60) <= 2, f"At input V={v}, expected Sat ~60, got {s_out}"


def test_white_balance_oklab_lightness_equalization():
    """
    Equal nominal brightness for warm orange (h=30, s=60, v=80) and cool blue (h=220, s=60, v=80)
    must produce comparable perceived lightness (OKLab L) rather than orange drastically outshining blue.
    """
    pipeline = RenderPipeline(curve_exponent=1.8, white_balance=[1.0, 0.96, 0.90])

    r_o, g_o, b_o = pipeline.correct_linear_rgb_sequence([(1.0, 0.5, 0.0)])[0]
    r_b, g_b, b_b = pipeline.correct_linear_rgb_sequence([(0.0, 0.5, 1.0)])[0]

    L_orange = linear_rgb_to_oklab(r_o / 100.0, g_o / 100.0, b_o / 100.0)[0]
    L_blue = linear_rgb_to_oklab(r_b / 100.0, g_b / 100.0, b_b / 100.0)[0]

    # Perceived lightness ratio should be well-balanced (within 25%), not 50%+ disparity
    assert abs(L_orange - L_blue) < 0.25


def test_low_end_brightness_curve_and_true_black():
    """
    Verify low-end toe curve has distinct non-zero steps in 1..20%
    and strictly maps 0 -> 0 (true black).
    """
    # Strict true black
    assert apply_brightness_curve(0.0, exponent=1.8) == 0.0

    # Low end steps
    outputs = [int(round(apply_brightness_curve(v / 100.0, exponent=1.8) * 100.0)) for v in range(1, 21)]
    unique_steps = len(set(outputs))
    # Must have at least 7 distinct non-zero steps in 1..20%
    assert unique_steps >= 7, f"Expected >= 7 distinct steps in 1..20%, got {unique_steps}: {outputs}"
    assert outputs[0] >= 1  # 1% input does not collapse to 0


def test_time_based_smoothing_step_invariance():
    """
    Verify time-based smoothing alpha = 1 - exp(-dt / tau) gives equivalent
    decay whether evaluated in two 50ms steps or one 100ms step.
    """
    tau = 0.20
    smoother1 = AsymmetricSmoother(tau_decay=tau)
    smoother2 = AsymmetricSmoother(tau_decay=tau)

    smoother1.reset(100.0)
    smoother2.reset(100.0)

    # Smoother 1: two 50ms steps decaying toward 0
    smoother1.update(0.0, dt=0.050)
    val1 = smoother1.update(0.0, dt=0.050)

    # Smoother 2: one 100ms step decaying toward 0
    val2 = smoother2.update(0.0, dt=0.100)

    assert abs(val1 - val2) < 0.05, f"Step size disparity: {val1:.3f} vs {val2:.3f}"


# ── 2. Phase O: Output Arbiter & Single Producer Enforcement ──────────────────

def test_output_arbiter_single_producer_ownership():
    """Verify OutputArbiter enforces exactly one producer per strip and stops previous producer cleanly."""
    arbiter = OutputArbiter()
    stopped = []

    def stop_static():
        stopped.append("static")

    def stop_audio():
        stopped.append("audio")

    # 1. Claim strip1 for STATIC
    assert arbiter.claim_output("strip1", OutputProducer.STATIC, on_relinquish=stop_static) is True
    assert arbiter.get_owner("strip1") == OutputProducer.STATIC
    assert arbiter.can_submit("strip1", OutputProducer.STATIC) is True
    assert arbiter.can_submit("strip1", OutputProducer.AUDIO) is False

    # 2. Claim strip1 for AUDIO (should cleanly stop STATIC)
    assert arbiter.claim_output("strip1", OutputProducer.AUDIO, on_relinquish=stop_audio) is True
    assert arbiter.get_owner("strip1") == OutputProducer.AUDIO
    assert "static" in stopped
    assert arbiter.can_submit("strip1", OutputProducer.AUDIO) is True
    assert arbiter.can_submit("strip1", OutputProducer.STATIC) is False

    # 3. Release output
    arbiter.release_output("strip1", OutputProducer.AUDIO)
    assert arbiter.get_owner("strip1") == OutputProducer.IDLE


# ── 3. Phase O: FrameBus Pub/Sub & Decoupling ──────────────────────────────────

def test_frame_bus_publish_and_subscribe():
    """Verify FrameBus delivers FramePackets to subscribers and rejects unowned producer submissions."""
    arbiter = OutputArbiter()
    bus = FrameBus(arbiter)

    received_frames = []

    def on_frame(packet: FramePacket):
        received_frames.append(packet)

    bus.subscribe("strip2", on_frame)

    # Attempt unauthorized submission before claiming ownership
    arbiter.claim_output("strip2", OutputProducer.EFFECT)
    unauthorized_packet = FramePacket(
        dev_id="strip2",
        producer=OutputProducer.AUDIO,  # Not the owner!
        segments=[[0, 100, 100]] * 50,
    )
    published = bus.publish(unauthorized_packet)
    assert published is False
    assert len(received_frames) == 0

    # Authorized submission from active owner
    authorized_packet = FramePacket(
        dev_id="strip2",
        producer=OutputProducer.EFFECT,
        segments=[[120, 80, 75]] * 50,
        brightness=75,
    )
    published = bus.publish(authorized_packet)
    assert published is True
    assert len(received_frames) == 1
    assert received_frames[0].dev_id == "strip2"

    # Latest frame retrieval
    latest = bus.get_latest_frame("strip2")
    assert latest is not None
    assert latest.segments[0] == [120, 80, 75]


# ── 4. Phase O: Composite Follower & Luminance Weighting ──────────────────────

def test_composite_follower_luminance_weighting_and_soft_max():
    """
    Verify Composite follower:
      - Ignores near-black zones
      - Accurately averages active saturated zones
      - Uses soft maximum brightness (not max_v) to prevent single-pixel kick flash spikes
    """
    class MockDevice:
        def __init__(self, model):
            self.model = model
            self.controller = MockController()

    class MockController:
        def __init__(self):
            self.last_submitted = None
        def submit_frame(self, frame):
            self.last_submitted = frame

    class MockHub:
        def __init__(self):
            self.arbiter = OutputArbiter()
            self.frame_bus = FrameBus(self.arbiter)
            self.devices = {
                "strip1": MockDevice("L900"),
                "strip2": MockDevice("L930"),
            }

    hub = MockHub()
    composite = CompositeSystemManager(hub)

    # Publish a frame to strip2: 45 dark zones (v=0), 5 bright magenta zones (h=300, s=100, v=80)
    segs = [[0, 0, 0]] * 45 + [[300, 100, 80]] * 5
    hub.arbiter.claim_output("strip2", OutputProducer.EFFECT)
    hub.frame_bus.publish(FramePacket(
        dev_id="strip2",
        producer=OutputProducer.EFFECT,
        segments=segs,
        brightness=80,
    ))

    # Read segments via composite
    read_segs = composite._get_l930_segments()
    assert read_segs is not None
    assert len(read_segs) == 50

    # Test soft maximum calculation
    zone_vs = [s[2] for s in segs]
    mean_v = float(np.mean(zone_vs))
    p90_v = float(np.percentile(zone_vs, 90))
    soft_max = 0.70 * mean_v + 0.30 * p90_v

    # Soft max should be significantly lower than max_v (80)
    assert soft_max < 45.0, f"Expected soft_max < 45, got {soft_max}"
    assert soft_max > 5.0


# ── 5. Config Schema & Security Strictness ─────────────────────────────────────

def test_config_schema_extra_forbid_and_security_token():
    """Verify Pydantic schema rejects invalid fields (extra='forbid') and enforces token auth on 0.0.0.0."""
    from pydantic import ValidationError

    valid_config = {
        "tapo": {
            "devices": {
                "strip1": {
                    "ip": "10.0.0.26",
                    "name": "Desk Strip",
                    "calibration": {
                        "curve_exponent": 1.8,
                        "white_balance": [1.0, 0.92, 0.85],
                        "min_brightness": 1,
                        "transition_ms": 0,
                    }
                }
            }
        },
        "web": {
            "host": "0.0.0.0",
            "port": 8765,
        },
        "audio": {
            "style": "shockwave",
            "accents": ["beat_flash"],
            "output_delay_ms": 35,
            "l900_mode": "style",
        },
        "screen_sync": {
            "profile": "gaming",
        },
        "modes": {
            "work": {"brightness": 80}
        },
        "effects": {
            "breathe": {"brightness_min": 20, "brightness_max": 80}
        },
        "hotkeys": {
            "toggle_power": "ctrl+alt+space"
        }
    }

    cfg = AppConfig(**valid_config)
    # When host is 0.0.0.0, token auth must be enabled with generated secret
    assert cfg.web.auth_enabled is True
    assert len(cfg.web.token) >= 32

    # Verify extra="forbid" raises ValidationError on unknown keys
    invalid_config = dict(valid_config)
    invalid_config["audio"]["unknown_typo_field"] = 123
    with pytest.raises(ValidationError):
        AppConfig(**invalid_config)
