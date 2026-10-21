from __future__ import annotations
import asyncio
import math
import threading
import time
from typing import Tuple, List, Optional, Dict, Any
import numpy as np

from src.pipeline import (
    tapo_hsv_to_rgb,
    rgb_to_oklab,
    oklab_to_rgb,
    linear_rgb_to_oklab,
    oklab_to_linear_rgb,
    rgb_to_oklch,
    oklch_to_rgb,
    rgb_to_tapo_hsv,
    AsymmetricSmoother,
)
from src.frame_bus import FramePacket, OutputProducer


class CompositeSystemManager:
    """
    Coordinates L900 (single-zone ambient fill) and L930 (WRGBIC 50-zone bias strip)
    as a single unified lighting system.

    Composite Modes:
      - "off"           : Independent control per device.
      - "average"       : L900 displays the spatial perceptual OKLab average of active zones on L930.
      - "complementary" : L900 displays the 180° perceptual complementary color to L930 for cinematic depth.
      - "contrast"      : L900 provides a slower, softer ambient room counterpart (lower saturation, slow decay).
      - "sync"          : L900 follows the dominant hue and brightness of L930 directly.

    Phase O enhancements:
      - Reads exclusively from FrameBus without private attribute access.
      - Luminance-weighted OKLab spatial color average excluding near-black zones.
      - Derives brightness from mean luminance or soft maximum (not max_v).
      - Time-based smoothing with alpha = 1 - exp(-dt / tau).
      - Strict ownership coordination via OutputArbiter.
    """

    def __init__(self, hub):
        self.hub = hub
        self.mode = "off"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._output_token: Optional[tuple[int, str]] = None

        # Time-based smoothers for brightness, chromaticity, and saturation
        self._v_smoother = AsymmetricSmoother(tau_attack=0.06, tau_decay=0.30)
        self._v_contrast_smoother = AsymmetricSmoother(tau_attack=0.12, tau_decay=0.60)
        self._a_smoother = AsymmetricSmoother(tau_attack=0.10, tau_decay=0.25)
        self._b_smoother = AsymmetricSmoother(tau_attack=0.10, tau_decay=0.25)
        self._s_smoother = AsymmetricSmoother(tau_attack=0.08, tau_decay=0.30)
        self._last_time = time.time()

    def is_active(self) -> bool:
        return self.mode != "off" and self._running

    def set_mode(self, mode: str):
        valid = ("off", "average", "complementary", "contrast", "sync")
        if mode in valid:
            self.mode = mode
            if mode != "off":
                l900_id = self._get_l900_dev_id() or "strip1"
                if hasattr(self.hub, "arbiter") and self.hub.arbiter:
                    self.hub.arbiter.claim_output(
                        l900_id,
                        OutputProducer.COMPOSITE_FOLLOWER,
                        on_relinquish=self._on_arbiter_relinquish,
                    )
                if not self._running:
                    self.start()
            elif mode == "off" and self._running:
                self.stop()

    def _on_arbiter_relinquish(self):
        """Called by OutputArbiter when another producer claims the L900 strip."""
        self._running = False
        self.mode = "off"

    def start(self):
        if self._running:
            return
        l900_id = self._get_l900_dev_id() or "strip1"
        self._output_token = (
            self.hub.frame_bus.capture_token(l900_id, OutputProducer.COMPOSITE_FOLLOWER)
            if getattr(self.hub, "frame_bus", None) else None
        )
        self._running = True
        self._last_time = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True, name="CompositeSystemWorker")
        self._thread.start()

    def stop(self):
        self._running = False
        self.mode = "off"
        l900_id = self._get_l900_dev_id() or "strip1"
        if hasattr(self.hub, "arbiter") and self.hub.arbiter:
            self.hub.arbiter.release_output(l900_id, OutputProducer.COMPOSITE_FOLLOWER)

    def _get_l930_dev_id(self) -> Optional[str]:
        if not hasattr(self.hub, "devices"):
            return None
        for dev_id, ctx in self.hub.devices.items():
            if getattr(ctx, "model", "") == "L930":
                return dev_id
        return None

    def _get_l900_dev_id(self) -> Optional[str]:
        if not hasattr(self.hub, "devices"):
            return None
        for dev_id, ctx in self.hub.devices.items():
            if getattr(ctx, "model", "") != "L930":
                return dev_id
        return None

    def _get_l930_segments(self) -> Optional[List[List[int]]]:
        l930_id = self._get_l930_dev_id() or "strip2"
        # 1. Primary: Read from FrameBus (decoupled pub/sub, zero private attribute access)
        if hasattr(self.hub, "frame_bus") and self.hub.frame_bus:
            packet = self.hub.frame_bus.get_latest_frame(l930_id)
            if packet and packet.segments:
                return packet.segments

        # 2. Fallback for tests/unmigrated controllers
        if hasattr(self.hub, "devices"):
            ctx = self.hub.devices.get(l930_id)
            if ctx:
                if hasattr(ctx, "fx_engine") and hasattr(ctx.fx_engine, "_rendered_segs") and ctx.fx_engine.is_running():
                    return ctx.fx_engine._rendered_segs
                if hasattr(ctx, "audio_sync") and hasattr(ctx.audio_sync, "_rendered_segs") and ctx.audio_sync.is_running():
                    return ctx.audio_sync._rendered_segs
                if hasattr(ctx, "screen_sync") and hasattr(ctx.screen_sync, "_rendered_segs") and ctx.screen_sync.is_running():
                    return ctx.screen_sync._rendered_segs
                if hasattr(ctx.controller, "last_submitted_frame"):
                    f = ctx.controller.last_submitted_frame
                    if f and "segments" in f:
                        return f["segments"]
                if hasattr(ctx.controller, "last_segments"):
                    return ctx.controller.last_segments
        return None

    def _get_l900_context(self):
        if not hasattr(self.hub, "devices"):
            return None
        for ctx in self.hub.devices.values():
            if getattr(ctx, "model", "") != "L930":
                return ctx
        return None

    def _run(self):
        self._last_time = time.time()
        while self._running:
            try:
                if self.mode == "off":
                    time.sleep(0.05)
                    continue

                l900_id = self._get_l900_dev_id() or "strip1"
                if hasattr(self.hub, "arbiter") and self.hub.arbiter:
                    if not self.hub.arbiter.can_submit(l900_id, OutputProducer.COMPOSITE_FOLLOWER):
                        time.sleep(0.05)
                        continue

                segs = self._get_l930_segments()
                l900_ctx = self._get_l900_context()

                if not segs or len(segs) == 0:
                    time.sleep(0.04)
                    continue

                now = time.time()
                dt = max(0.001, min(0.5, now - self._last_time))
                self._last_time = now

                # 1. Luminance-weighted OKLab spatial color average, excluding near-black zones
                total_L = 0.0
                total_a = 0.0
                total_b = 0.0
                total_w = 0.0
                zone_vs = []

                for h, s, v in segs:
                    zone_vs.append(v)
                    if v < 2:
                        continue  # Exclude near-black zones
                    r, g, b = tapo_hsv_to_rgb(h, s, v)
                    L, a, b_val = linear_rgb_to_oklab(r, g, b)
                    if L < 0.02:
                        continue  # Exclude near-black luminance

                    w = v / 100.0
                    total_L += L * w
                    total_a += a * w
                    total_b += b_val * w
                    total_w += w

                # 2. Derive target brightness from mean luminance or soft maximum (not max_v)
                if zone_vs:
                    mean_v = float(np.mean(zone_vs))
                    p90_v = float(np.percentile(zone_vs, 90))
                    soft_max_v = 0.70 * mean_v + 0.30 * p90_v
                else:
                    soft_max_v = 0.0

                if total_w < 1e-4 or soft_max_v < 0.5:
                    target_h, target_s, target_v = 0, 0, 0
                    target_a, target_b = 0.0, 0.0
                else:
                    avg_L = total_L / total_w
                    avg_a = total_a / total_w
                    avg_b = total_b / total_w

                    target_a = avg_a
                    target_b = avg_b

                    avg_r, avg_g, avg_b_col = oklab_to_linear_rgb(avg_L, avg_a, avg_b)
                    avg_h, avg_s, avg_v = rgb_to_tapo_hsv(avg_r, avg_g, avg_b_col)

                    if self.mode == "average":
                        target_h = avg_h
                        target_s = avg_s
                        target_v = int(soft_max_v * 0.85)

                    elif self.mode == "complementary":
                        L, C, h_deg = rgb_to_oklch(avg_r, avg_g, avg_b_col)
                        comp_h = (h_deg + 180.0) % 360.0
                        cr, cg, cb = oklch_to_rgb(L, C, comp_h)
                        ch, cs, cv = rgb_to_tapo_hsv(cr, cg, cb)
                        target_h = ch
                        target_s = cs
                        target_v = int(soft_max_v * 0.75)
                        _, target_a, target_b = linear_rgb_to_oklab(cr, cg, cb)

                    elif self.mode == "contrast":
                        target_h = avg_h
                        target_s = int(avg_s * 0.55)
                        target_v = int(soft_max_v * 0.60)

                    elif self.mode == "sync":
                        target_h = avg_h
                        target_s = avg_s
                        target_v = int(soft_max_v)

                # 3. Apply time-based asymmetrical smoothing (alpha = 1 - exp(-dt / tau))
                v_smoother = self._v_contrast_smoother if self.mode == "contrast" else self._v_smoother
                smoothed_v = int(round(v_smoother.update(float(target_v), dt=dt)))
                smoothed_a = self._a_smoother.update(target_a, dt=dt)
                smoothed_b = self._b_smoother.update(target_b, dt=dt)
                smoothed_s = int(round(self._s_smoother.update(float(target_s), dt=dt)))

                if abs(smoothed_a) > 1e-4 or abs(smoothed_b) > 1e-4:
                    hue_rad = math.atan2(smoothed_b, smoothed_a)
                    smoothed_h = int(round(math.degrees(hue_rad) % 360.0))
                else:
                    smoothed_h = target_h

                if smoothed_v == 0:
                    final_h, final_s, final_v = 0, 0, 0
                else:
                    final_h = smoothed_h
                    final_s = max(0, min(100, smoothed_s))
                    final_v = max(1, min(100, smoothed_v))

                # Respect the L900 master brightness inside the rendered frame, so
                # composite output never needs a direct controller brightness write.
                if l900_ctx is not None:
                    brightness_ceiling = max(0, min(100, int(l900_ctx.state.get("brightness", 100)))) / 100.0
                    final_v = max(0, min(100, int(round(final_v * brightness_ceiling))))
                    if final_v == 0:
                        final_h, final_s = 0, 0

                # 4. Submit only to the authoritative FrameBus consumer.
                if getattr(self.hub, "frame_bus", None) and self._output_token:
                    generation, producer_id = self._output_token
                    self.hub.frame_bus.publish_frame(
                        l900_id, OutputProducer.COMPOSITE_FOLLOWER,
                        {"h": final_h, "s": final_s, "b": final_v},
                        generation=generation, producer_id=producer_id,
                    )

                time.sleep(0.033)  # ~30 Hz smooth update pacing
            except Exception:
                time.sleep(0.05)
