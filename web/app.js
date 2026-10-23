// Tapo Dual-Strip Light Hub - Advanced Web Client & Dynamic Glassmorphism Engine
let state = {
  devices: {},
  modes: [],
  effects_l900: [],
  effects_l930: [],
  diagnostics: {},
  visualizer_modes: []
};

let currentDevId = "strip1";
let currentEffectCategory = "creative";
let currentExperienceTab = "ambient";
let ws = null;
let reconnectTimer = null;

const EXPERIENCE_METADATA = {
  // Ambient
  tide: { tags: "Slow · Ambient", desc: "Overlapping ocean waves with different speeds and thin seafoam crests on dark teal.", tab: "ambient", cat: "core" },
  embers: { tags: "Warm · Low motion", desc: "Near-black background with dark-red coal beds and isolated orange embers glowing at varied rates.", tab: "ambient", cat: "core" },
  breathe: { tags: "Gentle · Meditative", desc: "Deliberate inhale/exhale envelope with slow relaxing color-temperature shift.", tab: "ambient", cat: "core" },
  drift: { tags: "Smooth · Color shifting", desc: "Slow hue advection traveling across strip with subtle overlapping color clouds.", tab: "ambient", cat: "core" },
  starfield: { tags: "Dark · Twinkling", desc: "Near-black navy background with isolated stars brightening, holding, and fading independently.", tab: "ambient", cat: "core" },
  fireflies: { tags: "Organic · Bioluminescent", desc: "Loose clusters of green-gold lights with asynchronous bloom, short peak, and long fade.", tab: "ambient", cat: "core" },
  lava_lamp: { tags: "Viscous · Fluid", desc: "Viscous molten metaballs stretching, merging, and separating with dark gaps.", tab: "ambient", cat: "core" },
  golden_hour: { tags: "Warm · Twilight", desc: "Warm amber-to-rose horizon with slow moving bands and rare golden glints.", tab: "ambient", cat: "core" },
  flicker: { tags: "Organic · Hearth glow", desc: "Warm candlelight flicker with gentle random micro-variations.", tab: "ambient", cat: "core" },
  candle_flicker: { tags: "Organic · Hearth glow", desc: "Warm candlelight flicker with gentle random micro-variations.", tab: "ambient", cat: "core" },
  sunrise: { tags: "Gradual · Dawn glow", desc: "Slow warming progression from deep rose dawn to bright warm daylight.", tab: "ambient", cat: "core" },
  sunset: { tags: "Relaxing · Dusk fade", desc: "Gentle transition from amber gold into deep twilight violet.", tab: "ambient", cat: "core" },
  fireplace: { tags: "Warm · Cozy hearth", desc: "Roaring fireplace with dancing flame tips and ember base.", tab: "ambient", cat: "core" },
  sakura: { tags: "Delicate · Blossom", desc: "Soft pastel cherry blossom petals drifting serenely.", tab: "ambient", cat: "core" },
  ambient_drift: { tags: "Soft · Lavender drift", desc: "Cosmic violet wave nodes floating continuously.", tab: "ambient", cat: "core" },

  // Motion
  aurora: { tags: "Flowing · Atmospheric", desc: "Vertical celestial ribbons of violet, purple, and green-teal waving smoothly.", tab: "motion", cat: "core" },
  cyber_chase: { tags: "Motion · Energetic", desc: "High-speed electric cyan and magenta streaks racing with intense neon contrast.", tab: "motion", cat: "core" },
  comet: { tags: "Directional · Fast sweep", desc: "Streaking celestial head with long exponential fading tail.", tab: "motion", cat: "core" },
  sinelon: { tags: "Smooth · Pendulum sweep", desc: "Harmonic laser beam oscillating smoothly back and forth.", tab: "motion", cat: "core" },
  deep_ocean: { tags: "Aquatic · Deep pulse", desc: "Deep oceanic blue and cyan currents swelling and rippling in abyss.", tab: "motion", cat: "core" },
  raindrop: { tags: "Dynamic · Splash ripple", desc: "Scattered raindrops splashing with concentric expanding ripples.", tab: "motion", cat: "core" },
  lightning: { tags: "Dramatic · Storm flash", desc: "High-energy electrical storm with sudden branching lightning discharges.", tab: "motion", cat: "core" },
  rainbow: { tags: "Vibrant · Spectrum flow", desc: "Smooth continuous prismatic spectrum looping continuously.", tab: "motion", cat: "core" },
  meteor_shower: { tags: "Advanced · Multi-streak", desc: "Independent falling meteors streaking across the sky.", tab: "motion", cat: "advanced" },
  juggle: { tags: "Advanced · Multi-orb", desc: "Independently traveling colored orbs weaving together.", tab: "motion", cat: "advanced" },
  spiral_vortex: { tags: "Advanced · Rotational", desc: "Hypnotic rotational spiral winding into a center core.", tab: "motion", cat: "advanced" },
  gravity_slosh: { tags: "Advanced · Inertial", desc: "Viscous liquid sloshing with realistic boundary rebound physics.", tab: "motion", cat: "advanced" },
  lissajous_orbit: { tags: "Advanced · Geometric", desc: "Harmonic 3D Lissajous figure-8 spatial curve.", tab: "motion", cat: "advanced" },
  planar_wind: { tags: "Advanced · Directional", desc: "Directional atmospheric wave advecting smoothly.", tab: "motion", cat: "advanced" },
  radar_sweep: { tags: "Advanced · Phosphor sweep", desc: "360-degree rotating radar sweep with decaying phosphor echo.", tab: "motion", cat: "advanced" },
  vaporwave_neon: { tags: "Aesthetic · Retro 80s", desc: "Broad magenta and cyan synthwave aesthetic bands.", tab: "motion", cat: "advanced" },
  neon_heartbeat: { tags: "Rhythmic · Cardiac pulse", desc: "Realistic double-pulse cardiac rhythm with resting pause.", tab: "motion", cat: "advanced" },
  lantern_sweep: { tags: "Warm · Ambient motion", desc: "Warm slow lantern pendulum swaying gently.", tab: "motion", cat: "advanced" },
  candy_cane: { tags: "Seasonal · Holiday stripes", desc: "Festive rotating red and white peppermint candy stripes.", tab: "motion", cat: "seasonal" },
  haunted_mansion: { tags: "Seasonal · Spooky mist", desc: "Eerie spectral green and deep phantom violet shadows.", tab: "motion", cat: "seasonal" },
  police: { tags: "Novelty · Emergency beacon", desc: "Smooth alternating red and blue emergency siren pulses.", tab: "motion", cat: "novelty", warning: "Emergency vehicle siren warning." },

  // Creative (L930 WRGBIC Spatial & Optical)
  oil_slick: { tags: "Iridescent · Thin film", desc: "Petrol-like interference waves drifting across cyan, indigo, violet, rose, and amber.", tab: "motion", cat: "creative" },
  silk_ribbons: { tags: "Flowing · Opposing currents", desc: "Broad soft-edged Gaussian ribbons flowing in counter-currents with OKLab blending.", tab: "motion", cat: "creative" },
  nebula_bloom: { tags: "Cosmic · Deep space", desc: "Expansive celestial gas clouds with subtle cosmic shifts and dark negative space.", tab: "motion", cat: "creative" },
  holographic_moire: { tags: "Optical · Interference", desc: "Detuned spatial carrier wave interference creating macroscopic holographic light fringes.", tab: "motion", cat: "creative" },
  bioluminescent_tide: { tags: "Marine · Ocean swell", desc: "Multi-layer ocean swell simulation with glowing cyan crest highlights on dark navy.", tab: "motion", cat: "creative" },
  ember_drift: { tags: "Thermal · Heat bed", desc: "Convective heat bed with drifting copper and amber coals and localized flare-ups.", tab: "motion", cat: "creative" },
  cyberpunk: { tags: "Synthwave · High contrast", desc: "High-contrast synthwave waves in electric cyan, neon magenta, and deep ultraviolet with dark gaps.", tab: "motion", cat: "creative" },

  // Music
  pulse: { tags: "Rhythmic · Beat sync", desc: "High-energy transient bursts locked to bass kicks.", tab: "music", cat: "core" },
  spectrum: { tags: "Frequency · Multi-band", desc: "Direct multi-band frequency mapping from bass to treble across zones.", tab: "music", cat: "core" },
  flow: { tags: "Melodic · Liquid", desc: "Silky undulating acoustic ribbons following musical contour.", tab: "music", cat: "core" },
  edm: { tags: "High Energy · Rave", desc: "Explosive strobe flashes and laser sweeps built for bass drops.", tab: "music", cat: "core" },
  chill: { tags: "Warm · Lo-Fi vinyl", desc: "Cozy warm amber bass swells and gentle harmonic relaxation.", tab: "music", cat: "core" },
  bass_bounce: { tags: "Percussive · Low-end", desc: "Heavy kick-drum driven bouncing pulses radiating from impact points.", tab: "music", cat: "core" },
  center_burst: { tags: "Spatial · Radial", desc: "Symmetrical explosive burst expanding outward from center zone.", tab: "music", cat: "core" },
  twinkle: { tags: "High-freq · Sparkle", desc: "Percussive cymbals and high-frequency harmonics shimmering as stardust.", tab: "music", cat: "core" },
  director: { tags: "Intelligent · Auto-adaptive", desc: "Autonomous AI lighting director tracking musical key, BPM, and section changes.", tab: "music", cat: "advanced" },
  acoustic_string: { tags: "Harmonic · Timber", desc: "Warm resonance modeling plucked acoustic strings and guitar.", tab: "music", cat: "advanced" },
  hydro_acoustic: { tags: "Fluid · Underwater bass", desc: "Deep sub-aquatic acoustic pressure waves propagating smoothly.", tab: "music", cat: "advanced" },
  bpm_resonator: { tags: "Tempo · Phase-locked", desc: "Harmonic resonance metronome locked strictly to detected tempo.", tab: "music", cat: "advanced" },
  party: { tags: "Celebration · Dynamic color", desc: "Vibrant fast-paced party celebration color rotation.", tab: "music", cat: "core" },
  movie: { tags: "Cinematic · Subdued ambiance", desc: "Low-glare cinema bias lighting adapting to dynamic sound tracks.", tab: "music", cat: "core" },
  reactive_aurora: { tags: "Atmospheric · Reactive curtain", desc: "Bass gently drives curtain movement, mids shape body & color, transients create sparkling crest highlights.", tab: "music", cat: "core" }
};

