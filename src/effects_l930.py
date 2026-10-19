"""
L930 True 50-Zone Addressable WRGBIC Effects Engine.

Drives all 50 physical zones of the Tapo L930 independently.
Each custom effect computes 50 distinct [H, S, V] tuples per tick,
sent with adaptive latency crossfading for silky smooth transitions.
Native firmware effects are dispatched directly to the hardware.
"""
from __future__ import annotations

import asyncio
import math
import random
import threading
import time
from plugp100.api.light_effect_preset import LightEffectPreset
from src.frame_bus import FramePacket, OutputProducer

NUM_SEGMENTS = 50

# ── Math and easing helpers ──────────────────────────────────────────────────

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def _lerp_hue(h1: float, h2: float, t: float) -> float:
    diff = h2 - h1
    if diff > 180: diff -= 360
    elif diff < -180: diff += 360
    return (h1 + diff * t) % 360

def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


# ── Presets & Registry ────────────────────────────────────────────────────────

NATIVE_EFFECTS = {
    "rainbow":          LightEffectPreset.Rainbow,
    "aurora":           LightEffectPreset.Aurora,
    "ocean":            LightEffectPreset.Ocean,
    "lightning":        LightEffectPreset.Lightning,
    "raindrop":         LightEffectPreset.Raindrop,
    "spring":           LightEffectPreset.Spring,
    "sunrise":          LightEffectPreset.Sunrise,
    "sunset":           LightEffectPreset.Sunset,
    "flicker":          LightEffectPreset.Flicker,
    "candy_cane":       LightEffectPreset.CandyCane,
    "haunted_mansion":  LightEffectPreset.HauntedMansion,
    "icicle":           LightEffectPreset.Icicle,
}

CUSTOM_EFFECTS = {
    "rainbow_chase",
    "fire_crawl",
    "police",
    "comet",
    "pixel_bounce",
    "cyber_chase",
    "aurora_wave",
    "meteor",
    "spectrum_idle",
    "color_wipe",
    "matrix_rain",
    "strobe_party",
    "lava_lamp",
    "glitch_wave",
    "neon_heartbeat",
    "twinkle_stars",
    "hyperdrive",
    "sunset_glow",
    "plasma_flow",
    "vaporwave_neon",
    "portal_pulse",
    "sonar_sweep",
    "electric_arc",
    "quantum_dots",
    "ambient_drift",
    "northern_lights",
    "fireplace",
    "sakura",
    "golden_hour",
    "deep_ocean",
}


from src.pipeline import RenderPipeline
from src.visual_styles import blend_zones_oklab
from src.layered_effects import LayeredAuroraGenerator, LayeredFireGenerator, LayeredLavaGenerator

