from __future__ import annotations
import ctypes
from ctypes import wintypes
import datetime
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Dict, Any, Optional, List

from src.logger import log

PRESETS_FILE = Path(__file__).resolve().parent.parent / "presets.json"

# ── 1. JSON Scenes & Custom Presets Manager ──────────────────────────────────

class PresetManager:
    """Manages custom user scenes and snapshots saved to JSON."""

    def __init__(self, filepath: Path = PRESETS_FILE):
        self.filepath = filepath
        self.presets: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"[Presets] Error reading {self.filepath}: {e}")
        return {
            "Late Night Coding": {
                "description": "Warm tungsten amber on desk, low-glare cinema bias behind monitor",
                "devices": {
                    "strip1": {"power": True, "brightness": 25, "h": 32, "s": 85},
                    "strip2": {"power": True, "brightness": 35, "effect": "sunset_glow"}
                }
            },
            "Cyberpunk Battle Station": {
                "description": "Neon magenta desk fill with dynamic cyan chase on bias strip",
                "devices": {
                    "strip1": {"power": True, "brightness": 70, "h": 320, "s": 100},
                    "strip2": {"power": True, "brightness": 85, "effect": "cyber_chase"}
                }
            },
            "Deep Relaxation": {
                "description": "Soft lavender candle warmth and liquid lo-fi glow",
                "devices": {
                    "strip1": {"power": True, "brightness": 30, "h": 28, "s": 90},
                    "strip2": {"power": True, "brightness": 40, "effect": "calm"}
                }
            }
        }

    def save_to_disk(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.presets, f, indent=2)
        except Exception as e:
            log.error(f"[Presets] Failed saving presets to disk: {e}")

    def list_presets(self) -> Dict[str, Any]:
        return dict(self.presets)

    def save_current_as_preset(self, name: str, hub) -> dict:
        full_st = hub.get_full_state()
        snapshot = {
            "created_at": datetime.datetime.now().isoformat(),
            "devices": {}
        }
        for dev_id, d_st in full_st.get("devices", {}).items():
            entry = {
                "power": d_st.get("power", True),
                "brightness": d_st.get("brightness", 50),
                "active_label": d_st.get("active_label", "Idle")
            }
            if d_st.get("model") == "L930" and hasattr(hub, "frame_bus") and hub.frame_bus:
                packet = hub.frame_bus.get_latest_frame(dev_id)
                if packet and packet.segments:
                    entry["segments"] = [list(x) for x in packet.segments]
            snapshot["devices"][dev_id] = entry
        self.presets[name] = snapshot
        self.save_to_disk()
        return snapshot

    def apply_preset(self, name: str, hub) -> bool:
        if name not in self.presets:
            return False
        preset = self.presets[name]
        devs = preset.get("devices", {})
        for dev_id, st in devs.items():
            if dev_id in hub.devices:
                ctx = hub.devices[dev_id]
                pwr = st.get("power", True)
                hub.set_power(dev_id, pwr)
                if pwr:
                    if "brightness" in st:
                        hub.set_brightness(dev_id, st["brightness"])
                    if ("segments" in st or "regions" in st or "stops" in st) and ctx.model == "L930":
                        from src.modes import build_mode_segments
                        from src.frame_bus import FramePacket, OutputProducer
                        segs = build_mode_segments(st, num_zones=50)
                        b = st.get("brightness", 50)
                        hub.arbiter.claim_output(dev_id, OutputProducer.STATIC, on_relinquish=ctx.stop_all_active)
                        ctx.stop_all_active()
                        ctx.state["power"] = True
                        ctx.state["active_label"] = name
                        hub.frame_bus.publish(FramePacket(
                            dev_id=dev_id,
                            producer=OutputProducer.STATIC,
                            segments=segs,
                            brightness=b,
                        ))
                        if hasattr(ctx.controller, "set_segments"):
                            hub.loop_runner.run(ctx.controller.set_segments(segs, brightness=b, transition=600, priority=0))
                        elif hasattr(ctx.controller, "submit_frame"):
                            ctx.controller.submit_frame({"segments": segs, "brightness": b, "transition": 600})
                    elif "h" in st and "s" in st:
                        hub.apply_custom_color(dev_id, st["h"], st["s"], st.get("brightness", 50))
                    elif "effect" in st:
                        hub.apply_effect(dev_id, st["effect"])
        return True

    def delete_preset(self, name: str) -> bool:
        if name in self.presets:
            del self.presets[name]
            self.save_to_disk()
            return True
        return False


# ── 2. Circadian Rhythm Lighting Engine ──────────────────────────────────────