function drawCardBanner(canvas, effId) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  switch (effId) {
    case "tide": {
      // Flowing cyan wave threads on dark oceanic teal (User mockup match)
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "#02121d");
      grad.addColorStop(1, "#052636");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      const waves = [
        { color: "rgba(0, 168, 204, 0.4)", yOffset: h * 0.72, amp: 26, freq: 0.015, width: 8 },
        { color: "rgba(0, 229, 255, 0.75)", yOffset: h * 0.56, amp: 34, freq: 0.018, width: 6 },
        { color: "rgba(56, 189, 248, 0.85)", yOffset: h * 0.44, amp: 40, freq: 0.022, width: 4 },
        { color: "rgba(224, 247, 250, 0.95)", yOffset: h * 0.40, amp: 44, freq: 0.024, width: 2 }
      ];
      waves.forEach(wv => {
        ctx.beginPath();
        for (let x = 0; x <= w; x += 4) {
          const y = wv.yOffset + Math.sin(x * wv.freq + 1.2) * wv.amp + Math.cos(x * wv.freq * 0.5) * (wv.amp * 0.35);
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = wv.color;
        ctx.lineWidth = wv.width;
        ctx.shadowColor = "#00e5ff";
        ctx.shadowBlur = 14;
        ctx.stroke();
      });
      ctx.shadowBlur = 0;
      break;
    }
    case "embers": {
      // Dark charred coals with burning orange/gold sparks (User mockup match)
      const grad = ctx.createRadialGradient(w * 0.5, h, 10, w * 0.5, h, w * 0.8);
      grad.addColorStop(0, "#4a0e03");
      grad.addColorStop(0.4, "#1a0402");
      grad.addColorStop(1, "#060101");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      const coalGrad = ctx.createLinearGradient(0, h * 0.65, 0, h);
      coalGrad.addColorStop(0, "rgba(255, 69, 0, 0)");
      coalGrad.addColorStop(0.5, "rgba(255, 110, 0, 0.65)");
      coalGrad.addColorStop(1, "rgba(255, 180, 0, 0.9)");
      ctx.fillStyle = coalGrad;
      ctx.fillRect(0, h * 0.65, w, h * 0.35);

      const randSeed = [
        [0.15, 0.85, 3.5, "#ffcc00"], [0.28, 0.72, 4.0, "#ff9900"], [0.42, 0.88, 5.0, "#ffffff"],
        [0.55, 0.78, 4.2, "#ff5500"], [0.68, 0.82, 3.8, "#ffaa00"], [0.82, 0.75, 4.5, "#ff6600"],
        [0.22, 0.55, 2.8, "#ff8800"], [0.38, 0.48, 3.0, "#ffaa33"], [0.62, 0.52, 3.2, "#ffcc44"],
        [0.75, 0.45, 2.5, "#ff5500"], [0.48, 0.35, 2.2, "#ffaa00"], [0.58, 0.28, 1.8, "#ffdd66"],
        [0.32, 0.22, 1.6, "#ff9900"], [0.70, 0.25, 2.0, "#ff7700"], [0.88, 0.60, 3.0, "#ffbb00"]
      ];
      randSeed.forEach(([rx, ry, r, col]) => {
        ctx.beginPath();
        ctx.arc(rx * w, ry * h, r, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.shadowColor = col;
        ctx.shadowBlur = 10;
        ctx.fill();
      });
      ctx.shadowBlur = 0;
      break;
    }
    case "reactive_aurora":
    case "aurora": {
      // Vertical purple & emerald-cyan ribbons with star dust (User mockup match)
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "#05021a");
      grad.addColorStop(1, "#070b28");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);

      const curtains = [
        { x: 0.18, color1: "rgba(168, 85, 247, 0.75)", color2: "rgba(236, 72, 153, 0.4)", width: 45 },
        { x: 0.38, color1: "rgba(192, 132, 252, 0.85)", color2: "rgba(99, 102, 241, 0.5)", width: 55 },
        { x: 0.60, color1: "rgba(6, 182, 212, 0.75)", color2: "rgba(59, 130, 246, 0.5)", width: 50 },
        { x: 0.82, color1: "rgba(16, 185, 129, 0.7)", color2: "rgba(6, 182, 212, 0.4)", width: 40 }
      ];
      curtains.forEach(c => {
        const cGrad = ctx.createLinearGradient(0, 0, 0, h);
        cGrad.addColorStop(0, "rgba(0,0,0,0)");
        cGrad.addColorStop(0.35, c.color1);
        cGrad.addColorStop(0.85, c.color2);
        cGrad.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = cGrad;
        ctx.shadowColor = c.color1;
        ctx.shadowBlur = 18;
        ctx.fillRect(c.x * w - c.width * 0.5, 0, c.width, h);
      });
      ctx.shadowBlur = 0;

      for (let i = 0; i < 30; i++) {
        const sx = ((i * 37) % 100) / 100 * w;
        const sy = ((i * 59) % 100) / 100 * h;
        const sr = (i % 3 === 0) ? 1.5 : 0.9;
        ctx.beginPath();
        ctx.arc(sx, sy, sr, 0, Math.PI * 2);
        ctx.fillStyle = (i % 2 === 0) ? "rgba(255,255,255,0.9)" : "rgba(192, 132, 252, 0.8)";
        ctx.fill();
      }
      break;
    }
    case "cyber_chase": {
      // High-speed neon cyan & magenta converging streaks (User mockup match)
      ctx.fillStyle = "#030308";
      ctx.fillRect(0, 0, w, h);

      const streaks = [
        { y: 0.22, endY: 0.45, color: "#00f0ff", width: 5 },
        { y: 0.35, endY: 0.48, color: "#38bdf8", width: 4 },
        { y: 0.45, endY: 0.50, color: "#e0f2fe", width: 3 },
        { y: 0.55, endY: 0.51, color: "#ec4899", width: 3.5 },
        { y: 0.65, endY: 0.53, color: "#ff007f", width: 5 },
        { y: 0.78, endY: 0.56, color: "#a855f7", width: 4 }
      ];
      streaks.forEach(s => {
        ctx.beginPath();
        ctx.moveTo(0, s.y * h);
        ctx.bezierCurveTo(w * 0.4, s.y * h, w * 0.7, s.endY * h, w, s.endY * h);
        ctx.strokeStyle = s.color;
        ctx.lineWidth = s.width;
        ctx.shadowColor = s.color;
        ctx.shadowBlur = 14;
        ctx.stroke();
      });
      ctx.shadowBlur = 0;
      break;
    }
    case "breathe": {
      const grad = ctx.createRadialGradient(w * 0.5, h * 0.5, 5, w * 0.5, h * 0.5, w * 0.5);
      grad.addColorStop(0, "rgba(192, 132, 252, 0.9)");
      grad.addColorStop(0.35, "rgba(124, 110, 245, 0.6)");
      grad.addColorStop(0.7, "rgba(59, 130, 246, 0.2)");
      grad.addColorStop(1, "#070712");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      break;
    }
    case "drift": {
      const grad = ctx.createLinearGradient(0, 0, w, h);
      grad.addColorStop(0, "#4338ca");
      grad.addColorStop(0.35, "#7c3aed");
      grad.addColorStop(0.7, "#c026d3");
      grad.addColorStop(1, "#0284c7");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      break;
    }
    case "starfield": {
      ctx.fillStyle = "#03040a";
      ctx.fillRect(0, 0, w, h);
      const neb = ctx.createRadialGradient(w * 0.6, h * 0.4, 10, w * 0.6, h * 0.4, w * 0.5);
      neb.addColorStop(0, "rgba(30, 58, 138, 0.45)");
      neb.addColorStop(1, "transparent");
      ctx.fillStyle = neb;
      ctx.fillRect(0, 0, w, h);

      for (let i = 0; i < 40; i++) {
        const sx = ((i * 47) % 100) / 100 * w;
        const sy = ((i * 73) % 100) / 100 * h;
        const r = (i % 5 === 0) ? 2.0 : 1.0;
        ctx.beginPath();
        ctx.arc(sx, sy, r, 0, Math.PI * 2);
        ctx.fillStyle = "#ffffff";
        if (i % 5 === 0) {
          ctx.shadowColor = "#38bdf8";
          ctx.shadowBlur = 8;
        }
        ctx.fill();
        ctx.shadowBlur = 0;
      }
      break;
    }
    case "fireflies": {
      ctx.fillStyle = "#020f06";
      ctx.fillRect(0, 0, w, h);
      const orbs = [
        [0.2, 0.35, 12, "#a3e635"], [0.35, 0.65, 16, "#84cc16"],
        [0.55, 0.3, 14, "#facc15"], [0.72, 0.6, 18, "#a3e635"],
        [0.85, 0.4, 10, "#4ade80"]
      ];
      orbs.forEach(([ox, oy, or, col]) => {
        const g = ctx.createRadialGradient(ox * w, oy * h, 1, ox * w, oy * h, or * 2);
        g.addColorStop(0, col);
        g.addColorStop(0.4, col);
        g.addColorStop(1, "transparent");
        ctx.fillStyle = g;
        ctx.fillRect(ox * w - or * 2, oy * h - or * 2, or * 4, or * 4);
      });
      break;
    }
    case "lava_lamp": {
      ctx.fillStyle = "#0c0204";
      ctx.fillRect(0, 0, w, h);
      const blobs = [
        [0.3, 0.6, 32, "#f97316"], [0.45, 0.35, 26, "#ef4444"],
        [0.7, 0.55, 38, "#ea580c"], [0.6, 0.25, 20, "#fbbf24"]
      ];
      blobs.forEach(([bx, by, br, col]) => {
        const g = ctx.createRadialGradient(bx * w, by * h, 2, bx * w, by * h, br);
        g.addColorStop(0, "#fef08a");
        g.addColorStop(0.5, col);
        g.addColorStop(1, "transparent");
        ctx.fillStyle = g;
        ctx.fillRect(bx * w - br, by * h - br, br * 2, br * 2);
      });
      break;
    }
    case "golden_hour": {
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "#1e1b4b");
      grad.addColorStop(0.4, "#991b1b");
      grad.addColorStop(0.7, "#ea580c");
      grad.addColorStop(1, "#facc15");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      break;
    }
    case "comet": {
      ctx.fillStyle = "#03020a";
      ctx.fillRect(0, 0, w, h);
      const trail = ctx.createLinearGradient(w * 0.1, h * 0.8, w * 0.8, h * 0.2);
      trail.addColorStop(0, "rgba(168, 85, 247, 0)");
      trail.addColorStop(0.7, "rgba(192, 132, 252, 0.6)");
      trail.addColorStop(1, "#ffffff");
      ctx.beginPath();
      ctx.moveTo(w * 0.1, h * 0.8);
      ctx.lineTo(w * 0.8, h * 0.2);
      ctx.strokeStyle = trail;
      ctx.lineWidth = 6;
      ctx.shadowColor = "#c084fc";
      ctx.shadowBlur = 16;
      ctx.stroke();
      ctx.shadowBlur = 0;
      break;
    }
    case "sinelon": {
      ctx.fillStyle = "#060312";
      ctx.fillRect(0, 0, w, h);
      ctx.beginPath();
      for (let x = 0; x <= w; x += 4) {
        const y = h * 0.5 + Math.sin(x * 0.02) * (h * 0.35);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = "#818cf8";
      ctx.lineWidth = 4;
      ctx.shadowColor = "#6366f1";
      ctx.shadowBlur = 12;
      ctx.stroke();
      ctx.shadowBlur = 0;
      break;
    }
    case "deep_ocean": {
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "#020b14");
      grad.addColorStop(0.6, "#032d42");
      grad.addColorStop(1, "#06b6d4");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      break;
    }
    case "lightning": {
      ctx.fillStyle = "#070814";
      ctx.fillRect(0, 0, w, h);
      ctx.beginPath();
      ctx.moveTo(w * 0.3, 0);
      ctx.lineTo(w * 0.45, h * 0.35);
      ctx.lineTo(w * 0.4, h * 0.45);
      ctx.lineTo(w * 0.65, h * 0.7);
      ctx.lineTo(w * 0.55, h * 0.75);
      ctx.lineTo(w * 0.7, h);
      ctx.strokeStyle = "#93c5fd";
      ctx.lineWidth = 3.5;
      ctx.shadowColor = "#3b82f6";
      ctx.shadowBlur = 20;
      ctx.stroke();
      ctx.shadowBlur = 0;
      break;
    }
    case "rainbow": {
      const grad = ctx.createLinearGradient(0, 0, w, 0);
      grad.addColorStop(0, "#ef4444");
      grad.addColorStop(0.2, "#f59e0b");
      grad.addColorStop(0.4, "#10b981");
      grad.addColorStop(0.6, "#06b6d4");
      grad.addColorStop(0.8, "#6366f1");
      grad.addColorStop(1, "#ec4899");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      break;
    }
    case "pulse": {
      ctx.fillStyle = "#08020a";
      ctx.fillRect(0, 0, w, h);
      [0.2, 0.4, 0.65].forEach(rPct => {
        ctx.beginPath();
        ctx.arc(w * 0.5, h * 0.5, w * rPct, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(244, 63, 94, ${1.0 - rPct})`;
        ctx.lineWidth = 4;
        ctx.shadowColor = "#f43f5e";
        ctx.shadowBlur = 14;
        ctx.stroke();
      });
      ctx.shadowBlur = 0;
      break;
    }
    case "spectrum": {
      ctx.fillStyle = "#05050a";
      ctx.fillRect(0, 0, w, h);
      const bars = [0.35, 0.65, 0.9, 0.8, 0.5, 0.7, 0.95, 0.6, 0.4, 0.25];
      const barW = (w - 20) / bars.length;
      bars.forEach((bH, idx) => {
        const x = 10 + idx * barW;
        const barHeight = bH * (h - 20);
        const y = h - 10 - barHeight;
        const g = ctx.createLinearGradient(0, y, 0, h - 10);
        g.addColorStop(0, "#ef4444");
        g.addColorStop(0.5, "#eab308");
        g.addColorStop(1, "#10b981");
        ctx.fillStyle = g;
        ctx.fillRect(x + 2, y, barW - 4, barHeight);
      });
      break;
    }
    case "flow": {
      ctx.fillStyle = "#020d18";
      ctx.fillRect(0, 0, w, h);
      ctx.beginPath();
      for (let x = 0; x <= w; x += 3) {
        const y = h * 0.5 + Math.sin(x * 0.02) * (h * 0.25) + Math.cos(x * 0.04) * (h * 0.15);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 5;
      ctx.shadowColor = "#0284c7";
      ctx.shadowBlur = 15;
      ctx.stroke();
      ctx.shadowBlur = 0;
      break;
    }
    case "edm": {
      ctx.fillStyle = "#0c010b";
      ctx.fillRect(0, 0, w, h);
      for (let i = 0; i < 8; i++) {
        const angle = (i / 8) * Math.PI;
        ctx.beginPath();
        ctx.moveTo(w * 0.5 - Math.cos(angle) * w, h * 0.5 - Math.sin(angle) * h);
        ctx.lineTo(w * 0.5 + Math.cos(angle) * w, h * 0.5 + Math.sin(angle) * h);
        ctx.strokeStyle = (i % 2 === 0) ? "#f43f5e" : "#00f0ff";
        ctx.lineWidth = 3;
        ctx.shadowColor = ctx.strokeStyle;
        ctx.shadowBlur = 12;
        ctx.stroke();
      }
      ctx.shadowBlur = 0;
      break;
    }
    case "chill": {
      const g = ctx.createRadialGradient(w * 0.5, h * 0.5, 5, w * 0.5, h * 0.5, w * 0.5);
      g.addColorStop(0, "#fbbf24");
      g.addColorStop(0.5, "#d97706");
      g.addColorStop(1, "#1c1917");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
      break;
    }
    case "oil_slick": {
      const grad = ctx.createLinearGradient(0, 0, w, h);
      grad.addColorStop(0, "#030712");
      grad.addColorStop(1, "#0a0a1a");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      const cols = ["#06b6d4", "#4338ca", "#8b5cf6", "#ec4899", "#f59e0b"];
      cols.forEach((col, idx) => {
        ctx.beginPath();
        for (let x = 0; x <= w; x += 4) {
          const y = h * (0.3 + idx * 0.1) + Math.sin(x * 0.02 + idx * 1.3) * 16 + Math.cos(x * 0.035 - idx * 0.8) * 10;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = col;
        ctx.lineWidth = 4;
        ctx.shadowColor = col;
        ctx.shadowBlur = 10;
        ctx.stroke();
      });
      ctx.shadowBlur = 0;
      break;
    }
    case "silk_ribbons": {
      ctx.fillStyle = "#050510";
      ctx.fillRect(0, 0, w, h);
      const ribbons = [
        { col: "rgba(236, 72, 153, 0.75)", y: h * 0.35, freq: 0.018, amp: 22 },
        { col: "rgba(6, 182, 212, 0.75)", y: h * 0.52, freq: 0.022, amp: 26 },
        { col: "rgba(168, 85, 247, 0.75)", y: h * 0.68, freq: 0.016, amp: 20 }
      ];
      ribbons.forEach(rb => {
        ctx.beginPath();
        for (let x = 0; x <= w; x += 3) {
          const y = rb.y + Math.sin(x * rb.freq) * rb.amp;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = rb.col;
        ctx.lineWidth = 6;
        ctx.shadowColor = rb.col;
        ctx.shadowBlur = 12;
        ctx.stroke();
      });
      ctx.shadowBlur = 0;
      break;
    }
    case "nebula_bloom": {
      ctx.fillStyle = "#030208";
      ctx.fillRect(0, 0, w, h);
      const centers = [
        { x: w * 0.28, y: h * 0.45, r: 55, c1: "rgba(139, 92, 246, 0.6)", c2: "rgba(139, 92, 246, 0)" },
        { x: w * 0.68, y: h * 0.55, r: 65, c1: "rgba(217, 70, 239, 0.5)", c2: "rgba(217, 70, 239, 0)" },
        { x: w * 0.48, y: h * 0.32, r: 45, c1: "rgba(59, 130, 246, 0.4)", c2: "rgba(59, 130, 246, 0)" }
      ];
      centers.forEach(ct => {
        const rad = ctx.createRadialGradient(ct.x, ct.y, 2, ct.x, ct.y, ct.r);
        rad.addColorStop(0, ct.c1);
        rad.addColorStop(1, ct.c2);
        ctx.fillStyle = rad;
        ctx.beginPath();
        ctx.arc(ct.x, ct.y, ct.r, 0, Math.PI * 2);
        ctx.fill();
      });
      break;
    }
    case "holographic_moire": {
      ctx.fillStyle = "#02040a";
      ctx.fillRect(0, 0, w, h);
      ctx.lineWidth = 2;
      for (let i = 0; i < 16; i++) {
        const x = (i / 15) * w;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(w - x, h);
        ctx.strokeStyle = (i % 2 === 0) ? "rgba(56, 189, 248, 0.6)" : "rgba(129, 140, 248, 0.6)";
        ctx.stroke();
      }
      break;
    }
    case "bioluminescent_tide": {
      const sea = ctx.createLinearGradient(0, 0, 0, h);
      sea.addColorStop(0, "#010d18");
      sea.addColorStop(1, "#031e30");
      ctx.fillStyle = sea;
      ctx.fillRect(0, 0, w, h);
      const layers = [
        { y: h * 0.42, amp: 18, freq: 0.02, col: "rgba(14, 165, 233, 0.4)", lw: 6 },
        { y: h * 0.58, amp: 24, freq: 0.025, col: "rgba(6, 182, 212, 0.65)", lw: 5 },
        { y: h * 0.72, amp: 30, freq: 0.03, col: "rgba(34, 211, 238, 0.9)", lw: 3 }
      ];
      layers.forEach(l => {
        ctx.beginPath();
        for (let x = 0; x <= w; x += 3) {
          const y = l.y + Math.sin(x * l.freq + 1.0) * l.amp;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = l.col;
        ctx.lineWidth = l.lw;
        ctx.shadowColor = "#22d3ee";
        ctx.shadowBlur = 12;
        ctx.stroke();
      });
      ctx.shadowBlur = 0;
      break;
    }
    case "ember_drift": {
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, "#0a0302");
      grad.addColorStop(1, "#260803");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
      const coals = [
        [0.2, 0.75, 5, "#ff7700"], [0.35, 0.6, 4, "#ffaa00"], [0.5, 0.8, 6, "#ff4400"],
        [0.65, 0.55, 4, "#ff8800"], [0.8, 0.7, 5, "#ffbb00"], [0.45, 0.4, 3, "#ff5500"]
      ];
      coals.forEach(([rx, ry, r, col]) => {
        ctx.beginPath();
        ctx.arc(rx * w, ry * h, r, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.shadowColor = col;
        ctx.shadowBlur = 10;
        ctx.fill();
      });
      ctx.shadowBlur = 0;
      break;
    }
    default: {
      const c = EFFECT_COLORS[effId] || "#7c6ef5";
      const g = ctx.createLinearGradient(0, 0, w, h);
      g.addColorStop(0, "#080812");
      g.addColorStop(0.5, c);
      g.addColorStop(1, "#050508");
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
      break;
    }
  }
}

const MODE_COLORS = {
  work: "#fff9e6",
  deep_focus: "#ffffff",
  coding_night: "#ffe0b2",
  reading: "#ffd580",
  movie: "#38bdf8",
  sunset: "#f59e0b",
  dinner: "#ffb347",
  sleep: "#ff5c5c",
  cyberpunk: "#ec4899",
  synthwave: "#a855f7",
  gaming: "#3b82f6",
  ocean: "#06b6d4",
  forest: "#10b981",
  meditation: "#8b5cf6"
};

const EFFECT_COLORS = {
  oil_slick: "#06b6d4",
  silk_ribbons: "#ec4899",
  nebula_bloom: "#8b5cf6",
  holographic_moire: "#3b82f6",
  bioluminescent_tide: "#0ea5e9",
  ember_drift: "#f97316",
  cyberpunk: "#d946ef",
  ambient_drift: "#a855f7",
  northern_lights: "#10b981",
  fireplace: "#f97316",
  sakura: "#ec4899",
  golden_hour: "#f59e0b",
  candle_flicker: "#f97316",
  deep_ocean: "#06b6d4",
  pulse: "#f43f5e",
  rainbow: "#ff3b30",
  aurora: "#10b981",
  ocean: "#06b6d4",
  lightning: "#5856d6",
  fire_crawl: "#f97316",
  police: "#007aff",
  comet: "#af52de",
  pixel_bounce: "#ffffff",
  breathing_wave: "#7c6ef5",
  meteor: "#4da8ff",
  neon_chase: "#ec4899",
  color_wipe: "#ffd700",
  rainbow_chase: "#ff3b30",
  cyber_chase: "#f43f5e",
  aurora_wave: "#10b981",
  spectrum_idle: "#9d92ff",
  matrix_rain: "#22c55e",
  strobe_party: "#ffff00",
  lava_lamp: "#f97316",
  fireflies: "#a3e635",
  prism_sparks: "#e879f9",
  meteor_shower: "#38bdf8",
  glitch_wave: "#00ffff",
  neon_heartbeat: "#f43f5e",
  twinkle_stars: "#70a1ff",
  hyperdrive: "#5352ed",
  sunset_glow: "#ec4899",
  plasma_flow: "#a855f7",
  vaporwave_neon: "#f472b6",
  portal_pulse: "#10b981",
  sonar_sweep: "#06b6d4",
  electric_arc: "#38bdf8",
  quantum_dots: "#f59e0b"
};

function formatName(str) {
  if (!str) return "Idle";
  return str.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

// ── Theme Mapping Logic ───────────────────────────────────────────────────────
function getThemeForLabel(rawLabel) {
  if (!rawLabel) return "ambient_drift";
  const label = rawLabel.toLowerCase().replace(/[\s-_]+/g, "_");

  if (label.includes("aurora") || label.includes("northern") || label.includes("green") || label.includes("emerald")) {
    return "northern_lights";
  }
  if (label.includes("cinematic") || label.includes("movie")) {
    return "movie";
  }
  if (label.includes("wave") || label.includes("deep_ocean") || label.includes("ocean") || label.includes("sea") || label.includes("water") || label.includes("sonar") || label.includes("cyan")) {
    return "deep_ocean";
  }
  if (label.includes("ambient") || label.includes("drift")) {
    return "ambient_drift";
  }
  if (label.includes("fire") || label.includes("ember") || label.includes("candle") || label.includes("lava") || label.includes("flame") || label.includes("particles")) {
    return "fireplace";
  }
  if (label.includes("sakura") || label.includes("blossom") || label.includes("pink") || label.includes("cherry") || label.includes("rose")) {
    return "sakura";
  }
  if (label.includes("golden") || label.includes("sunset") || label.includes("sun") || label.includes("amber") || label.includes("reading") || label.includes("dinner") || label.includes("chill") || label.includes("lofi")) {
    return "golden_hour";
  }
  if (label.includes("pulse") || label.includes("cyber") || label.includes("synth") || label.includes("vapor") || label.includes("edm") || label.includes("neon") || label.includes("party")) {
    return "cyberpunk";
  }
  if (label.includes("matrix")) {
    return "matrix";
  }
  if (label.includes("classical") || label.includes("orchestral") || label.includes("acoustic")) {
    return "classical";
  }
  if (label.includes("hybrid") || label.includes("spectrum")) {
    return "northern_lights";
  }

  const validThemes = ["ambient_drift", "northern_lights", "fireplace", "sakura", "golden_hour", "deep_ocean", "cyberpunk", "matrix", "movie", "classical"];
  if (validThemes.includes(label)) return label;

  return "ambient_drift";
}

// ── DYNAMIC BACKGROUND CANVAS ENGINE (Client-side Glassmorphism) ──────────────
class DynamicBackground {
  constructor() {
    this.canvas = document.getElementById("bgFxCanvas");
    this.ctx = this.canvas ? this.canvas.getContext("2d") : null;
    this.theme = "ambient_drift";
    this.particles = [];
    this.stars = [];
    this.bokeh = [];
    this.width = window.innerWidth;
    this.height = window.innerHeight;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.animId = null;
    this.isRunning = false;
    this.time = 0;

    if (!this.canvas) return;

    this.resize = this.resize.bind(this);
    this.loop = this.loop.bind(this);

    window.addEventListener("resize", this.resize);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        this.stop();
      } else {
        this.start();
      }
    });

    this.resize();
    this.initParticles();
    this.start();
  }

  resize() {
    if (!this.canvas) return;
    this.width = window.innerWidth;
    this.height = window.innerHeight;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);

    this.canvas.width = this.width * this.dpr;
    this.canvas.height = this.height * this.dpr;
    if (this.ctx) {
      this.ctx.setTransform(1, 0, 0, 1, 0, 0);
      this.ctx.scale(this.dpr, this.dpr);
    }
  }

  setTheme(newTheme) {
    if (!newTheme || newTheme === this.theme) return;
    this.theme = newTheme;
    this.initParticles();
  }

  initParticles() {
    this.particles = [];
    this.stars = [];
    this.bokeh = [];

    const w = this.width;
    const h = this.height;

    if (this.theme === "ambient_drift") {
      // Cosmic violet wave nodes
      const count = 32;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.45,
          vy: (Math.random() - 0.5) * 0.45,
          r: 1.5 + Math.random() * 2.5,
          alpha: 0.3 + Math.random() * 0.5,
          pulse: Math.random() * Math.PI * 2
        });
      }
    } else if (this.theme === "northern_lights") {
      // Twinkling stars in arctic sky
      const starCount = 30;
      for (let i = 0; i < starCount; i++) {
        this.stars.push({
          x: Math.random() * w,
          y: Math.random() * h * 0.85,
          r: 0.8 + Math.random() * 1.6,
          alpha: 0.2 + Math.random() * 0.8,
          speed: 0.02 + Math.random() * 0.04,
          phase: Math.random() * Math.PI * 2
        });
      }
    } else if (this.theme === "fireplace") {
      // Rising embers
      const count = 36;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * w,
          y: h + Math.random() * 80,
          vx: (Math.random() - 0.5) * 0.8,
          vy: -(1.4 + Math.random() * 2.2),
          r: 1.5 + Math.random() * 2.8,
          alpha: 0.6 + Math.random() * 0.4,
          hue: 20 + Math.random() * 30, // 20 (orange) to 50 (gold)
          decay: 0.003 + Math.random() * 0.005,
          seed: Math.random() * 100
        });
      }
    } else if (this.theme === "sakura") {
      // Bokeh background circles
      for (let i = 0; i < 9; i++) {
        this.bokeh.push({
          x: Math.random() * w,
          y: Math.random() * h,
          r: 40 + Math.random() * 70,
          alpha: 0.04 + Math.random() * 0.06,
          vx: (Math.random() - 0.5) * 0.15,
          vy: (Math.random() - 0.5) * 0.15
        });
      }
      // Falling cherry blossom petals
      const count = 28;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          size: 7 + Math.random() * 8,
          vy: 0.9 + Math.random() * 1.3,
          vx: 0.3 + Math.random() * 0.7,
          angle: Math.random() * Math.PI * 2,
          spin: (Math.random() - 0.5) * 0.025,
          phase: Math.random() * Math.PI * 2,
          alpha: 0.65 + Math.random() * 0.3
        });
      }
    } else if (this.theme === "golden_hour") {
      // Warm floating golden dust motes
      const count = 32;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.35,
          vy: -(0.4 + Math.random() * 0.7),
          r: 1.5 + Math.random() * 3.0,
          alpha: 0.3 + Math.random() * 0.5,
          pulse: Math.random() * Math.PI * 2
        });
      }
    } else if (this.theme === "deep_ocean") {
      // Bioluminescent rising oceanic bubbles
      const count = 35;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          r: 3 + Math.random() * 8,
          vy: -(0.7 + Math.random() * 1.4),
          wobbleSpeed: 0.02 + Math.random() * 0.03,
          seed: Math.random() * 100,
          alpha: 0.35 + Math.random() * 0.45
        });
      }
    } else if (this.theme === "cyberpunk") {
      // Neon speed motes
      const count = 30;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() > 0.5 ? 1 : -1) * (0.8 + Math.random() * 1.5),
          vy: (Math.random() - 0.5) * 0.4,
          r: 1.8 + Math.random() * 2.2,
          alpha: 0.5 + Math.random() * 0.4,
          isPink: Math.random() > 0.5
        });
      }
    } else if (this.theme === "matrix") {
      // Falling digital code trails
      const count = 25;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.floor(Math.random() * (w / 18)) * 18,
          y: Math.random() * h,
          vy: 2.5 + Math.random() * 3.5,
          length: 6 + Math.floor(Math.random() * 8),
          alpha: 0.4 + Math.random() * 0.5
        });
      }
    } else {
      // Default sleek motes
      const count = 25;
      for (let i = 0; i < count; i++) {
        this.particles.push({
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.3,
          vy: (Math.random() - 0.5) * 0.3,
          r: 1.5 + Math.random() * 2.0,
          alpha: 0.3 + Math.random() * 0.4
        });
      }
    }
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    this.loop();
  }

  stop() {
    this.isRunning = false;
    if (this.animId) {
      cancelAnimationFrame(this.animId);
      this.animId = null;
    }
  }

  loop() {
    if (!this.isRunning) return;
    this.time += 0.016;
    this.render();
    this.animId = requestAnimationFrame(this.loop);
  }

  render() {
    const ctx = this.ctx;
    if (!ctx) return;
    const w = this.width;
    const h = this.height;
    const t = this.time;

    ctx.clearRect(0, 0, w, h);

    switch (this.theme) {
      case "ambient_drift":
        this.renderAmbientDrift(ctx, w, h, t);
        break;
      case "northern_lights":
        this.renderNorthernLights(ctx, w, h, t);
        break;
      case "fireplace":
        this.renderFireplace(ctx, w, h, t);
        break;
      case "sakura":
        this.renderSakura(ctx, w, h, t);
        break;
      case "golden_hour":
        this.renderGoldenHour(ctx, w, h, t);
        break;
      case "deep_ocean":
        this.renderDeepOcean(ctx, w, h, t);
        break;
      case "cyberpunk":
        this.renderCyberpunk(ctx, w, h, t);
        break;
      case "matrix":
        this.renderMatrix(ctx, w, h, t);
        break;
      default:
        this.renderDefault(ctx, w, h, t);
        break;
    }
  }

  // 1. Ambient Drift (Cosmic Violet Wave)
  renderAmbientDrift(ctx, w, h, t) {
    // Floating cosmic wave curves
    ctx.lineWidth = 1.5;
    for (let k = 0; k < 2; k++) {
      ctx.beginPath();
      const waveGrad = ctx.createLinearGradient(0, 0, w, 0);
      waveGrad.addColorStop(0, "rgba(168, 85, 247, 0)");
      waveGrad.addColorStop(0.5, "rgba(192, 132, 252, 0.28)");
      waveGrad.addColorStop(1, "rgba(99, 102, 241, 0)");
      ctx.strokeStyle = waveGrad;

      const yBase = h * (0.35 + k * 0.3);
      for (let x = 0; x <= w; x += 20) {
        const y = yBase + Math.sin(t * 0.8 + x * 0.004 + k) * 35 + Math.cos(t * 0.4 + x * 0.008) * 18;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }

    // Connect close particles with faint constellation lines
    const pts = this.particles;
    for (let i = 0; i < pts.length; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const dx = pts[i].x - pts[j].x;
        const dy = pts[i].y - pts[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 85) {
          ctx.beginPath();
          ctx.strokeStyle = `rgba(168, 85, 247, ${0.18 * (1 - dist / 85)})`;
          ctx.lineWidth = 0.8;
          ctx.moveTo(pts[i].x, pts[i].y);
          ctx.lineTo(pts[j].x, pts[j].y);
          ctx.stroke();
        }
      }
    }

    // Draw cosmic particles
    pts.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h;
      if (p.y > h) p.y = 0;

      const currentAlpha = p.alpha * (0.8 + 0.2 * Math.sin(t * 2 + p.pulse));
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(192, 132, 252, ${currentAlpha})`;
      ctx.shadowColor = "#a855f7";
      ctx.shadowBlur = 8;
      ctx.fill();
    });
    ctx.shadowBlur = 0;
  }

  // 2. Northern Lights (Aurora Borealis Emerald / Cyan Curtains)
  renderNorthernLights(ctx, w, h, t) {
    // Twinkling stars
    this.stars.forEach(s => {
      const alpha = s.alpha * (0.5 + 0.5 * Math.sin(t * 3 * s.speed * 10 + s.phase));
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
      ctx.fill();
    });

    // 3 Undulating vertical aurora ribbon curtains
    for (let c = 0; c < 3; c++) {
      ctx.beginPath();
      const xBase = w * (0.2 + c * 0.3);
      const grad = ctx.createLinearGradient(0, 0, 0, h);
      if (c === 0) {
        grad.addColorStop(0, "rgba(16, 185, 129, 0.38)");
        grad.addColorStop(0.6, "rgba(6, 182, 212, 0.22)");
        grad.addColorStop(1, "rgba(16, 185, 129, 0)");
      } else if (c === 1) {
        grad.addColorStop(0, "rgba(6, 182, 212, 0.32)");
        grad.addColorStop(0.5, "rgba(16, 185, 129, 0.26)");
        grad.addColorStop(1, "rgba(6, 182, 212, 0)");
      } else {
        grad.addColorStop(0, "rgba(52, 211, 153, 0.28)");
        grad.addColorStop(0.55, "rgba(6, 182, 212, 0.18)");
        grad.addColorStop(1, "rgba(52, 211, 153, 0)");
      }

      ctx.fillStyle = grad;
      ctx.moveTo(xBase - 80, 0);

      // Left edge of curtain
      for (let y = 0; y <= h; y += 30) {
        const xOffset = Math.sin(t * 0.7 + y * 0.003 + c) * 60 + Math.cos(t * 0.4 + y * 0.006) * 35;
        ctx.lineTo(xBase + xOffset - 60, y);
      }
      // Right edge of curtain
      for (let y = h; y >= 0; y -= 30) {
        const xOffset = Math.sin(t * 0.7 + y * 0.003 + c) * 60 + Math.cos(t * 0.4 + y * 0.006) * 35;
        ctx.lineTo(xBase + xOffset + 60, y);
      }
      ctx.closePath();
      ctx.fill();
    }
  }

  // 3. Fireplace (Charcoal & Rising Ember Sparks)
  renderFireplace(ctx, w, h, t) {
    // Warm hearth ambient glow at base
    const hearthGrad = ctx.createRadialGradient(w * 0.5, h, 20, w * 0.5, h, h * 0.65);
    hearthGrad.addColorStop(0, "rgba(249, 115, 22, 0.32)");
    hearthGrad.addColorStop(0.5, "rgba(220, 38, 38, 0.16)");
    hearthGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = hearthGrad;
    ctx.fillRect(0, 0, w, h);

    // Rising ember sparks
    this.particles.forEach(p => {
      p.y += p.vy;
      p.x += Math.sin(t * 2 + p.seed) * 0.9;
      p.alpha -= p.decay;

      if (p.y < -20 || p.alpha <= 0) {
        p.y = h + Math.random() * 40;
        p.x = Math.random() * w;
        p.alpha = 0.7 + Math.random() * 0.3;
        p.vy = -(1.4 + Math.random() * 2.2);
      }

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `hsla(${p.hue}, 95%, 65%, ${p.alpha})`;
      ctx.shadowColor = "#f97316";
      ctx.shadowBlur = 10;
      ctx.fill();
    });
    ctx.shadowBlur = 0;
  }

  // 4. Sakura (Cherry Blossom Falling Petals & Bokeh)
  renderSakura(ctx, w, h, t) {
    // Soft bokeh discs
    this.bokeh.forEach(b => {
      b.x += b.vx;
      b.y += b.vy;
      if (b.x < -100) b.x = w + 100;
      if (b.x > w + 100) b.x = -100;
      if (b.y < -100) b.y = h + 100;
      if (b.y > h + 100) b.y = -100;

      const grad = ctx.createRadialGradient(b.x, b.y, 0, b.x, b.y, b.r);
      grad.addColorStop(0, `rgba(244, 114, 182, ${b.alpha})`);
      grad.addColorStop(1, "rgba(244, 114, 182, 0)");
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2);
      ctx.fill();
    });

    // Falling petals with angular rotation
    this.particles.forEach(p => {
      p.y += p.vy;
      p.x += Math.sin(t * 1.2 + p.phase) * 1.1 + p.vx;
      p.angle += p.spin;

      if (p.y > h + 20) {
        p.y = -20;
        p.x = Math.random() * w;
      }
      if (p.x > w + 20) p.x = -20;
      if (p.x < -20) p.x = w + 20;

      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.angle);
      ctx.scale(Math.sin(p.angle * 1.5) * 0.4 + 0.8, 1);

      ctx.beginPath();
      const s = p.size;
      ctx.moveTo(0, -s);
      ctx.bezierCurveTo(s * 0.75, -s * 0.5, s * 0.75, s * 0.5, 0, s);
      ctx.bezierCurveTo(-s * 0.75, s * 0.5, -s * 0.75, -s * 0.5, 0, -s);

      ctx.fillStyle = `rgba(244, 114, 182, ${p.alpha})`;
      ctx.shadowColor = "#ec4899";
      ctx.shadowBlur = 6;
      ctx.fill();
      ctx.restore();
    });
    ctx.shadowBlur = 0;
  }

  // 5. Golden Hour (Sunset Twilight & Radiating Golden Dust)
  renderGoldenHour(ctx, w, h, t) {
    // Low sun horizon glow
    const sunGrad = ctx.createRadialGradient(w * 0.35, h * 0.9, 30, w * 0.35, h * 0.9, h * 0.75);
    sunGrad.addColorStop(0, "rgba(245, 158, 11, 0.42)");
    sunGrad.addColorStop(0.45, "rgba(234, 88, 12, 0.22)");
    sunGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = sunGrad;
    ctx.fillRect(0, 0, w, h);

    // Floating golden dust motes
    this.particles.forEach(p => {
      p.x += p.vx + Math.sin(t * 0.8 + p.pulse) * 0.35;
      p.y += p.vy;

      if (p.y < -20) {
        p.y = h + 20;
        p.x = Math.random() * w;
      }
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;

      const alpha = p.alpha * (0.7 + 0.3 * Math.sin(t * 2 + p.pulse));
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(251, 191, 36, ${alpha})`;
      ctx.shadowColor = "#f59e0b";
      ctx.shadowBlur = 8;
      ctx.fill();
    });
    ctx.shadowBlur = 0;
  }

  // 6. Deep Ocean (Bioluminescent Abyss & Rising Bubbles)
  renderDeepOcean(ctx, w, h, t) {
    // Rising bubbles with realistic specular reflection dot
    this.particles.forEach(p => {
      p.y += p.vy;
      p.x += Math.sin(p.y * 0.02 + p.seed) * 0.75;

      if (p.y < -30) {
        p.y = h + 20;
        p.x = Math.random() * w;
      }

      // Bubble glow & ring
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(6, 182, 212, ${p.alpha * 0.15})`;
      ctx.strokeStyle = `rgba(6, 182, 212, ${p.alpha * 0.65})`;
      ctx.lineWidth = 1.2;
      ctx.shadowColor = "#06b6d4";
      ctx.shadowBlur = 6;
      ctx.fill();
      ctx.stroke();

      // Specular highlight reflection
      ctx.beginPath();
      ctx.arc(p.x - p.r * 0.35, p.y - p.r * 0.35, Math.max(1, p.r * 0.25), 0, Math.PI * 2);
      ctx.fillStyle = `rgba(255, 255, 255, ${p.alpha * 0.8})`;
      ctx.fill();
    });
    ctx.shadowBlur = 0;
  }

  // Cyberpunk Mode
  renderCyberpunk(ctx, w, h, t) {
    this.particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h;
      if (p.y > h) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = p.isPink ? `rgba(244, 63, 94, ${p.alpha})` : `rgba(6, 182, 212, ${p.alpha})`;
      ctx.shadowColor = p.isPink ? "#f43f5e" : "#06b6d4";
      ctx.shadowBlur = 10;
      ctx.fill();
    });
    ctx.shadowBlur = 0;
  }

  // Matrix Rain Mode
  renderMatrix(ctx, w, h, t) {
    ctx.fillStyle = "#22c55e";
    ctx.font = "12px monospace";
    this.particles.forEach(p => {
      p.y += p.vy;
      if (p.y > h + 100) p.y = -40;

      for (let k = 0; k < p.length; k++) {
        const yPos = p.y - k * 14;
        if (yPos > 0 && yPos < h) {
          const charAlpha = (1 - k / p.length) * p.alpha;
          ctx.fillStyle = k === 0 ? "#ffffff" : `rgba(34, 197, 94, ${charAlpha})`;
          ctx.fillText(String.fromCharCode(0x30A0 + ((p.x + k) % 96)), p.x, yPos);
        }
      }
    });
  }

  // Default Sleek Mode
  renderDefault(ctx, w, h, t) {
    this.particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0) p.x = w;
      if (p.x > w) p.x = 0;
      if (p.y < 0) p.y = h;
      if (p.y > h) p.y = 0;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(124, 110, 245, ${p.alpha})`;
      ctx.fill();
    });
  }
}

// Instantiate Global Background Engine
const bgEngine = new DynamicBackground();
window.bgEngine = bgEngine;

// ── Auth Token Handling ───────────────────────────────────────────────────────
let authToken = localStorage.getItem("tapo_auth_token") || (new URLSearchParams(window.location.search)).get("token") || "";

function getAuthHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
    headers["X-Auth-Token"] = authToken;
  }
  return headers;
}

function showAuthModal() {
  const modal = document.getElementById("authModal");
  if (modal) modal.style.display = "flex";
}

function hideAuthModal() {
  const modal = document.getElementById("authModal");
  if (modal) modal.style.display = "none";
}

document.getElementById("btnSubmitAuth")?.addEventListener("click", () => {
  const inp = document.getElementById("authTokenInput");
  if (inp && inp.value.trim()) {
    authToken = inp.value.trim();
    localStorage.setItem("tapo_auth_token", authToken);
    hideAuthModal();
    if (ws) ws.close();
    connectWebSocket();
    loadAudioDevices();
  }
});

// ── WebSocket Connection & State Sync ─────────────────────────────────────────
function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const tokParam = authToken ? `?token=${encodeURIComponent(authToken)}` : "";
  const wsUrl = `${protocol}//${location.host}/ws${tokParam}`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById("connStatus")?.classList.add("online");
    const connText = document.getElementById("connText");
    if (connText) connText.textContent = "Live Connected";
    clearTimeout(reconnectTimer);
    hideAuthModal();
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "telemetry") {
        if (data.diagnostics) updateTelemetry(data.diagnostics);
        if (data.audio) updateAudioVisualizer(data.audio);
        if (data.zone_preview) drawZonePreview(data.zone_preview);
        return;
      }
      state = data;
      renderUI();
      if (state.diagnostics) {
        updateTelemetry(state.diagnostics);
      }
      if (state.zone_preview) {
        drawZonePreview(state.zone_preview);
      }
    } catch (e) {
      console.error("WS Parse error", e);
    }
  };

  ws.onclose = (ev) => {
    document.getElementById("connStatus")?.classList.remove("online");
    const connText = document.getElementById("connText");
    if (ev.code === 4401) {
      if (connText) connText.textContent = "Auth Required";
      showAuthModal();
    } else {
      if (connText) connText.textContent = "Reconnecting...";
      reconnectTimer = setTimeout(connectWebSocket, 2000);
    }
  };

  ws.onerror = () => {
    ws.close();
  };
}

