"""
scripts/render_gifs.py
Renders simulated 50-zone addressable LED light strip GIFs using the real effect engine
and real RenderPipeline calibration curves.

Generates 25 fps GIFs under 5 MB with caption 'simulated 50-zone strip' for:
- Pulse
- Spectrum
- Flow
- Movie (using synthetic sample clip luminance)
- 3 Ambient effects (Lava Lamp, Hearth Fire, Dusk)
"""
from __future__ import annotations

import colorsys
import math
import os
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline import RenderPipeline
from src.visual_styles import (
    PulseStyle,
    SpectrumStyle,
    FlowStyle,
    MovieStyle,
)
from src.screen_sync import ScreenData
from src.audio_dsp import MusicState, Section
from src.effects_l930 import L930EffectsEngine
from src.firmware_effects import PALETTES

NUM_ZONES = 50
WIDTH = 760
HEIGHT = 160
FPS = 25
DURATION_SEC = 2.4  # 60 frames = perfectly seamless 2.4s loop under 2MB
NUM_FRAMES = int(FPS * DURATION_SEC)

WALL_COLOR = (14, 15, 22)
PILL_H = 22
PILL_RADIUS = 6
STRIP_X0 = 45
STRIP_Y = 70
STRIP_W = WIDTH - 90
ZONE_PITCH = STRIP_W / float(NUM_ZONES)
ZONE_W = ZONE_PITCH - 2.0


def hsv_to_rgb(h: int, s: int, v: int) -> Tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s / 100.0, v / 100.0)
    return int(r * 255), int(g * 255), int(b * 255)


def draw_frame(
    zones_hsv: List[Tuple[int, int, int] | List[int]],
    pipeline: RenderPipeline,
    mode_name: str,
) -> Image.Image:
    """Applies real pipeline calibration and draws glowing pills on a dark wall."""
    # 1. Apply real calibration curve
    calibrated = pipeline.correct_hsv_sequence(zones_hsv)
    rgb_colors = [hsv_to_rgb(c[0], c[1], c[2]) for c in calibrated]

    # Base wall image
    base = Image.new("RGB", (WIDTH, HEIGHT), WALL_COLOR)

    # 2. Wall Bloom Layer (light bleed onto dark wall)
    bloom = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
    bloom_draw = ImageDraw.Draw(bloom)

    for i, col in enumerate(rgb_colors):
        zx = STRIP_X0 + i * ZONE_PITCH
        rad_x = int(ZONE_PITCH * 1.6)
        rad_y = 20
        bloom_draw.ellipse(
            [zx - rad_x, STRIP_Y - rad_y, zx + ZONE_W + rad_x, STRIP_Y + PILL_H + rad_y],
            fill=col,
        )

    bloom_blur = bloom.filter(ImageFilter.GaussianBlur(radius=15))
    base = ImageChops.screen(base, bloom_blur)
    draw = ImageDraw.Draw(base)

    # 3. Strip mounting track (aluminum extrusion channel)
    track_pad = 5
    draw.rounded_rectangle(
        [
            STRIP_X0 - track_pad,
            STRIP_Y - 4,
            STRIP_X0 + STRIP_W + track_pad,
            STRIP_Y + PILL_H + 4,
        ],
        radius=8,
        fill=(22, 24, 34),
        outline=(38, 42, 58),
    )

    # 4. Draw the 50 discrete glowing LED pills
    for i, col in enumerate(rgb_colors):
        zx = STRIP_X0 + i * ZONE_PITCH + 1
        draw.rounded_rectangle(
            [zx, STRIP_Y, zx + ZONE_W, STRIP_Y + PILL_H],
            radius=PILL_RADIUS,
            fill=col,
        )

    # 5. Text labels & required caption
    # Mode title
    draw.text((STRIP_X0, 22), f"MODE: {mode_name.upper()}", fill=(230, 235, 250))
    draw.text((STRIP_X0 + 260, 24), "50 ADDRESSABLE ZONES", fill=(110, 120, 150))

    # Required simulation caption
    caption = "simulated 50-zone strip"
    draw.text((WIDTH - STRIP_X0 - 150, HEIGHT - 28), caption, fill=(120, 125, 145))
    draw.text((STRIP_X0, HEIGHT - 28), "TAPO L930 WRGBIC", fill=(90, 95, 120))

    return base


def render_pulse_gif(pipeline: RenderPipeline, out_path: str):
    style = PulseStyle()
    pal = PALETTES["sunset"]
    style.set_params(preset_palette=pal, palette_mode="preset")
    dt = 1.0 / FPS
    frames = []

    for frame_idx in range(NUM_FRAMES):
        t = frame_idx * dt
        kick_phase = (t % 0.6) / 0.6
        kick = max(0.0, 1.0 - kick_phase * 4.0) ** 2.0
        energy = 0.35 + kick * 0.6
        bar_idx = int(t / 2.4 * 4) % 4
        ms = MusicState(
            energy=energy,
            energy_trend=0.0,
            kick=kick,
            beat_phase=kick_phase,
            bpm=100.0,
            bar_pos=bar_idx,
            section=Section.VERSE,
            silent=False,
        )
        zones = style.render(ms, dt, num_zones=NUM_ZONES)
        frames.append(draw_frame(zones, pipeline, "Pulse (Beat-Synced Swell)"))

    save_gif(frames, out_path)


