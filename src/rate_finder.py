"""
Safe Rate Finder Tool for Tapo L930 / L900.
Steps through test rates (e.g. 2, 4, 6, 8 updates/s) for N minutes or seconds,
monitors RTT, timeouts, errors, and handshakes, and saves the chosen cap to config.yaml.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
import yaml

# Ensure project root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.device_l930 import L930Controller
from src.hub import BackgroundLoop


async def run_rate_test(ctrl: L930Controller, rate_ups: float, duration_s: float):
    print(f"\n[RateFinder] >>> Testing {rate_ups} updates/sec for {duration_s:.1f}s...")
    ctrl.clear_frames()
    if ctrl.frame_sender:
        ctrl.frame_sender.set_send_budget(max_updates_per_s=rate_ups)

    start_t = time.time()
    frames_sent = 0
    interval = 1.0 / rate_ups

    # Sample color sequence alternating hues
    hues = [0, 60, 120, 180, 240, 300]
    hue_idx = 0

    while time.time() - start_t < duration_s:
        t_cycle = time.time()
        h = hues[hue_idx % len(hues)]
        hue_idx += 1
        frame = [[h, 85, 45]] * 50
        ctrl.submit_frame({
            "segments": frame,
            "brightness": 45,
            "transition": 100,
            "_pre_corrected": True
        })
        frames_sent += 1
        elapsed = time.time() - t_cycle
        await asyncio.sleep(max(0.005, interval - elapsed))

    # Read diagnostics
    diag = ctrl.diagnostics.snapshot()
    mean_rtt = diag.get("mean_response_time_ms", 0.0)
    p95_rtt = diag.get("p95_response_time_ms", 0.0)
    handshakes = diag.get("handshakes_per_min", 0.0)
    errors = diag.get("errors_per_min", 0.0)
    status = diag.get("status", "unknown")

    print(f"  Results for {rate_ups} ups:")
    print(f"    - Frames submitted: {frames_sent}")
    print(f"    - Mean response time: {mean_rtt:.1f} ms")
    print(f"    - p95 response time:  {p95_rtt:.1f} ms")
    print(f"    - Handshakes/min:     {handshakes:.1f}")
    print(f"    - Errors/min:         {errors:.1f}")
    print(f"    - Device Status:      {status}")

    # Pass criteria: p95 RTT < 350 ms, errors == 0, handshakes <= 2.0/min
    passed = (p95_rtt < 350.0 and errors == 0.0 and handshakes <= 2.0 and status == "connected")
    return {
        "rate": rate_ups,
        "mean_rtt": mean_rtt,
        "p95_rtt": p95_rtt,
        "handshakes": handshakes,
        "errors": errors,
        "passed": passed,
    }


def update_config_rate(dev_id: str, chosen_rate: float):
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if not cfg_path.exists():
        print(f"[RateFinder] config.yaml not found at {cfg_path}")
        return

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    devs = cfg.get("tapo", {}).get("devices", {})
    if dev_id in devs:
        if "calibration" not in devs[dev_id]:
            devs[dev_id]["calibration"] = {}
        devs[dev_id]["calibration"]["max_updates_per_s"] = float(chosen_rate)
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)
        print(f"[RateFinder] Successfully updated {dev_id} max_updates_per_s = {chosen_rate} in config.yaml!")


async def main_async(args):
    cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    dev_id = args.device
    dev_cfg = cfg.get("tapo", {}).get("devices", {}).get(dev_id)
    if not dev_cfg:
        print(f"[RateFinder] Device {dev_id} not found in config.yaml")
        return

    ip = dev_cfg.get("ip")
    email = os.getenv("TAPO_EMAIL")
    password = os.getenv("TAPO_PASSWORD")
    if not email or not password:
        print("[RateFinder] Missing TAPO_EMAIL or TAPO_PASSWORD in .env")
        return

    print(f"[RateFinder] Initializing controller for {dev_id} ({ip})...")
    loop = asyncio.get_running_loop()
    ctrl = L930Controller(
        ip=ip,
        email=email,
        password=password,
        dev_id=dev_id,
        loop=loop,
        calibration=dev_cfg.get("calibration", {})
    )

    try:
        await ctrl.connect()
        await ctrl.turn_on()
    except Exception as e:
        print(f"[RateFinder] Connection failed: {e}")
        return

    rates = [2.0, 4.0, 6.0, 8.0]
    duration = args.minutes * 60.0 if args.minutes is not None else args.duration
    results = []

    try:
        for r in rates:
            res = await run_rate_test(ctrl, r, duration)
            results.append(res)
            if not res["passed"]:
                print(f"[RateFinder] Rate {r} ups did not pass safety criteria. Halting step-up.")
                break

            # Prompt the user to note when the Tapo app shows the device offline
            if not args.no_prompt:
                user_resp = input(
                    f"\n[RateFinder] Check your Tapo mobile app now. Does {dev_id} show OFFLINE or unresponsive? [y/N]: "
                ).strip().lower()
                if user_resp in ("y", "yes"):
                    print(f"[RateFinder] Marked {r} updates/sec as unsafe based on Tapo mobile app.")
                    res["passed"] = False
                    break

            await asyncio.sleep(2.0)
    finally:
        print("\n[RateFinder] Cleaning up and turning off strip...")
        await ctrl.clean_shutdown()

    # Determine optimal safe rate
    passed_rates = [r["rate"] for r in results if r["passed"]]
    if passed_rates:
        chosen = max(passed_rates)
        print(f"\n[RateFinder] >>> Recommended Safe Max Rate: {chosen} updates/sec")
    else:
        chosen = 2.0
        print("\n[RateFinder] >>> None of the rates passed clean criteria. Defaulting to 2.0 updates/sec.")

    if args.save:
        update_config_rate(dev_id, chosen)
    elif not args.no_prompt:
        save_resp = input(f"[RateFinder] Save max_updates_per_s = {chosen} to config.yaml? [Y/n]: ").strip().lower()
        if save_resp in ("", "y", "yes"):
            update_config_rate(dev_id, chosen)


def main():
    parser = argparse.ArgumentParser(description="Tapo L930 Safe Rate Finder Tool")
    parser.add_argument("--device", default="strip2", help="Device ID to test (default: strip2)")
    parser.add_argument("--duration", type=float, default=15.0, help="Test duration per rate step in seconds (default: 15.0)")
    parser.add_argument("--minutes", type=float, default=None, help="Test duration per rate step in minutes (e.g. 1, 2, 5)")
    parser.add_argument("--save", action="store_true", help="Automatically save chosen safe cap to config.yaml without prompt")
    parser.add_argument("--no-prompt", action="store_true", help="Non-interactive mode (do not prompt for Tapo app status or saving)")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
