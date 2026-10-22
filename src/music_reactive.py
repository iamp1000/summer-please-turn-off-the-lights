from __future__ import annotations

import asyncio
import math
import threading
import time
from collections import deque
from typing import List, Dict, Any, Optional
import numpy as np
import soundcard as sc
from src.audio_dsp import SpectralFluxOnsetDetector, BPMTracker, DynamicAudioCalibrator, MusicAnalyzer, MusicState, Section
from src.visual_styles import get_visual_style, STYLE_REGISTRY, create_style_instances, AccentCompositor, DirectorStyle
from src.frame_bus import FramePacket, OutputProducer


def list_available_audio_devices() -> List[Dict[str, Any]]:
    """Returns a list of all audio playback / loopback devices available on Windows."""
    devices = [{"id": "auto", "name": "Auto-Detect Active Audio", "is_default": False}]
    try:
        def_spk_name = ""
        try:
            def_spk = sc.default_speaker()
            def_spk_name = def_spk.name
        except Exception:
            pass

        seen_names = set()
        for m in sc.all_microphones(include_loopback=True):
            if m.isloopback and m.name not in seen_names:
                seen_names.add(m.name)
                is_def = (m.name == def_spk_name)
                devices.append({
                    "id": m.name,
                    "name": m.name,
                    "is_default": is_def,
                })
    except Exception as e:
        print(f"[AudioDetector] Error listing devices: {e}")
    return devices


def get_audio_input_source(samplerate: int = 44100, blocksize: int = 1024, preferred_name: str | None = None):
    """
    Finds the active audio stream currently playing on Windows.
    1. If user selected a specific device in preferred_name, lock onto it.
    2. Otherwise, check default speaker loopback.
    3. If multiple devices exist, check which loopback currently has live signal (RMS > 0.001).
    """
    all_loopbacks = []
    try:
        all_loopbacks = [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]
    except Exception:
        pass

    # 1. User preferred device
    if preferred_name and preferred_name.strip().lower() not in ("auto", "auto-detect", "none", ""):
        p_lower = preferred_name.strip().lower()
        for m in all_loopbacks:
            if p_lower in m.name.lower():
                print(f"[AudioDetector] Using user-selected device: {m.name}")
                return m

    # 2. Check default speaker loopback
    def_mic = None
    try:
        spk = sc.default_speaker()
        def_mic = sc.get_microphone(spk.id, include_loopback=True)
    except Exception:
        pass

    # 3. Scan loopbacks for active playing audio
    best_dev = None
    best_rms = -1.0

    candidates = [def_mic] if def_mic else []
    for m in all_loopbacks:
        if m not in candidates:
            candidates.append(m)

    for dev in candidates:
        if dev is None: continue
        try:
            with dev.recorder(samplerate=samplerate, blocksize=blocksize, channels=1) as rec:
                data = rec.record(numframes=blocksize * 2)
                rms = float(np.sqrt(np.mean(data[:, 0] ** 2)))
                if rms > best_rms:
                    best_rms = rms
                    best_dev = dev
                if rms > 0.005:
                    print(f"[AudioDetector] Live signal locked: {dev.name} (RMS={rms:.4f})")
                    return dev
        except Exception:
            continue

    if best_dev is not None and best_rms > 0.0005:
        print(f"[AudioDetector] Selected highest signal: {best_dev.name} (RMS={best_rms:.4f})")
        return best_dev

    fallback = def_mic or (all_loopbacks[0] if all_loopbacks else None)
    if fallback:
        print(f"[AudioDetector] Defaulting to stream: {fallback.name}")
    return fallback


