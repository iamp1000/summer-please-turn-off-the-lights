"""
Loads named modes (work / midnight / warm_white / day / gaming / music / ...)
from config.yaml and applies them to a LightController.
"""

from __future__ import annotations

import asyncio
from src.device import LightController
from src.event_loop import BackgroundLoop
from src.frame_bus import FramePacket, OutputProducer


def build_mode_segments(mode: dict, num_zones: int = 50) -> list[list[int]]:
    """
    Builds 50 independent [H, S, V] zone tuples for L930 static modes & presets.
    Supports 3 multi-zone preset layouts:
    1. 'segments': Explicit 50-IC array [[h,s,v], ...] for custom pixel-painted scenes.
    2. 'regions': Slice map [{"range": [0, 15], "hsv": [320, 100, 75]}, ...]
    3. 'stops': Multi-stop OKLab anchor points with topology ('center_out', 'pods_3', 'linear').
    Fallback: Single-color modes get a subtle, elegant center-halo depth curve on L930.
    """
    from src.visual_styles import sample_palette_oklab

    # 1. Exact 50-IC array
    if "segments" in mode and isinstance(mode["segments"], list):
        segs = [list(x) for x in mode["segments"][:num_zones]]
        if len(segs) < num_zones:
            last = segs[-1] if segs else [30, 80, 50]
            segs.extend([list(last)] * (num_zones - len(segs)))
        return segs

    # 2. Arbitrary IC Region Slices (e.g. Left Wall, Behind Monitor, Right Wall)
    if "regions" in mode and isinstance(mode["regions"], list):
        b_default = mode.get("brightness", 50)
        segs = [[0, 0, 0] for _ in range(num_zones)]
        for reg in mode["regions"]:
            start, end = reg.get("range", [0, num_zones])
            hsv = reg.get("hsv", [30, 80, b_default])
            for idx in range(max(0, start), min(num_zones, end)):
                segs[idx] = [int(hsv[0]), int(hsv[1]), int(hsv[2])]
        return segs

    # 3. Spatial Gradient / Anchor Stops
    if "stops" in mode and isinstance(mode["stops"], list):
        stops = [tuple(c) for c in mode["stops"]]
        layout = mode.get("layout", "center_out")
        b = mode.get("brightness", 50)
        segs = []
        for i in range(num_zones):
            norm = i / float(max(1, num_zones - 1))
            if layout == "center_out":
                t = abs(norm - 0.5) * 2.0
            elif layout == "pods_3":
                t = abs(((norm * 3.0) % 2.0) - 1.0)
            else:
                t = norm
            h, s, v = sample_palette_oklab(stops, t)
            v_scaled = int(max(0, min(100, (v / 100.0) * b)))
            segs.append([h, s, v_scaled])
        return segs

    # Fallback: Single color or color temperature
    b = mode.get("brightness", 50)
    has_temp = "color_temp" in mode
    if has_temp:
        kelvin = mode.get("color_temp", 4000)
        norm_k = max(0.0, min(1.0, (kelvin - 2500) / 4000.0))
        h = int(30 + (210 - 30) * norm_k)
        s = int(55 - 40 * norm_k)
    else:
        h = mode.get("hue", 30)
        s = mode.get("saturation", 80)

    # Subtle center-halo depth curve (+-8% brightness outward) to break flat monotony on L930
    segs = []
    half = (num_zones - 1) / 2.0
    for i in range(num_zones):
        dist = abs(i - half) / half
        zone_b = int(max(1, min(100, b * (1.0 - 0.08 * dist))))
        segs.append([h, s, zone_b])
    return segs