// ── Diagnostics Telemetry Display ─────────────────────────────────────────────
function updateTelemetry(diagnostics) {
  if (!diagnostics) return;
  let diag = null;
  if (currentDevId === "all") {
    const keys = Object.keys(diagnostics);
    const l930Key = keys.find(k => state.devices && state.devices[k]?.model === "L930");
    diag = diagnostics[l930Key || keys[0]];
  } else {
    diag = diagnostics[currentDevId];
  }
  if (!diag) return;

  const elSend = document.getElementById("diagSendFps");
  const elRender = document.getElementById("diagRenderFps");
  const elRtt = document.getElementById("diagRtt");
  const elPacing = document.getElementById("diagPacing");
  const elDrops = document.getElementById("diagDrops");
  const elStatus = document.getElementById("diagStatus");
  const elErrors = document.getElementById("diagErrors");

  if (elSend) elSend.textContent = `${diag.send_fps} FPS`;
  if (elRender) elRender.textContent = `Render: ${diag.render_fps} FPS`;
  if (elRtt) elRtt.textContent = `${diag.rtt_ms} ms`;
  if (elPacing) elPacing.textContent = `Pacing: ${diag.pacing_delay_ms} ms`;
  if (elDrops) elDrops.textContent = `${diag.drop_rate_pct}%`;
  if (elStatus) {
    elStatus.textContent = diag.status;
    elStatus.style.color = diag.status === "connected" ? "#3dd68c" : (diag.status === "reconnecting" ? "#f5a623" : "#f55151");
  }
  if (elErrors) elErrors.textContent = `${diag.error_count} err · ${diag.reconnect_count} re-auth`;

  // Prominent Live Status Bar (Applied effect, send rate, errors)
  const topSend = document.getElementById("topSendRate");
  const topErr = document.getElementById("topErrorText");
  const topDot = document.getElementById("topErrorDot");
  const expStatus = document.getElementById("experienceStatusPill");
  const activeDev = state.devices?.[currentDevId] || {};

  if (topSend) topSend.textContent = `${diag.send_fps} FPS`;
  if (topErr) topErr.textContent = `${diag.error_count} errors`;
  if (topDot) topDot.style.background = diag.error_count > 0 ? "#ef4444" : "#3dd68c";
  if (expStatus) {
    const effName = formatName(activeDev.active_label || "Idle");
    const audioUnavailable = activeDev.active_label === "Audio Error";
    const statusSuffix = audioUnavailable ? " · audio unavailable" : "";
    expStatus.textContent = `${effName}${statusSuffix} · ${diag.send_fps} FPS · ${diag.error_count} err`;
    if (audioUnavailable && activeDev.last_error) {
      expStatus.title = activeDev.last_error;
    } else {
      expStatus.removeAttribute("title");
    }
  }

  const connText = document.getElementById("connText");
  if (connText && ws && ws.readyState === WebSocket.OPEN) {
    connText.textContent = `Live · ${diag.send_fps} FPS · ${diag.rtt_ms}ms`;
  }
}

