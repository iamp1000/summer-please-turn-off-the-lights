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
        "desc": "Overlapping ocean waves with different speeds and thin seafoam crests on dark teal",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "drift": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Slow hue advection traveling across strip with subtle overlapping color clouds",
        "default_palette": "dusk",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "dusk": {
        "kind": "streamed_slow",
        "group": "Ambient",
        "desc": "Slow non-repeating twilight progression: amber to dusty rose to mauve to deep violet",
        "default_palette": "dusk",
        "supported_controls": ["speed", "brightness"],
    },
    "breathe": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Deliberate inhale/exhale envelope with slow relaxing color-temperature shift",
        "default_palette": "warm_mono",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "starfield": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Near-black navy background with isolated stars brightening, holding, and fading independently",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness"],
    },
    "embers": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Near-black background with dark-red coal beds and isolated orange embers glowing at varied rates",
        "default_palette": "ember",
        "supported_controls": ["speed", "brightness", "particle_density"],
    },
    "fireflies": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Loose clusters of green-gold lights with asynchronous bloom, short peak, and long fade",
        "default_palette": "forest",
        "supported_controls": ["speed", "brightness", "particle_density"],
    },
    "prism_sparks": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Black background with sparse, high-saturation RGB sparks with varied lifetimes",
        "default_palette": "dusk",
        "supported_controls": ["speed", "brightness", "particle_density"],
    },
    "lava_lamp": {
        "kind": "streamed_slow",
        "group": "Ambient",
        "desc": "Viscous molten metaballs stretching, merging, and separating with dark gaps",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "golden_hour": {
        "kind": "streamed_slow",
        "group": "Ambient",
        "desc": "Warm amber-to-rose horizon with slow moving bands and rare golden glints",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "sunrise": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Progressive dawn: low warm glow, peach/gold, moving to soft daylight",
        "supported_controls": ["speed", "brightness"],
    },
    "sunset": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Reverse daylight progression through coral, rose, plum, and deep violet",
        "supported_controls": ["speed", "brightness"],
    },
    "flicker": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Understated candle/ember with localized warm surges and uneven flame intensity",
        "default_palette": "fire",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "bioluminescent_abyss": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Deep midnight navy field with intermittent cyan and emerald organisms glowing autonomously",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness"],
    },
    "campfire_hearth": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Multi-zone warm orange, deep crimson, and flickering gold glowing independently",
        "default_palette": "fire",
        "supported_controls": ["speed", "brightness"],
    },
    "glitter_cascade": {
        "kind": "streamed_slow",
        "group": "Ambient",
        "desc": "Slow drifting base palette overlaid with high-luminance micro-sparkles",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette", "particle_density"],
    },

    # ── Motion Group ─────────────────────────────────────────────────────────
    "hearth": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Three visibly separate fire beds with uneven flame tongues, hot tips, and dark gaps",
        "default_palette": "fire",
        "supported_controls": ["speed", "brightness"],
    },
    "comet": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "One or two decisive bright comet heads with long, cooling chromatic tails",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette", "tail_length"],
    },
    "meteor_shower": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Narrow one-way streaks with cold-white cores and long blue tails at irregular intervals",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness", "tail_length"],
    },
    "cyber_chase": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Two opposing colored pulses colliding at center with bright mixed flash and passing through",
        "default_palette": "dusk",
        "supported_controls": ["speed", "brightness", "palette", "flash_strength"],
    },
    "juggle": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "3 to 5 distinct glowing orbs with different speeds, spacing, and trajectories",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "sinelon": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Single sweeping beacon with phosphorescent decay trail",
        "default_palette": "dusk",
        "supported_controls": ["speed", "brightness", "palette", "tail_length"],
    },
    "confetti": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Short-lived saturated particles in sparse bursts with quiet dark gaps",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette", "particle_density"],
    },
    "radial_ripple": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "2D expanding concentric rings with bright crest and fading trail from headboard arch apex",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness", "palette", "wave_width"],
    },
    "spiral_vortex": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "2D polar angle vortex spinning smoothly with layered chromatic bands",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "gravity_slosh": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "2D U-tube gravity slosh falling from arch apex and rebounding at bottom corners",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness", "palette", "wave_width"],
    },
    "lissajous_orbit": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Invisible 2D Lissajous orbit with soft Euclidean proximity glow",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "planar_wind": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "45-degree planar wavefront slicing diagonally across 2D physical room space",
        "default_palette": "forest",
        "supported_controls": ["speed", "brightness", "palette", "wave_width"],
    },
    "radar_sweep": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Focused angular beam rotating around room center with exponential decay trail",
        "default_palette": "forest",
        "supported_controls": ["speed", "brightness", "palette", "tail_length"],
    },
    "bpm_resonator": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "FastLED beatsin8 multi-harmonic sine waves mixing additively in OKLab space",
        "default_palette": "dusk",
        "supported_controls": ["speed", "brightness", "palette", "wave_width"],
    },
    "dual_wipe": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Dual-head bi-directional wipe meeting at center and reversing",
        "default_palette": "dusk",
        "supported_controls": ["speed", "brightness", "palette"],
    },
    "vaporwave_neon": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Thick magenta, cyan, and violet bands with deep gaps and slow scanline",
        "default_palette": "dusk",
        "supported_controls": ["speed", "brightness"],
    },
    "sonar_sweep": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Single sweep head, exponential fading trail, and one faint acoustic echo",
        "default_palette": "forest",
        "supported_controls": ["speed", "brightness", "palette", "tail_length"],
    },
    "neon_heartbeat": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Anatomical lub-dub-pause rhythm with strong primary pulse and smaller secondary bloom",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness", "palette", "flash_strength"],
    },
    "lantern_sweep": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Warm moving core with wide golden halo and gentle lingering tail, eased at ends",
        "default_palette": "warm_mono",
        "supported_controls": ["speed", "brightness", "tail_length"],
    },
    "aurora": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Broad, slow-moving green, teal, and violet curtains with long overlapping transitions",
        "default_palette": "forest",
        "supported_controls": ["speed", "brightness", "wave_width"],
    },
    "deep_ocean": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Deep navy with subtle teal pressure waves and cyan bioluminescent highlights",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness"],
    },
    "ocean": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Native aqua and deep ocean swells running autonomously on firmware",
        "supported_controls": ["speed", "brightness"],
    },
    "raindrop": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Dark background punctuated by isolated drops that travel and fade at varied intervals",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness", "particle_density"],
    },
    "lightning": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Mostly dark with sharp white-blue flashes, irregular pauses, and uneven decays",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness", "flash_strength"],
    },
    "coordinated_lightning": {
        "kind": "streamed_slow",
        "group": "Motion",
        "desc": "Coordinated storm: sharp lightning strikes across segments with amber thunder roll",
        "default_palette": "tide",
        "supported_controls": ["speed", "brightness", "flash_strength"],
    },

    # ── Seasonal & Novelty (Collapsed) ───────────────────────────────────────
    "police": {
        "kind": "streamed_slow",
        "group": "Seasonal & Novelty",
        "desc": "Crisp red and blue alternating sections with tiny dark gaps between flashes",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness"],
    },
    "candy_cane": {
        "kind": "streamed_slow",
        "group": "Seasonal & Novelty",
        "desc": "Wide alternating red and white bands visibly moving along strip with clean edges",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness"],
    },
    "haunted_mansion": {
        "kind": "streamed_slow",
        "group": "Seasonal & Novelty",
        "desc": "Near-black base with rare emerald glows, eerie violet pools, and sudden flashes",
        "default_palette": "forest",
        "supported_controls": ["speed", "brightness"],
    },
    "rainbow": {
        "kind": "streamed_slow",
        "group": "Seasonal & Novelty",
        "desc": "Continuous seamless circulating rainbow gradient without abrupt jumps",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness"],
    },
    "infinite_prism": {
        "kind": "firmware",
        "group": "Seasonal & Novelty",
        "desc": "8-stage seamless cyclic gradient shifting across the color spectrum",
        "default_palette": "sunset",
        "supported_controls": ["speed", "brightness"],
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

        # Effect-specific tuning parameters (dynamically exposed in UI)
        self._tail_length: float = 1.0        # 0.3x to 3.0x multiplier
        self._particle_density: float = 1.0   # 0.2x to 3.0x multiplier
        self._wave_width: float = 1.0         # 0.3x to 3.0x multiplier
        self._flash_strength: float = 1.0     # 0.2x to 2.5x multiplier

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
        tail_length: Optional[float] = None,
        particle_density: Optional[float] = None,
        wave_width: Optional[float] = None,
        flash_strength: Optional[float] = None,
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
        if tail_length is not None:
            self._tail_length = max(0.2, min(3.0, float(tail_length)))
            changed = True
        if particle_density is not None:
            self._particle_density = max(0.2, min(3.0, float(particle_density)))
            changed = True
        if wave_width is not None:
            self._wave_width = max(0.2, min(3.0, float(wave_width)))
            changed = True
        if flash_strength is not None:
            self._flash_strength = max(0.2, min(3.0, float(flash_strength)))
            changed = True

        if changed and self._active_kind == "firmware" and self._active_effect_name:
            self._redeploy_current_firmware_effect()

    def start(self, effect_name: str, palette_name: Optional[str] = None, speed: Optional[float] = None, brightness: Optional[int] = None) -> bool:
        key = (effect_name or "").strip().lower()
        # Keep native UI aliases pointed at real catalog entries. The previous
        # alias path admitted "aurora_native" then indexed a nonexistent key.
        key = {"rainbow_native": "rainbow", "aurora_native": "aurora"}.get(key, key)
        if key not in EFFECT_CATALOG:
            self._last_error = f"Unknown L930 effect: {effect_name!r}"
            logger.error("[L930EffectsEngine] %s", self._last_error)
            return False

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

        # Stop the previous render worker before purging the frame queue. Without
        # this ordering its final in-flight frame can overwrite the newly selected
        # effect after the UI has already switched.
        self._stop_stream_worker()
        if hasattr(self._ctrl, "clear_frames"):
            self._ctrl.clear_frames()

        self._last_error = None
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
            # An explicit effect change should be immediate. The two-second
            # throttle remains for parameter-slider redeploys, not user selection.
            self._deploy_firmware_effect(key, force=True)
        elif kind == "streamed_slow":
            # Start slow streaming worker (<= 2 updates/s)
            self._start_stream_worker()
        else:
            self._last_error = f"Unsupported L930 effect kind {kind!r} for {key!r}"
            logger.error("[L930EffectsEngine] %s", self._last_error)
            self._active_effect_name = None
            self._active_kind = None
            return False
        return True

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

    def _deploy_firmware_effect(self, name: str, force: bool = False):
        fx = self._build_effect_payload(name)
        if fx is None:
            self._last_error = f"No firmware payload could be built for L930 effect {name!r}"
            logger.error("[L930EffectsEngine] %s", self._last_error)
            self._active_effect_name = None
            self._active_kind = None
            return

        gen = self._effect_generation
        with self._fw_lock:
            now = time.monotonic()
            # Parameter updates are throttled, but a deliberate effect selection
            # must not appear to hang behind the previous effect for two seconds.
            if not force and now - self._last_firmware_upload < 2.0:
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
            # Slow, independent per-IC fades make Drift ambient and stochastic, unlike
            # Tide's deliberate strip-wide traveling wave.
            angles = [math.radians(c[0]) for c in pal]
            hue_center = int(round(math.degrees(math.atan2(
                sum(math.sin(a) for a in angles),
                sum(math.cos(a) for a in angles),
            )) % 360))
            h0, h1 = max(0, hue_center - 26), min(359, hue_center + 26)
            t0 = max(200, min(6000, int(round(900 * sp_factor))))
            t1 = max(t0, min(6000, int(round(2400 * sp_factor))))
            fx = build_firmware_random_effect(
                name="Drift", hue_range=(h0, h1),
                saturation_range=(max(12, min(c[1] for c in pal) - 8), min(100, max(c[1] for c in pal) + 5)),
                brightness_range=(12, 68), transition_range=(t0, t1),
                random_seed=173, fadeoff=max(200, int(round(1500 * sp_factor))),
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
                name="Confetti", hue_range=(0, 359),
                saturation_range=(70, 100), brightness_range=(20, 100),
                transition_range=(t0, t1), random_seed=77,
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
            # Quiet deep-water shimmer: low values and slow independent fades,
            # intentionally different from Tide's layered traveling sequence.
            angles = [math.radians(c[0]) for c in pal]
            center = int(round(math.degrees(math.atan2(
                sum(math.sin(a) for a in angles),
                sum(math.cos(a) for a in angles),
            )) % 360))
            t0 = max(300, min(6000, int(round(1100 * sp_factor))))
            t1 = max(t0, min(6000, int(round(3000 * sp_factor))))
            fx = build_firmware_random_effect(
                name="DeepOcean", hue_range=(max(0, center - 22), min(359, center + 22)),
                saturation_range=(55, 95), brightness_range=(5, 46),
                transition_range=(t0, t1), random_seed=287,
                fadeoff=max(350, int(round(1800 * sp_factor))),
                backgrounds=[[195, 92, 3]], brightness=b,
            )
            fx.id = make_effect_id(f"deep_ocean_{self._palette_name}_s{int(round(self._speed * 100))}_b{b}")
            return fx

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
            # Sparse soft twinkles on dark navy background (WLED Fairy)
            return build_firmware_random_effect(
                name="Starfield",
                hue_range=(200, 230),
                saturation_range=(10, 40),
                brightness_range=(10, 100),
                transition_range=(400, 1500),
                random_seed=42,
                fadeoff=800,
                backgrounds=[[235, 90, 8]],
                brightness=b,
            )

        elif name == "embers":
            # Dim warm glow with slow random flicker for sleeping
            return build_firmware_random_effect(
                name="Embers",
                hue_range=(15, 35),
                saturation_range=(85, 100),
                brightness_range=(5, 45),
                transition_range=(600, 2000),
                random_seed=100,
                fadeoff=1200,
                backgrounds=[[10, 100, 15]],
                brightness=b,
            )

        elif name == "fireflies":
            # Green-gold bioluminescent points blinking independently against a dark field
            t0 = max(150, min(6000, int(round(350 * sp_factor))))
            t1 = max(t0, min(6000, int(round(950 * sp_factor))))
            return build_firmware_random_effect(
                name="Fireflies",
                hue_range=(75, 130),
                saturation_range=(75, 100),
                brightness_range=(5, 95),
                transition_range=(t0, t1),
                random_seed=333,
                fadeoff=max(200, int(round(750 * sp_factor))),
                backgrounds=[[100, 90, 2]],
                brightness=b,
            )

        elif name == "prism_sparks":
            # Saturated rainbow sparkles popping with independent IC timing
            t0 = max(100, min(6000, int(round(200 * sp_factor))))
            t1 = max(t0, min(6000, int(round(600 * sp_factor))))
            return build_firmware_random_effect(
                name="PrismSparks",
                hue_range=(0, 360),
                saturation_range=(85, 100),
                brightness_range=(10, 100),
                transition_range=(t0, t1),
                random_seed=444,
                fadeoff=max(150, int(round(450 * sp_factor))),
                backgrounds=[[0, 0, 0]],
                brightness=b,
            )

        elif name == "bioluminescent_abyss":
            t0 = max(200, min(6000, int(round(600 * sp_factor))))
            t1 = max(t0, min(6000, int(round(1800 * sp_factor))))
            return build_firmware_random_effect(
                name="BioAbyss",
                hue_range=(160, 195),
                saturation_range=(85, 100),
                brightness_range=(10, 85),
                transition_range=(t0, t1),
                random_seed=512,
                fadeoff=max(300, int(round(1200 * sp_factor))),
                backgrounds=[[230, 95, 3]],
                brightness=b,
            )

        elif name == "campfire_hearth":
            t0 = max(150, min(6000, int(round(400 * sp_factor))))
            t1 = max(t0, min(6000, int(round(1200 * sp_factor))))
            return build_firmware_random_effect(
                name="CampHearth",
                hue_range=(10, 42),
                saturation_range=(85, 100),
                brightness_range=(15, 95),
                transition_range=(t0, t1),
                random_seed=128,
                fadeoff=max(200, int(round(800 * sp_factor))),
                backgrounds=[[12, 100, 5]],
                brightness=b,
            )

        elif name == "dual_wipe":
            c1 = pal[0] if pal else (280, 85, 90)
            c2 = pal[1] if len(pal) > 1 else (180, 90, 90)
            seq = [c1, [c1[0], c1[1], 15], c2, [c2[0], c2[1], 15]]
            trans = int(min(6000, 750 * sp_factor))
            return build_firmware_sequence_effect(
                name="DualWipe", sequence=seq, spread=12, direction=3, transition=trans, brightness=b
            )

        elif name == "infinite_prism":
            seq = [
                [0, 100, 100], [45, 100, 100], [90, 100, 100], [135, 100, 100],
                [180, 100, 100], [225, 100, 100], [270, 100, 100], [315, 100, 100],
            ]
            trans = int(min(6000, 1500 * sp_factor))
            return build_firmware_sequence_effect(
                name="InfPrism", sequence=seq, spread=8, direction=1, transition=trans, brightness=b
            )

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

                # ── Ambient Group Dispatching ────────────────────────────────
                if eff == "tide":
                    segs = self._render_tide(t)
                    interval = 0.40
                    trans_ms = 400
                elif eff == "drift":
                    segs = self._render_drift(t)
                    interval = 0.45
                    trans_ms = 450
                elif eff == "dusk":
                    segs = self._render_standing_wave_dusk(t)
                    interval = 1.5
                    trans_ms = 1500
                elif eff == "breathe":
                    segs = self._render_breathe(t)
                    interval = 0.50
                    trans_ms = 500
                elif eff == "starfield":
                    segs = self._render_autonomous_starfield(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "embers":
                    segs = self._render_autonomous_embers(t)
                    interval = 0.45
                    trans_ms = 450
                elif eff == "fireflies":
                    segs = self._render_fireflies(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "lava_lamp":
                    segs = self._render_lava_lamp(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "golden_hour":
                    segs = self._render_standing_wave_golden_hour(t)
                    interval = 0.50
                    trans_ms = 500
                elif eff == "glitter_cascade":
                    segs = self._render_glitter_cascade(t)
                    interval = 0.30
                    trans_ms = 300

                # ── Motion Group Dispatching ─────────────────────────────────
                elif eff in ("hearth", "hearth_streamed"):
                    segs = self._render_hearth_fire2012(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "comet":
                    segs = self._render_multi_pod_comet(t)
                    interval = 0.32
                    trans_ms = 320
                elif eff == "meteor_shower":
                    segs = self._render_meteor_shower(t)
                    interval = 0.28
                    trans_ms = 280
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
                    interval = 0.32
                    trans_ms = 320
                elif eff == "confetti":
                    segs = self._render_confetti_burst(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "radial_ripple":
                    segs = self._render_radial_ripple(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "spiral_vortex":
                    segs = self._render_spiral_vortex(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "gravity_slosh":
                    segs = self._render_gravity_slosh(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "lissajous_orbit":
                    segs = self._render_lissajous_orbit(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "planar_wind":
                    segs = self._render_planar_wind(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "radar_sweep":
                    segs = self._render_radar_sweep(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "bpm_resonator":
                    segs = self._render_bpm_resonator(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "prism_sparks":
                    segs = self._render_prism_sparks(t)
                    interval = 0.30
                    trans_ms = 300
                elif eff == "vaporwave_neon":
                    segs = self._render_vaporwave_neon(t)
                    interval = 0.40
                    trans_ms = 400
                elif eff == "sonar_sweep":
                    segs = self._render_multi_pod_sonar(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "neon_heartbeat":
                    segs = self._render_anatomical_heartbeat(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "lantern_sweep":
                    segs = self._render_lantern_sweep(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "aurora":
                    segs = self._render_aurora(t)
                    interval = 0.50
                    trans_ms = 500
                elif eff == "deep_ocean":
                    segs = self._render_deep_ocean(t)
                    interval = 0.50
                    trans_ms = 500
                elif eff == "raindrop":
                    segs = self._render_raindrop(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "lightning":
                    segs = self._render_lightning(t)
                    interval = 0.25
                    trans_ms = 250
                elif eff == "coordinated_lightning":
                    segs = self._render_coordinated_lightning(t)
                    interval = 0.28
                    trans_ms = 280

                # ── Seasonal & Novelty Group Dispatching ─────────────────────
                elif eff == "police":
                    segs = self._render_police(t)
                    interval = 0.25
                    trans_ms = 200
                elif eff == "candy_cane":
                    segs = self._render_candy_cane(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "haunted_mansion":
                    segs = self._render_haunted_mansion(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "rainbow":
                    segs = self._render_rainbow(t)
                    interval = 0.35
                    trans_ms = 350
                elif eff == "bioluminescent_abyss":
                    # Deep navy field with intermittent cyan/emerald blooms
                    segs = []
                    for i in range(NUM_SEGMENTS):
                        flt = math.sin(t * 1.5 + i * 0.4)
                        if flt > 0.75:
                            h = 175 if (i % 2 == 0) else 190
                            v = int(20 + 70 * ((flt - 0.75) / 0.25))
                        else:
                            h, v = 230, 4
                        segs.append([h, 95, v])
                    interval = 0.35
                    trans_ms = 350
                elif eff == "campfire_hearth":
                    # Multi-zone warm orange, deep crimson, and flickering gold
                    segs = []
                    for i in range(NUM_SEGMENTS):
                        flt = math.sin(t * 3.0 + i * 0.8) + math.cos(t * 5.2 - i * 0.5)
                        norm_flt = max(0.0, min(1.0, (flt + 2.0) / 4.0))
                        h = int(12 + norm_flt * 28)
                        v = int(25 + norm_flt * 70)
                        segs.append([h, 95, v])
                    interval = 0.25
                    trans_ms = 250
                elif eff == "dual_wipe":
                    # Bi-directional dual wipe meeting in center
                    pos = (t * 25.0 * max(0.2, self._speed)) % 25.0
                    segs = []
                    pal_dw = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "dusk")
                    c1_h = pal_dw[0][0] if pal_dw else 280
                    c2_h = pal_dw[1][0] if len(pal_dw) > 1 else 180
                    for i in range(NUM_SEGMENTS):
                        if i < 25:
                            d = abs(i - pos)
                            v = int(max(10, 100 - d * 18))
                            segs.append([c1_h, 85, v])
                        else:
                            d = abs((49 - i) - pos)
                            v = int(max(10, 100 - d * 18))
                            segs.append([c2_h, 90, v])
                    interval = 0.25
                    trans_ms = 250
                elif eff == "infinite_prism":
                    # Circulating 8-step saturated rainbow prism
                    segs = []
                    sp_eff = max(0.2, self._speed)
                    for i in range(NUM_SEGMENTS):
                        h = int((i * (360.0 / 8.0) + t * 60.0 * sp_eff) % 360)
                        segs.append([h, 100, 100])
                    interval = 0.30
                    trans_ms = 300
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
        """
        Lava lamp: Fluid viscous molten metaballs drifting with smooth buoyant convection cells.
        Uses continuous harmonic trajectories and OKLab perceptual palette interpolation
        to eliminate discrete stepping and visual flickering.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        if not pal:
            pal = [(280, 85, 25), (345, 90, 75), (22, 95, 90), (48, 60, 100)]
        elif len(pal) == 1:
            pal = [pal[0], pal[0]]

        from src.visual_styles import sample_palette_oklab
        from src.pipeline import tapo_hsv_to_rgb, rgb_to_tapo_hsv

        sp = self._speed
        # 4 continuous, harmonic buoyant convection cells with non-integer phase ratios
        b1_pos = 18.0 + 12.0 * math.sin(0.30 * t * sp + 0.5) + 3.0 * math.cos(0.68 * t * sp)
        b1_rad = 7.5 + 1.2 * math.sin(0.18 * t * sp)

        b2_pos = 32.0 + 13.0 * math.cos(0.27 * t * sp + 1.2) + 2.5 * math.sin(0.57 * t * sp)
        b2_rad = 8.0 + 1.0 * math.cos(0.15 * t * sp)

        b3_pos = 24.5 + 18.0 * math.sin(0.36 * t * sp + 2.8)
        b3_rad = 5.5 + 0.8 * math.sin(0.35 * t * sp)

        b4_pos = 24.5 + 21.0 * math.cos(0.22 * t * sp + 4.1)
        b4_rad = 6.5 + 1.0 * math.sin(0.22 * t * sp)

        blobs = [
            (b1_pos, max(4.0, b1_rad)),
            (b2_pos, max(4.0, b2_rad)),
            (b3_pos, max(3.0, b3_rad)),
            (b4_pos, max(3.5, b4_rad)),
        ]

        # Keep self._metaballs updated for state inspection compatibility
        self._metaballs = [
            {"pos": b1_pos, "vel": 0.24 * sp, "radius": b1_rad},
            {"pos": b2_pos, "vel": -0.21 * sp, "radius": b2_rad},
            {"pos": b3_pos, "vel": 0.31 * sp, "radius": b3_rad},
            {"pos": b4_pos, "vel": -0.17 * sp, "radius": b4_rad},
        ]

        blob_colors = [
            sample_palette_oklab(pal, 0.15, cyclic=True),
            sample_palette_oklab(pal, 0.45, cyclic=True),
            sample_palette_oklab(pal, 0.75, cyclic=True),
            sample_palette_oklab(pal, 0.95, cyclic=True),
        ]

        # Different thermal densities make individual blobs distinct rather than
        # sharing one uniform field-to-brightness curve.
        heat_weights = [0.76, 1.0, 0.66, 0.88]
        segs = []
        for i in range(NUM_SEGMENTS):
            field = 0.0
            sum_r = sum_g = sum_b = 0.0
            for b_idx, (pos, rad) in enumerate(blobs):
                dist = abs(i - pos)
                if dist < rad:
                    r = dist / rad
                    edge = 1.0 - r * r
                    weight = edge * edge * heat_weights[b_idx % len(heat_weights)]
                    field += weight
                    bc_hsv = blob_colors[b_idx % len(blob_colors)]
                    b_rgb = tapo_hsv_to_rgb(bc_hsv[0], bc_hsv[1], 100)
                    sum_r += b_rgb[0] * weight
                    sum_g += b_rgb[1] * weight
                    sum_b += b_rgb[2] * weight

            norm_field = min(1.0, 1.0 - math.exp(-1.4 * field))
            if field > 1e-6:
                h, sat, _ = rgb_to_tapo_hsv(sum_r / field, sum_g / field, sum_b / field)
            else:
                bg_c = sample_palette_oklab(pal, 0.0, cyclic=True)
                h, sat = bg_c[0], bg_c[1]

            # Dark glass between blobs; only cores approach full brightness.
            bright = int(max(2, min(100, 2.0 + 98.0 * (norm_field ** 1.3))))
            segs.append([h, sat, bright])

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
            # Dynamic aerodynamic cometary tails scaled by tail_length
            d1 = i - pos1
            d2 = i - pos2
            d3 = abs(i - pos3)

            # Tail length stretches behind direction of travel
            tail_mult = max(0.2, getattr(self, "_tail_length", 1.0))
            tail_len = 3.8 * tail_mult
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

            # High-energy collision flash / specular impact bloom at center scaled by flash_strength
            flash_mult = max(0.2, getattr(self, "_flash_strength", 1.0))
            if collision_factor > 0.0:
                center_dist = abs(i - 24.5)
                impact_bloom = collision_factor * math.exp(-0.5 * (center_dist / 2.2) ** 2) * flash_mult
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
        tail_mult = max(0.2, getattr(self, "_tail_length", 1.0))
        decay_sigma = 3.5 * tail_mult
        pos_a = 24.5 + 24.0 * math.sin(t * 1.6 * sp)
        pos_b = 24.5 - 24.0 * math.sin(t * 2.1 * sp)
        segs = []
        for i in range(NUM_SEGMENTS):
            dist_a = abs(i - pos_a)
            dist_b = abs(i - pos_b)
            tail_a = math.exp(-dist_a / decay_sigma)
            tail_b = math.exp(-dist_b / decay_sigma)
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
        density_mult = max(0.2, getattr(self, "_particle_density", 1.0))
        # Threshold: lower threshold means higher particle density
        threshold = max(0.55, 0.95 - 0.10 * density_mult)
        segs = []

        for i in range(NUM_SEGMENTS):
            f = 1.5 + (i * 13 % 11) * 0.25 * sp
            phase = i * 29.3
            osc = math.sin(t * f + phase)

            if osc > threshold:
                sparkle_str = (osc - threshold) / (1.0 - threshold)
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

    def _render_meteor_shower(self, t: float) -> List[List[int]]:
        """Three staggered meteor heads cross the strip with asymmetric cool-white tails."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        sp = max(0.2, self._speed)
        tail_mult = max(0.2, getattr(self, "_tail_length", 1.0))
        meteors = [
            ((t * 13.0 * sp + 3.0) % (NUM_SEGMENTS + 16.0) - 8.0, 1.0, 7.0 * tail_mult),
            ((t * 9.0 * sp + 27.0) % (NUM_SEGMENTS + 20.0) - 10.0, 0.72, 10.0 * tail_mult),
            ((t * 16.0 * sp + 41.0) % (NUM_SEGMENTS + 12.0) - 6.0, 0.48, 5.0 * tail_mult),
        ]
        segs: List[List[int]] = []
        for i in range(NUM_SEGMENTS):
            peak, tail_pos = 0.0, 0.0
            for head, gain, tail_len in meteors:
                behind = head - i
                if 0.0 <= behind <= tail_len:
                    glow = math.exp(-behind / max(1.2, tail_len * 0.38)) * gain
                    if glow > peak:
                        peak, tail_pos = glow, behind / tail_len
                if abs(i - head) <= 1.15:
                    head_glow = gain * (1.0 - abs(i - head) / 1.15)
                    if head_glow > peak:
                        peak, tail_pos = head_glow, 0.0
            if peak <= 0.015:
                segs.append([pal[0][0], pal[0][1], 2])
                continue
            hue, sat, _ = sample_palette_oklab(pal, min(1.0, 0.08 + tail_pos * 0.92), cyclic=False)
            white_mix = max(0.0, 1.0 - tail_pos * 2.8)
            hue = int((hue * (1.0 - white_mix) + 195 * white_mix) % 360)
            sat = int(sat * (1.0 - white_mix) + 22 * white_mix)
            value = int(max(2, min(100, 2 + 98 * peak)))
            segs.append([hue, max(0, min(100, sat)), value])
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
        wave_mult = max(0.3, getattr(self, "_wave_width", 1.0))
        freq_factor = 4.0 / wave_mult
        topo = get_l930_topology()
        r_dists = topo.radial_projection(center_x=0.0, center_y=0.8)

        segs = []
        phase = (t * 0.8 * sp) % 1.0
        for i in range(NUM_SEGMENTS):
            r = r_dists[i]
            # Expanding circular wave crests scaled by wave_width
            wave = math.sin((r - phase) * freq_factor * math.pi)
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

    def _render_tide(self, t: float) -> List[List[int]]:
        """Overlapping ocean waves with different speeds and thin seafoam crests on dark teal."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        sp = self._speed
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            # Three overlapping ocean waves with different speeds and widths
            w1 = math.sin(x * 3.5 * math.pi - t * 0.9 * sp)
            w2 = math.cos(x * 5.0 * math.pi + t * 0.45 * sp)
            w3 = math.sin(x * 2.0 * math.pi - t * 1.4 * sp)
            wave = (w1 * 0.45 + w2 * 0.35 + w3 * 0.20)  # [-1.0, 1.0]

            # Base dark teal
            if wave > 0.42:
                # Thin traveling seafoam crest
                crest_factor = (wave - 0.42) / 0.58
                h = int(170 + 15 * (1.0 - crest_factor))
                s = int(max(15, 75 - crest_factor * 60))
                v = int(max(40, min(100, 45 + crest_factor * 55)))
            else:
                norm_d = (wave + 1.0) * 0.5
                h, s, _ = sample_palette_oklab(pal, norm_d * 0.4, cyclic=False)
                v = int(max(4, min(35, 6 + norm_d * 26)))
            segs.append([h, s, v])
        return segs

    def _render_drift(self, t: float) -> List[List[int]]:
        """Slow hue advection traveling across strip with subtle overlapping color clouds."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "dusk")
        sp = self._speed
        segs = []
        # Continuous advective drift
        flow_offset = t * 0.06 * sp
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            # Overlapping color clouds via multi-frequency advection
            cloud = 0.12 * math.sin(x * 4.0 * math.pi - flow_offset * 2.0 * math.pi) + \
                    0.08 * math.cos(x * 7.0 * math.pi + flow_offset * 1.5 * math.pi)
            pos = (x * 0.7 - flow_offset + cloud) % 1.0
            h, s, _ = sample_palette_oklab(pal, pos, cyclic=True)
            swell = 0.5 + 0.5 * math.sin(x * 3.0 * math.pi + flow_offset * 3.0)
            v = int(max(15, min(75, 20 + swell * 45)))
            segs.append([h, s, v])
        return segs

    def _render_breathe(self, t: float) -> List[List[int]]:
        """Deliberate inhale/exhale envelope with slow relaxing color-temperature shift."""
        sp = max(0.2, self._speed)
        # 10 second respiratory cycle: 4s inhale, 1s hold, 5s exhale
        cycle = 10.0 / sp
        phase = (t % cycle) / cycle
        if phase < 0.40:
            # Inhale: expanding, warming up
            p = phase / 0.40
            env = 0.5 - 0.5 * math.cos(p * math.pi)
        elif phase < 0.50:
            # Inhale hold
            env = 1.0
        else:
            # Exhale: slow smooth relaxation
            p = (phase - 0.50) / 0.50
            env = 0.5 + 0.5 * math.cos(p * math.pi)

        # Color temperature shift: soft cooler indigo/rose (260) -> warm incandescent amber (32)
        h = int(260 - env * 228)  # 260 -> 32
        s = int(50 + env * 42)
        v = int(max(6, min(100, 10 + env * 85)))
        return [[h, s, v]] * NUM_SEGMENTS

    def _render_fireflies(self, t: float) -> List[List[int]]:
        """Loose clusters of green-gold lights with asynchronous bloom, short peak, and long fade."""
        sp = self._speed
        segs = []
        # Two wandering swarm cluster centers
        c1 = 16.0 + 10.0 * math.sin(t * 0.35 * sp)
        c2 = 34.0 + 11.0 * math.cos(t * 0.28 * sp + 1.5)
        for i in range(NUM_SEGMENTS):
            dist1 = abs(i - c1)
            dist2 = abs(i - c2)
            cluster_prob = math.exp(-0.5 * (dist1 / 5.5) ** 2) + math.exp(-0.5 * (dist2 / 5.5) ** 2)

            # Independent non-synchronous oscillator per IC
            f = 0.8 + (i * 17 % 13) * 0.12 * sp
            phase = i * 23.7
            osc = math.sin(t * f + phase)
            if osc > 0.72 and cluster_prob > 0.15:
                # Asymmetric envelope: sharp bloom, long decay
                bloom = (osc - 0.72) / 0.28
                h = int(82 + (i % 5) * 8)  # Green-gold chartreuse
                s = 92
                v = int(max(8, min(100, 15 + bloom * 80 * min(1.0, cluster_prob))))
            else:
                h, s, v = 110, 85, 2  # Dark forest background
            segs.append([h, s, v])
        return segs

    def _render_prism_sparks(self, t: float) -> List[List[int]]:
        """Black background with sparse, high-saturation RGB sparks with varied lifetimes."""
        sp = self._speed
        segs = []
        for i in range(NUM_SEGMENTS):
            f = 1.2 + (i * 19 % 17) * 0.18 * sp
            phase = i * 31.415
            osc = math.sin(t * f + phase)
            if osc > 0.88:
                spark = (osc - 0.88) / 0.12
                h = int((i * 67 + t * 45 * sp) % 360)
                s = 100
                v = int(max(20, min(100, spark * 100)))
            else:
                h, s, v = 0, 0, 0  # Pure black background
            segs.append([h, s, v])
        return segs

    def _render_vaporwave_neon(self, t: float) -> List[List[int]]:
        """Thick magenta, cyan, and violet bands with deep gaps and slow scanline."""
        sp = self._speed
        segs = []
        scan = (t * 0.18 * sp) % 1.0
        colors = [(315, 100, 95), (185, 100, 100), (275, 100, 90)]  # Magenta, Cyan, Violet
        for i in range(NUM_SEGMENTS):
            x = (i / float(NUM_SEGMENTS - 1) - scan) % 1.0
            band_idx = int(x * 6) % 3
            band_pos = (x * 6) % 1.0

            # Strong graphic contrast with deep dark gaps
            if 0.15 <= band_pos <= 0.85:
                c = colors[band_idx]
                h, s = c[0], c[1]
                v = int(max(20, min(100, c[2] * (1.0 - abs(band_pos - 0.5) * 1.2))))
            else:
                h, s, v = 260, 90, 4  # Deep dark gap
            segs.append([h, s, v])
        return segs

    def _render_lantern_sweep(self, t: float) -> List[List[int]]:
        """Warm moving core with wide golden halo and gentle lingering tail, eased at ends."""
        sp = self._speed
        # Eased back-and-forth movement using sine shaping
        pos = 24.5 + 23.5 * math.sin(t * 1.1 * sp)
        segs = []
        for i in range(NUM_SEGMENTS):
            dist = abs(i - pos)
            # Warm core (dist < 2.0) and wide golden halo (dist < 8.0)
            core = math.exp(-0.5 * (dist / 1.6) ** 2)
            halo = math.exp(-0.5 * (dist / 6.0) ** 2) * 0.55
            intensity = min(1.0, core + halo)

            h = int(32 + (1.0 - core) * 12)  # 32 incandescent gold -> 44 soft warm amber
            s = int(85 + core * 15)
            v = int(max(4, min(100, 6 + intensity * 94)))
            segs.append([h, s, v])
        return segs

    def _render_aurora(self, t: float) -> List[List[int]]:
        """Broad, slow-moving green, teal, and violet curtains with long overlapping transitions."""
        sp = self._speed
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            # Overlapping atmospheric curtain ribbons
            c1 = math.sin(x * 2.2 * math.pi + t * 0.25 * sp)
            c2 = math.cos(x * 3.1 * math.pi - t * 0.18 * sp + 1.2)
            c3 = math.sin(x * 1.5 * math.pi + t * 0.32 * sp + 2.4)

            # Dominant wavelength selection
            if c1 > c2 and c1 > c3:
                h, s = 140, 95  # Emerald aurora
                v = int(max(10, min(90, 25 + (c1 + 1.0) * 30)))
            elif c2 > c3:
                h, s = 185, 90  # Cyan-teal ribbon
                v = int(max(10, min(90, 20 + (c2 + 1.0) * 32)))
            else:
                h, s = 275, 85  # Violet curtain
                v = int(max(10, min(90, 18 + (c3 + 1.0) * 30)))
            segs.append([h, s, v])
        return segs

    def _render_deep_ocean(self, t: float) -> List[List[int]]:
        """Deep navy with subtle teal pressure waves and cyan bioluminescent highlights."""
        sp = self._speed
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            pressure = 0.5 + 0.5 * math.sin(x * 3.0 * math.pi - t * 0.22 * sp)
            # Occasional cyan bioluminescent speckle
            spark = math.sin(t * (1.1 + (i % 7) * 0.2) * sp + i * 19.3)
            if spark > 0.90:
                h = 175
                s = 85
                v = int(max(15, min(80, 20 + (spark - 0.90) / 0.10 * 60)))
            else:
                h = int(210 + pressure * 18)
                s = int(85 + pressure * 12)
                v = int(max(3, min(35, 5 + pressure * 28)))
            segs.append([h, s, v])
        return segs

    def _render_raindrop(self, t: float) -> List[List[int]]:
        """Dark background punctuated by isolated drops that travel and fade at varied intervals."""
        sp = self._speed
        segs = [[220, 90, 3]] * NUM_SEGMENTS  # Dark background
        # 4 staggered raindrops traveling downward
        drops = [
            ((t * 14.0 * sp + 2.0) % (NUM_SEGMENTS + 8.0) - 4.0, 0.9),
            ((t * 11.0 * sp + 18.0) % (NUM_SEGMENTS + 12.0) - 6.0, 0.75),
            ((t * 16.0 * sp + 31.0) % (NUM_SEGMENTS + 10.0) - 5.0, 0.85),
            ((t * 9.5 * sp + 44.0) % (NUM_SEGMENTS + 15.0) - 7.0, 0.65),
        ]
        out = [list(c) for c in segs]
        for head, str_val in drops:
            for i in range(NUM_SEGMENTS):
                behind = head - i
                if 0.0 <= behind <= 3.5:
                    decay = (1.0 - behind / 3.5) ** 1.5 * str_val
                    v = int(max(out[i][2], min(100, 10 + decay * 88)))
                    out[i] = [195, max(15, int(90 - decay * 55)), v]
        return out

    def _render_lightning(self, t: float) -> List[List[int]]:
        """Mostly dark with sharp white-blue flashes, irregular pauses, and uneven decays."""
        sp = self._speed
        # Pseudo-random episodic thunderstorm cycle (~6.5s)
        cycle = 6.5 / max(0.2, sp)
        sub_t = t % cycle
        segs = [[230, 95, 2]] * NUM_SEGMENTS

        # Strike timings within cycle: 0.8s, 0.95s, 3.4s, 3.52s, 3.68s
        strikes = [
            (0.80, 0.12, 1.0, 15, 35),
            (0.95, 0.08, 0.7, 10, 45),
            (3.40, 0.10, 0.9, 0, 30),
            (3.52, 0.06, 0.6, 20, 48),
            (3.68, 0.18, 1.0, 5, 45),
        ]
        for s_start, s_dur, s_str, seg_start, seg_end in strikes:
            if s_start <= sub_t <= (s_start + s_dur):
                prog = (sub_t - s_start) / s_dur
                flash = (1.0 - prog) * s_str
                for i in range(seg_start, min(NUM_SEGMENTS, seg_end)):
                    h = 205
                    s = int(max(5, 30 - flash * 25))  # Sharp cool white-blue
                    v = int(max(segs[i][2], min(100, flash * 100)))
                    segs[i] = [h, s, v]
        return segs

    def _render_police(self, t: float) -> List[List[int]]:
        """Crisp red and blue alternating sections with tiny dark gaps between flashes."""
        sp = self._speed
        phase = (t * 4.0 * sp) % 2.0  # 4 Hz strobe
        half = NUM_SEGMENTS // 2
        segs = []
        is_red_phase = (phase < 1.0)
        strobe_on = (phase % 0.5) < 0.28  # Strobe pulse with dark gap

        for i in range(NUM_SEGMENTS):
            if i < half:
                # Left half: Red
                if is_red_phase and strobe_on:
                    segs.append([0, 100, 100])
                else:
                    segs.append([0, 100, 0])
            else:
                # Right half: Blue
                if (not is_red_phase) and strobe_on:
                    segs.append([240, 100, 100])
                else:
                    segs.append([240, 100, 0])
        return segs

    def _render_candy_cane(self, t: float) -> List[List[int]]:
        """Wide alternating red and white bands visibly moving along strip with clean edges."""
        sp = self._speed
        offset = t * 6.0 * sp
        segs = []
        band_width = 6.0
        for i in range(NUM_SEGMENTS):
            pos = (i - offset) % (band_width * 2.0)
            if pos < band_width:
                # Peppermint Red
                segs.append([355, 100, 100])
            else:
                # Crisp White
                segs.append([0, 0, 100])
        return segs

    def _render_haunted_mansion(self, t: float) -> List[List[int]]:
        """Near-black base with rare emerald glows, eerie violet pools, and sudden flashes."""
        sp = self._speed
        segs = []
        flash_time = (t * 0.4 * sp) % 5.0
        is_flash = (flash_time < 0.12)
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            eerie_violet = math.sin(x * 3.0 * math.pi + t * 0.3 * sp)
            emerald_pool = math.cos(x * 4.5 * math.pi - t * 0.22 * sp)

            if is_flash:
                segs.append([140, 30, 95])  # Spooky flash
            elif emerald_pool > 0.65:
                # Eerie emerald glow
                segs.append([135, 100, int(max(8, min(80, (emerald_pool - 0.65) * 200)))])
            elif eerie_violet > 0.50:
                # Eerie violet pool
                segs.append([285, 95, int(max(6, min(65, (eerie_violet - 0.50) * 120)))])
            else:
                segs.append([270, 95, 2])  # Near-black base
        return segs

    def _render_rainbow(self, t: float) -> List[List[int]]:
        """Continuous seamless circulating rainbow gradient without abrupt jumps."""
        sp = self._speed
        offset = (t * 0.12 * sp) % 1.0
        segs = []
        for i in range(NUM_SEGMENTS):
            hue = int(((i / float(NUM_SEGMENTS)) + offset) * 360) % 360
            segs.append([hue, 100, 100])
        return segs

    # ── 2D Spatial & Geometric Renderers (LEDGeometry Inspired) ───────────────

    def _render_gravity_slosh(self, t: float) -> List[List[int]]:
        """2D U-tube gravity slosh falling from headboard arch apex and rebounding at corners."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        sp = self._speed
        # Liquid height oscillation in U-tube: -1.0 (left high) to 1.0 (right high)
        theta = t * 2.2 * sp
        slosh = math.sin(theta)
        segs = []
        topo = get_l930_topology()

        for i in range(NUM_SEGMENTS):
            x, y = topo.coords[i]
            # Height relative to liquid surface level: surface tilts with slosh
            surface_y = slosh * x * 0.65
            submerged = max(0.0, min(1.0, (surface_y - y + 0.6) / 0.8))

            if submerged > 0.05:
                h, s, _ = sample_palette_oklab(pal, submerged, cyclic=False)
                v = int(max(10, min(100, submerged * 90)))
            else:
                h, s, v = pal[0][0], pal[0][1], 3
            segs.append([h, s, v])
        return segs

    def _render_lissajous_orbit(self, t: float) -> List[List[int]]:
        """Invisible 2D Lissajous orbit with soft Euclidean proximity glow."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        sp = self._speed
        topo = get_l930_topology()
        # Invisible point orbiting in 2D room space
        px = 0.80 * math.sin(1.15 * t * sp)
        py = 0.70 * math.cos(1.65 * t * sp + 0.4)

        segs = []
        for i in range(NUM_SEGMENTS):
            x, y = topo.coords[i]
            d = math.sqrt((x - px) ** 2 + (y - py) ** 2)
            glow = math.exp(-0.5 * (d / 0.40) ** 2)
            h, s, _ = sample_palette_oklab(pal, (t * 0.08 * sp + d * 0.5) % 1.0, cyclic=True)
            v = int(max(4, min(100, 6 + glow * 94)))
            segs.append([h, s, v])
        return segs

    def _render_planar_wind(self, t: float) -> List[List[int]]:
        """45-degree planar wavefront slicing diagonally across 2D physical room space."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "forest")
        sp = self._speed
        topo = get_l930_topology()
        proj = topo.directional_projection(angle_deg=45.0)

        segs = []
        phase = (t * 0.6 * sp) % 1.0
        for i in range(NUM_SEGMENTS):
            p = proj[i]
            wave = 0.5 + 0.5 * math.sin((p - phase) * 3.0 * 2.0 * math.pi)
            h, s, _ = sample_palette_oklab(pal, (p + phase * 0.5) % 1.0, cyclic=True)
            v = int(max(10, min(100, 15 + (wave ** 1.8) * 85)))
            segs.append([h, s, v])
        return segs

    def _render_radar_sweep(self, t: float) -> List[List[int]]:
        """Focused angular beam rotating around room center with exponential decay trail."""
        sp = self._speed
        topo = get_l930_topology()
        angles = topo.polar_projection(center_x=0.0, center_y=0.0)
        beam_angle = (t * 0.6 * sp) % 1.0

        segs = []
        for i in range(NUM_SEGMENTS):
            phi = angles[i]
            diff = (phi - beam_angle) % 1.0
            # Exponential phosphor decay behind sweep head
            if diff < 0.45:
                decay = math.exp(-diff / 0.12)
                h = 135  # Radar phosphor green
                s = int(max(20, 95 - decay * 60))
                v = int(max(4, min(100, 5 + decay * 95)))
            else:
                h, s, v = 140, 95, 2
            segs.append([h, s, v])
        return segs

    # ── FastLED Ports & Strips Effects ────────────────────────────────────────

    def _render_glitter_cascade(self, t: float) -> List[List[int]]:
        """Slow drifting base palette overlaid with high-luminance micro-sparkles."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        sp = self._speed
        segs = []
        drift = (t * 0.05 * sp) % 1.0
        for i in range(NUM_SEGMENTS):
            pos = (i / float(NUM_SEGMENTS - 1) + drift) % 1.0
            h, s, _ = sample_palette_oklab(pal, pos, cyclic=True)
            v = int(max(15, min(65, 30 + 25 * math.sin(pos * 2.0 * math.pi))))

            # Occasional sub-second glitter sparkle
            spark = math.sin(t * (3.5 + (i % 11) * 0.5) * sp + i * 29.3)
            if spark > 0.94:
                # White/golden glitter pop
                s = int(s * 0.25)
                v = 100
            segs.append([h, s, v])
        return segs

    def _render_bpm_resonator(self, t: float) -> List[List[int]]:
        """FastLED beatsin8 multi-harmonic sine waves mixing additively in OKLab space."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "dusk")
        sp = self._speed
        # 4 harmonic tempos: 60, 80, 100, 120 BPM
        b1 = math.sin(t * (60.0 / 60.0 * 2.0 * math.pi) * sp)
        b2 = math.sin(t * (80.0 / 60.0 * 2.0 * math.pi) * sp)
        b3 = math.sin(t * (100.0 / 60.0 * 2.0 * math.pi) * sp)
        b4 = math.sin(t * (120.0 / 60.0 * 2.0 * math.pi) * sp)

        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            wave = math.sin(x * 3.0 * math.pi + b1) * 0.35 + \
                   math.cos(x * 5.0 * math.pi + b2) * 0.25 + \
                   math.sin(x * 7.0 * math.pi + b3) * 0.20 + \
                   math.cos(x * 2.0 * math.pi + b4) * 0.20

            norm_w = (wave + 1.0) * 0.5
            h, s, _ = sample_palette_oklab(pal, norm_w, cyclic=True)
            v = int(max(12, min(100, 20 + norm_w * 80)))
            segs.append([h, s, v])
        return segs

    def _render_coordinated_lightning(self, t: float) -> List[List[int]]:
        """Coordinated storm: sharp lightning strikes across segments with amber thunder roll."""
        sp = self._speed
        flash_mult = max(0.2, getattr(self, "_flash_strength", 1.0))
        cycle = 8.0 / max(0.2, sp)
        sub_t = t % cycle
        segs = [[220, 95, 2]] * NUM_SEGMENTS

        if 1.0 <= sub_t <= 1.25:
            # Main lightning strike scaled by flash_strength
            prog = (sub_t - 1.0) / 0.25
            str_val = min(1.0, (1.0 - prog) * flash_mult)
            for i in range(12, 38):
                segs[i] = [200, 15, int(str_val * 100)]
        elif 1.35 <= sub_t <= 1.50:
            # Secondary branch flash scaled by flash_strength
            prog = (sub_t - 1.35) / 0.15
            str_val = min(1.0, (1.0 - prog) * 0.75 * flash_mult)
            for i in range(25, 48):
                segs[i] = [205, 25, int(str_val * 90)]
        elif 1.6 <= sub_t <= 3.8:
            # Deep amber rumbling afterglow across desk/bias
            rumble_prog = (sub_t - 1.6) / 2.2
            heat = math.exp(-rumble_prog * 2.5) * (0.6 + 0.4 * math.sin(t * 12.0 * sp)) * min(1.5, flash_mult)
            for i in range(NUM_SEGMENTS):
                segs[i] = [28, 95, int(max(2, min(40, heat * 38)))]
        return segs

    def _compute(self, name: str, t: float = 0.0) -> List[List[int]]:
        """Backward compatibility simulation computation for test suites."""
        eff = name.lower()
        if eff == "lava_lamp":
            return self._render_lava_lamp(t)
        elif eff == "dusk":
            return self._render_standing_wave_dusk(t)
        elif eff in ("golden_hour", "ambient_drift", "sakura", "northern_lights"):
            return self._render_standing_wave_golden_hour(t)
        elif eff in ("hearth", "fireplace", "fire_crawl"):
            return self._render_hearth_fire2012(t)
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
        elif eff == "tide":
            return self._render_tide(t)
        elif eff == "drift":
            return self._render_drift(t)
        elif eff == "breathe":
            return self._render_breathe(t)
        elif eff == "fireflies":
            return self._render_fireflies(t)
        elif eff == "prism_sparks":
            return self._render_prism_sparks(t)
        elif eff == "starfield":
            return self._render_autonomous_starfield(t)
        elif eff == "embers":
            return self._render_autonomous_embers(t)
        elif eff == "gravity_slosh":
            return self._render_gravity_slosh(t)
        elif eff == "lissajous_orbit":
            return self._render_lissajous_orbit(t)
        elif eff == "planar_wind":
            return self._render_planar_wind(t)
        elif eff == "radar_sweep":
            return self._render_radar_sweep(t)
        elif eff == "glitter_cascade":
            return self._render_glitter_cascade(t)
        elif eff == "bpm_resonator":
            return self._render_bpm_resonator(t)
        elif eff == "vaporwave_neon":
            return self._render_vaporwave_neon(t)
        elif eff == "lantern_sweep":
            return self._render_lantern_sweep(t)
        elif eff == "aurora":
            return self._render_aurora(t)
        elif eff == "deep_ocean":
            return self._render_deep_ocean(t)
        elif eff == "raindrop":
            return self._render_raindrop(t)
        elif eff == "lightning":
            return self._render_lightning(t)
        elif eff == "coordinated_lightning":
            return self._render_coordinated_lightning(t)
        elif eff == "police":
            return self._render_police(t)
        elif eff == "candy_cane":
            return self._render_candy_cane(t)
        elif eff == "haunted_mansion":
            return self._render_haunted_mansion(t)
        elif eff == "rainbow":
            return self._render_rainbow(t)
        elif eff == "flicker":
            # Candle flicker: localized warm candle micro-surges
            return [[32, 90, max(5, min(100, int(45 + 35 * math.sin(t * 3.0 + i * 7.7))))] for i in range(NUM_SEGMENTS)]
        elif eff == "sunrise":
            # Sunrise: progressive dawn peach-gold expansion from center
            prog = (math.sin(t * 0.4 * self._speed) + 1.0) * 0.5
            return [[int(20 + 25 * prog), int(95 - 40 * prog), int(max(10, min(100, 20 + prog * 80)))] for _ in range(NUM_SEGMENTS)]
        elif eff == "sunset":
            # Sunset: twilight plum to warm coral fade
            prog = (math.cos(t * 0.35 * self._speed) + 1.0) * 0.5
            return [[int(330 - 50 * prog), int(85 + 15 * prog), int(max(8, min(85, 15 + prog * 70)))] for _ in range(NUM_SEGMENTS)]
        elif eff in ("ocean", "ocean_waves"):
            return [[int(185 + 15 * math.sin(t * 0.8 + i * 0.2)), 90, int(35 + 25 * math.cos(t * 0.6 + i * 0.15))] for i in range(NUM_SEGMENTS)]
        return [[30, 80, 60]] * NUM_SEGMENTS

