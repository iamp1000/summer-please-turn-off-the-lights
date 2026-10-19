from __future__ import annotations
import functools
import math
import random
import time
from typing import List, Tuple, Dict, Any, Optional

import numpy as np

from src.audio_dsp import MusicState, Section, SourcePreset
from src.screen_sync import ScreenData
from src.pipeline import (
    lerp_oklab,
    rgb_to_tapo_hsv,
    tapo_hsv_to_rgb,
    oklch_to_rgb,
    rgb_to_oklch,
)

NUM_SEGMENTS = 50

# Default rich musical palette if none provided
DEFAULT_PALETTE = [(215, 85, 75), (180, 90, 80), (280, 80, 70), (45, 95, 85)]


# ── Continuous OKLab Palette Interpolation ───────────────────────────────────

@functools.lru_cache(maxsize=1024)
def _cached_tapo_hsv_to_rgb(h: int, s: int, v: int) -> Tuple[float, float, float]:
    return tapo_hsv_to_rgb(h, s, v)


def sample_palette_oklab(
    palette: Optional[List[Tuple[int, int, int]]],
    t: float,
    cyclic: bool = False
) -> Tuple[int, int, int]:
    """
    Samples continuously along a discrete palette in perceptual OKLab space.
    Eliminates hard color banding and prevents muddy grey/brown midpoints.

    Args:
        palette: List of (h, s, v) color stops (Tapo HSV format: 0..360, 0..100, 0..100).
        t: Normalized position along palette (0.0 to 1.0).
        cyclic: If True, wraps continuously around (0.0 -> end -> 0.0).
    """
    pal = palette or DEFAULT_PALETTE
    n = len(pal)
    if n == 0:
        return (215, 85, 75)
    if n == 1:
        return pal[0]

    if cyclic:
        norm_t = (t % 1.0 + 1.0) % 1.0
        scaled = norm_t * n
        i0 = int(scaled) % n
        i1 = (i0 + 1) % n
        frac = scaled - math.floor(scaled)
    else:
        norm_t = max(0.0, min(1.0, float(t)))
        scaled = norm_t * (n - 1)
        i0 = int(scaled)
        i1 = min(n - 1, i0 + 1)
        frac = scaled - i0

    rgb0 = _cached_tapo_hsv_to_rgb(*pal[i0])
    rgb1 = _cached_tapo_hsv_to_rgb(*pal[i1])
    interp_rgb = lerp_oklab(rgb0, rgb1, frac)
    return rgb_to_tapo_hsv(*interp_rgb)


def blend_zones_oklab(
    frame_a: List[Tuple[int, int, int] | List[int]],
    frame_b: List[Tuple[int, int, int] | List[int]],
    blend_factor: float
) -> List[Tuple[int, int, int]]:
    """Crossfades between two full zone frames smoothly along shortest angular path with hue preservation."""
    t = max(0.0, min(1.0, blend_factor))
    if t <= 0.0:
        return [(int(x[0]), int(x[1]), int(x[2])) for x in frame_a]
    if t >= 1.0:
        return [(int(x[0]), int(x[1]), int(x[2])) for x in frame_b]

    out = []
    n = min(len(frame_a), len(frame_b))
    for i in range(n):
        ha, sa, va = frame_a[i]
        hb, sb, vb = frame_b[i]

        # If one zone is dark/off (V<=3) or desaturated (S<=5), preserve the other zone's hue so lighting up never flashes red
        if va <= 3 or sa <= 5:
            h = hb
            s = sb
        elif vb <= 3 or sb <= 5:
            h = ha
            s = sa
        else:
            diff_h = (hb - ha + 180) % 360 - 180
            h = int(round((ha + diff_h * t) % 360))
            s = int(round(sa + (sb - sa) * t))

        v = int(round(va + (vb - va) * t))
        out.append((h, s, max(0, min(100, v))))
    return out


def exp_smooth_fast(current: float, target: float, dt: float, tau: float) -> float:
    """Continuous exponential filter alpha = 1 - exp(-dt / tau), rate independent."""
    if tau <= 1e-6:
        return target
    alpha = 1.0 - math.exp(-max(0.0, dt) / tau)
    return current + alpha * (target - current)


# ── Internal Shared Events: Build Tension & Drop Bloom ──────────────────────

class BuildTensionAccent:
    """
    During Section.BUILD, narrows lit area toward centre, dims baseline slightly,
    and increases contrast. Persistent envelope lasting >2 send periods.
    """
    def __init__(self):
        self.tension_env: float = 0.0

    def render_accent(
        self,
        state: MusicState,
        dt: float,
        num_zones: int,
        frame: List[Tuple[int, int, int]]
    ) -> List[Tuple[int, int, int]]:
        is_build = (state.section == Section.BUILD)
        target_t = state.tension if is_build else 0.0
        # Envelope: attack 200ms, decay 600ms
        tau = 0.20 if target_t > self.tension_env else 0.60
        self.tension_env = exp_smooth_fast(self.tension_env, target_t, dt, tau)

        if self.tension_env < 0.04 or len(frame) <= 1:
            return frame

        half = (num_zones - 1) / 2.0
        out = []
        for i, (h, s, v) in enumerate(frame):
            dist_norm = abs(i - half) / half
            narrow_factor = max(0.15, 1.0 - dist_norm * (self.tension_env * 0.75))
            new_v = int(v * narrow_factor)
            out.append((h, s, new_v))
        return out


class DropBloomAccent:
    """
    Pure white full-strip bloom for Section.DROP only.
    Strictly qualified: requires preceding BUILD or BREAKDOWN, cooldown >= 8s.
    Envelope: attack >= 30ms, hold >= 120ms, decay >= 400ms (total > 550ms > 2 send periods).
    White flash is restricted EXCLUSIVELY to this layer.
    """
    def __init__(self):
        self.cooldown: float = 0.0
        self.stage: str = "IDLE"  # "IDLE", "ATTACK", "HOLD", "DECAY"
        self.stage_time: float = 0.0
        self.bloom_intensity: float = 0.0
        self.last_drop_time: float = -10.0

    def render_accent(
        self,
        state: MusicState,
        dt: float,
        num_zones: int,
        frame: List[Tuple[int, int, int]]
    ) -> List[Tuple[int, int, int]]:
        self.cooldown = max(0.0, self.cooldown - dt)

        # Trigger drop bloom on qualified drop
        can_trigger = (
            state.section == Section.DROP
            and state.drop_strength > 0.80
            and self.cooldown <= 0.0
            and self.stage == "IDLE"
        )
        if can_trigger:
            self.stage = "HOLD"
            self.stage_time = 0.0
            self.bloom_intensity = 1.0
            self.cooldown = 8.0

        if self.stage != "IDLE":
            self.stage_time += dt
            if self.stage == "HOLD":
                # Hold: stay at 1.0 for 140 ms
                self.bloom_intensity = 1.0
                if self.stage_time >= 0.140:
                    self.stage = "DECAY"
                    self.stage_time = 0.0
            elif self.stage == "DECAY":
                # Decay: exponential decay over 450 ms
                self.bloom_intensity = max(0.0, 1.0 - (self.stage_time / 0.450))
                if self.stage_time >= 0.450:
                    self.stage = "IDLE"
                    self.stage_time = 0.0
                    self.bloom_intensity = 0.0

        if self.bloom_intensity <= 0.01:
            return frame

        # Apply pure white flash proportional to bloom intensity
        out = []
        half = (num_zones - 1) / 2.0
        for i, (h, s, v) in enumerate(frame):
            dist = abs(i - half) / half if num_zones > 1 else 0.0
            # Full strip bloom, peak in center
            spatial = math.exp(-0.5 * (dist / 0.70) ** 2) if num_zones > 1 else 1.0
            weight = self.bloom_intensity * spatial
            new_s = max(0, int(round(s * (1.0 - weight))))  # Saturation drops to 0 (pure white)
            new_v = min(100, int(round(v + (100 - v) * weight)))
            out.append((h, new_s, new_v))
        return out


