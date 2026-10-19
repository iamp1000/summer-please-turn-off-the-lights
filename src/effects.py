"""
L900 Ambient Light Effects Engine.

Drives slow, relaxing ambient light animations for single-zone light strips.
Rule:
- Slow effects only: Ambient Drift, Fireplace, Golden Hour, Ocean Waves, Color Breath, Candle Flicker.
- Send a target color every 1-3 seconds with transition_ms ~= interval in a single combined request.
"""
from __future__ import annotations

import math
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from src.frame_bus import FramePacket, OutputProducer
from src.pipeline import lerp_oklab, rgb_to_tapo_hsv, tapo_hsv_to_rgb
from src.firmware_effects import PALETTES, get_palette_hsv


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


class AnimationEngine:
    """
    Drives slow, soothing ambient effects for single-zone strips (L900).
    Sends target colors every 1-3s with transition matching the interval.
    """

    def __init__(self, controller, loop_runner, app_state, frame_bus: Any = None, dev_id: str = "strip1"):
        self._controller = controller
        self._loop_runner = loop_runner
        self._app_state = app_state
        self._frame_bus = frame_bus
        self._dev_id = dev_id

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._current_effect: Optional[Dict[str, Any]] = None
        self._effect_name: Optional[str] = None
        self._start_time = 0.0

        # Snapshot bulb state for entry crossfade
        self._start_b = 50
        self._start_h = 0
        self._start_s = 0
        self._speed_multiplier = 1.0
        self._brightness_cap = 100
        self._palette_name = "sunset"

    def set_parameters(self, speed: Optional[float] = None, brightness: Optional[int] = None, palette_name: Optional[str] = None):
        if speed is not None:
            self._speed_multiplier = max(0.2, min(3.0, float(speed)))
        if brightness is not None:
            self._brightness_cap = max(1, min(100, int(brightness)))
        if palette_name is not None:
            self._palette_name = str(palette_name).lower()

    def is_running(self) -> bool:
        return self._running

    def start(self, effect_config_or_name: Any):
        if isinstance(effect_config_or_name, str):
            self._effect_name = effect_config_or_name
            self._current_effect = {"name": effect_config_or_name}
        elif isinstance(effect_config_or_name, dict):
            self._current_effect = effect_config_or_name
            self._effect_name = effect_config_or_name.get("name", "ambient_drift")
        else:
            return

        self._start_time = time.time()
        self._start_b = getattr(self._controller, "last_b", 50)
        self._start_h = getattr(self._controller, "last_h", 0)
        self._start_s = getattr(self._controller, "last_s", 0)

        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="L900AnimationWorker")
        self._thread.start()

    def stop(self):
        self._running = False
        self._current_effect = None
        self._effect_name = None
        if hasattr(self._controller, "clear_frames"):
            self._controller.clear_frames()

    def _run(self):
        while self._running:
            try:
                if not self._current_effect:
                    time.sleep(0.1)
                    continue

                eff_name = (self._effect_name or "ambient_drift").lower()
                cfg = self._current_effect
                t = time.time() - self._start_time

                # Determine send interval & transition (scaled by speed multiplier)
                if eff_name == "candle_flicker":
                    interval = 0.8
                elif eff_name in ("golden_hour", "ambient_drift", "ocean_waves"):
                    interval = 2.5
                elif eff_name == "color_breath":
                    interval = 1.5
                elif eff_name == "fireplace":
                    interval = 1.2
                else:
                    interval = 2.0

                interval = max(0.4, interval / max(0.2, self._speed_multiplier))
                trans_ms = int(interval * 1000)

                # Compute target HSV with effective elapsed time
                effective_t = t * self._speed_multiplier
                h_val, s_val, b_val = self._compute_hsv(eff_name, cfg, effective_t)

                # Apply master ceiling from GUI and local brightness cap
                master_ceiling = (self._app_state.get("brightness", 100) / 100.0) * (self._brightness_cap / 100.0)
                b_val = max(1, min(100, int(b_val * master_ceiling)))

                # Entry crossfade (first 1.5 seconds)
                if t < 1.5:
                    alpha = _ease_out(t / 1.5)
                    b_val = int(self._start_b + (b_val - self._start_b) * alpha)
                    s_rgb = tapo_hsv_to_rgb(self._start_h, self._start_s, 100)
                    c_rgb = tapo_hsv_to_rgb(h_val, s_val, 100)
                    entry_rgb = lerp_oklab(s_rgb, c_rgb, alpha)
                    h_val, s_val, _ = rgb_to_tapo_hsv(*entry_rgb)

                frame_data = {
                    "h": int(h_val) % 360,
                    "s": max(0, min(100, int(s_val))),
                    "b": max(1, min(100, int(b_val))),
                    "transition": trans_ms,
                }

                if self._frame_bus:
                    self._frame_bus.publish(FramePacket(
                        dev_id=self._dev_id,
                        producer=OutputProducer.EFFECT,
                        hsv=(frame_data["h"], frame_data["s"], frame_data["b"]),
                        brightness=frame_data["b"],
                        transition=trans_ms,
                    ))

                if hasattr(self._controller, "submit_frame"):
                    self._controller.submit_frame(frame_data)
                elif hasattr(self._controller, "set_state"):
                    self._loop_runner.run(self._controller.set_state(
                        frame_data["h"], frame_data["s"], frame_data["b"], priority=1
                    ))

                time.sleep(interval)

            except Exception as e:
                time.sleep(1.0)

    def _compute_hsv(self, eff_name: str, cfg: dict, t: float) -> Tuple[int, int, int]:
        """Computes target HSV using OKLab palette interpolation."""
        # Palettes
        if eff_name == "ambient_drift":
            pal = [(220, 30, 80), (260, 25, 80), (320, 20, 80), (180, 25, 80)]
            speed = 0.04
            b_min, b_max = 30, 65
        elif eff_name == "northern_lights":
            pal = [(140, 95, 80), (160, 90, 85), (280, 80, 75), (180, 90, 85)]
            speed = 0.05
            b_min, b_max = 35, 70
        elif eff_name == "fireplace":
            pal = [(5, 100, 75), (24, 95, 85), (42, 90, 90)]
            speed = 0.08
            b_min, b_max = 25, 60
        elif eff_name == "golden_hour":
            pal = [(20, 75, 85), (35, 80, 90), (30, 65, 95)]
            speed = 0.03
            b_min, b_max = 40, 75
        elif eff_name == "candle_flicker":
            pal = [(32, 90, 90), (38, 85, 95), (25, 95, 80)]
            speed = 0.15
            b_min, b_max = 20, 65
        elif eff_name == "ocean_waves":
            pal = [(225, 85, 80), (200, 85, 85), (175, 75, 90)]
            speed = 0.04
            b_min, b_max = 35, 75
        elif eff_name == "color_breath":
            pal = get_palette_hsv("warm_mono")
            speed = 0.08
            b_min, b_max = 15, 85
        else:
            # Fallback to configured palette
            cfg_pal = cfg.get("palette")
            if cfg_pal and len(cfg_pal) > 0 and len(cfg_pal[0]) >= 2:
                pal = [(p[0], p[1], 80) for p in cfg_pal]
            else:
                pal = get_palette_hsv("sunset")
            speed = 0.05
            b_min, b_max = 30, 70

        # Sample palette continuously in OKLab space
        n = len(pal)
        c_phase = (t * speed) % n
        idx1 = int(c_phase)
        idx2 = (idx1 + 1) % n
        blend = c_phase - idx1

        h1, s1, _ = pal[idx1]
        h2, s2, _ = pal[idx2]

        rgb1 = tapo_hsv_to_rgb(h1, s1, 100)
        rgb2 = tapo_hsv_to_rgb(h2, s2, 100)
        interp_rgb = lerp_oklab(rgb1, rgb2, blend)
        h_val, s_val, _ = rgb_to_tapo_hsv(*interp_rgb)

        # Gentle breathing brightness wave
        wave = 0.5 + 0.5 * math.sin(t * speed * 2.0 * math.pi)
        if eff_name == "candle_flicker":
            wave = max(0.0, min(1.0, wave + random.uniform(-0.25, 0.25)))
        b_val = int(b_min + wave * (b_max - b_min))

        return int(h_val), int(s_val), int(b_val)