def render_spectrum_gif(pipeline: RenderPipeline, out_path: str):
    style = SpectrumStyle()
    pal = PALETTES["dusk"]
    style.set_params(preset_palette=pal, palette_mode="preset")
    dt = 1.0 / FPS
    frames = []

    for frame_idx in range(NUM_FRAMES):
        t = frame_idx * dt
        half = NUM_ZONES // 2
        bands = np.zeros(NUM_ZONES, dtype=np.float32)
        for i in range(NUM_ZONES):
            dist = abs(i - half) / float(half)
            wave = math.sin(t * 12.0 - dist * 5.0) * 0.5 + 0.5
            bounce = math.sin(t * 6.0 + i * 0.3) * 0.3 + 0.4
            bands[i] = float(np.clip(wave * 0.6 + bounce * 0.4, 0.0, 1.0))

        ms = MusicState(
            energy=0.7,
            energy_trend=0.0,
            kick=0.5,
            beat_phase=(t % 0.5) / 0.5,
            bpm=120.0,
            section=Section.VERSE,
            silent=False,
            bands=bands,
        )
        zones = style.render(ms, dt, num_zones=NUM_ZONES)
        frames.append(draw_frame(zones, pipeline, "Spectrum (50-Band Equalizer)"))

    save_gif(frames, out_path)


def render_flow_gif(pipeline: RenderPipeline, out_path: str):
    style = FlowStyle()
    pal = PALETTES["tide"]
    style.set_params(preset_palette=pal, palette_mode="preset")
    dt = 1.0 / FPS
    frames = []

    for frame_idx in range(NUM_FRAMES):
        t = frame_idx * dt
        ms = MusicState(
            energy=0.45 + 0.2 * math.sin(t * 2.0),
            energy_trend=0.0,
            kick=0.1,
            beat_phase=(t % 1.2) / 1.2,
            bpm=80.0,
            section=Section.VERSE,
            silent=False,
            harmonic_ratio=0.8,
        )
        zones = style.render(ms, dt, num_zones=NUM_ZONES)
        frames.append(draw_frame(zones, pipeline, "Flow (Perlin Noise Curtains)"))

    save_gif(frames, out_path)


def render_movie_gif(pipeline: RenderPipeline, out_path: str):
    style = MovieStyle()
    pal = PALETTES["warm_mono"]
    style.set_params(preset_palette=pal, palette_mode="preset")
    dt = 1.0 / FPS
    frames = []

    for frame_idx in range(NUM_FRAMES):
        t = frame_idx * dt
        col_hsvs = []
        pan = (t / DURATION_SEC) * 2.0 * math.pi
        for i in range(NUM_ZONES):
            p = i / float(NUM_ZONES - 1)
            h = int(32 + 180 * (math.sin(p * 3.0 + pan) * 0.5 + 0.5)) % 360
            s = int(50 + 25 * math.cos(p * 2.0))
            v = int(45 + 35 * math.sin(p * 4.0 - pan * 0.5))
            col_hsvs.append((h, s, v))

        sd = ScreenData(
            global_hsv=(35, 45, 55),
            column_hsvs=col_hsvs,
            is_static=False,
            timestamp=t,
        )
        style.screen_data = sd
        ms = MusicState(energy=0.3, kick=0.1, section=Section.VERSE, silent=False)
        zones = style.render(ms, dt, num_zones=NUM_ZONES, screen_data=sd)
        frames.append(draw_frame(zones, pipeline, "Movie (Cinematic Ambilight)"))

    save_gif(frames, out_path)


def render_ambient_gifs(pipeline: RenderPipeline, assets_dir: Path):
    engine = L930EffectsEngine(controller=None, loop_runner=None, app_state=None)
    dt = 1.0 / FPS

    # 1. Lava Lamp
    frames_lava = []
    for frame_idx in range(NUM_FRAMES):
        t = frame_idx * dt
        zones = engine._render_lava_lamp(t)
        frames_lava.append(draw_frame(zones, pipeline, "Lava Lamp (Fluid Metaballs)"))
    save_gif(frames_lava, str(assets_dir / "lava_lamp.gif"))

    # 2. Hearth (Fire2012 simulation)
    frames_hearth = []
    for frame_idx in range(NUM_FRAMES):
        t = frame_idx * dt
        zones = engine._render_hearth_fire2012(t)
        frames_hearth.append(draw_frame(zones, pipeline, "Hearth (Fire2012 Simulation)"))
    save_gif(frames_hearth, str(assets_dir / "hearth.gif"))

    # 3. Dusk
    frames_dusk = []
    for frame_idx in range(NUM_FRAMES):
        t = frame_idx * dt
        zones = engine._render_dusk(t)
        frames_dusk.append(draw_frame(zones, pipeline, "Dusk (Circadian Ambient)"))
    save_gif(frames_dusk, str(assets_dir / "dusk.gif"))


def save_gif(frames: List[Image.Image], out_path: str):
    # Optimize palette and save under 5MB
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        optimize=True,
        duration=int(1000 / FPS),
        loop=0,
    )
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"Exported {out_path} ({size_mb:.2f} MB)")


def main():
    assets_dir = PROJECT_ROOT / "assets"
    assets_dir.mkdir(exist_ok=True)
    pipeline = RenderPipeline(gamma=2.2, min_brightness=3, master_ceiling=1.0)

    print("Rendering 25 FPS GIFs for 50-zone strip...")
    render_pulse_gif(pipeline, str(assets_dir / "pulse.gif"))
    render_spectrum_gif(pipeline, str(assets_dir / "spectrum.gif"))
    render_flow_gif(pipeline, str(assets_dir / "flow.gif"))
    render_movie_gif(pipeline, str(assets_dir / "movie.gif"))
    render_ambient_gifs(pipeline, assets_dir)
    print("All GIFs rendered successfully!")


if __name__ == "__main__":
    main()