# ── Base VisualStyle Class ───────────────────────────────────────────────────

class VisualStyle:
    """
    Base visual style.
    Strictly 100% OFF (0% brightness) on silence for music styles.
    Events have persistent envelopes lasting >= 2 send periods (>400 ms).
    """
    name: str = "BaseStyle"

    def __init__(self):
        self.speed: float = 1.0        # 0.2x to 3.0x
        self.intensity: float = 1.0    # 0.2x to 2.5x
        self.palette_mode: str = "auto" # "auto", "fixed", "preset"
        self._preset_palette: Optional[List[Tuple[int, int, int]]] = None
        self.measured_latency_s: float = 0.0

    def set_params(
        self,
        speed: Optional[float] = None,
        intensity: Optional[float] = None,
        palette_mode: Optional[str] = None,
        preset_palette: Optional[List[Tuple[int, int, int]]] = None,
        measured_latency_s: Optional[float] = None,
        **kwargs: Any,
    ):
        if speed is not None:
            self.speed = max(0.2, min(3.0, float(speed)))
        if intensity is not None:
            self.intensity = max(0.2, min(2.5, float(intensity)))
        if palette_mode is not None:
            self.palette_mode = palette_mode
        if preset_palette is not None:
            self._preset_palette = preset_palette
        if measured_latency_s is not None:
            self.measured_latency_s = max(0.0, min(1.0, float(measured_latency_s)))

    def get_palette(self, state: MusicState) -> List[Tuple[int, int, int]]:
        if self.palette_mode in ("album_art", "artwork"):
            try:
                from src.artwork_sync import get_artwork_provider
                art_pal = get_artwork_provider().get_palette()
                if art_pal:
                    return art_pal
            except Exception:
                pass
        if self.palette_mode == "preset" and self._preset_palette:
            return self._preset_palette
        return state.palette or DEFAULT_PALETTE

    def is_silent_state(self, state: MusicState) -> bool:
        if state.section == Section.SILENT or state.energy <= 0.005:
            return True
        if getattr(state, "silent", False) and state.energy <= 0.010:
            return True
        return False

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        raise NotImplementedError


# ── 1. MOVIE MODE (Cinema Ambilight + Room Fill) ──────────────────────────────

class MovieStyle(VisualStyle):
    """
    Cinema Synchronization Mode:
    - L900 (behind monitor): Ambilight strip. Colour = luminance-weighted average of
      the screen content (letterbox detection on), smoothing tau 0.4-0.8 s, never below
      a configurable floor (default ~18%), small flare on low-band audio impacts.
    - L930 (behind bed backboard): Room fill. Warm base (2700K) drifting toward the
      screen's average colour with tau 3-5 s, plus a gentle left-to-right gradient from
      the screen's column colours (NOT 1:1 mapped). Audio layer: slow loudness swell
      (+-10-15%, tau ~400 ms) and a warm centre-out flare on relative low-band impacts
      (attack ~60 ms, decay ~800 ms); reduce audio layer to near zero when speech-band
      energy dominates. Silence or static screen = steady room light.
    - Never drops below configurable room floor.
    """
    name = "Movie"

    def __init__(self):
        super().__init__()
        self.room_level: float = 18.0          # Default ~18% room floor
        self.brightness_cap: float = 70.0      # Default ~70% ceiling
        self.screen_influence: float = 0.70    # 0.0 to 1.0
        self.audio_reactivity: float = 0.50    # 0.0 to 1.0

        self.screen_data: ScreenData = ScreenData()

        # L900 state: smoothed (h, s, v) and audio impact flare envelope
        self._l900_hsv: List[float] = [30.0, 45.0, 18.0]
        self._l900_flare_env: float = 0.0

        # L930 state: room fill warm base drifting toward screen, swell, flare
        self._l930_avg_hsv: List[float] = [30.0, 45.0, 18.0]
        self._l930_swell: float = 0.0
        self._l930_flare_env: float = 0.0

    def set_screen_data(self, data: ScreenData):
        self.screen_data = data

    def set_params(
        self,
        speed: Optional[float] = None,
        intensity: Optional[float] = None,
        palette_mode: Optional[str] = None,
        preset_palette: Optional[List[Tuple[int, int, int]]] = None,
        measured_latency_s: Optional[float] = None,
        room_level: Optional[float] = None,
        brightness_cap: Optional[float] = None,
        screen_influence: Optional[float] = None,
        audio_reactivity: Optional[float] = None,
        **kwargs: Any,
    ):
        super().set_params(speed, intensity, palette_mode, preset_palette, measured_latency_s)
        if room_level is not None:
            self.room_level = max(5.0, min(50.0, float(room_level)))
        if brightness_cap is not None:
            self.brightness_cap = max(30.0, min(100.0, float(brightness_cap)))
        if screen_influence is not None:
            self.screen_influence = max(0.0, min(1.0, float(screen_influence)))
        if audio_reactivity is not None:
            self.audio_reactivity = max(0.0, min(1.0, float(audio_reactivity)))

    def render(
        self,
        state: MusicState,
        dt: float,
        num_zones: int,
        screen_data: Optional[ScreenData] = None,
        **kwargs: Any
    ) -> List[Tuple[int, int, int]]:
        sd = screen_data or self.screen_data
        gh, gs, gv = sd.global_hsv
        cols = sd.column_hsvs if len(sd.column_hsvs) >= 50 else [sd.global_hsv] * 50

        # Speech dominance reduction: when dialogue dominates, reduce audio layer to near zero
        sp = getattr(state, "source_preset", None)
        is_speech = (sp == SourcePreset.MOVIE if "SourcePreset" in globals() else False) or (getattr(state, "speech_dominance", 0.0) > 0.50)
        audio_factor = 0.05 if is_speech else self.audio_reactivity

        # Low-band impact flare: warm centre-out flare on relative low-band impacts (attack ~60ms, decay ~800ms)
        is_impact = (state.kick > 0.40 or state.impact > 0.50)
        target_flare = float(max(state.kick, state.impact)) if is_impact else 0.0

        if target_flare > self._l930_flare_env:
            alpha_flare_att = 1.0 - math.exp(-dt / 0.060)
            self._l930_flare_env += alpha_flare_att * (target_flare - self._l930_flare_env)
            self._l900_flare_env += alpha_flare_att * (target_flare - self._l900_flare_env)
        else:
            alpha_flare_dec = 1.0 - math.exp(-dt / 0.800)
            self._l930_flare_env += alpha_flare_dec * (0.0 - self._l930_flare_env)
            self._l900_flare_env += alpha_flare_dec * (0.0 - self._l900_flare_env)

        # ── Single-Zone L900 Mapping (Ambilight behind monitor) ──
        if num_zones == 1:
            # Luminance-weighted screen colour with tau 0.4-0.8s (tau = 0.6s)
            alpha_900 = 1.0 - math.exp(-dt / 0.60)
            diff_h = (gh - self._l900_hsv[0] + 180) % 360 - 180
            self._l900_hsv[0] = (self._l900_hsv[0] + diff_h * alpha_900) % 360.0
            self._l900_hsv[1] += (gs - self._l900_hsv[1]) * alpha_900

            norm_v = gv / 100.0
            target_b = self.room_level + norm_v * (self.brightness_cap - self.room_level)
            self._l900_hsv[2] += (target_b - self._l900_hsv[2]) * alpha_900

            # Small flare on low-band audio impacts
            flare_b = self._l900_flare_env * 15.0 * audio_factor
            final_b = int(max(self.room_level, min(self.brightness_cap, self._l900_hsv[2] + flare_b)))
            return [(int(round(self._l900_hsv[0])), int(round(self._l900_hsv[1])), final_b)]

        # ── 50-Zone L930 Mapping (Room fill behind bed backboard) ──
        # Warm base 2700K: H=30, S=45
        warm_h, warm_s = 30.0, 45.0

        # Drift toward screen average colour with tau 3-5s (tau = 4.0s)
        alpha_drift = 1.0 - math.exp(-dt / 4.0)
        target_h = gh if self.screen_influence > 0.01 else warm_h
        target_s = min(75.0, gs * 0.70 + warm_s * 0.30)
        diff_h = (target_h - self._l930_avg_hsv[0] + 180) % 360 - 180
        self._l930_avg_hsv[0] = (self._l930_avg_hsv[0] + diff_h * alpha_drift) % 360.0
        self._l930_avg_hsv[1] += (target_s - self._l930_avg_hsv[1]) * alpha_drift

        # Slow loudness swell (+-10-15%, tau ~400ms)
        alpha_swell = 1.0 - math.exp(-dt / 0.400)
        target_swell = (state.energy - 0.50) * 20.0 * audio_factor
        self._l930_swell += alpha_swell * (target_swell - self._l930_swell)

        # Baseline room brightness: [room_level, brightness_cap]
        base_v = self.room_level + (gv / 100.0) * (self.brightness_cap - self.room_level) * self.screen_influence
        base_v = max(self.room_level, min(self.brightness_cap, base_v + self._l930_swell))

        # 5-tap spatial Gaussian kernel directly over screen column colours
        n_cols = len(cols)
        kernel = [0.061, 0.242, 0.383, 0.242, 0.061]  # Gaussian sigma ~ 1.0
        offsets = [-2, -1, 0, 1, 2]

        segs: List[Tuple[int, int, int]] = []
        half = (num_zones - 1) / 2.0
        flare_active = (self._l930_flare_env > 0.05)

        for i in range(num_zones):
            c_center = (i / float(max(1, num_zones - 1))) * float(max(1, n_cols - 1))
            c_idx = int(round(c_center))

            accum_sin = 0.0
            accum_cos = 0.0
            accum_s = 0.0
            accum_v = 0.0
            total_w = 0.0

            for w, off in zip(kernel, offsets):
                idx = max(0, min(n_cols - 1, c_idx + off))
                col_h, col_s, col_v = cols[idx]
                rad = math.radians(col_h)
                accum_sin += math.sin(rad) * w
                accum_cos += math.cos(rad) * w
                accum_s += col_s * w
                accum_v += col_v * w
                total_w += w

            conv_h = (math.degrees(math.atan2(accum_sin, accum_cos)) + 360.0) % 360.0
            conv_s = accum_s / max(1e-4, total_w)
            conv_v = accum_v / max(1e-4, total_w)

            # Spatial blend with room fill base
            diff_grad = (conv_h - self._l930_avg_hsv[0] + 180) % 360 - 180
            zone_h = (self._l930_avg_hsv[0] + diff_grad * 0.65) % 360.0
            zone_s = max(25.0, min(75.0, self._l930_avg_hsv[1] * 0.4 + conv_s * 0.6))

            # Warm centre-out audio flare
            dist_centre = abs(i - half)
            flare_b = 0.0
            if flare_active:
                flare_b = math.exp(-0.5 * (dist_centre / 6.0) ** 2) * self._l930_flare_env * 28.0 * audio_factor

            # Localized column brightness blended with room baseline
            col_brightness = self.room_level + (conv_v / 100.0) * (self.brightness_cap - self.room_level) * self.screen_influence
            zone_b = int(max(self.room_level, min(self.brightness_cap, max(base_v, col_brightness) + flare_b)))
            segs.append((int(round(zone_h)), int(round(zone_s)), zone_b))

        return segs


