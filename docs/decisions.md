# Architectural Decisions & Technical Assumptions

This document records architectural decisions, engineering rationales, and technical assumptions implemented in the genre-agnostic music-reactive pipeline (`Audio → Analyzer → MusicState → VisualStyle → Renderer → Sender`).

## Decision 1: Sample-Clock-Driven Determinism & Time-Invariant Exponential Smoothing
* **Rationale:** In earlier implementations, frame-rate-dependent histories (e.g. `maxlen=30` frames) and wall-clock timestamps (`time.time()`) caused analysis behavior to fluctuate whenever hop size or buffer delivery timing jittered.
* **Implementation:**
  * Every timestamp is derived strictly from the audio stream sample clock: $t = n_{\text{samples}} / f_s$.
  * All smoothing filters and decaying windows are formulated with continuous time constants $\tau$ (seconds) and computed using the actual frame duration $\Delta t$:
    $$\alpha = 1 - e^{-\Delta t / \tau}$$
  * This guarantees bit-for-bit identical, deterministic output across both real-time live WASAPI streams and offline WAV replay test harnesses.

## Decision 2: Scale-Invariant Adaptive Whitening & Log Compression
* **Rationale:** Fixed absolute thresholds (e.g. `max(0.15, std_flux)`) caused onset detection and energy tracking to break when system volume, Spotify preamp, or Voicemeeter levels changed.
* **Implementation:**
  * Spectrum magnitudes are log-compressed: $X_{\text{log}} = \log(1 + \gamma X)$.
  * Each of the 50 log bands maintains an exponentially smoothed running mean ($\tau \approx 2.5\text{ s}$).
  * Flux is computed on whitened log bands: $\tilde{X}_k = X_{\text{log}, k} / (\mu_k + \epsilon)$, making spectral flux scale-invariant across input gains.

## Decision 3: Autocorrelation/Comb-Filter Tempo Estimation with Phase-Locked Loop (PLL)
* **Rationale:** Median inter-onset intervals suffered from octave errors (e.g. reporting 70 BPM instead of 140 BPM) and jittered on syncopated polyrhythms or rapid hi-hats.
* **Implementation:**
  * Continuous onset strength envelope is tracked in an 8-second circular buffer.
  * Tempo is estimated via generalized autocorrelation / comb-filter bank over the 70–180 BPM range with harmonic weighting to eliminate half-time/double-time octave ambiguities.
  * A Phase-Locked Loop (PLL) synchronizes with detected beats, maintaining continuous `beat_phase` ($0.0 \to 1.0$), `bar_pos` ($0..3$), and emitting predictive beat markers without phase drift.

## Decision 4: Dual Fast/Slow Calibrator with Absolute Silence Gate and Stream Timeout
* **Rationale:** Fixed percentile windows fail when silent periods cause percentile ranges to collapse, falsely amplifying line noise into "loud" events. When switching songs, a single 45s window sluggishly blends two distinct tracks.
* **Implementation:**
  * Dual-ring buffer: a Fast Window ($\approx 5\text{ s}$) and a Slow Window ($\approx 45\text{ s}$).
  * Hard silence gate: below an absolute RMS threshold (e.g. $-54\text{ dBFS}$), the system immediately marks `silent = True` and locks percentiles.
  * Stream Timeout: if no WASAPI loopback audio buffers arrive for $\ge 120\text{ ms}$, the stream watchdog immediately triggers silence.
  * Rapid adaptation: if prolonged silence or a massive spectral discontinuity is detected, the slow history resets or blends rapidly into the fast history.
  * Computational efficiency: percentiles ($p_5, p_{50}, p_{95}, p_{99}$) are recomputed every $N=5$ frames rather than every sample block.

## Decision 5: Dedicated 4096-Sample STFT for Chroma, Pitch & Key Estimation
* **Rationale:** 50 log-spaced frequency bands lack the sub-band resolution needed for low-register pitch class identification (e.g. $40\text{ Hz} \to 200\text{ Hz}$).
* **Implementation:**
  * A dedicated 4096-sample circular STFT buffer provides $\approx 10.7\text{ Hz}$ frequency resolution.
  * Fractional bin peak interpolation with global tuning estimation ($\text{A4} \approx 440\text{ Hz}$ reference offset).
  * 12-pitch-class chroma accumulator decayed over a 15–20s exponential window.
  * Correlation with Krumhansl-Schmuckler (K-S) major/minor key profiles, producing `key_hue` and `key_confidence`.
  * Fallback: When `key_confidence < 0.40`, the palette gracefully transitions to an atmospheric palette driven by spectral centroid and energetic arousal.

