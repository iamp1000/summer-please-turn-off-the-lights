"""
Audio Evaluation CLI.

Runs MusicAnalyzer offline over any WAV file or synthetic benchmark.
Exports:
  1. Detailed CSV telemetry log (sections, transitions, BPM, energy, impact, drop_strength, white-flash events).
  2. Standalone interactive HTML timeline visualizer.
  3. Ground-truth transition timing error analysis (if --labels CSV is provided).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import wave
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.audio_dsp import MusicAnalyzer, MusicState, Section, SourcePreset
from src.audio_replay import SyntheticTrackGenerator


def read_wav_mono(path: str) -> Tuple[np.ndarray, int]:
    """Reads a WAV file and converts it to float32 mono [-1.0, 1.0]."""
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n_ch = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        dtype = np.int16
        scale = 32768.0
    elif sampwidth == 4:
        dtype = np.int32
        scale = 2147483648.0
    elif sampwidth == 1:
        dtype = np.uint8
        scale = 128.0
    else:
        raise ValueError(f"Unsupported sample width: {sampwidth}")

    data = np.frombuffer(raw, dtype=dtype)
    if sampwidth == 1:
        data = (data.astype(np.float32) - 128.0) / 128.0
    else:
        data = data.astype(np.float32) / scale

    if n_ch > 1:
        data = data.reshape(-1, n_ch).mean(axis=1)

    return data, sr


def analyze_audio_file(
    samples: np.ndarray,
    samplerate: int,
    blocksize: int = 1024,
    preset: str = "standard",
    sensitivity: float = 1.0,
    lookahead_ms: float = 40.0,
) -> List[Dict[str, Any]]:
    analyzer = MusicAnalyzer(
        samplerate=samplerate,
        blocksize=blocksize,
        sensitivity=sensitivity,
        latency_lookahead_ms=lookahead_ms,
    )
    analyzer.set_source_preset(preset)

    records: List[Dict[str, Any]] = []
    prev_section = Section.SILENT
    white_cooldown = 0.0

    n_samples = len(samples)
    for start in range(0, n_samples - blocksize + 1, blocksize):
        chunk = samples[start : start + blocksize]
        t = start / float(samplerate)
        dt = blocksize / float(samplerate)
        white_cooldown = max(0.0, white_cooldown - dt)

        st: MusicState = analyzer.process_samples(chunk, now=t)

        is_transition = (st.section != prev_section)
        prev_section = st.section

        is_white_flash = False
        if st.section == Section.DROP and st.drop_strength > 0.82 and st.impact > 0.80 and white_cooldown <= 0.0:
            is_white_flash = True
            white_cooldown = 8.0

        records.append({
            "timestamp": round(t, 4),
            "section": st.section.value,
            "section_transition": is_transition,
            "section_age": round(st.section_age, 3),
            "bpm": round(st.bpm, 1),
            "bpm_confidence": round(st.bpm_confidence, 3),
            "beat_phase": round(st.beat_phase, 3),
            "energy": round(st.energy, 4),
            "energy_trend": round(st.energy_trend, 4),
            "drop_strength": round(st.drop_strength, 4),
            "impact": round(st.impact, 4),
            "white_flash": is_white_flash,
            "key_hue": round(st.key_hue, 1),
            "mode": st.mode,
            "key_confidence": round(st.key_confidence, 3),
            "silent": st.silent,
        })

    return records


def export_csv(records: List[Dict[str, Any]], out_path: str):
    if not records:
        return
    fieldnames = list(records[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"[AudioCLI] Exported telemetry CSV to: {out_path}")


def evaluate_labels(records: List[Dict[str, Any]], labels_path: str):
    """Compares detected section transitions with ground-truth CSV."""
    truth: List[Tuple[float, str]] = []
    with open(labels_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            truth.append((float(row["timestamp"]), row["section"].strip().upper()))

    detected_transitions = [
        (r["timestamp"], r["section"])
        for r in records
        if r["section_transition"]
    ]

    print("\n" + "=" * 60)
    print(f"GROUND TRUTH EVALUATION: {labels_path}")
    print("=" * 60)
    print(f"{'Truth Time':<12} {'Expected Section':<18} {'Detected Time':<14} {'Delta (ms)':<10}")
    print("-" * 60)

    errors_ms = []
    for t_time, t_sec in truth:
        # Find closest detected transition matching this section
        matches = [d for d in detected_transitions if d[1] == t_sec]
        if matches:
            closest = min(matches, key=lambda x: abs(x[0] - t_time))
            delta_ms = (closest[0] - t_time) * 1000.0
            errors_ms.append(abs(delta_ms))
            print(f"{t_time:<12.3f} {t_sec:<18} {closest[0]:<14.3f} {delta_ms:+9.1f}ms")
        else:
            print(f"{t_time:<12.3f} {t_sec:<18} {'MISSING':<14} {'N/A':<10}")

    if errors_ms:
        mae = sum(errors_ms) / len(errors_ms)
        max_err = max(errors_ms)
        print("-" * 60)
        print(f"Mean Absolute Error (MAE): {mae:.1f} ms  |  Max Error: {max_err:.1f} ms")
    print("=" * 60 + "\n")


def generate_html_report(records: List[Dict[str, Any]], audio_name: str, out_path: str):
    """Generates an interactive standalone HTML5 timeline visualizer."""
    # Subsample records for fast rendering if track is long
    step = max(1, len(records) // 1200)
    sub = records[::step]

    times = [r["timestamp"] for r in sub]
    energies = [r["energy"] for r in sub]
    bpms = [r["bpm"] for r in sub]
    confidences = [r["bpm_confidence"] for r in sub]
    drop_strs = [r["drop_strength"] for r in sub]
    white_flashes = [r["timestamp"] for r in records if r["white_flash"]]
    sections = [r["section"] for r in sub]

    transitions = [r for r in records if r["section_transition"]]

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Music State Visualizer — {audio_name}</title>
<style>
  :root {{
    --bg: #0b0f19;
    --card: rgba(22, 30, 49, 0.75);
    --border: rgba(255, 255, 255, 0.08);
    --text: #e2e8f0;
    --accent: #38bdf8;
    --drop: #f43f5e;
    --build: #f59e0b;
    --verse: #10b981;
    --break: #8b5cf6;
    --intro: #06b6d4;
    --silent: #475569;
  }}
  body {{
    margin: 0;
    padding: 24px;
    background: radial-gradient(circle at 50% 0%, #1e1b4b 0%, var(--bg) 60%);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: var(--text);
  }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 28px; margin-bottom: 4px; font-weight: 700; }}
  .subtitle {{ color: #94a3b8; margin-bottom: 24px; font-size: 14px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    backdrop-filter: blur(16px);
    border-radius: 14px;
    padding: 16px;
  }}
  .stat-label {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }}
  .stat-value {{ font-size: 24px; font-weight: 700; margin-top: 4px; color: #fff; }}
  .canvas-card {{ margin-bottom: 24px; }}
  canvas {{ width: 100%; height: 260px; display: block; border-radius: 8px; }}
  .legend {{ display: flex; gap: 16px; margin-top: 12px; flex-wrap: wrap; font-size: 12px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 10px; height: 10px; border-radius: 3px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: #94a3b8; font-weight: 600; text-transform: uppercase; font-size: 11px; }}
</style>
</head>
<body>
<div class="container">
  <h1>\U0001f3b5 Music Analyzer Evaluation Report</h1>
  <div class="subtitle">Track: {audio_name} | Total Frames: {len(records)} | Timespan: {times[-1] if times else 0:.1f}s</div>

  <div class="grid">
    <div class="card">
      <div class="stat-label">Estimated Tempo</div>
      <div class="stat-value">{bpms[-1] if bpms else 120:.1f} <span style="font-size:14px;color:#94a3b8;">BPM</span></div>
    </div>
    <div class="card">
      <div class="stat-label">BPM Confidence</div>
      <div class="stat-value">{int(confidences[-1] * 100 if confidences else 0)}%</div>
    </div>
    <div class="card">
      <div class="stat-label">Musical Key & Mode</div>
      <div class="stat-value">{records[-1]["mode"].upper() if records else "MAJOR"} <span style="font-size:14px;color:#94a3b8;">({records[-1]["key_hue"] if records else 0}\u00b0)</span></div>
    </div>
    <div class="card">
      <div class="stat-label">Drop White Flashes</div>
      <div class="stat-value" style="color:var(--drop);">{len(white_flashes)} <span style="font-size:14px;color:#94a3b8;">Hits</span></div>
    </div>
  </div>

  <div class="card canvas-card">
    <h3 style="margin-top:0;">Timeline & Section Dynamics</h3>
    <canvas id="timelineChart"></canvas>
    <div class="legend">
      <div class="legend-item"><div class="dot" style="background:#38bdf8;"></div> Energy (0-1)</div>
      <div class="legend-item"><div class="dot" style="background:#f43f5e;"></div> Drop Strength</div>
      <div class="legend-item"><div class="dot" style="background:#ffffff; border:1px solid #aaa;"></div> White Flash Marker</div>
      <div class="legend-item"><div class="dot" style="background:var(--build);"></div> Build Section</div>
      <div class="legend-item"><div class="dot" style="background:var(--drop);"></div> Drop Section</div>
      <div class="legend-item"><div class="dot" style="background:var(--break);"></div> Breakdown</div>
    </div>
  </div>

  <div class="card">
    <h3 style="margin-top:0;">Detected Section Transitions</h3>
    <table>
      <thead>
        <tr><th>Timestamp</th><th>Section</th><th>Duration</th><th>Energy at Switch</th></tr>
      </thead>
      <tbody>
        {"".join(f"<tr><td>{t['timestamp']:.2f}s</td><td><b style='color:{get_sec_color(t['section'])};'>{t['section']}</b></td><td>{t['section_age']:.2f}s</td><td>{int(t['energy']*100)}%</td></tr>" for t in transitions)}
      </tbody>
    </table>
  </div>
</div>

<script>
const times = {json.dumps(times)};
const energies = {json.dumps(energies)};
const drops = {json.dumps(drop_strs)};
const sections = {json.dumps(sections)};
const whiteFlashes = {json.dumps(white_flashes)};

const canvas = document.getElementById("timelineChart");
const ctx = canvas.getContext("2d");

function resize() {{
  canvas.width = canvas.clientWidth * window.devicePixelRatio;
  canvas.height = canvas.clientHeight * window.devicePixelRatio;
  draw();
}}

function getSecColor(sec) {{
  switch(sec) {{
    case "DROP": return "rgba(244, 63, 94, 0.25)";
    case "BUILD": return "rgba(245, 158, 11, 0.25)";
    case "BREAKDOWN": return "rgba(139, 92, 246, 0.25)";
    case "VERSE": return "rgba(16, 185, 129, 0.15)";
    case "INTRO": return "rgba(6, 182, 212, 0.15)";
    default: return "rgba(71, 85, 105, 0.10)";
  }}
}}

function draw() {{
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const n = times.length;
  if (n < 2) return;

  // Draw Section Background bands
  for (let i = 0; i < n - 1; i++) {{
    const x0 = (i / n) * w;
    const x1 = ((i + 1) / n) * w;
    ctx.fillStyle = getSecColor(sections[i]);
    ctx.fillRect(x0, 0, x1 - x0, h);
  }}

  // Draw Energy Line
  ctx.beginPath();
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 2 * window.devicePixelRatio;
  for (let i = 0; i < n; i++) {{
    const x = (i / n) * w;
    const y = h - (energies[i] * (h - 20) + 10);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }}
  ctx.stroke();

  // Draw Drop Strength Line
  ctx.beginPath();
  ctx.strokeStyle = "#f43f5e";
  ctx.lineWidth = 1.5 * window.devicePixelRatio;
  for (let i = 0; i < n; i++) {{
    const x = (i / n) * w;
    const y = h - (drops[i] * (h - 20) + 10);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }}
  ctx.stroke();

  // Draw White Flash Markers
  whiteFlashes.forEach(wt => {{
    const idx = times.findIndex(t => t >= wt);
    if (idx >= 0) {{
      const x = (idx / n) * w;
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2 * window.devicePixelRatio;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();

      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(x, 15, 5, 0, Math.PI * 2);
      ctx.fill();
    }}
  }});
}}

window.addEventListener("resize", resize);
resize();
</script>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[AudioCLI] Exported interactive visualizer report to: {out_path}")


def get_sec_color(sec: str) -> str:
    palette = {
        "DROP": "#f43f5e",
        "BUILD": "#f59e0b",
        "BREAKDOWN": "#8b5cf6",
        "VERSE": "#10b981",
        "INTRO": "#06b6d4",
        "SILENT": "#64748b",
        "OUTRO": "#64748b",
    }
    return palette.get(sec, "#e2e8f0")


def run_click_flasher_calibration(lookahead_ms: float = 40.0, bpm: float = 128.0, duration: float = 8.0):
    """
    Flashes connected light strips synchronously with an audible click track.
    Allows user to tune lookahead_ms by eye and ear until exact lockstep is achieved.
    """
    try:
        import sounddevice as sd
    except ImportError:
        print("[AudioCLI] sounddevice package required for audible click playback.")
        return

    import time
    sr = 44100
    clicks = SyntheticTrackGenerator.generate_click_track(bpm=bpm, duration=duration, samplerate=sr)

    print(f"\n[Visual Flasher] Starting {duration}s calibration click track at {bpm} BPM (Lookahead: {lookahead_ms}ms)...")
    print("[Visual Flasher] Watch lights and listen to clicks through speakers to verify lockstep.")

    sd.play(clicks, samplerate=sr)

    hub = None
    try:
        from src.hub import TapoHub
        hub = TapoHub()
    except Exception as e:
        print(f"[Visual Flasher] Hub connection note: {e}")

    if hub:
        for dev in hub.devices.values():
            hub.arbiter.claim_output(dev.dev_id, OutputProducer.STATIC)
            try:
                if not getattr(dev.controller, "_is_on", True):
                    hub.loop_runner.run(dev.controller.turn_on(priority=0)).result(timeout=10.0)
            except Exception as e:
                print(f"[Visual Flasher] Could not power on {dev.dev_id}: {e}")

    beat_interval = 60.0 / bpm
    lead_sec = lookahead_ms / 1000.0
    start_time = time.monotonic()

    beat_idx = 0
    while (time.monotonic() - start_time) < duration:
        expected_audio_beat = start_time + beat_idx * beat_interval
        flash_send_time = expected_audio_beat - lead_sec
        now = time.monotonic()
        if now < flash_send_time:
            time.sleep(max(0.001, flash_send_time - now))

        if hub:
            from src.frame_bus import FramePacket, OutputProducer
            for dev in hub.devices.values():
                if dev.model == "L900":
                    hub.frame_bus.publish(FramePacket(
                        dev_id=dev.dev_id, producer=OutputProducer.STATIC,
                        hsv=(180, 0, 100), brightness=100,
                        generation=hub.arbiter.get_generation(dev.dev_id),
                    ))
                else:
                    hub.frame_bus.publish(FramePacket(
                        dev_id=dev.dev_id, producer=OutputProducer.STATIC,
                        segments=[[180, 0, 100]] * 50, brightness=100,
                        generation=hub.arbiter.get_generation(dev.dev_id),
                    ))

        time.sleep(0.060)
        if hub:
            for dev in hub.devices.values():
                if dev.model == "L900":
                    hub.frame_bus.publish(FramePacket(
                        dev_id=dev.dev_id, producer=OutputProducer.STATIC,
                        hsv=(0, 0, 0), brightness=0,
                        generation=hub.arbiter.get_generation(dev.dev_id),
                    ))
                else:
                    hub.frame_bus.publish(FramePacket(
                        dev_id=dev.dev_id, producer=OutputProducer.STATIC,
                        segments=[[0, 0, 0]] * 50, brightness=0,
                        generation=hub.arbiter.get_generation(dev.dev_id),
                    ))

        beat_idx += 1

    sd.wait()
    print("[Visual Flasher] Calibration track finished.\n")


def main():
    parser = argparse.ArgumentParser(description="Real-Audio MusicAnalyzer Evaluation CLI")
    parser.add_argument("wav", nargs="?", default="", help="Path to WAV audio file (optional if --synthetic used)")
    parser.add_argument("--synthetic", choices=["build_drop", "click", "halftime", "sweep"], help="Generate synthetic test audio")
    parser.add_argument("--output-csv", default="evaluation_telemetry.csv", help="Path to export CSV log")
    parser.add_argument("--output-html", default="evaluation_report.html", help="Path to export HTML visualizer")
    parser.add_argument("--labels", default="", help="Path to ground truth labels CSV for transition error evaluation")
    parser.add_argument("--preset", default="standard", choices=["standard", "movie", "live"], help="Audio source preset")
    parser.add_argument("--sensitivity", type=float, default=1.0, help="Calibrator sensitivity")
    parser.add_argument("--lookahead-ms", type=float, default=40.0, help="Per-strip latency lookahead (ms)")
    parser.add_argument("--calibrate-flasher", action="store_true", help="Run visual click flasher calibration with audio output")

    args = parser.parse_args()

    if args.calibrate_flasher:
        run_click_flasher_calibration(lookahead_ms=args.lookahead_ms)
        return

    if args.synthetic:
        sr = 44100
        print(f"[AudioCLI] Generating synthetic benchmark track: {args.synthetic}...")
        if args.synthetic == "build_drop":
            samples = SyntheticTrackGenerator.generate_build_and_drop(duration=16.0)
        elif args.synthetic == "click":
            samples = SyntheticTrackGenerator.generate_click_track(bpm=128.0, duration=8.0)
        elif args.synthetic == "halftime":
            samples = SyntheticTrackGenerator.generate_half_time_pattern(bpm=140.0, duration=8.0)
        else:
            samples = SyntheticTrackGenerator.generate_sine_sweep(40.0, 4000.0, duration=4.0)
        audio_name = f"Synthetic_{args.synthetic}"
    elif args.wav and os.path.exists(args.wav):
        print(f"[AudioCLI] Loading WAV audio: {args.wav}...")
        samples, sr = read_wav_mono(args.wav)
        audio_name = Path(args.wav).stem
    else:
        print("[AudioCLI] No WAV supplied and no --synthetic specified. Running default Build & Drop synthetic track.")
        sr = 44100
        samples = SyntheticTrackGenerator.generate_build_and_drop(duration=16.0)
        audio_name = "Synthetic_Build_and_Drop"

    print(f"[AudioCLI] Analyzing {len(samples)} samples ({len(samples)/sr:.2f}s) at {sr} Hz...")
    records = analyze_audio_file(
        samples=samples,
        samplerate=sr,
        preset=args.preset,
        sensitivity=args.sensitivity,
        lookahead_ms=args.lookahead_ms,
    )

    export_csv(records, args.output_csv)
    generate_html_report(records, audio_name, args.output_html)

    if args.labels and os.path.exists(args.labels):
        evaluate_labels(records, args.labels)


if __name__ == "__main__":
    main()