# ── 2. PULSE MODE (Concurrent Gaussian Ripples & Beat Swell) ─────────────────

class PulseStyle(VisualStyle):
    """
    Rhythm Mode:
    - L930: Concurrent Gaussian ripples (width 2-4 zones) spawned from centre on each kick,
            speed from bpm and intensity, trailing decay, ring colour = palette[bar index % n].
    - L900: Beat-synced swell with trailing decay.
    - Internal shared events: Build Tension & Drop Bloom.
    """
    name = "Pulse"

    def __init__(self):
        super().__init__()
        self.ripples: List[Dict[str, Any]] = []
        self._spawn_cooldown: float = 0.0
        self._prev_bar: int = -1
        self._bar_color_idx: int = 0
        self._single_b: float = 0.0
        self._single_color: Tuple[int, int, int] = (215, 85, 75)

        # Internal shared event layers
        self._tension = BuildTensionAccent()
        self._bloom = DropBloomAccent()

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self.ripples.clear()
            self._single_b = 0.0
            return [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)
        self._spawn_cooldown = max(0.0, self._spawn_cooldown - dt)

        # Stepping ring colour through palette each bar
        if state.bar_pos != self._prev_bar:
            if state.bar_pos == 0:
                self._bar_color_idx = (self._bar_color_idx + 1) % len(pal)
            self._prev_bar = state.bar_pos

        cur_color = pal[self._bar_color_idx % len(pal)]

        # Multi-Origin Beat Anchors: Inception rotates across bar positions
        BAR_ORIGINS = [24.5, 12.0, 37.0, 24.5]
        bar_idx = getattr(state, "bar_pos", 0) % 4
        origin = BAR_ORIGINS[bar_idx]

        # Spawn new ripple on kick or transient impact
        kick_hit = (state.kick > 0.12 or state.onset > 0.45 or state.impact > 0.20) and self._spawn_cooldown <= 0.0
        if kick_hit:
            self._spawn_cooldown = max(0.05, 0.08 / self.speed)
            bpm = max(60.0, min(180.0, state.bpm))
            speed_zones_per_sec = (55.0 + state.intensity * 40.0) * (bpm / 120.0) * self.speed
            init_pos = 0.0
            if getattr(self, "measured_latency_s", 0.0) > 0.0:
                init_pos = min(float((num_zones - 1) / 2.0), speed_zones_per_sec * float(self.measured_latency_s))
            self.ripples.append({
                "origin": origin,
                "pos": init_pos,
                "speed": speed_zones_per_sec,
                "sigma": 2.5 + state.intensity * 1.5,  # Width 2.5-4 zones
                "life": 1.0,
                "energy": max(0.60, state.energy * 0.5 + state.kick * 0.5),
                "color": cur_color,
            })
            if len(self.ripples) > 6:
                self.ripples.pop(0)

        # Update active ripples
        alive = []
        half = (num_zones - 1) / 2.0
        for r in self.ripples:
            r["pos"] += r["speed"] * dt
            r["life"] -= dt * (1.6 * self.speed)  # Envelope lasting > 500 ms (> 2 send periods)
            max_dist = max(r.get("origin", half), num_zones - r.get("origin", half)) + 6.0
            if r["pos"] <= max_dist and r["life"] > 0.0:
                alive.append(r)
        self.ripples = alive

        # ── Single-Zone L900 Mapping ──
        if num_zones == 1:
            if kick_hit:
                target_b = (state.energy ** 1.1) * 70.0 + state.kick * 30.0
                self._single_b = max(self._single_b, target_b * self.intensity)
                self._single_color = cur_color
            else:
                decay_tau = 0.18 / self.speed  # Persistent envelope > 2 send periods
                self._single_b *= math.exp(-dt / decay_tau)

            baseline = (state.energy * 25.0) * self.intensity
            final_b = int(max(0, min(100, self._single_b + baseline)))
            h, s, _ = self._single_color
            frame = [(h, s, final_b)]
            frame = self._tension.render_accent(state, dt, num_zones, frame)
            frame = self._bloom.render_accent(state, dt, num_zones, frame)
            return frame

        # ── 50-Zone L930 Mapping ──
        segs: List[Tuple[int, int, int]] = []
        base_h, base_s, _ = pal[0]
        if base_s <= 5:
            base_h, base_s = cur_color[0], cur_color[1]
        baseline_b = (state.energy * 25.0) * self.intensity
        kick_punch = (state.kick * 45.0) * self.intensity

        for i in range(num_zones):
            accum_b = 0.0
            chosen_h = base_h
            chosen_s = base_s
            max_r_b = 0.0

            for r in self.ripples:
                orig = r.get("origin", half)
                dist = abs(i - orig)
                diff = abs(dist - r["pos"])
                sigma = r["sigma"]
                gaussian = math.exp(-0.5 * (diff / max(0.5, sigma)) ** 2)
                r_b = gaussian * r["life"] * r["energy"] * 100.0 * self.intensity

                if r_b > max_r_b:
                    max_r_b = r_b
                    chosen_h = r["color"][0]
                    chosen_s = r["color"][1]
                accum_b += r_b

            # Center/Crown bass wash on kicks (illuminates top span 15..35)
            dist_center_norm = abs(i - half) / half
            center_accent = max(0.0, 1.0 - dist_center_norm * 1.5) * kick_punch
            if center_accent > 5.0 and max_r_b < 20.0:
                chosen_h, chosen_s = cur_color[0], cur_color[1]

            # Snare & Hi-Hat Counter-Pops (Per-IC spatial accents)
            if state.snare > 0.40:
                dist_snare = min(abs(i - 12.0), abs(i - 24.5), abs(i - 37.0))
                if dist_snare <= 2.0:
                    snare_flash = (2.0 - dist_snare) / 2.0 * (state.snare * 45.0)
                    accum_b += snare_flash
                    chosen_s = max(10, chosen_s - int(snare_flash * 0.35))

            if state.hat > 0.35:
                if (i * 17) % 5 == 0:
                    accum_b += state.hat * 35.0

            final_b = int(max(0, min(100, accum_b + baseline_b + center_accent)))
            segs.append((chosen_h, chosen_s, final_b))

        # Apply internal shared events: build tension and drop bloom
        segs = self._tension.render_accent(state, dt, num_zones, segs)
        segs = self._bloom.render_accent(state, dt, num_zones, segs)
        return segs