// ── Audio DSP Live Spectrum & Music Understanding Visualizer ─────────────────
function updateAudioVisualizer(audioData) {
  if (!audioData) return;
  let info = null;
  if (currentDevId === "all") {
    const keys = Object.keys(audioData);
    const l930Key = keys.find(k => state.devices && state.devices[k]?.model === "L930");
    info = audioData[l930Key || keys[0]];
  } else {
    info = audioData[currentDevId];
  }
  if (!info) return;

  // 1. BPM Pill
  const bpmPill = document.getElementById("audioBpmPill");
  if (bpmPill) {
    if (info.active) {
      bpmPill.textContent = `⚡ ${Math.round(info.bpm || 120)} BPM`;
      bpmPill.style.color = "#3dd68c";
      bpmPill.style.background = "rgba(61, 214, 140, 0.15)";
    } else {
      bpmPill.textContent = "💤 Inactive";
      bpmPill.style.color = "#888899";
      bpmPill.style.background = "rgba(255, 255, 255, 0.05)";
    }
  }

  // 2. Section Badge with Neon Status Colors
  const secBadge = document.getElementById("musicSectionBadge");
  if (secBadge && info.section) {
    const sec = info.section.toUpperCase();
    secBadge.textContent = sec;
    if (sec === "DROP") {
      secBadge.style.color = "#ffffff";
      secBadge.style.background = "rgba(244, 63, 94, 0.55)";
      secBadge.style.borderColor = "#f43f5e";
      secBadge.style.boxShadow = "0 0 12px rgba(244, 63, 94, 0.8)";
    } else if (sec === "BUILD") {
      secBadge.style.color = "#fbbf24";
      secBadge.style.background = "rgba(245, 158, 11, 0.25)";
      secBadge.style.borderColor = "#f59e0b";
      secBadge.style.boxShadow = "0 0 8px rgba(245, 158, 11, 0.4)";
    } else if (sec === "BREAKDOWN") {
      secBadge.style.color = "#06b6d4";
      secBadge.style.background = "rgba(6, 182, 212, 0.2)";
      secBadge.style.borderColor = "#06b6d4";
      secBadge.style.boxShadow = "none";
    } else if (sec === "VERSE") {
      secBadge.style.color = "#3dd68c";
      secBadge.style.background = "rgba(61, 214, 140, 0.15)";
      secBadge.style.borderColor = "rgba(61, 214, 140, 0.35)";
      secBadge.style.boxShadow = "none";
    } else {
      secBadge.style.color = "#888899";
      secBadge.style.background = "rgba(255, 255, 255, 0.05)";
      secBadge.style.borderColor = "#444455";
      secBadge.style.boxShadow = "none";
    }
  }

  // 3. Musical Key & Mode Pill
  const keyPill = document.getElementById("musicKeyPill");
  if (keyPill && info.key_hue !== undefined) {
    const keyDeg = Math.round(info.key_hue);
    const modeStr = (info.mode || "maj").toUpperCase();
    keyPill.textContent = `🎼 ${keyDeg}° ${modeStr}`;
  }

  // 4. 4-Beat Bar Indicator Dots
  const dotsContainer = document.getElementById("musicBeatDots");
  if (dotsContainer && info.bar_pos !== undefined) {
    const curPos = info.bar_pos % 4;
    let dotsHtml = "";
    for (let b = 0; b < 4; b++) {
      if (b === curPos) {
        dotsHtml += `<span style="color: var(--theme-accent); font-weight: 800; text-shadow: 0 0 6px var(--theme-accent-glow);">●</span>`;
      } else {
        dotsHtml += `<span style="color: rgba(255,255,255,0.25);">○</span>`;
      }
    }
    dotsContainer.innerHTML = dotsHtml;
  }

  // 5. Live Song Palette Chips
  const paletteContainer = document.getElementById("musicPaletteChips");
  if (paletteContainer && info.palette && info.palette.length) {
    let chipsHtml = "";
    info.palette.slice(0, 4).forEach(c => {
      const [h, s, v] = c;
      chipsHtml += `<span style="width: 12px; height: 12px; border-radius: 50%; background: hsl(${h}, ${s}%, ${Math.max(25, v)}%); border: 1px solid rgba(255,255,255,0.25); display: inline-block;"></span>`;
    });
    paletteContainer.innerHTML = chipsHtml;
  }

  // 6. Active Visual Style Button Synchronization
  if (info.style) {
    document.querySelectorAll("#vstyleButtons button").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.vstyle === info.style);
    });
  }

  // 7. Sensitivity & AGC Slider
  const sensVal = document.getElementById("audioSensVal");
  const sensSlider = document.getElementById("audioSensSlider");
  if (sensVal && sensSlider && document.activeElement !== sensSlider && info.sensitivity !== undefined) {
    sensVal.textContent = `${info.sensitivity.toFixed(1)}x`;
    sensSlider.value = info.sensitivity;
  }

  // 8. Latency Lookahead Slider Sync
  const lookaheadVal = document.getElementById("audioLookaheadVal");
  const lookaheadSlider = document.getElementById("audioLookaheadSlider");
  if (lookaheadVal && lookaheadSlider && document.activeElement !== lookaheadSlider && info.lookahead_ms !== undefined) {
    lookaheadVal.textContent = `${Math.round(info.lookahead_ms)}ms`;
    lookaheadSlider.value = Math.round(info.lookahead_ms);
  }

  if (info.spectrum) {
    drawAudioSpectrum(info.spectrum);
  }
}

