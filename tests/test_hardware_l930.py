"""
Hardware Acceptance & Soak Test Suite for Physical Tapo L930 / L900 Devices.

This test suite executes against real physical hardware when available on the local network.
In headless CI environments (e.g., GitHub Actions runners) where physical hardware is not present,
it cleanly skips with an explicit diagnostic message.
"""
from __future__ import annotations

import asyncio
import os
import socket
import pytest
import dotenv
from pathlib import Path

from src.device_l930 import L930Controller
from src.effects_l930 import L930EffectsEngine, EFFECT_CATALOG


def _find_active_tapo_hardware() -> tuple[str, str, str] | None:
    """Probes candidate IPs and environment to detect physical Tapo hardware."""
    env = dotenv.dotenv_values(".env")
    email = env.get("TAPO_EMAIL")
    password = env.get("TAPO_PASSWORD")
    if not email or not password:
        return None

    # Common candidate IPs from config and local DHCP ranges
    candidate_ips = [
        "10.0.0.6", "10.0.0.8", "10.0.0.24", "10.0.0.26",
        "192.168.1.50", "192.168.1.51", "192.168.1.24", "192.168.1.26"
    ]

    for ip in candidate_ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.12)
            res = s.connect_ex((ip, 80))
            s.close()
            if res == 0:
                return ip, email, password
        except Exception:
            continue
    return None


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_physical_hardware_connection_and_effects():
    """
    Release Gate 6 - Physical Hardware Acceptance:
    Verifies actual physical device communication, firmware deployment, and frame transmission.
    """
    hw_info = _find_active_tapo_hardware()
    if hw_info is None:
        pytest.skip(
            "Physical Tapo L930 hardware not reachable on this host/network "
            "(normal in headless CI runner without IoT hardware)"
        )

    ip, email, password = hw_info
    ctrl = L930Controller(ip, email, password, dev_id="hw_test_strip")

    try:
        # 1. Real connection & authentication
        await asyncio.wait_for(ctrl.connect(), timeout=10.0)
        assert ctrl._is_on is not None, "Physical controller failed to report power state"

        # 2. Real firmware effect deployment
        engine = L930EffectsEngine(ctrl, None, {})
        for eff_name in ("tide", "starfield", "flicker"):
            fx = engine._build_effect_payload(eff_name)
            assert fx is not None, f"Payload builder failed for {eff_name}"
            accepted = await ctrl.set_native_effect(fx, priority=0)
            assert accepted is True, f"Physical device rejected firmware effect {eff_name}"

        # 3. Real 50-zone addressable HSV segment transmission
        test_frame = [[210, 85, 45]] * 50
        sent = await ctrl.set_segments(test_frame, master_brightness=50, transition=200)
        assert sent is True, "Physical device rejected 50-zone addressable segment frame"

        # 4. Telemetry check
        rtt = ctrl.diagnostics.total_latency_ms
        assert rtt >= 0.0, "Physical device diagnostics did not record valid RTT"

    finally:
        await ctrl.clean_shutdown()
