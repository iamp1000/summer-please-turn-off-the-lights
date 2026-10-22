from __future__ import annotations
import asyncio
import os
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Any, List
import yaml

from src.device import LightController
from src.device_l930 import L930Controller
from src.event_loop import BackgroundLoop
from src.modes import ModeManager
from src.effects import AnimationEngine
from src.effects_l930 import (
    L930EffectsEngine, EFFECT_CATALOG, CORE_EFFECTS, ADVANCED_EFFECTS,
    SEASONAL_EFFECTS, NOVELTY_EFFECTS, OCCASIONAL_EFFECTS, CREATIVE_EFFECTS,
    ACTIVE_EFFECTS, resolve_effect_alias, NATIVE_ALIASES
)
from src.music_reactive import MusicReactive, list_available_audio_devices
from src.music_reactive_l930 import MusicReactiveL930
from src.screen_sync import ScreenSync
from src.composite_sync import CompositeSystemManager
from src.automation import PresetManager, CircadianLightingEngine, WindowsPowerGuardian
from src.frame_bus import FrameBus, OutputArbiter, OutputProducer, FramePacket
from src.audio_dsp import AudioCaptureCoordinator


class DeviceContext:
    def __init__(self, dev_id: str, cfg: dict, controller: Any, loop_runner: BackgroundLoop, modes_cfg: dict, effects_cfg: dict | None = None, audio_device: str | None = None, frame_bus: Any = None, arbiter: Any = None, audio_coordinator: Any = None):
        self.dev_id = dev_id
        self.cfg = cfg
        self.name = cfg.get("name", dev_id)
        self.model = cfg.get("model", "L900").upper()
        self.ip = cfg.get("ip", "")
        self.controller = controller
        self.loop_runner = loop_runner
        self.frame_bus = frame_bus
        self.arbiter = arbiter
        
        self.state = {
            "id": self.dev_id,
            "name": self.name,
            "model": self.model,
            "ip": self.ip,
            "power": True,
            "brightness": 50,
            "active_label": "Idle",
            "connected": False,
            "effect_status": "idle",
            "last_error": None,
        }
        
        self.mode_mgr = ModeManager(
            modes_cfg, controller, loop_runner, frame_bus=frame_bus, dev_id=dev_id,
            arbiter=arbiter, on_relinquish=self.stop_all_active,
        )
        
        if self.model == "L930":
            self.fx_engine = L930EffectsEngine(controller, loop_runner, self.state, frame_bus=frame_bus, dev_id=dev_id)
            self.audio_sync = MusicReactiveL930(controller, loop_runner, self.state, preferred_device=audio_device, frame_bus=frame_bus, dev_id=dev_id)
        else:
            self.fx_engine = AnimationEngine(controller, loop_runner, self.state, frame_bus=frame_bus, dev_id=dev_id)
            self.audio_sync = MusicReactive(controller, loop_runner, self.state, preferred_device=audio_device, frame_bus=frame_bus, dev_id=dev_id)
            
        if audio_coordinator and hasattr(self.audio_sync, "set_coordinator"):
            self.audio_sync.set_coordinator(audio_coordinator)

        self.screen_sync = ScreenSync(controller, loop_runner, self.state, frame_bus=frame_bus, dev_id=dev_id)
        if hasattr(self.audio_sync, "_screen_sync"):
            self.audio_sync._screen_sync = self.screen_sync
        self.effects_cfg = effects_cfg

    def stop_all_active(self):
        self.fx_engine.stop()
        self.audio_sync.stop()
        self.screen_sync.stop()
        if hasattr(self.controller, "clear_frames"):
            self.controller.clear_frames()