function drawAudioSpectrum(spectrum) {
  const canvas = document.getElementById("audioSpectrumCanvas");
  if (!canvas || !spectrum || !spectrum.length) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const numBars = spectrum.length;
  const barWidth = Math.max(1, (w / numBars) - 1);

  for (let i = 0; i < numBars; i++) {
    const val = Math.max(0, Math.min(1.0, spectrum[i]));
    const barHeight = Math.max(2, val * (h - 4));
    const x = i * (barWidth + 1);
    const y = h - barHeight;

    const hue = (i / numBars) * 280;
    ctx.fillStyle = `hsl(${hue}, 85%, 60%)`;
    ctx.fillRect(x, y, barWidth, barHeight);
  }
}

function drawZonePreview(segments) {
  const canvas = document.getElementById("zonePreviewCanvas");
  const trayCanvas = document.getElementById("trayPreviewCanvas");
  if (!segments || !segments.length) return;

  [canvas, trayCanvas].forEach(c => {
    if (!c) return;
    const ctx = c.getContext("2d");
    const w = c.width;
    const h = c.height;
    ctx.clearRect(0, 0, w, h);

    const numZones = segments.length;
    const blockW = w / numZones;

    for (let i = 0; i < numZones; i++) {
      const [hue, sat, val] = segments[i];
      ctx.fillStyle = `hsl(${hue}, ${sat}%, ${Math.round(val * 0.55)}%)`;
      ctx.fillRect(i * blockW, 0, blockW, h);
    }
  });
}

// ── API Helpers ───────────────────────────────────────────────────────────────
async function apiPost(endpoint, body) {
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify(body)
    });
    if (res.status === 401) {
      showAuthModal();
    }
    return res;
  } catch (err) {
    console.error("API error", err);
  }
}

async function apiGet(endpoint) {
  try {
    const res = await fetch(endpoint, {
      headers: getAuthHeaders()
    });
    if (res.status === 401) {
      showAuthModal();
    }
    return res;
  } catch (err) {
    console.error("API GET error", err);
  }
}

