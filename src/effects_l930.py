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


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Cubic interpolation with zero slope at both edges."""
    if edge1 <= edge0:
        return 1.0 if x >= edge1 else 0.0
    u = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return u * u * (3.0 - 2.0 * u)

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

NATIVE_ALIASES: Dict[str, str] = {
    "sunrise_native": "sunrise",
    "sunset_native": "sunset",
    "flicker_native": "flicker",
    "ocean_native": "ocean",
    "raindrop_native": "raindrop",
    "lightning_native": "lightning",
    "aurora_native": "aurora",
    "rainbow_native": "rainbow",
    "candy_cane_native": "candy_cane",
    "haunted_mansion_native": "haunted_mansion",
    "liquid_iridescence": "oil_slick",
    "moire": "holographic_moire",
    "pacifica": "bioluminescent_tide",
    "embers_drift": "ember_drift",
}


def resolve_effect_alias(name: str) -> str:
    """Resolves native effect aliases and suffixes to valid catalog keys."""
    key = (name or "").strip().lower()
    if key in NATIVE_ALIASES:
        return NATIVE_ALIASES[key]
    if key.endswith("_native"):
        base = key[:-7]
        if base in EFFECT_CATALOG or base in NATIVE_PRESETS:
            return base
    return key


# Effect classification registry
EFFECT_CATALOG: Dict[str, Dict[str, Any]] = {
    # ── 1. Core Effects (22) ─────────────────────────────────────────────────
    'tide': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Overlapping ocean waves with different speeds and thin seafoam crests on dark teal',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'drift': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Slow hue advection traveling across strip with subtle overlapping color clouds',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'breathe': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Deliberate inhale/exhale envelope with slow relaxing color-temperature shift',
        'default_palette': 'warm_mono',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'starfield': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Near-black navy background with isolated stars brightening, holding, and fading independently',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness', 'particle_density'],
    },
    'embers': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Near-black background with dark-red coal beds and isolated orange embers glowing at varied rates',
        'default_palette': 'ember',
        'supported_controls': ['speed', 'brightness', 'particle_density'],
    },
    'fireflies': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Loose clusters of green-gold lights with asynchronous bloom, short peak, and long fade',
        'default_palette': 'forest',
        'supported_controls': ['speed', 'brightness', 'particle_density'],
    },
    'lava_lamp': {
        'kind': 'streamed_slow',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Viscous molten metaballs stretching, merging, and separating with dark gaps',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'golden_hour': {
        'kind': 'streamed_slow',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Warm amber-to-rose horizon with slow moving bands and rare golden glints',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'sunrise': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Progressive dawn: low warm glow, peach/gold, moving to soft daylight',
        'supported_controls': ['speed', 'brightness'],
    },
    'sunset': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Reverse daylight progression through coral, rose, plum, and deep violet',
        'supported_controls': ['speed', 'brightness'],
    },
    'flicker': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Understated candle/ember with localized warm surges and uneven flame intensity',
        'default_palette': 'fire',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'campfire_hearth': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'core',
        'desc': 'Multi-zone warm orange, deep crimson, and flickering gold glowing independently',
        'default_palette': 'fire',
        'supported_controls': ['speed', 'brightness'],
    },
    'comet': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'core',
        'desc': 'One or two decisive bright comet heads with long, cooling chromatic tails',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness', 'palette', 'tail_length'],
    },
    'sinelon': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'core',
        'desc': 'Single sweeping beacon with phosphorescent decay trail',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness', 'palette', 'tail_length'],
    },
    'cyber_chase': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'core',
        'desc': 'Two opposing colored pulses with broad continuous tails, smooth reversal, and a softened center bloom',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness', 'palette', 'flash_strength'],
    },
    'radial_ripple': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'core',
        'desc': '2D expanding concentric rings with bright crest and fading trail from arch apex',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness', 'palette', 'wave_width'],
    },
    'aurora': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'core',
        'desc': 'Broad, slow-moving green, teal, and violet curtains with continuously blended hues',
        'default_palette': 'forest',
        'supported_controls': ['speed', 'brightness', 'wave_width'],
    },
    'deep_ocean': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'core',
        'desc': 'Deep navy with subtle teal pressure waves and cyan bioluminescent highlights',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness'],
    },
    'raindrop': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'core',
        'desc': 'Dark background with slow multi-direction drops, soft heads, and long fading tails',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness', 'particle_density'],
    },
    'lightning': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'core',
        'desc': 'Mostly dark with sharp white-blue flashes, irregular pauses, and uneven decays',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness', 'flash_strength'],
    },
    'rainbow': {
        'kind': 'firmware',
        'group': 'Seasonal & Novelty',
        'category': 'core',
        'desc': 'Continuous seamless circulating rainbow gradient without abrupt jumps',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness'],
    },
    'prism_sparks': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'core',
        'desc': 'Black background with sparse, high-saturation RGB sparks with varied lifetimes',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness', 'particle_density'],
    },

    # ── 2. Advanced Effects (10) ─────────────────────────────────────────────
    'meteor_shower': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'advanced',
        'desc': 'Narrow one-way streaks with cold-white cores and long blue tails at irregular intervals',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness', 'tail_length'],
    },
    'juggle': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'advanced',
        'desc': '3 to 5 distinct glowing orbs with different speeds, spacing, and trajectories',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'spiral_vortex': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'advanced',
        'desc': '2D polar angle vortex spinning smoothly with layered chromatic bands',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'gravity_slosh': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'advanced',
        'desc': '2D U-tube gravity slosh falling from arch apex and rebounding at bottom corners',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness', 'palette', 'wave_width'],
    },
    'lissajous_orbit': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'advanced',
        'desc': 'Invisible 2D Lissajous orbit with soft Euclidean proximity glow',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'planar_wind': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'advanced',
        'desc': '45-degree planar wavefront slicing diagonally across 2D physical room space',
        'default_palette': 'forest',
        'supported_controls': ['speed', 'brightness', 'palette', 'wave_width'],
    },
    'radar_sweep': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'advanced',
        'desc': 'Focused angular beam rotating around room center with exponential decay trail',
        'default_palette': 'forest',
        'supported_controls': ['speed', 'brightness', 'palette', 'tail_length'],
    },
    'vaporwave_neon': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'advanced',
        'desc': 'Thick magenta, cyan, and violet bands with deep gaps and slow scanline',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness'],
    },
    'neon_heartbeat': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'advanced',
        'desc': 'Anatomical lub-dub-pause rhythm with strong primary pulse and smaller secondary bloom',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness', 'palette', 'flash_strength'],
    },
    'lantern_sweep': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'advanced',
        'desc': 'Warm moving core with wide golden halo and gentle lingering tail, eased at ends',
        'default_palette': 'warm_mono',
        'supported_controls': ['speed', 'brightness', 'tail_length'],
    },

    # ── 3. Seasonal & Novelty Effects (3) ────────────────────────────────────
    'candy_cane': {
        'kind': 'firmware',
        'group': 'Seasonal & Novelty',
        'subgroup': 'Seasonal',
        'category': 'seasonal',
        'desc': 'Wide red and warm-white bands moving with softened transitions and slower motion',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness'],
    },
    'haunted_mansion': {
        'kind': 'firmware',
        'group': 'Seasonal & Novelty',
        'subgroup': 'Seasonal / Spooky',
        'category': 'seasonal',
        'desc': 'Near-black base with gradual, localized emerald glows and eerie violet pools',
        'default_palette': 'forest',
        'supported_controls': ['speed', 'brightness'],
    },
    'police': {
        'kind': 'firmware',
        'group': 'Seasonal & Novelty',
        'subgroup': 'Novelty',
        'category': 'novelty',
        'desc': 'Slow alternating red and blue siren pulses with smooth brightness envelopes',
        'warning': 'Rapid flashing / strobe warning: contains high-contrast alternating red/blue pulses.',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness'],
    },

    # ── 3b. Creative Original Designs (7) ────────────────────────────────────
    'oil_slick': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'creative',
        'desc': 'Thin-film interference fields drifting across petrol cyan, indigo, violet, rose, and amber hues',
        'default_palette': 'sunset',
        'supported_controls': ['speed', 'brightness'],
    },
    'silk_ribbons': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'creative',
        'desc': 'Broad, soft-edged luminous ribbons flowing in opposite directions and blending smoothly in OKLab space',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness'],
    },
    'nebula_bloom': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'creative',
        'desc': 'Atmospheric cosmic violet, indigo, and fuchsia clouds expanding and breathing over deep space negative space',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness'],
    },
    'holographic_moire': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'creative',
        'desc': 'Two detuned spatial carrier waves producing moving macroscopic interference fringes and holographic sheen',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'bioluminescent_tide': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'creative',
        'desc': 'Pacifica-inspired multi-layer oceanic swell simulation with glowing turquoise crests and deep abyssal baseline',
        'default_palette': 'tide',
        'supported_controls': ['speed', 'brightness'],
    },
    'ember_drift': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'creative',
        'desc': 'Simulated 1D thermal convection with drifting copper coals and breathing heat pockets',
        'default_palette': 'ember',
        'supported_controls': ['speed', 'brightness'],
    },
    'cyberpunk': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'creative',
        'desc': 'Dedicated synthwave dual-layer composition with electric cyan waves, neon magenta baseline, and golden highlights',
        'default_palette': 'dusk',
        'supported_controls': ['speed', 'brightness'],
    },

    # ── 4. Merged Entries / Aliases (10) ─────────────────────────────────────
    'dusk': {
        'kind': 'streamed_slow',
        'group': 'Ambient',
        'category': 'alias',
        'desc': 'Merged into golden_hour: slow twilight progression from amber to deep violet',
        'default_palette': 'dusk',
        'alias_of': 'golden_hour',
        'default_params': {'palette': 'dusk'},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness'],
    },
    'ocean': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'alias',
        'desc': 'Merged into tide: native ocean swells and traveling crest waves',
        'default_palette': 'tide',
        'alias_of': 'tide',
        'default_params': {'palette': 'tide'},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness'],
    },
    'bioluminescent_abyss': {
        'kind': 'firmware',
        'group': 'Ambient',
        'category': 'alias',
        'desc': 'Merged into deep_ocean: midnight ocean trench with emerald/cyan glowing blooms',
        'default_palette': 'tide',
        'alias_of': 'deep_ocean',
        'default_params': {'palette': 'tide'},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness'],
    },
    'hearth': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'alias',
        'desc': 'Merged into campfire_hearth: dynamic warm coal bed and flickering fire tongues',
        'default_palette': 'fire',
        'alias_of': 'campfire_hearth',
        'default_params': {'palette': 'fire'},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness'],
    },
    'glitter_cascade': {
        'kind': 'streamed_slow',
        'group': 'Ambient',
        'category': 'alias',
        'desc': 'Merged into starfield: slow drifting base palette with dense micro-sparkles',
        'default_palette': 'sunset',
        'alias_of': 'starfield',
        'default_params': {'particle_density': 1.8},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness', 'particle_density'],
    },
    'confetti': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'alias',
        'desc': 'Merged into prism_sparks: short-lived saturated festive particle bursts',
        'default_palette': 'sunset',
        'alias_of': 'prism_sparks',
        'default_params': {'particle_density': 2.0},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness', 'particle_density'],
    },
    'dual_wipe': {
        'kind': 'firmware',
        'group': 'Motion',
        'category': 'alias',
        'desc': 'Merged into cyber_chase: dual-head bi-directional wipe meeting at center',
        'default_palette': 'dusk',
        'alias_of': 'cyber_chase',
        'default_params': {'flash_strength': 1.5},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness', 'palette'],
    },
    'sonar_sweep': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'alias',
        'desc': 'Merged into radar_sweep: sweep head with exponential echo decay trail',
        'default_palette': 'forest',
        'alias_of': 'radar_sweep',
        'default_params': {'tail_length': 2.0},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness', 'palette', 'tail_length'],
    },
    'coordinated_lightning': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'alias',
        'desc': 'Merged into lightning: multi-stage coordinated lightning storm with thunder roll',
        'default_palette': 'tide',
        'alias_of': 'lightning',
        'default_params': {'flash_strength': 2.0},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness', 'flash_strength'],
    },
    'infinite_prism': {
        'kind': 'firmware',
        'group': 'Seasonal & Novelty',
        'category': 'alias',
        'desc': 'Merged into rainbow: multi-stage seamless spectral gradient cycle',
        'default_palette': 'sunset',
        'alias_of': 'rainbow',
        'default_params': {'speed': 1.5},
        'deprecated': True,
        'supported_controls': ['speed', 'brightness'],
    },

    # ── 5. Moved to Music-Reactive (1) ───────────────────────────────────────
    'bpm_resonator': {
        'kind': 'streamed_slow',
        'group': 'Motion',
        'category': 'reactive',
        'desc': 'FastLED beatsin8 multi-harmonic synthesis (moved to music-reactive styles)',
        'default_palette': 'dusk',
        'alias_of': 'radial_ripple',
        'supported_controls': ['speed', 'brightness', 'palette', 'wave_width'],
    },
}

# Deliberately curated shelf: stock Tapo modes, aliases, strobe toys and
# one-dimensional chase effects remain internal for compatibility but are not exposed.
CORE_EFFECTS: List[str] = []
CREATIVE_EFFECTS: List[str] = [
    "oil_slick", "silk_ribbons", "nebula_bloom",
    "holographic_moire", "ember_drift",
]
SPATIAL_EXPERIMENTS: List[str] = [
    "spiral_vortex", "gravity_slosh", "lissajous_orbit",
    "planar_wind", "vaporwave_neon",
]
ADVANCED_EFFECTS: List[str] = list(SPATIAL_EXPERIMENTS)
SEASONAL_EFFECTS: List[str] = []
NOVELTY_EFFECTS: List[str] = []
OCCASIONAL_EFFECTS: List[str] = []
ACTIVE_EFFECTS: List[str] = CREATIVE_EFFECTS + SPATIAL_EXPERIMENTS
CUSTOM_EFFECTS = list(ACTIVE_EFFECTS)


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
        self._output_token: Optional[Tuple[int, str]] = None

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
        if isinstance(self._app_state, dict):
            self._app_state["effect_status"] = "requested"
            self._app_state["last_error"] = None

        key = resolve_effect_alias(effect_name)
        if key not in EFFECT_CATALOG:
            self._last_error = f"Unknown L930 effect: {effect_name!r}"
            logger.error("[L930EffectsEngine] %s", self._last_error)
            if isinstance(self._app_state, dict):
                self._app_state["effect_status"] = "failed"
                self._app_state["last_error"] = self._last_error
            return False

        # Increment effect generation immediately and snapshot output ownership for
        # this specific producer session. Old workers cannot acquire a new token.
        self._effect_generation += 1
        self._output_token = (
            self._frame_bus.capture_token(self._dev_id, OutputProducer.EFFECT)
            if self._frame_bus else None
        )

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

        meta = EFFECT_CATALOG[key]
        if "alias_of" in meta:
            alias_meta = meta
            key = meta["alias_of"]
            meta = EFFECT_CATALOG.get(key, meta)
            for p_name, p_val in alias_meta.get("default_params", {}).items():
                if p_name == "palette" and palette_name is None:
                    palette_name = p_val
                elif p_name == "speed" and speed is None:
                    speed = p_val
                elif p_name == "brightness" and brightness is None:
                    brightness = p_val
                elif hasattr(self, f"_{p_name}"):
                    setattr(self, f"_{p_name}", p_val)

        if palette_name and palette_name.strip().lower() in PALETTES:
            self._palette_name = palette_name.strip().lower()
        elif "default_palette" in meta:
            self._palette_name = meta["default_palette"]

        if speed is not None:
            self._speed = max(0.2, min(3.0, float(speed)))
        if brightness is not None:
            self._brightness = max(1, min(100, int(brightness)))

        kind = meta["kind"]
        self._active_effect_name = key
        self._active_kind = kind
        self._start_time = time.monotonic()

        if kind == "firmware":
            if isinstance(self._app_state, dict):
                self._app_state["effect_status"] = "sent"
            # An explicit effect change should be immediate. Only report success
            # after the controller confirms that the device accepted the effect.
            if not self._deploy_firmware_effect(key, force=True):
                if isinstance(self._app_state, dict):
                    self._app_state["effect_status"] = "failed"
                    self._app_state["last_error"] = self._last_error
                return False
            if isinstance(self._app_state, dict):
                self._app_state["effect_status"] = "accepted"
                self._app_state["last_error"] = None
        elif kind == "streamed_slow":
            if isinstance(self._app_state, dict):
                self._app_state["effect_status"] = "sent"
            # Start slow streaming worker (<= 2 updates/s)
            self._start_stream_worker()
        else:
            self._last_error = f"Unsupported L930 effect kind {kind!r} for {key!r}"
            logger.error("[L930EffectsEngine] %s", self._last_error)
            self._active_effect_name = None
            self._active_kind = None
            if isinstance(self._app_state, dict):
                self._app_state["effect_status"] = "failed"
                self._app_state["last_error"] = self._last_error
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

    def _output_session_is_current(self) -> bool:
        if not self._frame_bus:
            return True
        if not self._output_token:
            return False
        generation, producer_id = self._output_token
        return self._frame_bus.is_token_current(
            self._dev_id, OutputProducer.EFFECT, generation, producer_id
        )

    def _native_effect_token_kwargs(self) -> dict:
        if self._frame_bus and hasattr(self._ctrl, "set_output_token_authorizer"):
            if not self._output_token:
                return {"output_token": None}
            generation, producer_id = self._output_token
            return {"output_token": (OutputProducer.EFFECT, generation, producer_id)}
        return {}

    def _deploy_firmware_effect(self, name: str, force: bool = False) -> bool:
        if not self._output_session_is_current():
            self._last_error = "Output ownership changed before firmware effect deployment"
            return False

        fx = self._build_effect_payload(name)
        if fx is None:
            self._last_error = f"No firmware payload could be built for L930 effect {name!r}"
            logger.error("[L930EffectsEngine] %s", self._last_error)
            self._active_effect_name = None
            self._active_kind = None
            return False

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
                return True

            self._last_firmware_upload = now
            self._pending_fw_upload = None
            if self._pending_fw_timer is not None:
                try:
                    self._pending_fw_timer.cancel()
                except Exception:
                    pass
                self._pending_fw_timer = None

        try:
            if not self._output_session_is_current():
                self._last_error = "Output ownership changed before firmware effect transmission"
                return False
            future = self._loop_runner.run(
                self._ctrl.set_native_effect(
                    fx, priority=0, **self._native_effect_token_kwargs()
                )
            )
            # BackgroundLoop.run returns a Future: wait for the hardware ACK so
            # we can distinguish "accepted" from merely "queued in asyncio".
            result_method = getattr(future, "result", None)
            result = result_method(timeout=10.0) if callable(result_method) else future
            if result is False:
                raise RuntimeError(f"Controller rejected firmware effect {name!r}")
            self._last_error = None
            return True
        except Exception as exc:
            self._last_error = f"Failed to deploy L930 firmware effect {name!r}: {exc}"
            logger.error("[L930EffectsEngine] %s", self._last_error)
            self._active_effect_name = None
            self._active_kind = None
            if isinstance(self._app_state, dict):
                self._app_state["effect_status"] = "failed"
                self._app_state["last_error"] = self._last_error
            return False

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
        if not self._output_session_is_current():
            logger.debug("[L930EffectsEngine] Dropping pending firmware command after ownership changed")
            return
        self._loop_runner.run(
            self._ctrl.set_native_effect(
                fx, priority=0, **self._native_effect_token_kwargs()
            )
        )

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
            tl = max(0.2, min(3.0, self._tail_length))
            spread = max(2, min(25, int(round(5 * tl))))
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
            fx = build_firmware_sequence_effect(
                name="LanternSweep", sequence=seq, spread=spread, direction=1, transition=trans, brightness=b
            )
            fx.id = make_effect_id(f"lantern_sweep_s{int(round(self._speed * 100))}_b{b}_tl{int(round(tl * 100))}")
            return fx

        elif name == "comet":
            # Bright comet head with cooling tail
            tl = max(0.2, min(3.0, self._tail_length))
            spread = max(2, min(25, int(round(4 * tl))))
            c_head = [180, 20, 100]  # White-cyan hot head
            tail_colors = pal[:4] if pal else [[280, 80, 60], [240, 80, 30]]
            seq = [c_head] + [list(c) for c in tail_colors]
            trans = int(min(6000, 400 * sp_factor))
            fx = build_firmware_sequence_effect(
                name="Comet", sequence=seq, spread=spread, direction=1, transition=trans, brightness=b
            )
            fx.id = make_effect_id(f"comet_s{int(round(self._speed * 100))}_b{b}_tl{int(round(tl * 100))}")
            return fx

        elif name == "cyber_chase":
            # Two color pulses passing through each other with configurable flash strength
            fs = max(0.2, min(3.0, self._flash_strength))
            b_high = max(10, min(100, int(round(100 * fs))))
            c1 = pal[0] if len(pal) > 0 else (320, 100, 100)
            c2 = pal[1] if len(pal) > 1 else (185, 100, 100)
            seq = [[c1[0], c1[1], b_high], (0, 0, 10), [c2[0], c2[1], b_high], (0, 0, 10)]
            trans = int(min(6000, 600 * sp_factor))
            fx = build_firmware_sequence_effect(
                name="CyberChase", sequence=seq, spread=8, direction=1, transition=trans, brightness=b
            )
            fx.id = make_effect_id(f"cyber_chase_s{int(round(self._speed * 100))}_b{b}_fs{int(round(fs * 100))}")
            return fx

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
            tl = max(0.2, min(3.0, self._tail_length))
            spread = max(2, min(25, int(round(8 * tl))))
            c = pal[0] if pal else (320, 100, 100)
            seq = [
                [c[0], c[1], 100],
                [c[0], c[1], 50],
                [c[0], c[1], 15],
                [c[0], c[1], 5],
            ]
            trans = int(min(6000, 400 * sp_factor))
            fx = build_firmware_sequence_effect(
                name="Sinelon", sequence=seq, spread=spread, direction=2, transition=trans, brightness=b
            )
            fx.id = make_effect_id(f"sinelon_s{int(round(self._speed * 100))}_b{b}_tl{int(round(tl * 100))}")
            return fx

        elif name == "confetti":
            dens = max(0.2, min(3.0, self._particle_density))
            seed = max(1, min(600, int(round(77 * dens))))
            fade = max(80, min(6000, int(round(600 * sp_factor / dens))))
            t0 = max(80, min(6000, int(round(300 * sp_factor / math.sqrt(dens)))))
            t1 = max(t0, min(6000, int(round(1000 * sp_factor / math.sqrt(dens)))))
            fx = build_firmware_random_effect(
                name="Confetti", hue_range=(0, 359),
                saturation_range=(70, 100), brightness_range=(20, 100),
                transition_range=(t0, t1), random_seed=seed,
                fadeoff=fade,
                backgrounds=[[pal[0][0], pal[0][1], 2]], brightness=b,
            )
            fx.id = make_effect_id(f"confetti_s{int(round(self._speed * 100))}_b{b}_d{int(round(dens * 100))}_{self._palette_name}")
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

        # ── Creative Original Designs (Firmware-Accelerated Payloads) ───────
        elif name in ("oil_slick", "liquid_iridescence"):
            seq = [
                [160, 90, 40],   # Petrol green
                [200, 85, 75],   # Sheen cyan
                [285, 90, 80],   # Oily magenta/violet
                [340, 80, 70],   # Slick crimson
                [35, 95, 90],    # Golden amber highlight
                [75, 80, 60],    # Acid yellow-green
            ]
            trans = int(min(6000, 2500 * sp_factor))
            return build_firmware_sequence_effect(
                name="OilSlick", sequence=seq, spread=12, direction=1, transition=trans, brightness=b
            )

        elif name == "silk_ribbons":
            seq = [
                [270, 50, 85],   # Lavender mist
                [335, 45, 90],   # Rose quartz
                [25, 45, 95],    # Champagne gold
                [165, 40, 90],   # Seafoam silk
                [210, 45, 85],   # Soft powder blue
            ]
            trans = int(min(6000, 2200 * sp_factor))
            return build_firmware_sequence_effect(
                name="SilkRibbons", sequence=seq, spread=10, direction=3, transition=trans, brightness=b
            )

        elif name == "nebula_bloom":
            seq = [
                [240, 95, 30],   # Deep space indigo
                [275, 90, 75],   # Ultraviolet gas
                [320, 95, 90],   # Magenta starburst
                [190, 85, 70],   # Cyan stellar dust
                [255, 90, 40],   # Violet abyss
            ]
            trans = int(min(6000, 2800 * sp_factor))
            return build_firmware_sequence_effect(
                name="NebulaBloom", sequence=seq, spread=14, direction=4, transition=trans, brightness=b
            )

        elif name in ("holographic_moire", "moire"):
            seq = [
                [185, 95, 95],   # Electric cyan
                [275, 90, 85],   # Hologram violet
                [140, 90, 85],   # Emerald fringe
                [45, 90, 90],    # Golden flare
            ]
            trans = int(min(6000, 1200 * sp_factor))
            return build_firmware_sequence_effect(
                name="HoloMoire", sequence=seq, spread=5, direction=1, transition=trans, brightness=b
            )

        elif name in ("bioluminescent_tide", "pacifica"):
            seq = [
                [225, 90, 35],   # Abyssal deep ocean
                [205, 85, 70],   # Cerulean wave
                [175, 85, 95],   # Glowing turquoise crest
                [160, 40, 100],  # Pale seafoam froth
                [215, 90, 45],   # Oceanic undertow
            ]
            trans = int(min(6000, 2000 * sp_factor))
            return build_firmware_sequence_effect(
                name="BioTide", sequence=seq, spread=12, direction=3, transition=trans, brightness=b
            )

        elif name in ("ember_drift", "embers_drift"):
            seq = [
                [5, 100, 35],    # Deep mahogany red
                [18, 95, 75],    # Glowing orange coal
                [32, 90, 95],    # Radiant amber ember
                [12, 100, 50],   # Smoldering briquette
                [0, 100, 20],    # Dark ash base
            ]
            trans = int(min(6000, 2400 * sp_factor))
            return build_firmware_sequence_effect(
                name="EmberDrift", sequence=seq, spread=8, direction=1, transition=trans, brightness=b
            )

        elif name == "cyberpunk":
            seq = [
                [265, 90, 40],   # Deep night violet
                [325, 95, 95],   # Hot electric magenta
                [185, 95, 95],   # Acid cyan
                [45, 95, 90],    # Cyber gold
                [280, 85, 60],   # Neon indigo
            ]
            trans = int(min(6000, 900 * sp_factor))
            return build_firmware_sequence_effect(
                name="Cyberpunk", sequence=seq, spread=8, direction=1, transition=trans, brightness=b
            )

        # ── Advanced Effects (Firmware-Accelerated Payloads) ─────────────────
        elif name == "meteor_shower":
            tl = max(0.2, min(3.0, self._tail_length))
            spread = max(2, min(25, int(round(6 * tl))))
            seq = [
                [210, 20, 100],  # White-cyan hot core
                [225, 90, 85],   # Sapphire blue ion head
                [245, 95, 60],   # Deep blue tail
                [265, 90, 25],   # Fading violet plasma
                [275, 80, 5],    # Lingering trail dust
                [240, 90, 0],    # Black night sky
            ]
            trans = int(min(6000, 350 * sp_factor))
            fx = build_firmware_sequence_effect(
                name="MeteorShower", sequence=seq, spread=spread, direction=1, transition=trans, brightness=b
            )
            fx.id = make_effect_id(f"meteor_s{int(round(self._speed * 100))}_b{b}_tl{int(round(tl * 100))}")
            return fx

        elif name == "gravity_slosh":
            seq = pal[:5] if len(pal) >= 5 else pal
            trans = int(min(6000, 1400 * sp_factor))
            return build_firmware_sequence_effect(
                name="GravitySlosh", sequence=seq, spread=12, direction=4, transition=trans, brightness=b
            )

        elif name == "lissajous_orbit":
            seq = pal[:4] if len(pal) >= 4 else pal
            trans = int(min(6000, 1200 * sp_factor))
            return build_firmware_sequence_effect(
                name="LissajousOrbit", sequence=seq, spread=10, direction=3, transition=trans, brightness=b
            )

        elif name == "planar_wind":
            seq = pal[:5] if len(pal) >= 5 else pal
            trans = int(min(6000, 2200 * sp_factor))
            return build_firmware_sequence_effect(
                name="PlanarWind", sequence=seq, spread=16, direction=1, transition=trans, brightness=b
            )

        # 3. Firmware Random Effects
        elif name == "starfield":
            # Sparse soft twinkles on dark navy background with configurable particle density
            dens = max(0.2, min(3.0, self._particle_density))
            seed = max(1, min(600, int(round(42 * dens))))
            fade = max(150, min(6000, int(round(800 / dens))))
            t0 = max(100, min(6000, int(round(400 * sp_factor / math.sqrt(dens)))))
            t1 = max(t0, min(6000, int(round(1500 * sp_factor / math.sqrt(dens)))))
            fx = build_firmware_random_effect(
                name="Starfield",
                hue_range=(200, 230),
                saturation_range=(10, 40),
                brightness_range=(10, 100),
                transition_range=(t0, t1),
                random_seed=seed,
                fadeoff=fade,
                backgrounds=[[235, 90, 8]],
                brightness=b,
            )
            fx.id = make_effect_id(f"starfield_s{int(round(self._speed * 100))}_b{b}_d{int(round(dens * 100))}")
            return fx

        elif name == "embers":
            # Dim warm glow with slow random flicker consuming particle density
            dens = max(0.2, min(3.0, self._particle_density))
            seed = max(1, min(600, int(round(100 * dens))))
            fade = max(150, min(6000, int(round(1200 / dens))))
            t0 = max(100, min(6000, int(round(600 * sp_factor / math.sqrt(dens)))))
            t1 = max(t0, min(6000, int(round(2000 * sp_factor / math.sqrt(dens)))))
            fx = build_firmware_random_effect(
                name="Embers",
                hue_range=(15, 35),
                saturation_range=(85, 100),
                brightness_range=(5, 45),
                transition_range=(t0, t1),
                random_seed=seed,
                fadeoff=fade,
                backgrounds=[[10, 100, 15]],
                brightness=b,
            )
            fx.id = make_effect_id(f"embers_s{int(round(self._speed * 100))}_b{b}_d{int(round(dens * 100))}")
            return fx

        elif name == "fireflies":
            # Green-gold bioluminescent points blinking independently consuming particle density
            dens = max(0.2, min(3.0, self._particle_density))
            seed = max(1, min(600, int(round(333 * dens))))
            fade = max(150, min(6000, int(round(750 * sp_factor / dens))))
            t0 = max(100, min(6000, int(round(350 * sp_factor / math.sqrt(dens)))))
            t1 = max(t0, min(6000, int(round(950 * sp_factor / math.sqrt(dens)))))
            fx = build_firmware_random_effect(
                name="Fireflies",
                hue_range=(75, 130),
                saturation_range=(75, 100),
                brightness_range=(5, 95),
                transition_range=(t0, t1),
                random_seed=seed,
                fadeoff=fade,
                backgrounds=[[100, 90, 2]],
                brightness=b,
            )
            fx.id = make_effect_id(f"fireflies_s{int(round(self._speed * 100))}_b{b}_d{int(round(dens * 100))}")
            return fx

        elif name == "prism_sparks":
            # Saturated rainbow sparkles popping with independent IC timing and particle density
            dens = max(0.2, min(3.0, self._particle_density))
            seed = max(1, min(600, int(round(444 * dens))))
            fade = max(100, min(6000, int(round(450 * sp_factor / dens))))
            t0 = max(80, min(6000, int(round(200 * sp_factor / math.sqrt(dens)))))
            t1 = max(t0, min(6000, int(round(600 * sp_factor / math.sqrt(dens)))))
            fx = build_firmware_random_effect(
                name="PrismSparks",
                hue_range=(0, 360),
                saturation_range=(85, 100),
                brightness_range=(10, 100),
                transition_range=(t0, t1),
                random_seed=seed,
                fadeoff=fade,
                backgrounds=[[0, 0, 0]],
                brightness=b,
            )
            fx.id = make_effect_id(f"prism_sparks_s{int(round(self._speed * 100))}_b{b}_d{int(round(dens * 100))}")
            return fx

        elif name == "bioluminescent_abyss":
            dens = max(0.2, min(3.0, self._particle_density))
            seed = max(1, min(600, int(round(512 * dens))))
            fade = max(150, min(6000, int(round(1200 * sp_factor / dens))))
            t0 = max(100, min(6000, int(round(600 * sp_factor / math.sqrt(dens)))))
            t1 = max(t0, min(6000, int(round(1800 * sp_factor / math.sqrt(dens)))))
            fx = build_firmware_random_effect(
                name="BioAbyss",
                hue_range=(160, 195),
                saturation_range=(85, 100),
                brightness_range=(10, 85),
                transition_range=(t0, t1),
                random_seed=seed,
                fadeoff=fade,
                backgrounds=[[230, 95, 3]],
                brightness=b,
            )
            fx.id = make_effect_id(f"bioabyss_s{int(round(self._speed * 100))}_b{b}_d{int(round(dens * 100))}")
            return fx

        elif name == "campfire_hearth":
            t0 = max(150, min(6000, int(round(400 * sp_factor))))
            t1 = max(t0, min(6000, int(round(1200 * sp_factor))))
            fx = build_firmware_random_effect(
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
            fx.id = make_effect_id(f"camphearth_s{int(round(self._speed * 100))}_b{b}")
            return fx

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

        if name in EFFECT_CATALOG and "alias_of" in EFFECT_CATALOG[name]:
            return self._build_effect_payload(EFFECT_CATALOG[name]["alias_of"])

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
        Slow streamed loop (<= 2 updates/s).
        Transition_ms matches update interval so the device hardware does the smooth crossfading.
        Firmware-run effects are strictly kept on firmware path; only procedural streamed effects run here.
        """
        while not stop_event.is_set() and generation == self._effect_generation:
            try:
                eff = self._active_effect_name
                if not eff or self._active_kind != "streamed_slow":
                    if stop_event.wait(0.1):
                        break
                    continue

                now = time.monotonic()
                t = now - self._start_time

                # Base interval 0.5s strictly satisfies <= 2 updates per second limit
                interval = 0.50

                # ── Core Streamed Effects ────────────────────────────────────
                if eff == "lava_lamp":
                    segs = self._render_lava_lamp(t)
                elif eff == "golden_hour":
                    segs = self._render_standing_wave_golden_hour(t)
                elif eff == "comet":
                    segs = self._render_multi_pod_comet(t)
                elif eff == "sinelon":
                    segs = self._render_sinelon_sweep(t)
                elif eff == "cyber_chase":
                    segs = self._render_collider_chase(t)
                elif eff == "radial_ripple":
                    segs = self._render_radial_ripple(t)
                elif eff == "aurora":
                    segs = self._render_aurora(t)
                elif eff == "raindrop":
                    segs = self._render_raindrop(t)
                elif eff == "lightning":
                    segs = self._render_lightning(t)
                elif eff == "rainbow":
                    segs = self._render_rainbow(t)

                # ── Advanced Streamed Effects ────────────────────────────────
                elif eff == "meteor_shower":
                    segs = self._render_meteor_shower(t)
                elif eff == "juggle":
                    segs = self._render_harmonic_juggle(t)
                elif eff == "spiral_vortex":
                    segs = self._render_spiral_vortex(t)
                elif eff == "gravity_slosh":
                    segs = self._render_gravity_slosh(t)
                elif eff == "lissajous_orbit":
                    segs = self._render_lissajous_orbit(t)
                elif eff == "planar_wind":
                    segs = self._render_planar_wind(t)
                elif eff == "radar_sweep":
                    segs = self._render_radar_sweep(t)
                elif eff == "vaporwave_neon":
                    segs = self._render_vaporwave_neon(t)
                elif eff == "neon_heartbeat":
                    segs = self._render_anatomical_heartbeat(t)
                elif eff == "lantern_sweep":
                    segs = self._render_lantern_sweep(t)

                # ── Seasonal & Novelty Group Dispatching ─────────────────────
                elif eff == "candy_cane":
                    segs = self._render_candy_cane(t)
                elif eff == "haunted_mansion":
                    segs = self._render_haunted_mansion(t)
                elif eff == "police":
                    segs = self._render_police(t)

                # ── Creative Original Designs ────────────────────────────────
                elif eff in ("oil_slick", "liquid_iridescence"):
                    segs = self._render_oil_slick(t)
                elif eff == "silk_ribbons":
                    segs = self._render_silk_ribbons(t)
                elif eff == "nebula_bloom":
                    segs = self._render_nebula_bloom(t)
                elif eff in ("holographic_moire", "moire"):
                    segs = self._render_holographic_moire(t)
                elif eff in ("bioluminescent_tide", "pacifica"):
                    segs = self._render_bioluminescent_tide(t)
                elif eff in ("ember_drift", "embers_drift"):
                    segs = self._render_ember_drift(t)
                elif eff == "cyberpunk":
                    segs = self._render_cyberpunk(t)
                else:
                    segs = [[30, 60, 50]] * NUM_SEGMENTS

                # Enforce <= 2 updates/s limit (interval >= 0.50s)
                interval = max(0.50, interval)

                # Dynamic hardware adaptation: if controller throttled under AIMD or RTT latency, lengthen interval
                if hasattr(self._ctrl, "current_interval"):
                    interval = max(interval, float(self._ctrl.current_interval))
                elif hasattr(self._ctrl, "_current_interval") and self._ctrl._current_interval:
                    interval = max(interval, float(self._ctrl._current_interval))
                elif hasattr(self._ctrl, "frame_sender") and self._ctrl.frame_sender:
                    aimd_cap = getattr(self._ctrl.frame_sender, "_aimd_rate_cap", 2.0)
                    interval = max(interval, 1.0 / max(0.5, aimd_cap))

                trans_ms = max(500, int(round(interval * 1000)))

                # Early stale frame guard before CPU color correction
                if generation != self._effect_generation or stop_event.is_set():
                    break

                # Master brightness and gamma correction
                b = self._brightness
                master_ceiling = b / 100.0
                corrected = self._pipeline.correct_hsv_sequence(segs, master_ceiling=master_ceiling)

                # Stale frame guard right before publishing or submitting
                if generation != self._effect_generation or stop_event.is_set():
                    break

                frame_data = {
                    "segments": corrected,
                    "brightness": b,
                    "transition": trans_ms,
                    "_pre_corrected": True,
                }
                if self._frame_bus:
                    if self._output_token is None:
                        if stop_event.wait(0.1):
                            break
                        continue
                    token_generation, token_id = self._output_token
                    published = self._frame_bus.publish_frame(
                        self._dev_id, OutputProducer.EFFECT, frame_data,
                        generation=token_generation, producer_id=token_id,
                    )
                    if not published:
                        # Ownership/session changed; this stream must never retag itself.
                        if stop_event.wait(0.1):
                            break
                        continue
                elif hasattr(self._ctrl, "submit_frame"):
                    self._ctrl.submit_frame(frame_data)

                self._last_successful_frame = time.time()
                if isinstance(self._app_state, dict):
                    self._app_state["effect_status"] = "accepted"
                    self._app_state["last_error"] = None

                if stop_event.wait(interval):
                    break
            except Exception as e:
                logger.exception(f"[L930EffectsEngine] Exception in stream worker ({eff}): {e}")
                self._last_error = str(e)
                if isinstance(self._app_state, dict):
                    self._app_state["effect_status"] = "failed"
                    self._app_state["last_error"] = str(e)
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

        # 3. Randomly ignite new sparks near bottom/center (and maintain base ember warmth)
        if random.randint(0, 255) < sparking or max(self._heat) < 60.0:
            for _ in range(random.randint(1, 3)):
                y = random.randint(0, 4)
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

    def _effective_render_interval(self) -> float:
        """Best current estimate of physical send cadence, including AIMD protection."""
        interval = 0.50
        ctrl = self._ctrl
        if ctrl is not None:
            for attr in ("current_interval", "_current_interval"):
                try:
                    value = float(getattr(ctrl, attr, 0.0) or 0.0)
                except (TypeError, ValueError):
                    value = 0.0
                if value > 0.0:
                    interval = max(interval, value)
            sender = getattr(ctrl, "frame_sender", None)
            if sender is not None:
                try:
                    configured = float(getattr(sender, "max_updates_per_s", 2.0))
                    aimd = float(getattr(sender, "_aimd_rate_cap", configured))
                    effective_rate = max(0.5, min(configured, aimd))
                    interval = max(interval, 1.0 / effective_rate)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
        return max(0.50, interval)

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
        # Slow the full convergence/divergence cycle as the physical send rate falls.
        render_interval = self._effective_render_interval()
        cycle_period = max(3.2 / sp, 16.0 * render_interval)
        phase = (t % cycle_period) / cycle_period
        theta = 2.0 * math.pi * phase

        # Non-linear spring/elastic shaping: accelerates toward center, decelerates at ends
        u = 0.5 + 0.5 * math.cos(theta)
        s = u ** 0.82
        pos1 = 24.5 - 24.0 * s   # Left Head: 0.5 -> 24.5 -> 0.5
        pos2 = 24.5 + 24.0 * s   # Right Head: 48.5 -> 24.5 -> 48.5
        v_dir = -math.sin(theta)  # > 0: converging inward; < 0: diverging outward

        # Head 3: Asynchronous harmonic cross-oscillator
        pos3 = 24.5 + 16.0 * math.sin(t * 0.95 * sp + 1.2)

        # Broaden the center bloom so it persists across sampled frames.
        dist_between = pos2 - pos1
        tail_mult = max(0.2, getattr(self, "_tail_length", 1.0))
        collision_radius = 7.5 + 1.5 * tail_mult
        collision_factor = (1.0 - _smoothstep(0.0, collision_radius, dist_between)) ** 2.0
        inward_weight = _smoothstep(-0.35, 0.35, v_dir)

        segs = []
        for i in range(NUM_SEGMENTS):
            # Dynamic aerodynamic cometary tails scaled by tail_length
            d1 = i - pos1
            d2 = i - pos2
            d3 = abs(i - pos3)

            # Blend tail direction through each reversal to remove a hard snap.
            tail_len = 3.8 * tail_mult
            short_sigma = 1.8
            outer_sigma = short_sigma + (tail_len - short_sigma) * inward_weight
            inner_sigma = short_sigma + (tail_len - short_sigma) * (1.0 - inward_weight)
            sigma1 = outer_sigma if d1 <= 0.0 else inner_sigma
            sigma2 = outer_sigma if d2 >= 0.0 else inner_sigma

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

            # Soft, bounded collision bloom (not a single sampled flash).
            flash_mult = max(0.2, min(1.6, getattr(self, "_flash_strength", 1.0)))
            if collision_factor > 0.0:
                center_dist = abs(i - 24.5)
                impact_bloom = collision_factor * math.exp(-0.5 * (center_dist / 3.0) ** 2) * flash_mult * 0.70
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
        """
        Rhythmic Cardiac Glow: Continuous resting cardiovascular wave with smooth
        systolic compression and diastolic vascular relaxation expanding outward.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        c_lub = pal[0]
        c_dub = pal[1] if len(pal) > 1 else (c_lub[0], max(10, c_lub[1] - 25), c_lub[2])

        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        cycle_period = max(3.4 / sp, 6.0 * interval)
        phase = (t % cycle_period) / cycle_period

        # Smooth double-pulse cardiovascular envelope with resting diastole
        lub_env = math.exp(-0.5 * ((phase - 0.12) / 0.08) ** 2) if phase < 0.28 else 0.0
        dub_env = math.exp(-0.5 * ((phase - 0.35) / 0.10) ** 2) if 0.18 < phase < 0.60 else 0.0

        fs = max(0.2, min(3.0, getattr(self, "_flash_strength", 1.0)))
        segs = []
        half = 24.5
        for i in range(NUM_SEGMENTS):
            norm_dist = abs(i - half) / half
            prop_lub = math.exp(-0.5 * ((norm_dist - phase * 1.4) / 0.28) ** 2) * lub_env
            prop_dub = math.exp(-0.5 * ((norm_dist - (phase - 0.18) * 1.4) / 0.32) ** 2) * dub_env

            pulse = (prop_lub * 1.1 + prop_dub * 0.85) * fs
            base_b = 8
            total_b = int(max(base_b, min(100, base_b + pulse * 82.0)))

            mix = prop_dub / (prop_lub + prop_dub + 1e-4)
            h = int((c_lub[0] * (1.0 - mix) + c_dub[0] * mix) % 360)
            s = int(c_lub[1] * (1.0 - mix) + c_dub[1] * mix)
            segs.append([h, s, total_b])
        return segs

    def _render_standing_wave_golden_hour(self, t: float) -> List[List[int]]:
        """Standing Wave Horizon: Superposition of opposing waves with twilight dusk progression variation."""
        pal_name = self._palette_name if self._palette_name in PALETTES else "sunset"
        pal = get_palette_hsv(pal_name)
        from src.visual_styles import sample_palette_oklab
        segs = []
        sp = self._speed
        # Twilight horizon cycle progression for dusk variation (slow 240s non-repeating cycle)
        if pal_name == "dusk":
            cycle_period = 240.0 / max(0.2, sp)
            progress = (t % cycle_period) / cycle_period
            for i in range(NUM_SEGMENTS):
                x = i / 49.0
                standing = (math.sin(x * 2.5 * math.pi) * 0.15)
                h, s, _ = sample_palette_oklab(pal, (progress + standing) % 1.0, cyclic=True)
                segs.append([h, s, int(max(20, min(100, 75 * (1.0 - 0.2 * abs(x - 0.5)))))])
            return segs

        for i in range(NUM_SEGMENTS):
            x = i / 49.0
            wave = math.sin(x * 3.0 * math.pi - t * 0.8 * sp) + math.cos(x * 5.0 * math.pi + t * 0.55 * sp)
            norm_wave = (wave + 2.0) / 4.0
            h, s, _ = sample_palette_oklab(pal, norm_wave)
            b = int(max(30, min(100, 50 + norm_wave * 50)))
            segs.append([h, s, b])
        return segs

    def _render_standing_wave_dusk(self, t: float) -> List[List[int]]:
        """Dusk variation (absorbed into golden_hour engine with dusk palette)."""
        old_pal = self._palette_name
        self._palette_name = "dusk"
        try:
            return self._render_standing_wave_golden_hour(t)
        finally:
            self._palette_name = old_pal

    def _render_autonomous_starfield(self, t: float) -> List[List[int]]:
        """50 Autonomous IC Agents: Starfield with configurable particle density and glitter cascade pops."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        bg_h, bg_s = pal[0][0], pal[0][1]
        star_h, star_s = pal[1][:2] if len(pal) > 1 else (200, 30)
        segs = []
        sp = self._speed
        density_mult = max(0.2, getattr(self, "_particle_density", 1.0))
        flash_mult = max(0.2, getattr(self, "_flash_strength", 1.0))
        # Threshold: density scales star frequency; flash scales high-luminance pops
        threshold = max(0.60, 0.92 - 0.12 * density_mult)
        for i in range(NUM_SEGMENTS):
            osc = math.sin(t * (1.2 + (i % 7) * 0.35) * sp + i * 17.3)
            if osc > threshold:
                twinkle = (osc - threshold) / (1.0 - threshold)
                if flash_mult > 1.2 and osc > (threshold + (1.0 - threshold) * 0.7):
                    # High-luminance micro-sparkle / glitter pop
                    h = star_h
                    s = int(star_s * 0.25)
                    b = 100
                else:
                    h = star_h
                    s = star_s
                    b = int(max(15, min(100, 20 + twinkle * 80)))
                segs.append([h, s, b])
            else:
                segs.append([bg_h, bg_s, 12])
        return segs

    def _render_autonomous_embers(self, t: float) -> List[List[int]]:
        """Autonomous warm glowing embers with per-IC random flicker consuming particle density."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "ember")
        dens = max(0.2, min(3.0, getattr(self, "_particle_density", 1.0)))
        segs = []
        sp = self._speed
        for i in range(NUM_SEGMENTS):
            flicker = math.sin(t * (1.8 + (i % 5) * 0.4) * sp + i * 23.9)
            norm = max(0.0, min(1.0, (flicker + 1.0) * 0.5 * math.sqrt(dens)))
            from src.visual_styles import sample_palette_oklab
            h, s, _ = sample_palette_oklab(pal, norm * 0.4)
            b = int(max(4, min(100, (12 + norm * 30) * min(1.5, math.sqrt(dens)))))
            segs.append([h, s, b])
        return segs

    def _render_multi_pod_comet(self, t: float) -> List[List[int]]:
        """Multi-Pod Comets: 2 comets gliding and crossing with cadence-adapted harmonic motion and exponential tails."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        tail_mult = max(0.2, getattr(self, "_tail_length", 1.0))
        decay_sigma = 4.5 * tail_mult

        period_a = max(6.5 / sp, 12.0 * interval)
        period_b = max(9.0 / sp, 16.0 * interval)
        pos_a = 24.5 + 22.0 * math.sin((t / period_a) * 2.0 * math.pi)
        pos_b = 24.5 - 22.0 * math.sin((t / period_b) * 2.0 * math.pi)

        segs = []
        for i in range(NUM_SEGMENTS):
            dist_a = abs(i - pos_a)
            dist_b = abs(i - pos_b)
            tail_a = math.exp(-dist_a / decay_sigma)
            tail_b = math.exp(-dist_b / decay_sigma)
            total = min(1.0, tail_a + tail_b)
            h, s, _ = sample_palette_oklab(pal, total)
            b = int(max(6, min(100, 8 + total * 92)))
            segs.append([h, s, b])
        return segs

    def _render_multi_pod_sonar(self, t: float) -> List[List[int]]:
        """Sonar sweep variation (absorbed into radar_sweep engine with tail multiplier)."""
        old_t = getattr(self, "_tail_length", 1.0)
        self._tail_length = old_t * 1.8
        try:
            return self._render_radar_sweep(t)
        finally:
            self._tail_length = old_t

    def _render_harmonic_juggle(self, t: float) -> List[List[int]]:
        """
        Harmonic Juggle: 4 broad glowing orbs weaving in and out of phase
        with true OKLab additive chromatic blending and smooth spatial envelopes.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()

        # 4 harmonic orbs with slow prime periods
        periods = [
            max(8.0 / sp, 14.0 * interval),
            max(11.0 / sp, 18.0 * interval),
            max(14.0 / sp, 22.0 * interval),
            max(17.0 / sp, 26.0 * interval),
        ]
        orb_data = []
        for k in range(4):
            phase = (t / periods[k] + k * 0.25) * 2.0 * math.pi
            pos = 24.5 + 22.0 * math.sin(phase)
            norm_k = (k / 4.0 + t * 0.03 * sp) % 1.0
            h, s, _ = sample_palette_oklab(pal, norm_k, cyclic=True)
            orb_data.append((pos, h, s, norm_k))

        segs: List[List[int]] = []
        for i in range(NUM_SEGMENTS):
            total_weight = 0.0
            weighted_norm = 0.0
            for pos, _, _, norm_k in orb_data:
                dist = abs(i - pos)
                weight = math.exp(-0.5 * (dist / 4.5) ** 2)
                if weight > 0.02:
                    total_weight += weight
                    weighted_norm += norm_k * weight

            if total_weight > 0.02:
                avg_norm = (weighted_norm / total_weight) % 1.0
                h, s, _ = sample_palette_oklab(pal, avg_norm, cyclic=True)
                v = int(max(10, min(100, 12 + total_weight * 72.0)))
            else:
                h, s = pal[0][0], pal[0][1]
                v = 10
            segs.append([h, s, v])
        return segs

    def _render_sinelon_sweep(self, t: float) -> List[List[int]]:
        """
        FastLED Sinelon (adapted for L930 50 ICs):
        A sweeping beacon gliding harmonically back and forth, leaving an exponential
        phosphorescent decay trail paced for hardware cadence.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "dusk")
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        period = max(7.0 / sp, 14.0 * interval)
        phase = (t / period) * 2.0 * math.pi
        pos = 24.5 + 22.0 * math.sin(phase)
        vel = math.cos(phase)

        norm_t = (t * 0.05 * sp) % 1.0
        beacon_h, beacon_s, _ = sample_palette_oklab(pal, norm_t, cyclic=True)

        segs = []
        tl = max(0.2, min(3.0, getattr(self, "_tail_length", 1.0)))
        for i in range(NUM_SEGMENTS):
            dist = abs(i - pos)
            head_glow = math.exp(-0.5 * (dist / 3.0) ** 2)
            trailing_offset = (pos - i) if vel > 0 else (i - pos)
            if trailing_offset > 0:
                trail_glow = math.exp(-trailing_offset / (7.0 * tl)) * 0.65
            else:
                trail_glow = 0.0

            intensity = min(1.0, head_glow + trail_glow)
            v = int(max(8, min(100, 8 + intensity * 92.0)))
            if head_glow < 0.4 and intensity > 0.08:
                tail_h, tail_s, _ = sample_palette_oklab(pal, (norm_t + 0.25) % 1.0, cyclic=True)
                segs.append([tail_h, tail_s, v])
            else:
                segs.append([beacon_h, beacon_s, v])

        return segs

    def _render_confetti_burst(self, t: float) -> List[List[int]]:
        """Confetti burst variation (absorbed into prism_sparks particle engine with elevated density)."""
        old_d = getattr(self, "_particle_density", 1.0)
        self._particle_density = old_d * 1.8
        try:
            return self._render_prism_sparks(t)
        finally:
            self._particle_density = old_d

    def _render_meteor_shower(self, t: float) -> List[List[int]]:
        """Three staggered meteor heads cross the strip with smooth cadence-paced drift and long luminous tails."""
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        tail_mult = max(0.2, getattr(self, "_tail_length", 1.0))

        travel_span = NUM_SEGMENTS + 20.0
        period_a = max(12.0 / sp, (travel_span * interval) / 2.2)
        period_b = max(16.0 / sp, (travel_span * interval) / 1.8)
        period_c = max(20.0 / sp, (travel_span * interval) / 1.5)

        pos_a = ((t / period_a) % 1.0) * travel_span - 10.0
        pos_b = (((t / period_b) + 0.38) % 1.0) * travel_span - 10.0
        pos_c = (((t / period_c) + 0.72) % 1.0) * travel_span - 10.0

        meteors = [
            (pos_a, 1.0, 16.0 * tail_mult, 2.8),
            (pos_b, 0.78, 20.0 * tail_mult, 3.2),
            (pos_c, 0.60, 14.0 * tail_mult, 2.5),
        ]
        segs: List[List[int]] = []
        for i in range(NUM_SEGMENTS):
            peak, tail_pos = 0.0, 0.0
            for head, gain, tail_len, core_r in meteors:
                dist = abs(i - head)
                core_glow = gain * math.exp(-0.5 * (dist / core_r) ** 2)
                if core_glow > peak:
                    peak = core_glow
                    tail_pos = 0.0

                behind = head - i
                if 0.0 < behind <= tail_len:
                    tail_glow = gain * math.exp(-behind / max(2.5, tail_len * 0.40)) * 0.85
                    if tail_glow > peak:
                        peak = tail_glow
                        tail_pos = behind / tail_len

            ambient_glow = 0.08 + 0.04 * math.sin(i * 0.3 + t * 0.2)
            total_intensity = min(1.0, ambient_glow + peak)

            hue, sat, _ = sample_palette_oklab(pal, min(1.0, 0.10 + tail_pos * 0.90), cyclic=False)
            white_mix = max(0.0, 1.0 - tail_pos * 2.5) * (peak ** 1.5)
            hue = int((hue * (1.0 - white_mix) + 195 * white_mix) % 360)
            sat = int(sat * (1.0 - white_mix) + 20 * white_mix)
            value = int(max(8, min(100, 8 + 92 * total_intensity)))
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
        Hypnotic Spiral Vortex: Smooth continuous logarithmic spiral wave
        flowing inward with seamless OKLab gradient advection and zero angular phase jumps.
        """
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()

        period = max(11.0 / sp, 18.0 * interval)
        rot_phase = (t / period) % 1.0

        segs = []
        for i in range(NUM_SEGMENTS):
            norm_r = abs(i - 24.5) / 24.5
            spiral_phase = (norm_r * 2.2 - rot_phase) % 1.0
            wave = 0.5 + 0.5 * math.cos(spiral_phase * 2.0 * math.pi)

            h, s, _ = sample_palette_oklab(pal, (norm_r * 0.6 + rot_phase * 0.4) % 1.0, cyclic=True)
            core_intensity = 0.35 + 0.65 * (wave ** 1.4)
            v = int(max(15, min(100, 15 + core_intensity * 75 * (1.0 - 0.25 * norm_r))))
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
        """Deliberate inhale/exhale envelope with slow relaxing color-temperature shift modulated by selected palette."""
        sp = max(0.2, self._speed)
        # 10 second respiratory cycle: 4s inhale, 1s hold, 5s exhale
        cycle = 10.0 / sp
        phase = (t % cycle) / cycle
        if phase < 0.40:
            p = phase / 0.40
            env = 0.5 - 0.5 * math.cos(p * math.pi)
        elif phase < 0.50:
            env = 1.0
        else:
            p = (phase - 0.50) / 0.50
            env = 0.5 + 0.5 * math.cos(p * math.pi)

        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        c0 = pal[0]
        c1 = pal[1] if len(pal) > 1 else (c0[0], max(10, c0[1] - 30), c0[2])

        h = int((c0[0] * (1.0 - env) + c1[0] * env) % 360)
        s = int(c0[1] * (1.0 - env * 0.3) + c1[1] * (env * 0.3))
        v = int(max(6, min(100, 10 + env * 85)))
        return [[h, s, v]] * NUM_SEGMENTS

    def _render_fireflies(self, t: float) -> List[List[int]]:
        """Loose clusters of green-gold lights with asynchronous bloom, short peak, and long fade consuming particle density."""
        sp = self._speed
        dens = max(0.2, min(3.0, getattr(self, "_particle_density", 1.0)))
        segs = []
        # Two wandering swarm cluster centers
        c1 = 16.0 + 10.0 * math.sin(t * 0.35 * sp)
        c2 = 34.0 + 11.0 * math.cos(t * 0.28 * sp + 1.5)
        thresh = max(0.40, min(0.90, 0.82 - 0.12 * math.sqrt(dens)))
        min_cluster = max(0.04, 0.15 / math.sqrt(dens))
        for i in range(NUM_SEGMENTS):
            dist1 = abs(i - c1)
            dist2 = abs(i - c2)
            cluster_prob = math.exp(-0.5 * (dist1 / 5.5) ** 2) + math.exp(-0.5 * (dist2 / 5.5) ** 2)

            # Independent non-synchronous oscillator per IC
            f = 0.8 + (i * 17 % 13) * 0.12 * sp
            phase = i * 23.7
            osc = math.sin(t * f + phase)
            if osc > thresh and cluster_prob > min_cluster:
                bloom = (osc - thresh) / (1.0 - thresh)
                h = int(82 + (i % 5) * 8)
                s = 92
                v = int(max(8, min(100, 15 + bloom * 80 * min(1.0, cluster_prob * math.sqrt(dens)))))
            else:
                h, s, v = 110, 85, 2
            segs.append([h, s, v])
        return segs

    def _render_prism_sparks(self, t: float) -> List[List[int]]:
        """Prism Sparks with particle density scaling and confetti burst dynamics."""
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        from src.visual_styles import sample_palette_oklab
        sp = self._speed
        density_mult = max(0.2, getattr(self, "_particle_density", 1.0))
        threshold = max(0.55, 0.94 - 0.08 * density_mult)
        segs = []
        is_burst = density_mult > 1.5

        for i in range(NUM_SEGMENTS):
            f = 1.2 + (i * 19 % 17) * 0.18 * sp
            phase = i * 31.415
            osc = math.sin(t * f + phase)
            if osc > threshold:
                spark = (osc - threshold) / (1.0 - threshold)
                if is_burst:
                    norm_hue = ((i * 37 % 100) / 100.0 + t * 0.08 * sp) % 1.0
                    h, s, _ = sample_palette_oklab(pal, norm_hue, cyclic=True)
                else:
                    h = int((i * 67 + t * 45 * sp) % 360)
                    s = 100
                v = int(max(20, min(100, spark * 100)))
                segs.append([h, s, v])
            else:
                if is_burst:
                    amb_pos = (i / 49.0 + t * 0.03 * sp) % 1.0
                    h, s, _ = sample_palette_oklab(pal, amb_pos, cyclic=True)
                    v = int(max(5, min(18, 12 + osc * 5)))
                    segs.append([h, s, v])
                else:
                    segs.append([0, 0, 0])
        return segs

    def _render_vaporwave_neon(self, t: float) -> List[List[int]]:
        """
        Synthwave Neon Horizons: Continuous trigonometric OKLab blending between
        electric cyan, neon magenta, and deep violet bands with smooth antialiased dark valleys.
        """
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        period = max(14.0 / sp, 22.0 * interval)
        scan = (t / period) % 1.0

        neon_pal = [(315, 100, 95), (185, 100, 100), (275, 100, 90)]
        segs = []
        for i in range(NUM_SEGMENTS):
            norm_pos = (i / float(NUM_SEGMENTS - 1) - scan) % 1.0
            wave = 0.5 + 0.5 * math.sin(norm_pos * 3.0 * 2.0 * math.pi)
            h, s, _ = sample_palette_oklab(neon_pal, norm_pos, cyclic=True)
            v = int(max(10, min(100, 12 + (wave ** 1.6) * 88)))
            segs.append([h, s, v])
        return segs

    def _render_lantern_sweep(self, t: float) -> List[List[int]]:
        """
        Warm Lantern Sweep: Gentle harmonic lantern swaying with a broad warm
        amber core, golden halo, and graceful cadence-adapted motion.
        """
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        tl = max(0.4, min(2.5, getattr(self, "_tail_length", 1.0)))

        period = max(8.0 / sp, 15.0 * interval)
        pos = 24.5 + 21.0 * math.sin((t / period) * 2.0 * math.pi)

        segs = []
        for i in range(NUM_SEGMENTS):
            dist = abs(i - pos)
            core = math.exp(-0.5 * (dist / 3.5) ** 2)
            halo = math.exp(-0.5 * (dist / (10.0 * tl)) ** 2) * 0.60
            intensity = min(1.0, core * 0.85 + halo * 0.45)

            h = int(30 + (1.0 - core) * 12)
            s = int(82 + core * 18)
            v = int(max(10, min(100, 12 + intensity * 88)))
            segs.append([h, s, v])
        return segs

    def _render_aurora(self, t: float) -> List[List[int]]:
        """Broad aurora curtains blended continuously through emerald, teal, and violet in OKLab space."""
        from src.visual_styles import sample_palette_oklab

        sp = max(0.2, self._speed)
        ww = max(0.3, min(3.0, getattr(self, "_wave_width", 1.0)))
        aurora_palette = [
            (140, 95, 88),  # Vibrant Emerald
            (165, 92, 92),  # Luminous Mint
            (185, 90, 90),  # Turquoise/Cyan
            (235, 85, 85),  # Deep Celestial Blue
            (275, 88, 85),  # Ethereal Violet
        ]
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            # Overlapping atmospheric curtain ribbons with wave width scaling
            c1 = math.sin(x * (2.2 / ww) * math.pi + t * 0.25 * sp)
            c2 = math.cos(x * (3.1 / ww) * math.pi - t * 0.18 * sp + 1.2)
            c3 = math.sin(x * (1.5 / ww) * math.pi + t * 0.32 * sp + 2.4)

            # Continuous normalized curtain position in [0.0, 1.0]
            curtain_pos = 0.5 + 0.32 * c1 + 0.18 * c2
            curtain_pos = max(0.0, min(1.0, curtain_pos))

            h, s, _ = sample_palette_oklab(aurora_palette, curtain_pos, cyclic=False)
            intensity = 0.5 + 0.5 * c3
            val = int(max(15, min(92, 22 + intensity * 68)))
            segs.append([h, s, val])
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
        """Slow multi-direction droplets with soft cores and long, coherent fading wakes."""
        sp = max(0.2, self._speed)
        dens = max(0.2, min(3.0, getattr(self, "_particle_density", 1.0)))
        interval = self._effective_render_interval()
        tail_len = 5.5 + 0.6 * dens
        travel_span = NUM_SEGMENTS + 2.0 * tail_len
        base = [212, 88, 3]
        out = [list(base) for _ in range(NUM_SEGMENTS)]
        drops = [
            (0.03, 10.0, 0.92, 1),
            (0.19, 12.2, 0.76, -1),
            (0.37, 9.8, 0.84, 1),
            (0.54, 13.0, 0.67, -1),
            (0.72, 11.1, 0.81, 1),
            (0.88, 14.0, 0.90, -1),
        ]
        count = max(1, min(len(drops), int(round(4.0 * dens))))
        for phase, nominal_period, strength, direction in drops[:count]:
            # Cap motion to roughly four zones per physical update at the current AIMD rate.
            minimum_period = travel_span * interval / 4.2
            period = max(nominal_period / sp, minimum_period)
            progress = ((t / period) + phase) % 1.0
            if direction > 0:
                head = progress * travel_span - tail_len
            else:
                head = (1.0 - progress) * travel_span - tail_len

            for i in range(NUM_SEGMENTS):
                behind = head - i if direction > 0 else i - head
                core = math.exp(-0.5 * (behind / 1.15) ** 2)
                if behind >= 0.0:
                    trail = math.exp(-2.5 * behind / tail_len) * (1.0 - _smoothstep(0.72, 1.0, behind / tail_len))
                elif behind > -1.8:
                    trail = 0.12 * math.exp(-0.5 * (behind / 1.15) ** 2)
                else:
                    trail = 0.0
                intensity = strength * max(core, trail)
                val = int(max(out[i][2], min(82, 3 + 74 * intensity)))
                hue = int(190 + 16 * max(0.0, min(1.0, 1.0 - max(0.0, behind) / tail_len)))
                sat = int(max(58, min(92, 86 - 18 * max(0.0, behind) / tail_len)))
                if val > out[i][2]:
                    out[i] = [hue, sat, val]
        return out

    def _render_lightning(self, t: float) -> List[List[int]]:
        """
        Atmospheric Thunderstorm: Continuous dark ambient storm front with rolling
        electric sheet lightning blooming smoothly over 1.0-1.5s and trailing warm amber thunder roll.
        """
        sp = max(0.2, self._speed)
        sub_t = (t * sp) % 7.0

        segs = []
        for i in range(NUM_SEGMENTS):
            cloud = 0.5 + 0.5 * math.sin(i * 0.2 + t * 0.15 * sp)
            segs.append([230, 90, int(6 + cloud * 8)])

        flash_mult = max(0.3, min(2.5, getattr(self, "_flash_strength", 1.0)))

        # Sheet lightning episode: 1.0s to 3.6s
        if 1.0 <= sub_t <= 2.2:
            prog = (sub_t - 1.0) / 1.2
            envelope = math.sin(prog * math.pi) * flash_mult
            for i in range(10, 40):
                local_f = envelope * (1.0 - abs(i - 25.0) / 16.0)
                if local_f > 0:
                    segs[i] = [205, int(max(8, 38 - local_f * 30)), int(max(segs[i][2], min(100, 15 + local_f * 85)))]
        elif 2.4 <= sub_t <= 3.6:
            prog = (sub_t - 2.4) / 1.2
            envelope = (math.sin(prog * math.pi) ** 1.3) * flash_mult
            for i in range(NUM_SEGMENTS):
                local_f = envelope * (0.6 + 0.4 * math.sin(i * 0.35))
                segs[i] = [210, int(max(5, 35 - local_f * 30)), int(max(segs[i][2], min(100, 12 + local_f * 88)))]

        # Coordinated amber thunder roll rumble following strike episode (4.2s to 5.8s)
        if 4.2 <= sub_t <= 5.8:
            roll_prog = (sub_t - 4.2) / 1.6
            rumble = math.sin(roll_prog * math.pi) * 0.38 * min(1.5, flash_mult)
            for i in range(NUM_SEGMENTS):
                segs[i] = [28, 95, int(max(segs[i][2], min(45, 6 + rumble * 36)))]

        return segs

    def _render_police(self, t: float) -> List[List[int]]:
        """Slow alternating red/blue siren pulses with eased envelopes, not a strobe."""
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        period = max(4.0 / sp, 3.5 * interval, 3.4)
        phase = (t / period) % 1.0
        red_envelope = 0.0
        blue_envelope = 0.0

        if phase < 0.5:
            local = phase * 2.0
            red_envelope = _smoothstep(0.0, 0.24, local) * (1.0 - _smoothstep(0.76, 1.0, local))
        else:
            local = (phase - 0.5) * 2.0
            blue_envelope = _smoothstep(0.0, 0.24, local) * (1.0 - _smoothstep(0.76, 1.0, local))

        half = NUM_SEGMENTS // 2
        segs = []
        red_val = int(7 + 86 * red_envelope)
        blue_val = int(7 + 86 * blue_envelope)
        for i in range(NUM_SEGMENTS):
            if i < half:
                segs.append([0, 100, red_val])
            else:
                segs.append([240, 100, blue_val])
        return segs

    def _render_candy_cane(self, t: float) -> List[List[int]]:
        """Slow red and warm-cream bands with soft interpolated boundaries."""
        from src.pipeline import tapo_hsv_to_rgb, rgb_to_tapo_hsv

        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        band_width = 7.0
        period = band_width * 2.0
        # Keep motion legible without letting each frame skip a whole band edge.
        zones_per_update = 3.2
        minimum_period = period * interval / zones_per_update
        travel_period = max(9.0 / sp, minimum_period)
        offset = (t / travel_period) * NUM_SEGMENTS

        red_rgb = tapo_hsv_to_rgb(355, 92, 95)
        cream_rgb = tapo_hsv_to_rgb(38, 18, 92)

        segs = []
        for i in range(NUM_SEGMENTS):
            pos = (i - offset) % period
            if pos < 1.5:
                blend = _smoothstep(0.0, 3.0, pos + 1.5)
                rgb = tuple(cream_rgb[c] * (1.0 - blend) + red_rgb[c] * blend for c in range(3))
            elif pos > period - 1.5:
                blend = _smoothstep(period - 1.5, period + 1.5, pos)
                rgb = tuple(cream_rgb[c] * (1.0 - blend) + red_rgb[c] * blend for c in range(3))
            elif abs(pos - band_width) <= 1.5:
                blend = _smoothstep(band_width - 1.5, band_width + 1.5, pos)
                rgb = tuple(red_rgb[c] * (1.0 - blend) + cream_rgb[c] * blend for c in range(3))
            elif pos < band_width:
                rgb = red_rgb
            else:
                rgb = cream_rgb
            h, sat, val = rgb_to_tapo_hsv(*rgb)
            segs.append([h, sat, val])
        return segs

    def _render_haunted_mansion(self, t: float) -> List[List[int]]:
        """Near-black with gradual, localized emerald and violet glows; never a full-strip flash."""
        from src.pipeline import tapo_hsv_to_rgb, rgb_to_tapo_hsv

        sp = max(0.2, self._speed)
        base_rgb = tapo_hsv_to_rgb(270, 90, 2)
        emerald_rgb = tapo_hsv_to_rgb(137, 95, 100)
        violet_rgb = tapo_hsv_to_rgb(282, 92, 100)

        center_emerald_a = 7.0 + 4.5 * math.sin(t * 0.10 * sp + 0.4)
        center_emerald_b = 34.0 + 5.5 * math.sin(t * 0.08 * sp + 1.7)
        center_violet = 23.5 + 12.0 * math.sin(t * 0.09 * sp + 2.1)

        # Long release/attack curves keep the atmosphere calm across 0.5–1 Hz sends.
        env_a = 0.12 + 0.88 * (0.5 + 0.5 * math.sin(t * 0.18 * sp + 0.6))
        env_b = 0.10 + 0.90 * (0.5 + 0.5 * math.sin(t * 0.14 * sp + 2.0))
        env_v = 0.10 + 0.90 * (0.5 + 0.5 * math.sin(t * 0.12 * sp + 3.2))

        segs = []
        for i in range(NUM_SEGMENTS):
            green_a = 0.46 * env_a * math.exp(-0.5 * ((i - center_emerald_a) / 3.8) ** 2)
            green_b = 0.38 * env_b * math.exp(-0.5 * ((i - center_emerald_b) / 4.5) ** 2)
            violet = 0.43 * env_v * math.exp(-0.5 * ((i - center_violet) / 4.0) ** 2)
            rgb = tuple(
                min(1.0, base_rgb[c] + emerald_rgb[c] * (green_a + green_b) + violet_rgb[c] * violet)
                for c in range(3)
            )
            h, sat, val = rgb_to_tapo_hsv(*rgb)
            segs.append([h, sat, max(1, min(64, val))])
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
        """
        Viscous U-tube fluid dynamics: Gentle liquid rocking with smooth
        continuous meniscus curvature, surface tension, and zero boundary clipping.
        """
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "tide")
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()

        period = max(9.0 / sp, 16.0 * interval)
        theta = (t / period) * 2.0 * math.pi
        slosh = math.sin(theta)

        segs = []
        ww = max(0.4, min(2.5, getattr(self, "_wave_width", 1.0)))
        for i in range(NUM_SEGMENTS):
            norm_x = (i - 24.5) / 24.5
            surface_height = slosh * norm_x * 0.65 - 0.15 * (1.0 - norm_x ** 2)
            submerged = 1.0 / (1.0 + math.exp(-surface_height / (0.35 * ww)))
            meniscus_factor = math.exp(-0.5 * (surface_height / (0.22 * ww)) ** 2)

            h, s, _ = sample_palette_oklab(pal, submerged * 0.75 + meniscus_factor * 0.25, cyclic=False)
            v = int(max(12, min(100, 15 + submerged * 55 + meniscus_factor * 30)))
            segs.append([h, s, v])
        return segs

    def _render_lissajous_orbit(self, t: float) -> List[List[int]]:
        """
        Harmonic Lissajous Orbit: 2D celestial orbit with a broad Euclidean
        gravity well and trailing ether wake, paced for hardware cadence.
        """
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        topo = get_l930_topology()

        t_a = t / max(13.0 / sp, 22.0 * interval)
        t_b = t / max(19.0 / sp, 30.0 * interval)
        px = 0.75 * math.sin(t_a * 2.0 * math.pi)
        py = 0.65 * math.cos(t_b * 2.0 * math.pi + 0.5)

        segs = []
        for i in range(NUM_SEGMENTS):
            x, y = topo.coords[i]
            d = math.sqrt((x - px) ** 2 + (y - py) ** 2)
            glow = math.exp(-0.5 * (d / 0.95) ** 2)
            h, s, _ = sample_palette_oklab(pal, (d * 0.4 + t * 0.04 * sp) % 1.0, cyclic=True)
            v = int(max(12, min(100, 12 + glow * 88)))
            segs.append([h, s, v])
        return segs

    def _render_planar_wind(self, t: float) -> List[List[int]]:
        """
        Atmospheric Planar Wind: Broad atmospheric breeze advecting across
        room space with gentle envelope progression and lush foliage/sage tones.
        """
        from src.visual_styles import sample_palette_oklab
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "forest")
        sp = max(0.2, self._speed)
        interval = self._effective_render_interval()
        topo = get_l930_topology()
        proj = topo.directional_projection(angle_deg=45.0)

        period = max(13.0 / sp, 22.0 * interval)
        phase = (t / period) % 1.0
        ww = max(0.5, min(2.5, getattr(self, "_wave_width", 1.0)))

        segs = []
        for i in range(NUM_SEGMENTS):
            p = proj[i]
            wave = 0.5 + 0.5 * math.sin((p - phase) * (1.2 / ww) * 2.0 * math.pi)
            subtle = 0.15 * math.sin((p * 2.5 + phase * 1.5) * math.pi)
            intensity = min(1.0, wave ** 1.3 + subtle)

            h, s, _ = sample_palette_oklab(pal, (p * 0.5 + phase * 0.5) % 1.0, cyclic=True)
            v = int(max(15, min(100, 18 + intensity * 78)))
            segs.append([h, s, v])
        return segs

    def _render_radar_sweep(self, t: float) -> List[List[int]]:
        """
        Phosphor Radar Sweep: Continuous sweeping beam with broad Gaussian
        beam profile and lingering phosphor persistence across physical frames.
        """
        sp = max(0.2, self._speed)
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "forest")
        interval = self._effective_render_interval()
        tail_mult = max(0.2, getattr(self, "_tail_length", 1.0))
        topo = get_l930_topology()
        angles = topo.polar_projection(center_x=0.0, center_y=0.0)

        period = max(8.5 / sp, 15.0 * interval)
        beam_angle = (t / period) % 1.0

        segs = []
        head_h = pal[0][0] if pal else 142
        trail_window = min(0.92, 0.55 * tail_mult)
        decay_rate = 0.20 * tail_mult

        for i in range(NUM_SEGMENTS):
            phi = angles[i]
            diff = (phi - beam_angle) % 1.0
            if diff < trail_window:
                decay = math.exp(-diff / decay_rate)
                h = head_h
                s = int(max(30, 95 - decay * 55))
                v = int(max(8, min(100, 8 + decay * 92)))
            else:
                h, s, v = head_h, 85, 8
            segs.append([h, s, v])
        return segs

    # ── FastLED Ports & Strips Effects ────────────────────────────────────────

    def _render_glitter_cascade(self, t: float) -> List[List[int]]:
        """Glitter cascade variation (absorbed into starfield with elevated density and flash)."""
        old_d = getattr(self, "_particle_density", 1.0)
        old_f = getattr(self, "_flash_strength", 1.0)
        self._particle_density = old_d * 1.8
        self._flash_strength = old_f * 1.5
        try:
            return self._render_autonomous_starfield(t)
        finally:
            self._particle_density = old_d
            self._flash_strength = old_f

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

        ww = max(0.3, min(3.0, getattr(self, "_wave_width", 1.0)))
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            wave = math.sin(x * (3.0 / ww) * math.pi + b1) * 0.35 + \
                   math.cos(x * (5.0 / ww) * math.pi + b2) * 0.25 + \
                   math.sin(x * (7.0 / ww) * math.pi + b3) * 0.20 + \
                   math.cos(x * (2.0 / ww) * math.pi + b4) * 0.20

            norm_w = (wave + 1.0) * 0.5
            h, s, _ = sample_palette_oklab(pal, norm_w, cyclic=True)
            v = int(max(12, min(100, 20 + norm_w * 80)))
            segs.append([h, s, v])
        return segs

    def _render_coordinated_lightning(self, t: float) -> List[List[int]]:
        """Coordinated storm variation (absorbed into lightning engine with flash multiplier)."""
        old_f = getattr(self, "_flash_strength", 1.0)
        self._flash_strength = old_f * 1.8
        try:
            return self._render_lightning(t)
        finally:
            self._flash_strength = old_f

    # ── Creative Original Designs (Cadence-Aware Procedural Fields) ──────────

    def _render_oil_slick(self, t: float) -> List[List[int]]:
        """
        Oil Slick / Liquid Iridescence:
        Multiple thin-film interference fields drifting at irrational phase rates,
        producing petrol-like shifts: Cyan -> Indigo -> Violet -> Rose -> Amber -> Cyan.
        Overlapping waves continuously modulate local hue and brightness with zero jumps.
        """
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        oil_palette = [
            (185, 95, 90),  # Electric Cyan
            (235, 90, 85),  # Deep Indigo
            (280, 90, 95),  # Fluorescent Violet
            (335, 90, 90),  # Neon Rose
            (35, 95, 95),   # Golden Amber
        ]
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            f1 = math.sin(x * 3.4 * math.pi + t * 0.22 * sp)
            f2 = math.cos(x * 5.1 * math.pi - t * 0.17 * sp + 1.4)
            f3 = math.sin(x * 2.1 * math.pi + t * 0.31 * sp + 2.7)
            phase = (0.5 + 0.28 * f1 + 0.22 * f2 + 0.18 * f3) % 1.0
            h, s, _ = sample_palette_oklab(oil_palette, phase, cyclic=True)
            intensity = 0.5 + 0.3 * f1 + 0.2 * f3
            val = int(max(15, min(95, 25 + intensity * 68)))
            segs.append([h, s, val])
        return segs

    def _render_silk_ribbons(self, t: float) -> List[List[int]]:
        """
        Silk Ribbons:
        Three broad, soft-edged luminous bands gliding in opposing directions.
        The brightness peaks move gradually, and the bands blend into one another smoothly in OKLab space.
        """
        from src.pipeline import tapo_hsv_to_rgb, rgb_to_tapo_hsv
        sp = max(0.2, self._speed)
        col_gold = tapo_hsv_to_rgb(42, 95, 95)
        col_magenta = tapo_hsv_to_rgb(320, 90, 95)
        col_teal = tapo_hsv_to_rgb(180, 90, 90)

        c1 = (0.5 + 0.45 * math.sin(t * 0.19 * sp)) * (NUM_SEGMENTS - 1)
        c2 = (0.5 + 0.45 * math.cos(t * 0.14 * sp + 1.2)) * (NUM_SEGMENTS - 1)
        c3 = (0.5 + 0.45 * math.sin(t * 0.23 * sp + 2.8)) * (NUM_SEGMENTS - 1)

        sigma = 6.8
        base_rgb = tapo_hsv_to_rgb(260, 80, 4)

        segs = []
        for i in range(NUM_SEGMENTS):
            w1 = math.exp(-0.5 * ((i - c1) / sigma) ** 2)
            w2 = math.exp(-0.5 * ((i - c2) / sigma) ** 2)
            w3 = math.exp(-0.5 * ((i - c3) / sigma) ** 2)

            r = min(1.0, base_rgb[0] + col_gold[0] * w1 * 0.8 + col_magenta[0] * w2 * 0.8 + col_teal[0] * w3 * 0.8)
            g = min(1.0, base_rgb[1] + col_gold[1] * w1 * 0.8 + col_magenta[1] * w2 * 0.8 + col_teal[1] * w3 * 0.8)
            b = min(1.0, base_rgb[2] + col_gold[2] * w1 * 0.8 + col_magenta[2] * w2 * 0.8 + col_teal[2] * w3 * 0.8)

            h, s, v = rgb_to_tapo_hsv(r, g, b)
            segs.append([h, s, max(6, min(95, v))])
        return segs

    def _render_nebula_bloom(self, t: float) -> List[List[int]]:
        """
        Nebula Bloom:
        Atmospheric clouds of violet, indigo, cyan, and fuchsia expanding and drifting
        over deep space navy, preserving rich negative space with zero strip-wide flashes.
        """
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        nebula_palette = [
            (240, 95, 30),  # Deep Space Navy
            (265, 90, 65),  # Royal Indigo
            (295, 85, 80),  # Celestial Violet
            (330, 90, 85),  # Cosmic Fuchsia
            (195, 90, 75),  # Starlight Cyan
        ]
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            n1 = math.sin(x * 2.8 * math.pi + t * 0.12 * sp)
            n2 = 0.5 * math.cos(x * 6.2 * math.pi - t * 0.18 * sp + 1.1)
            n3 = 0.25 * math.sin(x * 11.5 * math.pi + t * 0.25 * sp + 2.3)
            density = (n1 + n2 + n3 + 1.75) / 3.5

            contrast = max(0.0, density - 0.35) / 0.65
            cloud_p = contrast ** 1.6

            h, s, _ = sample_palette_oklab(nebula_palette, cloud_p, cyclic=False)
            val = int(max(2, min(90, 3 + cloud_p * 85)))
            segs.append([h, s, val])
        return segs

    def _render_holographic_moire(self, t: float) -> List[List[int]]:
        """
        Holographic Moiré:
        Two periodic optical waves with slightly detuned spatial frequencies sliding past
        each other, producing macroscopic moving interference envelopes and holographic sheen.
        """
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "dusk")
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            c1 = math.sin(2.0 * math.pi * 4.0 * x - t * 0.35 * sp)
            c2 = math.sin(2.0 * math.pi * 4.6 * x + t * 0.28 * sp + 0.8)
            envelope = 0.5 + 0.5 * (c1 * c2)
            pal_t = (envelope + x * 0.3 + t * 0.08 * sp) % 1.0
            h, s, _ = sample_palette_oklab(pal, pal_t, cyclic=True)
            val = int(max(6, min(95, 10 + envelope * 82)))
            segs.append([h, s, val])
        return segs

    def _render_bioluminescent_tide(self, t: float) -> List[List[int]]:
        """
        Bioluminescent Tide:
        Pacifica-inspired multi-layer oceanic swell simulation.
        Deep oceanic navy floor with rolling aquamarine waves and localized glowing cyan crests.
        """
        sp = max(0.2, self._speed)
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            w1 = math.sin(x * 2.5 * math.pi + t * 0.22 * sp)
            w2 = math.cos(x * 3.8 * math.pi - t * 0.16 * sp + 1.2)
            w3 = math.sin(x * 5.2 * math.pi + t * 0.31 * sp + 2.5)
            w4 = math.cos(x * 1.8 * math.pi - t * 0.11 * sp + 0.7)

            combined = (w1 * 0.35 + w2 * 0.30 + w3 * 0.20 + w4 * 0.15)
            height = 0.5 + 0.5 * combined

            hue = int(225 - height * 45)
            sat = int(max(65, min(95, 95 - height * 25)))

            if height > 0.78:
                crest = (height - 0.78) / 0.22
                hue = 175
                sat = int(max(30, 80 - crest * 45))
                val = int(min(100, 55 + crest * 45))
            else:
                val = int(max(4, min(65, 8 + height * 52)))
            segs.append([hue, sat, val])
        return segs

    def _render_ember_drift(self, t: float) -> List[List[int]]:
        """
        Ember Drift:
        Simulated 1D thermal convection bed. Warm copper and deep ruby coals drift slowly,
        punctuated by gentle glowing heat pockets that swell and cool organically.
        """
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        ember_palette = [
            (0, 100, 25),    # Dark Charred Ruby
            (12, 100, 60),   # Glowing Copper
            (28, 95, 85),    # Warm Flame Amber
            (42, 90, 100),   # Radiant Golden Glow
        ]
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            heat1 = 0.5 + 0.5 * math.sin(x * 3.2 * math.pi + t * 0.14 * sp)
            heat2 = 0.5 + 0.5 * math.cos(x * 6.0 * math.pi - t * 0.21 * sp + 1.8)
            pulse = 0.5 + 0.5 * math.sin(t * 0.35 * sp + i * 2.7)
            temp = heat1 * 0.55 + heat2 * 0.30 + pulse * 0.15

            h, s, _ = sample_palette_oklab(ember_palette, temp, cyclic=False)
            val = int(max(5, min(95, 12 + temp * 80)))
            segs.append([h, s, val])
        return segs

    def _render_cyberpunk(self, t: float) -> List[List[int]]:
        """
        Cyberpunk:
        Rich synthwave dual-layer composition. Electric cyan carrier waves sliding over
        neon magenta and deep ultraviolet baselines with golden apex highlights.
        """
        from src.visual_styles import sample_palette_oklab
        sp = max(0.2, self._speed)
        cyber_palette = [
            (280, 95, 40),  # Dark Ultraviolet
            (325, 95, 90),  # Neon Magenta
            (185, 95, 95),  # Electric Cyan
            (45, 90, 100),  # Neon Gold
        ]
        segs = []
        for i in range(NUM_SEGMENTS):
            x = i / float(NUM_SEGMENTS - 1)
            w1 = math.sin(x * 3.5 * math.pi + t * 0.28 * sp)
            w2 = math.cos(x * 2.2 * math.pi - t * 0.19 * sp + 1.5)
            comp = (w1 + w2) * 0.5
            pos = (0.5 + 0.5 * comp + x * 0.2) % 1.0
            h, s, _ = sample_palette_oklab(cyber_palette, pos, cyclic=True)
            val = int(max(15, min(95, 25 + (0.5 + 0.5 * w1) * 68)))
            segs.append([h, s, val])
        return segs

    def _compute(self, name: str, t: float = 0.0, apply_brightness: bool = False) -> List[List[int]]:
        """Realistic preview generator and backward compatibility computation for all catalog effects and aliases."""
        segs = self._compute_raw(name, t)
        if apply_brightness:
            b_scale = max(0.01, min(1.0, self._brightness / 100.0))
            return [[h, s, max(1, min(100, int(round(v * b_scale))))] for h, s, v in segs]
        return segs

    def _compute_raw(self, name: str, t: float = 0.0) -> List[List[int]]:
        eff = resolve_effect_alias(name)

        if eff == "lava_lamp":
            return self._render_lava_lamp(t)
        elif eff == "dusk":
            return self._render_standing_wave_dusk(t)
        elif eff in ("golden_hour", "ambient_drift", "sakura", "northern_lights"):
            return self._render_standing_wave_golden_hour(t)
        elif eff in ("campfire_hearth", "hearth", "fireplace", "fire_crawl"):
            return self._render_hearth_fire2012(t)
        elif eff in ("cyber_chase", "dual_wipe"):
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
        elif eff in ("tide", "ocean", "ocean_waves"):
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
        elif eff in ("deep_ocean", "bioluminescent_abyss"):
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
        elif eff in ("rainbow", "infinite_prism"):
            return self._render_rainbow(t)
        elif eff in ("oil_slick", "liquid_iridescence"):
            return self._render_oil_slick(t)
        elif eff == "silk_ribbons":
            return self._render_silk_ribbons(t)
        elif eff == "nebula_bloom":
            return self._render_nebula_bloom(t)
        elif eff in ("holographic_moire", "moire"):
            return self._render_holographic_moire(t)
        elif eff in ("bioluminescent_tide", "pacifica"):
            return self._render_bioluminescent_tide(t)
        elif eff in ("ember_drift", "embers_drift"):
            return self._render_ember_drift(t)
        elif eff == "cyberpunk":
            return self._render_cyberpunk(t)
        elif eff == "flicker":
            # Candle flicker: localized warm candle micro-surges with speed, brightness, and palette
            sp = max(0.2, self._speed)
            pal = get_palette_hsv(self._palette_name if self._palette_name in PALETTES else "sunset")
            base_h, base_s = pal[0][0], pal[0][1]
            return [[base_h, base_s, max(5, min(100, int(45 + 35 * math.sin(t * 3.0 * sp + i * 7.7))))] for i in range(NUM_SEGMENTS)]
        elif eff == "sunrise":
            # Sunrise: progressive dawn peach-gold expansion from center outwards
            sp = max(0.2, self._speed)
            prog = (math.sin(t * 0.4 * sp) + 1.0) * 0.5
            half = (NUM_SEGMENTS - 1) / 2.0
            segs = []
            for i in range(NUM_SEGMENTS):
                dist = abs(i - half) / half
                local_prog = max(0.0, min(1.0, prog * 1.5 - dist * 0.5))
                h = int(20 + 25 * local_prog)
                s = int(95 - 40 * local_prog)
                v = int(max(10, min(100, 20 + local_prog * 80)))
                segs.append([h, s, v])
            return segs
        elif eff == "sunset":
            # Sunset: twilight plum horizon edges fading into warm coral core
            sp = max(0.2, self._speed)
            prog = (math.cos(t * 0.35 * sp) + 1.0) * 0.5
            half = (NUM_SEGMENTS - 1) / 2.0
            segs = []
            for i in range(NUM_SEGMENTS):
                dist = abs(i - half) / half
                local_prog = max(0.0, min(1.0, prog * 1.4 - (1.0 - dist) * 0.4))
                h = int(330 - 50 * local_prog)
                s = int(85 + 15 * local_prog)
                v = int(max(8, min(85, 15 + local_prog * 70)))
                segs.append([h, s, v])
            return segs

        if eff in EFFECT_CATALOG and "alias_of" in EFFECT_CATALOG[eff]:
            return self._compute_raw(EFFECT_CATALOG[eff]["alias_of"], t)

        return [[30, 80, 60]] * NUM_SEGMENTS
