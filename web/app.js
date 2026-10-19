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
let ws = null;
let reconnectTimer = null;

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
  if (!canvas || !segments || !segments.length) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  const numZones = segments.length;
  const blockW = w / numZones;

  for (let i = 0; i < numZones; i++) {
    const [hue, sat, val] = segments[i];
    ctx.fillStyle = `hsl(${hue}, ${sat}%, ${Math.round(val * 0.55)}%)`;
    ctx.fillRect(i * blockW, 0, blockW, h);
  }
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

  // 4. Dynamic Effects
  const fxGrid = document.getElementById("effectsGrid");
  const fxHeader = document.getElementById("effectsHeader");
  const fxCount = document.getElementById("effectsCount");

  const effectsList = isL930 ? state.effects_l930 : state.effects_l900;
  const effectQuery = (document.getElementById("effectSearch")?.value || "").trim().toLowerCase();
  let visibleEffectCount = 0;
  fxHeader.textContent = isL930 ? "L930 50-ZONE WRGBIC EFFECTS" : "L900 SLOW AMBIENT EFFECTS";

  let fxHtml = `
    <div style="grid-column: 1 / -1; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; background: rgba(0,0,0,0.25); padding: 8px 10px; border-radius: 8px;">
      <div>
        <div style="font-size: 9px; font-weight: 700; color: #888899; margin-bottom: 2px;">⚡ SPEED</div>
        <select onchange="updateFxSpeed(this.value)" style="width: 100%; background: #181824; color: #eee; border: 1px solid #2d2d40; border-radius: 6px; padding: 3px 6px; font-size: 11px;">
          <option value="0.5">0.5x (Slow)</option>
          <option value="1.0" selected>1.0x (Normal)</option>
          <option value="1.5">1.5x (Fast)</option>
          <option value="2.0">2.0x (Hyper)</option>
        </select>
      </div>
      <div>
        <div style="font-size: 9px; font-weight: 700; color: #888899; margin-bottom: 2px;">🎨 PALETTE</div>
        <select onchange="updateFxPalette(this.value)" style="width: 100%; background: #181824; color: #eee; border: 1px solid #2d2d40; border-radius: 6px; padding: 3px 6px; font-size: 11px;">
          <option value="sunset" selected>Sunset</option>
          <option value="forest">Forest</option>
          <option value="fire">Fire</option>
          <option value="pastel">Pastel</option>
          <option value="tide">Tide</option>
          <option value="dusk">Dusk</option>
          <option value="ember">Ember</option>
          <option value="warm_mono">WarmMono</option>
        </select>
      </div>
    </div>
  `;

  if (isL930 && state.effects_catalog) {
    const catalog = state.effects_catalog;
    const groups = { "Ambient": [], "Motion": [], "Seasonal & Novelty": [] };
    Object.keys(catalog).forEach(k => {
      const g = catalog[k].group || "Motion";
      if (groups[g]) groups[g].push(k);
    });

    Object.keys(groups).forEach(gName => {
      const items = groups[gName];
      if (!items.length) return;
      const isNovelty = (gName === "Seasonal & Novelty");
      fxHtml += `
        <div style="grid-column: 1 / -1; margin-top: 6px; font-size: 10px; font-weight: 800; color: #a1a1aa; text-transform: uppercase; cursor: pointer;" onclick="toggleGroup('${gName}')">
          ${isNovelty ? '▶ ' + gName + ' (COLLAPSED)' : '▼ ' + gName}
        </div>
      `;
      const visibleItems = items.filter(eff => {
        const meta = catalog[eff] || {};
        return `${eff} ${formatName(eff)} ${meta.desc || ""} ${meta.group || ""}`.toLowerCase().includes(effectQuery);
      });
      if (!visibleItems.length) return;
      visibleEffectCount += visibleItems.length;
      visibleItems.forEach(eff => {
        const isAct = (activeDev.active_label === eff) ? "active" : "";
        const color = EFFECT_COLORS[eff] || "#7c6ef5";
        const meta = catalog[eff] || {};
        const kind = meta.kind === "firmware" ? "On-device" : "Procedural";
        fxHtml += `
          <button class="item-btn effect-item ${isAct} grp-${gName.replace(/\s+/g, '')}" title="${meta.desc || formatName(eff)} · ${kind}" onclick="applyEffect('${eff}')">
            <span class="item-dot" style="background: ${color};"></span>
            <span class="effect-item-copy"><span>${formatName(eff)}</span><small>${kind}</small></span>
          </button>
        `;
      });
    });
  } else {
    const visibleItems = effectsList.filter(eff => `${eff} ${formatName(eff)}`.toLowerCase().includes(effectQuery));
    visibleEffectCount += visibleItems.length;
    visibleItems.forEach(eff => {
      const isAct = (activeDev.active_label === eff) ? "active" : "";
      const color = EFFECT_COLORS[eff] || "#7c6ef5";
      fxHtml += `
        <button class="item-btn effect-item ${isAct}" onclick="applyEffect('${eff}')">
          <span class="item-dot" style="background: ${color};"></span>
          <span class="effect-item-copy"><span>${formatName(eff)}</span></span>
        </button>
      `;
    });
  }
  fxGrid.innerHTML = fxHtml;
  fxCount.textContent = effectQuery
    ? `${visibleEffectCount} / ${effectsList.length} modes`
    : `${effectsList.length} modes`;
  let emptySearch = document.getElementById("effectsEmptyState");
  if (!emptySearch) {
    emptySearch = document.createElement("p");
    emptySearch.id = "effectsEmptyState";
    emptySearch.className = "effects-empty";
    fxGrid.parentNode.insertBefore(emptySearch, fxGrid.nextSibling);
  }
  emptySearch.hidden = visibleEffectCount > 0;
  emptySearch.textContent = effectQuery ? `No effects match “${effectQuery}”. Try another name or behavior.` : "";

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

function applyEffect(name) {
  const theme = getThemeForLabel(name);
  document.body.setAttribute("data-theme", theme);
  bgEngine.setTheme(theme);
  apiPost(`/api/device/${currentDevId}/effect`, { effect: name });
}

function toggleGroup(gName) {
  const cls = `grp-${gName.replace(/\s+/g, '')}`;
  const btns = document.querySelectorAll(`.${cls}`);
  btns.forEach(b => {
    b.style.display = (b.style.display === 'none') ? 'flex' : 'none';
  });
}

function updateFxSpeed(val) {
  apiPost(`/api/device/${currentDevId}/effect_params`, { speed: parseFloat(val) });
}

function updateFxPalette(val) {
  apiPost(`/api/device/${currentDevId}/effect_params`, { palette_name: val });
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
