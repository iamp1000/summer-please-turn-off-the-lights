"""
L900 Ambient Light Effects Engine.

Drives slow, relaxing ambient light animations for single-zone light strips.
Rule:
- Slow effects only: Ambient Drift, Fireplace, Golden Hour, Ocean Waves, Color Breath, Candle Flicker.
- Send a target color every 1-3 seconds with transition_ms ~= interval in a single combined request.
"""
from __future__ import annotations

import logging
import math
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("tapo")

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
        self._stop_event: Optional[threading.Event] = None
        self._effect_generation: int = 0
        self._last_error: Optional[str] = None

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
        self.stop()

        if isinstance(effect_config_or_name, str):
            self._effect_name = effect_config_or_name
            self._current_effect = {"name": effect_config_or_name}
        elif isinstance(effect_config_or_name, dict):
            self._current_effect = effect_config_or_name
            self._effect_name = effect_config_or_name.get("name", "ambient_drift")
        else:
            return

        self._effect_generation += 1
        self._start_time = time.monotonic()
        self._start_b = getattr(self._controller, "last_b", 50)
        self._start_h = getattr(self._controller, "last_h", 0)
        self._start_s = getattr(self._controller, "last_s", 0)

        self._running = True
        stop_event = threading.Event()
        self._stop_event = stop_event
        gen = self._effect_generation

        self._thread = threading.Thread(
            target=self._run,
            args=(stop_event, gen),
            daemon=True,
            name=f"L900Anim-{self._effect_name}"
        )
        self._thread.start()

    def stop(self):
        self._effect_generation += 1
        self._running = False
        event = self._stop_event
        if event is not None:
            event.set()
        thread = self._thread
        if thread and thread.is_alive() and thread != threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None
        self._stop_event = None
        self._current_effect = None
        self._effect_name = None
        if hasattr(self._controller, "clear_frames"):
            self._controller.clear_frames()

    def _run(self, stop_event: threading.Event, generation: int):
        while not stop_event.is_set() and generation == self._effect_generation:
            try:
                if not self._current_effect:
                    if stop_event.wait(0.1):
                        break
                    continue

                eff_name = (self._effect_name or "ambient_drift").lower()
                cfg = self._current_effect
                t = time.monotonic() - self._start_time

                # 1. Determine send interval & transition duration based on physical nature
                sp_mult = max(0.2, self._speed_multiplier)
                if eff_name == "candle_flicker":
                    # Rapid, irregular updates with short attack to prevent smoothing away flickers
                    interval = random.uniform(0.12, 0.28) / sp_mult
                    trans_ms = max(40, int(interval * 500))
                elif eff_name == "fireplace":
                    # Active thermal turbulence with surging attacks
                    interval = max(0.25, 0.45 / sp_mult)
                    trans_ms = int(interval * 700)
                elif eff_name == "color_breath":
                    # Smooth respiratory pacing
                    interval = max(0.35, 0.60 / sp_mult)
                    trans_ms = int(interval * 950)
                elif eff_name == "ocean_waves":
                    # Swell and surf rhythm
                    interval = max(0.40, 0.85 / sp_mult)
                    trans_ms = int(interval * 900)
                elif eff_name == "golden_hour":
                    # Stable, sunlit slow drift
                    interval = max(1.0, 3.2 / sp_mult)
                    trans_ms = int(interval * 1000)
                elif eff_name == "ambient_drift":
                    # Silky, long palette migration
                    interval = max(1.0, 3.0 / sp_mult)
                    trans_ms = int(interval * 1000)
                else:
                    interval = max(0.5, 2.0 / sp_mult)
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
                    published = self._frame_bus.publish(FramePacket(
                        dev_id=self._dev_id,
                        producer=OutputProducer.EFFECT,
                        hsv=(frame_data["h"], frame_data["s"], frame_data["b"]),
                        brightness=frame_data["b"],
                        transition=trans_ms,
                    ))
                    if not published:
                        if stop_event.wait(0.1):
                            break
                        continue

                if hasattr(self._controller, "submit_frame"):
                    self._controller.submit_frame(frame_data)
                elif hasattr(self._controller, "set_state"):
                    self._loop_runner.run(self._controller.set_state(
                        frame_data["h"], frame_data["s"], frame_data["b"], priority=1
                    ))

                if stop_event.wait(interval):
                    break

            except Exception as e:
                logger.exception(f"[AnimationEngine] Exception in L900 worker: {e}")
                self._last_error = str(e)
                if stop_event.wait(1.0):
                    break

    def _compute_hsv(self, eff_name: str, cfg: dict, t: float) -> Tuple[int, int, int]:
        """
        Computes target HSV using distinct temporal, color evolution,
        and brightness envelopes tailored specifically for a single-zone strip.
        """
        # 1. Ambient Drift: Slow, subtle palette migration with low-amplitude brightness variation
        if eff_name == "ambient_drift":
            pal = [(220, 25, 80), (330, 20, 80), (270, 22, 80), (175, 20, 80)]
            speed = 0.02
            n = len(pal)
            c_phase = (t * speed) % n
            idx1 = int(c_phase)
            idx2 = (idx1 + 1) % n
            blend = c_phase - idx1

            rgb1 = tapo_hsv_to_rgb(pal[idx1][0], pal[idx1][1], 100)
            rgb2 = tapo_hsv_to_rgb(pal[idx2][0], pal[idx2][1], 100)
            interp_rgb = lerp_oklab(rgb1, rgb2, blend)
            h_val, s_val, _ = rgb_to_tapo_hsv(*interp_rgb)

            # Restful, low-amplitude breathing variation (48% to 62%)
            norm_drift = 0.5 + 0.5 * math.sin(t * speed * 2.0 * math.pi)
            b_val = int(50 + norm_drift * 12)
            return int(h_val), int(s_val), max(1, min(100, b_val))

        # 2. Fireplace: Irregular warmth changes with occasional brighter flame surges
        elif eff_name == "fireplace":
            # Multi-octave irregular thermal turbulence
            simmer = math.sin(t * 1.8) * 0.45 + math.sin(t * 3.7 + 0.8) * 0.35 + math.sin(t * 6.3 + 1.9) * 0.20
            # Episodic flame tongue surges
            surge_osc = math.sin(t * 0.75 + 2.1)
            surge = max(0.0, (surge_osc - 0.35) / 0.65) ** 1.8
            # Low ember simmer drops into 0.15-0.35, flame flares boost up to 0.85-1.0
            intensity = max(0.0, 0.45 * (simmer + 1.0) * 0.5 + 0.55 * surge)

            # Color temperature changes with flame surge:
            # Simmering embers: deep crimson orange (14°); Hot flame surges: golden yellow (38°)
            h_val = int(14 + intensity * 24)
            s_val = int(98 - surge * 18)
            b_val = int(max(20, min(95, 20 + intensity * 74)))
            return int(h_val), int(s_val), b_val

        # 3. Golden Hour: Stable rich amber and honey palette with slow rose shifts (sunlit & radiant)
        elif eff_name == "golden_hour":
            pal = [(34, 85, 95), (42, 80, 92), (22, 85, 90), (14, 75, 86)]
            speed = 0.015
            n = len(pal)
            c_phase = (t * speed) % n
            idx1 = int(c_phase)
            idx2 = (idx1 + 1) % n
            blend = c_phase - idx1

            rgb1 = tapo_hsv_to_rgb(pal[idx1][0], pal[idx1][1], 100)
            rgb2 = tapo_hsv_to_rgb(pal[idx2][0], pal[idx2][1], 100)
            interp_rgb = lerp_oklab(rgb1, rgb2, blend)
            h_val, s_val, _ = rgb_to_tapo_hsv(*interp_rgb)

            # Consistently radiant, sunlit glow (76% to 90%)
            sunlit_wave = 0.5 + 0.5 * math.sin(t * speed * 2.0 * math.pi)
            b_val = int(76 + sunlit_wave * 14)
            return int(h_val), int(s_val), max(1, min(100, b_val))

        # 4. Ocean Waves: Slow blue-to-teal changes with distinct asymmetric swell and recession
        elif eff_name == "ocean_waves":
            period = 7.5
            phase = (t % period) / period
            if phase < 0.45:
                # Swell build-up: water accelerates toward crest
                p = phase / 0.45
                env = p ** 2.2
                h_val = int(215 - env * 45)  # 215 deep navy -> 170 coastal teal
                s_val = int(85 - env * 25)
                b_val = int(24 + env * 66)
            else:
                # Recession / undertow: exponential damping back to deep indigo
                p = (phase - 0.45) / 0.55
                decay = math.exp(-p * 3.5)
                h_val = int(170 + (1.0 - decay) * 45)
                s_val = int(60 + (1.0 - decay) * 25)
                b_val = int(24 + decay * 66)
            return int(h_val), int(s_val), max(1, min(100, b_val))

        # 5. Color Breath: Holds chosen warm hue, focuses on 10s physiological respiratory curve
        elif eff_name == "color_breath":
            pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "warm_mono")
            h_val, s_val = pal[0][0], pal[0][1]

            # 10s Respiratory cycle: 4s inhale, 1s hold, 5s exhale
            cycle = 10.0
            phase = (t % cycle) / cycle
            if phase < 0.40:
                p = phase / 0.40
                curve = 0.5 - 0.5 * math.cos(p * math.pi)  # Smooth cubic ease-in
            elif phase < 0.50:
                curve = 1.0  # Post-inspiratory hold
            else:
                p = (phase - 0.50) / 0.50
                curve = 0.5 + 0.5 * math.cos(p * math.pi)  # Relaxing exhale decay

            b_val = int(max(10, min(88, 12 + curve * 76)))
            return int(h_val), int(s_val), b_val

        # 6. Candle Flicker: Fast irregular brightness changes with color-temperature shifts
        elif eff_name == "candle_flicker":
            # Fast drafting flutter and micro-drops
            f1 = math.sin(t * 14.3) * 0.35
            f2 = math.cos(t * 23.7) * 0.25
            draft = -0.35 if (math.sin(t * 3.1) > 0.82) else 0.0
            flutter = f1 + f2 + draft + random.uniform(-0.15, 0.15)
            norm_flame = max(0.0, min(1.0, 0.65 + flutter * 0.45))

            # Color temperature: draft drops cool to deeper red-orange (27°), hot surges flare to golden yellow (38°)
            h_val = int(27 + norm_flame * 11)
            s_val = int(95 - norm_flame * 10)
            b_val = int(max(18, min(95, 20 + norm_flame * 72)))
            return int(h_val), int(s_val), b_val

        # Fallback / Custom Palette
        else:
            cfg_pal = cfg.get("palette")
            if cfg_pal and len(cfg_pal) > 0 and len(cfg_pal[0]) >= 2:
                pal = [(p[0], p[1], 80) for p in cfg_pal]
            else:
                pal = get_palette_hsv("sunset")
            speed = 0.05
            n = len(pal)
            c_phase = (t * speed) % n
            idx1 = int(c_phase)
            idx2 = (idx1 + 1) % n
            blend = c_phase - idx1

            rgb1 = tapo_hsv_to_rgb(pal[idx1][0], pal[idx1][1], 100)
            rgb2 = tapo_hsv_to_rgb(pal[idx2][0], pal[idx2][1], 100)
            interp_rgb = lerp_oklab(rgb1, rgb2, blend)
            h_val, s_val, _ = rgb_to_tapo_hsv(*interp_rgb)
            wave = 0.5 + 0.5 * math.sin(t * speed * 2.0 * math.pi)
            b_val = int(30 + wave * 40)
            return int(h_val), int(s_val), max(1, min(100, b_val))

