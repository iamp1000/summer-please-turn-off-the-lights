"""
L930 Reworked Effects Engine — Firmware Looping + Slow Streamed Hybrid.

Architecture:
1. Classification:
   - "firmware": uploaded once, loops on L930 microcontroller with ZERO PC network traffic.
     Streaming worker is paused/idle while a firmware effect is running.
     Parameter changes (speed, brightness, palette) rebuild the effect definition at most once per 2s.
   - "streamed_slow": procedural physical models (Lava Lamp, Hearth Fire2012, Dusk)
     rendered at <= 2 updates/s with transition_ms ~= update interval.
   - "live": music and movie modes only.

2. Groups:
   - Ambient: Tide, Drift, Dusk, Breathe, Starfield, Embers, Lava Lamp, Golden Hour,
              Native Sunrise, Native Sunset, Native Flicker
   - Motion: Hearth, Comet, Cyber Chase, Vaporwave Neon, Sonar Sweep, Neon Heartbeat,
             Lantern Sweep, Aurora (firmware), Deep Ocean (firmware),
             Native Ocean, Native Raindrop, Native Lightning
   - Seasonal & Novelty (Collapsed): Police, Native Candy Cane, Native Haunted Mansion, Native Rainbow
"""
from __future__ import annotations

import asyncio
import logging
import math
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("tapo")

from plugp100.api.light_effect import LightEffect
from plugp100.api.light_effect_preset import LightEffectPreset
from src.frame_bus import FramePacket, OutputProducer
from src.pipeline import RenderPipeline
from src.firmware_effects import (
    PALETTES,
    get_palette_hsv,
    build_firmware_sequence_effect,
    build_firmware_random_effect,
    make_effect_id,
)
from src.geometry import get_l930_topology

NUM_SEGMENTS = 50

# Native firmware presets
NATIVE_PRESETS: Dict[str, LightEffectPreset] = {
    "sunrise":          LightEffectPreset.Sunrise,
    "sunset":           LightEffectPreset.Sunset,
    "flicker":          LightEffectPreset.Flicker,
    "ocean":            LightEffectPreset.Ocean,
    "raindrop":         LightEffectPreset.Raindrop,
    "lightning":        LightEffectPreset.Lightning,
    "aurora_native":    LightEffectPreset.Aurora,
    "rainbow_native":   LightEffectPreset.Rainbow,
    "candy_cane":       LightEffectPreset.CandyCane,
    "haunted_mansion":  LightEffectPreset.HauntedMansion,
}

# Effect classification registry
EFFECT_CATALOG: Dict[str, Dict[str, Any]] = {
    # ── Ambient Group ────────────────────────────────────────────────────────
    "tide": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Layered slow ocean waves with pale highlights (Pacifica-style)",
        "default_palette": "tide",
    },
    "drift": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Muted 16-color glide across the strip with 6s transition",
        "default_palette": "sunset",
    },
    "dusk": {
        "kind": "streamed_slow",
        "group": "Ambient",
        "desc": "Warm to rose to violet over many minutes (circadian-linked)",
        "default_palette": "dusk",
    },
    "breathe": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Slow 6-8s whole-strip breathing cycle for winding down",
        "default_palette": "warm_mono",
    },
    "starfield": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "50 autonomous IC agents with independent sine oscillators and prime phase offsets",
        "default_palette": "tide",
    },
    "embers": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Independent warm ember ICs with slow randomized glow and long decay",
        "default_palette": "ember",
    },
    "fireflies": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Green-gold bioluminescent points with independent rise and decay",
        "default_palette": "forest",
    },
    "prism_sparks": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "High-saturation RGB pinpoints with fast independent phosphor fades",
        "default_palette": "dusk",
    },
    "lava_lamp": {
        "kind": "streamed_slow",
        "group": "Ambient",
        "desc": "Viscous molten metaballs drifting with long transitions (1-2 updates/s)",
        "default_palette": "sunset",
    },
    "golden_hour": {
        "kind": "streamed_slow",
        "group": "Ambient",
        "desc": "Standing wave twilight horizon and radiating golden dust",
        "default_palette": "sunset",
    },
    "sunrise": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Native progressive dawn awakening sequence",
    },
    "sunset": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Native twilight twilight fade sequence",
    },
    "flicker": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Native candlelight micro-fluctuation",
    },

    # ── Motion Group ─────────────────────────────────────────────────────────
    "hearth": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Non-linear multi-bed hearth with 3 anchor beds and independent per-IC flicker",
        "default_palette": "fire",
    },
    "comet": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Multi-pod bouncing comets with cooling chromatic tails",
        "default_palette": "sunset",
    },
    "meteor_shower": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Three narrow meteor heads with cool-white cores and blue fading tails",
        "default_palette": "tide",
    },
    "cyber_chase": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "True bi-directional colliders with additive OKLab/RGB mixing",
        "default_palette": "dusk",
    },
    "juggle": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "FastLED classic: 8 colored orbs weaving harmonically across the 50 zones with Gaussian glow",
        "default_palette": "sunset",
    },
    "sinelon": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "FastLED classic: Sweeping beacon with harmonic motion and phosphorescent decay trail",
        "default_palette": "dusk",
    },
    "confetti": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "FastLED classic: Multi-colored shimmering speckles popping and fading smoothly",
        "default_palette": "sunset",
    },
    "radial_ripple": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "2D geometric radial ripple radiating symmetrically from headboard arch center",
        "default_palette": "tide",
    },
    "spiral_vortex": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "2D polar angle vortex spinning smoothly around the room/bed center",
        "default_palette": "sunset",
    },
    "vaporwave_neon": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Slow aesthetic gradient drift in magenta, cyan, and violet",
        "default_palette": "dusk",
    },
    "sonar_sweep": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Multi-pod acoustic radar sweep with soft exponential fading tail",
        "default_palette": "forest",
    },
    "neon_heartbeat": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Anatomical heartbeat wave with center lub pulse and secondary dub blooms",
        "default_palette": "sunset",
    },
    "lantern_sweep": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Slow Cylon-style light that glides back and forth with glowing tail",
        "default_palette": "warm_mono",
    },
    "aurora": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Polar light ribbon sequence with wide spread and long transition",
        "default_palette": "forest",
    },
    "deep_ocean": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Layered blue-green oceanic wave sequence",
        "default_palette": "tide",
    },
    "ocean": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Native aqua and deep ocean swells",
    },
    "raindrop": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Native soft droplets falling along strip",
    },
    "lightning": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Native electric storm flashes",
    },

    # ── Seasonal & Novelty (Collapsed) ───────────────────────────────────────
    "police": {
        "kind": "firmware",
        "group": "Seasonal & Novelty",
        "desc": "Split-strip alternating emergency flasher sequence",
        "default_palette": "sunset",
    },
    "candy_cane": {
        "kind": "firmware",
        "group": "Seasonal & Novelty",
        "desc": "Native peppermint red and crisp white bands",
    },
    "haunted_mansion": {
        "kind": "firmware",
        "group": "Seasonal & Novelty",
        "desc": "Native spooky emerald green and eerie purple lightning flashes",
    },
    "rainbow": {
        "kind": "firmware",
        "group": "Seasonal & Novelty",
        "desc": "Native classic rainbow gradient sequence",
    },
}

CUSTOM_EFFECTS = list(EFFECT_CATALOG.keys())