## Decision 6: Section State Machine with Dwell Hysteresis & Drop Qualification
* **Rationale:** Audio state machines without dwell times suffer from rapid state chatter between Verse and Build.
* **Implementation:**
  * States: `SILENT`, `INTRO`, `VERSE`, `BUILD`, `DROP`, `BREAKDOWN`, `OUTRO`.
  * Minimum dwell times: `BUILD` requires $\ge 2.5\text{ s}$, `DROP` requires $\ge 1.8\text{ s}$, `BREAKDOWN` requires $\ge 3.0\text{ s}$.
  * State progression exposes `section_age` (elapsed seconds) and `section_progress` ($0.0 \to 1.0$).
  * Drop qualification: a `DROP` is high only when preceded by `BUILD` or `BREAKDOWN`, and kick energy exceeds the song's rolling 95th percentile.

## Decision 7: Immutable Snapshots & Thread Concurrency
* **Rationale:** Mutating a shared state object while a 30 FPS render loop reads it causes torn reads and array race conditions.
* **Implementation:**
  * `MusicAnalyzer` outputs an immutable, frozen or copy-safe `MusicState` snapshot.
  * The audio worker publishes this snapshot atomically to a single-slot buffer (`self._latest_music_state`).
  * The visual renderer fetches the latest snapshot without locks, guaranteeing that rendering never stalls the audio thread.

## Decision 8: Upstream plugp100 Protocol Resilience (TPAP & KLAP Fallback)
* **Rationale:** The Tapo L930 (firmware 1.4.3 Build 260430) uses the TPAP transport. Upstream `plugp100`'s `TpapProtocol._load_json_dict` calls `payload.decode()` using strict UTF-8. When an effect ID stored on the device contains non-UTF-8 bytes (e.g. byte `0xBE` in `DynamicZones`), `json.loads` crashed with `UnicodeDecodeError`. In default auto-guessing mode, this caused `plugp100` to mark the IP as unavailable and falsely report `HostUnreachableError`.
* **Implementation:**
  * Created `src/tapo_patch.py`, monkey-patching `TpapProtocol._load_json_dict` and `KlapChiper.decrypt` with a `latin-1` fallback decoder that never raises on any byte sequence $0..255$.
  * Configured multi-protocol direct fallback in `L930Controller.connect()` (TPAP preferred) and `LightController.connect()` (KLAP v2 preferred), enabling instant ~1-second connection to both physical strips.

## Decision 9: Brickwall Dynamic Range Normalization & Silence Capping
* **Rationale:** In tracks with high continuous RMS (brickwalled masters or loud synth passages), naively subtracting $p_5$ collapsed dynamic range: $(0.15 - 0.15) \to 0.0$. Multiplying uncapped $p_5$ to determine silence caused audible music to falsely trigger silence shutdown.
* **Implementation:**
  * Normalized energy lower bound is clamped against the silence gate floor:
    $$\text{floor} = \min(0.010, p_5), \quad \Delta_{\text{dyn}} = \max(0.030, p_{95} - \text{floor})$$
    $$\text{norm\_energy} = \min\left(1.0, \frac{\text{rms} - \text{floor}}{\Delta_{\text{dyn}}} \cdot \text{sensitivity}\right)$$
  * Silence threshold is strictly capped: $\text{silence\_thresh} = \max(0.0020, \min(0.010, p_5 \cdot 1.20))$. Audible passages ($> -40\text{ dBFS}$) never trigger false silence.

## Decision 10: Strict Drop White Flash Gating & Preceding Build Requirement
* **Rationale:** Frequent or spurious white flashes ruin the visual drama of drops.
* **Implementation:**
  * White flash in `PulseStyle` and `MusicReactive` strictly requires:
    1. `section == Section.DROP`
    2. `drop_strength > 0.82`
    3. `impact > 0.80`
    4. Preceding `BUILD` or `BREAKDOWN` within the last $12\text{ s}$ (`now - last_build_time <= 12.0`)
    5. Cooldown $\ge 8.0\text{ s}$
  * Prevents white flash from triggering during dialogue, transitions, or ordinary verse kicks.