class MusicReactive:
    """
    Audio-reactive lighting engine for Tapo L900 LED Strip (single zone).
    Default state when quiet: COMPLETELY OFF (0% brightness).
    Reacts with zero latency to laptop audio across 6 tailored profiles:
      1. single_color  - Pure single color beat pulse (no random cycling)
      2. edm_drop      - High-impact bass drop attack & punch
      3. lively        - Multi-instrument harmonic spectrum mapping
      4. upbeat        - Bouncy energetic rhythm & pop pulse
      5. calm          - Warm soothing acoustic / lo-fi relaxation
      6. movie         - Netflix & movie cinematic dialogue / soundtrack bias
    """

    def __init__(self, controller, loop_runner, app_state, samplerate=44100, blocksize=512, preferred_device: str | None = None, frame_bus: Any = None, dev_id: str = "strip1"):
        self._controller = controller
        self._loop_runner = loop_runner
        self._app_state = app_state
        self._frame_bus = frame_bus
        self._dev_id = dev_id
        self._samplerate = samplerate
        self._blocksize = blocksize
        self._preferred_device = preferred_device
        self._shared_analyzer: Optional[MusicAnalyzer] = None

        self._running = False
        self._thread = None
        self._run_generation = 0
        self._updater_future = None

        self._mode = "edm_drop"
        self._single_hue = 185  # Clean electric cyan default for single-color mode

        self._target_state: tuple[int, int, int] | None = None
        self._last_sent_state = None
        self._last_sent_time = 0.0

        # Unified Two-Axis MusicAnalyzer & VisualStyle Engine
        self._analyzer = MusicAnalyzer(samplerate=self._samplerate, blocksize=self._blocksize, sensitivity=1.0)
        self._styles = create_style_instances()
        self._compositor = AccentCompositor()
        self.style_name = "auto"
        self._mode = "auto"
        self.latest_music_state: MusicState | None = None
        self._coordinator: Any = None

        from src.pipeline import RenderPipeline
        self._pipeline = RenderPipeline(gamma=2.2, r_calib=1.0, g_calib=0.92, b_calib=0.85)
        self._silence_duration = 0.0
        self._powered_down_for_silence = False

        # DSP Pipeline: AGC, Onset Detection & Real-Time Beat Tracking
        self._calibrator = DynamicAudioCalibrator(sensitivity=1.0)
        self._onset_detector = SpectralFluxOnsetDetector(num_bins=16, threshold_mult=1.35)
        self._bpm_tracker = BPMTracker()
        self.latest_spectrum = [0.0] * 50
        self.estimated_bpm = 120.0
        self.confidence = 0.0

        # Dynamics tracking
        self._bass_history = deque(maxlen=24)
        self._volume_history = deque(maxlen=40)
        self._beat_pop = 0.0
        self._white_punch = 0.0
        self._last_beat_time = 0.0
        self._smoothed_brightness = 0.0
        self._smoothed_hue = 185.0
        self._silence_count = 0
        self._stream_time = 0.0

        # Frequency masks
        freqs = np.fft.rfftfreq(blocksize, d=1.0 / samplerate)
        self._bass_mask = (freqs >= 20) & (freqs < 180)
        self._mid_mask = (freqs >= 180) & (freqs < 2400)
        self._treble_mask = (freqs >= 2400) & (freqs < 14000)

        # Specialized bands for Classical & Movie profiles
        self._sub_bass_mask = (freqs >= 20) & (freqs < 90)
        self._speech_mask = (freqs >= 250) & (freqs < 3400)
        self._acoustic_warmth_mask = (freqs >= 200) & (freqs < 1200)
        self._acoustic_high_mask = (freqs >= 1200) & (freqs < 8000)

        # 16-band log spaced masks for spectrum visualizer and onset detection
        self._flux_freqs = np.logspace(np.log10(20), np.log10(14000), 17)
        self._flux_masks = [
            (freqs >= self._flux_freqs[i]) & (freqs < self._flux_freqs[i + 1])
            for i in range(16)
        ]

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

    def _submit_frame(self, frame):
        """Route render frames through FrameBus when the hub is active."""
        if self._frame_bus is not None:
            return self._frame_bus.publish_frame_dict(self._dev_id, OutputProducer.AUDIO, frame)
        if hasattr(self._controller, "submit_frame"):
            return self._controller.submit_frame(frame)
        return False

    def is_running(self):
        return self._running

    def set_mode(self, mode: str):
        m = (mode or "auto").strip().lower()
        self._mode = m
        self.style_name = m
        print(f"[MusicReactive L900] Switched profile/style to: {m}")

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

    def set_device(self, device_name: str | None):
        self._preferred_device = device_name
        if self._running:
            self.stop()
            self.start()

    def set_shared_analyzer(self, analyzer: MusicAnalyzer):
        self._shared_analyzer = analyzer

    def set_coordinator(self, coordinator: Any):
        self._coordinator = coordinator

    def start(self):
        if self._running:
            return
        self._run_generation += 1
        generation = self._run_generation
        self._running = True
        if self._coordinator:
            self._coordinator.register_subscriber(self)
            self._coordinator.start()
            self._thread = threading.Thread(target=self._render_loop, args=(generation,), daemon=True, name="MusicReactiveL900RenderLoop")
        elif self._shared_analyzer is not None:
            self._thread = threading.Thread(target=self._render_loop, daemon=True, name="MusicReactiveL900RenderLoop")
        else:
            self._thread = threading.Thread(target=self._run, args=(generation,), daemon=True, name="MusicReactiveL900Worker")
        self._thread.start()

    def _render_loop(self, generation=None):
        generation = self._run_generation if generation is None else generation
        last_t = time.perf_counter()
        target_fps = 60.0
        target_dt = 1.0 / target_fps

        while self._running and generation == self._run_generation:
            t0 = time.perf_counter()
            dt = max(0.001, min(0.10, t0 - last_t))
            last_t = t0

            if self._coordinator:
                st, timing = self._coordinator.get_latest_state()
            elif self._shared_analyzer is not None:
                st = self._shared_analyzer.state
                timing = {"t_audio_recv": t0, "t_analysis_done": t0}
            else:
                st = self._analyzer.state
                timing = {"t_audio_recv": t0, "t_analysis_done": t0}

            self.latest_music_state = st
            self.estimated_bpm = getattr(st, "bpm", 120.0)
            self.confidence = getattr(st, "bpm_confidence", 0.0)
            self._render_from_music_state(st, dt, timing=timing)

            elapsed = time.perf_counter() - t0
            sleep_time = max(0.001, target_dt - elapsed)
            if self._coordinator and hasattr(self._coordinator, "new_frame_event"):
                self._coordinator.new_frame_event.wait(timeout=sleep_time)
                self._coordinator.new_frame_event.clear()
            else:
                time.sleep(sleep_time)

    def _run_shared(self):
        self._render_loop()

    def _render_from_music_state(self, st: MusicState, dt: float, timing: Optional[Dict[str, float]] = None):
        master_ceiling = self._app_state.get("brightness", 100) / 100.0
        is_movie = (self.style_name == "movie")

        if (st.energy <= 0.005 or getattr(st, "silent", False)) and not is_movie:
            self._target_state = (0, 0, 0)
            if hasattr(self._controller, "submit_frame"):
                self._submit_frame({"h": 0, "s": 0, "b": 0, "_pre_corrected": True})
            return

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
        measured_lat = getattr(getattr(self._controller, "diagnostics", None), "total_latency_ms", 0.0) / 1000.0
        style.set_params(measured_latency_s=measured_lat)

        sd = getattr(self, "screen_data", None)
        if sd is None and hasattr(self, "_screen_sync") and getattr(self._screen_sync, "latest_screen_data", None):
            sd = self._screen_sync.latest_screen_data

        segs = style.render(st, dt=dt, num_zones=1, screen_data=sd)
        if style_key not in ("auto", "hybrid", "director", "movie") and hasattr(self, "_compositor"):
            segs = self._compositor.composite(st, dt=dt, num_zones=1, base_frame=segs)

        t_rendered = time.perf_counter()
        h, s, b = segs[0]

        # White punch tracking for tests
        if st.section == Section.DROP and st.drop_strength > 0.82 and st.impact > 0.80:
            self._white_punch = 100.0
        else:
            self._white_punch = max(0.0, self._white_punch - dt * 150.0)

        hc, sc, vc = self._pipeline.correct_hsv_tuple(h, s, b, master_ceiling=master_ceiling)
        self._target_state = (vc, hc, sc)

        frame_dict = {"h": hc, "s": sc, "b": vc, "_pre_corrected": True}
        if timing:
            frame_dict["t_audio_recv"] = timing.get("t_audio_recv", t_rendered)
            frame_dict["t_analysis_done"] = timing.get("t_analysis_done", t_rendered)
            frame_dict["t_frame_rendered"] = t_rendered


        if hasattr(self._controller, "submit_frame"):
            self._submit_frame(frame_dict)

    def stop(self):
        self._running = False
        self._run_generation += 1
        thread = self._thread
        if self._coordinator:
            self._coordinator.unregister_subscriber(self)
        if thread and thread.is_alive() and thread != threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None
        self._target_state = (0, 0, 0)
        if hasattr(self._controller, "clear_frames"):
            self._controller.clear_frames()
        if hasattr(self._controller, "submit_frame"):
            self._submit_frame({"h": 0, "s": 0, "b": 0})

    def _should_send(self, b, h, s):
        if self._last_sent_state is None:
            return True
        lb, lh, ls = self._last_sent_state
        if b == 0 and lb != 0:
            return True  # Always immediately push complete blackness
        return (abs(b - lb) >= 2 or abs(h - lh) >= 5 or abs(s - ls) >= 8)

    def _run(self, generation=None):
        generation = self._run_generation if generation is None else generation
        mic = get_audio_input_source(self._samplerate, self._blocksize, self._preferred_device)
        if not mic:
            print("[MusicReactive L900] No audio device detected.")
            return

        from src.master_volume import get_master_volume_probe
        vol_probe = get_master_volume_probe()

        while self._running and generation == self._run_generation:
            try:
                with mic.recorder(samplerate=self._samplerate, blocksize=self._blocksize, channels=1) as recorder:
                    while self._running and generation == self._run_generation:
                        data = recorder.record(numframes=self._blocksize)
                        raw_samples = data[:, 0]
                        samples = vol_probe.compensate_samples(raw_samples)
                        self._process_samples(samples)
            except Exception:
                time.sleep(0.3)

    def _process_samples(self, samples: np.ndarray):
        block_dur = len(samples) / float(self._samplerate)
        self._stream_time += block_dur
        now = self._stream_time
        dt = block_dur

        # ── AGC & DYNAMIC NOISE FLOOR TRACKING ─────────────────────────────────
        rms = float(np.sqrt(np.mean(samples ** 2)) + 1e-9)
        vol_norm = self._calibrator.update(rms)

        # ── DEFAULT STATE: STRICTLY 100% OFF WHEN SILENT ──────────────────────
        silence_thresh = max(0.0020, min(0.010, self._calibrator.noise_floor * 1.20))
        if rms < silence_thresh:
            self._silence_duration += dt
            self._silence_count += 1
            if self._silence_count > 5:
                # Fast linear decay to absolute blackness OFF
                self._smoothed_brightness *= 0.55
                if self._smoothed_brightness < 1.0:
                    self._smoothed_brightness = 0.0
                    self._white_punch = 0.0
                    self._beat_pop = 0.0
                    self._target_state = (0, 0, 0)
                else:
                    self._target_state = (int(self._smoothed_brightness), int(self._smoothed_hue), 100)
                self.latest_spectrum = [0.0] * 50
                if hasattr(self._controller, "submit_frame"):
                    b_out = int(self._smoothed_brightness)
                    self._submit_frame({"h": int(self._smoothed_hue) if b_out > 0 else 0, "s": 100 if b_out > 0 else 0, "b": b_out, "_pre_corrected": True})

            # True black: on sustained silence (> 3 s) turn the strip off
            if self._silence_duration >= 3.0 and not self._powered_down_for_silence:
                self._powered_down_for_silence = True
                if hasattr(self._controller, "turn_off"):
                    if self._loop_runner and getattr(self._loop_runner, "loop", None):
                        asyncio.run_coroutine_threadsafe(self._controller.turn_off(), self._loop_runner.loop)
                    else:
                        res = self._controller.turn_off()
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
                # Audio has resumed after sustained silence! Turn strip on cleanly without flash
                t_resume_start = time.perf_counter()
                self._powered_down_for_silence = False
                if hasattr(self._controller, "turn_on"):
                    if self._loop_runner and getattr(self._loop_runner, "loop", None):
                        fut = asyncio.run_coroutine_threadsafe(self._controller.turn_on(), self._loop_runner.loop)
                        try:
                            fut.result(timeout=1.0)
                        except Exception:
                            pass
                    else:
                        res = self._controller.turn_on()
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
                    if hasattr(self._controller, "diagnostics"):
                        self._controller.diagnostics.record_resume_latency(resume_latency)
            self._silence_count = 0
            self._silence_duration = 0.0

        # FFT Analysis
        fft = np.abs(np.fft.rfft(samples))
        bass_energy = float(np.mean(fft[self._bass_mask])) if np.any(self._bass_mask) else 0.0
        mid_energy = float(np.mean(fft[self._mid_mask])) if np.any(self._mid_mask) else 0.0
        treble_energy = float(np.mean(fft[self._treble_mask])) if np.any(self._treble_mask) else 0.0

        # Multi-band energy for spectral flux onset detection
        flux_energies = np.zeros(16, dtype=np.float32)
        for i, mask in enumerate(self._flux_masks):
            if np.any(mask):
                flux_energies[i] = float(np.mean(fft[mask]))

        p = float(np.max(flux_energies))
        if p > 1e-5:
            norm_flux = np.clip(flux_energies / p, 0.0, 1.0)
        else:
            norm_flux = flux_energies

        # Populate 50-band visual spectrum via linear interpolation
        xp = np.linspace(0, 1, 16)
        x_target = np.linspace(0, 1, 50)
        self.latest_spectrum = [float(x) for x in np.interp(x_target, xp, norm_flux)]

        # Spectral flux transient onset detection
        flux, is_onset = self._onset_detector.process(norm_flux, now, dt=dt)
        if is_onset:
            self._bpm_tracker.record_onset(now)

        self.estimated_bpm = self._bpm_tracker.estimated_bpm
        self.confidence = self._bpm_tracker.confidence

        # Real-time onset beat response (predictive beat firing removed to eliminate double-firing)
        is_kick = is_onset

        # Base theme color derived from key estimation
        base_hue = self.latest_music_state.key_hue if self.latest_music_state else 185.0

        # Extreme bass drop & transient detection
        self._bass_history.append(bass_energy)
        avg_bass = float(np.mean(self._bass_history)) if self._bass_history else 0.1

        if is_kick and (bass_energy > max(0.03, avg_bass * 1.40)) and (bass_energy > 0.10 or vol_norm > 0.80):
            self._white_punch = 100.0
            self._beat_pop = 60.0
            self._last_beat_time = now
        elif is_kick:
            self._beat_pop = 45.0
            if bass_energy > 0.03:
                self._white_punch = max(self._white_punch, 35.0)
            self._last_beat_time = now

        if hasattr(self, "_analyzer"):
            self.latest_music_state = self._analyzer.process_samples(samples, now=now)

        # Dynamic rhythm envelope adaptation based on tracked BPM
        bpm = self.estimated_bpm
        decay_rate = 0.10 if bpm >= 125.0 else (0.22 if bpm < 110.0 else 0.15)
        self._white_punch *= math.exp(-dt / decay_rate)
        self._beat_pop *= math.exp(-dt / decay_rate)

        master_ceiling = self._app_state.get("brightness", 100) / 100.0

        # ── Two-Axis Visual Style Dispatch (Genre-Agnostic) ───────────────────
        if (self.style_name in self._styles or self.style_name in STYLE_REGISTRY) and self._mode not in ("single_color", "edm_drop", "lively", "upbeat", "calm", "classical", "movie"):
            style = self._styles.get(self.style_name, self._styles["auto"])
            # Pass measured transport latency for render-ahead
            measured_lat = getattr(getattr(self._controller, "diagnostics", None), "total_latency_ms", 0.0) / 1000.0
            style.set_params(measured_latency_s=measured_lat)
            segs = style.render(self.latest_music_state, dt=dt, num_zones=1)
            if self.style_name not in ("auto", "hybrid", "director") and hasattr(self, "_compositor"):
                segs = self._compositor.composite(self.latest_music_state, dt=dt, num_zones=1, base_frame=segs)
            h, s, b = segs[0]
            if self.latest_music_state.energy <= 0.005:
                b = 0
            # Apply gamma and white-balance calibration in render thread
            hc, sc, vc = self._pipeline.correct_hsv_tuple(h, s, b, master_ceiling=master_ceiling)
            self._target_state = (vc, hc, sc)
            if hasattr(self._controller, "submit_frame"):
                self._submit_frame({"h": hc, "s": sc, "b": vc, "_pre_corrected": True})
            return

        # ── 1. Single Color Beat Pulse ────────────────────────────────────────
        elif self._mode == "single_color":
            # Pure fixed color, strictly reacting to beat volume & kicks. No random shifts!
            b_val = vol_norm * 65.0 + self._beat_pop
            b = max(0, min(100, int(b_val * master_ceiling)))
            self._target_state = (b, self._single_hue, 100)

        # ── 2. EDM & Heavy Bass Drops (Pure White Flash -> Cascading Color) ─────
        elif self._mode == "edm_drop":
            b_val = (vol_norm ** 1.5) * 55.0 + self._beat_pop * 1.3
            b = max(0, min(100, int(b_val * master_ceiling)))

            # Extreme peak flash: saturation collapses to 0 -> pure laser white punch!
            # As white punch decays, saturation recovers and color cascades through neon to base_hue
            if self._white_punch > 50.0:
                s = max(0, int(100.0 - (self._white_punch - 50.0) * 3.4))
                h = int(base_hue)
            else:
                release_ratio = self._white_punch / 50.0
                s = min(100, int(80.0 + 20.0 * (1.0 - release_ratio)))
                h = int((base_hue + release_ratio * 120.0) % 360)

            self._target_state = (b, h, s)

        # ── 3. Lively (All Instruments Harmonic Spectrum) ─────────────────────
        elif self._mode == "lively":
            diff = base_hue - self._smoothed_hue
            if diff > 180: diff -= 360
            elif diff < -180: diff += 360
            self._smoothed_hue = (self._smoothed_hue + diff * 0.35) % 360
            b_val = vol_norm * 65.0 + self._beat_pop * 0.8
            b = max(0, min(100, int(b_val * master_ceiling)))
            self._target_state = (b, int(self._smoothed_hue), 95)

        # ── 4. Upbeat & Rhythm ────────────────────────────────────────────────
        elif self._mode == "upbeat":
            # Bouncy rhythmic oscillation centered around AdaptiveBaseColor
            h = int((base_hue + math.sin(now * 3.5) * 45.0 + vol_norm * 40.0) % 360)
            b_val = vol_norm * 70.0 + self._beat_pop * 0.6
            b = max(0, min(100, int(b_val * master_ceiling)))
            self._target_state = (b, h, 100)

        # ── 5. Calm & Lo-Fi ───────────────────────────────────────────────────
        elif self._mode == "calm":
            # Warm soothing candlelight gold (28° - 35°); velvety smooth response
            b_val = vol_norm * 50.0
            self._smoothed_brightness = 0.82 * self._smoothed_brightness + 0.18 * b_val
            b = max(0, min(100, int(self._smoothed_brightness * master_ceiling)))
            self._target_state = (b, 30, 88)

        # ── 6. Classical & Acoustic Mode ──────────────────────────────────────
        elif self._mode == "classical":
            # Wide dynamic range expansion: soft pianissimos illuminate gently (15-35%),
            # orchestral fortissimos swell into warm concert-hall radiance without harsh clipping.
            acoustic_vol = min(1.25, (vol_norm ** 0.78) * 1.30)
            b_target = acoustic_vol * 75.0 + (self._beat_pop * 0.35)
            self._smoothed_brightness = 0.70 * self._smoothed_brightness + 0.30 * b_target
            b = max(0, min(100, int(self._smoothed_brightness * master_ceiling)))

            # Acoustic harmonic balance: cellos/wood (200-1200Hz) vs soaring violins/flutes (1200-8000Hz)
            warmth = float(np.mean(fft[self._acoustic_warmth_mask])) if np.any(self._acoustic_warmth_mask) else 0.01
            highs = float(np.mean(fft[self._acoustic_high_mask])) if np.any(self._acoustic_high_mask) else 0.01
            acoustic_ratio = highs / (warmth + highs + 1e-9)

            # Warm mahogany gold (32°) to celestial concert sapphire (195°) on violin climaxes
            target_h = 32.0 + acoustic_ratio * 163.0
            diff = target_h - self._smoothed_hue
            if diff > 180: diff -= 360
            elif diff < -180: diff += 360
            self._smoothed_hue = (self._smoothed_hue + diff * 0.20) % 360
            self._target_state = (b, int(self._smoothed_hue), 85)

        # ── 7. Movie Night (Netflix & Cinematic Dialogue / Rumble Bias) ───────
        elif self._mode == "movie":
            # Dialogue Formant Isolation (250Hz - 3400Hz) & Sub-bass Rumble (20Hz - 90Hz)
            speech_energy = float(np.mean(fft[self._speech_mask])) if np.any(self._speech_mask) else 0.0
            sub_bass = float(np.mean(fft[self._sub_bass_mask])) if np.any(self._sub_bass_mask) else 0.0

            dialogue_b = 0.0
            if rms > silence_thresh:
                dialogue_b = 10.0 + min(15.0, (speech_energy / max(1e-5, speech_energy + mid_energy)) * 18.0)

            is_explosion = (sub_bass > speech_energy * 0.85 and vol_norm > 0.40) or (self._white_punch > 40.0)
            rumble_b = (vol_norm ** 1.3) * 45.0 + (self._beat_pop * 1.1 if is_explosion else 0.0)

            b_val = dialogue_b + rumble_b
            b = max(0, min(100, int(b_val * master_ceiling)))

            if is_explosion:
                # Fiery cinematic orange/crimson on dramatic action/explosions
                h, s = 16, 95
            else:
                # Comfortable 2700K warm tungsten ambient bias during dialogue and scenes
                h, s = 26, 75

            self._target_state = (b, h, s)

        if self._target_state is not None:
            b_val, h_val, s_val = self._target_state
            if self._should_send(b_val, h_val, s_val):
                self._last_sent_state = (b_val, h_val, s_val)
                self._last_sent_time = now
                if hasattr(self._controller, "submit_frame"):
                    hc, sc, vc = self._pipeline.correct_hsv_tuple(h_val, s_val, b_val, master_ceiling=master_ceiling)
                    self._submit_frame({"h": hc, "s": sc, "b": vc, "_pre_corrected": True})