// ── Render Complete UI ────────────────────────────────────────────────────────
function renderUI() {
  const devKeys = Object.keys(state.devices || {});
  if (!devKeys.length) return;

  if (currentDevId !== "all" && !state.devices[currentDevId]) {
    currentDevId = devKeys[0];
  }

  if (state.diagnostics) {
    updateTelemetry(state.diagnostics);
  }

  // 1. Render Device Switcher Tabs
  const tabsContainer = document.getElementById("deviceTabs");
  let tabsHtml = "";
  
  devKeys.forEach(k => {
    const dev = state.devices[k];
    const isAct = currentDevId === k ? "active" : "";
    tabsHtml += `
      <button class="device-tab ${isAct}" onclick="switchDevice('${k}')">
        <span>${dev.name.split('(')[0].trim()}</span>
        <span class="tab-badge">${dev.model}</span>
      </button>
    `;
  });

  tabsHtml += `
    <button class="device-tab ${currentDevId === 'all' ? 'active' : ''}" onclick="switchDevice('all')">
      <span>Both Strips</span>
      <span class="tab-badge">Sync All</span>
    </button>
  `;
  tabsContainer.innerHTML = tabsHtml;

  // 2. Active Device Info
  let activeDev = null;
  if (currentDevId === "all") {
    activeDev = {
      name: "All Light Strips",
      model: "DUAL SYNC",
      power: devKeys.some(k => state.devices[k].power),
      brightness: Math.round(devKeys.reduce((a, k) => a + state.devices[k].brightness, 0) / devKeys.length),
      active_label: devKeys.map(k => state.devices[k].active_label).filter((v, i, a) => a.indexOf(v) === i).join(" + ")
    };
  } else {
    activeDev = state.devices[currentDevId];
  }

  document.getElementById("activeDevName").textContent = activeDev.name;
  document.getElementById("devBadge").textContent = activeDev.model;
  document.getElementById("nowPlayingText").textContent = formatName(activeDev.active_label || "Idle");

  // Synchronize dynamic glassmorphism theme with active state
  const currentTheme = getThemeForLabel(activeDev.active_label);
  document.body.setAttribute("data-theme", currentTheme);
  bgEngine.setTheme(currentTheme);

  // Power Button
  const btnPwr = document.getElementById("btnDevicePower");
  const pwrLabel = document.getElementById("pwrLabel");
  if (activeDev.power) {
    btnPwr.classList.add("active");
    pwrLabel.textContent = "ON";
  } else {
    btnPwr.classList.remove("active");
    pwrLabel.textContent = "OFF";
  }

  // Master Power in Header
  const anyOn = devKeys.some(k => state.devices[k].power);
  document.getElementById("btnMasterPower").classList.toggle("active", anyOn);

  // Brightness and Slider Fill Track
  const brightPct = `${activeDev.brightness}%`;
  document.getElementById("brightSlider").value = activeDev.brightness;
  document.getElementById("brightVal").textContent = brightPct;
  document.documentElement.style.setProperty("--bright-pct", brightPct);
  document.documentElement.style.setProperty("--slider-pct", brightPct);

  // 3. Sync Cards (Music / Screen)
  const isL930 = (currentDevId !== "all" && activeDev.model === "L930");
  const musicTitle = document.getElementById("musicSyncTitle");
  const musicDesc = document.getElementById("musicSyncDesc");
  if (isL930) {
    musicTitle.textContent = "Audio Spectrum (IC)";
    musicDesc.textContent = "50-Zone WRGBIC EQ Visualizer";
  } else {
    musicTitle.textContent = "Audio Reactive";
    musicDesc.textContent = "Bass pulse & color cycle";
  }

  const isMusicActive = (activeDev.active_label || "").includes("Audio");
  const isScreenActive = (activeDev.active_label || "").includes("Screen");

  document.getElementById("btnMusicSync").classList.toggle("active", isMusicActive);
  document.getElementById("btnScreenSync").classList.toggle("active", isScreenActive);

  const vmodesContainer = document.getElementById("visualizerModes");
  if (vmodesContainer) {
    vmodesContainer.style.display = isMusicActive ? "block" : "none";
  }

  // Composite Synergy & Circadian Rhythm
  const curComposite = state.composite_mode || "off";
  document.querySelectorAll("#compositeButtons button").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.cmode === curComposite);
  });

  const btnCircadian = document.getElementById("btnCircadianToggle");
  if (btnCircadian) {
    btnCircadian.textContent = state.circadian_enabled ? "☀️ Circadian: ON" : "☀️ Circadian: OFF";
    btnCircadian.style.color = state.circadian_enabled ? "#3dd68c" : "#f5a623";
    btnCircadian.style.borderColor = state.circadian_enabled ? "#3dd68c" : "#2d2d40";
  }

  // Zone Preview Card Visibility
  const zoneCard = document.getElementById("zonePreviewCard");
  if (zoneCard) {
    zoneCard.style.display = (isL930 || currentDevId === "all") ? "block" : "none";
  }

  // 4. Visual Experience Hub (Ambient · Motion · Music)
  const expGrid = document.getElementById("experienceCardsGrid") || document.getElementById("effectsGrid");
  const expHeader = document.getElementById("experienceHubHeader") || document.getElementById("effectsHeader");
  const expSubheading = document.getElementById("experienceSubheading");
  const expCount = document.getElementById("effectsCount");
  const expStatusPill = document.getElementById("experienceStatusPill");

  if (expHeader) {
    expHeader.textContent = isL930 ? "L930 LIGHTING" : "L900 LIGHTING";
  }
  if (expSubheading) {
    expSubheading.textContent = isL930 ? "CURATED LIGHTING SYSTEM · 50-ZONE ADDRESSABLE" : "SLOW AMBIENT LIGHTING SYSTEM";
  }
  if (expStatusPill) {
    expStatusPill.textContent = activeDev.device_on ? "Live & Streaming" : "Standby";
  }

  // Segment tabs active state
  document.querySelectorAll(".primary-segment-tab").forEach(tabBtn => {
    tabBtn.classList.toggle("active", tabBtn.dataset.tab === currentExperienceTab);
  });

  const filterTabsEl = document.getElementById("effectsFilterTabs");
  if (filterTabsEl) {
    filterTabsEl.style.display = (isL930 && currentExperienceTab === "motion") ? "flex" : "none";
    filterTabsEl.querySelectorAll(".effect-tab-btn").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.category === currentEffectCategory);
    });
  }

  const effectSearchQuery = (document.getElementById("effectSearch")?.value || "").trim().toLowerCase();
  let availableItems = [];

  if (currentExperienceTab === "music") {
    // Music visualizer modes
    const musicModes = [
      "reactive_aurora", "pulse", "flow", "chill", "edm", "spectrum", "bass_bounce", "center_burst",
      "twinkle", "director", "acoustic_string", "hydro_acoustic", "bpm_resonator",
      "party", "movie"
    ];
    availableItems = musicModes.map(id => ({
      id,
      meta: EXPERIENCE_METADATA[id] || { tags: "Music Reactive", desc: formatName(id) }
    }));
  } else if (isL930 && state.effects_catalog) {
    const catalog = state.effects_catalog;
    // The visible shelf is intentionally allow-listed by the backend's curated
    // active_effects list. Legacy/core Tapo-like presets remain internal only.
    const curatedSource = Array.isArray(state.active_effects) && state.active_effects.length
      ? state.active_effects
      : (Array.isArray(state.effects_l930) ? state.effects_l930 : []);
    const curatedIds = new Set(curatedSource);
    let keys = Object.keys(catalog).filter(k =>
      curatedIds.has(k) &&
      catalog[k]?.category !== "alias" &&
      catalog[k]?.category !== "reactive" &&
      catalog[k]?.category !== "core" &&
      catalog[k]?.category !== "seasonal" &&
      catalog[k]?.category !== "novelty"
    );

    if (currentExperienceTab === "ambient") {
      keys = keys.filter(k => {
        const m = catalog[k] || {};
        const meta = EXPERIENCE_METADATA[k] || {};
        return (m.group === "Ambient" || meta.tab === "ambient");
      });
    } else {
      // Motion tab
      keys = keys.filter(k => {
        const m = catalog[k] || {};
        const meta = EXPERIENCE_METADATA[k] || {};
        return (m.group === "Motion" || m.group === "Seasonal & Novelty" || m.group === "Creative" || meta.tab === "motion");
      });
      if (currentEffectCategory === "core") {
        keys = keys.filter(k => catalog[k]?.category === "core");
      } else if (currentEffectCategory === "advanced") {
        keys = keys.filter(k => catalog[k]?.category === "advanced");
      } else if (currentEffectCategory === "creative") {
        keys = keys.filter(k => catalog[k]?.category === "creative");
      } else if (currentEffectCategory === "seasonal") {
        keys = keys.filter(k => catalog[k]?.category === "seasonal");
      } else if (currentEffectCategory === "novelty") {
        keys = keys.filter(k => catalog[k]?.category === "novelty");
      }
    }

    availableItems = keys.map(id => ({
      id,
      meta: { ...(catalog[id] || {}), ...(EXPERIENCE_METADATA[id] || {}) }
    }));
  } else {
    // L900 or fallback list
    const effectsList = isL930 ? (state.effects_l930 || []) : (state.effects_l900 || []);
    availableItems = effectsList.map(id => ({
      id,
      meta: EXPERIENCE_METADATA[id] || { tags: "Slow · Ambient", desc: formatName(id) }
    }));
  }

  // Filter by search query if any
  if (effectSearchQuery) {
    availableItems = availableItems.filter(item => {
      const fullText = `${item.id} ${formatName(item.id)} ${item.meta.tags || ''} ${item.meta.desc || ''}`.toLowerCase();
      return fullText.includes(effectSearchQuery);
    });
  }

  let cardsHtml = "";
  const activeLabel = (activeDev.active_label || "").toLowerCase();

  availableItems.forEach(item => {
    const id = item.id;
    const meta = item.meta || {};
    const isActive = (activeLabel === id) || (currentExperienceTab === "music" && state.audio_style === id);
    const isWarn = Boolean(meta.warning);
    const isAdv = meta.category === "advanced" || meta.cat === "advanced";
    const isCreative = meta.category === "creative" || meta.cat === "creative";
    const isSeasonal = meta.category === "seasonal" || meta.cat === "seasonal";

    let badgeOverlay = "";
    if (isWarn) {
      badgeOverlay = `<span class="card-badge-overlay warning">⚠️ Rapid Flash</span>`;
    } else if (isCreative) {
      badgeOverlay = `<span class="card-badge-overlay creative">Creative</span>`;
    } else if (isSeasonal) {
      badgeOverlay = `<span class="card-badge-overlay seasonal">Seasonal</span>`;
    } else if (isAdv) {
      badgeOverlay = `<span class="card-badge-overlay advanced">Advanced</span>`;
    }

    const tags = meta.tags || (meta.group ? `${meta.group} · Smooth` : "Curated · WRGBIC");

    cardsHtml += `
      <div class="experience-card ${isActive ? 'active' : ''}" data-id="${id}" onclick="selectExperience('${id}', '${currentExperienceTab}')">
        <div class="card-banner-wrapper">
          <canvas class="card-banner-canvas" width="340" height="180" data-eff="${id}"></canvas>
          ${badgeOverlay}
        </div>
        <div class="card-meta">
          <h3 class="card-title">${formatName(id)}</h3>
          <p class="card-subtitle">${tags}</p>
        </div>
      </div>
    `;
  });

  if (expGrid) {
    expGrid.innerHTML = cardsHtml;
  }

  // Render procedural artwork on all visible card canvases
  requestAnimationFrame(() => {
    document.querySelectorAll(".card-banner-canvas").forEach(cv => {
      const effId = cv.dataset.eff;
      if (effId) drawCardBanner(cv, effId);
    });
  });

  // Update In-Situ Selected Effect Tray
  updateSelectedEffectTray(activeDev.active_label);

  const emptyState = document.getElementById("effectsEmptyState");
  if (emptyState) {
    emptyState.hidden = availableItems.length > 0;
  }
  if (expCount) {
    expCount.textContent = `${availableItems.length} available`;
  }
  if (emptyState) emptyState.hidden = visibleEffectCount > 0;

  // 5. Static Presets
  const presetsGrid = document.getElementById("presetsGrid");
  let presetsHtml = "";
  (state.modes || []).forEach(m => {
    const isAct = (activeDev.active_label === m) ? "active" : "";
    const color = MODE_COLORS[m] || "#ffffff";
    presetsHtml += `
      <button class="item-btn ${isAct}" onclick="applyMode('${m}')">
        <span class="item-dot" style="background: ${color};"></span>
        <span>${formatName(m)}</span>
      </button>
    `;
  });
  presetsGrid.innerHTML = presetsHtml;
}

// ── Control Actions ───────────────────────────────────────────────────────────
function switchDevice(devId) {
  currentDevId = devId;
  renderUI();
}

function applyMode(name) {
  const theme = getThemeForLabel(name);
  document.body.setAttribute("data-theme", theme);
  bgEngine.setTheme(theme);
  apiPost(`/api/device/${currentDevId}/mode`, { mode: name });
}

function setEffectCategory(cat) {
  currentEffectCategory = cat;
  renderUI();
}

