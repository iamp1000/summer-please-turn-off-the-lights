"""
Effect Lab — Interactive & Automated Calibration Tool for Tapo L930 Firmware Effects.

Tests and logs:
- Sequence effect parameters: up to 16 HSV colors, spread, direction (1-4), transition (0-6000 ms), expansion strategy.
- Random effect parameters: init_states, hue/saturation/brightness ranges, transition ranges, seeds (1-600).
- Native preset extraction and verification.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
import dotenv

from plugp100.api.light_effect import LightEffect
from plugp100.api.light_effect_preset import LightEffectPreset
from src.device_l930 import L930Controller


class EffectLab:
    def __init__(self, ip: str, email: str, password: str):
        self.ip = ip
        self.email = email
        self.password = password
        self.ctrl = L930Controller(ip, email, password)

    async def connect(self):
        return await self.ctrl.connect()

    async def extract_native_templates(self) -> Dict[str, Any]:
        """Applies native effects, reads back lighting-effect data via get_device_info, and extracts definitions."""
        templates = {}
        presets = [
            LightEffectPreset.Rainbow,
            LightEffectPreset.Aurora,
            LightEffectPreset.Ocean,
            LightEffectPreset.Lightning,
            LightEffectPreset.Raindrop,
            LightEffectPreset.Flicker,
            LightEffectPreset.Sunrise,
            LightEffectPreset.Sunset,
            LightEffectPreset.CandyCane,
            LightEffectPreset.HauntedMansion,
            LightEffectPreset.Spring,
            LightEffectPreset.Icicle,
            LightEffectPreset.Christmas,
            LightEffectPreset.ChristmasLight,
            LightEffectPreset.Hanukkah,
            LightEffectPreset.Valentines,
            LightEffectPreset.BubblingCauldron,
        ]

        for preset in presets:
            try:
                fx = preset.to_effect()
                res = await self.ctrl._device.set_light_effect(fx)
                await asyncio.sleep(0.35)
                raw = await self.ctrl._device.client.get_device_info()
                data = raw.get_or_else({})
                def_state = data.get("default_states", {}).get("state", {}).get("lighting_effect", {})
                templates[preset.name] = def_state
            except Exception as e:
                templates[preset.name] = {"error": str(e)}

        return templates

    async def test_sequence_parameters(self) -> Dict[str, Any]:
        """Tests sequence parameters across spread, directions, colors, and transitions."""
        results = {}

        # 1. Spread testing (1, 5, 10, 16, 25)
        spread_results = {}
        seq = [[0, 100, 100], [120, 100, 100], [240, 100, 100]]
        for sp in [1, 5, 10, 16, 25]:
            fx = LightEffect(
                id=f"TapoStrip_lab_spread_{sp:02d}",
                name=f"Spread{sp}",
                display_colors=seq,
                enable=1,
                brightness=80,
                custom=1,
                direction=1,
                duration=0,
                expansion_strategy=1,
                repeat_times=0,
                segments=[0],
                sequence=seq,
                spread=sp,
                transition=1000,
                type="sequence",
            )
            res = await self.ctrl._device.set_light_effect(fx)
            spread_results[str(sp)] = res.is_success() if hasattr(res, "is_success") else bool(res)
            await asyncio.sleep(0.2)
        results["spread"] = spread_results

        # 2. Direction testing (1..4)
        dir_results = {}
        for d in [1, 2, 3, 4]:
            fx = LightEffect(
                id=f"TapoStrip_lab_dir_{d}",
                name=f"Dir{d}",
                display_colors=seq,
                enable=1,
                brightness=80,
                custom=1,
                direction=d,
                duration=0,
                expansion_strategy=1,
                repeat_times=0,
                segments=[0],
                sequence=seq,
                spread=8,
                transition=1000,
                type="sequence",
            )
            res = await self.ctrl._device.set_light_effect(fx)
            dir_results[str(d)] = res.is_success() if hasattr(res, "is_success") else bool(res)
            await asyncio.sleep(0.2)
        results["direction"] = dir_results

        # 3. Maximum color count (up to 16)
        color_results = {}
        for count in [4, 8, 12, 16]:
            col_seq = [[int(i * (360 / count)), 100, 100] for i in range(count)]
            fx = LightEffect(
                id=f"TapoStrip_lab_colors_{count:02d}",
                name=f"Colors{count}",
                display_colors=col_seq[:4],
                enable=1,
                brightness=80,
                custom=1,
                direction=1,
                duration=0,
                expansion_strategy=1,
                repeat_times=0,
                segments=[0],
                sequence=col_seq,
                spread=4,
                transition=1000,
                type="sequence",
            )
            res = await self.ctrl._device.set_light_effect(fx)
            color_results[str(count)] = res.is_success() if hasattr(res, "is_success") else bool(res)
            await asyncio.sleep(0.2)
        results["color_count"] = color_results

        # 4. Transition limits (0, 500, 2000, 6000)
        trans_results = {}
        for t in [0, 500, 2000, 6000]:
            fx = LightEffect(
                id=f"TapoStrip_lab_trans_{t:04d}",
                name=f"Trans{t}",
                display_colors=seq,
                enable=1,
                brightness=80,
                custom=1,
                direction=1,
                duration=0,
                expansion_strategy=1,
                repeat_times=0,
                segments=[0],
                sequence=seq,
                spread=8,
                transition=t,
                type="sequence",
            )
            res = await self.ctrl._device.set_light_effect(fx)
            trans_results[str(t)] = res.is_success() if hasattr(res, "is_success") else bool(res)
            await asyncio.sleep(0.2)
        results["transitions"] = trans_results

        return results

    async def test_random_parameters(self) -> Dict[str, Any]:
        """Tests random effect configurations and seeds."""
        results = {}
        for seed in [1, 24, 100, 600]:
            fx = LightEffect(
                id=f"TapoStrip_lab_rnd_seed_{seed}",
                name=f"RndSeed{seed}",
                display_colors=[[200, 50, 100]],
                enable=1,
                brightness=80,
                custom=1,
                duration=0,
                expansion_strategy=1,
                fadeoff=500,
                hue_range=[180, 260],
                init_states=[[220, 50, 100]],
                random_seed=seed,
                repeat_times=None,
                saturation_range=[40, 80],
                brightness_range=[20, 100],
                segments=[0],
                sequence=None,
                transition=0,
                transition_range=[200, 1000],
                type="random",
            )
            res = await self.ctrl._device.set_light_effect(fx)
            results[f"seed_{seed}"] = res.is_success() if hasattr(res, "is_success") else bool(res)
            await asyncio.sleep(0.2)
        return results

    async def close(self):
        if self.ctrl._device and hasattr(self.ctrl._device, "client"):
            await self.ctrl._device.client.close()


async def main():
    env = dotenv.dotenv_values(".env")
    email = env.get("TAPO_EMAIL")
    password = env.get("TAPO_PASSWORD")
    if not email or not password:
        print("Missing credentials in .env")
        sys.exit(1)

    lab = EffectLab("10.0.0.24", email, password)
    print("Connecting to L930 for Effect Lab calibration...")
    await lab.connect()

    print("\n--- Extracting Native Firmware Templates ---")
    templates = await lab.extract_native_templates()
    for name, tpl in templates.items():
        print(f"[{name}]: type={tpl.get('type')}, direction={tpl.get('direction')}, spread={tpl.get('spread')}, trans={tpl.get('transition')}")

    print("\n--- Testing Sequence Effect Parameters ---")
    seq_res = await lab.test_sequence_parameters()
    print("Sequence Results:", json.dumps(seq_res, indent=2))

    print("\n--- Testing Random Effect Parameters ---")
    rnd_res = await lab.test_random_parameters()
    print("Random Results:", json.dumps(rnd_res, indent=2))

    await lab.close()


if __name__ == "__main__":
    asyncio.run(main())
