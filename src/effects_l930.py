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
import math
import random
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from plugp100.api.light_effect import LightEffect
from plugp100.api.light_effect_preset import LightEffectPreset
from src.frame_bus import FramePacket, OutputProducer
from src.pipeline import RenderPipeline
from src.firmware_effects import (
    PALETTES,
    get_palette_hsv,
    build_firmware_sequence_effect,
    build_firmware_random_effect,
)

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
        "desc": "Sparse soft twinkles on dark navy background (WLED Fairy reference)",
        "default_palette": "tide",
    },
    "embers": {
        "kind": "firmware",
        "group": "Ambient",
        "desc": "Very dim warm glow with slow random flicker for sleeping",
        "default_palette": "ember",
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
        "desc": "Warm sunset twilight and radiating golden dust",
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
        "kind": "firmware",  # Default to hardware loop; also supports streamed Fire2012
        "group": "Motion",
        "desc": "Restrained flame simulation with glowing ember foundation",
        "default_palette": "fire",
    },
    "comet": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Bright comet head with cooling chromatic tail traversing the strip",
        "default_palette": "sunset",
    },
    "cyber_chase": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Two color pulses passing through each other and adding at intersection",
        "default_palette": "dusk",
    },
    "vaporwave_neon": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Slow aesthetic gradient drift in magenta, cyan, and violet",
        "default_palette": "dusk",
    },
    "sonar_sweep": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Smooth radar sweep with soft exponential fading tail",
        "default_palette": "forest",
    },
    "neon_heartbeat": {
        "kind": "firmware",
        "group": "Motion",
        "desc": "Slow soft double-pulse rhythm for evening relaxation",
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
        self._active_effect_name: Optional[str] = None
        self._active_kind: Optional[str] = None
        self._start_time: float = 0.0

        # Current user parameters
        self._speed: float = 1.0         # 0.2x to 3.0x
        self._brightness: int = 100      # 1 to 100
        self._palette_name: str = "sunset"

        # Rate-limiting parameter updates to firmware (at most once per 2s)
        self._last_firmware_upload: float = 0.0
        self._pending_fw_upload: Optional[LightEffect] = None
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

    def start(self, effect_name: str, palette_name: Optional[str] = None, speed: Optional[float] = None):
        key = effect_name.strip().lower()
        if key not in EFFECT_CATALOG:
            # Check native aliases
            if key in NATIVE_PRESETS:
                key = "rainbow" if key == "rainbow_native" else key
            else:
                return

        if palette_name and palette_name.strip().lower() in PALETTES:
            self._palette_name = palette_name.strip().lower()
        elif "default_palette" in EFFECT_CATALOG[key]:
            self._palette_name = EFFECT_CATALOG[key]["default_palette"]

        if speed is not None:
            self._speed = max(0.2, min(3.0, float(speed)))

        meta = EFFECT_CATALOG[key]
        kind = meta["kind"]
        self._active_effect_name = key
        self._active_kind = kind
        self._start_time = time.time()

        if kind == "firmware":
            # Stop streaming worker: streaming sender is completely idle while firmware effect runs
            self._stop_stream_worker()
            self._deploy_firmware_effect(key)
        elif kind == "streamed_slow":
            # Start slow streaming worker (<= 2 updates/s)
            self._start_stream_worker()

    def stop(self):
        self._stop_stream_worker()
        self._active_effect_name = None
        self._active_kind = None
        if hasattr(self._ctrl, "clear_frames"):
            self._ctrl.clear_frames()

    # ── Firmware Effect Deployment ────────────────────────────────────────────

    def _deploy_firmware_effect(self, name: str):
        fx = self._build_effect_payload(name)
        if fx is None:
            return

        with self._fw_lock:
            now = time.time()
            # Throttle firmware uploads to at most once per 2s
            if now - self._last_firmware_upload < 2.0:
                self._pending_fw_upload = fx
                # Schedule upload after throttle period
                threading.Timer(2.0 - (now - self._last_firmware_upload), self._flush_pending_firmware_upload).start()
                return

            self._last_firmware_upload = now
            self._pending_fw_upload = None

        self._loop_runner.run(self._ctrl.set_native_effect(fx, priority=0))

    def _flush_pending_firmware_upload(self):
        with self._fw_lock:
            fx = self._pending_fw_upload
            self._pending_fw_upload = None
            if fx is None:
                return
            self._last_firmware_upload = time.time()
        self._loop_runner.run(self._ctrl.set_native_effect(fx, priority=0))

    def _redeploy_current_firmware_effect(self):
        if self._active_effect_name and self._active_kind == "firmware":
            self._deploy_firmware_effect(self._active_effect_name)

    def _build_effect_payload(self, name: str) -> Optional[LightEffect]:
        """Constructs valid LightEffect definition for firmware execution."""
        b = self._brightness
        pal = get_palette_hsv(self._palette_name)
        sp_factor = 1.0 / max(0.2, self._speed)

        # 1. Native Presets
        if name in ("sunrise", "sunset", "flicker", "ocean", "raindrop", "lightning", "candy_cane", "haunted_mansion"):
            preset_enum = NATIVE_PRESETS.get(name)
            if preset_enum:
                fx = preset_enum.to_effect()
                fx.brightness = b
                return fx
        if name == "rainbow":
            fx = LightEffectPreset.Rainbow.to_effect()
            fx.brightness = b
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
            # Muted 16-color glide across the strip with 6s transition
            seq16 = self._expand_palette_to_16(pal)
            trans = int(min(6000, 6000 * sp_factor))
            return build_firmware_sequence_effect(
                name="Drift", sequence=seq16, spread=12, direction=1, transition=trans, brightness=b
            )

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
        self._thread = threading.Thread(target=self._stream_run, daemon=True, name="L930SlowStreamWorker")
        self._thread.start()

    def _stop_stream_worker(self):
        self._running = False
        if self._thread and self._thread.is_alive() and self._thread != threading.current_thread():
            self._thread.join(timeout=0.2)
        self._thread = None

    def _stream_run(self):
        """
        Slow streamed loop (1 to 2 updates/s).
        Transition_ms matches update interval so the device hardware does the smooth crossfading.
        """
        interval = 0.8  # ~1.25 updates per second
        trans_ms = int(interval * 1000)

        while self._running:
            try:
                eff = self._active_effect_name
                if not eff or self._active_kind != "streamed_slow":
                    time.sleep(0.1)
                    continue

                now = time.time()
                t = now - self._start_time

                if eff == "lava_lamp":
                    segs = self._render_lava_lamp(t)
                    interval = 0.8
                    trans_ms = 800
                elif eff == "dusk":
                    segs = self._render_dusk(t)
                    interval = 5.0  # One update every 5-6s with 6000ms transition
                    trans_ms = 5000
                elif eff == "golden_hour":
                    segs = self._render_golden_hour(t)
                    interval = 1.0
                    trans_ms = 1000
                elif eff == "hearth_streamed":
                    segs = self._render_hearth_fire2012(t)
                    interval = 0.5  # 2 updates/s
                    trans_ms = 500
                else:
                    segs = [[30, 60, 50]] * NUM_SEGMENTS

                # Master brightness and gamma correction
                b = self._brightness
                master_ceiling = b / 100.0
                corrected = self._pipeline.correct_hsv_sequence(segs, master_ceiling=master_ceiling)

                if self._frame_bus:
                    self._frame_bus.publish(FramePacket(
                        dev_id=self._dev_id,
                        producer=OutputProducer.EFFECT,
                        segments=corrected,
                        brightness=b,
                        transition=trans_ms,
                    ))

                if hasattr(self._ctrl, "submit_frame"):
                    self._ctrl.submit_frame({
                        "segments": corrected,
                        "brightness": b,
                        "transition": trans_ms,
                        "_pre_corrected": True,
                    })

                time.sleep(interval)
            except Exception as e:
                time.sleep(1.0)

    # ── Procedural Streamed Models ───────────────────────────────────────────

    def _render_lava_lamp(self, t: float) -> List[List[int]]:
        """Lava lamp: 2-3 palette colors, slow buoyant convection cells."""
        pal = get_palette_hsv(self._palette_name)
        c1 = pal[0] if len(pal) > 0 else (20, 100, 80)
        c2 = pal[1] if len(pal) > 1 else (340, 85, 75)
        c3 = pal[2] if len(pal) > 2 else (280, 80, 50)

        # Update metaball positions
        for mb in self._metaballs:
            mb["pos"] += mb["vel"] * self._speed
            if mb["pos"] < 2.0 or mb["pos"] > 47.0:
                mb["vel"] *= -1.0

        segs = []
        for i in range(NUM_SEGMENTS):
            # Compute total potential field
            field = 0.0
            for mb in self._metaballs:
                dist = abs(i - mb["pos"])
                if dist < mb["radius"]:
                    field += (1.0 - dist / mb["radius"]) ** 2.0

            if field > 0.65:
                # Hot blob core
                h, s, v = c1
                bright = int(min(100, 70 + field * 30))
            elif field > 0.25:
                # Viscous outer envelope
                h, s, v = c2
                bright = int(min(100, 45 + field * 40))
            else:
                # Cooler background crust
                h, s, v = c3
                bright = 20

            segs.append([h, s, bright])
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

    def _compute(self, name: str, t: float = 0.0) -> List[List[int]]:
        """Backward compatibility simulation computation for test suites."""
        eff = name.lower()
        if eff == "lava_lamp":
            return self._render_lava_lamp(t)
        elif eff == "dusk":
            return self._render_dusk(t)
        elif eff in ("golden_hour", "ambient_drift", "sakura", "deep_ocean", "northern_lights"):
            return self._render_golden_hour(t)
        elif eff in ("hearth", "fireplace", "fire_crawl"):
            return self._render_hearth_fire2012(t)
        return [[30, 80, 60]] * NUM_SEGMENTS