class L930EffectsEngine:
    """
    Reworked L930 Effects Engine.
    Executes repeating animations as autonomous firmware loops (zero network traffic).
    Streams procedural models at <= 2 updates/s with matched transition times.
    """

    def __init__(self, controller, loop_runner, app_state, frame_bus: Any = None, dev_id: str = "strip2"):
        self._ctrl = controller
        self._loop_runner = loop_runner
        self._app_state = app_state
        self._frame_bus = frame_bus
        self._dev_id = dev_id

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._effect_generation: int = 0
        self._last_error: Optional[str] = None
        self._last_successful_frame: float = 0.0

        self._active_effect_name: Optional[str] = None
        self._active_kind: Optional[str] = None
        self._start_time: float = 0.0

        # Current user parameters
        self._speed: float = 1.0         # 0.2x to 3.0x
        self._brightness: int = 50       # 1 to 100, synced with device context
        self._palette_name: str = "sunset"

        # Rate-limiting parameter updates to firmware (at most once per 2s)
        self._last_firmware_upload: float = 0.0
        self._pending_fw_upload: Optional[Tuple[int, str, LightEffect]] = None
        self._pending_fw_timer: Optional[threading.Timer] = None
        self._fw_lock = threading.Lock()

        # Dedicated pre-correction pipeline
        self._pipeline = RenderPipeline(gamma=2.2, r_calib=1.0, g_calib=0.96, b_calib=0.90)

        # Procedural simulation state for slow streamed effects
        self._heat = [0.0] * NUM_SEGMENTS
        self._metaballs = [
            {"pos": 10.0, "vel": 0.4, "radius": 7.0},
            {"pos": 28.0, "vel": -0.3, "radius": 9.0},
            {"pos": 42.0, "vel": 0.5, "radius": 6.0},
        ]

    def is_running(self) -> bool:
        return self._running or (self._active_kind == "firmware")

    def get_catalog(self) -> Dict[str, Dict[str, Any]]:
        return EFFECT_CATALOG

    def set_parameters(
        self,
        speed: Optional[float] = None,
        brightness: Optional[int] = None,
        palette_name: Optional[str] = None,
    ):
        """Updates effect parameters. If a firmware effect is running, rebuilds and re-uploads."""
        changed = False
        if speed is not None:
            self._speed = max(0.2, min(3.0, float(speed)))
            changed = True
        if brightness is not None:
            self._brightness = max(1, min(100, int(brightness)))
            changed = True
        if palette_name and palette_name.strip().lower() in PALETTES:
            self._palette_name = palette_name.strip().lower()
            changed = True

        if changed and self._active_kind == "firmware" and self._active_effect_name:
            self._redeploy_current_firmware_effect()

    def start(self, effect_name: str, palette_name: Optional[str] = None, speed: Optional[float] = None, brightness: Optional[int] = None):
        key = effect_name.strip().lower()
        if key not in EFFECT_CATALOG:
            # Check native aliases
            if key in NATIVE_PRESETS:
                key = "rainbow" if key == "rainbow_native" else key
            else:
                return

        # Increment effect generation immediately
        self._effect_generation += 1

        # Invalidate any pending firmware timers from previous effects immediately
        with self._fw_lock:
            if self._pending_fw_timer is not None:
                try:
                    self._pending_fw_timer.cancel()
                except Exception:
                    pass
                self._pending_fw_timer = None
            self._pending_fw_upload = None

        if palette_name and palette_name.strip().lower() in PALETTES:
            self._palette_name = palette_name.strip().lower()
        elif "default_palette" in EFFECT_CATALOG[key]:
            self._palette_name = EFFECT_CATALOG[key]["default_palette"]

        if speed is not None:
            self._speed = max(0.2, min(3.0, float(speed)))
        if brightness is not None:
            self._brightness = max(1, min(100, int(brightness)))

        meta = EFFECT_CATALOG[key]
        kind = meta["kind"]
        self._active_effect_name = key
        self._active_kind = kind
        self._start_time = time.monotonic()

        if kind == "firmware":
            # Stop streaming worker cleanly
            self._stop_stream_worker()
            self._deploy_firmware_effect(key)
        elif kind == "streamed_slow":
            # Start slow streaming worker (<= 2 updates/s)
            self._start_stream_worker()

    def stop(self):
        self._effect_generation += 1
        self._stop_stream_worker()
        with self._fw_lock:
            if self._pending_fw_timer is not None:
                try:
                    self._pending_fw_timer.cancel()
                except Exception:
                    pass
                self._pending_fw_timer = None
            self._pending_fw_upload = None
        self._active_effect_name = None
        self._active_kind = None
        if hasattr(self._ctrl, "clear_frames"):
            self._ctrl.clear_frames()

    # ── Firmware Effect Deployment ────────────────────────────────────────────

    def _deploy_firmware_effect(self, name: str):
        fx = self._build_effect_payload(name)
        if fx is None:
            return

        gen = self._effect_generation
        with self._fw_lock:
            now = time.monotonic()
            # Throttle firmware uploads to at most once per 2s
            if now - self._last_firmware_upload < 2.0:
                self._pending_fw_upload = (gen, name, fx)
                # Debounce: cancel any existing pending timer before scheduling a new one
                if self._pending_fw_timer is not None:
                    try:
                        self._pending_fw_timer.cancel()
                    except Exception:
                        pass
                delay = max(0.1, 2.0 - (now - self._last_firmware_upload))
                self._pending_fw_timer = threading.Timer(delay, self._flush_pending_firmware_upload)
                self._pending_fw_timer.start()
                return

            self._last_firmware_upload = now
            self._pending_fw_upload = None
            if self._pending_fw_timer is not None:
                try:
                    self._pending_fw_timer.cancel()
                except Exception:
                    pass
                self._pending_fw_timer = None

        self._loop_runner.run(self._ctrl.set_native_effect(fx, priority=0))

    def _flush_pending_firmware_upload(self):
        with self._fw_lock:
            pending = self._pending_fw_upload
            self._pending_fw_upload = None
            self._pending_fw_timer = None
            if pending is None:
                return
            gen, name, fx = pending
            # Validate that the effect generation and active effect are still current
            if gen != self._effect_generation or self._active_kind != "firmware" or self._active_effect_name != name:
                logger.debug(f"[L930EffectsEngine] Dropping stale firmware upload for '{name}' (gen {gen} != {self._effect_generation})")
                return
            self._last_firmware_upload = time.monotonic()
        self._loop_runner.run(self._ctrl.set_native_effect(fx, priority=0))

    def _redeploy_current_firmware_effect(self):
        if self._active_effect_name and self._active_kind == "firmware":
            self._deploy_firmware_effect(self._active_effect_name)

    def _build_effect_payload(self, name: str) -> Optional[LightEffect]:
        """Constructs valid LightEffect definition for firmware execution."""
        b = self._brightness
        pal = get_palette_hsv(self._palette_name)
        sp_factor = 1.0 / max(0.2, self._speed)

        # 1. Native Presets with Full Speed, Brightness, and Palette Scaling
        if name == "flicker":
            # Native Flicker base preset (authentic candlelight / burning fireplace micro-fluctuations)
            preset_enum = NATIVE_PRESETS.get("flicker", LightEffectPreset.Flicker)
            fx = preset_enum.to_effect()
            fx.brightness = b
            fx.custom = 1

            # Scale transition_range with speed:
            # Base hardware transition_range is [375, 500] ms at 1.0x speed.
            # At 0.5x speed: sp_factor = 2.0 -> [750, 1000] ms (lazy, gentle glowing embers / cozy fireplace)
            # At 2.0x speed: sp_factor = 0.5 -> [188, 250] ms (active, crackling dancing flames)
            base_t0, base_t1 = 375, 500
            t0 = max(50, min(6000, int(round(base_t0 * sp_factor))))
            t1 = max(t0, min(6000, int(round(base_t1 * sp_factor))))
            fx.transition_range = [t0, t1]

            # Preserve the authentic warm burning firelight that the user loves
            if self._palette_name in ("sunset", "fire", "ember", "warm_mono", "auto"):
                fx.hue_range = [30, 40]
                fx.saturation_range = [90, 100]
                fx.brightness_range = [max(10, int(b * 0.45)), max(20, b)]
                fx.init_states = [[30, 85, max(20, int(b * 0.8))]]
                fx.display_colors = [[30, 85, b], [38, 95, b]]
            else:
                hues = [c[0] for c in pal]
                sats = [c[1] for c in pal]
                min_h, max_h = min(hues), max(hues)
                if min_h == max_h:
                    max_h = (min_h + 15) % 360
                fx.hue_range = [min_h, max_h]
                fx.saturation_range = [min(sats), max(sats)]
                fx.brightness_range = [max(10, int(b * 0.45)), max(20, b)]
                fx.init_states = [[pal[0][0], pal[0][1], max(20, int(b * 0.8))]]
                fx.display_colors = [[pal[0][0], pal[0][1], b], [pal[-1][0], pal[-1][1], b]]

            fx.id = make_effect_id(f"flicker_s{int(round(self._speed * 100))}_b{b}_{self._palette_name}")
            return fx

        if name in ("sunrise", "sunset", "ocean", "raindrop", "lightning", "candy_cane", "haunted_mansion"):
            preset_enum = NATIVE_PRESETS.get(name)
            if preset_enum:
                fx = preset_enum.to_effect()
                fx.brightness = b
                if fx.transition_range:
                    t0 = max(50, min(6000, int(round(fx.transition_range[0] * sp_factor))))
                    t1 = max(t0, min(6000, int(round(fx.transition_range[1] * sp_factor))))
                    fx.transition_range = [t0, t1]
                if fx.transition:
                    fx.transition = max(0, min(6000, int(round(fx.transition * sp_factor))))
                if fx.duration:
                    fx.duration = max(0, int(round(fx.duration * sp_factor)))
                if abs(self._speed - 1.0) > 0.02 or b != 100:
                    fx.custom = 1
                    fx.id = make_effect_id(f"{name}_s{int(round(self._speed * 100))}_b{b}")
                return fx

        if name == "rainbow":
            fx = LightEffectPreset.Rainbow.to_effect()
            fx.brightness = b
            if fx.transition:
                fx.transition = max(0, min(6000, int(round(fx.transition * sp_factor))))
            if abs(self._speed - 1.0) > 0.02 or b != 100:
                fx.custom = 1
                fx.id = make_effect_id(f"rainbow_s{int(round(self._speed * 100))}_b{b}")
            return fx

        # 2. Firmware Sequences
        if name == "tide":
            # Layered slow ocean waves with pale highlight (Pacifica)
            seq = pal[:5] if len(pal) >= 5 else pal
            trans = int(min(6000, 2000 * sp_factor))
            return build_firmware_sequence_effect(
                name="Tide", sequence=seq, spread=16, direction=3, transition=trans, brightness=b
            )

        elif name == "drift":
            # Drift is a soft per-IC field, not another whole-strip sweep like Tide.
            angles = [math.radians(c[0]) for c in pal]
            center = int(round(math.degrees(math.atan2(
                sum(math.sin(a) for a in angles), sum(math.cos(a) for a in angles)
            )) % 360))
            t0 = max(150, min(6000, int(round(900 * sp_factor))))
            t1 = max(t0, min(6000, int(round(2200 * sp_factor))))
            fx = build_firmware_random_effect(
                name="Drift", hue_range=(max(0, center - 28), min(359, center + 28)),
                saturation_range=(max(10, min(c[1] for c in pal) - 10), min(100, max(c[1] for c in pal) + 5)),
                brightness_range=(18, 72), transition_range=(t0, t1), random_seed=173,
                fadeoff=max(150, int(round(1400 * sp_factor))),
                backgrounds=[[pal[0][0], pal[0][1], 2]], brightness=b,
            )
            fx.id = make_effect_id(f"drift_{self._palette_name}_s{int(round(self._speed * 100))}_b{b}")
            return fx

        elif name == "breathe":
            # Slow 6-8s whole-strip breathing cycle
            c = pal[0] if pal else (32, 45, 90)
            seq = [
                [c[0], c[1], 15],
                [c[0], c[1], 50],
                [c[0], c[1], 100],
                [c[0], c[1], 75],
                [c[0], c[1], 25],
            ]
            trans = int(min(6000, 1500 * sp_factor))
            return build_firmware_sequence_effect(
                name="Breathe", sequence=seq, spread=50, direction=1, transition=trans, brightness=b
            )

        elif name == "lantern_sweep":
            # Slow Cylon-style light that glides back and forth with glowing tail
            c = pal[0] if pal else (32, 45, 90)
            seq = [
                [c[0], c[1], 100],
                [c[0], c[1], 60],
                [c[0], c[1], 25],
                [c[0], c[1], 5],
                [c[0], c[1], 25],
                [c[0], c[1], 60],
            ]
            trans = int(min(6000, 500 * sp_factor))
            return build_firmware_sequence_effect(
                name="LanternSweep", sequence=seq, spread=5, direction=1, transition=trans, brightness=b
            )

        elif name == "comet":
            # Bright comet head with cooling tail
            c_head = [180, 20, 100]  # White-cyan hot head
            tail_colors = pal[:4] if pal else [[280, 80, 60], [240, 80, 30]]
            seq = [c_head] + [list(c) for c in tail_colors]
            trans = int(min(6000, 400 * sp_factor))
            return build_firmware_sequence_effect(
                name="Comet", sequence=seq, spread=4, direction=1, transition=trans, brightness=b
            )

        elif name == "cyber_chase":
            # Two color pulses passing through each other
            c1 = pal[0] if len(pal) > 0 else (320, 100, 100)
            c2 = pal[1] if len(pal) > 1 else (185, 100, 100)
            seq = [c1, (0, 0, 10), c2, (0, 0, 10)]
            trans = int(min(6000, 600 * sp_factor))
            return build_firmware_sequence_effect(
                name="CyberChase", sequence=seq, spread=8, direction=1, transition=trans, brightness=b
            )

        elif name == "juggle":
            # 8-color cycling sequence
            seq = [
                [0, 100, 100], [45, 100, 100], [90, 100, 100], [135, 100, 100],
                [180, 100, 100], [225, 100, 100], [270, 100, 100], [315, 100, 100],
            ]
            trans = int(min(6000, 350 * sp_factor))
            return build_firmware_sequence_effect(
                name="Juggle", sequence=seq, spread=6, direction=1, transition=trans, brightness=b
            )

        elif name == "sinelon":
            c = pal[0] if pal else (320, 100, 100)
            seq = [
                [c[0], c[1], 100],
                [c[0], c[1], 50],
                [c[0], c[1], 15],
                [c[0], c[1], 5],
            ]
            trans = int(min(6000, 400 * sp_factor))
            return build_firmware_sequence_effect(
                name="Sinelon", sequence=seq, spread=8, direction=2, transition=trans, brightness=b
            )

        elif name == "confetti":
            t0 = max(80, min(6000, int(round(300 * sp_factor))))
            t1 = max(t0, min(6000, int(round(1000 * sp_factor))))
            fx = build_firmware_random_effect(
                name="Confetti", hue_range=(0, 359), saturation_range=(70, 100),
                brightness_range=(20, 100), transition_range=(t0, t1), random_seed=77,
                fadeoff=max(120, int(round(600 * sp_factor))),
                backgrounds=[[pal[0][0], pal[0][1], 2]], brightness=b,
            )
            fx.id = make_effect_id(f"confetti_s{int(round(self._speed * 100))}_b{b}_{self._palette_name}")
            return fx

        elif name == "radial_ripple":
            seq = [
                [200, 90, 100],
                [180, 85, 80],
                [220, 80, 50],
                [240, 70, 20],
                [200, 90, 10],
            ]
            trans = int(min(6000, 450 * sp_factor))
            return build_firmware_sequence_effect(
                name="RadialRipple", sequence=seq, spread=10, direction=2, transition=trans, brightness=b
            )

        elif name == "spiral_vortex":
            seq = [
                [0, 95, 100], [60, 95, 100], [120, 95, 100],
                [180, 95, 100], [240, 95, 100], [300, 95, 100]
            ]
            trans = int(min(6000, 500 * sp_factor))
            return build_firmware_sequence_effect(
                name="SpiralVortex", sequence=seq, spread=8, direction=1, transition=trans, brightness=b
            )

        elif name == "vaporwave_neon":
            # Slow aesthetic gradient drift in magenta, cyan, and violet
            seq = [
                [315, 85, 90],
                [275, 90, 80],
                [185, 90, 95],
                [335, 80, 85],
            ]
            trans = int(min(6000, 2500 * sp_factor))
            return build_firmware_sequence_effect(
                name="VaporwaveNeon", sequence=seq, spread=10, direction=1, transition=trans, brightness=b
            )

        elif name == "sonar_sweep":
            # Smooth radar sweep with soft exponential fading tail
            c = pal[0] if pal else (125, 95, 90)
            seq = [
                [c[0], c[1], 100],
                [c[0], c[1], 65],
                [c[0], c[1], 30],
                [c[0], c[1], 8],
                [c[0], c[1], 4],
            ]
            trans = int(min(6000, 700 * sp_factor))
            return build_firmware_sequence_effect(
                name="SonarSweep", sequence=seq, spread=6, direction=1, transition=trans, brightness=b
            )

        elif name == "neon_heartbeat":
            # Soft double-pulse rhythm
            seq = [
                [350, 95, 100],
                [350, 95, 20],
                [350, 95, 75],
                [350, 95, 10],
                [350, 95, 10],
            ]
            trans = int(min(6000, 300 * sp_factor))
            return build_firmware_sequence_effect(
                name="NeonHeartbeat", sequence=seq, spread=12, direction=3, transition=trans, brightness=b
            )

        elif name == "hearth":
            # Merged fire effect firmware approximation
            seq = [
                [0, 100, 25],
                [12, 100, 75],
                [26, 100, 95],
                [42, 90, 100],
                [20, 100, 80],
                [5, 100, 40],
            ]
            trans = int(min(6000, 800 * sp_factor))
            return build_firmware_sequence_effect(
                name="Hearth", sequence=seq, spread=7, direction=1, transition=trans, brightness=b
            )

        elif name == "aurora":
            # Firmware Aurora sequence with long transition and broad spread
            seq = [
                [120, 100, 100],
                [240, 100, 100],
                [260, 100, 100],
                [280, 100, 100],
            ]
            trans = int(min(6000, 2000 * sp_factor))
            return build_firmware_sequence_effect(
                name="Aurora", sequence=seq, spread=7, direction=4, transition=trans, brightness=b
            )

        elif name == "deep_ocean":
            # Firmware Pacifica-style ocean waves
            seq = [
                [198, 84, 30],
                [198, 70, 45],
                [215, 80, 50],
                [180, 90, 40],
            ]
            trans = int(min(6000, 2500 * sp_factor))
            return build_firmware_sequence_effect(
                name="DeepOcean", sequence=seq, spread=14, direction=3, transition=trans, brightness=b
            )

        elif name == "police":
            # Split red / blue sequence
            seq = [
                [0, 100, 100],
                [0, 100, 10],
                [225, 100, 100],
                [225, 100, 10],
            ]
            trans = int(min(6000, 200 * sp_factor))
            return build_firmware_sequence_effect(
                name="Police", sequence=seq, spread=25, direction=1, transition=trans, brightness=b
            )

        # 3. Firmware Random Effects
        elif name == "starfield":
            # Cool star-like points, each with independent fade timing.
            t0 = max(100, min(6000, int(round(400 * sp_factor))))
            t1 = max(t0, min(6000, int(round(1500 * sp_factor))))
            fx = build_firmware_random_effect(
                name="Starfield", hue_range=(200, 230), saturation_range=(8, 42),
                brightness_range=(8, 100), transition_range=(t0, t1), random_seed=42,
                fadeoff=max(150, int(round(800 * sp_factor))),
                backgrounds=[[235, 90, 2]], brightness=b,
            )
            fx.id = make_effect_id(f"starfield_{self._palette_name}_s{int(round(self._speed * 100))}_b{b}")
            return fx

        elif name == "embers":
            t0 = max(150, min(6000, int(round(600 * sp_factor))))
            t1 = max(t0, min(6000, int(round(2000 * sp_factor))))
            fx = build_firmware_random_effect(
                name="Embers", hue_range=(8, 38), saturation_range=(82, 100),
                brightness_range=(5, 48), transition_range=(t0, t1), random_seed=100,
                fadeoff=max(250, int(round(1200 * sp_factor))),
                backgrounds=[[18, 100, 2]], brightness=b,
            )
            fx.id = make_effect_id(f"embers_s{int(round(self._speed * 100))}_b{b}_{self._palette_name}")
            return fx

        elif name == "fireflies":
            t0 = max(150, min(6000, int(round(500 * sp_factor))))
            t1 = max(t0, min(6000, int(round(1700 * sp_factor))))
            fx = build_firmware_random_effect(
                name="Fireflies", hue_range=(72, 150), saturation_range=(58, 100),
                brightness_range=(12, 92), transition_range=(t0, t1), random_seed=319,
                fadeoff=max(180, int(round(1100 * sp_factor))),
                backgrounds=[[135, 80, 2]], brightness=b,
            )
            fx.id = make_effect_id(f"fireflies_s{int(round(self._speed * 100))}_b{b}")
            return fx

        elif name == "prism_sparks":
            t0 = max(70, min(6000, int(round(120 * sp_factor))))
            t1 = max(t0, min(6000, int(round(700 * sp_factor))))
            fx = build_firmware_random_effect(
                name="PrismSparks", hue_range=(0, 359), saturation_range=(82, 100),
                brightness_range=(20, 100), transition_range=(t0, t1), random_seed=211,
                fadeoff=max(80, int(round(350 * sp_factor))),
                backgrounds=[[260, 80, 2]], brightness=b,
            )
            fx.id = make_effect_id(f"prism_sparks_s{int(round(self._speed * 100))}_b{b}")
            return fx

        return None

    def _expand_palette_to_16(self, palette: List[Tuple[int, int, int]]) -> List[List[int]]:
        """Expands discrete palette to exactly 16 smoothly interpolated color stops."""
        from src.visual_styles import sample_palette_oklab
        out = []
        for i in range(16):
            t = i / 15.0
            hsv = sample_palette_oklab(palette, t, cyclic=True)
            out.append([hsv[0], hsv[1], hsv[2]])
        return out

    # ── Slow Streamed Worker (<= 2 updates/s) ─────────────────────────────────

    def _start_stream_worker(self):
        self._stop_stream_worker()
        self._running = True
        stop_event = threading.Event()
        self._stop_event = stop_event
        gen = self._effect_generation
        self._thread = threading.Thread(
            target=self._stream_run,
            args=(stop_event, gen),
            daemon=True,
            name=f"L930Stream-{self._active_effect_name}"
        )
        self._thread.start()

    def _stop_stream_worker(self):
        self._running = False
        event = self._stop_event
        if event is not None:
            event.set()
        thread = self._thread
        if thread and thread.is_alive() and thread != threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None
        self._stop_event = None

    def _stream_run(self, stop_event: threading.Event, generation: int):
        """
        Slow streamed loop (1 to 2 updates/s).
        Transition_ms matches update interval so the device hardware does the smooth crossfading.
        """
        interval = 0.8  # ~1.25 updates per second
        trans_ms = int(interval * 1000)

        while not stop_event.is_set() and generation == self._effect_generation:
            try:
                eff = self._active_effect_name
                if not eff or self._active_kind != "streamed_slow":
                    if stop_event.wait(0.1):
                        break
                    continue

                now = time.monotonic()
                t = now - self._start_time

                if eff == "lava_lamp":
                    segs = self._render_lava_lamp(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "dusk":
                    segs = self._render_standing_wave_dusk(t)
                    interval = 2.0
                    trans_ms = 2000
                elif eff == "golden_hour":
                    segs = self._render_standing_wave_golden_hour(t)
                    interval = 0.5
                    trans_ms = 500
                elif eff in ("hearth", "hearth_streamed"):
                    segs = self._render_hearth_fire2012(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "cyber_chase":
                    segs = self._render_collider_chase(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "juggle":
                    segs = self._render_harmonic_juggle(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "sinelon":
                    segs = self._render_sinelon_sweep(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "confetti":
                    segs = self._render_confetti_burst(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "meteor_shower":
                    segs = self._render_meteor_shower(t)
                    interval = 0.28
                    trans_ms = 260
                elif eff == "radial_ripple":
                    segs = self._render_radial_ripple(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "spiral_vortex":
                    segs = self._render_spiral_vortex(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "neon_heartbeat":
                    segs = self._render_anatomical_heartbeat(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "comet":
                    segs = self._render_multi_pod_comet(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "sonar_sweep":
                    segs = self._render_multi_pod_sonar(t)
                    interval = 0.4
                    trans_ms = 400
                elif eff == "starfield":
                    segs = self._render_autonomous_starfield(t)
                    interval = 0.4
                    trans_ms = 400
                elif eff == "embers":
                    segs = self._render_autonomous_embers(t)
                    interval = 0.5
                    trans_ms = 500
                else:
                    segs = [[30, 60, 50]] * NUM_SEGMENTS

                # Master brightness and gamma correction
                b = self._brightness
                master_ceiling = b / 100.0
                corrected = self._pipeline.correct_hsv_sequence(segs, master_ceiling=master_ceiling)

                if self._frame_bus:
                    published = self._frame_bus.publish(FramePacket(
                        dev_id=self._dev_id,
                        producer=OutputProducer.EFFECT,
                        segments=corrected,
                        brightness=b,
                        transition=trans_ms,
                    ))
                    if not published:
                        # Another producer has output ownership; yield gracefully
                        if stop_event.wait(0.1):
                            break
                        continue

                if hasattr(self._ctrl, "submit_frame"):
                    self._ctrl.submit_frame({
                        "segments": corrected,
                        "brightness": b,
                        "transition": trans_ms,
                        "_pre_corrected": True,
                    })

                self._last_successful_frame = time.time()
                if stop_event.wait(interval):
                    break
            except Exception as e:
                logger.exception(f"[L930EffectsEngine] Exception in stream worker ({eff}): {e}")
                self._last_error = str(e)
                if stop_event.wait(1.0):
                    break

    # ── Procedural Streamed Models ───────────────────────────────────────────

    def _render_lava_lamp(self, t: float) -> List[List[int]]:
        """Five deforming molten metaballs with a dark background and blended blob colors."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        if not pal:
            pal = [(280, 85, 25), (345, 90, 75), (22, 95, 90), (48, 60, 100)]
        elif len(pal) == 1:
            pal = [pal[0], pal[0]]
        from src.visual_styles import sample_palette_oklab
        from src.pipeline import tapo_hsv_to_rgb, rgb_to_tapo_hsv
        sp = max(0.2, self._speed)
        cells = [
            (7.5 + 7.5*math.sin(.62*t*sp+.4) + 2*math.sin(1.17*t*sp+1.3), 5+.1*math.sin(.34*t*sp)+1.4, .08),
            (41 + 6.5*math.sin(.49*t*sp+2.1) + 2*math.cos(.91*t*sp), 6.2+1.4*math.cos(.29*t*sp+.7), .31),
            (24.5+15*math.sin(.37*t*sp+2.8), 4.4+math.sin(.57*t*sp+1.1), .53),
            (24.5+18*math.cos(.31*t*sp+4.1), 5.4+1.2*math.sin(.41*t*sp+2), .74),
            (14+6.5*math.cos(.78*t*sp+1.8), 3.8+.8*math.sin(.63*t*sp+.9), .91),
        ]
        blobs=[(max(-2,min(NUM_SEGMENTS+1,p)),max(3,r),phase) for p,r,phase in cells]
        self._metaballs=[{"pos":p,"vel":0.0,"radius":r} for p,r,_ in blobs]
        segs=[]
        for i in range(NUM_SEGMENTS):
            field=sr=sg=sb=0.0
            for j,(pos,radius,phase) in enumerate(blobs):
                dist=abs(i-pos)
                if dist>=radius: continue
                x=dist/radius; weight=(1-x*x)**2; field+=weight
                bh,bs,_=sample_palette_oklab(pal,(phase+.025*math.sin(t*.11*sp+j))%1,cyclic=False)
                cr,cg,cb=tapo_hsv_to_rgb(bh,bs,100)
                sr+=cr*weight; sg+=cg*weight; sb+=cb*weight
            if field<=1e-6:
                segs.append([pal[0][0],pal[0][1],2]); continue
            density=min(1.0,1-math.exp(-1.25*field))
            h,sat,_=rgb_to_tapo_hsv(sr/field,sg/field,sb/field)
            segs.append([int(h)%360,max(0,min(100,int(sat))),int(max(2,min(100,2+98*density**1.08)))])
        return segs

    def _render_meteor_shower(self, t: float) -> List[List[int]]:
        """Several asymmetric meteor streaks move with cool-white heads and blue tails."""
        from src.visual_styles import sample_palette_oklab
        pal=get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        sp=max(.2,self._speed)
        meteors=[((t*13*sp+3)%(NUM_SEGMENTS+16)-8,1.0,7.0),
                 ((t*9*sp+27)%(NUM_SEGMENTS+20)-10,.72,10.0),
                 ((t*16*sp+41)%(NUM_SEGMENTS+12)-6,.48,5.0)]
        segs=[]
        for i in range(NUM_SEGMENTS):
            best=trail=0.0
            for head,gain,length in meteors:
                behind=head-i
                if 0<=behind<=length:
                    glow=math.exp(-behind/max(1.2,length*.38))*gain
                    if glow>best: best,trail=glow,behind/length
                if abs(i-head)<=1.15:
                    glow=gain*(1-abs(i-head)/1.15)
                    if glow>best: best,trail=glow,0.0
            if best<=.015:
                segs.append([pal[0][0],pal[0][1],2]); continue
            h,sat,_=sample_palette_oklab(pal,min(1,.1+trail*.9),cyclic=False)
            mix=max(0,1-trail*2.8)
            segs.append([int((h*(1-mix)+195*mix)%360),int(sat*(1-mix)+22*mix),int(max(2,min(100,2+98*best)))])
        return segs

    def _render_dusk(self, t: float) -> List[List[int]]:
        """Dusk: warm to rose to violet over many minutes (one update every 5-6s)."""
        cycle_period = 300.0 / max(0.2, self._speed)  # 5 minute natural progression
        progress = (t % cycle_period) / cycle_period

        # Warm amber -> Rose magenta -> Amethyst violet
        pal = get_palette_hsv("dusk")
        from src.visual_styles import sample_palette_oklab
        c = sample_palette_oklab(pal, progress, cyclic=True)

        segs = []
        for i in range(NUM_SEGMENTS):
            zone_offset = (i / float(NUM_SEGMENTS - 1)) * 0.15
            sub_c = sample_palette_oklab(pal, (progress + zone_offset) % 1.0, cyclic=True)
            segs.append([sub_c[0], sub_c[1], sub_c[2]])
        return segs

    def _render_golden_hour(self, t: float) -> List[List[int]]:
        """Golden hour horizontal twilight drift."""
        pal = get_palette_hsv("sunset")
        from src.visual_styles import sample_palette_oklab
        segs = []
        drift = (t * 0.05 * self._speed) % 1.0
        for i in range(NUM_SEGMENTS):
            pos = (i / float(NUM_SEGMENTS - 1) + drift) % 1.0
            c = sample_palette_oklab(pal, pos, cyclic=True)
            segs.append([c[0], c[1], c[2]])
        return segs

    def _render_hearth_fire2012(self, t: float) -> List[List[int]]:
        """Fire2012 simulation with cooling and sparking parameters."""
        n = NUM_SEGMENTS
        cooling = int(55 * self._speed)
        sparking = int(120 * self._speed)

        # 1. Cool down every cell a little
        for i in range(n):
            cool = random.randint(0, ((cooling * 10) // n) + 2)
            self._heat[i] = max(0.0, self._heat[i] - cool)

        # 2. Heat from each cell drifts up and diffuses
        for k in range(n - 1, 1, -1):
            self._heat[k] = (self._heat[k - 1] + self._heat[k - 2] + self._heat[k - 2]) / 3.0

        # 3. Randomly ignite new sparks near bottom/center
        if random.randint(0, 255) < sparking:
            y = random.randint(0, 3)
            self._heat[y] = min(255.0, self._heat[y] + random.randint(160, 255))

        # Map heat to fire palette
        pal = get_palette_hsv("fire")
        from src.visual_styles import sample_palette_oklab
        segs = []
        for i in range(n):
            norm_heat = min(1.0, self._heat[i] / 240.0)
            c = sample_palette_oklab(pal, norm_heat)
            v = int(norm_heat * 100)
            segs.append([c[0], c[1], max(5, v)])
        return segs

    # ── Non-Linear Procedural Renderers (Eliminates Start-to-End Bias) ────────

    def _render_collider_chase(self, t: float) -> List[List[int]]:
        """
        Procedural Moving Light Engine: Dual-End Convergence & Divergence with Inward/Outward Collision Effects.
        Two primary light heads start at opposite edges (IC 0 and IC 49), accelerate inward,
        collide at the center with high-energy additive OKLab blending and specular impact flare,
        then bounce outward with trailing aerodynamic tails.
        """
        from src.pipeline import tapo_hsv_to_rgb, rgb_to_tapo_hsv
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "dusk")
        c1 = pal[0] if len(pal) > 0 else (185, 100, 100)
        c2 = pal[1] if len(pal) > 1 else (315, 95, 100)
        c3 = pal[2] if len(pal) > 2 else (275, 90, 80)

        c1_rgb = tapo_hsv_to_rgb(*c1)
        c2_rgb = tapo_hsv_to_rgb(*c2)
        c3_rgb = tapo_hsv_to_rgb(*c3)

        sp = max(0.2, self._speed)
        # Harmonically bounded 3.2s convergence-divergence cycle
        cycle_period = 3.2 / sp
        phase = (t % cycle_period) / cycle_period
        theta = 2.0 * math.pi * phase

        # Non-linear spring/elastic shaping: accelerates toward center, decelerates at ends
        u = 0.5 + 0.5 * math.cos(theta)
        s = u ** 0.82
        pos1 = 24.5 - 24.0 * s   # Left Head: 0.5 -> 24.5 -> 0.5
        pos2 = 24.5 + 24.0 * s   # Right Head: 48.5 -> 24.5 -> 48.5
        v_dir = -math.sin(theta)  # > 0: converging inward; < 0: diverging outward

        # Head 3: Asynchronous harmonic cross-oscillator
        pos3 = 24.5 + 16.0 * math.sin(t * 2.3 * sp + 1.2)

        # Collision impact detection (active when heads are within 3.8 ICs of center)
        dist_between = pos2 - pos1
        collision_factor = max(0.0, 1.0 - (dist_between / 3.8)) ** 2.0 if dist_between < 3.8 else 0.0

        segs = []
        for i in range(NUM_SEGMENTS):
            # Dynamic aerodynamic cometary tails
            d1 = i - pos1
            d2 = i - pos2
            d3 = abs(i - pos3)

            # Tail length stretches behind direction of travel
            tail_len = 3.8
            if v_dir >= 0.0:
                # Inward motion: tails trail toward outer edges
                sigma1 = tail_len if d1 <= 0.0 else 1.8
                sigma2 = tail_len if d2 >= 0.0 else 1.8
            else:
                # Outward motion: tails trail toward center
                sigma1 = 1.8 if d1 <= 0.0 else tail_len
                sigma2 = 1.8 if d2 >= 0.0 else tail_len

            w1 = math.exp(-0.5 * (d1 / sigma1) ** 2)
            w2 = math.exp(-0.5 * (d2 / sigma2) ** 2)
            w3 = math.exp(-0.5 * (d3 / 2.2) ** 2) * 0.45

            # Base ambient floor
            r = 0.02
            g = 0.02
            b = 0.04

            # Additive perceptual contribution from heads
            r += c1_rgb[0] * w1 + c2_rgb[0] * w2 + c3_rgb[0] * w3
            g += c1_rgb[1] * w1 + c2_rgb[1] * w2 + c3_rgb[1] * w3
            b += c1_rgb[2] * w1 + c2_rgb[2] * w2 + c3_rgb[2] * w3

            # High-energy collision flash / specular impact bloom at center
            if collision_factor > 0.0:
                center_dist = abs(i - 24.5)
                impact_bloom = collision_factor * math.exp(-0.5 * (center_dist / 2.2) ** 2)
                r += impact_bloom * 0.85
                g += impact_bloom * 0.85
                b += impact_bloom * 0.95

            # Clamp channels to [0.0, 1.0] and convert to Tapo HSV
            r_clamped = min(1.0, max(0.0, r))
            g_clamped = min(1.0, max(0.0, g))
            b_clamped = min(1.0, max(0.0, b))
            h, s, v = rgb_to_tapo_hsv(r_clamped, g_clamped, b_clamped)

            # Boost brightness at heads
            peak_w = max(w1, w2, w3, collision_factor)
            v = int(max(10, min(100, 15.0 + peak_w * 85.0)))
            segs.append([h, s, v])

        return segs

    def _render_non_linear_hearth(self, t: float) -> List[List[int]]:
        """Non-Linear Multi-Bed Hearth: 3 anchor beds at IC 0, 24.5, 49 with independent per-IC flicker."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "fire")
        segs = []
        anchors = [0.0, 24.5, 49.0]
        for i in range(NUM_SEGMENTS):
            # Distance to nearest ember bed (0 at anchor, ~12 at peak of flame)
            dist = min(abs(i - a) for a in anchors)
            norm_height = min(1.0, dist / 12.5)

            # Per-IC independent flicker using prime-number phase offsets (no linear wave)
            flicker = 0.5 + 0.5 * math.sin(t * 4.5 * self._speed + (i * 19.7))
            heat = max(0.05, (1.0 - norm_height * 0.75) * (0.65 + 0.35 * flicker))

            h, s, _ = sample_palette_oklab(pal, 1.0 - heat)
            segs.append([h, s, int(heat * 100)])
        return segs

    def _render_anatomical_heartbeat(self, t: float) -> List[List[int]]:
        """Anatomical Heartbeat Wave: Center ICs (22..27) pulse first (lub), 150ms later secondary dub blooms at 10 and 40."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        c_lub = pal[0]
        c_dub = pal[1] if len(pal) > 1 else pal[0]

        cycle_period = 1.2 / max(0.3, self._speed)
        phase = (t % cycle_period) / cycle_period

        # Lub pulse (center, phase 0.0 to 0.35)
        lub_env = math.exp(-0.5 * ((phase - 0.10) / 0.06) ** 2) if phase < 0.35 else 0.0
        # Dub pulse (secondary lateral beds at 10 and 39, phase 0.18 to 0.55)
        dub_env = math.exp(-0.5 * ((phase - 0.26) / 0.07) ** 2) if phase < 0.55 else 0.0

        segs = []
        half = 24.5
        for i in range(NUM_SEGMENTS):
            w_lub = math.exp(-0.5 * ((i - half) / 4.0) ** 2) * lub_env
            w_dub = (math.exp(-0.5 * ((i - 10.0) / 4.5) ** 2) + math.exp(-0.5 * ((i - 39.0) / 4.5) ** 2)) * dub_env

            base_b = 8
            total_b = int(max(base_b, min(100, base_b + w_lub * 85.0 + w_dub * 70.0)))
            if w_dub > w_lub:
                h, s = c_dub[0], c_dub[1]
            else:
                h, s = c_lub[0], c_lub[1]
            segs.append([h, s, total_b])
        return segs

    def _render_standing_wave_golden_hour(self, t: float) -> List[List[int]]:
        """Standing Wave Horizon: Superposition of two opposing waves so colors breathe in place without scrolling."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        segs = []
        sp = self._speed
        for i in range(NUM_SEGMENTS):
            x = i / 49.0
            wave = math.sin(x * 3.0 * math.pi - t * 0.8 * sp) + math.cos(x * 5.0 * math.pi + t * 0.55 * sp)
            norm_wave = (wave + 2.0) / 4.0
            h, s, _ = sample_palette_oklab(pal, norm_wave)
            b = int(max(30, min(100, 50 + norm_wave * 50)))
            segs.append([h, s, b])
        return segs

    def _render_standing_wave_dusk(self, t: float) -> List[List[int]]:
        """Dusk standing wave progression."""
        pal = get_palette_hsv("dusk")
        from src.visual_styles import sample_palette_oklab
        segs = []
        sp = self._speed
        cycle_period = 240.0 / max(0.2, sp)
        progress = (t % cycle_period) / cycle_period
        for i in range(NUM_SEGMENTS):
            x = i / 49.0
            standing = (math.sin(x * 2.5 * math.pi) * 0.15)
            h, s, _ = sample_palette_oklab(pal, (progress + standing) % 1.0, cyclic=True)
            segs.append([h, s, int(max(20, 75 * (1.0 - 0.2 * abs(x - 0.5))))])
        return segs

    def _render_autonomous_starfield(self, t: float) -> List[List[int]]:
        """50 Autonomous IC Agents: Independent sine oscillators and prime phase offsets for zero linear correlation."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        bg_h, bg_s = pal[0][0], pal[0][1]
        star_h, star_s = pal[1][0] if len(pal) > 1 else 200, 30
        segs = []
        sp = self._speed
        for i in range(NUM_SEGMENTS):
            osc = math.sin(t * (1.2 + (i % 7) * 0.35) * sp + i * 17.3)
            if osc > 0.80:
                twinkle = (osc - 0.80) / 0.20
                b = int(max(15, min(100, 20 + twinkle * 80)))
                segs.append([star_h, star_s, b])
            else:
                segs.append([bg_h, bg_s, 12])
        return segs

    def _render_autonomous_embers(self, t: float) -> List[List[int]]:
        """Autonomous warm glowing embers with per-IC random flicker."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "ember")
        segs = []
        sp = self._speed
        for i in range(NUM_SEGMENTS):
            flicker = math.sin(t * (1.8 + (i % 5) * 0.4) * sp + i * 23.9)
            norm = (flicker + 1.0) * 0.5
            from src.visual_styles import sample_palette_oklab
            h, s, _ = sample_palette_oklab(pal, norm * 0.4)
            b = int(max(6, min(45, 12 + norm * 30)))
            segs.append([h, s, b])
        return segs

    def _render_multi_pod_comet(self, t: float) -> List[List[int]]:
        """Multi-Pod Comets: 2 comets bouncing and crossing with exponential tails."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        sp = self._speed
        pos_a = 24.5 + 24.0 * math.sin(t * 1.6 * sp)
        pos_b = 24.5 - 24.0 * math.sin(t * 2.1 * sp)
        segs = []
        for i in range(NUM_SEGMENTS):
            dist_a = abs(i - pos_a)
            dist_b = abs(i - pos_b)
            tail_a = math.exp(-dist_a / 3.5)
            tail_b = math.exp(-dist_b / 3.5)
            total = min(1.0, tail_a + tail_b)
            h, s, _ = sample_palette_oklab(pal, total)
            b = int(max(5, min(100, total * 100)))
            segs.append([h, s, b])
        return segs

    def _render_multi_pod_sonar(self, t: float) -> List[List[int]]:
        """Sonar Sweep: Center-outward repeating sweeps with smooth exponential fading tail."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "forest")
        from src.visual_styles import sample_palette_oklab
        sp = self._speed
        radius = (t * 18.0 * sp) % 28.0
        segs = []
        half = 24.5
        for i in range(NUM_SEGMENTS):
            dist = abs(i - half)
            diff = dist - radius
            if -8.0 <= diff <= 1.0:
                glow = math.exp(-abs(diff) / 2.5)
            else:
                glow = 0.05
            h, s, _ = sample_palette_oklab(pal, glow)
            b = int(max(5, min(100, glow * 100)))
            segs.append([h, s, b])
        return segs

    def _render_harmonic_juggle(self, t: float) -> List[List[int]]:
        """
        FastLED Juggle (adapted for L930 50 ICs):
        8 colored orbs weaving in and out of sync with prime harmonic frequencies.
        Additive Gaussian intensity and chromatic blending.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        sp = self._speed
        segs: List[List[int]] = []

        orb_positions = []
        orb_colors = []
        for k in range(8):
            freq = 0.35 * (k + 7) / 10.0 * sp
            phase = k * (math.pi / 4.0)
            pos = 24.5 + 23.5 * math.sin(t * freq + phase)
            orb_positions.append(pos)
            norm_k = (k / 8.0 + t * 0.05 * sp) % 1.0
            h, s, _ = sample_palette_oklab(pal, norm_k, cyclic=True)
            orb_colors.append((h, s))

        for i in range(NUM_SEGMENTS):
            total_weight = 0.0
            max_weight = 0.0
            dominant_h, dominant_s = orb_colors[0]

            for k in range(8):
                dist = abs(i - orb_positions[k])
                weight = math.exp(-0.5 * (dist / 1.8) ** 2)
                if weight > 0.05:
                    total_weight += weight
                    if weight > max_weight:
                        max_weight = weight
                        dominant_h, dominant_s = orb_colors[k]

            v = int(max(6, min(100, (total_weight * 85.0))))
            segs.append([dominant_h, dominant_s, v])

        return segs

    def _render_sinelon_sweep(self, t: float) -> List[List[int]]:
        """
        FastLED Sinelon (adapted for L930 50 ICs):
        A sweeping beacon gliding harmonically back and forth, leaving an exponential
        phosphorescent decay trail.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "dusk")
        from src.visual_styles import sample_palette_oklab
        sp = self._speed
        pos = 24.5 + 24.0 * math.sin(t * 2.2 * sp)
        vel = math.cos(t * 2.2 * sp)

        norm_t = (t * 0.12 * sp) % 1.0
        beacon_h, beacon_s, _ = sample_palette_oklab(pal, norm_t, cyclic=True)

        segs = []
        for i in range(NUM_SEGMENTS):
            dist = abs(i - pos)
            head_glow = math.exp(-0.5 * (dist / 1.5) ** 2)
            trailing_offset = (pos - i) if vel > 0 else (i - pos)
            if trailing_offset > 0:
                trail_glow = math.exp(-trailing_offset / 5.5) * 0.65
            else:
                trail_glow = 0.0

            intensity = min(1.0, head_glow + trail_glow)
            v = int(max(5, min(100, intensity * 95.0)))
            if head_glow < 0.5 and intensity > 0.1:
                tail_h, tail_s, _ = sample_palette_oklab(pal, (norm_t + 0.25) % 1.0, cyclic=True)
                segs.append([tail_h, tail_s, v])
            else:
                segs.append([beacon_h, beacon_s, v])

        return segs

    def _render_confetti_burst(self, t: float) -> List[List[int]]:
        """
        FastLED Confetti (adapted for L930 50 ICs):
        Random colored speckles that blink in and smoothly decay into an ambient floor.
        Deterministic multi-frequency cellular oscillators ensure zero random jitter.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        sp = self._speed
        segs = []

        for i in range(NUM_SEGMENTS):
            f = 1.5 + (i * 13 % 11) * 0.25 * sp
            phase = i * 29.3
            osc = math.sin(t * f + phase)

            if osc > 0.85:
                sparkle_str = (osc - 0.85) / 0.15
                norm_hue = ((i * 37 % 100) / 100.0 + t * 0.08 * sp) % 1.0
                h, s, _ = sample_palette_oklab(pal, norm_hue, cyclic=True)
                v = int(max(15, min(100, 25 + sparkle_str * 75)))
                segs.append([h, s, v])
            else:
                amb_pos = (i / 49.0 + t * 0.03 * sp) % 1.0
                h, s, _ = sample_palette_oklab(pal, amb_pos, cyclic=True)
                v = int(max(5, min(18, 12 + osc * 5)))
                segs.append([h, s, v])

        return segs

    def _render_radial_ripple(self, t: float) -> List[List[int]]:
        """
        2D Geometric Radial Ripple:
        Uses StripTopology radial distance projection r from top-center (0.0, 0.8)
        to expand circular waves symmetrically down both bed legs.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        from src.visual_styles import sample_palette_oklab
        sp = self._speed
        topo = get_l930_topology()
        r_dists = topo.radial_projection(center_x=0.0, center_y=0.8)

        segs = []
        phase = (t * 0.8 * sp) % 1.0
        for i in range(NUM_SEGMENTS):
            r = r_dists[i]
            # Expanding circular wave crests
            wave = math.sin((r - phase) * 4.0 * math.pi)
            norm_wave = (wave + 1.0) * 0.5
            h, s, _ = sample_palette_oklab(pal, (r + phase * 0.5) % 1.0, cyclic=True)
            v = int(max(10, min(100, (15 + norm_wave * 85))))
            segs.append([h, s, v])
        return segs

    def _render_spiral_vortex(self, t: float) -> List[List[int]]:
        """
        2D Polar Angle Vortex:
        Uses StripTopology polar angle projection phi in [0, 1] around (0.0, 0.0)
        to rotate a continuous angular pinwheel.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        sp = self._speed
        topo = get_l930_topology()
        phi_angles = topo.polar_projection(center_x=0.0, center_y=0.0)

        segs = []
        rot = (t * 0.5 * sp) % 1.0
        for i in range(NUM_SEGMENTS):
            phi = phi_angles[i]
            t_col = (phi + rot) % 1.0
            h, s, _ = sample_palette_oklab(pal, t_col, cyclic=True)
            v = int(max(20, min(100, 60 + 35 * math.sin((phi + rot * 2.0) * 2.0 * math.pi))))
            segs.append([h, s, v])
        return segs

    def _compute(self, name: str, t: float = 0.0) -> List[List[int]]:
        """Backward compatibility simulation computation for test suites."""
        eff = name.lower()
        if eff == "lava_lamp":
            return self._render_lava_lamp(t)
        elif eff == "dusk":
            return self._render_standing_wave_dusk(t)
        elif eff in ("golden_hour", "ambient_drift", "sakura", "deep_ocean", "northern_lights"):
            return self._render_standing_wave_golden_hour(t)
        elif eff in ("hearth", "fireplace", "fire_crawl"):
            return self._render_non_linear_hearth(t)
        elif eff == "cyber_chase":
            return self._render_collider_chase(t)
        elif eff == "juggle":
            return self._render_harmonic_juggle(t)
        elif eff == "sinelon":
            return self._render_sinelon_sweep(t)
        elif eff == "confetti":
            return self._render_confetti_burst(t)
        elif eff == "radial_ripple":
            return self._render_radial_ripple(t)
        elif eff == "spiral_vortex":
            return self._render_spiral_vortex(t)
        elif eff == "neon_heartbeat":
            return self._render_anatomical_heartbeat(t)
        elif eff == "comet":
            return self._render_multi_pod_comet(t)
        elif eff == "sonar_sweep":
            return self._render_multi_pod_sonar(t)
        elif eff == "meteor_shower":
            return self._render_meteor_shower(t)
        elif eff == "starfield":
            return self._render_autonomous_starfield(t)
        elif eff == "embers":
            return self._render_autonomous_embers(t)
        return [[30, 80, 60]] * NUM_SEGMENTS