function showToast(message, type = "info", duration = 3500) {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast-item toast-${type}`;
  toast.textContent = message;

  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.add("toast-show");
  });

  setTimeout(() => {
    toast.classList.remove("toast-show");
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 300);
  }, duration);
}

async function applyEffect(name, btnElement = null) {
  const meta = (state.effects_catalog || {})[name] || {};
  if (meta.warning && !sessionStorage.getItem(`warned_${name}`)) {
    if (!confirm(`⚠️ Warning: ${meta.warning}\n\nDo you want to proceed?`)) {
      return;
    }
    sessionStorage.setItem(`warned_${name}`, "true");
  }

  const btn = btnElement || document.querySelector(`.effect-item[data-eff="${name}"]`) || (window.event?.currentTarget);
  if (btn) {
    btn.classList.add("loading");
  }

  try {
    const res = await apiPost(`/api/device/${currentDevId}/effect`, { effect: name });
    if (!res || !res.ok) {
      let errMsg = "Device rejected effect deployment";
      try {
        const data = await res.json();
        if (data && data.detail) errMsg = data.detail;
      } catch (e) {}
      showToast(`⚠️ ${errMsg}`, "error");
      return;
    }

    // Effect confirmed by device! Update theme & notify user
    const theme = getThemeForLabel(name);
    document.body.setAttribute("data-theme", theme);
    bgEngine.setTheme(theme);
    showToast(`✓ Loaded ${formatName(name)}`, "success");
  } catch (err) {
    console.error("Effect deployment error:", err);
    showToast(`⚠️ Network error deploying ${formatName(name)}`, "error");
  } finally {
    if (btn) {
      btn.classList.remove("loading");
    }
  }
}

function toggleGroup(gName) {
  const cls = `grp-${gName.replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const btns = document.querySelectorAll(`.${cls}`);
  btns.forEach(b => {
    b.style.display = (b.style.display === 'none') ? 'flex' : 'none';
  });
}

function switchExperienceTab(tab) {
  currentExperienceTab = tab;
  document.querySelectorAll(".primary-segment-tab").forEach(tabBtn => {
    tabBtn.classList.toggle("active", tabBtn.dataset.tab === tab);
  });
  renderUI();
}

function selectExperience(id, tab) {
  if (tab === "music" || currentExperienceTab === "music") {
    selectMusicStyle(id);
  } else {
    applyEffect(id);
  }
}

async function selectMusicStyle(style) {
  const activeDev = state.devices?.[currentDevId] || {};
  if (!activeDev.music_sync) {
    await apiPost(`/api/device/${currentDevId}/music`, {});
  }
  const theme = getThemeForLabel(style);
  document.body.setAttribute("data-theme", theme);
  bgEngine.setTheme(theme);
  await apiPost(`/api/device/${currentDevId}/music/mode`, { mode: style });
  showToast(`🎵 Music Visualizer: ${formatName(style)}`, "success");
  renderUI();
}

function updateSelectedEffectTray(activeLabel) {
  const dev = state.devices?.[currentDevId] || {};
  const currentEff = activeLabel || dev.active_label || "tide";
  const catalog = state.effects_catalog || {};
  const meta = catalog[currentEff] || EXPERIENCE_METADATA[currentEff] || {};
  const supported = new Set(meta.supported_controls || ["speed", "brightness", "palette"]);

  const titleEl = document.getElementById("trayEffectTitle");
  if (titleEl) titleEl.textContent = formatName(currentEff);

  const kindEl = document.getElementById("trayKindBadge");
  if (kindEl) {
    if (currentExperienceTab === "music") {
      kindEl.textContent = "AUDIO REACTIVE";
    } else {
      kindEl.textContent = meta.kind === "firmware" ? "ON-DEVICE FIRMWARE" : "PROCEDURAL STREAM";
    }
  }

  const descEl = document.getElementById("trayEffectDesc");
  if (descEl) descEl.textContent = meta.desc || EXPERIENCE_METADATA[currentEff]?.desc || "Dynamic 50-zone light experience.";

  // Dynamic slider boxes
  const boxSpeed = document.getElementById("trayBoxSpeed");
  const boxBright = document.getElementById("trayBoxBrightness");
  const boxPalette = document.getElementById("trayBoxPalette");
  const boxDensity = document.getElementById("trayBoxDensity");
  const boxTail = document.getElementById("trayBoxTail");
  const boxWidth = document.getElementById("trayBoxWidth");
  const boxFlash = document.getElementById("trayBoxFlash");
  const musicTelemetry = document.getElementById("trayMusicTelemetry");

  if (currentExperienceTab === "music") {
    if (musicTelemetry) musicTelemetry.style.display = "flex";
    if (boxPalette) boxPalette.style.display = "none";
    if (boxDensity) boxDensity.style.display = "none";
    if (boxTail) boxTail.style.display = "none";
    if (boxWidth) boxWidth.style.display = "none";
    if (boxFlash) boxFlash.style.display = "none";
  } else {
    if (musicTelemetry) musicTelemetry.style.display = "none";
    if (boxPalette) boxPalette.style.display = supported.has("palette") ? "flex" : "none";
    if (boxDensity) boxDensity.style.display = supported.has("particle_density") ? "flex" : "none";
    if (boxTail) boxTail.style.display = supported.has("tail_length") ? "flex" : "none";
    if (boxWidth) boxWidth.style.display = supported.has("wave_width") ? "flex" : "none";
    if (boxFlash) boxFlash.style.display = supported.has("flash_strength") ? "flex" : "none";
  }

  // Start smooth real-time animated preview on tray canvas
  startTrayPreviewAnimation(currentEff);
}

// ── Accurate Real-Time Animated Preview Engine ────────────────────────────────
let previewAnimId = null;
let previewActiveEffect = "tide";
const previewParams = {
  speed: 1.0,
  brightness: 80,
  wave_width: 1.0,
  tail_length: 1.0,
  particle_density: 1.0,
  flash_strength: 1.0,
  palette_name: "sunset"
};

const FX_PALETTES = {
  sunset:    [[12, 100, 100], [28, 95, 95], [335, 75, 80], [270, 70, 60]],
  forest:    [[140, 85, 70], [95, 90, 80], [45, 95, 85], [165, 80, 60]],
  fire:      [[8, 100, 100], [22, 100, 95], [38, 95, 90], [5, 100, 70]],
  pastel:    [[330, 45, 95], [210, 40, 95], [160, 40, 95], [45, 45, 95]],
  tide:      [[195, 90, 85], [175, 85, 90], [215, 80, 75], [155, 75, 70]],
  dusk:      [[275, 80, 75], [320, 85, 80], [18, 95, 90], [240, 70, 60]],
  ember:     [[15, 100, 90], [28, 95, 85], [5, 100, 75], [38, 90, 95]],
  warm_mono: [[30, 90, 90], [35, 85, 95], [25, 95, 85], [40, 80, 100]],
  auto:      [[200, 80, 85], [280, 75, 85], [340, 80, 85], [40, 85, 90]]
};

function sampleFxPalette(paletteName, normPos) {
  const palKey = (paletteName || "sunset").toLowerCase();
  const pal = FX_PALETTES[palKey] || FX_PALETTES.sunset;
  const p = Math.max(0, Math.min(0.9999, ((normPos % 1) + 1) % 1));
  const idx = Math.floor(p * pal.length);
  const nextIdx = (idx + 1) % pal.length;
  const frac = (p * pal.length) - idx;
  const c1 = pal[idx];
  const c2 = pal[nextIdx];
  let hDiff = c2[0] - c1[0];
  if (hDiff > 180) hDiff -= 360;
  if (hDiff < -180) hDiff += 360;
  const h = Math.round((c1[0] + hDiff * frac + 360) % 360);
  const s = Math.round(c1[1] + (c2[1] - c1[1]) * frac);
  const v = Math.round(c1[2] + (c2[2] - c1[2]) * frac);
  return [h, s, v];
}

function computePreviewSegments(effectName, t, numZones, params) {
  const eff = (effectName || "tide").toLowerCase();
  const segments = [];
  const spd = params.speed || 1.0;
  const effT = t * spd;
  const palName = params.palette_name || params.palette || "sunset";
  const pal = FX_PALETTES[palName] || FX_PALETTES.sunset;
  const c0 = pal[0];
  const c1 = pal[1] || pal[0];
  const c2 = pal[2] || pal[0];

  for (let i = 0; i < numZones; i++) {
    let h = 200, s = 80, v = 50;

    switch (eff) {
      case "tide":
      case "ocean": {
        const waveWidth = params.wave_width || 1.0;
        const w1 = Math.sin(i * 0.15 * waveWidth - effT * 1.5);
        const w2 = Math.cos(i * 0.28 - effT * 0.9);
        v = Math.max(12, Math.min(100, Math.round(50 + 45 * (w1 * 0.6 + w2 * 0.4))));
        const [ph, ps] = sampleFxPalette(palName, (i / numZones) * 0.4 + w1 * 0.12 - effT * 0.05);
        h = ph;
        s = Math.round(ps * 0.9);
        break;
      }
      case "golden_hour":
      case "dusk": {
        const waveWidth = params.wave_width || 1.0;
        const w = Math.sin(i * 0.14 * waveWidth - effT * 0.8) * 0.6 + Math.cos(i * 0.22 + effT * 0.5) * 0.4;
        const norm = (w + 1) * 0.5;
        const [ph, ps] = sampleFxPalette(palName, norm);
        h = ph; s = ps;
        v = Math.round(25 + 70 * norm);
        break;
      }
      case "lava_lamp": {
        const b1 = Math.sin(i * 0.18 - effT * 1.2);
        const b2 = Math.cos(i * 0.25 + effT * 0.9);
        const norm = (b1 * 0.55 + b2 * 0.45 + 1) * 0.5;
        const [ph, ps] = sampleFxPalette(palName, norm);
        h = ph; s = ps;
        v = Math.round(20 + 75 * norm);
        break;
      }
      case "drift": {
        const [ph, ps] = sampleFxPalette(palName, (i / numZones) + effT * 0.1);
        h = ph; s = ps;
        v = Math.round(30 + 45 * Math.sin(i * 0.2 + effT * 0.8));
        break;
      }
      case "embers": {
        const baseV = 16 + Math.round(14 * Math.sin(i * 0.35 + effT * 0.6));
        const density = params.particle_density || 1.0;
        const isSpark = Math.sin(i * 13.7 + Math.floor(effT * 4.0 * density)) > 0.85;
        if (isSpark) {
          h = 36; s = 100; v = 100;
        } else {
          h = c0[0]; s = c0[1]; v = baseV;
        }
        break;
      }
      case "flicker": {
        const surge = Math.sin(effT * 5.0 + i * 7.7) * 0.35;
        h = c0[0]; s = c0[1];
        v = Math.max(5, Math.min(100, Math.round(50 + 45 * surge)));
        break;
      }
      case "aurora":
      case "reactive_aurora": {
        const width = params.wave_width || 1.0;
        const wave = Math.sin(i * 0.16 * width + effT * 1.3);
        const [ph, ps] = sampleFxPalette(palName, (wave + 1) * 0.5);
        h = ph;
        s = Math.round(ps * 0.95);
        v = 30 + Math.round(60 * Math.abs(wave));
        break;
      }
      case "cyber_chase":
      case "dual_wipe": {
        const flash = params.flash_strength || 1.0;
        const pos1 = Math.floor(effT * 24) % numZones;
        const pos2 = (numZones - 1 - (Math.floor(effT * 24) % numZones));
        const d1 = Math.min(Math.abs(i - pos1), Math.abs(i - pos1 + numZones));
        const d2 = Math.min(Math.abs(i - pos2), Math.abs(i - pos2 + numZones));
        if (d1 < 3) {
          h = c0[0]; s = c0[1]; v = Math.min(100, Math.round(100 * flash * (1 - d1 / 3)));
        } else if (d2 < 3) {
          h = c1[0]; s = c1[1]; v = Math.min(100, Math.round(100 * flash * (1 - d2 / 3)));
        } else {
          h = c2[0]; s = Math.round(c2[1] * 0.7); v = 10;
        }
        break;
      }
      case "comet": {
        const head = (effT * 18) % numZones;
        const tailLen = 12 * (params.tail_length || 1.0);
        const dist = (head - i + numZones) % numZones;
        if (dist < tailLen) {
          const fade = 1.0 - (dist / tailLen);
          const [ph, ps] = sampleFxPalette(palName, 1.0 - fade * 0.5);
          h = ph; s = ps; v = Math.round(100 * fade * fade);
        } else {
          h = c0[0]; s = Math.round(c0[1] * 0.6); v = 4;
        }
        break;
      }
      case "sinelon": {
        const tailLen = 6 * (params.tail_length || 1.0);
        const center = (numZones / 2) + ((numZones / 2) - 2) * Math.sin(effT * 2.4);
        const d = Math.abs(i - center);
        const [ph, ps] = sampleFxPalette(palName, Math.min(1.0, d / tailLen));
        h = ph; s = ps;
        v = d < tailLen ? Math.round(100 * (1 - d / tailLen)) : 8;
        break;
      }
      case "radar_sweep":
      case "sonar_sweep": {
        const tailLen = 8 * (params.tail_length || 1.0);
        const head = (effT * 22) % numZones;
        const d = (head - i + numZones) % numZones;
        const [ph, ps] = sampleFxPalette(palName, Math.min(1.0, d / tailLen));
        h = ph; s = ps;
        v = d < tailLen ? Math.round(100 * Math.exp(-d / (tailLen * 0.4))) : 6;
        break;
      }
      case "starfield":
      case "glitter_cascade": {
        const density = params.particle_density || 1.0;
        const isStar = Math.sin(i * 17.3 + Math.floor(effT * 2.5 * density)) > 0.88;
        h = c0[0]; s = isStar ? 20 : c0[1];
        v = isStar ? 100 : 8;
        break;
      }
      case "fireflies": {
        const density = params.particle_density || 1.0;
        const bloom = Math.sin(i * 7.1 + effT * 1.8 * density);
        h = 85; s = 95;
        v = bloom > 0.7 ? Math.round(95 * (bloom - 0.7) / 0.3) : 5;
        break;
      }
      case "breathe": {
        const env = (Math.sin(effT * 1.2) + 1.0) * 0.5;
        let hDiff = c1[0] - c0[0];
        if (hDiff > 180) hDiff -= 360;
        if (hDiff < -180) hDiff += 360;
        h = Math.round((c0[0] + hDiff * env + 360) % 360);
        s = Math.round(c0[1] * (1 - env * 0.3) + c1[1] * (env * 0.3));
        v = Math.round(15 + 80 * env);
        break;
      }
      case "rainbow":
      case "infinite_prism": {
        h = Math.round((i * (360 / numZones) + effT * 40) % 360);
        s = 100; v = 85;
        break;
      }
      case "neon_heartbeat": {
        const cycle = (effT * 1.6) % 2.0;
        const lub = cycle < 0.4 ? Math.sin((cycle / 0.4) * Math.PI) : 0;
        const dub = (cycle >= 0.3 && cycle < 0.7) ? Math.sin(((cycle - 0.3) / 0.4) * Math.PI) * 0.75 : 0;
        const centerDist = Math.abs(i - (numZones / 2));
        if (lub > 0 && centerDist < 6) {
          h = c0[0]; s = c0[1]; v = Math.round(15 + 85 * lub);
        } else if (dub > 0 && (centerDist > 10 && centerDist < 20)) {
          h = c1[0]; s = c1[1]; v = Math.round(15 + 75 * dub);
        } else {
          h = c2[0]; s = c2[1]; v = 8;
        }
        break;
      }
      case "lightning":
      case "coordinated_lightning": {
        const flash = params.flash_strength || 1.0;
        const isBolt = Math.sin(effT * 7.0) > 0.93;
        h = 215; s = 80;
        v = isBolt ? Math.min(100, Math.round(100 * flash)) : 8;
        break;
      }
      default: {
        const wave = Math.sin(i * 0.2 + effT * 2.0);
        const [ph, ps] = sampleFxPalette(palName, (i / numZones) * 0.5 + Math.abs(wave) * 0.5);
        h = ph; s = ps;
        v = Math.round(30 + 50 * Math.abs(wave));
        break;
      }
    }
    segments.push([h, s, v]);
  }
  return segments;
}

function startTrayPreviewAnimation(effectName) {
  if (effectName) previewActiveEffect = effectName;
  const canvas = document.getElementById("trayPreviewCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const numZones = 50;

  if (previewAnimId) cancelAnimationFrame(previewAnimId);

  let startT = performance.now();
  function renderStep(now) {
    const elapsed = (now - startT) / 1000.0;
    const w = canvas.width;
    const h = canvas.height;
    const blockW = w / numZones;
    ctx.clearRect(0, 0, w, h);

    const segments = computePreviewSegments(previewActiveEffect, elapsed, numZones, previewParams);
    const bMult = (previewParams.brightness || 80) / 100.0;

    for (let i = 0; i < numZones; i++) {
      const [hue, sat, val] = segments[i];
      const adjVal = Math.round(val * bMult * 0.55);
      ctx.fillStyle = `hsl(${hue}, ${sat}%, ${adjVal}%)`;
      ctx.fillRect(i * blockW, 0, blockW, h);
    }
    previewAnimId = requestAnimationFrame(renderStep);
  }
  previewAnimId = requestAnimationFrame(renderStep);
}

function updateFxSpeed(val) {
  const v = parseFloat(val);
  previewParams.speed = v;
  const el = document.getElementById("traySpeedVal");
  if (el) el.textContent = `${v.toFixed(1)}x`;
  apiPost(`/api/device/${currentDevId}/effect_params`, { speed: v });
}

function updateFxBrightness(val) {
  const v = parseInt(val, 10);
  previewParams.brightness = v;
  const el = document.getElementById("trayBrightVal");
  if (el) el.textContent = `${v}%`;
  apiPost(`/api/device/${currentDevId}/effect_params`, { brightness: v });
}

function updateFxPalette(val) {
  previewParams.palette_name = val;
  const el = document.getElementById("trayPaletteVal");
  if (el) el.textContent = formatName(val);
  apiPost(`/api/device/${currentDevId}/effect_params`, { palette_name: val });
}

function updateFxDensity(val) {
  const v = parseFloat(val);
  previewParams.particle_density = v;
  const el = document.getElementById("trayDensityVal");
  if (el) el.textContent = `${v.toFixed(1)}x`;
  apiPost(`/api/device/${currentDevId}/effect_params`, { particle_density: v });
}

function updateFxTail(val) {
  const v = parseFloat(val);
  previewParams.tail_length = v;
  const el = document.getElementById("trayTailVal");
  if (el) el.textContent = `${v.toFixed(1)}x`;
  apiPost(`/api/device/${currentDevId}/effect_params`, { tail_length: v });
}

function updateFxWidth(val) {
  const v = parseFloat(val);
  previewParams.wave_width = v;
  const el = document.getElementById("trayWidthVal");
  if (el) el.textContent = `${v.toFixed(1)}x`;
  apiPost(`/api/device/${currentDevId}/effect_params`, { wave_width: v });
}

function updateFxFlash(val) {
  const v = parseFloat(val);
  previewParams.flash_strength = v;
  const el = document.getElementById("trayFlashVal");
  if (el) el.textContent = `${v.toFixed(1)}x`;
  apiPost(`/api/device/${currentDevId}/effect_params`, { flash_strength: v });
}

document.getElementById("effectSearch")?.addEventListener("input", () => renderUI());

// Power Toggle
document.getElementById("btnDevicePower").addEventListener("click", () => {
  apiPost(`/api/device/${currentDevId}/power`, {});
});

document.getElementById("btnMasterPower").addEventListener("click", () => {
  apiPost(`/api/device/all/power`, {});
});

// Brightness Slider
let brightDebounce = null;
const slider = document.getElementById("brightSlider");
slider.addEventListener("input", (e) => {
  const val = parseInt(e.target.value);
  const pct = `${val}%`;
  document.getElementById("brightVal").textContent = pct;
  document.documentElement.style.setProperty("--bright-pct", pct);
  document.documentElement.style.setProperty("--slider-pct", pct);
  clearTimeout(brightDebounce);
  brightDebounce = setTimeout(() => {
    apiPost(`/api/device/${currentDevId}/brightness`, { brightness: val });
  }, 40);
});

// Quick Levels
document.querySelectorAll(".quick-levels button").forEach(btn => {
  btn.addEventListener("click", () => {
    const lvl = parseInt(btn.dataset.level);
    const pct = `${lvl}%`;
    document.getElementById("brightSlider").value = lvl;
    document.getElementById("brightVal").textContent = pct;
    document.documentElement.style.setProperty("--bright-pct", pct);
    document.documentElement.style.setProperty("--slider-pct", pct);
    apiPost(`/api/device/${currentDevId}/brightness`, { brightness: lvl });
  });
});

// Audio Device Selection
async function loadAudioDevices() {
  try {
    const res = await apiGet("/api/audio/devices");
    if (!res || !res.ok) return;
    const data = await res.json();
    const sel = document.getElementById("audioDeviceSelect");
    const badge = document.getElementById("activeAudioDeviceBadge");
    if (!sel) return;

    let html = "";
    (data.devices || []).forEach(d => {
      const isSel = (d.id === data.selected || (d.id === 'auto' && (!data.selected || data.selected === 'auto')));
      html += `<option value="${d.id}" ${isSel ? 'selected' : ''}>${d.name}</option>`;
    });
    sel.innerHTML = html;
    if (badge) {
      badge.textContent = data.selected === "auto" ? "Auto-Detect" : (data.selected.length > 22 ? data.selected.slice(0, 20) + "…" : data.selected);
    }
  } catch (e) {
    console.error("Audio devices load error", e);
  }
}

const audioSelect = document.getElementById("audioDeviceSelect");
if (audioSelect) {
  audioSelect.addEventListener("change", async (e) => {
    const dev = e.target.value;
    await apiPost("/api/audio/select", { device: dev });
    const badge = document.getElementById("activeAudioDeviceBadge");
    if (badge) {
      badge.textContent = dev === "auto" ? "Auto-Detect" : (dev.length > 22 ? dev.slice(0, 20) + "…" : dev);
    }
  });
}

// Sync Toggles
document.getElementById("btnMusicSync").addEventListener("click", () => {
  apiPost(`/api/device/${currentDevId}/music`, {});
});

document.getElementById("btnScreenSync").addEventListener("click", () => {
  apiPost(`/api/device/${currentDevId}/screen`, {});
});

// Two-Axis Visual Styles Selection
document.querySelectorAll("#vstyleButtons button, #vmodeButtons button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#vstyleButtons button, #vmodeButtons button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const style = btn.dataset.vstyle || btn.dataset.vmode;
    const theme = getThemeForLabel(style);
    document.body.setAttribute("data-theme", theme);
    bgEngine.setTheme(theme);
    apiPost(`/api/device/${currentDevId}/music/mode`, { mode: style });
  });
});

