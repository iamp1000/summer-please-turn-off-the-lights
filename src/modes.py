"""
Loads named modes (work / midnight / warm_white / day / gaming / music / ...)
from config.yaml and applies them to a LightController.
"""

from __future__ import annotations

import asyncio
from src.device import LightController
from src.event_loop import BackgroundLoop


class ModeManager:
    def __init__(self, modes: dict, controller: LightController, loop_runner: BackgroundLoop):
        self._modes = modes
        self._controller = controller
        self._loop_runner = loop_runner

    def names(self):
        return list(self._modes.keys())

    def apply(self, name: str):
        """Sync entry point -- safe to call from a hotkey callback or tray click."""
        mode = self._modes.get(name)
        if mode is None:
            raise KeyError(f"Unknown mode: {name!r}. Known modes: {self.names()}")
        future = self._loop_runner.run(self._apply_async(mode))
        return future

    async def _apply_async(self, mode: dict):
        """Crossfade over 600ms for a premium '$200 smart light' feel."""
        # Grab current global state so we crossfade smoothly even if coming from an effect
        self._last_b = self._controller.last_b
        self._last_h = self._controller.last_h
        self._last_s = self._controller.last_s
        self._last_k = self._controller.last_k
        
        target_b = mode.get("brightness", self._last_b)
        target_h = mode.get("hue", self._last_h)
        target_s = mode.get("saturation", self._last_s)
        target_k = mode.get("color_temp", self._last_k)
        
        has_color = "hue" in mode
        has_temp = "color_temp" in mode
        
        await self._controller.turn_on(priority=0)
        
        steps = 4
        for i in range(1, steps + 1):
            alpha = i / float(steps)
            b = int(self._last_b + (target_b - self._last_b) * alpha)
            
            if has_temp:
                k = int(self._last_k + (target_k - self._last_k) * alpha)
                await self._controller.set_color_temperature(k, priority=0)
                await self._controller.set_brightness(b, priority=0)
            elif has_color:
                h_diff = target_h - self._last_h
                if h_diff > 180: h_diff -= 360
                elif h_diff < -180: h_diff += 360
                
                h = int((self._last_h + h_diff * alpha) % 360)
                s = int(self._last_s + (target_s - self._last_s) * alpha)
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
