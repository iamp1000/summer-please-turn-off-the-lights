from __future__ import annotations
import math
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Callable
import numpy as np

from src.audio_dsp import MusicAnalyzer, MusicState, Section

@dataclass
class ReplaySummary:
    duration_seconds: float
    total_frames: int
    bpm: float
    key: str
    mode: str
    sections_detected: List[Tuple[float, str]]
    drop_count: int
    avg_energy: float
    peak_energy: float


class FakeDeviceSimulator:
    """
    Simulates Tapo physical hardware (L900 single-zone and L930 50-zone)
    for deterministic offline testing, verifying frame rates, boundary bounds, and drop cooldowns.
    """

    def __init__(self, model: str = "L930"):
        self.model = model
        self.frames: List[Dict[str, Any]] = []
        self.last_submitted_frame: Dict[str, Any] | None = None
        self.timestamps: List[float] = []

    def submit_frame(self, frame_data: dict):
        self.frames.append(frame_data)
        self.last_submitted_frame = frame_data
        self.timestamps.append(time.monotonic())

    def clear_frames(self):
        self.frames.clear()


class WavReplayer:
    """
    Loads loopback audio recordings from WAV files and replays them
    through MusicAnalyzer deterministically for tuning and automated benchmarking.
    """

    def __init__(self, analyzer: MusicAnalyzer | None = None, blocksize: int = 1024):
        self.blocksize = blocksize
        self.analyzer = analyzer or MusicAnalyzer(samplerate=44100, blocksize=blocksize)
        self.state_history: List[MusicState] = []
        self.timestamps: List[float] = []

    def load_wav(self, file_path: str | Path) -> Tuple[np.ndarray, int]:
        """Loads WAV audio file and converts to float32 mono in [-1.0, 1.0]."""
        with wave.open(str(file_path), "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw_bytes = wf.readframes(n_frames)

        if sampwidth == 2:
            data = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            data = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
        elif sampwidth == 1:
            data = (np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        else:
            raise ValueError(f"Unsupported WAV sample width: {sampwidth}")

        if channels > 1:
            data = data.reshape(-1, channels)
            data = np.mean(data, axis=1)

        return data, framerate

    def replay_buffer(
        self,
        samples: np.ndarray,
        samplerate: int = 44100,
        realtime: bool = False,
        on_frame: Optional[Callable[[MusicState, int], None]] = None
    ) -> ReplaySummary:
        """
        Replays audio buffer through the analyzer.
        realtime=True: sleeps between blocks for live wall-clock pacing.
        realtime=False: processes as fast as CPU allows for regression testing.
        """
        self.state_history.clear()
        self.timestamps.clear()

        n_samples = len(samples)
        block_sec = self.blocksize / samplerate
        sim_time = 0.0

        sections_detected: List[Tuple[float, str]] = []
        last_section = None
        drop_count = 0

        for start_idx in range(0, n_samples - self.blocksize, self.blocksize):
            chunk = samples[start_idx : start_idx + self.blocksize]
            sim_time += block_sec

            state = self.analyzer.process_samples(chunk, now=sim_time)
            self.state_history.append(state)
            self.timestamps.append(sim_time)

            if state.section.value != last_section:
                sections_detected.append((round(sim_time, 2), state.section.value))
                last_section = state.section.value

            if state.section == Section.DROP:
                drop_count += 1

            if on_frame:
                on_frame(state, start_idx)

            if realtime:
                time.sleep(block_sec)

        energies = [s.energy for s in self.state_history]
        last_state = self.state_history[-1] if self.state_history else MusicState()

        return ReplaySummary(
            duration_seconds=round(n_samples / samplerate, 2),
            total_frames=len(self.state_history),
            bpm=last_state.bpm,
            key=f"{last_state.key_hue:.0f}°",
            mode=last_state.mode,
            sections_detected=sections_detected,
            drop_count=drop_count,
            avg_energy=round(float(np.mean(energies)), 3) if energies else 0.0,
            peak_energy=round(float(np.max(energies)), 3) if energies else 0.0
        )

    def replay_file(self, file_path: str | Path, realtime: bool = False) -> ReplaySummary:
        samples, sr = self.load_wav(file_path)
        return self.replay_buffer(samples, samplerate=sr, realtime=realtime)


# ── Synthetic Reference Audio Test Suite Generator ────────────────────────────

class SyntheticTrackGenerator:
    """
    Generates deterministic reference tracks for regression testing:
    1. EDM Build & Drop: 128 BPM 4-on-the-floor, climbing snare roll, 1-beat silence, sub-bass drop.
    2. Classical Orchestral Swell: A minor violin/cello swell from pianissimo to fortissimo.
    3. Calm Lo-Fi: 80 BPM mellow chill groove.
    """

    @staticmethod
    def generate_edm_track(duration: float = 16.0, samplerate: int = 44100) -> np.ndarray:
        t = np.linspace(0, duration, int(duration * samplerate), endpoint=False)
        output = np.zeros_like(t)

        bpm = 128.0
        beat_dur = 60.0 / bpm

        # 0.0s - 8.0s: Verse (4-on-the-floor kick)
        # 8.0s - 12.0s: Build (accelerating snare roll + frequency sweep riser)
        # 12.0s - 12.4s: Breakdown / Silence
        # 12.4s - 16.0s: Drop (huge sub-bass 45Hz + noise burst + kick)

        for i in range(int(duration / beat_dur)):
            beat_t = i * beat_dur
            if beat_t >= duration: break

            # Verse Kicks
            if beat_t < 8.0 or beat_t >= 12.4:
                kick_len = int(0.18 * samplerate)
                idx = int(beat_t * samplerate)
                end = min(len(output), idx + kick_len)
                kt = np.linspace(0, 0.18, end - idx)
                # Pitch drop kick 130 Hz -> 45 Hz
                f_kick = 45.0 + 85.0 * np.exp(-kt * 35.0)
                phase = 2.0 * np.pi * np.cumsum(f_kick) / samplerate
                env = np.exp(-kt * 22.0)
                output[idx:end] += 0.85 * np.sin(phase) * env

            # Drop Sub-bass
            if beat_t >= 12.4:
                idx = int(beat_t * samplerate)
                end = min(len(output), idx + int(beat_dur * samplerate))
                st = np.linspace(0, beat_dur, end - idx)
                output[idx:end] += 0.70 * np.sin(2.0 * np.pi * 48.0 * st)

        # Build riser (8.0s - 12.0s)
        build_mask = (t >= 8.0) & (t < 12.0)
        t_build = t[build_mask] - 8.0
        sweep_f = 200.0 + 800.0 * (t_build / 4.0) ** 2
        sweep_phase = 2.0 * np.pi * np.cumsum(sweep_f) / samplerate
        amp = (t_build / 4.0) * 0.75
        output[build_mask] += amp * np.sin(sweep_phase)

        # Silence breakdown (12.0s - 12.4s)
        break_mask = (t >= 12.0) & (t < 12.4)
        output[break_mask] = 0.0

        return np.clip(output, -1.0, 1.0).astype(np.float32)

    @staticmethod
    def generate_classical_track(duration: float = 12.0, samplerate: int = 44100) -> np.ndarray:
        t = np.linspace(0, duration, int(duration * samplerate), endpoint=False)
        output = np.zeros_like(t)

        # Dynamic swell envelope (pianissimo pp to fortissimo ff)
        # Envelope: 0.15 at t=0, swells to 0.95 at t=8.0, decays to 0.20
        env = 0.15 + 0.80 * np.sin((t / duration) * np.pi)

        # A minor chord harmonics: A3 (220 Hz), C4 (261.6 Hz), E4 (329.6 Hz), A4 (440 Hz)
        harmonics = [
            (220.0, 0.40),
            (261.6, 0.30),
            (329.6, 0.25),
            (440.0, 0.20),
            (659.2, 0.10),
            (880.0, 0.08),
        ]
        for freq, weight in harmonics:
            output += weight * np.sin(2.0 * np.pi * freq * t)

        output *= env
        return np.clip(output, -1.0, 1.0).astype(np.float32)

    @staticmethod
    def generate_click_track(bpm: float = 128.0, duration: float = 8.0, samplerate: int = 44100) -> np.ndarray:
        """Generates sharp, unambiguous periodic clicks at exact BPM intervals."""
        n_samples = int(duration * samplerate)
        output = np.zeros(n_samples, dtype=np.float32)
        beat_interval = 60.0 / bpm
        click_len = int(0.012 * samplerate)

        # 1 kHz click blip with steep decay
        t_click = np.linspace(0, 0.012, click_len, endpoint=False)
        click_wave = (np.sin(2 * np.pi * 1000.0 * t_click) * np.exp(-t_click * 350.0)).astype(np.float32)

        cur_t = 0.0
        while cur_t < duration:
            idx = int(cur_t * samplerate)
            if idx + click_len <= n_samples:
                output[idx : idx + click_len] += 0.90 * click_wave
            cur_t += beat_interval

        return output

    @staticmethod
    def generate_half_time_pattern(bpm: float = 140.0, duration: float = 8.0, samplerate: int = 44100) -> np.ndarray:
        """Generates a half-time pattern (Kick on beat 1, Snare on beat 3)."""
        n_samples = int(duration * samplerate)
        output = np.zeros(n_samples, dtype=np.float32)
        beat_interval = 60.0 / bpm
        beat_idx = 0
        cur_t = 0.0

        while cur_t < duration:
            idx = int(cur_t * samplerate)
            bar_beat = beat_idx % 4

            if bar_beat == 0 and idx + int(0.15 * samplerate) <= n_samples:
                # Kick (60 Hz punch)
                k_len = int(0.15 * samplerate)
                kt = np.linspace(0, 0.15, k_len)
                output[idx : idx + k_len] += 0.85 * np.sin(2 * np.pi * 60.0 * kt) * np.exp(-kt * 25.0)
            elif bar_beat == 2 and idx + int(0.12 * samplerate) <= n_samples:
                # Snare (noise burst + 220 Hz tone)
                s_len = int(0.12 * samplerate)
                st = np.linspace(0, 0.12, s_len)
                noise = np.random.uniform(-0.5, 0.5, s_len)
                output[idx : idx + s_len] += (0.6 * np.sin(2 * np.pi * 220.0 * st) + 0.4 * noise) * np.exp(-st * 20.0)

            cur_t += beat_interval
            beat_idx += 1

        return np.clip(output, -1.0, 1.0).astype(np.float32)

    @staticmethod
    def generate_sine_sweep(f_start: float = 40.0, f_end: float = 4000.0, duration: float = 4.0, samplerate: int = 44100) -> np.ndarray:
        """Generates an exponential sinusoidal frequency sweep."""
        t = np.linspace(0, duration, int(duration * samplerate), endpoint=False)
        phase = 2.0 * np.pi * f_start * (math.pow(f_end / f_start, 1.0 / duration) ** t - 1.0) / math.log(f_end / f_start)
        return (0.75 * np.sin(phase)).astype(np.float32)

    @staticmethod
    def generate_white_noise_bursts(duration: float = 4.0, burst_interval: float = 0.5, burst_len: float = 0.08, samplerate: int = 44100) -> np.ndarray:
        """Generates periodic white noise bursts with silence gaps."""
        n_samples = int(duration * samplerate)
        output = np.zeros(n_samples, dtype=np.float32)
        b_samples = int(burst_len * samplerate)

        cur_t = 0.0
        while cur_t < duration:
            idx = int(cur_t * samplerate)
            if idx + b_samples <= n_samples:
                output[idx : idx + b_samples] = np.random.uniform(-0.7, 0.7, b_samples).astype(np.float32)
            cur_t += burst_interval

        return output

    @staticmethod
    def generate_silence(duration: float = 3.0, samplerate: int = 44100) -> np.ndarray:
        """Generates pure digital silence."""
        return np.zeros(int(duration * samplerate), dtype=np.float32)

    @staticmethod
    def generate_build_and_drop(duration: float = 14.0, samplerate: int = 44100) -> np.ndarray:
        """Synthetic build (rising filtered noise and accelerating density), breakdown, then drop."""
        return SyntheticTrackGenerator.generate_edm_track(duration=duration, samplerate=samplerate)

