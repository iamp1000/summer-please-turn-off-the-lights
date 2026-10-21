"""
L930 Controller — True 50-Zone Addressable WRGBIC LED Strip.

The Tapo L930 has 50 individually addressable zones across 5 meters.
Hardware Protocol Requirements:
  - Effect ID MUST be exactly 32 hex characters (e.g. 'a1b2c3d4e5f60718293a4b5c6d7e8f90').
    Any other ID format is silently discarded by firmware with enable=0.
  - Frame pushes use type='static', segments=[0], expansion_strategy=1, custom=0.
  - sequence contains 50 [hue, saturation, brightness] values, mapping 1:1 to all 50 zones.
  - Decoupled 'latest frame wins' sender drops stale frames and dynamically adapts to measured RTT.
  - Auto-reauth on session timeout & background watchdog recovery.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional
from plyer import notification
from plugp100.common.credentials import AuthCredential

try:
    from plugp100.devices.factory import DeviceConnectConfiguration, connect
except ImportError:
    from plugp100.new.device_factory import DeviceConnectConfiguration, connect
from plugp100.api.light_effect import LightEffect

from src.diagnostics import DeviceDiagnostics
from src.frame_sender import LatestFrameSender
from src.logger import log

NUM_SEGMENTS = 50

# 32-hex ID required by L930 firmware
_STATIC_EFFECT_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
_SEQUENCE_EFFECT_ID = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def is_session_timeout(e: Exception) -> bool:
    """Detects whether an error was caused by an expired Tapo KLAP token or auth handshake."""
    msg = str(e).lower()
    return any(
        kw in msg
        for kw in (
            "session_timeout",
            "-1003",
            "-1501",
            "invalid authentication",
            "token_expired",
            "handshake",
            "unauthorized",
            "401",
            "403",
        )
    )


def safe_notify(title: str, message: str):
    """Safely dispatches desktop toast notification without crashing headless threads."""
    import sys
    if "pytest" in sys.modules:
        return
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="Tapo Control",
            timeout=2,
        )
    except Exception:
        pass


def make_50_zone_effect(
    segments_hsv: list[tuple[int, int, int] | list[int]],
    master_brightness: int = 100,
    transition: int = 0,
    pre_corrected: bool = False,
) -> LightEffect:
    """
    Build a 50-zone addressable LightEffect mapping 1:1 to the L930's 50 physical IC zones.
    segments_hsv: list of (h, s, v) values (up to 50; padded/truncated to 50).
    Pure serialization: does not perform heavy CPU math if pre_corrected=True.
    Preserves true black: zero brightness is strictly zero (no 1% minimum glow).
    """
    if pre_corrected:
        seq = [
            [int(item[0]) % 360, max(0, min(100, int(item[1]))), max(0, min(100, int(item[2])))]
            for item in list(segments_hsv)[:NUM_SEGMENTS]
        ]
    else:
        from src.pipeline import RenderPipeline
        master_mult = max(0, min(100, master_brightness)) / 100.0
        pipeline = RenderPipeline(gamma=2.2, r_calib=1.0, g_calib=0.96, b_calib=0.90, master_ceiling=master_mult)
        seq = pipeline.correct_hsv_sequence(segments_hsv[:NUM_SEGMENTS])

    # Pad with last color or dim if fewer than 50
    last = seq[-1] if seq else [0, 0, 0]
    while len(seq) < NUM_SEGMENTS:
        seq.append(list(last))

    return LightEffect(
        id=_STATIC_EFFECT_ID,
        name="DynamicZones",
        display_colors=seq[:4],
        enable=1,
        brightness=100,
        custom=1,
        direction=None,
        duration=0,
        expansion_strategy=1,
        fadeoff=None,
        hue_range=None,
        init_states=[],
        random_seed=None,
        repeat_times=0,
        saturation_range=None,
        segment_length=None,
        segments=list(range(NUM_SEGMENTS)),
        sequence=seq,
        spread=None,
        transition=int(transition),
        transition_range=None,
        type="static",
    )


class L930Controller:
    """
    Controls a Tapo L930 IC strip with 50 individually addressable zones.
    Features:
      - Decoupled 'latest frame wins' sender with dynamic adaptive pacing
      - Deep performance telemetry & instrumentation (send FPS, RTT ms, drop rate)
      - Session timeout detection & automatic re-authentication
      - Background watchdog for connection drop recovery
    """

    def __init__(
        self,
        ip: str,
        email: str,
        password: str,
        dev_id: str = "strip2",
        loop: Optional[asyncio.AbstractEventLoop] = None,
        calibration: Optional[Dict[str, Any]] = None,
    ):
        self.dev_id = dev_id
        self._ip = ip
        self._credentials = AuthCredential(email, password)
        self._device = None
        self._loop = loop

        self._lock = asyncio.Lock()
        self._reconnecting = False
        self._backoff_time = 0.5
        self._failure_streak = 0
        self._last_successful_response = 0.0
        self._last_reauth_time = time.time()

        calib = calibration or {}
        curve_exp = calib.get("curve_exponent", 1.8) if isinstance(calib, dict) else getattr(calib, "curve_exponent", 1.8)
        wb = calib.get("white_balance", [1.0, 0.96, 0.90]) if isinstance(calib, dict) else getattr(calib, "white_balance", [1.0, 0.96, 0.90])
        min_b = calib.get("min_brightness", 0) if isinstance(calib, dict) else getattr(calib, "min_brightness", 0)
        trans_ms = calib.get("transition_ms", 0) if isinstance(calib, dict) else getattr(calib, "transition_ms", 0)
        self.music_transition_ms = calib.get("music_transition_ms", 120) if isinstance(calib, dict) else 120
        self.default_transition_ms = trans_ms if trans_ms > 0 else self.music_transition_ms
        self.movie_transition_ms = calib.get("movie_transition_ms", 800) if isinstance(calib, dict) else 800
        self._max_updates_per_s = float(calib.get("max_updates_per_s", 8.0) if isinstance(calib, dict) else 8.0)
        self._movie_max_updates_per_s = float(calib.get("movie_max_updates_per_s", 2.0) if isinstance(calib, dict) else 2.0)
        self._min_zone_delta = float(calib.get("min_zone_delta", 1.5) if isinstance(calib, dict) else 1.5)

        from src.pipeline import RenderPipeline
        self._render_pipeline = RenderPipeline(
            curve_exponent=curve_exp,
            white_balance=wb,
            min_brightness=min_b,
            transition_ms=trans_ms,
            master_ceiling=1.0,
        )

        # State tracking
        self.last_h = 0
        self.last_s = 0
        self.last_b = 50
        self.last_k = 4000
        self.last_segments: list[list[int]] = [[0, 0, 0]] * NUM_SEGMENTS
        self._is_on = True

        # Telemetry & Frame Sender
        self.diagnostics = DeviceDiagnostics(dev_id=self.dev_id)
        self.frame_sender: Optional[LatestFrameSender] = None
        if self._loop:
            self._init_sender(self._loop)

        # Output-token validator installed by FrameBus when this controller is bound.
        self._output_token_authorizer = None

        # Watchdog task
        self._watchdog_task: Optional[asyncio.Task] = None

    def _init_sender(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        if self.frame_sender is None:
            max_ups = getattr(self, "_max_updates_per_s", 8.0)
            min_delta = getattr(self, "_min_zone_delta", 1.5)
            self.frame_sender = LatestFrameSender(
                dev_id=self.dev_id,
                transmit_fn=self.transmit_frame,
                diagnostics=self.diagnostics,
                loop=loop,
                max_updates_per_s=max_ups,
                min_zone_delta=min_delta,
            )
            self.frame_sender.start()

    def submit_frame(self, frame: Any):
        """Submit frame to decoupled sender. Latest frame overwrites pending."""
        if self.frame_sender and self._is_on:
            self.frame_sender.submit_frame(frame)

    def clear_frames(self):
        """Immediately purge pending animation frames."""
        if self.frame_sender:
            self.frame_sender.clear()

    # ── Connection & Session Re-Auth ──────────────────────────────────────────

    async def connect(self):
        """Connects or re-authenticates with the Tapo device."""
        import src.tapo_patch  # Ensure robustness patches are active
        self.diagnostics.record_reconnect()

        # Try TPAP first (standard on L930 v1.4+ firmware), fallback to KLAP v2, then auto-guess
        attempts = [
            {"encryption_type": "tpap"},
            {"encryption_type": "klap", "encryption_version": 2},
            {},
        ]
        last_exc = None
        for opts in attempts:
            try:
                config = DeviceConnectConfiguration(
                    host=self._ip,
                    credentials=self._credentials,
                    **opts,
                )
                self._device = await connect(config)
                await self._device.update()
                self._is_on = getattr(self._device, "is_on", True)
                self._backoff_time = 0.5
                self._last_successful_response = time.time()
                self.diagnostics.set_status("connected")
                log.info(f"[{self.dev_id}] Connected to L930 at {self._ip} ({opts})")
                return self._device
            except Exception as e:
                last_exc = e
                log.debug(f"[{self.dev_id}] Connect attempt with {opts} failed: {e}")

        self.diagnostics.record_error(str(last_exc))
        raise last_exc

    async def _ensure_connected(self):
        if self._device is None and not self._reconnecting:
            await self.connect()

    async def _handle_session_reauth(self) -> bool:
        """
        Immediate re-authentication on the first session timeout (zero backoff sleep).
        Never holds the device lock during sleep.
        """
        if self._reconnecting:
            return False

        self._reconnecting = True
        try:
            self._device = None
            await self.connect()
            self._failure_streak = 0
            self._backoff_time = 0.5
            self._last_reauth_time = time.time()
            log.info(f"[{self.dev_id}] L930 session restored immediately!")
            return True
        except Exception as e:
            self._failure_streak += 1
            log.error(f"[{self.dev_id}] L930 immediate reauth failed (streak {self._failure_streak}): {e}")
            return False
        finally:
            self._reconnecting = False

    async def _handle_failure(self, exception: Exception) -> bool:
        """
        Handles network drops or session timeouts with auto-reauth and exponential backoff.
        Never holds the device lock during sleep.
        """
        is_timeout = is_session_timeout(exception)
        self.diagnostics.record_error(str(exception), is_timeout=is_timeout)

        if is_timeout and self._failure_streak == 0:
            return await self._handle_session_reauth()

        if self._reconnecting:
            return False

        self._reconnecting = True
        log.warning(
            f"[{self.dev_id}] L930 error: {exception} (timeout={is_timeout}). "
            f"Backing off for {self._backoff_time:.1f}s..."
        )

        safe_notify(f"{self.dev_id} Reconnecting", f"Session reconnecting: {exception}")

        await asyncio.sleep(self._backoff_time)
        self._backoff_time = min(30.0, self._backoff_time * 2.0)

        try:
            self._device = None  # Force fresh handshake
            await self.connect()
            self._failure_streak = 0
            self._last_reauth_time = time.time()
            log.info(f"[{self.dev_id}] L930 session restored successfully!")
            return True
        except Exception as e:
            self._failure_streak += 1
            log.error(f"[{self.dev_id}] L930 reconnect failed: {e}")
            return False
        finally:
            self._reconnecting = False

    # ── Watchdog ──────────────────────────────────────────────────────────────

    def start_watchdog(self):
        if self._loop and (self._watchdog_task is None or self._watchdog_task.done()):
            self._watchdog_task = asyncio.run_coroutine_threadsafe(
                self._watchdog_loop(), self._loop
            )

    async def _watchdog_loop(self):
        """Monitors session health every 15s, proactively refreshes session token, and recovers silent sockets."""
        while True:
            await asyncio.sleep(15.0)
            try:
                now = time.time()
                # Proactively refresh session token every 10-15 minutes before hard expiry
                if self._device is not None and (now - self._last_reauth_time > 600.0):
                    log.info(f"[{self.dev_id}] Proactively refreshing L930 session token...")
                    await self._device.update()
                    self._last_reauth_time = now
                elif self._is_on and (now - self._last_successful_response > 25.0):
                    if self._device is None or self.diagnostics.status in ("error", "timeout", "disconnected"):
                        log.info(f"[{self.dev_id}] Watchdog initiating proactive reconnect...")
                        await self.connect()
            except Exception as e:
                log.debug(f"[{self.dev_id}] Watchdog check notice: {e}")

    # ── Decoupled Transmit ────────────────────────────────────────────────────

    async def transmit_frame(self, frame: Any) -> bool:
        """
        Transmits 50-zone HSV frame to the physical L930 hardware.
        Accepts:
          - list of 50 [h, s, v] or (h, s, v) tuples
          - dict with 'segments', optional 'brightness', 'transition', '_pre_corrected'
        """
        if not self._is_on:
            return False

        trans = getattr(self, "music_transition_ms", 120)
        pre_corrected = False
        if isinstance(frame, dict):
            segs = frame.get("segments", self.last_segments)
            b = frame.get("brightness", self.last_b)
            trans = frame.get("transition", trans)
            pre_corrected = frame.get("_pre_corrected", False)
        elif isinstance(frame, list):
            segs = frame
            b = self.last_b
        else:
            return False

        effect = make_50_zone_effect(segs, master_brightness=max(0, min(100, b)), transition=trans, pre_corrected=pre_corrected)

        need_reauth = False
        async with self._lock:
            try:
                await self._ensure_connected()
                res = await self._device.set_light_effect(effect)
                self.last_segments = segs
                self._last_successful_response = time.time()
                self._failure_streak = 0
                return res.is_success() if hasattr(res, "is_success") else bool(res)
            except Exception as e:
                if is_session_timeout(e):
                    need_reauth = True
                else:
                    asyncio.create_task(self._handle_failure(e))
                    return False

        # Lock is released before reauth! Never sleep while holding the device lock.
        if need_reauth:
            log.warning(f"[{self.dev_id}] Session timed out during frame push. Re-authenticating immediately...")
            reconnected = await self._handle_session_reauth()
            if reconnected:
                async with self._lock:
                    try:
                        res = await self._device.set_light_effect(effect)
                        self._last_successful_response = time.time()
                        return res.is_success() if hasattr(res, "is_success") else bool(res)
                    except Exception:
                        return False
        return False

    # ── Priority User Controls ────────────────────────────────────────────────

    async def turn_on(self, priority: int = 0):
        self.clear_frames()
        async with self._lock:
            try:
                await self._ensure_connected()
                await self._device.turn_on()
                self._is_on = True
                self._last_successful_response = time.time()
                self.diagnostics.set_status("connected")
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def turn_off(self, priority: int = 0):
        self.clear_frames()
        self._is_on = False
        async with self._lock:
            try:
                await self._ensure_connected()
                # Clear active dynamic light effect to prevent L930 board overload
                try:
                    off_effect = LightEffect(
                        id=_STATIC_EFFECT_ID,
                        name="Off",
                        display_colors=[],
                        enable=0,
                        brightness=0,
                        custom=0,
                        segments=[0],
                        sequence=[[0, 0, 0]] * NUM_SEGMENTS,
                        type="static"
                    )
                    await self._device.set_light_effect(off_effect)
                except Exception:
                    pass
                await self._device.turn_off()
                self.last_segments = [[0, 0, 0]] * NUM_SEGMENTS
                self._last_successful_response = time.time()
                self.diagnostics.set_status("off")
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def set_brightness(self, percent: int, priority: int = 1):
        if priority > 0 and self._lock.locked():
            return
        async with self._lock:
            try:
                self.last_b = percent
                await self._ensure_connected()
                if percent == 0:
                    self.clear_frames()
                    if self._is_on:
                        try:
                            off_effect = LightEffect(
                                id=_STATIC_EFFECT_ID,
                                name="Off",
                                display_colors=[],
                                enable=0,
                                brightness=0,
                                custom=0,
                                segments=[0],
                                sequence=[[0, 0, 0]] * NUM_SEGMENTS,
                                type="static"
                            )
                            await self._device.set_light_effect(off_effect)
                        except Exception:
                            pass
                        await self._device.turn_off()
                        self._is_on = False
                else:
                    if not self._is_on:
                        await self._device.turn_on()
                        self._is_on = True
                    await self._device.set_brightness(max(1, percent))
                self._last_successful_response = time.time()
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def set_hue_saturation(self, hue: int, saturation: int, priority: int = 1):
        """Sets all 50 zones to uniform color."""
        if priority > 0 and self._lock.locked():
            return
        async with self._lock:
            try:
                self.last_h = hue
                self.last_s = saturation
                await self._ensure_connected()
                if not self._is_on:
                    await self._device.turn_on()
                    self._is_on = True
                await self._device.set_hue_saturation(hue, saturation)
                self._last_successful_response = time.time()
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def set_color_temperature(self, kelvin: int, priority: int = 1):
        if priority > 0 and self._lock.locked():
            return
        async with self._lock:
            try:
                self.last_k = kelvin
                await self._ensure_connected()
                if not self._is_on:
                    await self._device.turn_on()
                    self._is_on = True
                await self._device.set_color_temperature(kelvin)
                self._last_successful_response = time.time()
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def set_state(self, hue: int, saturation: int, brightness: int, priority: int = 1):
        """Atomically sets hue, saturation, and brightness across all 50 zones."""
        if priority > 0 and self._lock.locked():
            return
        async with self._lock:
            try:
                self.last_h = hue
                self.last_s = saturation
                self.last_b = brightness
                await self._ensure_connected()
                if not self._is_on and brightness > 0:
                    await self._device.turn_on()
                    self._is_on = True
                await self._device.set_brightness(max(1, brightness))
                await self._device.set_hue_saturation(hue, saturation)
                self._last_successful_response = time.time()
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    @property
    def current_interval(self) -> float:
        """Effective send interval in seconds accounting for AIMD network fallback."""
        if getattr(self, "frame_sender", None):
            aimd_cap = getattr(self.frame_sender, "_aimd_rate_cap", 2.0)
            return 1.0 / max(0.5, aimd_cap)
        return 0.5

    def set_output_token_authorizer(self, authorizer):
        """Install FrameBus ownership validation for non-frame output commands."""
        self._output_token_authorizer = authorizer

    def _native_effect_token_is_current(self, output_token) -> bool:
        if output_token is None:
            return True  # standalone hardware tools can use the controller without a FrameBus
        authorizer = self._output_token_authorizer
        if authorizer is None:
            return False
        try:
            producer, generation, producer_id = output_token
            return bool(authorizer(producer, generation, producer_id))
        except Exception:
            return False

    async def set_native_effect(
        self, effect: LightEffect, priority: int = 1, *, output_token=None
    ) -> bool:
        """Push a firmware effect, rejecting sessions that no longer own the strip."""
        if not self._native_effect_token_is_current(output_token):
            return False
        self.clear_frames()
        if priority > 0 and self._lock.locked():
            return False
        async with self._lock:
            try:
                await self._ensure_connected()
                # Check again after connection awaits and just before physical I/O.
                if not self._native_effect_token_is_current(output_token):
                    return False
                res = await self._device.set_light_effect(effect)
                self._is_on = True
                self._last_successful_response = time.time()
                return res.is_success() if hasattr(res, "is_success") else True
            except Exception as e:
                # Recovery still runs, but do not conceal the failed deployment from
                # the caller: the UI must not report that an effect loaded when it did not.
                asyncio.create_task(self._handle_failure(e))
                log.error(f"[{self.dev_id}] L930 firmware effect deployment failed: {e}")
                return False

    async def set_segments(
        self,
        segments_hsv: list[tuple[int, int, int] | list[int]],
        master_brightness: int = 100,
        transition: int = 0,
        priority: int = 0,
    ) -> bool:
        """Directly addresses all 50 physical zones using the decoupled transmit logic."""
        frame = {
            "segments": segments_hsv,
            "brightness": master_brightness,
            "transition": transition,
        }
        return await self.transmit_frame(frame)

    async def set_sequence_animation(
        self,
        palette_hsv: list[list[int]],
        spread: int = 10,
        direction: int = 1,
        transition: int = 500,
        name: str = "CustomSequence",
    ) -> bool:
        """Deploys an in-firmware sequence that flows across the strip automatically."""
        self.clear_frames()
        fx = LightEffect(
            id=_SEQUENCE_EFFECT_ID,
            name=name,
            display_colors=palette_hsv[:4],
            enable=1,
            brightness=100,
            custom=0,
            direction=direction,
            duration=0,
            expansion_strategy=1,
            repeat_times=0,
            segments=[0],
            sequence=palette_hsv,
            spread=spread,
            transition=transition,
            type="sequence",
        )
        return await self.set_native_effect(fx, priority=0)

    async def clean_shutdown(self):
        """
        Disables custom dynamic effects, resets hardware to normal static state,
        clears pending frames, and cleanly closes the session to prevent board overload.
        """
        self.clear_frames()
        if self._watchdog_task is not None:
            try:
                self._watchdog_task.cancel()
            except Exception:
                pass
            self._watchdog_task = None
        if self.frame_sender:
            self.frame_sender.stop()
        async with self._lock:
            try:
                if self._device is not None:
                    try:
                        off_effect = LightEffect(
                            id=_STATIC_EFFECT_ID,
                            name="Off",
                            display_colors=[],
                            enable=0,
                            brightness=0,
                            custom=0,
                            segments=[0],
                            sequence=[[0, 0, 0]] * NUM_SEGMENTS,
                            type="static"
                        )
                        await self._device.set_light_effect(off_effect)
                    except Exception:
                        pass
                    try:
                        await self._device.turn_off()
                    except Exception:
                        pass
                    if hasattr(self._device, "client") and hasattr(self._device.client, "close"):
                        try:
                            await self._device.client.close()
                        except Exception:
                            pass
            except Exception as e:
                log.debug(f"[{self.dev_id}] clean_shutdown notice: {e}")
            finally:
                self._device = None
                self._is_on = False
                self.diagnostics.set_status("disconnected")

