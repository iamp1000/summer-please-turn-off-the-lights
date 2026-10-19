from __future__ import annotations

import threading
import time
import math
import asyncio
import random
from src.frame_bus import FramePacket, OutputProducer


class AnimationEngine:
    """
    Drives smooth, looping light animations.

    Each effect config may carry:
      palette          – list of [hue, sat] pairs
      color_speed      – hue cycle speed multiplier
      brightness_min   – floor brightness (int, 1-100)
      brightness_max   – ceiling brightness (int, 1-100)
      brightness_speed – wave speed multiplier
      wave_shape       – "sine" | "triangle" | "sawtooth" | "random"  (default sine)
      strobe_hz        – if set, overrides wave with a strobe at N Hz
      pulse_color      – [h, s] for a single-color pulse (ignores palette)
    """

    def __init__(self, controller, loop_runner, app_state, frame_bus: Any = None, dev_id: str = "strip1"):
        self._controller   = controller
        self._loop_runner  = loop_runner
        self._app_state    = app_state
        self._frame_bus    = frame_bus
        self._dev_id       = dev_id
        self._running      = False
        self._thread       = None
        self._updater_future = None
        self._current_effect = None
        self._start_time   = 0.0
        self._target_state = None

        # For crossfade entry
        self._start_b  = 50
        self._start_h  = 0
        self._start_s  = 0

    def is_running(self) -> bool:
        return self._running

    def start(self, effect_config: dict):
        self._current_effect = effect_config
        self._start_time     = time.time()

        # Snapshot current bulb state so we crossfade smoothly from it
        self._start_b = self._controller.last_b
        self._start_h = self._controller.last_h
        self._start_s = self._controller.last_s

        if self._running:
            return  # already running – just swapped effect above
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._target_state = None
        self._current_effect = None
        if hasattr(self._controller, "clear_frames"):
            self._controller.clear_frames()

    # ── physics thread ───────────────────────────────────────────────────────

    def _run(self):
        while self._running:
            try:
                if not self._current_effect:
                    time.sleep(0.05)
                    continue

                cfg = self._current_effect
                t   = time.time() - self._start_time

                # ── brightness wave ──────────────────────────────────────────
                b_min   = cfg.get("brightness_min", 20)
                b_max   = cfg.get("brightness_max", 80)
                b_speed = cfg.get("brightness_speed", 1.0)
                shape   = cfg.get("wave_shape", "sine")
                b_range = b_max - b_min

                # Master slider acts as an overall ceiling
                ceiling = self._app_state.get("brightness", 100) / 100.0
                b_min   = max(1, int(b_min * ceiling))
                b_max   = max(b_min, int(b_max * ceiling))
                b_range = b_max - b_min

                wave_phase = t * b_speed * 0.4

                if shape == "triangle":
                    pos   = (wave_phase % 1.0)
                    wave  = 1.0 - abs(2 * pos - 1.0)
                elif shape == "sawtooth":
                    wave  = (wave_phase % 1.0)
                elif shape == "random":
                    wave  = 0.5 + 0.5 * math.sin(wave_phase * 2 * math.pi
                                                   + random.uniform(-0.3, 0.3))
                else:  # sine (default)
                    wave  = 0.5 + 0.5 * math.sin(wave_phase * 2 * math.pi)

                b_val = b_min + wave * b_range

                # ── strobe override ──────────────────────────────────────────
                strobe_hz = cfg.get("strobe_hz")
                if strobe_hz:
                    strobe_cycle = 1.0 / max(0.5, strobe_hz)
                    pos = (t % strobe_cycle) / strobe_cycle
                    b_val = b_max if pos < 0.5 else b_min

                # ── colour ───────────────────────────────────────────────────
                pulse_color = cfg.get("pulse_color")
                if pulse_color:
                    h_val, s_val = pulse_color[0], pulse_color[1]
                else:
                    palette = cfg.get("palette", [[0, 0]])
                    c_speed = cfg.get("color_speed", 1.0) * 0.004
                    p_len   = len(palette)
                    if p_len == 1:
                        h_val, s_val = palette[0]
                    else:
                        c_phase = (t * c_speed) % p_len
                        idx1    = int(c_phase)
                        idx2    = (idx1 + 1) % p_len
                        blend   = c_phase - idx1
                        h1, s1  = palette[idx1]
                        h2, s2  = palette[idx2]
                    from src.pipeline import tapo_hsv_to_rgb, lerp_oklab, rgb_to_tapo_hsv
                    rgb1 = tapo_hsv_to_rgb(h1, s1, 100)
                    rgb2 = tapo_hsv_to_rgb(h2, s2, 100)
                    mid_rgb = lerp_oklab(rgb1, rgb2, blend)
                    h_val, s_val, _ = rgb_to_tapo_hsv(*mid_rgb)

                # ── entry crossfade in perceptual OKLab space ────────────────
                if t < 1.2:
                    alpha = _ease_out(t / 1.2)
                    b_val = self._start_b + (b_val - self._start_b) * alpha
                    from src.pipeline import tapo_hsv_to_rgb, lerp_oklab, rgb_to_tapo_hsv
                    s_rgb = tapo_hsv_to_rgb(self._start_h, self._start_s, 100)
                    c_rgb = tapo_hsv_to_rgb(h_val, s_val, 100)
                    entry_rgb = lerp_oklab(s_rgb, c_rgb, alpha)
                    h_val, s_val, _ = rgb_to_tapo_hsv(*entry_rgb)

                self._target_state = (
                    max(1, int(b_val)),
                    int(h_val) % 360,
                    int(s_val)
                )

                if self._frame_bus:
                    self._frame_bus.publish(FramePacket(
                        dev_id=self._dev_id,
                        producer=OutputProducer.EFFECT,
                        hsv=(int(h_val) % 360, int(s_val), max(1, int(b_val))),
                        brightness=max(1, int(b_val)),
                    ))

                if hasattr(self._controller, "submit_frame"):
                    self._controller.submit_frame({"h": int(h_val) % 360, "s": int(s_val), "b": max(1, int(b_val))})

                # Candle flicker needs faster physics for realism
                flicker = cfg.get("flicker", False)
                time.sleep(0.016 if flicker else 0.025)

            except Exception as e:
                print(f"[Effects] Engine error: {e}")
                time.sleep(0.5)


# ── helpers ──────────────────────────────────────────────────────────────────

def _ease_out(t: float) -> float:
    """Cubic ease-out: fast start, smooth arrival."""
    return 1.0 - (1.0 - t) ** 3