# ── 3. SPECTRUM & SEGMENTED VU MODES ─────────────────────────────────────────

class SegmentedVUStyle(VisualStyle):
    """
    Segmented VU Visualizer Mode:
    - L930: Multi-Pod Bi-Directional Staccato Blocks (5 instrument pods of 10 ICs each
            expanding from pod centers with floating peak dots and dynamic breaks).
            Also supports layout="unidirectional" (0->49 progression).
    - L900: Smooth single-zone energy & frequency wash.
    - Internal shared events: Build Tension & Drop Bloom.
    """
    name = "SegmentedVU"

    def __init__(self, layout: str = "multi_pod"):
        super().__init__()
        self.layout: str = layout
        self.fill_level: float = 0.0
        self.peak_zone: float = 0.0
        self.peak_hold_timer: float = 0.0
        self.break_offset: int = 0
        self._last_impact_time: float = 0.0
        self._single_level: float = 0.0
        self._cached_pal: Optional[Tuple[Tuple[int, int, int], ...]] = None
        self._cached_gradient: List[Tuple[int, int]] = []
        self.pod_levels = [0.0] * 5
        self.pod_peaks = [0.0] * 5
        self.pod_peak_timers = [0.0] * 5

        # Internal shared event layers
        self._tension = BuildTensionAccent()
        self._bloom = DropBloomAccent()

    def set_params(self, layout: Optional[str] = None, **kwargs: Any):
        super().set_params(**kwargs)
        if layout is not None:
            self.layout = layout.strip().lower()

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self.fill_level = 0.0
            self.peak_zone = 0.0
            self.peak_hold_timer = 0.0
            self.pod_levels = [0.0] * 5
            self.pod_peaks = [0.0] * 5
            self._single_level = 0.0
            return [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)

        # ── Single-Zone L900 Mapping ──
        if num_zones == 1:
            target_b = (state.energy * 75.0 + state.kick * 25.0) * self.intensity
            tau = 0.02 if target_b > self._single_level else 0.18
            self._single_level = exp_smooth_fast(self._single_level, target_b, dt, tau)

            t_col = max(0.0, min(1.0, state.energy * 0.8 + state.kick * 0.2))
            h, s, _ = sample_palette_oklab(pal, t_col)
            b = int(max(0, min(100, self._single_level)))
            frame = [(h, s, b)]
            frame = self._tension.render_accent(state, dt, num_zones, frame)
            frame = self._bloom.render_accent(state, dt, num_zones, frame)
            return frame

        # ── 50-Zone L930 Mapping: Unidirectional Legacy Fallback ──
        if self.layout == "unidirectional":
            pal_tuple = tuple(pal)
            if pal_tuple != self._cached_pal or len(self._cached_gradient) != num_zones:
                self._cached_gradient = [
                    sample_palette_oklab(pal, i / max(1, num_zones - 1))[:2]
                    for i in range(num_zones)
                ]
                self._cached_pal = pal_tuple

            raw_target_zones = (state.energy * 0.65 + state.kick * 0.35) * num_zones * self.intensity
            raw_target_zones = max(0.0, min(float(num_zones), raw_target_zones))

            if raw_target_zones > self.fill_level:
                self.fill_level = exp_smooth_fast(self.fill_level, raw_target_zones, dt, 0.015)
            else:
                self.fill_level = exp_smooth_fast(self.fill_level, raw_target_zones, dt, 0.085 / self.speed)

            if self.fill_level >= self.peak_zone:
                self.peak_zone = self.fill_level
                self.peak_hold_timer = 0.12
            else:
                if self.peak_hold_timer > 0.0:
                    self.peak_hold_timer -= dt
                else:
                    self.peak_zone = max(0.0, self.peak_zone - dt * (28.0 * self.speed))

            now = time.time()
            if (state.hat > 0.45 or state.impact > 0.5) and (now - self._last_impact_time > 0.12):
                self.break_offset = (self.break_offset + 1) % 5
                self._last_impact_time = now

            cur_fill_int = int(math.ceil(self.fill_level))
            peak_idx = int(round(self.peak_zone))

            segs: List[Tuple[int, int, int]] = []
            for i in range(num_zones):
                h, s = self._cached_gradient[i]
                is_break = ((i + self.break_offset) % 5 == 4)
                if is_break and state.snare > 0.7 and state.hat > 0.6:
                    is_break = False

                if i < cur_fill_int:
                    if is_break:
                        b_val = 0
                    else:
                        dist_to_head = abs(i - self.fill_level)
                        b_norm = max(35, 100 - dist_to_head * 2.0)
                        b_val = int(max(0, min(100, b_norm)))
                elif i == peak_idx and peak_idx < num_zones:
                    b_val = 90
                else:
                    b_val = 0
                segs.append((h, s, b_val))

            segs = self._tension.render_accent(state, dt, num_zones, segs)
            segs = self._bloom.render_accent(state, dt, num_zones, segs)
            return segs

        # ── 50-Zone L930 Mapping: Multi-Pod Bi-Directional Staccato Mode (Default) ──
        num_pods = 5
        pod_size = num_zones // num_pods
        segs = [(0, 0, 0)] * num_zones

        if len(self.pod_levels) != num_pods:
            self.pod_levels = [0.0] * num_pods
            self.pod_peaks = [0.0] * num_pods
            self.pod_peak_timers = [0.0] * num_pods

        if len(state.bands) >= 50 and float(np.max(state.bands)) > 0.001:
            bands = state.bands
        else:
            bands = np.full(50, max(state.energy, state.kick * 0.8), dtype=np.float32)

        now = time.time()
        if (state.hat > 0.45 or state.impact > 0.5) and (now - self._last_impact_time > 0.12):
            self.break_offset = (self.break_offset + 1) % 5
            self._last_impact_time = now

        for p in range(num_pods):
            b_start = p * 10
            pod_energy = float(np.mean(bands[b_start : b_start + 10])) * self.intensity
            target_half = min(pod_size / 2.0, pod_energy * (pod_size / 2.0) * 1.5)

            if target_half > self.pod_levels[p]:
                self.pod_levels[p] = exp_smooth_fast(self.pod_levels[p], target_half, dt, 0.015)
            else:
                self.pod_levels[p] = exp_smooth_fast(self.pod_levels[p], target_half, dt, 0.085 / self.speed)

            if self.pod_levels[p] >= self.pod_peaks[p]:
                self.pod_peaks[p] = self.pod_levels[p]
                self.pod_peak_timers[p] = 0.12
            else:
                if self.pod_peak_timers[p] > 0.0:
                    self.pod_peak_timers[p] -= dt
                else:
                    self.pod_peaks[p] = max(0.0, self.pod_peaks[p] - dt * (18.0 * self.speed))

            pod_center = p * pod_size + (pod_size - 1) / 2.0
            h, s, _ = sample_palette_oklab(pal, p / float(num_pods - 1))

            cur_half = self.pod_levels[p]
            peak_dist = self.pod_peaks[p]

            for local_i in range(pod_size):
                ic = p * pod_size + local_i
                dist = abs(ic - pod_center)

                is_break = ((ic + self.break_offset) % 5 == 4)
                if is_break and state.snare > 0.7 and state.hat > 0.6:
                    is_break = False

                if is_break:
                    v = 0
                elif dist <= cur_half:
                    falloff = dist / max(0.5, pod_size / 2.0)
                    v = int(max(25, 100 * (1.0 - falloff * 0.45)))
                elif abs(dist - peak_dist) < 0.65:
                    v = 90
                else:
                    v = 0

                segs[ic] = (h, s, v)

        segs = self._tension.render_accent(state, dt, num_zones, segs)
        segs = self._bloom.render_accent(state, dt, num_zones, segs)
        return segs


