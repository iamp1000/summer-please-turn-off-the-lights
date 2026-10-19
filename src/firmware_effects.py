"""
L930 Firmware Effect Builder & Definitions.

Provides structured builders for:
1. Firmware Sequence effects (up to 16 HSV colors, spread, direction 1-4, transition 0-6000 ms, repeat_times=0).
2. Firmware Random effects (init_states, hue/sat/bright ranges, transition_range, random_seed 1-600, fadeoff).

Validates all firmware constraints:
- Max 16 colors in sequence
- Transition in [0, 6000] ms
- Seed in [1, 600]
- Display colors <= 4
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple
from plugp100.api.light_effect import LightEffect


# ── Built-in Perceptual HSV Color Palettes (Curated for Bedroom & Ambient) ────
# Palettes: Auto, Sunset, Forest, Fire, Pastel, Tide, Dusk, Ember, WarmMono.
# (Neon and Cyberpunk removed).

PALETTES: Dict[str, List[Tuple[int, int, int]]] = {
    # Sunset: deep night purple -> crimson -> sunset orange -> warm amber -> golden light
    "sunset": [
        (280, 85, 25),
        (345, 90, 75),
        (22, 95, 90),
        (38, 90, 95),
        (48, 60, 100),
    ],
    # Forest: abyssal pine -> emerald -> spring leaf -> lime zest -> sunlight canopy
    "forest": [
        (160, 90, 30),
        (145, 90, 65),
        (120, 80, 80),
        (85, 75, 85),
        (55, 60, 95),
    ],
    # Fire: cold ember -> dark blood red -> blaze orange -> flame yellow -> warm white hot
    "fire": [
        (0, 100, 20),
        (8, 100, 75),
        (24, 100, 95),
        (42, 95, 100),
        (50, 40, 100),
    ],
    # Pastel: soft lavender -> powder sky blue -> tranquil mint -> soft peach
    "pastel": [
        (265, 45, 85),
        (205, 45, 90),
        (155, 40, 90),
        (28, 50, 95),
    ],
    # Tide: Pacifica oceanic waves (deep ocean navy -> cerulean -> aquamarine -> seafoam crest)
    "tide": [
        (225, 90, 35),
        (210, 85, 65),
        (190, 80, 80),
        (170, 65, 85),
        (160, 30, 95),
    ],
    # Dusk: twilight rose & violet gradient (warm rose -> magenta twilight -> deep amethyst violet)
    "dusk": [
        (15, 75, 80),
        (335, 75, 75),
        (295, 80, 70),
        (260, 85, 60),
    ],
    # Ember: glowing coals (deep mahogany red -> glowing ember orange -> dim warm amber)
    "ember": [
        (5, 100, 45),
        (16, 95, 65),
        (28, 90, 75),
    ],
    # WarmMono: ultra-clean cozy 2700K warm white (subtle golden warmth)
    "warm_mono": [
        (32, 45, 90),
        (34, 40, 95),
        (30, 50, 85),
    ],
    # Auto fallback
    "auto": [
        (215, 80, 85),
        (180, 85, 85),
        (280, 75, 80),
        (42, 90, 90),
    ],
}


def get_palette_hsv(palette_name: str) -> List[Tuple[int, int, int]]:
    """Resolves palette name to list of (H, S, V) tuples."""
    key = (palette_name or "sunset").strip().lower()
    return PALETTES.get(key, PALETTES["sunset"])


def make_effect_id(name: str) -> str:
    """Generates a stable 32-hex character ID required by L930 firmware."""
    return hashlib.md5(f"tapo_l930_fw_{name}".encode("utf-8")).hexdigest()


def build_firmware_sequence_effect(
    name: str,
    sequence: List[List[int] | Tuple[int, int, int]],
    spread: int = 10,
    direction: int = 1,
    transition: int = 1500,
    repeat_times: int = 0,
    expansion_strategy: int = 1,
    brightness: int = 100,
) -> LightEffect:
    """
    Builds a firmware-looping sequence effect adhering strictly to L930 hardware limits:
    - sequence <= 16 colors
    - 0 <= transition <= 6000 ms
    - direction in [1, 2, 3, 4]
    - display_colors <= 4
    """
    if not sequence:
        sequence = [(200, 100, 100), (40, 100, 100)]

    # Enforce hardware limit of 16 colors max
    seq_clamped = [[int(c[0]) % 360, max(0, min(100, int(c[1]))), max(0, min(100, int(c[2])))] for c in sequence[:16]]

    # Enforce hardware transition limits: 0..6000 ms
    trans_clamped = max(0, min(6000, int(transition)))

    # Direction in [1..4]
    dir_clamped = max(1, min(4, int(direction)))

    # Display colors for Tapo app card icon (up to 4 colors)
    disp_colors = seq_clamped[:4]

    fx_id = make_effect_id(name)

    return LightEffect(
        id=fx_id,
        name=name,
        display_colors=disp_colors,
        enable=1,
        brightness=max(1, min(100, int(brightness))),
        custom=1,
        direction=dir_clamped,
        duration=0,
        expansion_strategy=expansion_strategy,
        repeat_times=repeat_times,
        segments=[0],
        sequence=seq_clamped,
        spread=max(1, int(spread)),
        transition=trans_clamped,
        type="sequence",
    )


def build_firmware_random_effect(
    name: str,
    hue_range: Tuple[int, int] | List[int],
    saturation_range: Tuple[int, int] | List[int] = (30, 100),
    brightness_range: Tuple[int, int] | List[int] = (20, 100),
    transition_range: Tuple[int, int] | List[int] = (200, 1000),
    random_seed: int = 100,
    fadeoff: int = 500,
    init_state: Optional[List[int] | Tuple[int, int, int]] = None,
    backgrounds: Optional[List[List[int]]] = None,
    brightness: int = 100,
) -> LightEffect:
    """
    Builds a firmware-looping random effect adhering strictly to L930 hardware limits:
    - seed in [1, 600]
    - 0 <= transition <= 6000 ms
    """
    seed_clamped = max(1, min(600, int(random_seed)))
    h_range = [int(hue_range[0]) % 360, int(hue_range[1]) % 360]
    s_range = [max(0, min(100, int(saturation_range[0]))), max(0, min(100, int(saturation_range[1])))]
    b_range = [max(0, min(100, int(brightness_range[0]))), max(0, min(100, int(brightness_range[1])))]
    t_range = [max(0, min(6000, int(transition_range[0]))), max(0, min(6000, int(transition_range[1])))]

    init_s = [list(init_state)] if init_state else [[h_range[0], s_range[0], b_range[1]]]
    bg_list = backgrounds or []
    disp_colors = [[h_range[0], s_range[1], b_range[1]]]

    fx_id = make_effect_id(name)

    return LightEffect(
        id=fx_id,
        name=name,
        display_colors=disp_colors,
        enable=1,
        brightness=max(1, min(100, int(brightness))),
        custom=1,
        duration=0,
        expansion_strategy=1,
        fadeoff=max(0, int(fadeoff)),
        hue_range=h_range,
        saturation_range=s_range,
        brightness_range=b_range,
        init_states=init_s,
        backgrounds=bg_list,
        random_seed=seed_clamped,
        repeat_times=None,
        segments=[0],
        sequence=None,
        transition=0,
        transition_range=t_range,
        type="random",
    )