## Decision 11: Two-Axis Decoupled Visual Styles vs Audio Source Presets
* **Rationale:** Genre modes conflated "how the music sounds" with "how the lights look".
* **Implementation:**
  * 8 Pure Visual Styles (`Pulse`, `Spectrum`, `Aurora`, `Wave`, `Cinematic`, `Ambient`, `Particles`, `Hybrid`) solely render visual aesthetics from `MusicState`. `CinematicStyle` has zero hardcoded dialogue branching.
  * Audio Source Presets (`SourcePreset.STANDARD`, `SourcePreset.MOVIE`, `SourcePreset.LIVE`) adjust DSP frequency weighting in `MusicAnalyzer`: `SourcePreset.MOVIE` monitors dialogue dominance ($250\text{ Hz} \to 3400\text{ Hz}$) and applies gentle dialogue dimming so speaking scenes stay cozy and subtle while action explosions burst through dynamically.

## Decision 12: Single Audio Capture Loopback Thread (`AudioCaptureCoordinator`)
* **Rationale:** Previously, both `MusicReactive` and `MusicReactiveL930` ran independent soundcard loopback capture threads and duplicated DSP routines, desynchronizing strip palettes, causing beat-phase discordance, and overloading CPU scheduling.
* **Implementation:**
  * `AudioCaptureCoordinator` owns the single active audio loopback stream.
  * Writes incoming blocks to an `AudioRingBuffer` and executes a single `MusicAnalyzer` instance.
  * Atomically publishes an immutable `MusicState` snapshot and timing metadata to an atomic slot.
  * Started automatically when any strip enters audio reactive mode and stopped cleanly when all strips exit.

## Decision 13: Dedicated 60 Hz Render Thread Per Hardware Device
* **Rationale:** Coupling rendering directly to audio block arrival (~23 ms) caused rendering to stall whenever network latency backed up, dropping FPS and freezing animations.
* **Implementation:**
  * Dedicated 60 Hz `_render_loop()` per device (`MusicReactiveL930` and `MusicReactive`).
  * Each device owns its own isolated style instances created via `create_style_instances()`, preventing mutable state leaks.
  * Renders with actual measured frame delta $\Delta t$ and submits frames to `LatestFrameSender`, completely decoupling audio analysis from network transmission.

## Decision 14: Per-Stage Latency Telemetry & Real-Time Backlog Detection
* **Rationale:** Pinpointing lag required verifiable measurements across every step of the pipeline.
* **Implementation:**
  * Frames track 6 explicit timestamps: $t_{\text{audio\_recv}} \to t_{\text{analysis\_done}} \to t_{\text{frame\_rendered}} \to t_{\text{frame\_submitted}} \to t_{\text{http\_sent}} \to t_{\text{http\_resp}}$.
  * `DeviceDiagnostics` records rolling medians and p95 percentiles for each stage: `analysis`, `render`, `queue`, `http`, and `e2e`.
  * Backlog warnings are emitted if $\Delta t_{\text{analysis}} > 0.80 \times \Delta t_{\text{block}}$, signaling CPU saturation before audio queues overflow.

## Decision 15: Low-Pass Kick Envelope & Log-Interpolated Filterbank Continuity
* **Rationale:** High-frequency transients (hats, snares) contaminated kick detection, while discrete FFT bin masking caused low-frequency sub-bass bins to be empty.
* **Implementation:**
  * `LowPassKickDetector` employs a 2nd-order IIR Butterworth low-pass filter ($f_c = 120\text{ Hz}$) followed by an asymmetric attack/decay envelope follower.
  * 50 log bands are mapped via continuous piecewise linear interpolation (`np.interp`) over logarithmically spaced centers ($20\text{ Hz} \to 16000\text{ Hz}$), guaranteeing positive continuous energy across all bands without empty bins.

## Decision 16: Persistent Accent Envelopes & High-Confidence Beat Lookahead
* **Rationale:** Single-frame flashes were invisible at 15 Hz network send rates or looked like rendering glitches. Premature lookahead caused lights to jump ahead on weak rhythms.
* **Implementation:**
  * Transient visual events (white flash, drop bloom, beat pops) use continuous attack-hold-decay state machines: $\ge 30\text{ ms}$ attack, $\ge 120\text{ ms}$ hold, $\ge 400\text{ ms}$ decay.
  * Lookahead compensation is gated strictly to `bpm_confidence >= 0.65`, ensuring lights only advance ahead when tempo lock is stable and confident.