class SpectrumStyle(VisualStyle):
    """
    Equalizer Mode:
    - L930: Mirrored 50-band display (bass at centre, treble at ends), peak-hold markers
            (fall time ~600 ms), colour from smooth palette gradient by frequency position.
            Supports layout="mirrored" or layout="segmented" (unidirectional VU with staccato breaks).
    - L900: Smoothed energy wash reflecting overall spectrum balance.
    - Internal shared events: Build Tension & Drop Bloom.
    """
    name = "Spectrum"

    def __init__(self, layout: str = "mirrored"):
        super().__init__()
        self.layout: str = layout
        self._segmented_delegate = SegmentedVUStyle()
        self.levels = [0.0] * NUM_SEGMENTS
        self.peaks = [0.0] * NUM_SEGMENTS
        self.peak_hold_timers = [0.0] * NUM_SEGMENTS
        self._single_level: float = 0.0
        self._cached_pal: Optional[Tuple[Tuple[int, int, int], ...]] = None
        self._cached_gradient: List[Tuple[int, int]] = []

        # Internal shared event layers
        self._tension = BuildTensionAccent()
        self._bloom = DropBloomAccent()

    def set_params(self, layout: Optional[str] = None, **kwargs: Any):
        super().set_params(**kwargs)
        if layout is not None:
            self.layout = layout.strip().lower()
        self._segmented_delegate.set_params(**kwargs)

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.layout in ("segmented", "vu", "staccato"):
            return self._segmented_delegate.render(state, dt, num_zones, **kwargs)

        if self.is_silent_state(state):
            self.levels = [0.0] * num_zones
            self.peaks = [0.0] * num_zones
            self._single_level = 0.0
            return [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)
        bands = state.bands if len(state.bands) >= 50 else np.full(50, state.energy, dtype=np.float32)

        # ── Single-Zone L900 Mapping ──
        if num_zones == 1:
            bass_bias = float(np.mean(bands[:12]))
            treble_bias = float(np.mean(bands[38:]))
            target_b = (state.energy * 75.0 + state.kick * 25.0) * self.intensity
            tau = 0.02 if target_b > self._single_level else 0.18
            self._single_level = exp_smooth_fast(self._single_level, target_b, dt, tau)

            t_col = max(0.0, min(1.0, 0.5 + (treble_bias - bass_bias) * 1.5))
            h, s, _ = sample_palette_oklab(pal, t_col)
            b = int(max(0, min(100, self._single_level)))
            frame = [(h, s, b)]
            frame = self._tension.render_accent(state, dt, num_zones, frame)
            frame = self._bloom.render_accent(state, dt, num_zones, frame)
            return frame

        # ── 50-Zone L930 Mapping ──
        if len(self.levels) != num_zones:
            self.levels = [0.0] * num_zones
            self.peaks = [0.0] * num_zones
            self.peak_hold_timers = [0.0] * num_zones

        half = (num_zones - 1) / 2.0
        pal_tuple = tuple(pal)
        if pal_tuple != self._cached_pal or len(self._cached_gradient) != num_zones:
            self._cached_gradient = [
                sample_palette_oklab(pal, abs(i - half) / half)[:2]
                for i in range(num_zones)
            ]
            self._cached_pal = pal_tuple

        segs: List[Tuple[int, int, int]] = []

        for i in range(num_zones):
            # Mirrored: Center (dist=0) -> Bass (band 0..4), Edges (dist=half) -> Treble (band 45..49)
            norm_dist = abs(i - half) / half
            band_idx = min(49, int(norm_dist * 49.0))
            # Square root contrast expansion so quiet bands pop visibly
            band_val = math.sqrt(max(0.0, float(bands[band_idx])))
            raw_target = band_val * 100.0 * self.intensity

            # Fast attack (12ms), snappy responsive decay (80ms / speed)
            if raw_target > self.levels[i]:
                self.levels[i] = exp_smooth_fast(self.levels[i], raw_target, dt, 0.012)
            else:
                self.levels[i] = exp_smooth_fast(self.levels[i], raw_target, dt, 0.080 / self.speed)

            # Peak-hold markers: hold for 120ms, fall slowly over ~600ms (>2 send periods)
            if self.levels[i] >= self.peaks[i]:
                self.peaks[i] = self.levels[i]
                self.peak_hold_timers[i] = 0.12
            else:
                if self.peak_hold_timers[i] > 0.0:
                    self.peak_hold_timers[i] -= dt
                else:
                    self.peaks[i] = max(0.0, self.peaks[i] - dt * (120.0 * self.speed))

            # Continuous OKLab palette gradient across strip
            h, s = self._cached_gradient[i]

            # Unchoked, full dynamic range with snappy peak highlights
            b_val = max(self.levels[i], self.peaks[i] * 0.95)
            final_b = int(max(0, min(100, b_val)))
            segs.append((h, s, final_b))

        # Apply internal shared events: build tension and drop bloom
        segs = self._tension.render_accent(state, dt, num_zones, segs)
        segs = self._bloom.render_accent(state, dt, num_zones, segs)
        return segs


# ── 4. FLOW MODE (Noise Curtains & Melody Pitch Glow) ─────────────────────────