class LightHub:
    """Central manager for multiple Tapo light strips (L900, L930, etc.)"""

    def __init__(self, raw_config: dict, loop_runner: BackgroundLoop):
        self.config = raw_config
        self.loop_runner = loop_runner
        self.devices: Dict[str, DeviceContext] = {}
        self._state_callbacks: List[Callable[[dict], None]] = []
        self._lock = threading.Lock()

        # Output Arbiter & Decoupled Frame Bus
        self.arbiter = OutputArbiter()
        self.frame_bus = FrameBus(self.arbiter)
        
        email = os.getenv("TAPO_EMAIL")
        password = os.getenv("TAPO_PASSWORD")
        if not email or not password:
            raise ValueError("Authentication credentials (TAPO_EMAIL, TAPO_PASSWORD) missing in .env")

        devs_cfg = raw_config.get("tapo", {}).get("devices", {})
        modes_cfg = raw_config.get("modes", {})
        effects_cfg = raw_config.get("effects", {})
        audio_cfg = raw_config.get("audio", {})
        self.audio_device = audio_cfg.get("device", "auto")
        bs = int(audio_cfg.get("blocksize", 512))
        lookahead = float(audio_cfg.get("latency_lookahead_ms", 40.0))
        self.audio_coordinator = AudioCaptureCoordinator(
            samplerate=44100,
            blocksize=bs,
            preferred_device=self.audio_device,
            lookahead_ms=lookahead,
        )

        for dev_id, d_cfg in devs_cfg.items():
            model = d_cfg.get("model", "L900").upper()
            ip = d_cfg["ip"]
            calib = d_cfg.get("calibration", {})
            if model == "L930":
                ctrl = L930Controller(ip=ip, email=email, password=password, dev_id=dev_id, loop=loop_runner.loop, calibration=calib)
            else:
                ctrl = LightController(ip=ip, email=email, password=password, dev_id=dev_id, loop=loop_runner.loop, calibration=calib)

            # One authoritative hardware-frame consumer per physical device.
            self.frame_bus.bind_device(dev_id, ctrl)

            ctx = DeviceContext(
                dev_id, d_cfg, ctrl, loop_runner, modes_cfg, effects_cfg,
                audio_device=self.audio_device, frame_bus=self.frame_bus,
                arbiter=self.arbiter, audio_coordinator=self.audio_coordinator
            )
            self.devices[dev_id] = ctx

        self.composite_mgr = CompositeSystemManager(self)
        self.preset_mgr = PresetManager()
        self.circadian_engine = CircadianLightingEngine(self)
        self.power_guardian = WindowsPowerGuardian(self)
        self.power_guardian.start()

    def start_connections(self):
        """Asynchronously connect to all devices without blocking."""
        for dev_id, ctx in self.devices.items():
            async def _connect_dev(c=ctx):
                try:
                    await c.controller.connect()
                    c.state["connected"] = True
                    c.controller.start_watchdog()
                    print(f"[{c.name}] Connected successfully at {c.ip}")
                except Exception as ex:
                    c.state["connected"] = False
                    print(f"[{c.name}] Initial connection notice: {ex}")
                self.notify_change()
            self.loop_runner.run(_connect_dev())

    def subscribe(self, callback: Callable[[dict], None]):
        with self._lock:
            self._state_callbacks.append(callback)

    def unsubscribe(self, callback: Callable[[dict], None]):
        with self._lock:
            if callback in self._state_callbacks:
                self._state_callbacks.remove(callback)

    def notify_change(self):
        st = self.get_full_state()
        with self._lock:
            cbs = list(self._state_callbacks)
        for cb in cbs:
            try:
                cb(st)
            except Exception as e:
                print(f"[Hub] State callback error: {e}")

    def get_diagnostics(self) -> dict:
        return {
            dev_id: ctx.controller.diagnostics.snapshot()
            for dev_id, ctx in self.devices.items()
        }

    def get_full_state(self) -> dict:
        return {
            "devices": {dev_id: dict(ctx.state) for dev_id, ctx in self.devices.items()},
            "diagnostics": self.get_diagnostics(),
            "modes": list(self.config.get("modes", {}).keys()),
            "effects_l900": [
                "ambient_drift", "fireplace", "golden_hour", "ocean_waves", "color_breath", "candle_flicker"
            ],
            "effects_l930": list(ACTIVE_EFFECTS),
            "effects_catalog": {name: EFFECT_CATALOG[name] for name in ACTIVE_EFFECTS if name in EFFECT_CATALOG},
            "core_effects": CORE_EFFECTS,
            "advanced_effects": ADVANCED_EFFECTS,
            "seasonal_effects": SEASONAL_EFFECTS,
            "novelty_effects": NOVELTY_EFFECTS,
            "occasional_effects": OCCASIONAL_EFFECTS,
            "creative_effects": CREATIVE_EFFECTS,
            "active_effects": ACTIVE_EFFECTS,
            "palettes": ["auto", "sunset", "forest", "fire", "pastel", "tide", "dusk", "ember", "warm_mono"],
            "visualizer_styles": [
                {"id": "party", "name": "🎉 Party"},
                {"id": "chill", "name": "☕ Chill"},
                {"id": "edm", "name": "💥 EDM"},
                {"id": "acoustic_string", "name": "🎸 Acoustic String"},
                {"id": "hydro_acoustic", "name": "💧 Hydro Acoustic"},
                {"id": "lofi_vinyl", "name": "📻 Lofi Vinyl"},
                {"id": "melodic_contour", "name": "🎼 Melodic Ribbon"},
                {"id": "bpm_resonator", "name": "🎛️ BPM Resonator"},
                {"id": "movie", "name": "🎬 Movie"},
                {"id": "pulse", "name": "⚡ Pulse"},
                {"id": "spectrum", "name": "📊 Spectrum"},
                {"id": "flow", "name": "🌊 Flow"},
                {"id": "bass_bounce", "name": "🏀 Bounce"},
                {"id": "center_burst", "name": "💫 Burst"},
                {"id": "twinkle", "name": "✨ Twinkle"},
                {"id": "bpm_resonator", "name": "🎛️ BPM Resonator"},
            ],
            "visualizer_modes": [
                {"id": "party", "name": "🎉 Party"},
                {"id": "chill", "name": "☕ Chill"},
                {"id": "edm", "name": "💥 EDM"},
                {"id": "acoustic_string", "name": "🎸 Acoustic String"},
                {"id": "hydro_acoustic", "name": "💧 Hydro Acoustic"},
                {"id": "lofi_vinyl", "name": "📻 Lofi Vinyl"},
                {"id": "melodic_contour", "name": "🎼 Melodic Ribbon"},
                {"id": "movie", "name": "🎬 Movie"},
                {"id": "pulse", "name": "⚡ Pulse"},
                {"id": "spectrum", "name": "📊 Spectrum"},
                {"id": "flow", "name": "🌊 Flow"},
                {"id": "bass_bounce", "name": "🏀 Bounce"},
                {"id": "center_burst", "name": "💫 Burst"},
                {"id": "twinkle", "name": "✨ Twinkle"},
            ],
            "visualizer_accents": [],
            "audio_device": self.audio_device,
            "composite_mode": self.composite_mgr.mode,
            "circadian_enabled": self.circadian_engine.enabled,
            "presets": list(self.preset_mgr.list_presets().keys()),
            "zone_preview": self.get_zone_preview(),
        }

    def get_zone_preview(self, dev_id: Optional[str] = None) -> Optional[List[List[int]]]:
        target_devs = [self.devices[dev_id]] if (dev_id and dev_id in self.devices) else list(self.devices.values())
        for ctx in target_devs:
            did = ctx.dev_id
            if ctx.model == "L930":
                is_fw = hasattr(ctx, "fx_engine") and getattr(ctx.fx_engine, "_active_kind", None) == "firmware"
                if not is_fw and hasattr(self, "frame_bus") and self.frame_bus:
                    packet = self.frame_bus.get_latest_frame(did)
                    if packet and packet.segments:
                        return packet.segments
                if hasattr(ctx, "fx_engine") and hasattr(ctx.fx_engine, "_active_effect_name") and ctx.fx_engine._active_effect_name:
                    t = time.monotonic() - getattr(ctx.fx_engine, "_start_time", 0.0)
                    sim = ctx.fx_engine._compute(ctx.fx_engine._active_effect_name, t)
                    if sim:
                        return sim
                if hasattr(ctx.controller, "last_segments") and ctx.controller.last_segments:
                    return ctx.controller.last_segments
            else:
                if hasattr(self, "frame_bus") and self.frame_bus:
                    packet = self.frame_bus.get_latest_frame(did)
                    if packet and packet.hsv:
                        return [list(packet.hsv)] * 50
                h = getattr(ctx.controller, "last_h", 0)
                s = getattr(ctx.controller, "last_s", 0)
                b = getattr(ctx.controller, "last_b", 50) if ctx.state.get("power", True) else 0
                return [[h, s, b]] * 50
        return None

    def set_composite_mode(self, mode: str):
        self.composite_mgr.set_mode(mode)
        self.notify_change()

    def toggle_circadian(self) -> bool:
        if self.circadian_engine.enabled:
            self.circadian_engine.stop()
        else:
            self.circadian_engine.start()
        self.notify_change()
        return self.circadian_engine.enabled

    def apply_preset(self, name: str) -> bool:
        success = self.preset_mgr.apply_preset(name, self)
        if success:
            self.notify_change()
        return success

    def save_preset(self, name: str) -> dict:
        res = self.preset_mgr.save_current_as_preset(name, self)
        self.notify_change()
        return res

    def get_audio_devices(self) -> List[Dict[str, Any]]:
        return list_available_audio_devices()

    def set_audio_device(self, device_name: str):
        self.audio_device = device_name
        audio_labels = ("Audio Reactive", "Audio Spectrum (IC)", "Audio Error")
        audio_requested = any(
            ctx.audio_sync.is_running() or ctx.state.get("active_label") in audio_labels
            for ctx in self.devices.values()
        )
        if hasattr(self, "audio_coordinator") and self.audio_coordinator:
            self.audio_coordinator.preferred_device = device_name
            # Also restart an errored/stopped capture worker when audio mode remains selected.
            if audio_requested:
                self.audio_coordinator.stop()
                self.audio_coordinator.start()
        for ctx in self.devices.values():
            if hasattr(ctx.audio_sync, "set_device"):
                ctx.audio_sync.set_device(device_name)
        # Persist to config.yaml safely
        try:
            cfg_path = Path(__file__).resolve().parent.parent / "config.yaml"
            with open(cfg_path, "r", encoding="utf-8") as f:
                c = yaml.safe_load(f) or {}
            if "audio" not in c:
                c["audio"] = {}
            c["audio"]["device"] = device_name
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(c, f, sort_keys=False)
            print(f"[Hub] Audio device preference saved: {device_name}")
        except Exception as e:
            print(f"[Hub] Failed to save audio device in config: {e}")

    def get_audio_telemetry(self) -> dict:
        result = {}
        coord_st = None
        coordinator = getattr(self, "audio_coordinator", None)
        if coordinator and getattr(coordinator, "status", None) == "active":
            coord_st, _ = coordinator.get_latest_state()
        coord_status = getattr(coordinator, "status", "not_configured") if coordinator else "not_configured"
        coord_error = getattr(coordinator, "last_error", None) if coordinator else None

        for dev_id, ctx in self.devices.items():
            sync = ctx.audio_sync
            analyzer = getattr(sync, "_analyzer", None)
            st = getattr(sync, "latest_music_state", None) or coord_st or (analyzer.state if analyzer else None)

            # Determine noise floor from calibrator if available
            calibrator = getattr(analyzer, "calibrator", None) or getattr(sync, "_calibrator", None)
            noise_floor_val = float(getattr(calibrator, "p5", getattr(calibrator, "noise_floor", 0.005)))

            # Get outgoing send FPS from controller diagnostics
            diag = getattr(getattr(ctx, "controller", None), "diagnostics", None)
            tx_fps = float(getattr(diag, "send_fps", 0.0))

            raw_spectrum = getattr(sync, "latest_spectrum", None)
            if not raw_spectrum and st is not None and hasattr(st, "bands") and len(st.bands) > 0:
                raw_spectrum = [float(x) for x in st.bands]
            if not raw_spectrum:
                raw_spectrum = [0.0] * 50

            uses_shared_capture = coordinator is not None and getattr(sync, "_coordinator", None) is coordinator
            capture_status = (
                coord_status if uses_shared_capture
                else ("error" if getattr(sync, "_last_error", None)
                      else ("active" if sync.is_running() else "stopped"))
            )
            capture_error = coord_error if uses_shared_capture else getattr(sync, "_last_error", None)
            audio_active = sync.is_running() and (
                not uses_shared_capture or capture_status == "active"
            )

            result[dev_id] = {
                "active": audio_active,
                "capture_status": capture_status,
                "capture_error": capture_error,
                "audio_source": (
                    getattr(coordinator, "active_device_name", None) or getattr(coordinator, "preferred_device", None)
                    if uses_shared_capture else getattr(sync, "_preferred_device", None)
                ),
                "renderer_running": bool(sync.is_running()),
                "signal_active": bool(st is not None and not getattr(st, "silent", True) and float(getattr(st, "energy", 0.0)) >= 0.035),
                "spectrum": [float(x) for x in raw_spectrum],
                "bpm": float(getattr(st, "bpm", getattr(sync, "estimated_bpm", 120.0))),
                "confidence": float(getattr(st, "bpm_confidence", getattr(sync, "confidence", 0.0))),
                "onset": float(getattr(st, "onset", 0.0)),
                "kick": float(getattr(st, "kick", 0.0)),
                "snare": float(getattr(st, "snare", 0.0)),
                "hat": float(getattr(st, "hat", 0.0)),
                "noise_floor": noise_floor_val,
                "send_fps": tx_fps,
                "beat_phase": getattr(st, "beat_phase", 0.0) if st else 0.0,
                "bar_pos": getattr(st, "bar_pos", 0) if st else 0,
                "energy": getattr(st, "energy", 0.0) if st else 0.0,
                "energy_trend": getattr(st, "energy_trend", 0.0) if st else 0.0,
                "centroid": getattr(st, "centroid", 1000.0) if st else 1000.0,
                "intensity": getattr(st, "intensity", 0.0) if st else 0.0,
                "tension": getattr(st, "tension", 0.0) if st else 0.0,
                "impact": getattr(st, "impact", 0.0) if st else 0.0,
                "section": getattr(st.section, "value", "SILENT") if (st and hasattr(st, "section")) else "SILENT",
                "drop_strength": getattr(st, "drop_strength", 0.0) if st else 0.0,
                "key_hue": getattr(st, "key_hue", 215.0) if st else 215.0,
                "mode": getattr(st, "mode", "major") if st else "major",
                "palette": getattr(st, "palette", []) if st else [],
                "harmonic_ratio": getattr(st, "harmonic_ratio", 0.5) if st else 0.5,
                "sensitivity": getattr(sync, "sensitivity", 1.0),
                "lookahead_ms": getattr(sync, "latency_lookahead_ms", 40.0),
                "style": getattr(sync, "style_name", getattr(sync, "_mode", "hybrid")),
            }
        return result

    def set_effect_params(self, dev_id: str, **kwargs):
        """Passes effect tuning parameters (speed, brightness, palette_name, tail_length, etc.) to target engines."""
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            if hasattr(ctx, "fx_engine") and hasattr(ctx.fx_engine, "set_parameters"):
                ctx.fx_engine.set_parameters(**kwargs)
        self.notify_change()

    def set_audio_sensitivity(self, dev_id: str, val: float):
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            if hasattr(ctx.audio_sync, "set_sensitivity"):
                ctx.audio_sync.set_sensitivity(val)
        self.notify_change()

    def set_audio_lookahead(self, dev_id: str, val: float):
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            if hasattr(ctx.audio_sync, "set_latency_lookahead"):
                ctx.audio_sync.set_latency_lookahead(val)
        self.notify_change()

    def _resolve_targets(self, dev_id: str) -> List[DeviceContext]:
        if dev_id == "all":
            return list(self.devices.values())
        if dev_id in self.devices:
            return [self.devices[dev_id]]
        return list(self.devices.values())[:1]

    def set_power(self, dev_id: str, state: bool | None = None):
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            new_power = not ctx.state["power"] if state is None else state
            ctx.state["power"] = new_power
            # Revoke the previous session and clear its queue before issuing power commands.
            if not new_power:
                self.arbiter.claim_output(
                    ctx.dev_id, OutputProducer.IDLE,
                    on_relinquish=ctx.stop_all_active, renew=True,
                )
                ctx.state["active_label"] = "Off"
                self.loop_runner.run(ctx.controller.turn_off(priority=0))
            else:
                self.arbiter.claim_output(
                    ctx.dev_id, OutputProducer.STATIC,
                    on_relinquish=ctx.stop_all_active, renew=True,
                )
                ctx.state["active_label"] = "Idle"
                self.loop_runner.run(ctx.controller.turn_on(priority=0))
        self.notify_change()

    def set_brightness(self, dev_id: str, val: int):
        """Adjust brightness through the active producer, never via a competing hardware write."""
        val = max(1, min(100, int(val)))
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            ctx.state["brightness"] = val

            if hasattr(ctx, "fx_engine") and hasattr(ctx.fx_engine, "set_parameters"):
                ctx.fx_engine.set_parameters(brightness=val)

            # In the live application every device is bound to FrameBus. Dynamic
            # producers consume the updated app state/engine parameter and publish
            # their next frame; they must not be overridden by a direct brightness API.
            if getattr(self, "frame_bus", None) and getattr(self, "arbiter", None):
                owner = self.arbiter.get_owner(ctx.dev_id)
                if owner != OutputProducer.STATIC:
                    continue

                token = self.frame_bus.capture_token(ctx.dev_id, OutputProducer.STATIC)
                if token is None:
                    continue
                generation, producer_id = token
                current = self.frame_bus.get_latest_frame(ctx.dev_id)

                if ctx.model == "L930":
                    segments = current.segments if current and current.segments else getattr(ctx.controller, "last_segments", None)
                    if not segments:
                        continue
                    packet = FramePacket(
                        dev_id=ctx.dev_id,
                        producer=OutputProducer.STATIC,
                        segments=[list(zone) for zone in segments],
                        brightness=val,
                        transition=current.transition if current else 600,
                        pre_corrected=current.pre_corrected if current else False,
                        generation=generation,
                        producer_id=producer_id,
                    )
                else:
                    if current and current.hsv:
                        h, s, _old_b = current.hsv[:3]
                    else:
                        h = getattr(ctx.controller, "last_h", 0)
                        s = getattr(ctx.controller, "last_s", 0)
                    packet = FramePacket(
                        dev_id=ctx.dev_id,
                        producer=OutputProducer.STATIC,
                        hsv=(int(h), int(s), val),
                        brightness=val,
                        transition=current.transition if current else 600,
                        generation=generation,
                        producer_id=producer_id,
                    )
                self.frame_bus.publish(packet)
            else:
                # Compatibility for isolated controller use without the hub's FrameBus.
                self.loop_runner.run(ctx.controller.set_brightness(val, priority=1))
        self.notify_change()

    def apply_mode(self, dev_id: str, mode_name: str):
        targets = self._resolve_targets(dev_id)
        mode_data = self.config.get("modes", {}).get(mode_name, {})
        for ctx in targets:
            self.arbiter.claim_output(
                ctx.dev_id, OutputProducer.STATIC,
                on_relinquish=ctx.stop_all_active, renew=True,
            )
            output_token = self.frame_bus.capture_token(ctx.dev_id, OutputProducer.STATIC)
            ctx.stop_all_active()
            ctx.state["power"] = True
            ctx.state["active_label"] = mode_name
            # ModeManager emits either the L930 spatial frame or the L900 crossfade
            # frames, all tagged with this ownership generation and delivered once.
            self.loop_runner.run(
                ctx.mode_mgr._apply_async(mode_data, output_token=output_token)
            )
        self.notify_change()

    def apply_effect(self, dev_id: str, effect_name: str) -> bool:
        targets = self._resolve_targets(dev_id)

        # Validate every target before stopping its current producer. A bad
        # key must not turn off music/screen mode and then claim the effect loaded.
        for ctx in targets:
            if ctx.model == "L930":
                key = resolve_effect_alias(effect_name)
                if key not in EFFECT_CATALOG:
                    ctx.state["effect_status"] = "failed"
                    ctx.state["last_error"] = f"Unknown L930 effect: {effect_name!r}"
                    self.notify_change()
                    raise ValueError(f"Unknown L930 effect: {effect_name!r}")

        for ctx in targets:
            ctx.state["effect_status"] = "requested"
            ctx.state["last_error"] = None
            self.arbiter.claim_output(ctx.dev_id, OutputProducer.EFFECT, on_relinquish=ctx.fx_engine.stop, renew=True)
            ctx.audio_sync.stop()
            ctx.screen_sync.stop()
            cur_b = ctx.state.get("brightness", 50)
            if hasattr(ctx, "fx_engine") and hasattr(ctx.fx_engine, "set_parameters"):
                ctx.fx_engine.set_parameters(brightness=cur_b)
            if ctx.model == "L930":
                ctx.state["effect_status"] = "sent"
                started = ctx.fx_engine.start(effect_name, brightness=cur_b)
                if started is False:
                    ctx.state["effect_status"] = "failed"
                    err_msg = getattr(ctx.fx_engine, "_last_error", None) or f"Failed to start L930 effect {effect_name!r}"
                    ctx.state["last_error"] = err_msg
                    self.notify_change()
                    raise RuntimeError(err_msg)
                ctx.state["effect_status"] = "accepted"
                ctx.state["last_error"] = None
            else:
                eff_cfg = dict(self.config.get("effects", {}).get(effect_name, {}))
                eff_cfg["name"] = effect_name
                ctx.fx_engine.start(eff_cfg)
                ctx.state["effect_status"] = "accepted"
                ctx.state["last_error"] = None
            ctx.state["power"] = True
            ctx.state["active_label"] = effect_name
        self.notify_change()
        return True

    def retry_audio_capture(self, dev_id: str):
        """Restart shared loopback capture and the selected light renderer."""
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            try:
                ctx.audio_sync.stop()
            except Exception:
                pass
        coordinator = getattr(self, "audio_coordinator", None)
        if coordinator:
            coordinator.stop()
        # All consumers share one analyzer; stopping the selected renderers ensures
        # toggle_music starts fresh AUDIO ownership sessions rather than switching them off.
        self.toggle_music(dev_id)

    def toggle_music(self, dev_id: str):
        targets = self._resolve_targets(dev_id)
        l900_mode = self.config.get("audio", {}).get("l900_mode", "style")
        
        # Check if any target is currently running audio
        any_running = any(ctx.audio_sync.is_running() for ctx in targets)
        
        l930_ctx = next((c for c in self.devices.values() if c.model == "L930"), None)
        l900_ctx = next((c for c in self.devices.values() if c.model != "L930"), None)

        if any_running:
            for ctx in targets:
                ctx.audio_sync.stop()
                # Transition to an authorized static-black scene rather than queueing
                # an AUDIO black frame that would be invalidated on release.
                self.arbiter.claim_output(
                    ctx.dev_id, OutputProducer.STATIC,
                    on_relinquish=ctx.stop_all_active, renew=True,
                )
                self.frame_bus.publish(FramePacket(
                    dev_id=ctx.dev_id,
                    producer=OutputProducer.STATIC,
                    segments=[[0, 0, 0]] * 50 if ctx.model == "L930" else None,
                    hsv=(0, 0, 0) if ctx.model != "L930" else None,
                    brightness=0,
                    transition=250,
                ))
                ctx.state["active_label"] = "Idle"
            if self.composite_mgr.is_active():
                self.composite_mgr.stop()
            if not any(ctx.audio_sync.is_running() for ctx in self.devices.values()):
                if hasattr(self, "audio_coordinator") and self.audio_coordinator:
                    self.audio_coordinator.stop()
        else:
            if hasattr(self, "audio_coordinator") and self.audio_coordinator:
                self.audio_coordinator.start()
            if l930_ctx and l930_ctx in targets:
                l930_ctx.fx_engine.stop()
                l930_ctx.screen_sync.stop()
                self.arbiter.claim_output(l930_ctx.dev_id, OutputProducer.AUDIO, on_relinquish=l930_ctx.audio_sync.stop, renew=True)
                l930_ctx.state["power"] = True
                l930_ctx.state["active_label"] = "Audio Spectrum (IC)"
                l930_ctx.audio_sync.start()

                if l900_ctx and l900_ctx in targets:
                    l900_ctx.fx_engine.stop()
                    l900_ctx.screen_sync.stop()
                    if l900_mode == "composite":
                        self.composite_mgr.set_mode("average")
                        l900_ctx.state["power"] = True
                        l900_ctx.state["active_label"] = "Composite Follower"
                    else:
                        if hasattr(l930_ctx.audio_sync, "get_analyzer"):
                            l900_ctx.audio_sync.set_shared_analyzer(l930_ctx.audio_sync.get_analyzer())
                        self.arbiter.claim_output(l900_ctx.dev_id, OutputProducer.AUDIO, on_relinquish=l900_ctx.audio_sync.stop, renew=True)
                        l900_ctx.state["power"] = True
                        l900_ctx.state["active_label"] = "Audio Reactive"
                        l900_ctx.audio_sync.start()
            else:
                for ctx in targets:
                    ctx.fx_engine.stop()
                    ctx.screen_sync.stop()
                    self.arbiter.claim_output(ctx.dev_id, OutputProducer.AUDIO, on_relinquish=ctx.audio_sync.stop, renew=True)
                    ctx.state["power"] = True
                    ctx.state["active_label"] = "Audio Reactive"
                    ctx.audio_sync.start()
        self.notify_change()

    def set_music_mode(self, dev_id: str, mode: str):
        targets = self._resolve_targets(dev_id)
        is_movie = (mode.lower() == "movie")
        for ctx in targets:
            if hasattr(ctx.audio_sync, "set_style"):
                ctx.audio_sync.set_style(mode)
            elif hasattr(ctx.audio_sync, "set_mode"):
                ctx.audio_sync.set_mode(mode)
            # When Movie mode is active, make sure ScreenSync is capturing to feed latest_screen_data
            if is_movie:
                if hasattr(ctx, "screen_sync") and not ctx.screen_sync.is_running():
                    ctx.screen_sync.start()
                if hasattr(ctx.audio_sync, "_screen_sync"):
                    ctx.audio_sync._screen_sync = ctx.screen_sync
            if hasattr(ctx, "screen_sync"):
                ctx.audio_sync._screen_sync = ctx.screen_sync
        self.notify_change()

    def set_accent(self, dev_id: str, name: str, enabled: bool):
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            if hasattr(ctx.audio_sync, "set_accent"):
                ctx.audio_sync.set_accent(name, enabled)
        self.notify_change()

    def set_style_params(self, dev_id: str, speed: float | None = None, intensity: float | None = None, smoothing: float | None = None, palette_mode: str | None = None):
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            if hasattr(ctx.audio_sync, "set_style_params"):
                ctx.audio_sync.set_style_params(speed=speed, intensity=intensity, smoothing=smoothing, palette_mode=palette_mode)
        self.notify_change()

    def toggle_screen(self, dev_id: str):
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            ctx.fx_engine.stop()
            ctx.audio_sync.stop()
            if ctx.screen_sync.is_running():
                ctx.screen_sync.stop()
                self.arbiter.release_output(ctx.dev_id, OutputProducer.SCREEN_SYNC)
                ctx.state["active_label"] = "Idle"
            else:
                self.arbiter.claim_output(ctx.dev_id, OutputProducer.SCREEN_SYNC, on_relinquish=ctx.screen_sync.stop, renew=True)
                ctx.state["power"] = True
                ctx.state["active_label"] = "Screen Reactive"
                ctx.screen_sync.start()
        self.notify_change()

    def apply_custom_color(self, dev_id: str, h: int, s: int, v: int):
        targets = self._resolve_targets(dev_id)
        for ctx in targets:
            self.arbiter.claim_output(ctx.dev_id, OutputProducer.STATIC, on_relinquish=ctx.stop_all_active, renew=True)
            output_token = self.frame_bus.capture_token(ctx.dev_id, OutputProducer.STATIC)
            ctx.stop_all_active()
            ctx.state["power"] = True
            ctx.state["active_label"] = "Custom Wheel"
            ctx.state["brightness"] = v
            if ctx.model == "L930":
                packet = FramePacket(
                    dev_id=ctx.dev_id,
                    producer=OutputProducer.STATIC,
                    segments=[[h, s, v]] * 50,
                    brightness=v,
                    transition=600,
                    generation=output_token[0] if output_token else None,
                    producer_id=output_token[1] if output_token else None,
                )
            else:
                packet = FramePacket(
                    dev_id=ctx.dev_id,
                    producer=OutputProducer.STATIC,
                    hsv=(h, s, v),
                    brightness=v,
                    transition=600,
                    generation=output_token[0] if output_token else None,
                    producer_id=output_token[1] if output_token else None,
                )

            async def _apply_custom_output(c=ctx, p=packet):
                await c.controller.turn_on(priority=0)
                self.frame_bus.publish(p)

            self.loop_runner.run(_apply_custom_output())
        self.notify_change()

    def shutdown(self):
        """Clean shutdown: stops all animation threads and turns off all strips without queue residue."""
        if hasattr(self, "audio_coordinator") and self.audio_coordinator:
            self.audio_coordinator.stop()
        self.composite_mgr.stop()
        self.circadian_engine.stop()
        self.power_guardian.stop()
        for ctx in self.devices.values():
            ctx.stop_all_active()
            try:
                if hasattr(ctx.controller, "clean_shutdown"):
                    fut = self.loop_runner.run(ctx.controller.clean_shutdown())
                    fut.result(timeout=3.0)
                else:
                    fut = self.loop_runner.run(ctx.controller.turn_off(priority=0))
                    fut.result(timeout=2.0)
            except Exception:
                pass
