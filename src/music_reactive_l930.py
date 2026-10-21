from __future__ import annotations

import asyncio
import math
import random
import threading
import time
from collections import deque
import numpy as np
import soundcard as sc
from src.music_reactive import get_audio_input_source
from src.audio_dsp import SpectralFluxOnsetDetector, BPMTracker, DynamicAudioCalibrator, MusicAnalyzer, MusicState, Section
from src.visual_styles import get_visual_style, STYLE_REGISTRY, create_style_instances, AccentCompositor, DirectorStyle, sample_palette_oklab
from src.frame_bus import FramePacket, OutputProducer
from src.music_dynamics import MusicBrightnessFloor, music_is_genuinely_active, fade_segments, silence_fade_duration, effective_send_rate
from src.music_dynamics import MusicBrightnessFloor, music_is_genuinely_active, fade_segments, silence_fade_duration

NUM_SEGMENTS = 50

# Logarithmic frequency boundaries for 50 zones (20 Hz to 16,000 Hz)
FREQS_50 = np.logspace(np.log10(20), np.log10(16000), NUM_SEGMENTS + 1)
BAND_LIMITS = [(FREQS_50[i], FREQS_50[i + 1]) for i in range(NUM_SEGMENTS)]

# Full instrument spectrum color mapping across the 50 zones:
# Zones 0-10: Bass drum & sub (Crimson/Red)
# Zones 11-22: Bass guitar & rhythm keys (Amber/Gold)
# Zones 23-35: Lead vocals & guitars (Emerald/Cyan)
# Zones 36-44: High synths & horns (Royal Blue)
# Zones 45-49: Hi-hats & cymbals (Violet/Magenta)
ZONE_HUES = []
for i in range(NUM_SEGMENTS):
    t = i / (NUM_SEGMENTS - 1)
    if t < 0.22:
        h = int((t / 0.22) * 25)
    elif t < 0.44:
        h = int(25 + ((t - 0.22) / 0.22) * 30)
    elif t < 0.66:
        h = int(65 + ((t - 0.44) / 0.22) * 85)
    elif t < 0.85:
        h = int(175 + ((t - 0.66) / 0.19) * 60)
    else:
        h = int(260 + ((t - 0.85) / 0.15) * 60)
    ZONE_HUES.append(h % 360)


