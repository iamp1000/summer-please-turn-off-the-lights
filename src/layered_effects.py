from __future__ import annotations
import math
import random
import time
from typing import Tuple, List, Dict, Callable
import numpy as np

from src.pipeline import lerp_oklab, rgb_to_tapo_hsv, tapo_hsv_to_rgb

NUM_SEGMENTS = 50

# ── Procedural Fractal Value / Perlin Noise ──────────────────────────────────

class ValueNoise1D:
    """
    Continuous smooth multi-octave 1D/2D procedural noise with cubic Hermite spline easing.
    Produces organic natural motions without jerky steps or discrete jumps.
    """

    def __init__(self, seed: int = 42):
        rng = np.random.RandomState(seed)
        self._table = rng.uniform(0.0, 1.0, 1024).astype(np.float32)

    def _sample(self, x: float) -> float:
        xi = int(math.floor(x))
        xf = x - xi
        # Quintic Hermite easing: 6t^5 - 15t^4 + 10t^3
        u = xf * xf * xf * (xf * (xf * 6.0 - 15.0) + 10.0)
        i0 = xi & 1023
        i1 = (xi + 1) & 1023
        v0 = self._table[i0]
        v1 = self._table[i1]
        return float(v0 + u * (v1 - v0))

    def noise(self, x: float, octaves: int = 3, persistence: float = 0.5) -> float:
        total = 0.0
        frequency = 1.0
        amplitude = 1.0
        max_value = 0.0
        for _ in range(octaves):
            total += self._sample(x * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= 2.0
        return total / max_value


# ── Curated Perceptual Color Palettes ─────────────────────────────────────────

PALETTES: Dict[str, List[Tuple[float, Tuple[float, float, float]]]] = {
    "sunset": [
        (0.00, (0.05, 0.01, 0.08)),  # Night purple
        (0.25, (0.75, 0.05, 0.20)),  # Crimson
        (0.55, (1.00, 0.35, 0.02)),  # Sunset orange
        (0.80, (1.00, 0.75, 0.15)),  # Warm amber
        (1.00, (1.00, 0.95, 0.65)),  # Golden light
    ],
    "cyberpunk": [
        (0.00, (0.02, 0.01, 0.12)),  # Dark void
        (0.30, (0.00, 0.90, 1.00)),  # Electric cyan
        (0.65, (1.00, 0.00, 0.45)),  # Neon magenta
        (0.85, (0.60, 0.00, 1.00)),  # Violet purple
        (1.00, (1.00, 0.92, 0.05)),  # Neon yellow
    ],
    "forest": [
        (0.00, (0.01, 0.05, 0.02)),  # Abyssal pine
        (0.35, (0.04, 0.45, 0.18)),  # Emerald
        (0.65, (0.15, 0.75, 0.15)),  # Spring leaf
        (0.85, (0.50, 0.85, 0.10)),  # Lime zest
        (1.00, (0.95, 0.90, 0.40)),  # Sunlight canopy
    ],
    "ocean": [
        (0.00, (0.01, 0.03, 0.10)),  # Oceanic abyss
        (0.35, (0.00, 0.30, 0.65)),  # Deep blue
        (0.65, (0.02, 0.70, 0.85)),  # Cerulean
        (0.85, (0.20, 0.95, 0.90)),  # Aquamarine
        (1.00, (0.85, 0.98, 1.00)),  # Seafoam crest
    ],
    "fire": [
        (0.00, (0.00, 0.00, 0.00)),  # Cold ember
        (0.20, (0.45, 0.02, 0.00)),  # Dark blood red
        (0.50, (0.95, 0.25, 0.00)),  # Blaze orange
        (0.80, (1.00, 0.75, 0.05)),  # Flame yellow
        (1.00, (1.00, 1.00, 0.85)),  # White hot
    ],
    "aurora": [
        (0.00, (0.02, 0.05, 0.15)),  # Arctic twilight
        (0.35, (0.05, 0.90, 0.45)),  # Emerald ribbon
        (0.70, (0.10, 0.45, 0.95)),  # Royal blue
        (1.00, (0.75, 0.20, 0.85)),  # Magenta curtains
    ],
    "plasma": [
        (0.00, (0.08, 0.00, 0.20)),  # Deep violet
        (0.35, (0.85, 0.05, 0.40)),  # Hot pink
        (0.70, (0.15, 0.45, 0.95)),  # Electric blue
        (1.00, (0.05, 0.95, 0.85)),  # Ionized cyan
    ],
    "ambient_drift": [
        (0.00, (0.05, 0.02, 0.15)),  # Deep twilight indigo
        (0.35, (0.50, 0.15, 0.85)),  # Cosmic violet
        (0.70, (0.75, 0.35, 0.95)),  # Orchid magenta
        (1.00, (0.90, 0.75, 1.00)),  # Pale lavender starlight
    ],
    "sakura": [
        (0.00, (0.12, 0.02, 0.08)),  # Plum dark
        (0.35, (0.85, 0.20, 0.50)),  # Rose bloom
        (0.70, (0.98, 0.55, 0.75)),  # Cherry blossom pink
        (1.00, (1.00, 0.92, 0.96)),  # Soft petal white
    ],
    "golden_hour": [
        (0.00, (0.12, 0.04, 0.01)),  # Deep twilight horizon
        (0.35, (0.92, 0.35, 0.05)),  # Sunset orange
        (0.70, (0.98, 0.68, 0.10)),  # Golden amber
        (1.00, (1.00, 0.94, 0.60)),  # Radiating sunlit gold
    ],
    "deep_ocean": [
        (0.00, (0.01, 0.03, 0.12)),  # Abyssal midnight navy
        (0.35, (0.02, 0.30, 0.70)),  # Deep cerulean
        (0.70, (0.05, 0.75, 0.88)),  # Bioluminescent cyan
        (1.00, (0.60, 0.95, 0.98)),  # Seafoam crest
    ],
}

def sample_palette(palette_name: str, t: float) -> Tuple[float, float, float]:
    """
    Samples a color palette at point t in [0.0, 1.0] using perceptual OKLab interpolation.
    """
    pts = PALETTES.get(palette_name, PALETTES["sunset"])
    t_clamped = max(0.0, min(1.0, t))

    if t_clamped <= pts[0][0]:
        return pts[0][1]
    if t_clamped >= pts[-1][0]:
        return pts[-1][1]

    for i in range(len(pts) - 1):
        p0_pos, p0_col = pts[i]
        p1_pos, p1_col = pts[i + 1]
        if p0_pos <= t_clamped <= p1_pos:
            local_t = (t_clamped - p0_pos) / max(1e-5, p1_pos - p0_pos)
            return lerp_oklab(p0_col, p1_col, local_t)

    return pts[-1][1]


# ── Heat Diffusion Physics Simulation ────────────────────────────────────────

class HeatDiffusionSimulation:
    """
    True 1D thermal dissipation model for hyper-realistic fire.
    Heat diffuses across neighboring zones while cooling upward, with
    random thermal sparks ignited at the base.
    """

    def __init__(self, num_zones: int = NUM_SEGMENTS, cooling: float = 0.06, spark_prob: float = 0.35):
        self.num_zones = num_zones
        self.cooling = cooling
        self.spark_prob = spark_prob
        self.heat = np.zeros(num_zones, dtype=np.float32)

    def tick(self) -> np.ndarray:
        # 1. Thermal dissipation & cooling
        diffused = self.heat.copy()
        for i in range(1, self.num_zones - 1):
            diffused[i] = (self.heat[i - 1] + 2.0 * self.heat[i] + self.heat[i + 1]) / 4.0

        # Cool down
        cool_rate = np.random.uniform(self.cooling * 0.7, self.cooling * 1.3, self.num_zones)
        self.heat = np.maximum(0.0, diffused - cool_rate)

        # 2. Random ignition at source zones (first 6 zones)
        if random.random() < self.spark_prob:
            ignite_idx = random.randint(0, min(5, self.num_zones - 1))
            self.heat[ignite_idx] = min(1.0, self.heat[ignite_idx] + random.uniform(0.6, 1.0))

        # Secondary convection drift toward outer edges
        for i in range(self.num_zones - 1, 0, -1):
            self.heat[i] = 0.75 * self.heat[i] + 0.25 * self.heat[i - 1]

        return self.heat


# ── Decaying Beat Ripple Engine ──────────────────────────────────────────────

class DecayingBeatRipple:
    """Expanding radial shockwave with exponential decay triggered by audio beats."""

    def __init__(self, center: float = 25.0, speed: float = 1.4, width: float = 4.5, decay: float = 0.92):
        self.center = center
        self.speed = speed
        self.width = width
        self.decay = decay
        self.radius = 0.0
        self.amplitude = 1.0
        self.active = True

    def update(self) -> bool:
        self.radius += self.speed
        self.amplitude *= self.decay
        if self.amplitude < 0.02 or self.radius > (NUM_SEGMENTS / 2.0 + 8.0):
            self.active = False
        return self.active

    def evaluate(self, zone_idx: int) -> float:
        dist = abs(zone_idx - self.center)
        ring_dist = abs(dist - self.radius)
        if ring_dist < self.width:
            intensity = (1.0 - ring_dist / self.width) ** 2
            return intensity * self.amplitude
        return 0.0


# ── Layer Compositor & Blend Modes ───────────────────────────────────────────

def blend_channels(base: float, effect: float, mode: str = "add") -> float:
    """Blends two 0.0-1.0 channel values using selected blend mode."""
    if mode == "add":
        return min(1.0, base + effect)
    elif mode == "screen":
        return 1.0 - (1.0 - base) * (1.0 - effect)
    elif mode == "overlay":
        if base < 0.5:
            return min(1.0, 2.0 * base * effect)
        else:
            return min(1.0, 1.0 - 2.0 * (1.0 - base) * (1.0 - effect))
    elif mode == "multiply":
        return base * effect
    # Normal alpha blend
    return effect

def composite_layers(
    base: List[Tuple[float, float, float]],
    effect: List[Tuple[float, float, float]] | None = None,
    overlay: List[Tuple[float, float, float]] | None = None,
    effect_opacity: float = 1.0,
    overlay_opacity: float = 1.0,
    effect_mode: str = "add",
    overlay_mode: str = "screen"
) -> List[Tuple[float, float, float]]:
    """
    Composites 3 independent 50-zone render buffers:
      Layer 1: Base Layer (e.g. ambient gradient, perlin flow, ambilight)
      Layer 2: Effect Layer (e.g. traveling waves, particles, heat diffusion)
      Layer 3: Overlay Layer (e.g. beat ripples, strobe flash, laser sparkles)
    """
    result = []
    for i in range(NUM_SEGMENTS):
        br, bg, bb = base[i]

        # Apply Layer 2 (Effect)
        if effect is not None:
            er, eg, eb = effect[i]
            er_scaled = er * effect_opacity
            eg_scaled = eg * effect_opacity
            eb_scaled = eb * effect_opacity
            br = blend_channels(br, er_scaled, effect_mode)
            bg = blend_channels(bg, eg_scaled, effect_mode)
            bb = blend_channels(bb, eb_scaled, effect_mode)

        # Apply Layer 3 (Overlay)
        if overlay is not None:
            or_, og, ob = overlay[i]
            or_scaled = or_ * overlay_opacity
            og_scaled = og * overlay_opacity
            ob_scaled = ob * overlay_opacity
            br = blend_channels(br, or_scaled, overlay_mode)
            bg = blend_channels(bg, og_scaled, overlay_mode)
            bb = blend_channels(bb, ob_scaled, overlay_mode)

        result.append((max(0.0, min(1.0, br)), max(0.0, min(1.0, bg)), max(0.0, min(1.0, bb))))
    return result


# ── Layered Effect Generators ────────────────────────────────────────────────

class LayeredAuroraGenerator:
    """Base Perlin gradient flow + waving green curtains + twinkling stars."""

    def __init__(self, palette_name: str = "aurora", speed: float = 1.0):
        self.palette = palette_name
        self.speed = speed
        self.noise = ValueNoise1D(seed=101)

    def render_frame(self, t: float) -> List[Tuple[int, int, int]]:
        # 1. Base Layer: Gentle undulating gradient
        base = []
        for i in range(NUM_SEGMENTS):
            norm_pos = i / (NUM_SEGMENTS - 1)
            n = self.noise.noise(norm_pos * 1.5 + t * 0.15 * self.speed, octaves=2)
            c = sample_palette(self.palette, (norm_pos * 0.6 + n * 0.4) % 1.0)
            base.append(c)

        # 2. Effect Layer: Flowing harmonic curtains
        effect = []
        for i in range(NUM_SEGMENTS):
            curtain = math.sin((i * 0.22) + t * 0.8 * self.speed) * 0.5 + 0.5
            c = sample_palette(self.palette, curtain)
            effect.append((c[0] * curtain * 0.8, c[1] * curtain * 0.8, c[2] * curtain * 0.8))

        # 3. Overlay Layer: High latitude twinkle sparkles
        overlay = []
        for i in range(NUM_SEGMENTS):
            twinkle_n = self.noise.noise(i * 12.0 + t * 2.5 * self.speed, octaves=1)
            if twinkle_n > 0.82:
                spk = (twinkle_n - 0.82) / 0.18
                overlay.append((spk, spk, spk))
            else:
                overlay.append((0.0, 0.0, 0.0))

        # Composite & convert to Tapo HSV
        blended = composite_layers(base, effect, overlay, effect_opacity=0.75, overlay_opacity=0.90, effect_mode="add", overlay_mode="screen")
        return [rgb_to_tapo_hsv(*col) for col in blended]


class LayeredFireGenerator:
    """Base thermal diffusion model + fiery ember overlay."""

    def __init__(self, palette_name: str = "fire", speed: float = 1.0):
        self.palette = palette_name
        self.speed = speed
        self.sim = HeatDiffusionSimulation(num_zones=NUM_SEGMENTS, cooling=0.06 * speed, spark_prob=0.40 * speed)

    def render_frame(self, t: float) -> List[Tuple[int, int, int]]:
        heat = self.sim.tick()
        base = []
        for i in range(NUM_SEGMENTS):
            h_val = float(heat[i])
            c = sample_palette(self.palette, h_val)
            # Modulate brightness by heat level
            base.append((c[0] * h_val, c[1] * h_val, c[2] * h_val))

        # Ember sparks overlay
        overlay = []
        for i in range(NUM_SEGMENTS):
            if random.random() < 0.05 and heat[i] > 0.35:
                overlay.append((1.0, 0.9, 0.6))
            else:
                overlay.append((0.0, 0.0, 0.0))

        blended = composite_layers(base, None, overlay, overlay_opacity=0.85, overlay_mode="screen")
        return [rgb_to_tapo_hsv(*col) for col in blended]


class LayeredLavaGenerator:
    """Base volcanic crust + rising glowing convection cells."""

    def __init__(self, palette_name: str = "sunset", speed: float = 1.0):
        self.palette = palette_name
        self.speed = speed
        self.noise = ValueNoise1D(seed=303)

    def render_frame(self, t: float) -> List[Tuple[int, int, int]]:
        base = []
        effect = []
        for i in range(NUM_SEGMENTS):
            norm_pos = i / (NUM_SEGMENTS - 1)
            # Viscous flow
            n1 = self.noise.noise(norm_pos * 2.0 - t * 0.12 * self.speed, octaves=3)
            base.append(sample_palette(self.palette, n1))

            # Convection hot spots
            n2 = self.noise.noise(norm_pos * 4.0 + t * 0.20 * self.speed, octaves=2)
            if n2 > 0.65:
                intensity = (n2 - 0.65) / 0.35
                effect.append((intensity, intensity * 0.6, 0.0))
            else:
                effect.append((0.0, 0.0, 0.0))

        blended = composite_layers(base, effect, None, effect_opacity=0.80, effect_mode="add")
        return [rgb_to_tapo_hsv(*col) for col in blended]