const sensSlider = document.getElementById("audioSensSlider");
if (sensSlider) {
  sensSlider.addEventListener("input", (e) => {
    const val = parseFloat(e.target.value);
    const lbl = document.getElementById("audioSensVal");
    if (lbl) lbl.textContent = `${val.toFixed(1)}x`;
  });
  sensSlider.addEventListener("change", (e) => {
    const val = parseFloat(e.target.value);
    apiPost(`/api/device/${currentDevId}/music/sensitivity`, { sensitivity: val });
  });
}

const lookaheadSlider = document.getElementById("audioLookaheadSlider");
if (lookaheadSlider) {
  lookaheadSlider.addEventListener("input", (e) => {
    const val = parseInt(e.target.value);
    const lbl = document.getElementById("audioLookaheadVal");
    if (lbl) lbl.textContent = `${val}ms`;
  });
  lookaheadSlider.addEventListener("change", (e) => {
    const val = parseInt(e.target.value);
    apiPost(`/api/device/${currentDevId}/music/lookahead`, { lookahead_ms: val });
  });
}

// Interactive Tap-to-Calibrate Latency
let tapTimes = [];
let tapTimeout = null;
const btnTapSync = document.getElementById("btnTapSync");
const tapStatus = document.getElementById("tapSyncStatus");

if (btnTapSync && tapStatus) {
  btnTapSync.addEventListener("click", () => {
    const now = performance.now();
    tapTimes.push(now);

    clearTimeout(tapTimeout);
    tapTimeout = setTimeout(() => {
      tapTimes = [];
      tapStatus.style.display = "none";
      btnTapSync.textContent = "🎯 Tap";
      btnTapSync.style.background = "rgba(61, 214, 140, 0.15)";
    }, 3500);

    const count = tapTimes.length;
    tapStatus.style.display = "block";
    btnTapSync.style.background = "rgba(61, 214, 140, 0.35)";

    if (count < 4) {
      btnTapSync.textContent = `🎯 ${count}/4`;
      tapStatus.textContent = `👆 Tap ${4 - count} more time${(4 - count) > 1 ? 's' : ''} on the beat...`;
    } else {
      const diffs = [];
      for (let i = 1; i < tapTimes.length; i++) {
        diffs.push(tapTimes[i] - tapTimes[i - 1]);
      }
      const avgInterval = diffs.reduce((a, b) => a + b, 0) / diffs.length;

      let calibratedLookahead = 45;
      if (avgInterval > 250 && avgInterval < 1200) {
        const phaseOffset = Math.round((avgInterval * 0.08) / 5) * 5;
        calibratedLookahead = Math.min(120, Math.max(20, 30 + phaseOffset));
      }

      const slider = document.getElementById("audioLookaheadSlider");
      const lbl = document.getElementById("audioLookaheadVal");
      if (slider) slider.value = calibratedLookahead;
      if (lbl) lbl.textContent = `${calibratedLookahead}ms`;

      apiPost(`/api/device/${currentDevId}/music/lookahead`, { lookahead_ms: calibratedLookahead });

      btnTapSync.textContent = "✅ Synced";
      tapStatus.textContent = `⚡ Calibrated lookahead to ${calibratedLookahead}ms! Packet transit compensated.`;

      tapTimes = [];
      setTimeout(() => {
        tapStatus.style.display = "none";
        btnTapSync.textContent = "🎯 Tap";
        btnTapSync.style.background = "rgba(61, 214, 140, 0.15)";
      }, 3000);
    }
  });
}

// Toggle Audio Delay Help Drawer
const btnDelayHelp = document.getElementById("btnAudioDelayHelp");
const delayGuide = document.getElementById("audioDelayGuide");
if (btnDelayHelp && delayGuide) {
  btnDelayHelp.addEventListener("click", () => {
    const isShowing = delayGuide.style.display !== "none";
    delayGuide.style.display = isShowing ? "none" : "block";
    btnDelayHelp.style.color = isShowing ? "#a1a1aa" : "#3dd68c";
    btnDelayHelp.style.borderColor = isShowing ? "rgba(255, 255, 255, 0.2)" : "rgba(61, 214, 140, 0.4)";
  });
}

// Composite Synergy Buttons
document.querySelectorAll("#compositeButtons button").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#compositeButtons button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const mode = btn.dataset.cmode;
    apiPost("/api/composite/mode", { mode });
  });
});

// Circadian Toggle
document.getElementById("btnCircadianToggle")?.addEventListener("click", () => {
  apiPost("/api/circadian/toggle", {});
});

// Color Swatches
document.querySelectorAll(".swatches-grid button").forEach(btn => {
  btn.addEventListener("click", () => {
    const h = parseInt(btn.dataset.h);
    const s = parseInt(btn.dataset.s);
    const v = parseInt(slider.value) || 80;
    apiPost(`/api/device/${currentDevId}/color`, { h, s, v });
  });
});

// Native Color Picker (live throttled sending)
let colorPickerTimeout = null;
let lastColorSentTime = 0;

function sendPickedColor(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return;
  const [h, s, v] = rgbToHsv(rgb.r, rgb.g, rgb.b);
  apiPost(`/api/device/${currentDevId}/color`, { h, s, v });
  lastColorSentTime = Date.now();
}

const colorInput = document.getElementById("nativeColorPicker");
colorInput.addEventListener("input", (e) => {
  const hex = e.target.value;
  const now = Date.now();
  if (now - lastColorSentTime >= 100) {
    sendPickedColor(hex);
  } else {
    clearTimeout(colorPickerTimeout);
    colorPickerTimeout = setTimeout(() => sendPickedColor(hex), 100);
  }
});
colorInput.addEventListener("change", (e) => {
  clearTimeout(colorPickerTimeout);
  sendPickedColor(e.target.value);
});

function hexToRgb(hex) {
  const res = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return res ? {
    r: parseInt(res[1], 16),
    g: parseInt(res[2], 16),
    b: parseInt(res[3], 16)
  } : null;
}

function rgbToHsv(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h, s, v = max;
  const d = max - min;
  s = max === 0 ? 0 : d / max;
  if (max === min) {
    h = 0;
  } else {
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h /= 6;
  }
  return [Math.round(h * 360), Math.round(s * 100), Math.round(v * 100)];
}

// Initialize on page load
connectWebSocket();
loadAudioDevices();