class MusicReactiveL930:
    """
    True 50-Zone WRGBIC Audio-Reactive Visualizer Engine for Tapo L930.
    Default state when quiet: STRICTLY 100% OFF (0% brightness).
    Features 7 distinct tailored profiles with individual IC zone mapping:
      1. single_color  - Pure single color gravimeter beat pulse (no random cycling)
      2. edm_drop      - Extreme white-flash drop strike & cascading outward shockwave
      3. lively        - WLED GEQ 50-band instrument equalizer (each instrument on its own LEDs)
      4. upbeat        - WLED Freqwave rhythmic pop pulse and bounce
      5. calm          - WLED Liquid Puddle warm soothing lo-fi relaxation
      6. classical     - Physical 50-zone acoustic orchestral stage (cellos, piano, violins)
      7. movie         - Netflix & movie cinematic dialogue center bias & sub-bass rumble
    """

    def __init__(self, controller, loop_runner, app_state, samplerate=44100, blocksize=512, preferred_device: str | None = None, frame_bus: Any = None, dev_id: str = "strip2"):
        self._ctrl = controller
        self._loop_runner = loop_runner
        self._app_state = app_state
        self._frame_bus = frame_bus
        self._dev_id = dev_id
        self._output_token: Optional[tuple[int, str]] = None
        self._sr = samplerate
        self._samplerate = samplerate
        self._bs = blocksize
        self._preferred_device = preferred_device

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._run_generation = 0
        self._worker_context = threading.local()
        self._last_error: Optional[str] = None
        self._updater_future = None

        self._levels = np.zeros(NUM_SEGMENTS, dtype=np.float32)
        self._rendered_segs = [[0, 0, 0] for _ in range(NUM_SEGMENTS)]
        self._target_segs: list[list[int]] | None = None

        # Unified Two-Axis MusicAnalyzer & VisualStyle Engine
        self._analyzer = MusicAnalyzer(samplerate=self._sr, blocksize=self._bs, sensitivity=1.0)
        self._styles = create_style_instances()
        self._compositor = AccentCompositor()
        self.style_name = "auto"
        self._visual_mode = "auto"
        self.latest_music_state: MusicState | None = None
        self._coordinator: Any = None

        from src.pipeline import RenderPipeline
        self._pipeline = RenderPipeline(gamma=2.2, r_calib=1.0, g_calib=0.96, b_calib=0.90)
        self._silence_duration = 0.0
        self._powered_down_for_silence = False
        self._brightness_floor = MusicBrightnessFloor()
        self._last_active_segs: Optional[list[list[int]]] = None
        self._latency_lookahead_ms = 0.0  # Kept at 0 by default; true lockstep achieved via measured output delay

        # DSP Pipeline: AGC, Onset Detection & Real-Time Beat Tracking
        self._calibrator = DynamicAudioCalibrator(sensitivity=1.0)
        self._onset_detector = SpectralFluxOnsetDetector(num_bins=NUM_SEGMENTS, threshold_mult=1.35)
        self._bpm_tracker = BPMTracker()
        self.latest_spectrum = [0.0] * NUM_SEGMENTS
        self.estimated_bpm = 120.0
        self.confidence = 0.0

        # Dynamics & AGC state
        self._rolling_peak = 0.15
        self._bass_history = deque(maxlen=20)
        self._beat_punch = 0.0
        self._white_punch = 0.0
        self._last_beat_time = 0.0
        self._silence_count = 0
        self._stream_time = 0.0

        # Frequency bin masks
        freqs = np.fft.rfftfreq(blocksize, d=1.0 / samplerate)
        self._masks = [
            (freqs >= lo) & (freqs < hi)
            for lo, hi in BAND_LIMITS
        ]
        self._sub_bass_mask = (freqs >= 20) & (freqs < 90)
        self._speech_mask = (freqs >= 250) & (freqs < 3400)

        # Equalization compensation curve
        self._eq_weights = np.linspace(1.2, 4.2, NUM_SEGMENTS)
        self._eq_weights[:10] *= 0.90  # prevent sub-bass clip

        # 7 Profiles & 8 Visual Styles
        self._visual_mode = "edm_drop"
        self._single_hue = 185  # Clean electric cyan default for single-color mode

        # Dynamic state trackers
        self._ripple_pos = -1.0
        self._wave_phase = 0.0
        self._peak_pos = 0
        self._peak_hold = 0.0

    @property
    def sensitivity(self) -> float:
        return self._calibrator.sensitivity

    def set_sensitivity(self, val: float):
        self._calibrator.sensitivity = max(0.1, min(4.0, float(val)))
        if hasattr(self, "_analyzer"):
            self._analyzer.sensitivity = self._calibrator.sensitivity

    @property
    def latency_lookahead_ms(self) -> float:
        return getattr(self, "_latency_lookahead_ms", 40.0)

    def set_latency_lookahead(self, lookahead_ms: float):
        self._latency_lookahead_ms = max(0.0, min(250.0, float(lookahead_ms)))
        if hasattr(self, "_analyzer"):
            self._analyzer.set_latency_lookahead(self._latency_lookahead_ms)

    def is_running(self) -> bool:
        return self._running

    def set_mode(self, mode: str):
        m = (mode or "auto").strip().lower()
        self._visual_mode = m
        self.style_name = m
        print(f"[MusicReactiveL930] Switched profile/style to: {m}")

    def set_style(self, style: str):
        self.set_mode(style)

    def set_accent(self, name: str, enabled: bool):
        self._compositor.set_accent_enabled(name, enabled)
        director = self._styles.get("auto")
        if isinstance(director, DirectorStyle):
            director.compositor.set_accent_enabled(name, enabled)

    def set_style_params(self, speed: float | None = None, intensity: float | None = None, smoothing: float | None = None, palette_mode: str | None = None):
        for s in self._styles.values():
            s.set_params(speed=speed, intensity=intensity, smoothing=smoothing, palette_mode=palette_mode)

    def get_analyzer(self) -> MusicAnalyzer:
        return self._analyzer

    def set_coordinator(self, coordinator: Any):
        self._coordinator = coordinator

    def set_device(self, device_name: str | None):
        was_active = self._running or (
            isinstance(self._app_state, dict)
            and self._app_state.get("active_label") in (
                "Audio Reactive", "Audio Spectrum (IC)", "Audio Error"
            )
        )
        self._preferred_device = device_name
        if was_active:
            self.stop()
            self.start()

    def _publish_frame(self, frame: dict, output_token=None, allow_stopped: bool = False) -> bool:
        """Route frames through the captured AUDIO ownership generation."""
        worker_generation = getattr(self._worker_context, "generation", None)
        if (worker_generation is not None
                and worker_generation != self._run_generation
                and not allow_stopped):
            return False
        if self._frame_bus:
            token = output_token if output_token is not None else self._output_token
            if token is None:
                return False
            generation, producer_id = token
            return self._frame_bus.publish_frame(
                self._dev_id, OutputProducer.AUDIO, frame,
                generation=generation, producer_id=producer_id,
            )
        submit = getattr(self._ctrl, "submit_frame", None)
        if submit:
            submit(frame)
            return True
        return False

    def _is_run_current(self, generation: int, stop_event: threading.Event) -> bool:
        return (
            self._running
            and generation == self._run_generation
            and not stop_event.is_set()
        )

    def _report_audio_error(self, message: str):
        """Publish true black if still authorized, then expose the capture failure."""
        message = str(message) or "Audio capture failed."
        token = self._output_token
        if hasattr(self._ctrl, "clear_frames"):
            self._ctrl.clear_frames()
        dark_frame = {
            "segments": [[0, 0, 0] for _ in range(NUM_SEGMENTS)],
            "brightness": 0, "transition": 0, "_pre_corrected": True,
        }
        if self._frame_bus:
            if token is not None:
                self._publish_frame(dark_frame, output_token=token, allow_stopped=True)
        else:
            self._publish_frame(dark_frame, allow_stopped=True)
        self._last_error = message
        if isinstance(self._app_state, dict):
            self._app_state["last_error"] = message
            if self._app_state.get("active_label") in (
                "Audio Reactive", "Audio Spectrum (IC)", "Audio Error"
            ):
                self._app_state["active_label"] = "Audio Error"
        self._running = False
        self._run_generation += 1
        if self._stop_event:
            self._stop_event.set()
        if self._coordinator:
            self._coordinator.unregister_subscriber(self)

    def start(self):
        if self._running:
            return
        old_thread = self._thread
        if old_thread and old_thread.is_alive():
            self.stop()
            old_thread = self._thread
            if old_thread and old_thread.is_alive():
                self._report_audio_error(
                    "Previous music worker is still running; refusing to start a duplicate."
                )
                return

        self._last_error = None
        if isinstance(self._app_state, dict):
            self._app_state["last_error"] = None
        self._run_generation += 1
        generation = self._run_generation
        stop_event = threading.Event()
        self._stop_event = stop_event
        self._output_token = (
            self._frame_bus.capture_token(self._dev_id, OutputProducer.AUDIO)
            if self._frame_bus else None
        )
        self._running = True
        if self._coordinator:
            self._coordinator.register_subscriber(self)
            self._coordinator.start()
            target = self._render_loop
            name = "MusicReactiveL930RenderLoop"
        else:
            target = self._run
            name = "MusicReactiveL930Worker"
        self._thread = threading.Thread(
            target=target, args=(generation, stop_event), daemon=True, name=name
        )
        self._thread.start()

    def stop(self):
        token = self._output_token
        self._running = False
        self._run_generation += 1
        self._output_token = None
        stop_event = self._stop_event
        if stop_event:
            stop_event.set()
        if self._coordinator:
            self._coordinator.unregister_subscriber(self)
            if hasattr(self._coordinator, "new_frame_event"):
                self._coordinator.new_frame_event.set()

        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        if thread and not thread.is_alive() and self._thread is thread:
            self._thread = None
            self._stop_event = None
        elif thread and thread.is_alive():
            message = "Music render worker did not stop within 2 seconds."
            self._last_error = message
            if isinstance(self._app_state, dict):
                self._app_state["last_error"] = message

        if hasattr(self._ctrl, "clear_frames"):
            self._ctrl.clear_frames()
        self._target_segs = [[0, 0, 0] for _ in range(NUM_SEGMENTS)]
        self._rendered_segs = [[0, 0, 0] for _ in range(NUM_SEGMENTS)]
        dark = {"segments": [[0, 0, 0] for _ in range(NUM_SEGMENTS)],
                "brightness": 0, "transition": 0, "_pre_corrected": True}
        if self._frame_bus and token:
            self._frame_bus.publish_frame(
                self._dev_id, OutputProducer.AUDIO, dark,
                generation=token[0], producer_id=token[1],
            )
        else:
            self._publish_frame(dark, output_token=token, allow_stopped=True)

    def _render_loop(
        self, generation: Optional[int] = None, stop_event: Optional[threading.Event] = None
    ):
        generation = self._run_generation if generation is None else generation
        self._worker_context.generation = generation
        stop_event = (self._stop_event or threading.Event()) if stop_event is None else stop_event
        last_t = time.perf_counter()
        target_fps = 60.0
        target_dt = 1.0 / target_fps

        while self._is_run_current(generation, stop_event):
            if self._coordinator and getattr(self._coordinator, "status", None) == "error":
                self._report_audio_error(
                    getattr(self._coordinator, "last_error", None)
                    or "Shared audio capture failed."
                )
                break

            t0 = time.perf_counter()
            dt = max(0.001, min(0.10, t0 - last_t))
            last_t = t0

            if self._coordinator:
                st, timing = self._coordinator.get_latest_state()
            else:
                st = self._analyzer.state
                timing = {"t_audio_recv": t0, "t_analysis_done": t0}

            self.latest_music_state = st
            self._render_from_music_state(st, dt, timing=timing)

            elapsed = time.perf_counter() - t0
            sleep_time = max(0.001, target_dt - elapsed)
            if self._coordinator and hasattr(self._coordinator, "new_frame_event"):
                self._coordinator.new_frame_event.wait(timeout=sleep_time)
            else:
                stop_event.wait(sleep_time)

    def _render_from_music_state(self, st: MusicState, dt: float, timing: Optional[Dict[str, float]] = None):
        master_ceiling = self._app_state.get("brightness", 100) / 100.0

        is_movie = (self.style_name == "movie")
        active_audio = music_is_genuinely_active(st) and not is_movie
        floor_value = self._brightness_floor.update(
            st, dt, master_ceiling=master_ceiling, enabled=not is_movie,
            force_inactive=not active_audio,
        )

        if not active_audio:
            if not is_movie:
                self._silence_duration += dt
                self._silence_count += 1
                self._white_punch = 0.0
                self._beat_punch = 0.0
                self.latest_spectrum = [0.0] * NUM_SEGMENTS
                fade_duration = silence_fade_duration(self._ctrl, fallback_rate=8.0)
                fade_start = 0.12
                factor = 1.0 if self._silence_duration <= fade_start else max(
                    0.0, 1.0 - (self._silence_duration - fade_start) / fade_duration
                )
                base = self._last_active_segs or [[0, 0, 0] for _ in range(NUM_SEGMENTS)]
                faded = fade_segments(base, factor)
                self._target_segs = faded
                self._rendered_segs = faded
                sender = getattr(self._ctrl, "frame_sender", None)
                configured_ups = max(0.5, float(getattr(self._ctrl, "_max_updates_per_s", 8.0)))
                active_ups = configured_ups
                if sender:
                    active_ups = max(0.5, min(
                        configured_ups,
                        float(getattr(sender, "_aimd_rate_cap", configured_ups)),
                    ))
                transition = min(6000, max(
                    int(getattr(self._ctrl, "music_transition_ms", 120)),
                    int(round(980.0 / active_ups)),
                ))
                self._publish_frame({
                    "segments": faded,
                    "brightness": max((zone[2] for zone in faded), default=0),
                    "transition": transition,
                    "_pre_corrected": True,
                })

                if self._silence_duration >= 3.0 and not self._powered_down_for_silence:
                    self._powered_down_for_silence = True
                    if hasattr(self._ctrl, "turn_off"):
                        if self._loop_runner and getattr(self._loop_runner, "loop", None):
                            asyncio.run_coroutine_threadsafe(self._ctrl.turn_off(), self._loop_runner.loop)
            return

        self._silence_count = 0
        self._silence_duration = 0.0
        if self._powered_down_for_silence:
            self._powered_down_for_silence = False
            if hasattr(self._ctrl, "turn_on"):
                if self._loop_runner and getattr(self._loop_runner, "loop", None):
                    asyncio.run_coroutine_threadsafe(self._ctrl.turn_on(), self._loop_runner.loop)

        style_key = self.style_name
        # Check direct match in style registry first so dedicated vibe styles are never clobbered
        if style_key in self._styles:
            style = self._styles[style_key]
        elif style_key == "edm_drop":
            style = self._styles.get("edm", self._styles.get("pulse"))
        elif style_key in ("lively", "classical"):
            style = self._styles.get("spectrum" if style_key == "lively" else "flow")
        elif style_key == "upbeat":
            style = self._styles.get("flow", self._styles.get("pulse"))
        elif style_key == "calm":
            style = self._styles.get("chill", self._styles.get("flow"))
        elif style_key == "single_color":
            style = self._styles.get("pulse")
        else:
            style = self._styles.get(style_key, self._styles.get("pulse", self._styles.get("auto")))
        measured_lat = getattr(getattr(self._ctrl, "diagnostics", None), "total_latency_ms", 0.0) / 1000.0
        output_rate = effective_send_rate(self._ctrl, fallback_rate=8.0)
        style.set_params(measured_latency_s=measured_lat, output_interval_s=1.0 / output_rate)

        sd = getattr(self, "screen_data", None)
        if sd is None and hasattr(self, "_screen_sync") and getattr(self._screen_sync, "latest_screen_data", None):
            sd = self._screen_sync.latest_screen_data

        segs = style.render(st, dt=dt, num_zones=NUM_SEGMENTS, screen_data=sd)
        if style_key not in ("auto", "hybrid", "director", "movie") and hasattr(self, "_compositor"):
            segs = self._compositor.composite(st, dt=dt, num_zones=NUM_SEGMENTS, base_frame=segs)

        t_rendered = time.perf_counter()

        self.latest_spectrum = [float(x) for x in getattr(st, "bands", [0.0] * NUM_SEGMENTS)]
        self.estimated_bpm = getattr(st, "bpm", 120.0)
        self.confidence = getattr(st, "bpm_confidence", 0.0)

        if st.section == Section.DROP and st.drop_strength > 0.82 and st.impact > 0.80:
            self._white_punch = 100.0
            self._beat_punch = 65.0
        else:
            self._white_punch = max(0.0, self._white_punch - dt * 150.0)
            self._beat_punch = max(0.0, self._beat_punch - dt * 120.0)

        corrected_segs = self._pipeline.correct_hsv_sequence(segs, master_ceiling=master_ceiling)
        corrected_segs = self._brightness_floor.apply_l930(corrected_segs, floor_value)
        self._last_active_segs = [list(zone) for zone in corrected_segs]
        self._target_segs = corrected_segs
        self._rendered_segs = corrected_segs
        brightness_val = int(max(x[2] for x in corrected_segs)) if corrected_segs else 0

        # Keep hardware transitions matched to the *effective* send interval.
        # When AIMD drops a slow strip to 1 FPS, a fixed 120ms music transition
        # creates a dark/stale gap for ~880ms and looks like flicker.
        is_movie = (style_key == "movie")
        target_max_ups = getattr(self._ctrl, "_movie_max_updates_per_s", 2.0) if is_movie else getattr(self._ctrl, "_max_updates_per_s", 8.0)
        target_max_ups = max(0.5, float(target_max_ups))

        frame_sender = getattr(self._ctrl, "frame_sender", None)
        if frame_sender:
            if getattr(frame_sender, "max_updates_per_s", None) != target_max_ups:
                frame_sender.set_send_budget(max_updates_per_s=target_max_ups)
            effective_ups = max(
                0.5,
                min(target_max_ups, float(getattr(frame_sender, "_aimd_rate_cap", target_max_ups))),
            )
        else:
            effective_ups = target_max_ups

        configured_transition = (
            getattr(self._ctrl, "movie_transition_ms", 800)
            if is_movie else getattr(self._ctrl, "music_transition_ms", 120)
        )
        # 98% of the send period prevents the device from snapping back to a
        # previous/stale state between updates. Clamp to the firmware's 6000ms max.
        rate_matched_transition = int(round(980.0 / effective_ups))
        trans_ms = max(0, min(6000, max(int(configured_transition), rate_matched_transition)))

        frame_dict = {
            "segments": corrected_segs,
            "brightness": brightness_val,
            "transition": trans_ms,
            "_pre_corrected": True,
        }
        if timing:
            frame_dict["t_audio_recv"] = timing.get("t_audio_recv", t_rendered)
            frame_dict["t_analysis_done"] = timing.get("t_analysis_done", t_rendered)
            frame_dict["t_frame_rendered"] = t_rendered

        self._publish_frame(frame_dict)

    def _run(
        self, generation: Optional[int] = None, stop_event: Optional[threading.Event] = None
    ):
        generation = self._run_generation if generation is None else generation
        self._worker_context.generation = generation
        stop_event = (self._stop_event or threading.Event()) if stop_event is None else stop_event
        try:
            mic = get_audio_input_source(self._sr, self._bs, self._preferred_device)
        except Exception as exc:
            self._report_audio_error(f"Audio input discovery failed: {exc}")
            return
        if not mic:
            self._report_audio_error(
                "No audio input source was found. Check the selected loopback device and audio permissions."
            )
            return

        print(f"[MusicReactiveL930] Active audio stream: {mic.name}")
        silent_chunks = 0
        while self._is_run_current(generation, stop_event):
            try:
                with mic.recorder(samplerate=self._sr, blocksize=self._bs, channels=1) as rec:
                    while self._is_run_current(generation, stop_event):
                        data = rec.record(numframes=self._bs)
                        samples = data[:, 0]
                        rms = float(np.sqrt(np.mean(samples ** 2)))
                        if rms < 0.001:
                            silent_chunks += 1
                            if silent_chunks > 180:
                                new_mic = get_audio_input_source(
                                    self._sr, self._bs, self._preferred_device
                                )
                                if new_mic and new_mic.id != mic.id:
                                    mic = new_mic
                                    silent_chunks = 0
                                    break
                        else:
                            silent_chunks = 0
                        self._process(samples, rms)
            except Exception as exc:
                if self._is_run_current(generation, stop_event):
                    self._report_audio_error(f"Audio capture failed: {exc}")
                break

    def _process(self, samples: np.ndarray, rms: float):
        block_dur = len(samples) / float(self._samplerate)
        self._stream_time += block_dur
        now = self._stream_time
        dt = block_dur
        half = NUM_SEGMENTS // 2

        if self._visual_mode not in ("classical", "movie", "edm_drop"):
            t_recv = time.perf_counter()
            st = self._analyzer.process_samples(samples, now=now, t_recv=t_recv)
            self.latest_music_state = st
            timing = {
                "t_audio_recv": t_recv,
                "t_analysis_done": time.perf_counter(),
            }
            self._render_from_music_state(st, dt, timing=timing)
            return

        # ── AGC & DYNAMIC NOISE FLOOR TRACKING ─────────────────────────────────
        vol_norm = self._calibrator.update(rms)

        # ── DEFAULT STATE: STRICTLY 100% OFF WHEN SILENT ──────────────────────
        silence_thresh = max(0.0020, min(0.010, self._calibrator.noise_floor * 1.20))
        if rms < silence_thresh and self._visual_mode != "movie":
            self._silence_duration += dt
            self._silence_count += 1
            self._brightness_floor.update(
                self.latest_music_state, dt,
                master_ceiling=self._app_state.get("brightness", 100) / 100.0,
                enabled=False, force_inactive=True,
            )
            self._white_punch = 0.0
            self._beat_punch = 0.0
            self._ripple_pos = -1.0

            fade_duration = silence_fade_duration(self._ctrl, fallback_rate=8.0)
            fade_start = 0.12
            factor = 1.0 if self._silence_duration <= fade_start else max(
                0.0, 1.0 - (self._silence_duration - fade_start) / fade_duration
            )
            base = self._last_active_segs or [[0, 0, 0] for _ in range(NUM_SEGMENTS)]
            faded = fade_segments(base, factor)
            self._target_segs = faded
            self._rendered_segs = faded
            self._levels *= factor
            self.latest_spectrum = [0.0] * NUM_SEGMENTS
            sender = getattr(self._ctrl, "frame_sender", None)
            configured_ups = max(0.5, float(getattr(self._ctrl, "_max_updates_per_s", 8.0)))
            effective_ups = configured_ups
            if sender:
                effective_ups = max(0.5, min(
                    configured_ups,
                    float(getattr(sender, "_aimd_rate_cap", configured_ups)),
                ))
            transition = min(6000, max(
                int(getattr(self._ctrl, "music_transition_ms", 120)),
                int(round(980.0 / effective_ups)),
            ))
            self._publish_frame({
                "segments": faded,
                "brightness": max((zone[2] for zone in faded), default=0),
                "transition": transition,
                "_pre_corrected": True,
            })

            # True black: on sustained silence (> 3 s) turn the strip off
            if self._silence_duration >= 3.0 and not self._powered_down_for_silence:
                self._powered_down_for_silence = True
                if hasattr(self._ctrl, "turn_off"):
                    if self._loop_runner and getattr(self._loop_runner, "loop", None):
                        asyncio.run_coroutine_threadsafe(self._ctrl.turn_off(), self._loop_runner.loop)
                    else:
                        res = self._ctrl.turn_off()
                        if asyncio.iscoroutine(res):
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    asyncio.create_task(res)
                                else:
                                    loop.run_until_complete(res)
                            except Exception:
                                pass
            return
        else:
            if self._powered_down_for_silence:
                # Audio resumes after sustained silence! Turn strip on cleanly without flash
                t_resume_start = time.perf_counter()
                self._powered_down_for_silence = False
                if hasattr(self._ctrl, "turn_on"):
                    if self._loop_runner and getattr(self._loop_runner, "loop", None):
                        fut = asyncio.run_coroutine_threadsafe(self._ctrl.turn_on(), self._loop_runner.loop)
                        try:
                            fut.result(timeout=1.0)
                        except Exception:
                            pass
                    else:
                        res = self._ctrl.turn_on()
                        if asyncio.iscoroutine(res):
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    asyncio.create_task(res)
                                else:
                                    loop.run_until_complete(res)
                            except Exception:
                                pass
                    resume_latency = (time.perf_counter() - t_resume_start) * 1000.0
                    if hasattr(self._ctrl, "diagnostics"):
                        self._ctrl.diagnostics.record_resume_latency(resume_latency)
            self._silence_count = 0
            self._silence_duration = 0.0

        # FFT frequency breakdown
        fft = np.abs(np.fft.rfft(samples))

        energies = np.zeros(NUM_SEGMENTS, dtype=np.float32)
        for i, mask in enumerate(self._masks):
            if np.any(mask):
                energies[i] = float(np.mean(fft[mask])) * self._eq_weights[i]

        inst_peak = float(np.max(energies))
        if inst_peak > self._rolling_peak:
            self._rolling_peak = 0.70 * self._rolling_peak + 0.30 * inst_peak
        else:
            self._rolling_peak = max(0.015, self._rolling_peak * 0.992)

        norm_energies = np.clip(energies / max(1e-5, self._rolling_peak * 0.85), 0.0, 1.0)
        self.latest_spectrum = [float(x) for x in norm_energies]

        # Spectral flux transient onset detection
        flux, is_onset = self._onset_detector.process(norm_energies, now, dt=dt)
        if is_onset:
            self._bpm_tracker.record_onset(now)

        self.estimated_bpm = self._bpm_tracker.estimated_bpm
        self.confidence = self._bpm_tracker.confidence

        # Real-time onset beat response (zero beat-guessing / no predictive firing)
        is_kick = is_onset

        # Base theme color derived from key estimation
        base_hue = self.latest_music_state.key_hue if self.latest_music_state else 185.0

        # Extreme bass drop & transient detection
        bass_e = float(np.mean(energies[:12]))
        mid_e = float(np.mean(energies[12:35]))
        treble_e = float(np.mean(energies[35:]))
        self._bass_history.append(bass_e)
        avg_bass = float(np.mean(self._bass_history)) if self._bass_history else 0.1

        bass_led = bass_e > max(0.03, avg_bass * 1.40) and (bass_e > 0.10 or vol_norm > 0.80)
        bass_led = bass_led and bass_e >= mid_e * 0.65 and bass_e >= treble_e * 0.40
        if is_kick and bass_led:
            self._white_punch = 100.0
            self._beat_punch = 65.0
            self._ripple_pos = 0.0  # Launch explosive shockwave from center!
            self._last_beat_time = now
        elif is_kick:
            self._beat_punch = 50.0
            if bass_e > 0.03:
                self._white_punch = max(self._white_punch, 35.0)
            if self._ripple_pos < 0.0:
                self._ripple_pos = 0.0
            self._last_beat_time = now

        # Dynamic rhythm envelope adaptation based on tracked BPM
        bpm = self.estimated_bpm
        decay_rate = 0.10 if bpm >= 125.0 else (0.22 if bpm < 110.0 else 0.15)
        self._white_punch *= math.exp(-dt / decay_rate)
        self._beat_punch *= math.exp(-dt / decay_rate)
        vol_ratio = min(1.0, vol_norm)

        # Per-zone peak followers
        for i in range(NUM_SEGMENTS):
            target_val = norm_energies[i] * 100.0
            if i < 12:
                target_val = min(100.0, target_val + self._beat_punch * 0.75)

            if target_val > self._levels[i]:
                self._levels[i] = 0.85 * target_val + 0.15 * self._levels[i]
            else:
                self._levels[i] = 0.35 * target_val + 0.65 * self._levels[i]

        if hasattr(self, "_analyzer"):
            self.latest_music_state = self._analyzer.process_samples(samples, now=now)

        # ── Two-Axis Visual Style Dispatch (Genre-Agnostic) ───────────────────
        if (self.style_name in self._styles or self.style_name in STYLE_REGISTRY) and self._visual_mode not in ("single_color", "edm_drop", "lively", "upbeat", "calm", "classical", "movie"):
            style = self._styles.get(self.style_name, self._styles["auto"])
            # Pass measured transport latency for render-ahead
            measured_lat = getattr(getattr(self._ctrl, "diagnostics", None), "total_latency_ms", 0.0) / 1000.0
            style.set_params(measured_latency_s=measured_lat)
            segs = style.render(self.latest_music_state, dt=dt, num_zones=NUM_SEGMENTS)
            if self.style_name not in ("auto", "hybrid", "director") and hasattr(self, "_compositor"):
                segs = self._compositor.composite(self.latest_music_state, dt=dt, num_zones=NUM_SEGMENTS, base_frame=segs)
            self._target_segs = segs
            self._rendered_segs = segs
            if hasattr(self._ctrl, "submit_frame"):
                # Handle master brightness ceiling in render thread ONCE; do NOT double-scale by energy*100
                master_ceiling = self._app_state.get("brightness", 100) / 100.0
                if self.latest_music_state.energy <= 0.005:
                    corrected = [[0, 0, 0]] * NUM_SEGMENTS
                else:
                    corrected = self._pipeline.correct_hsv_sequence(segs, master_ceiling=master_ceiling)

                # Set transition per mode: hardware crossfade (default 120ms or higher for ambient flow modes)
                music_trans = getattr(self._ctrl, "music_transition_ms", None)
                def_music_trans = music_trans if music_trans is not None and music_trans > 0 else 120
                if self.style_name in ("aurora", "plasma", "comet", "calm"):
                    trans = max(80, def_music_trans)
                else:
                    trans = def_music_trans


                self._publish_frame({"segments": corrected, "brightness": 100, "transition": trans, "_pre_corrected": True})
            return

        segs = []

        # ── 1. Single Color Beat Pulse (WLED Gravimeter / Center Outward) ────
        if self._visual_mode == "single_color":
            if self._ripple_pos >= 0.0:
                self._ripple_pos += 2.2
                if self._ripple_pos > half + 4:
                    self._ripple_pos = -1.0

            for i in range(NUM_SEGMENTS):
                dist = abs(i - half)
                ring_dist = abs(dist - self._ripple_pos) if self._ripple_pos >= 0 else 999.0
                if ring_dist < 3.5:
                    wave_b = int((1.0 - ring_dist / 3.5) * 100)
                else:
                    wave_b = 0
                lvl_idx = min(NUM_SEGMENTS - 1, dist * 2)
                direct_b = int(self._levels[lvl_idx] * 0.6)
                final_v = max(0, min(100, wave_b + direct_b))
                segs.append([self._single_hue, 100, final_v])

        # ── 2. EDM & Heavy Drops (Pure White Strike & Cascading Outward Shockwave) ──
        elif self._visual_mode == "edm_drop":
            if self._ripple_pos >= 0.0:
                self._ripple_pos += 2.8
                if self._ripple_pos > half + 6:
                    self._ripple_pos = -1.0

            rng = random.Random(int(now * 30.0))
            treble = treble_e

            for i in range(NUM_SEGMENTS):
                dist = abs(i - half)
                ring_dist = abs(dist - self._ripple_pos) if self._ripple_pos >= 0 else 999.0

                # On extreme drop: center zones (22-27) flash pure blinding white
                if dist <= 2 and self._white_punch > 65.0:
                    segs.append([int(base_hue), 0, 100])
                elif ring_dist < 4.0:
                    shock_b = int((1.0 - ring_dist / 4.0) * 100)
                    dist_factor = min(1.0, dist / half)
                    shock_s = min(100, int(dist_factor * 100))
                    if dist < 6:
                        shock_h = int(base_hue)
                    elif dist < 14:
                        shock_h = 180  # Electric cyan
                    else:
                        shock_h = 320 if (dist % 4 == 0) else int(base_hue)
                    segs.append([shock_h, shock_s, shock_b])
                elif (i < 6 or i > 43) and treble > 0.35 and rng.random() < 0.22:
                    # High-frequency accents remain saturated and palette-led; only a
                    # qualified bass-drop envelope is allowed to introduce white.
                    palette = self.latest_music_state.palette if self.latest_music_state else [(185, 90, 85), (280, 85, 80), (335, 88, 75), (42, 90, 88)]
                    palette_pos = (
                        (i / float(NUM_SEGMENTS)) * 0.28
                        + (self.latest_music_state.centroid_norm if self.latest_music_state else 0.5) * 0.42
                        + (self.latest_music_state.beat_phase if self.latest_music_state else 0.0) * 0.30
                    ) % 1.0
                    spark_h, spark_s, _ = sample_palette_oklab(palette, palette_pos, cyclic=True)
                    segs.append([int(spark_h), max(72, int(spark_s)), int(78 + min(18, treble * 18))])
                else:
                    lvl_idx = min(NUM_SEGMENTS - 1, dist * 2)
                    direct_v = int(self._levels[lvl_idx] * 0.45) if self._levels[lvl_idx] > 20 else 0
                    segs.append([270, 95, direct_v])

        # ── 3. Lively (WLED 50-Band GEQ Harmonic Instrument Equalizer) ────────
        elif self._visual_mode == "lively":
            # Each instrument lights up its own physical LEDs along the 50 zones
            for i in range(NUM_SEGMENTS):
                v = int(self._levels[i])
                if v < 4:
                    segs.append([0, 0, 0])
                else:
                    h = ZONE_HUES[i]
                    s = 70 if (v > 90 and i > 35) else 95
                    segs.append([h, s, v])

        # ── 4. Upbeat & Rhythm (WLED Freqwave Pop Bounce) ─────────────────────
        elif self._visual_mode == "upbeat":
            speed_mult = 1.0 + vol_ratio * 3.5
            self._wave_phase = (self._wave_phase + dt * speed_mult * 40.0) % 360.0
            for i in range(NUM_SEGMENTS):
                h = int((base_hue + self._wave_phase + (i / NUM_SEGMENTS) * 180.0) % 360)
                v = int(self._levels[i])
                segs.append([h, 100, v if v > 4 else 0])

        # ── 5. Calm & Lo-Fi (WLED Liquid Puddle Warm Relaxation) ──────────────
        elif self._visual_mode == "calm":
            for i in range(NUM_SEGMENTS):
                dist = abs(i - half)
                norm_idx = int((dist / half) * (NUM_SEGMENTS - 1))
                v = int(self._levels[norm_idx] * 0.70)
                if v < 3:
                    segs.append([0, 0, 0])
                else:
                    h = 28 if i % 2 == 0 else 35
                    segs.append([h, 90, v])

        # ── 6. Classical & Acoustic Mode (50-Zone Physical Orchestral Stage) ──
        elif self._visual_mode == "classical":
            # 50-Zone Physical Orchestral Stage Layout
            # Zones 0-14: Stage Left - Cellos, double bass, bassoons (Low acoustic warmth)
            # Zones 15-34: Center Stage - Grand piano, oboe, woodwinds, violas (Concert gold)
            # Zones 35-49: Stage Right - First violins, flutes, brass fortissimo (Concert sapphire/cyan)
            for i in range(NUM_SEGMENTS):
                raw_v = self._levels[i]
                expanded_v = int(min(100.0, (raw_v ** 0.82) * 1.30))
                if expanded_v < 4:
                    segs.append([0, 0, 0])
                    continue

                if i <= 14:
                    norm_pos = i / 14.0
                    h = int(24 + norm_pos * 14)  # 24° to 38°
                    s = 88
                    segs.append([h, s, expanded_v])
                elif i <= 34:
                    norm_pos = (i - 15) / 19.0
                    h = int(45 + norm_pos * 40)  # 45° to 85°
                    s = 82
                    segs.append([h, s, expanded_v])
                else:
                    norm_pos = (i - 35) / 14.0
                    h = int(180 + norm_pos * 35)  # 180° to 215°
                    s = 92
                    segs.append([h, s, expanded_v])

        # ── 7. Movie Night (Netflix & Cinematic Dialogue Center & Flank Rumble)
        elif self._visual_mode == "movie":
            speech_energy = float(np.mean(fft[self._speech_mask])) if np.any(self._speech_mask) else 0.0
            sub_bass = float(np.mean(fft[self._sub_bass_mask])) if np.any(self._sub_bass_mask) else 0.0
            is_explosion = (sub_bass > speech_energy * 0.85 and vol_norm > 0.40) or (self._white_punch > 40.0)

            dialogue_v = 0
            if rms > silence_thresh:
                dialogue_v = int(10 + min(14, (speech_energy / max(1e-5, speech_energy + mid_e)) * 18.0))

            for i in range(NUM_SEGMENTS):
                dist = abs(i - half)
                if is_explosion:
                    rumble_dist = abs(dist - (self._ripple_pos if self._ripple_pos >= 0 else 0))
                    if rumble_dist < 5.0:
                        flare_v = int((1.0 - rumble_dist / 5.0) * 100)
                        segs.append([16, 95, flare_v])
                    else:
                        segs.append([16, 95, int(self._beat_punch * 0.5)])
                elif 18 <= i <= 31:
                    segs.append([26, 75, dialogue_v])
                else:
                    lvl_idx = min(NUM_SEGMENTS - 1, dist * 2)
                    score_v = int(self._levels[lvl_idx] * 0.65) if self._levels[lvl_idx] > 18 else 0
                    segs.append([205, 85, score_v])

        self._target_segs = segs
        self._smooth_to_rendered(segs, alpha=0.60, dt=dt)

    def _smooth_to_rendered(
        self, target_segs: list[list[int]], alpha: float = 0.55,
        cache_active: bool = True, dt: float = 0.05,
    ):
        smoothed = []
        all_dark = True
        for i in range(NUM_SEGMENTS):
            th, ts, tv = target_segs[i]
            rh, rs, rv = self._rendered_segs[i]
            if tv > 0:
                all_dark = False

            # If rendered zone was dark or desaturated, snap hue & saturation immediately to target
            # to prevent sweeping through Hue=0 (Red flash) when turning on or changing color
            if rv <= 3 or rs <= 5:
                rh = th
                rs = ts
            # If target zone is turning off, preserve rendered hue so it doesn't snap to Red (0)
            if tv <= 0:
                th = rh

            diff = th - rh
            if diff > 180: diff -= 360
            elif diff < -180: diff += 360
            h = int((rh + diff * alpha) % 360)
            s = int(rs + (ts - rs) * alpha)
            # Asymmetric smoothing: fast attack for snappy beat hits, smooth decay to prevent strobing
            if tv > rv:
                v = int(rv + (tv - rv) * min(1.0, alpha * 1.5))
            else:
                v = int(rv + (tv - rv) * (alpha * 0.70))
            smoothed.append([h, s, v])

        # If targeting total silence and all rendered values drop below 1, preserve hues and snap brightness to 0
        if all_dark and max(seg[2] for seg in smoothed) <= 1:
            smoothed = [[seg[0], seg[1], 0] for seg in self._rendered_segs]

        self._rendered_segs = smoothed
        master_ceiling = self._app_state.get("brightness", 85) / 100.0
        active = cache_active and self._visual_mode != "movie" and music_is_genuinely_active(self.latest_music_state)
        floor_value = self._brightness_floor.update(
            self.latest_music_state, dt, master_ceiling=master_ceiling,
            enabled=(self._visual_mode != "movie"), force_inactive=not active,
        )
        corrected = self._pipeline.correct_hsv_sequence(smoothed, master_ceiling=master_ceiling)
        if active:
            corrected = self._brightness_floor.apply_l930(corrected, floor_value)
            if any(zone[2] > 0 for zone in corrected):
                self._last_active_segs = [list(zone) for zone in corrected]
        music_trans = getattr(self._ctrl, "music_transition_ms", None)
        trans = music_trans if music_trans is not None and music_trans > 0 else 120
        self._publish_frame({"segments": corrected, "brightness": 100, "transition": trans, "_pre_corrected": True})
