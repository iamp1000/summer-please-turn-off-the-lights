from __future__ import annotations

import asyncio
import colorsys
import ctypes
import math
from pathlib import Path
import threading
import time
from dataclasses import dataclass, field
from typing import Tuple, List, Optional
import numpy as np
import yaml

@dataclass
class ScreenData:
    global_hsv: Tuple[int, int, int] = (30, 45, 50)  # Luminance-weighted average screen colour
    column_hsvs: List[Tuple[int, int, int]] = field(default_factory=lambda: [(30, 45, 50)] * 50)
    is_static: bool = False
    timestamp: float = 0.0

# DXGI Desktop Duplication (GPU direct)
try:
    import dxcam
except (ImportError, OSError, Exception):
    dxcam = None

# MSS Fallback
try:
    import mss
except ImportError:
    mss = None

from src.pipeline import ZoneAsymmetricSmoother, AsymmetricSmoother
from src.frame_bus import FramePacket, OutputProducer
from src.logger import log

user32 = ctypes.windll.user32


def ensure_desktop_access():
    """Ensure current thread is attached to interactive desktop station."""
    try:
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            user32.CloseDesktop(hdesk)
    except Exception:
        pass


def detect_letterbox_bounds(img: np.ndarray, black_thresh: int = 14) -> Tuple[int, int, int, int]:
    """
    Detects letterbox (top/bottom) and pillarbox (left/right) black bars.
    Returns (left, top, right, bottom) bounding box of active video content.
    """
    h, w = img.shape[:2]
    # Fast 8x downsample for instant analysis
    sample = img[::8, ::8, :3]
    row_lums = np.mean(sample, axis=(1, 2))
    col_lums = np.mean(sample, axis=(0, 2))

    top = 0
    for r in range(len(row_lums)):
        if row_lums[r] > black_thresh:
            top = r * 8
            break

    bottom = h
    for r in range(len(row_lums) - 1, -1, -1):
        if row_lums[r] > black_thresh:
            bottom = min(h, (r + 1) * 8)
            break

    left = 0
    for c in range(len(col_lums)):
        if col_lums[c] > black_thresh:
            left = c * 8
            break

    right = w
    for c in range(len(col_lums) - 1, -1, -1):
        if col_lums[c] > black_thresh:
            right = min(w, (c + 1) * 8)
            break

    # If the scene is fully dark or detection exceeds 80% screen, return full display
    if (bottom - top) < h * 0.35 or (right - left) < w * 0.35:
        return (0, 0, w, h)

    return (left, top, right, bottom)


def extract_dominant_color_weighted(bgr_pixels: np.ndarray, sat_boost: float = 1.30) -> Tuple[int, int, int]:
    """
    Saturation-weighted dominant color extractor.
    Gives exponential weight to vibrant/saturated pixels so ambient lights pop
    instead of turning into a washed-out grey average.
    """
    if len(bgr_pixels) == 0:
        return (0, 0, 50)

    b = bgr_pixels[:, 0].astype(np.float32) / 255.0
    g = bgr_pixels[:, 1].astype(np.float32) / 255.0
    r = bgr_pixels[:, 2].astype(np.float32) / 255.0

    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    delta = max_c - min_c

    sat = np.where(max_c > 0.001, delta / max_c, 0.0)
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    # Saturation exponential weighting
    weights = ((sat + 0.12) ** 2.2) * (lum + 0.08)
    sum_w = float(np.sum(weights))

    if sum_w <= 0.001:
        mean_b = float(np.mean(b))
        mean_g = float(np.mean(g))
        mean_r = float(np.mean(r))
    else:
        mean_b = float(np.sum(b * weights) / sum_w)
        mean_g = float(np.sum(g * weights) / sum_w)
        mean_r = float(np.sum(r * weights) / sum_w)

    hc, sc, vc = colorsys.rgb_to_hsv(mean_r, mean_g, mean_b)
    # Apply vivid saturation & contrast curve
    sc = min(1.0, sc * sat_boost)
    vc = min(1.0, (vc ** 0.70))

    return (int(round(hc * 360.0)) % 360, int(round(sc * 100.0)), max(5, min(100, int(round(vc * 100.0)))))