class FlowStyle(VisualStyle):
    """
    Organic Flow Mode:
    - L930: 2-octave noise curtains coloured from the palette, speed and brightness scaled
            by energy and local band energy. When harmonic_ratio is high (>0.65), adds Melody
            glow (dominant pitch maps to position, sustained notes spread, ~400 ms falloff).
    - L900: Slow palette wash with organic breathing.
    - Internal shared events: Build Tension & Drop Bloom.
    """
    name = "Flow"

    def __init__(self):
        super().__init__()
        self.phase: float = 0.0
        self._single_phase: float = 0.0
        self.chroma_levels = np.zeros(12, dtype=np.float32)
        self.pitch_sustain = np.zeros(12, dtype=np.float32)

        # Internal shared event layers
        self._tension = BuildTensionAccent()
        self._bloom = DropBloomAccent()

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self.chroma_levels.fill(0.0)
            self.pitch_sustain.fill(0.0)
            return [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)
        speed_factor = (0.35 + state.energy * 0.90 + (1.0 - state.harmonic_ratio) * 0.35) * self.speed
        self.phase += speed_factor * dt

        # ── Single-Zone L900 Mapping ──
        if num_zones == 1:
            self._single_phase += speed_factor * dt * 0.5
            t_col = (math.sin(self._single_phase) * 0.5 + 0.5)
            h, s, _ = sample_palette_oklab(pal, t_col, cyclic=True)
            b = int(max(0, min(100, (40.0 + state.energy * 55.0) * self.intensity)))
            frame = [(h, s, b)]
            frame = self._tension.render_accent(state, dt, num_zones, frame)
            frame = self._bloom.render_accent(state, dt, num_zones, frame)
            return frame

        # ── 50-Zone L930 Mapping: 2-Octave Noise Curtains ──
        segs: List[Tuple[int, int, int]] = []
        bands = state.bands if len(state.bands) >= 50 else np.full(50, state.energy, dtype=np.float32)

        # 1. Update Chroma & Melody Tracking (active when harmonic_ratio is high)
        chroma = state.chroma if len(state.chroma) == 12 else np.full(12, 0.08, dtype=np.float32)
        for p in range(12):
            raw_c = chroma[p]
            if raw_c > self.chroma_levels[p]:
                self.chroma_levels[p] = exp_smooth_fast(self.chroma_levels[p], raw_c, dt, 0.04)
                self.pitch_sustain[p] = min(2.0, self.pitch_sustain[p] + dt)
            else:
                # ~400 ms falloff for melody glow
                self.chroma_levels[p] = exp_smooth_fast(self.chroma_levels[p], raw_c, dt, 0.400 / self.speed)
                self.pitch_sustain[p] = max(0.0, self.pitch_sustain[p] - dt * 2.0)

        is_melody_active = (state.harmonic_ratio > 0.65)
        # Polyphonic Pitch Constellation: top 3 active pitches mapped via Circle of Fifths
        top_pitches = []
        if is_melody_active:
            top_pitches = [p for p in np.argsort(self.chroma_levels)[-3:] if self.chroma_levels[p] > 0.12]

        for i in range(num_zones):
            x = i / float(num_zones - 1)
            effective_phase = self.phase + speed_factor * self.measured_latency_s
            # 2-octave harmonic noise simulation
            octave1 = math.sin(x * 4.0 * math.pi + effective_phase * 2.2)
            octave2 = math.sin(x * 8.0 * math.pi - effective_phase * 3.4) * 0.5
            noise_val = (octave1 + octave2 + 1.5) / 3.0  # 0.0 to 1.0

            # Scale brightness by local frequency energy with square-root lift
            band_e = math.sqrt(max(0.0, float(bands[i])))
            lift = band_e * 0.65
            # Dynamic contrast: scale from 15% floor up to 100% on high energy
            brightness = (noise_val * 0.50 + lift * 0.50) * (state.energy * 0.85 + 0.35) * 110.0 * self.intensity

            # Non-linear organic palette sampling (colors emerge from curtain folds)
            t_pal = (noise_val * 0.65 + math.sin(effective_phase * 0.25) * 0.35 + 0.5) % 1.0
            h, s, _ = sample_palette_oklab(pal, t_pal, cyclic=True)

            # 2. Polyphonic Pitch Constellation (Circle of Fifths spatial distribution)
            if top_pitches:
                for p in top_pitches:
                    pitch_center = (((p * 7) % 12) / 11.0) * (num_zones - 1)
                    sustain = self.pitch_sustain[p]
                    sigma = 2.0 + sustain * 2.2
                    diff = abs(i - pitch_center)
                    gauss = math.exp(-0.5 * (diff / max(0.5, sigma)) ** 2)
                    pitch_boost = gauss * self.chroma_levels[p] * 50.0
                    brightness = min(100.0, brightness + pitch_boost)
                    if pitch_boost > 15.0:
                        pitch_h = (p * 30.0 + 15.0) % 360.0
                        diff_h = (pitch_h - h + 180) % 360 - 180
                        h = int(round((h + diff_h * 0.50) % 360))

            final_b = int(max(0, min(100, brightness)))
            segs.append((h, s, final_b))

        # Apply internal shared events: build tension and drop bloom
        segs = self._tension.render_accent(state, dt, num_zones, segs)
        segs = self._bloom.render_accent(state, dt, num_zones, segs)
        return segs


# ── Custom Vibe & Genre Engines (Party, Chill, EDM) ──────────────────────────

class PartyStyle(VisualStyle):
    """High-energy club/party mode with chaotic multi-point bursts and rapid color shifts."""
    name = "Party"

    def __init__(self):
        super().__init__()
        self._spark_positions: List[int] = []

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self._spark_positions.clear()
            return [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)
        segs = []

        # Clear older sparks quickly for staccato feel
        self._spark_positions = [p for p in self._spark_positions if random.random() > 0.5]

        # Spawn random flashes on high onsets or hat triggers
        onset_val = getattr(state, "onset", 0.0)
        hat_val = getattr(state, "hat", 0.0)
        if onset_val > 0.65 or hat_val > 0.50:
            self._spark_positions.append(random.randint(0, max(0, num_zones - 1)))
            if len(self._spark_positions) > 8:
                self._spark_positions.pop(0)

        # Base rapid energetic wave
        t_base = time.time() * 3.5 * self.speed
        for i in range(num_zones):
            # Complex multi-frequency interference for chaotic club feel
            wave = math.sin(i * 0.35 + t_base) * math.cos(i * 0.20 - t_base * 1.5)
            norm_wave = (wave + 1.0) / 2.0

            # Palette color selection
            h, s, _ = sample_palette_oklab(pal, (norm_wave + i * 0.02) % 1.0, cyclic=True)

            # Brightness punch driven by energy & transients
            v = int((norm_wave * 0.5 + state.energy * 0.5) * 90.0 * self.intensity)

            # Add random party spark flashes
            if i in self._spark_positions:
                v = 100
                h = (h + 120) % 360  # Complementary color pop for party contrast

            segs.append((h, s, max(10, min(100, v))))

        return segs


class ChillStyle(VisualStyle):
    """Slow, relaxed lounge/lo-fi mode with velvety breathing and warm ambient shifts."""
    name = "Chill"

    def __init__(self):
        super().__init__()
        self._smooth_v: float = 30.0

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self._smooth_v = 0.0
            return [(0, 0, 0)] * num_zones

        # Force warm cozy palette if in auto mode
        pal = [(32, 85, 80), (22, 90, 85), (345, 60, 75), (45, 50, 90)] if self.palette_mode == "auto" else self.get_palette(state)

        # Organic breathing envelope with lo-fi beat pulse response
        kick_val = float(getattr(state, "kick", 0.0))
        target_v = (20.0 + state.energy * 50.0 + kick_val * 25.0) * self.intensity
        alpha = 1.0 - math.exp(-dt / 0.70) if dt > 0 else 0.0
        self._smooth_v += alpha * (target_v - self._smooth_v)

        t_drift = time.time() * 0.15 * self.speed
        segs = []
        half = (num_zones - 1) / 2.0 if num_zones > 1 else 0.5

        for i in range(num_zones):
            dist_center = abs(i - half) / max(0.5, half)
            # Soft center-out warmth gradient
            spatial_curve = 1.0 - (dist_center * 0.25)

            # Slow spatial palette drift
            t_pal = (i / float(max(1, num_zones)) * 0.5 + t_drift) % 1.0
            h, s, _ = sample_palette_oklab(pal, t_pal, cyclic=True)

            v = int(max(12, min(90, self._smooth_v * spatial_curve)))
            segs.append((h, s, v))

        return segs