class L930EffectsEngine:
    """Drives 50-zone addressable WRGBIC animations on the Tapo L930."""

    def __init__(self, controller, loop_runner, app_state, frame_bus: Any = None, dev_id: str = "strip2"):
        self._ctrl = controller
        self._loop_runner = loop_runner
        self._app_state = app_state
        self._frame_bus = frame_bus
        self._dev_id = dev_id
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._effect_name = None
        self._start_time = 0.0
        self._target_segs = None
        self._rendered_segs: list[list[int]] = [[0, 0, 0]] * NUM_SEGMENTS
        self._updater_future = None
        self._native_running = False
        
        # Dedicated pre-correction pipeline (prevents per-frame allocation in asyncio thread)
        self._pipeline = RenderPipeline(gamma=2.2, r_calib=1.0, g_calib=0.96, b_calib=0.90)
        
        # Smooth OKLab crossfade on effect switch (350 ms)
        self._transition_from: Optional[List[List[int]]] = None
        self._transition_start: float = 0.0
        self._transition_duration: float = 0.35
        
        # Layered effect generators (noise, diffusion, compositing)
        self._gen_aurora = LayeredAuroraGenerator(palette_name="aurora", speed=1.0)
        self._gen_fire = LayeredFireGenerator(palette_name="fire", speed=1.0)
        self._gen_lava = LayeredLavaGenerator(palette_name="sunset", speed=1.0)
        self._gen_ambient_drift = LayeredAuroraGenerator(palette_name="ambient_drift", speed=0.7)
        self._gen_sakura = LayeredAuroraGenerator(palette_name="sakura", speed=0.8)
        self._gen_golden_hour = LayeredAuroraGenerator(palette_name="golden_hour", speed=0.6)
        self._gen_deep_ocean = LayeredAuroraGenerator(palette_name="deep_ocean", speed=0.7)

    def is_running(self) -> bool:
        return self._running or self._native_running

    def start(self, effect_name: str):
        # Native firmware presets run directly on hardware
        if effect_name in NATIVE_EFFECTS:
            self._stop_custom_worker()
            self._native_running = True
            self._effect_name = effect_name
            preset = NATIVE_EFFECTS[effect_name]
            fx = preset.to_effect()
            self._loop_runner.run(self._ctrl.set_native_effect(fx, priority=0))
            return

        if self._native_running:
            self._native_running = False

        # Capture current frame for silky-smooth 350ms OKLab crossfade (only if already lit)
        if self._rendered_segs and any(seg[2] > 3 for seg in self._rendered_segs):
            self._transition_from = [list(seg) for seg in self._rendered_segs]
            self._transition_start = time.time()
        else:
            self._transition_from = None

        self._effect_name = effect_name
        self._start_time = time.time()

        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True, name="L930EffectsWorker")
            self._thread.start()

    def _stop_custom_worker(self):
        self._running = False
        self._transition_from = None
        self._target_segs = None
        if self._thread and self._thread.is_alive() and self._thread != threading.current_thread():
            self._thread.join(timeout=0.15)
        self._thread = None
        if hasattr(self._ctrl, "clear_frames"):
            self._ctrl.clear_frames()

    def stop(self):
        self._stop_custom_worker()
        self._native_running = False
        self._effect_name = None

    # ── Physics & Math Thread (40 FPS Decoupled Generator) ───────────────────

    def _run(self):
        while self._running:
            try:
                if self._effect_name not in CUSTOM_EFFECTS:
                    time.sleep(0.05)
                    continue
                now = time.time()
                t = now - self._start_time
                target_segs = self._compute(self._effect_name, t)
                if target_segs:
                    # Apply smooth OKLab crossfade if transitioning between effects
                    if self._transition_from is not None:
                        trans_t = (now - self._transition_start) / max(0.05, self._transition_duration)
                        if trans_t < 1.0:
                            blended = blend_zones_oklab(self._transition_from, target_segs, trans_t)
                            target_segs = [list(x) for x in blended]
                        else:
                            self._transition_from = None

                    self._rendered_segs = target_segs
                    self._target_segs = target_segs
                    
                    # Submit pre-corrected frame directly to decoupled transmitter
                    b = self._app_state.get("brightness", 85)
                    master_ceiling = b / 100.0
                    corrected = self._pipeline.correct_hsv_sequence(target_segs, master_ceiling=master_ceiling)

                    if self._frame_bus:
                        self._frame_bus.publish(FramePacket(
                            dev_id=self._dev_id,
                            producer=OutputProducer.EFFECT,
                            segments=corrected,
                            brightness=b,
                            transition=0,
                        ))

                    if hasattr(self._ctrl, "submit_frame"):
                        self._ctrl.submit_frame({
                            "segments": corrected,
                            "brightness": b,
                            "transition": 0,
                            "_pre_corrected": True
                        })
                    else:
                        self._loop_runner.run(self._ctrl.set_segments(corrected, master_brightness=b))

                time.sleep(0.025)  # 40 fps physics calculation
            except Exception as e:
                time.sleep(0.2)

    def _compute(self, name: str, t: float) -> list[list[int]]:
        n = NUM_SEGMENTS
        if name == "rainbow_chase":
            return self._rainbow_chase(t, n)
        elif name == "fire_crawl":
            return self._fire(t, n)
        elif name == "police":
            return self._police(t, n)
        elif name == "comet":
            return self._comet(t, n)
        elif name == "pixel_bounce":
            return self._pixel_bounce(t, n)
        elif name == "cyber_chase":
            return self._cyber_chase(t, n)
        elif name == "aurora_wave":
            return self._aurora_wave(t, n)
        elif name == "meteor":
            return self._meteor(t, n)
        elif name == "spectrum_idle":
            return self._spectrum_idle(t, n)
        elif name == "color_wipe":
            return self._color_wipe(t, n)
        elif name == "matrix_rain":
            return self._matrix_rain(t, n)
        elif name == "strobe_party":
            return self._strobe_party(t, n)
        elif name == "lava_lamp":
            return self._lava_lamp(t, n)
        elif name == "glitch_wave":
            return self._glitch_wave(t, n)
        elif name == "neon_heartbeat":
            return self._neon_heartbeat(t, n)
        elif name == "twinkle_stars":
            return self._twinkle_stars(t, n)
        elif name == "hyperdrive":
            return self._hyperdrive(t, n)
        elif name == "sunset_glow":
            return self._sunset_glow(t, n)
        elif name == "plasma_flow":
            return self._plasma_flow(t, n)
        elif name == "vaporwave_neon":
            return self._vaporwave_neon(t, n)
        elif name == "portal_pulse":
            return self._portal_pulse(t, n)
        elif name == "sonar_sweep":
            return self._sonar_sweep(t, n)
        elif name == "electric_arc":
            return self._electric_arc(t, n)
        elif name == "quantum_dots":
            return self._quantum_dots(t, n)
        elif name == "ambient_drift":
            return self._gen_ambient_drift.render_frame(t)
        elif name == "northern_lights":
            return self._gen_aurora.render_frame(t)
        elif name == "fireplace":
            return self._gen_fire.render_frame(t)
        elif name == "sakura":
            return self._gen_sakura.render_frame(t)
        elif name == "golden_hour":
            return self._gen_golden_hour.render_frame(t)
        elif name == "deep_ocean":
            return self._gen_deep_ocean.render_frame(t)
        return [[0, 0, 0]] * n

    # ── 50-Zone Effect Algorithms ─────────────────────────────────────────────

    def _rainbow_chase(self, t: float, n: int) -> list[list[int]]:
        """Continuous 360° rainbow rolling seamlessly through all 50 LEDs."""
        segs = []
        speed = 45.0
        for i in range(n):
            h = int((t * speed + (i / n) * 360.0)) % 360
            segs.append([h, 100, 100])
        return segs

    def _fire(self, t: float, n: int) -> list[list[int]]:
        """Physical heat diffusion simulation + ember sparks overlay across 50 zones."""
        return self._gen_fire.render_frame(t)

    def _police(self, t: float, n: int) -> list[list[int]]:
        """High-intensity emergency strobe: Left 25 Red vs Right 25 Blue."""
        half = n // 2
        phase = int(t * 6.0) % 4
        segs = []
        for i in range(n):
            if i < half:
                if phase in (0, 1):
                    segs.append([0, 100, 100])
                else:
                    segs.append([0, 0, 3])
            else:
                if phase in (2, 3):
                    segs.append([225, 100, 100])
                else:
                    segs.append([0, 0, 3])
        return segs

    def _comet(self, t: float, n: int) -> list[list[int]]:
        """Blazing white-cyan comet head with deep purple fading tail across 50 zones."""
        speed = 8.0
        pos = (t * speed) % (n + 16) - 8
        tail_len = 16
        segs = []
        for i in range(n):
            dist = pos - i
            if 0 <= dist < tail_len:
                intensity = _ease_out(1.0 - (dist / tail_len))
                if dist < 2.0:
                    segs.append([180, int(dist * 35), 100])
                else:
                    h = int(285 - dist * 4)
                    s = int(max(70, 100 - dist * 2))
                    v = int(max(5, intensity * 100))
                    segs.append([h, s, v])
            else:
                segs.append([240, 80, 4])
        return segs

    def _pixel_bounce(self, t: float, n: int) -> list[list[int]]:
        """Laser scanner / Cylon bounce oscillating smoothly across the 50 LEDs."""
        period = 3.2
        norm = (t % period) / period
        head = (1.0 - abs(2.0 * norm - 1.0)) * (n - 1)
        width = 4.0
        segs = []
        for i in range(n):
            dist = abs(head - i)
            if dist < width:
                b = int(max(10, (1.0 - dist / width) * 100))
                segs.append([340, 100, b])
            else:
                segs.append([260, 90, 4])
        return segs

    def _cyber_chase(self, t: float, n: int) -> list[list[int]]:
        """Cyberpunk alternating waves of Hot Pink (320°) and Neon Cyan (180°)."""
        segs = []
        speed = 2.5
        for i in range(n):
            wave = math.sin((i / 7.0) - t * speed)
            if wave > 0:
                h = 320
                v = int(20 + wave * 80)
            else:
                h = 180
                v = int(20 + (-wave) * 80)
            segs.append([h, 100, v])
        return segs

    def _aurora_wave(self, t: float, n: int) -> list[list[int]]:
        """Multi-layer Arctic aurora: Perlin gradient flow + harmonic curtain wave + starlight overlay."""
        return self._gen_aurora.render_frame(t)

    def _meteor(self, t: float, n: int) -> list[list[int]]:
        """Cascading meteor drops sparking across the 50 LEDs."""
        segs = [[230, 80, 5] for _ in range(n)]
        for speed, offset in ((12.0, 0.0), (18.0, 25.0)):
            head = int((t * speed + offset) % (n + 10))
            for trail in range(8):
                idx = head - trail
                if 0 <= idx < n:
                    fade = 1.0 - (trail / 8.0)
                    segs[idx] = [190, int(trail * 12), int(fade * 100)]
        return segs

    def _spectrum_idle(self, t: float, n: int) -> list[list[int]]:
        """Simulated 50-band music equalizer idle animation."""
        segs = []
        for i in range(n):
            freq_pos = i / (n - 1)
            h = int(freq_pos * 290.0)
            bounce = math.sin(t * 4.0 + i * 0.6) * 0.35 + math.cos(t * 8.0 + i * 1.3) * 0.25 + 0.4
            v = int(max(12, min(100, bounce * 100)))
            segs.append([h, 95, v])
        return segs

    def _color_wipe(self, t: float, n: int) -> list[list[int]]:
        """Sequential pixel wipe across all 50 zones switching palettes."""
        palettes = [0, 60, 120, 180, 240, 300]
        cycle_time = 4.0
        current_cycle = int(t / cycle_time)
        color_a = palettes[current_cycle % len(palettes)]
        color_b = palettes[(current_cycle + 1) % len(palettes)]
        progress = (t % cycle_time) / cycle_time
        wipe_pos = int(progress * n)
        segs = []
        for i in range(n):
            h = color_b if i <= wipe_pos else color_a
            segs.append([h, 100, 100])
        return segs

    def _matrix_rain(self, t: float, n: int) -> list[list[int]]:
        """Cascading neon matrix digital code rain drops."""
        segs = [[135, 100, 4] for _ in range(n)]  # Dark emerald base
        for offset, speed in ((0.0, 7.0), (18.0, 9.5), (35.0, 6.0)):
            pos = int((t * speed + offset) % (n + 12))
            for trail in range(8):
                idx = pos - trail
                if 0 <= idx < n:
                    if trail == 0:
                        segs[idx] = [120, 20, 100]  # White-green glowing head
                    else:
                        v = int((1.0 - trail / 8.0) * 90)
                        segs[idx] = [135, 100, max(5, v)]
        return segs

    def _strobe_party(self, t: float, n: int) -> list[list[int]]:
        """High-energy BPM party strobe across alternating blocks."""
        bpm = 130
        beat = int(t * (bpm / 60.0) * 4)
        colors = [0, 60, 180, 290, 120]
        c1 = colors[beat % len(colors)]
        c2 = colors[(beat + 2) % len(colors)]
        segs = []
        for i in range(n):
            block = (i // 5) % 2
            if (beat % 2) == block:
                h = c1 if block == 0 else c2
                segs.append([h, 100, 100])
            else:
                segs.append([0, 0, 5])
        return segs

    def _lava_lamp(self, t: float, n: int) -> list[list[int]]:
        """Multi-layer magma lava lamp: viscous crust base + buoyant convection cells."""
        return self._gen_lava.render_frame(t)

    def _glitch_wave(self, t: float, n: int) -> list[list[int]]:
        """Cyberpunk glitch with random electric flashes and stutter steps."""
        step = int(t * 8.0)
        rng = random.Random(step)
        glitch_zone = rng.randint(0, n - 6)
        glitch_active = rng.random() > 0.4
        segs = []
        for i in range(n):
            wave = (math.sin(i * 0.2 - t * 3.0) + 1.0) / 2.0
            h = int(180 + wave * 140)  # Cyan to Magenta
            v = int(30 + wave * 60)
            if glitch_active and glitch_zone <= i <= glitch_zone + 5:
                h = 60  # Flash electric yellow
                v = 100
            segs.append([h, 95, v])
        return segs

    def _neon_heartbeat(self, t: float, n: int) -> list[list[int]]:
        """Double-thump crimson heartbeat expanding from center outward."""
        half = n // 2
        cycle = t % 1.2
        # Double pulse at t=0 and t=0.25
        if cycle < 0.18:
            pulse = math.sin((cycle / 0.18) * math.pi)
        elif 0.22 <= cycle < 0.40:
            pulse = math.sin(((cycle - 0.22) / 0.18) * math.pi) * 0.75
        else:
            pulse = 0.0

        spread = pulse * half
        segs = []
        for i in range(n):
            dist = abs(i - half)
            if dist <= spread:
                intensity = 1.0 - (dist / max(1.0, spread))
                v = int(20 + intensity * 80)
                segs.append([350, 100, v])
            else:
                segs.append([350, 100, 10])
        return segs

    def _twinkle_stars(self, t: float, n: int) -> list[list[int]]:
        """Deep midnight space blue with sparkling diamond stars."""
        segs = [[235, 90, 8] for _ in range(n)]
        rng = random.Random(int(t * 3.0))
        for _ in range(7):
            idx = rng.randint(0, n - 1)
            twinkle_v = rng.randint(70, 100)
            segs[idx] = [210, 20, twinkle_v]  # Diamond white-blue
        return segs

    def _hyperdrive(self, t: float, n: int) -> list[list[int]]:
        """Hyperspace acceleration streaks stretching from center to ends."""
        half = n // 2
        speed = 10.0
        pos = (t * speed) % half
        segs = []
        for i in range(n):
            dist = abs(i - half)
            streak = (dist - pos) % half
            if streak < 3.0:
                v = int((1.0 - streak / 3.0) * 100)
                segs.append([195, 30, max(10, v)])
            else:
                segs.append([240, 80, 8])
        return segs

    def _sunset_glow(self, t: float, n: int) -> list[list[int]]:
        """Golden hour shifting into dusk violet and rose across the 50 zones."""
        segs = []
        for i in range(n):
            p = i / (n - 1)
            shift = math.sin(t * 0.3 + p * 1.5) * 0.5 + 0.5
            # From warm golden sunset (28°) to dusky violet (310°)
            h = int(_lerp_hue(28, 310, p * 0.7 + shift * 0.3))
            v = int(40 + shift * 55)
            segs.append([h, 95, v])
        return segs

    def _plasma_flow(self, t: float, n: int) -> list[list[int]]:
        """Tri-frequency fluid plasma wave rolling across all 50 zones."""
        segs = []
        for i in range(n):
            p = i / (n - 1)
            v1 = math.sin(p * 10.0 + t * 1.5)
            v2 = math.sin(p * 5.0 - t * 2.0 + math.cos(t * 0.7))
            v3 = math.sin((p + t * 0.4) * 8.0)
            blend = (v1 + v2 + v3 + 3.0) / 6.0
            h = int((blend * 360.0 + t * 20.0) % 360)
            v = int(45 + blend * 55)
            segs.append([h, 100, v])
        return segs

    def _vaporwave_neon(self, t: float, n: int) -> list[list[int]]:
        """Aesthetic 80s gradient between neon magenta, pastel cyan, and soft coral."""
        segs = []
        for i in range(n):
            p = i / (n - 1)
            phase = math.sin(t * 1.2 + p * 3.14) * 0.5 + 0.5
            h = int(_lerp_hue(315, 180, phase))
            s = int(85 + math.sin(t * 2.0 + p * 4.0) * 15)
            v = int(60 + phase * 40)
            segs.append([h, s, v])
        return segs

    def _portal_pulse(self, t: float, n: int) -> list[list[int]]:
        """Dual inward converging waves meeting at center with golden energy explosion."""
        half = n // 2
        pos = (t * 8.0) % half
        segs = []
        for i in range(n):
            dist = abs(i - half)
            ring = abs(dist - pos)
            if ring < 3.5:
                bright = int((1.0 - ring / 3.5) * 100)
                h = 175 if dist > 6 else 45
                segs.append([h, 95, max(15, bright)])
            else:
                segs.append([260, 85, 6])
        return segs

    def _sonar_sweep(self, t: float, n: int) -> list[list[int]]:
        """Phosphor green radar sweep pinging from side to side across 50 zones."""
        period = 3.6
        norm = (t % period) / period
        head = (1.0 - abs(2.0 * norm - 1.0)) * (n - 1)
        segs = []
        for i in range(n):
            dist = abs(head - i)
            if dist < 6.0:
                fade = (1.0 - dist / 6.0) ** 1.5
                segs.append([125, 100, int(fade * 100)])
            else:
                segs.append([140, 90, 4])
        return segs

    def _electric_arc(self, t: float, n: int) -> list[list[int]]:
        """High-voltage electric blue arcs leaping randomly between zones."""
        step = int(t * 12.0)
        rng = random.Random(step)
        arc_start = rng.randint(0, n - 8)
        arc_len = rng.randint(4, 8)
        segs = [[225, 90, 8] for _ in range(n)]
        for j in range(arc_len):
            idx = arc_start + j
            if idx < n:
                flicker_v = rng.randint(80, 100)
                sat = rng.randint(10, 45)
                segs[idx] = [205, sat, flicker_v]
        return segs

    def _quantum_dots(self, t: float, n: int) -> list[list[int]]:
        """Shimmering quantum superposition dots expanding and collapsing."""
        segs = []
        phi = 1.6180339887
        for i in range(n):
            val = (math.sin(i * phi * 4.0 + t * 3.0) + 1.0) / 2.0
            val = val ** 3.0
            h = int((i * 137.5 + t * 25.0) % 360)
            v = int(10 + val * 90)
            segs.append([h, 100, v])
        return segs