class ModeManager:
    def __init__(self, modes: dict, controller: LightController, loop_runner: BackgroundLoop,
                 frame_bus=None, dev_id: str = "strip1", arbiter=None, on_relinquish=None):
        self._modes = modes
        self._controller = controller
        self._loop_runner = loop_runner
        self._frame_bus = frame_bus
        self._dev_id = dev_id
        self._arbiter = arbiter
        self._on_relinquish = on_relinquish

    def names(self):
        return list(self._modes.keys())

    def apply(self, name: str):
        """Sync entry point -- safe to call from a hotkey callback or tray click."""
        mode = self._modes.get(name)
        if mode is None:
            raise KeyError(f"Unknown mode: {name!r}. Known modes: {self.names()}")
        output_token = None
        if self._frame_bus and self._arbiter:
            self._arbiter.claim_output(
                self._dev_id, OutputProducer.STATIC, on_relinquish=self._on_relinquish,
                renew=True,
            )
            output_token = self._frame_bus.capture_token(self._dev_id, OutputProducer.STATIC)
        future = self._loop_runner.run(self._apply_async(mode, output_token=output_token))
        return future

    async def _apply_async(self, mode: dict, output_token=None):
        """Crossfade over 600ms, publishing each rendered scene through FrameBus."""
        if output_token is None and self._frame_bus:
            output_token = self._frame_bus.capture_token(self._dev_id, OutputProducer.STATIC)
        # Grab current global state so we crossfade smoothly even if coming from an effect
        self._last_b = getattr(self._controller, "last_b", 50)
        self._last_h = getattr(self._controller, "last_h", 0)
        self._last_s = getattr(self._controller, "last_s", 0)
        self._last_k = getattr(self._controller, "last_k", 4000)
        
        target_b = mode.get("brightness", self._last_b)
        target_h = mode.get("hue", self._last_h)
        target_s = mode.get("saturation", self._last_s)
        target_k = mode.get("color_temp", self._last_k)

        # Multi-Zone L930: scene frames use the same ownership-checked route.
        if hasattr(self._controller, "set_segments"):
            segs = build_mode_segments(mode, num_zones=50)
            await self._controller.turn_on(priority=0)
            if self._frame_bus:
                if output_token:
                    generation, producer_id = output_token
                    self._frame_bus.publish(FramePacket(
                        dev_id=self._dev_id, producer=OutputProducer.STATIC,
                        segments=segs, brightness=target_b, transition=600,
                        generation=generation, producer_id=producer_id,
                    ))
            else:
                await self._controller.set_segments(segs, brightness=target_b, transition=600, priority=0)
            self._last_b = target_b
            if "hue" in mode: self._last_h = mode["hue"]
            if "saturation" in mode: self._last_s = mode["saturation"]
            if "color_temp" in mode: self._last_k = mode["color_temp"]
            return
        
        has_color = "hue" in mode
        has_temp = "color_temp" in mode
        
        await self._controller.turn_on(priority=0)
        
        steps = 4
        for i in range(1, steps + 1):
            alpha = i / float(steps)
            b = int(self._last_b + (target_b - self._last_b) * alpha)

            if has_temp:
                k = int(self._last_k + (target_k - self._last_k) * alpha)
                norm_k = max(0.0, min(1.0, (k - 2500) / 4000.0))
                h_target = int(30 + (210 - 30) * norm_k)
                s_target = int(55 - 40 * norm_k)
                h_diff = h_target - self._last_h
                if h_diff > 180: h_diff -= 360
                elif h_diff < -180: h_diff += 360
                h = int((self._last_h + h_diff * alpha) % 360)
                s = int(self._last_s + (s_target - self._last_s) * alpha)
            elif has_color:
                h_diff = target_h - self._last_h
                if h_diff > 180: h_diff -= 360
                elif h_diff < -180: h_diff += 360
                h = int((self._last_h + h_diff * alpha) % 360)
                s = int(self._last_s + (target_s - self._last_s) * alpha)
            else:
                h, s = self._last_h, self._last_s

            if self._frame_bus:
                if output_token:
                    generation, producer_id = output_token
                    self._frame_bus.publish(FramePacket(
                        dev_id=self._dev_id, producer=OutputProducer.STATIC,
                        hsv=(h, s, b), brightness=b, transition=80,
                        generation=generation, producer_id=producer_id,
                    ))
            elif has_temp:
                k = int(self._last_k + (target_k - self._last_k) * alpha)
                await self._controller.set_color_temperature(k, priority=0)
                await self._controller.set_brightness(b, priority=0)
            elif has_color:
                if hasattr(self._controller, "set_state"):
                    await self._controller.set_state(h, s, b, priority=0)
                else:
                    await self._controller.set_hue_saturation(h, s, priority=0)
                    await self._controller.set_brightness(b, priority=0)
            else:
                await self._controller.set_brightness(b, priority=0)

            if i < steps:
                await asyncio.sleep(0.08)
            
        self._last_b = target_b
        if has_temp: 
            self._last_k = target_k
        if has_color: 
            self._last_h = target_h
            self._last_s = target_s
