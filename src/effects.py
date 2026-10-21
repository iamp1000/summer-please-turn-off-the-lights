"""
L900 Ambient Light Effects Engine.

Drives restrained target changes for single-zone L900 strips. The L900 HSB
transport transmits hue, saturation and brightness but does not consume the
per-frame "transition" metadata used by the L930 path. Ambient smoothness therefore
comes from slow envelopes, modest per-update changes and safe sender pacing.
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
        self._output_token: Optional[tuple[int, str]] = None

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
        self._output_token = (
            self._frame_bus.capture_token(self._dev_id, OutputProducer.EFFECT)
            if self._frame_bus else None
        )
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

    def _timing_for_effect(self, eff_name: str, speed_multiplier: float) -> Tuple[float, int]:
        """Return safe target cadence and advisory transition metadata for L900."""
        sp_mult = max(0.2, float(speed_multiplier))
        if eff_name == "candle_flicker":
            interval = max(0.42, random.uniform(0.48, 0.62) / sp_mult)
        elif eff_name == "fireplace":
            interval = max(0.50, 0.66 / sp_mult)
        elif eff_name == "color_breath":
            interval = max(0.55, 0.75 / sp_mult)
        elif eff_name == "ocean_waves":
            interval = max(0.65, 0.95 / sp_mult)
        elif eff_name == "golden_hour":
            interval = max(1.0, 3.2 / sp_mult)
        elif eff_name == "ambient_drift":
            interval = max(1.0, 3.0 / sp_mult)
        else:
            interval = max(0.5, 2.0 / sp_mult)
        # Metadata only: this transport does not send a native L900 transition duration.
        return interval, int(round(interval * 1000.0))

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

                # L900's HSB transport ignores transition metadata, so pace small target changes.
                interval, trans_ms = self._timing_for_effect(eff_name, self._speed_multiplier)


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
                    if self._output_token is None:
                        if stop_event.wait(0.1):
                            break
                        continue
                    generation, producer_id = self._output_token
                    published = self._frame_bus.publish_frame(
                        self._dev_id, OutputProducer.EFFECT, frame_data,
                        generation=generation, producer_id=producer_id,
                    )
                    if not published:
                        if stop_event.wait(0.1):
                            break
                        continue
                elif hasattr(self._controller, "submit_frame"):
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

        # 2. Fireplace: soft, low-frequency ember and flame movement for the L900.
        elif eff_name == "fireplace":
            simmer = (
                math.sin(t * 0.85) * 0.34
                + math.sin(t * 1.30 + 0.8) * 0.24
                + math.sin(t * 2.0 + 1.9) * 0.12
            )
            surge_osc = math.sin(t * 0.34 + 2.1)
            surge = max(0.0, (surge_osc - 0.45) / 0.55) ** 2.0
            intensity = max(0.0, 0.60 * (simmer + 1.0) * 0.5 + 0.40 * surge)
            h_val = int(18 + intensity * 16)
            s_val = int(97 - surge * 9)
            b_val = int(max(24, min(72, 24 + intensity * 48)))
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

        # 4. Ocean Waves: slow, restrained swell and recession; fewer sharp target steps.
        elif eff_name == "ocean_waves":
            period = 12.0
            phase = (t % period) / period
            if phase < 0.48:
                p = phase / 0.48
                env = 0.5 - 0.5 * math.cos(p * math.pi)
                h_val = int(214 - env * 30)
                s_val = int(78 - env * 16)
                b_val = int(32 + env * 40)
            else:
                p = (phase - 0.48) / 0.52
                decay = math.exp(-p * 2.6)
                h_val = int(184 + (1.0 - decay) * 30)
                s_val = int(62 + (1.0 - decay) * 16)
                b_val = int(32 + decay * 40)
            return int(h_val), int(s_val), max(1, min(100, b_val))



        # 5. Color Breath: slow, low-glare respiratory cycle with a long crest hold.
        elif eff_name == "color_breath":
            pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "warm_mono")
            h_val, s_val = pal[0][0], pal[0][1]
            cycle = 14.0
            phase = (t % cycle) / cycle
            if phase < 0.43:
                p = phase / 0.43
                curve = 0.5 - 0.5 * math.cos(p * math.pi)
            elif phase < 0.54:
                curve = 1.0
            else:
                p = (phase - 0.54) / 0.46
                curve = 0.5 + 0.5 * math.cos(p * math.pi)
            b_val = int(max(22, min(68, 22 + curve * 46)))
            return int(h_val), int(s_val), b_val



        # 6. Candle Flicker: slow, restrained flame flutter with a narrow brightness range.
        elif eff_name == "candle_flicker":
            f1 = math.sin(t * 0.95) * 0.22
            f2 = math.cos(t * 1.65) * 0.10
            draft = -0.14 if math.sin(t * 0.42) > 0.88 else 0.0
            flutter = f1 + f2 + draft + random.uniform(-0.035, 0.035)
            norm_flame = max(0.0, min(1.0, 0.60 + flutter))
            h_val = int(26 + norm_flame * 8)
            s_val = int(96 - norm_flame * 8)
            b_val = int(max(25, min(62, 25 + norm_flame * 42)))
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