class CircadianLightingEngine:
    """
    Dynamically modulates brightness and color temperature across the 24-hour solar cycle
    to enhance daytime alertness and promote natural melatonin production at night.
    """

    def __init__(self, hub):
        self.hub = hub
        self.enabled = False
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self.enabled = True
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="CircadianEngine")
        self._thread.start()

    def stop(self):
        self.enabled = False
        self._running = False

    def get_solar_target(self, current_hour: float) -> Tuple[int, int, int]:
        """
        Returns target (Hue, Saturation, Brightness) for the given decimal hour (0.0 - 24.0).
        """
        if 6.0 <= current_hour < 9.0:
            # Morning sunrise: warm amber-gold -> soft daylight
            t = (current_hour - 6.0) / 3.0
            h = int(28 + t * 15)
            s = int(80 - t * 50)
            b = int(35 + t * 55)
        elif 9.0 <= current_hour < 17.0:
            # Daytime: high alertness neutral white (daylight 5500K)
            h = 45
            s = 15
            b = 100
        elif 17.0 <= current_hour < 20.5:
            # Sunset / Evening: calming warm gold -> deep amber
            t = (current_hour - 17.0) / 3.5
            h = int(45 - t * 18)
            s = int(20 + t * 65)
            b = int(100 - t * 45)
        elif 20.5 <= current_hour < 23.0:
            # Pre-sleep melatonin protection: warm candle tungsten (2200K)
            t = (current_hour - 20.5) / 2.5
            h = int(27 - t * 8)
            s = int(85 + t * 15)
            b = int(55 - t * 30)
        else:
            # Night: 23:00 to 06:00 - Deep nightlight
            h = 18
            s = 100
            b = 8

        return max(0, min(360, h)), max(0, min(100, s)), max(5, min(100, b))

    def _run(self):
        while self._running:
            try:
                now = datetime.datetime.now()
                dec_hour = now.hour + now.minute / 60.0 + now.second / 3600.0
                h, s, b = self.get_solar_target(dec_hour)

                for dev_id, ctx in self.hub.devices.items():
                    if ctx.state.get("power", True) and ctx.state.get("active_label") in ("Idle", "Circadian", "White"):
                        ctx.state["active_label"] = "Circadian"
                        self.hub.set_brightness(dev_id, b)
                        self.hub.apply_custom_color(dev_id, h, s, b)

                # Update every 60 seconds
                time.sleep(60.0)
            except Exception as e:
                log.warning(f"[Circadian] Step error: {e}")
                time.sleep(10.0)


# ── 3. Windows Lock / Idle / Sleep Power Guardian ────────────────────────────

class WindowsPowerGuardian:
    """
    Automatically turns off strips when Windows is locked, sleeping, or idle for N minutes,
    and seamlessly restores lighting state when unlocked.
    """

    def __init__(self, hub, idle_timeout_minutes: int = 15):
        self.hub = hub
        self.idle_timeout_sec = idle_timeout_minutes * 60
        self.enabled = True
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_locked_or_idle = False
        self._saved_states: Dict[str, Any] = {}

    def start(self):
        if self._running or os.name != "nt":
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="PowerGuardianWorker")
        self._thread.start()

    def stop(self):
        self._running = False

    def _get_idle_seconds(self) -> float:
        try:
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                return max(0.0, millis / 1000.0)
        except Exception:
            pass
        return 0.0

    def _turn_off_and_save(self):
        if self._is_locked_or_idle:
            return
        self._is_locked_or_idle = True
        self._saved_states = {}
        for dev_id, ctx in self.hub.devices.items():
            self._saved_states[dev_id] = {
                "power": ctx.state.get("power", True),
                "brightness": ctx.state.get("brightness", 50),
                "active_label": ctx.state.get("active_label", "Idle")
            }
            if ctx.state.get("power", True):
                self.hub.set_power(dev_id, False)
        log.info("[PowerGuardian] Windows idle/locked detected. Lights turned off to save power.")

    def _restore_saved_state(self):
        if not self._is_locked_or_idle:
            return
        self._is_locked_or_idle = False
        for dev_id, st in self._saved_states.items():
            if st.get("power", False):
                self.hub.set_power(dev_id, True)
                self.hub.set_brightness(dev_id, st.get("brightness", 50))
        log.info("[PowerGuardian] User returned / unlocked. Lights restored.")

    def _run(self):
        while self._running:
            try:
                idle_sec = self._get_idle_seconds()
                if idle_sec > self.idle_timeout_sec and not self._is_locked_or_idle:
                    self._turn_off_and_save()
                elif idle_sec < 5.0 and self._is_locked_or_idle:
                    self._restore_saved_state()
                time.sleep(3.0)
            except Exception:
                time.sleep(5.0)
