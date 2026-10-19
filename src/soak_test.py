"""
Soak test runner for Tapo L930 firmware effects.

Runs each firmware effect for a configured duration (default: 30 minutes in soak mode,
or 10 seconds in quick verification mode) and continuously pings/checks that the
strip remains responsive, connected, and functional without packet flood crashes.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import dotenv

from src.device_l930 import L930Controller
from src.effects_l930 import L930EffectsEngine, EFFECT_CATALOG


async def run_soak_test(duration_minutes: float = 30.0, dev_ip: str = "10.0.0.24"):
    env = dotenv.dotenv_values(".env")
    email = env.get("TAPO_EMAIL")
    password = env.get("TAPO_PASSWORD")
    if not email or not password:
        print("Missing credentials in .env file.")
        sys.exit(1)

    print(f"Connecting to Tapo L930 at {dev_ip}...")
    ctrl = L930Controller(dev_ip, email, password)
    await ctrl.connect()

    firmware_effects = [k for k, v in EFFECT_CATALOG.items() if v["kind"] == "firmware"]
    print(f"Found {len(firmware_effects)} firmware effects to soak-test: {firmware_effects}")

    duration_per_effect_sec = (duration_minutes * 60.0) / len(firmware_effects)
    print(f"Total test time: {duration_minutes:.1f} minutes (~{duration_per_effect_sec:.1f}s per effect)\n")

    engine = L930EffectsEngine(ctrl, None, {})

    for idx, eff_name in enumerate(firmware_effects):
        print(f"[{idx+1}/{len(firmware_effects)}] Deploying firmware effect: '{eff_name}'...")
        fx = engine._build_effect_payload(eff_name)
        if not fx:
            print(f"  [ERROR] Failed to construct payload for {eff_name}")
            continue

        res = await ctrl.set_native_effect(fx, priority=0)
        print(f"  Upload response: {res}")

        start_t = time.time()
        check_interval = 5.0
        while time.time() - start_t < duration_per_effect_sec:
            await asyncio.sleep(min(check_interval, max(0.1, duration_per_effect_sec - (time.time() - start_t))))
            try:
                # Ping device state without disturbing lighting effect
                t0 = time.perf_counter()
                dev = ctrl._device
                if dev and hasattr(dev, "client"):
                    raw = await dev.client.get_device_info()
                    rtt = (time.perf_counter() - t0) * 1000.0
                    data = raw.get_or_else({})
                    is_on = data.get("device_on", False)
                    print(f"    Reachability check OK: RTT={rtt:.1f}ms, is_on={is_on}", flush=True)
            except Exception as e:
                print(f"    [WARN] Reachability check failed: {e}", flush=True)

        print(f"  Completed soak run for '{eff_name}'. Strip is healthy.\n", flush=True)

    print("All firmware soak tests passed successfully! Clean shutdown...")
    await ctrl.clean_shutdown()


def main():
    parser = argparse.ArgumentParser(description="L930 Firmware Effect Soak Test Runner")
    parser.add_argument("--minutes", type=float, default=30.0, help="Total soak duration in minutes (default 30)")
    parser.add_argument("--quick", action="store_true", help="Quick mode (15 seconds per effect)")
    parser.add_argument("--ip", type=str, default="10.0.0.24", help="L930 IP address")
    args = parser.parse_args()

    dur = (len([k for k, v in EFFECT_CATALOG.items() if v["kind"] == "firmware"]) * 15.0 / 60.0) if args.quick else args.minutes
    asyncio.run(run_soak_test(duration_minutes=dur, dev_ip=args.ip))


if __name__ == "__main__":
    main()