class EdmModeStyle(VisualStyle):
    """High-impact EDM mode featuring bass-triggered white flashes and explosive shockwaves."""
    name = "EDM"

    def __init__(self):
        super().__init__()
        self.ripples: List[Dict[str, float]] = []
        self._flash_decay: float = 0.0

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self.ripples.clear()
            self._flash_decay = 0.0
            return [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)
        half = (num_zones - 1) / 2.0 if num_zones > 1 else 0.5

        # Trigger massive white flash & shockwave on drops / heavy kicks
        drop_val = float(getattr(state, "drop_strength", 0.0))
        kick_val = float(getattr(state, "kick", 0.0))
        impact_val = float(getattr(state, "impact", 0.0))
        is_drop_hit = (drop_val > 0.80 or kick_val > 0.45 or impact_val > 0.75)
        if is_drop_hit and self._flash_decay <= 0.0:
            self._flash_decay = 1.0  # Full white flash trigger
            self.ripples.append({
                "pos": half,
                "speed": 75.0 * self.speed,
                "radius": 1.0,
                "life": 1.0
            })

        self._flash_decay = max(0.0, self._flash_decay - dt * 2.2)  # Fast drop recovery (~450ms)

        # Update shockwaves
        alive_ripples = []
        for r in self.ripples:
            r["radius"] += r["speed"] * dt
            r["life"] -= dt * 1.5
            if r["life"] > 0.0 and r["radius"] < num_zones * 1.2:
                alive_ripples.append(r)
        self.ripples = alive_ripples

        segs = []
        t_anim = time.time() * 2.0 * self.speed

        for i in range(num_zones):
            dist_centre = abs(i - half)

            # Check if hit by any active shockwave ring
            ring_intensity = 0.0
            for r in self.ripples:
                ring_dist = abs(dist_centre - r["radius"])
                if ring_dist < 4.0:
                    ring_intensity = max(ring_intensity, (1.0 - ring_dist / 4.0) * r["life"])

            # Base reactive audio level per zone
            base_v = int((state.energy * 50.0 + kick_val * 30.0) * self.intensity)

            if self._flash_decay > 0.4 and dist_centre < 12:
                # Blinding white flash core during drop hits
                key_h = int(getattr(state, "key_hue", 0))
                h, s, v = (key_h, 0, 100)
            elif ring_intensity > 0.1:
                # Electric neon ring on shockwave boundary
                h, s = sample_palette_oklab(pal, (dist_centre / max(1.0, half) + t_anim) % 1.0)[:2]
                v = int(max(base_v, ring_intensity * 100.0))
            else:
                # Background bass pulse
                h, s = sample_palette_oklab(pal, (i / float(max(1, num_zones)) + t_anim * 0.2) % 1.0)[:2]
                v = int(max(15, base_v + int(math.sin(i * 0.5 + t_anim) * 15)))

            segs.append((h, s, max(5, min(100, v))))

        return segs


# ── LumiSync Spatial Reaction Styles ─────────────────────────────────────────