SCREEN_PROFILES = {
    "video": {
        "letterbox_detection": True,
        "sat_boost": 1.35,
        "attack_rate": 0.70,
        "decay_rate": 0.22,
        "cut_threshold": 0.40,
        "stride": 12,
    },
    "gaming": {
        "letterbox_detection": False,
        "sat_boost": 1.45,
        "attack_rate": 0.92,
        "decay_rate": 0.40,
        "cut_threshold": 0.32,
        "stride": 10,
    },
    "desktop": {
        "letterbox_detection": False,
        "sat_boost": 1.10,
        "attack_rate": 0.40,
        "decay_rate": 0.18,
        "cut_threshold": 0.50,
        "stride": 16,
    },
}


class ScreenSync:
    """
    High-Performance Ambilight Synchronizer.
    Features:
      - DXGI Desktop Duplication (dxcam) GPU direct capture with MSS fallback
      - Letterbox / Pillarbox black-bar auto-detection
      - Saturation-weighted dominant color sampling (vivid colors, zero grey mud)
      - Hard scene-cut detection with instant snap
      - Asymmetric attack/decay temporal smoothing
      - Video / Gaming / Desktop tuning profiles
    """

    def __init__(self, controller, loop_runner, app_state, frame_bus: Any = None, dev_id: str = "strip2"):
        self._controller = controller
        self._loop_runner = loop_runner
        self._app_state = app_state
        self._frame_bus = frame_bus
        self._dev_id = dev_id
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._monitor_index = 0
        self._profile_name = "video"
        self._camera = None

        self._zone_smoother = ZoneAsymmetricSmoother(num_zones=50, attack_rate=0.70, decay_rate=0.22)
        self._l900_smoother = AsymmetricSmoother(attack_rate=0.70, decay_rate=0.22)
        self._last_sampled_v = 50.0
        self._smoothed_global_hsv = (30.0, 45.0, 50.0)
        self._rendered_segs: list[list[int]] = [[0, 0, 0]] * 50
        self.latest_screen_data: ScreenData = ScreenData()

        self._load_config()

    def _load_config(self):
        try:
            config_path = Path(__file__).resolve().parent.parent / "config.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                sc_cfg = cfg.get("screen_sync", {})
                self._monitor_index = max(0, sc_cfg.get("monitor_index", 1) - 1)
                self._profile_name = sc_cfg.get("profile", "video")
        except Exception:
            pass

    def set_profile(self, profile: str):
        if profile in SCREEN_PROFILES:
            self._profile_name = profile
            p = SCREEN_PROFILES[profile]
            self._zone_smoother.attack = p["attack_rate"]
            self._zone_smoother.decay = p["decay_rate"]
            self._l900_smoother.attack_rate = p["attack_rate"]
            self._l900_smoother.decay_rate = p["decay_rate"]
            log.info(f"[ScreenSync] Switched profile to: {profile}")

    def _submit_frame(self, frame):
        """Route render frames through FrameBus when the hub is active."""
        if self._frame_bus is not None:
            return self._frame_bus.publish_frame_dict(self._dev_id, OutputProducer.SCREEN_SYNC, frame)
        if hasattr(self._controller, "submit_frame"):
            return self._controller.submit_frame(frame)
        return False

    def is_running(self) -> bool:
        return self._running

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="ScreenSyncDXGIWorker")
        self._thread.start()

    def stop(self):
        self._running = False
        if hasattr(self._controller, "clear_frames"):
            self._controller.clear_frames()
        if self._camera:
            try:
                del self._camera
                self._camera = None
            except Exception:
                pass

    def _init_camera(self):
        if dxcam is not None:
            try:
                self._camera = dxcam.create(output_idx=self._monitor_index, output_color_mode="BGR")
                if self._camera:
                    log.info(f"[ScreenSync] DXGI Desktop Duplication active on display {self._monitor_index}")
                    return True
            except Exception as e:
                log.warning(f"[ScreenSync] DXGI init notice: {e}. Falling back to MSS.")
        return False

    def _extract_colors(self, img: np.ndarray, is_l930: bool, profile: dict):
        h, w = img.shape[:2]
        sat_boost = profile["sat_boost"]
        stride = profile["stride"]

        # Letterbox / black-bar crop
        if profile["letterbox_detection"]:
            left, top, right, bottom = detect_letterbox_bounds(img)
            content_img = img[top:bottom, left:right]
        else:
            content_img = img

        ch, cw = content_img.shape[:2]

        # 1. Whole-screen dominant color for L900
        full_sample = content_img[::stride, ::stride, :3].reshape(-1, 3)
        global_hsv = extract_dominant_color_weighted(full_sample, sat_boost=sat_boost)

        if not is_l930:
            return None, global_hsv

        # 2. 50 vertical columns across active content width for L930
        col_w = max(1, cw // 50)
        segs = []
        for i in range(50):
            x1 = i * col_w
            x2 = (i + 1) * col_w if i < 49 else cw
            column_pixels = content_img[::stride, x1:x2:4, :3].reshape(-1, 3)
            hsv = extract_dominant_color_weighted(column_pixels, sat_boost=sat_boost)
            segs.append(list(hsv))

        return segs, global_hsv

    def _run(self):
        ensure_desktop_access()
        is_l930 = hasattr(self._controller, "set_segments")
        dxgi_ready = self._init_camera()

        while self._running:
            profile = SCREEN_PROFILES.get(self._profile_name, SCREEN_PROFILES["video"])
            try:
                # ── DXGI Capture Path (Primary) ───────────────────────────────
                if dxgi_ready and self._camera:
                    frame = self._camera.grab()
                    if frame is not None:
                        segs, global_hsv = self._extract_colors(frame, is_l930, profile)
                        self._dispatch(segs, global_hsv, is_l930, profile)
                    time.sleep(0.025)
                    continue

                # ── MSS Fallback Path ─────────────────────────────────────────
                if mss is not None:
                    with mss.mss() as sct:
                        mon_idx = min(self._monitor_index + 1, len(sct.monitors) - 1)
                        monitor = sct.monitors[mon_idx]
                        while self._running:
                            img_grab = sct.grab(monitor)
                            frame = np.array(img_grab)[:, :, :3]  # BGRA -> BGR
                            segs, global_hsv = self._extract_colors(frame, is_l930, profile)
                            self._dispatch(segs, global_hsv, is_l930, profile)
                            time.sleep(0.030)
                else:
                    time.sleep(0.5)

            except Exception as e:
                log.debug(f"[ScreenSync] Frame notice: {e}")
                time.sleep(0.2)

    def _dispatch(self, segs, global_hsv, is_l930: bool, profile: dict):
        cut_thresh = profile["cut_threshold"]
        master_ceiling = self._app_state.get("brightness", 100) / 100.0

        col_tuples = [tuple(s) for s in segs] if segs else [global_hsv] * 50
        self.latest_screen_data = ScreenData(
            global_hsv=global_hsv,
            column_hsvs=col_tuples,
            is_static=False,
            timestamp=time.time(),
        )

        if is_l930 and segs:
            # Scene cuts are damped, never snapped: the output cadence is too low for hard jumps.
            avg_v_target = sum(s[2] for s in segs) / 50.0
            diff = abs(avg_v_target - self._last_sampled_v) / 100.0
            if diff > cut_thresh:
                # Temporarily reduce attack while the cut settles; decay remains gentle.
                self._zone_smoother.attack = min(self._zone_smoother.attack, 0.22)
            else:
                self._zone_smoother.attack = profile["attack_rate"]
            smoothed_segs = self._zone_smoother.update(segs)
            self._last_sampled_v = avg_v_target
            self._rendered_segs = smoothed_segs
            scaled_b = max(1, int(100 * master_ceiling))


            if hasattr(self._controller, "submit_frame"):
                self._submit_frame({"segments": smoothed_segs, "brightness": scaled_b, "transition": 0})
        else:
            gh, gs, gv = global_hsv
            prev_h, prev_s, prev_v = self._smoothed_global_hsv
            hue_delta = ((float(gh) - prev_h + 180.0) % 360.0) - 180.0
            # Dominant hue and saturation are low-pass filtered to avoid scene-cut flashes.
            alpha = 0.16 if abs(hue_delta) > 45.0 else 0.24
            smooth_h = (prev_h + alpha * hue_delta) % 360.0
            smooth_s = prev_s + alpha * (float(gs) - prev_s)
            smoothed_v = self._l900_smoother.update(float(gv))
            self._smoothed_global_hsv = (smooth_h, smooth_s, smoothed_v)
            final_b = max(1, int(smoothed_v * master_ceiling))
            gh, gs = int(round(smooth_h)) % 360, int(round(smooth_s))


            if hasattr(self._controller, "submit_frame"):
                self._submit_frame({"h": gh, "s": gs, "b": final_b})
