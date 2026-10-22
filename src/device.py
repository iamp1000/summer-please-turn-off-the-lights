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

from src.diagnostics import DeviceDiagnostics
from src.frame_sender import LatestFrameSender
from src.logger import log


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


class LightController:
    """
    Controls a single Tapo color light strip / bulb (L900).
    Features:
      - Latest-frame-wins decoupled async sender
      - Full telemetry & diagnostics (FPS, RTT, drops, errors)
      - Automatic re-authentication on session timeout with exponential backoff
      - Resilient watchdog for automatic background recovery
    """

    def __init__(
        self,
        ip: str,
        email: str,
        password: str,
        dev_id: str = "strip1",
        loop: Optional[asyncio.AbstractEventLoop] = None,
        calibration: Optional[Dict[str, Any]] = None,
    ):
        self.dev_id = dev_id
        self._ip = ip
        self._credentials = AuthCredential(email, password)
        self._device = None
        self._loop = loop

        # Reliability & Locks
        self._lock = asyncio.Lock()
        self._reconnecting = False
        self._backoff_time = 0.5
        self._failure_streak = 0
        self._last_successful_response = 0.0
        self._last_reauth_time = time.time()

        calib = calibration or {}
        curve_exp = calib.get("curve_exponent", 1.8) if isinstance(calib, dict) else getattr(calib, "curve_exponent", 1.8)
        wb = calib.get("white_balance", [1.0, 0.92, 0.85]) if isinstance(calib, dict) else getattr(calib, "white_balance", [1.0, 0.92, 0.85])
        min_b = calib.get("min_brightness", 1) if isinstance(calib, dict) else getattr(calib, "min_brightness", 1)
        trans_ms = calib.get("transition_ms", 0) if isinstance(calib, dict) else getattr(calib, "transition_ms", 0)
        self.default_transition_ms = trans_ms
        self._max_updates_per_s = float(calib.get("max_updates_per_s", 5.0) if isinstance(calib, dict) else 5.0)
        self._min_zone_delta = float(calib.get("min_zone_delta", 3.0) if isinstance(calib, dict) else 3.0)

        from src.pipeline import RenderPipeline
        self._render_pipeline = RenderPipeline(
            curve_exponent=curve_exp,
            white_balance=wb,
            min_brightness=min_b,
            transition_ms=trans_ms,
            master_ceiling=1.0,
        )

        # State tracking for crossfades
        self.last_h = 0
        self.last_s = 0
        self.last_b = 50
        self.last_k = 4000
        self._is_on = True

        # Telemetry & Frame Sender
        self.diagnostics = DeviceDiagnostics(dev_id=self.dev_id)
        self.frame_sender: Optional[LatestFrameSender] = None
        self._frame_authorizer: Optional[Callable[[Any], bool]] = None
        if self._loop:
            self._init_sender(self._loop)

        # Watchdog task
        self._watchdog_task: Optional[asyncio.Task] = None

    def _init_sender(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        if self.frame_sender is None:
            max_ups = getattr(self, "_max_updates_per_s", 5.0)
            min_delta = getattr(self, "_min_zone_delta", 3.0)
            self.frame_sender = LatestFrameSender(
                dev_id=self.dev_id,
                transmit_fn=self.transmit_frame,
                diagnostics=self.diagnostics,
                loop=loop,
                max_updates_per_s=max_ups,
                min_zone_delta=min_delta,
            )
            self.frame_sender.start()

    def set_frame_authorizer(self, authorizer: Optional[Callable[[Any], bool]]):
        """Install FrameBus ownership validation at the final hardware boundary."""
        self._frame_authorizer = authorizer

    def _frame_is_authorized(self, frame: Any) -> bool:
        authorizer = self._frame_authorizer
        if authorizer is None:
            return True
        try:
            return bool(authorizer(frame))
        except Exception:
            return False

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

        # Try KLAP v2 first (standard on L900), fallback to TPAP, then auto-guess
        attempts = [
            {"encryption_type": "klap", "encryption_version": 2},
            {"encryption_type": "tpap"},
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
                self._backoff_time = 0.5  # Reset backoff on success
                self._last_successful_response = time.time()
                self.diagnostics.set_status("connected")
                log.info(f"[{self.dev_id}] Connected to L900 at {self._ip} ({opts})")
                return self._device
            except Exception as e:
                last_exc = e
                log.debug(f"[{self.dev_id}] Connect attempt with {opts} failed: {e}")

        self.diagnostics.record_error(str(last_exc))
        raise last_exc

    async def _ensure_connected(self):
        if self._device is None and not self._reconnecting:
            await self.connect()

    async def _send_combined_hsb(self, h: int, s: int, b: int) -> bool:
        """
        Sends Hue, Saturation, and Brightness in a SINGLE request via
        LightColorDeviceInfoParams on self._device.client.
        Falls back to separate calls if combined setter is not supported (e.g. test mocks).
        """
        if hasattr(self._device, "client") and hasattr(self._device.client, "set_device_info"):
            try:
                from plugp100.api.requests.set_device_info.set_light_color_info_params import LightColorDeviceInfoParams
                params = LightColorDeviceInfoParams(hue=h, saturation=s, brightness=b, color_temp=0)
            except ImportError:
                params = None

            if params is not None:
                res = await self._device.client.set_device_info(params)
                return res.is_success() if hasattr(res, "is_success") else bool(res)

        if hasattr(self._device, "set_hue_saturation"):
            await self._device.set_hue_saturation(h, s)
        if hasattr(self._device, "set_brightness"):
            await self._device.set_brightness(b)
        return True

    async def _handle_session_reauth(self) -> bool:
        """
        Immediate re-authentication on the first session timeout (zero backoff sleep).
        Only introduces exponential backoff after repeated connection failures.
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
            log.info(f"[{self.dev_id}] Session restored immediately!")
            return True
        except Exception as e:
            self._failure_streak += 1
            log.error(f"[{self.dev_id}] Reauth attempt failed (streak {self._failure_streak}): {e}")
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
            f"[{self.dev_id}] Device error: {exception} (timeout={is_timeout}). "
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
            log.info(f"[{self.dev_id}] Session restored successfully!")
            return True
        except Exception as e:
            self._failure_streak += 1
            log.error(f"[{self.dev_id}] Reconnection attempt failed: {e}")
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
                    log.info(f"[{self.dev_id}] Proactively refreshing L900 session token...")
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
        Transmits a rendered frame to the physical device.
        Accepts:
          - tuple (h, s, b)
          - dict with 'h', 's', 'b' keys and optional '_pre_corrected'
        """
        if not self._is_on or not self._frame_is_authorized(frame):
            return False

        pre_corrected = False
        if isinstance(frame, dict):
            h = frame.get("h", self.last_h)
            s = frame.get("s", self.last_s)
            b = frame.get("b", self.last_b)
            pre_corrected = frame.get("_pre_corrected", False)
        elif isinstance(frame, (tuple, list)) and len(frame) >= 3:
            h, s, b = frame[0], frame[1], frame[2]
        else:
            return False

        if pre_corrected:
            hc = int(h) % 360
            sc = max(0, min(100, int(s)))
            gamma_b = max(0, min(100, int(b)))
        else:
            hc, sc, gamma_b = self._render_pipeline.correct_hsv_tuple(int(h), int(s), int(b))

        need_reauth = False
        async with self._lock:
            try:
                await self._ensure_connected()
                if not self._frame_is_authorized(frame):
                    return False
                await self._send_combined_hsb(hc, sc, gamma_b)
                self.last_h = hc
                self.last_s = sc
                self.last_b = gamma_b
                self._last_successful_response = time.time()
                self._failure_streak = 0
                return True
            except Exception as e:
                if is_session_timeout(e):
                    need_reauth = True
                else:
                    asyncio.create_task(self._handle_failure(e))
                    return False

        # Lock is released before reauth! Never sleep while holding the device lock.
        if need_reauth:
            log.warning(f"[{self.dev_id}] Session timed out during frame send. Re-authenticating immediately...")
            reconnected = await self._handle_session_reauth()
            if reconnected:
                # Retry frame once with identical computed values
                async with self._lock:
                    try:
                        if not self._frame_is_authorized(frame):
                            return False
                        await self._send_combined_hsb(hc, sc, gamma_b)
                        self.last_h = hc
                        self.last_s = sc
                        self.last_b = gamma_b
                        self._last_successful_response = time.time()
                        return True
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
                await self._device.turn_off()
                self._last_successful_response = time.time()
                self.diagnostics.set_status("off")
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def toggle(self, priority: int = 1):
        if priority > 0 and self._lock.locked():
            return
        if self._is_on:
            await self.turn_off(priority=priority)
        else:
            await self.turn_on(priority=priority)

    async def set_brightness(self, percent: int, priority: int = 1):
        """percent: 0-100"""
        if priority > 0 and self._lock.locked():
            return
        async with self._lock:
            try:
                self.last_b = percent
                await self._ensure_connected()
                if percent == 0:
                    if self._is_on:
                        await self._device.turn_off()
                        self._is_on = False
                else:
                    if not self._is_on:
                        await self._device.turn_on()
                        self._is_on = True
                    await self._device.set_brightness(max(1, min(100, percent)))
                self._last_successful_response = time.time()
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def set_hue_saturation(self, hue: int, saturation: int, priority: int = 1):
        if priority > 0 and self._lock.locked():
            return
        async with self._lock:
            try:
                self.last_h = hue
                self.last_s = saturation
                await self._ensure_connected()
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
                self.last_h = 0
                self.last_s = 0
                await self._ensure_connected()
                await self._device.set_color_temperature(kelvin)
                self._last_successful_response = time.time()
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def set_state(self, hue: int, saturation: int, brightness: int, priority: int = 1):
        """Atomically sets hue, saturation, and brightness via single combined request."""
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

                if brightness == 0:
                    await self._device.turn_off()
                    self._is_on = False
                else:
                    await self._send_combined_hsb(hue, saturation, max(1, min(100, brightness)))
                self._last_successful_response = time.time()
            except Exception as e:
                asyncio.create_task(self._handle_failure(e))

    async def clean_shutdown(self):
        """
        Cleanly turns off device, cancels pending tasks, and closes network session.
        """
        async with self._lock:
            try:
                if self._device is not None:
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