class BassBounceStyle(VisualStyle):
    """
    Symmetrical inward bass reaction (ported from LumiSync):
    - Sub-bass and kicks drive light filling symmetrically from the outer ends inward toward the center.
    - Smooth envelope response with fast attack (tau=0.06s) and musical decay (tau=0.25s).
    - Color is sampled from the active palette (or Album Art), weighted by bass energy and key.
    - Single-zone fallback (L900): Breathes dynamically with kick punch and bass-energy scale.
    """
    name = "BassBounce"

    def __init__(self):
        super().__init__()
        self._fill_level: float = 0.0

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self._fill_level = 0.0
            return [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)
        kick_val = float(getattr(state, "kick", 0.0))
        energy = float(getattr(state, "energy", 0.0))
        intensity = self.intensity

        # Bass share calculation from bands if available
        if hasattr(state, "bands") and len(state.bands) > 0:
            bass_slice = state.bands[:max(1, len(state.bands) // 8)]
            bass_energy = float(np.mean(bass_slice))
            total_energy = float(np.mean(state.bands)) + 1e-6
            bass_share = float(np.clip(bass_energy / total_energy, 0.0, 1.0))
        else:
            bass_share = float(np.clip(kick_val * 0.7 + energy * 0.3, 0.0, 1.0))

        # Target fill depth [0.0, 1.0]: level * sqrt(bass_share)
        raw_fill = (energy * 0.4 + kick_val * 0.6) * math.sqrt(max(0.1, bass_share)) * intensity
        target_fill = float(np.clip(raw_fill, 0.0, 1.0))

        # Smooth envelope: fast attack, smooth decay
        tau = 0.05 / self.speed if target_fill > self._fill_level else 0.22 / self.speed
        self._fill_level = exp_smooth_fast(self._fill_level, target_fill, dt, tau)

        # Single-zone L900 fallback
        if num_zones <= 1:
            h, s, _ = pal[0] if pal else (215, 85, 75)
            v = int(np.clip(self._fill_level * 100.0, 5, 100))
            return [(h, s, v)]

        half = (num_zones + 1) // 2
        active_from_each_end = min(half, int(math.ceil(self._fill_level * half)))

        frame: List[Tuple[int, int, int]] = []
        for i in range(num_zones):
            edge_dist = min(i, num_zones - 1 - i)
            if edge_dist < active_from_each_end:
                norm_pos = edge_dist / max(1.0, float(half))
                h, s, _ = sample_palette_oklab(pal, norm_pos, cyclic=False)
                boost = 1.0 + kick_val * 0.4
                v = int(np.clip(min(100.0, 85.0 * boost * intensity), 10, 100))
                frame.append((h, s, v))
            else:
                h, s, _ = pal[0] if pal else (215, 85, 75)
                v = int(np.clip(energy * 15.0 * intensity, 0, 25))
                frame.append((h, s, v))
        return frame


class CenterBurstStyle(VisualStyle):
    """
    Symmetrical outward ripple burst (ported from LumiSync):
    - Transients and kicks launch vivid color ripples from the center of the strip outward to both ends.
    - Shifts previous zone values outward each step, leaving an ambient floor behind.
    - Single-zone fallback (L900): High-transient explosive burst pulses.
    """
    name = "CenterBurst"

    def __init__(self):
        super().__init__()
        self._frame: List[Tuple[int, int, int]] = []
        self._single_v: float = 0.0

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self._frame = [(0, 0, 0)] * num_zones
            self._single_v = 0.0
            return [(0, 0, 0)] * num_zones

        if len(self._frame) != num_zones:
            self._frame = [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)
        kick_val = float(getattr(state, "kick", 0.0))
        onset_val = float(getattr(state, "onset", 0.0))
        energy = float(getattr(state, "energy", 0.0))
        beat_strength = float(np.clip(kick_val * 0.7 + onset_val * 0.3 + energy * 0.2, 0.0, 1.0))

        # Single-zone L900 fallback
        if num_zones <= 1:
            target_v = beat_strength * 100.0 * self.intensity
            tau = 0.04 / self.speed if target_v > self._single_v else 0.20 / self.speed
            self._single_v = exp_smooth_fast(self._single_v, target_v, dt, tau)
            h, s, _ = sample_palette_oklab(pal, (time.time() * 0.1 * self.speed) % 1.0, cyclic=True)
            return [(h, s, int(np.clip(self._single_v, 5, 100)))]

        # Symmetrical outward shockwave with continuous propagation
        left_center = (num_zones - 1) // 2
        right_center = num_zones // 2
        prev = self._frame
        new_frame: List[Tuple[int, int, int]] = list(prev)

        # Shift outward from center to outer ends proportionally to speed
        shift_step = max(1, int(round(20.0 * self.speed * dt)))
        for _ in range(min(3, shift_step)):
            temp = list(new_frame)
            for i in range(left_center):
                temp[i] = new_frame[i + 1]
            for i in range(right_center + 1, num_zones):
                temp[i] = new_frame[i - 1]
            new_frame = temp

        phase = float(getattr(state, "beat_phase", 0.0))
        h, s, _ = sample_palette_oklab(pal, phase, cyclic=True)
        center_v = int(np.clip((30.0 + 70.0 * beat_strength) * self.intensity, 15, 100))
        center_color = (h, s, center_v)

        new_frame[left_center] = center_color
        new_frame[right_center] = center_color

        decay = max(0.80, 1.0 - 0.45 * dt * self.speed)
        self._frame = [
            (c[0], c[1], int(c[2] * decay))
            for c in new_frame
        ]
        return list(self._frame)


class TwinkleStyle(VisualStyle):
    """
    Sparkle & Ambient Glow (ported from LumiSync):
    - Treble/hi-hats drive sparkle density and brightness.
    - Low/mid energy creates a velvet ambient background floor from the palette.
    - High-velocity random micro-sparkles across IC zones.
    - Single-zone fallback (L900): Soft ambient glow with treble micro-shimmers.
    """
    name = "Twinkle"

    def __init__(self):
        super().__init__()
        self._twinkles: List[Tuple[int, int, int]] = []
        self._phase: float = 0.0

    def render(self, state: MusicState, dt: float, num_zones: int, **kwargs: Any) -> List[Tuple[int, int, int]]:
        if self.is_silent_state(state):
            self._twinkles = [(0, 0, 0)] * num_zones
            return [(0, 0, 0)] * num_zones

        if len(self._twinkles) != num_zones:
            self._twinkles = [(0, 0, 0)] * num_zones

        pal = self.get_palette(state)
        hat_val = float(getattr(state, "hat", 0.0))
        energy = float(getattr(state, "energy", 0.0))
        onset_val = float(getattr(state, "onset", 0.0))

        decay_factor = max(0.50, 1.0 - 1.8 * dt * self.speed)
        self._twinkles = [
            (c[0], c[1], int(c[2] * decay_factor))
            for c in self._twinkles
        ]

        if hasattr(state, "bands") and len(state.bands) > 0:
            treble_slice = state.bands[int(len(state.bands) * 0.7):]
            treble_e = float(np.mean(treble_slice))
            total_e = float(np.mean(state.bands)) + 1e-6
            treble_share = float(np.clip(treble_e / total_e, 0.0, 1.0))
        else:
            treble_share = float(np.clip(hat_val * 0.8 + 0.2, 0.0, 1.0))

        # Single-zone L900 fallback
        if num_zones <= 1:
            h, s, _ = pal[0] if pal else (215, 85, 75)
            ambient_v = int(energy * 40.0 * self.intensity)
            shimmer_v = int(hat_val * 50.0 * self.intensity)
            return [(h, s, int(np.clip(ambient_v + shimmer_v, 5, 100)))]

        sparkle_count = max(1, int(round(
            (hat_val * 1.5 + onset_val * 0.8) * (2.0 + treble_share * max(2, num_zones // 3))
        )))

        sparkle_h = (int(getattr(state, "key_hue", 180)) + 60) % 360
        sparkle_color = (sparkle_h, max(10, int(35 * (1.0 - hat_val))), 100)

        step = int(self._phase)
        for offset in range(min(num_zones, sparkle_count)):
            idx = (step * 7 + offset * 3) % num_zones
            cur = self._twinkles[idx]
            if sparkle_color[2] > cur[2]:
                self._twinkles[idx] = sparkle_color
        self._phase = (self._phase + 1.0 + hat_val * 4.0) % 1000.0

        t_drift = time.time() * 0.12 * self.speed
        frame: List[Tuple[int, int, int]] = []
        for i in range(num_zones):
            amb_pos = (i / float(max(1, num_zones)) + t_drift) % 1.0
            h_amb, s_amb, _ = sample_palette_oklab(pal, amb_pos, cyclic=True)
            v_amb = int(np.clip((10.0 + energy * 40.0) * self.intensity, 5, 55))

            t_col = self._twinkles[i]
            if t_col[2] > v_amb:
                frame.append((t_col[0], t_col[1], t_col[2]))
            else:
                frame.append((h_amb, s_amb, v_amb))

        return frame


# ── Backward Compatibility Shims & Aliases ───────────────────────────────────

ShockwaveStyle = PulseStyle
MirrorEQStyle = SpectrumStyle
AuroraStyle = FlowStyle
CometStyle = FlowStyle
FireStyle = PulseStyle
PlasmaStyle = FlowStyle
StarfieldStyle = FlowStyle
MelodyStyle = FlowStyle
DirectorStyle = PulseStyle
HybridStyle = PulseStyle
WaveStyle = FlowStyle
CinematicStyle = MovieStyle
AmbientStyle = FlowStyle
ParticlesStyle = FlowStyle

class BeatFlashAccent:
    def __init__(self):
        self.flash_env: float = 0.0

    def render_accent(self, state, dt, num_zones, frame):
        target = float(getattr(state, "kick", 0.0))
        if target > self.flash_env:
            self.flash_env = target
        else:
            self.flash_env = max(0.0, self.flash_env - dt * 2.0)
        return frame

class HatSparkleAccent:
    def __init__(self): pass
    def render_accent(self, state, dt, num_zones, frame): return frame

class AccentCompositor:
    """Backward compatibility shim."""
    def __init__(self):
        pass
    def set_accent_enabled(self, name: str, enabled: bool):
        pass
    def composite(self, state: MusicState, dt: float, num_zones: int, base_frame: List[Tuple[int, int, int]]) -> List[Tuple[int, int, int]]:
        return base_frame


# ── Per-Device Style Factory ─────────────────────────────────────────────────

def create_style_instances() -> Dict[str, VisualStyle]:
    """
    Returns fresh, independent style instances per hardware device (L930 and L900).
    Ensures zero cross-contamination of animation buffers or mutable state.
    Exactly four core modes: Movie, Pulse, Spectrum, Flow.
    """
    party = PartyStyle()
    chill = ChillStyle()
    edm = EdmModeStyle()
    movie = MovieStyle()
    pulse = PulseStyle()
    spectrum = SpectrumStyle()
    flow = FlowStyle()
    segmented = SegmentedVUStyle()
    bass_bounce = BassBounceStyle()
    center_burst = CenterBurstStyle()
    twinkle = TwinkleStyle()

    registry: Dict[str, VisualStyle] = {
        # Custom Vibe & Genre Engines
        "party": party,
        "club": party,
        "chill": chill,
        "lofi": chill,
        "edm": edm,
        "drop": edm,
        "edm_drop": edm,

        # LumiSync Spatial Reaction Styles
        "bass_bounce": bass_bounce,
        "bounce": bass_bounce,
        "center_burst": center_burst,
        "burst": center_burst,
        "twinkle": twinkle,
        "sparkle": twinkle,

        # Core primary modes
        "movie": movie,
        "pulse": pulse,
        "spectrum": spectrum,
        "flow": flow,

        # Segmented VU Mode & Aliases
        "segmented": segmented,
        "segmented_vu": segmented,
        "staccato": segmented,

        # Migration & Backward Compatibility Aliases:
        "shockwave": pulse,
        "mirror_eq": spectrum,
        "aurora": flow,
        "auto": pulse,
        "director": pulse,
        "hybrid": pulse,
        "single_color": pulse,
        "lively": spectrum,
        "classical": spectrum,
        "upbeat": flow,
        "calm": chill,
        "comet": flow,
        "fire": pulse,
        "plasma": flow,
        "starfield": flow,
        "melody": flow,
        "cinematic": movie,
        "ambient": flow,
        "wave": flow,
        "particles": flow,
    }
    return registry


# Global fallback registry
STYLE_REGISTRY: Dict[str, VisualStyle] = create_style_instances()

def get_visual_style(name: str) -> VisualStyle:
    key = (name or "pulse").strip().lower()
    return STYLE_REGISTRY.get(key, STYLE_REGISTRY["pulse"])
