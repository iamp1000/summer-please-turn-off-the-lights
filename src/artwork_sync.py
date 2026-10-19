"""
Windows Media Session Artwork Palette Provider (ported & enhanced from LumiSync).

Extracts the album artwork of the currently playing media (Spotify, Tidal, YouTube, Apple Music, etc.)
via Windows GlobalSystemMediaTransportControlsSessionManager (GSMTC), quantizes the image to dominant
vibrant color stops, and converts them into Tapo HSV palettes for real-time visualizer rendering.
"""

from __future__ import annotations
import asyncio
import colorsys
import io
import sys
import threading
import time
from typing import List, Tuple, Optional
from PIL import Image, UnidentifiedImageError

RGB = Tuple[int, int, int]
HSV = Tuple[int, int, int]

MAX_ARTWORK_BYTES = 8 * 1024 * 1024


def extract_palette_from_bytes(image_bytes: bytes | None, color_count: int = 6) -> List[HSV]:
    """
    Extracts a saturated, distinct palette of Tapo HSV tuples (0..360, 0..100, 0..100)
    from encoded cover artwork bytes.
    """
    if not image_bytes or color_count <= 0:
        return []

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            img = source.convert("RGB")
            img.thumbnail((96, 96), Image.Resampling.LANCZOS)
            quantized = img.quantize(
                colors=max(8, min(32, color_count * 3)),
                method=Image.Quantize.MEDIANCUT,
            )
            color_table = quantized.getpalette() or []
            indexed_colors = quantized.getcolors() or []
    except (OSError, UnidentifiedImageError, ValueError):
        return []

    candidates: List[Tuple[float, HSV]] = []
    for population, index in indexed_colors:
        offset = int(index) * 3
        if offset + 2 >= len(color_table):
            continue
        r, g, b = color_table[offset : offset + 3]
        h_float, s_float, v_float = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

        # Skip near-black noise
        if v_float < 0.08:
            continue

        # Enrich saturation and value for vivid LED representation
        if s_float >= 0.08:
            s_float = min(1.0, max(0.40, s_float * 1.18))
        v_float = min(1.0, max(0.45, v_float * 1.10))

        h_deg = int(round(h_float * 360.0)) % 360
        s_pct = int(round(s_float * 100.0))
        v_pct = int(round(v_float * 100.0))

        # Weight higher population and saturation
        score = float(population) * (0.35 + s_float) * (0.30 + v_float)
        candidates.append((score, (h_deg, s_pct, v_pct)))

    # Deduplicate colors by hue distance
    palette: List[HSV] = []
    for _score, (h, s, v) in sorted(candidates, key=lambda c: c[0], reverse=True):
        if all(min(abs(h - ex[0]), 360 - abs(h - ex[0])) >= 25 or abs(s - ex[1]) >= 25 for ex in palette):
            palette.append((h, s, v))
        if len(palette) >= color_count:
            break

    return palette


async def _fetch_current_artwork_bytes() -> Optional[bytes]:
    if sys.platform != "win32":
        return None
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
        from winrt.windows.storage.streams import DataReader

        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        if not manager:
            return None
        session = manager.get_current_session()
        if not session:
            return None
        properties = await session.try_get_media_properties_async()
        if not properties or not properties.thumbnail:
            return None

        stream = await properties.thumbnail.open_read_async()
        if not stream or stream.size <= 0:
            return None

        size = min(int(stream.size), MAX_ARTWORK_BYTES)
        reader = DataReader(stream.get_input_stream_at(0))
        await reader.load_async(size)
        buf = bytearray(size)
        reader.read_bytes(buf)
        reader.close()
        stream.close()
        return bytes(buf)
    except Exception:
        return None


class ArtworkPaletteProvider:
    """Polls media artwork asynchronously in background and caches latest palette."""

    def __init__(self, poll_interval: float = 6.0):
        self.poll_interval = max(2.0, float(poll_interval))
        self._palette: List[HSV] = []
        self._next_poll = 0.0
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_title = ""

    def get_palette(self) -> List[HSV]:
        """Returns immediately, launching a background update thread if poll interval has elapsed."""
        worker_to_start = None
        with self._lock:
            now = time.monotonic()
            if now >= self._next_poll and (self._worker is None or not self._worker.is_alive()):
                self._next_poll = now + self.poll_interval
                worker_to_start = threading.Thread(
                    target=self._refresh_worker,
                    name="ArtworkPaletteSync",
                    daemon=True
                )
                self._worker = worker_to_start
            current = list(self._palette)

        if worker_to_start:
            worker_to_start.start()
        return current

    def _refresh_worker(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            raw_bytes = loop.run_until_complete(_fetch_current_artwork_bytes())
            loop.close()

            if raw_bytes:
                pal = extract_palette_from_bytes(raw_bytes, color_count=6)
                if pal:
                    with self._lock:
                        self._palette = pal
        except Exception:
            pass


# Global singleton
_artwork_provider: Optional[ArtworkPaletteProvider] = None


def get_artwork_provider() -> ArtworkPaletteProvider:
    global _artwork_provider
    if _artwork_provider is None:
        _artwork_provider = ArtworkPaletteProvider()
    return _artwork_provider
