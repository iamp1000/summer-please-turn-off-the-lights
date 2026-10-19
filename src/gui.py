from __future__ import annotations
import colorsys
import socket
import time
import customtkinter as ctk
from src.colorpicker import ModernColorPicker

# ── Dynamic Glassmorphism Theme Palettes (Matching Reference Designs) ──────────
THEMES = {
    "ambient_drift": {
        "name": "Ambient Drift",
        "bg": "#120a22",
        "surface": "#1d1136",
        "surface_raised": "#271747",
        "surface_high": "#362061",
        "border": "#46297d",
        "border_glow": "#8b5cf6",
        "accent": "#8b5cf6",
        "accent_glow": "#a78bfa",
        "accent_soft": "#311854",
        "power_glow": "#8b5cf6",
        "hero_tint": "#231245",
        "hero_border": "#5c2d9e",
        "text_primary": "#f5f3ff",
        "text_secondary": "#c4b5fd",
        "text_muted": "#8572a8",
    },
    "northern_lights": {
        "name": "Northern Lights",
        "bg": "#061b17",
        "surface": "#0d362e",
        "surface_raised": "#124a3f",
        "surface_high": "#1a6355",
        "border": "#1b6d5e",
        "border_glow": "#10b981",
        "accent": "#10b981",
        "accent_glow": "#34d399",
        "accent_soft": "#11473d",
        "power_glow": "#10b981",
        "hero_tint": "#0f3d35",
        "hero_border": "#1b7d6a",
        "text_primary": "#ecfdf5",
        "text_secondary": "#a7f3d0",
        "text_muted": "#64948a",
    },
    "fireplace": {
        "name": "Fireplace",
        "bg": "#1c0b05",
        "surface": "#38170a",
        "surface_raised": "#4d200e",
        "surface_high": "#662b14",
        "border": "#733017",
        "border_glow": "#f97316",
        "accent": "#f97316",
        "accent_glow": "#fb923c",
        "accent_soft": "#4f1f0d",
        "power_glow": "#f97316",
        "hero_tint": "#42190a",
        "hero_border": "#8f3b18",
        "text_primary": "#fff7ed",
        "text_secondary": "#fed7aa",
        "text_muted": "#996b57",
    },
    "sakura": {
        "name": "Sakura",
        "bg": "#1f0915",
        "surface": "#3d132b",
        "surface_raised": "#541a3c",
        "surface_high": "#6e234f",
        "border": "#7d2859",
        "border_glow": "#f43f5e",
        "accent": "#f43f5e",
        "accent_glow": "#fb7185",
        "accent_soft": "#57183c",
        "power_glow": "#f43f5e",
        "hero_tint": "#471531",
        "hero_border": "#962c68",
        "text_primary": "#fff1f2",
        "text_secondary": "#fecdd3",
        "text_muted": "#9e607f",
    },
    "golden_hour": {
        "name": "Golden Hour",
        "bg": "#1f1304",
        "surface": "#3d2609",
        "surface_raised": "#54340d",
        "surface_high": "#6e4512",
        "border": "#7d4f15",
        "border_glow": "#f59e0b",
        "accent": "#f59e0b",
        "accent_glow": "#fbbf24",
        "accent_soft": "#54350c",
        "power_glow": "#f59e0b",
        "hero_tint": "#472b08",
        "hero_border": "#965c12",
        "text_primary": "#fffbeb",
        "text_secondary": "#fde68a",
        "text_muted": "#997b52",
    },
    "deep_ocean": {
        "name": "Deep Ocean",
        "bg": "#051322",
        "surface": "#0c2847",
        "surface_raised": "#103761",
        "surface_high": "#164c85",
        "border": "#1b5a9e",
        "border_glow": "#06b6d4",
        "accent": "#06b6d4",
        "accent_glow": "#22d3ee",
        "accent_soft": "#0f3a69",
        "power_glow": "#06b6d4",
        "hero_tint": "#0d3259",
        "hero_border": "#1e6bb5",
        "text_primary": "#ecfeff",
        "text_secondary": "#a5f3fc",
        "text_muted": "#5e829e",
    },
}

def get_theme_for_label(label: str) -> str:
    lbl = (label or "").lower()
    if any(k in lbl for k in ("drift", "cyber", "pulse", "shockwave", "melody", "strobe", "matrix", "synthwave", "glitch", "work", "auto", "hybrid", "director")):
        return "ambient_drift"
    if any(k in lbl for k in ("northern", "aurora", "green", "spring", "forest", "tree")):
        return "northern_lights"
    if any(k in lbl for k in ("fire", "candle", "flame", "lava", "ember", "dinner")):
        return "fireplace"
    if any(k in lbl for k in ("sakura", "pink", "rose", "blossom", "heart", "sunset_glow", "sleep", "plasma")):
        return "sakura"
    if any(k in lbl for k in ("gold", "sun", "warm", "amber", "sunrise", "reading", "mirror", "mirror_eq", "spectrum")):
        return "golden_hour"
    if any(k in lbl for k in ("ocean", "water", "rain", "blue", "cyan", "sea", "deep", "ice", "cool", "comet", "starfield", "stars", "wave")):
        return "deep_ocean"
    return "ambient_drift"

MODE_COLORS = {
    "work":        "#fff9e6",
    "deep_focus":  "#ffffff",
    "coding_night":"#ffe0b2",
    "reading":     "#ffd580",
    "movie":       "#e8f0fe",
    "sunset":      "#ff8c42",
    "dinner":      "#ffb347",
    "sleep":       "#ff5c5c",
    "cyberpunk":   "#d966ff",
    "synthwave":   "#aa44ff",
    "gaming":      "#4488ff",
    "ocean":       "#44ccff",
    "forest":      "#44cc88",
    "meditation":  "#9966ff",
}

MODE_TRANSITIONS = {
    "movie": 800,
    "pulse": 200,
    "spectrum": 200,
    "flow": 200,
    "shockwave": 200,
    "mirror_eq": 200,
    "aurora": 200,
    "auto": 200,
}

EFFECT_COLORS = {
    "ambient_drift":    "#aa88ff",
    "northern_lights":  "#44ffaa",
    "fireplace":        "#ff6622",
    "sakura":           "#ff88cc",
    "golden_hour":      "#ffcc44",
    "candle_flicker":   "#ff9933",
    "deep_ocean":       "#0088ff",
    "pulse":            "#ff44aa",
    "rainbow":          "#ff3b30",
    "aurora":           "#34c759",
    "ocean":            "#00c7be",
    "lightning":        "#5856d6",
    "fire_crawl":       "#ff5c00",
    "police":           "#007aff",
    "comet":            "#af52de",
    "pixel_bounce":     "#ffffff",
    "breathing_wave":   "#7c6ef5",
    "meteor":           "#4da8ff",
    "neon_chase":       "#ff007f",
    "color_wipe":       "#ffd700",
    "raindrop":         "#00d2ff",
    "spring":           "#2ecc71",
    "sunrise":          "#f39c12",
    "sunset":           "#e67e22",
    "flicker":          "#f1c40f",
    "rainbow_chase":    "#ff3b30",
    "cyber_chase":      "#ff007f",
    "aurora_wave":      "#34c759",
    "spectrum_idle":    "#9d92ff",
    "matrix_rain":      "#00ff66",
    "strobe_party":     "#ffff00",
    "lava_lamp":        "#ff4500",
    "glitch_wave":      "#00ffff",
    "neon_heartbeat":   "#ff0055",
    "twinkle_stars":    "#70a1ff",
    "hyperdrive":       "#5352ed",
    "sunset_glow":      "#ff6b81",
    "plasma_flow":      "#a55eea",
    "vaporwave_neon":   "#ff78ae",
    "portal_pulse":     "#20bf6b",
    "sonar_sweep":      "#0fb9b1",
    "electric_arc":     "#45aaf2",
    "quantum_dots":     "#fa8231",
}

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class TapoGUI:
    """
    Modern glassmorphic desktop GUI matching reference screenshots exactly.
    100% responsive, fully scrollable, zero hidden buttons, with dynamic
    atmospheric themes for Ambient Drift, Northern Lights, Fireplace, Sakura,
    Golden Hour, and Deep Ocean.
    """

    WIDTH  = 500
    HEIGHT = 860

    def __init__(self, hub, on_quit):
        self.hub = hub
        self.on_quit = on_quit
        
        self.dev_keys = list(hub.devices.keys())
        self.current_dev_id = self.dev_keys[0] if self.dev_keys else "all"
        self.current_theme_key = "ambient_drift"
        self.theme = THEMES[self.current_theme_key]

        self.app = ctk.CTk()
        self.app.title("Tapo Light Control Hub")
        self.app.resizable(True, True)
        self.app.minsize(460, 580)
        self.app.overrideredirect(True)
        try:
            self.app.attributes("-toolwindow", True)
        except Exception:
            pass

        self.app.configure(fg_color=self.theme["bg"])
        self.app.attributes("-alpha", 0.96)

        self.buttons = {}
        self.tab_buttons = {}
        self.vstyle_buttons = {}
        self.accent_buttons = {}
        self.accent_states = {
            "beat_flash": True,
            "hat_sparkle": True,
            "build_tension": True,
            "drop_bloom": True,
        }
        self.style_speed = 1.0
        self.style_intensity = 1.0
        self.style_palette_mode = "auto"
        self._click_test_active = False
        self._click_test_timer = None
        self.quick_level_buttons = {}
        self.card_frames = []
        self.active_picker = None
        self.local_ip = get_local_ip()

        # Tap Sync calibration state
        self._tap_times = []
        self._tap_timer_id = None

        self.app.bind("<FocusOut>", self._on_focus_out)
        self.app.bind("<Escape>", lambda e: self.hide_window())
        self.app.protocol("WM_DELETE_WINDOW", self.quit)

        self._build_ui()
        self.hub.subscribe(self._on_hub_update)

    def _on_focus_out(self, event):
        if self.active_picker:
            return
        try:
            x, y = self.app.winfo_pointerxy()
            wx, wy = self.app.winfo_rootx(), self.app.winfo_rooty()
            ww, wh = self.app.winfo_width(), self.app.winfo_height()
            if not (wx <= x <= wx + ww and wy <= y <= wy + wh):
                self.hide_window()
        except Exception:
            pass

    def _enable_drag(self, widget):
        def start(event):
            self._dx = event.x
            self._dy = event.y
        def drag(event):
            x = self.app.winfo_x() + (event.x - self._dx)
            y = self.app.winfo_y() + (event.y - self._dy)
            self.app.geometry(f"+{x}+{y}")
        widget.bind("<Button-1>", start)
        widget.bind("<B1-Motion>", drag)

    def _bind_mousewheel_recursive(self, widget):
        def _on_wheel(e):
            try:
                self.scroll_body._parent_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except Exception:
                pass
        widget.bind("<MouseWheel>", _on_wheel)
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)

    def _build_ui(self):
        t = self.theme
        self.root_frame = ctk.CTkFrame(self.app, fg_color=t["bg"], corner_radius=0)
        self.root_frame.pack(fill="both", expand=True)

        # ── 1. HEADER (Top Bar) ──────────────────────────────────────────────
        self.header = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        self.header.pack(fill="x", padx=20, pady=(16, 10))
        self.header.columnconfigure(1, weight=1)

        # Left Icon badge (⚡)
        icon_badge = ctk.CTkFrame(self.header, width=38, height=38, corner_radius=10, fg_color=t["surface_raised"])
        icon_badge.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="w")
        icon_badge.pack_propagate(False)
        self.header_icon_lbl = ctk.CTkLabel(icon_badge, text="⚡", font=ctk.CTkFont(size=18), text_color="#f59e0b")
        self.header_icon_lbl.place(relx=0.5, rely=0.5, anchor="center")

        # Titles
        self.header_title = ctk.CTkLabel(
            self.header, text="Tapo Light Hub",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=t["text_primary"]
        )
        self.header_title.grid(row=0, column=1, sticky="w")

        sub_row = ctk.CTkFrame(self.header, fg_color="transparent")
        sub_row.grid(row=1, column=1, sticky="w")
        self.header_status_dot = ctk.CTkLabel(sub_row, text="●", font=ctk.CTkFont(size=9), text_color="#10b981")
        self.header_status_dot.pack(side="left", padx=(0, 5))
        self.header_status_lbl = ctk.CTkLabel(sub_row, text="Live Connected", font=ctk.CTkFont(size=10, weight="bold"), text_color=t["text_secondary"])
        self.header_status_lbl.pack(side="left")

        self._enable_drag(self.header)
        self._enable_drag(self.header_title)

        # Right buttons: Circular glowing power button & Close
        btn_box = ctk.CTkFrame(self.header, fg_color="transparent")
        btn_box.grid(row=0, column=2, rowspan=2, sticky="e")

        self.btn_top_power = ctk.CTkButton(
            btn_box, text="⏻", width=38, height=38, corner_radius=19,
            fg_color=t["accent_soft"], hover_color=t["accent"],
            border_width=2, border_color=t["power_glow"],
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=t["text_primary"],
            command=self._handle_power_click
        )
        self.btn_top_power.pack(side="left", padx=(0, 8))

        btn_close = ctk.CTkButton(
            btn_box, text="✕", width=34, height=34, corner_radius=17,
            fg_color=t["surface_raised"], hover_color="#f43f5e",
            text_color=t["text_secondary"], font=ctk.CTkFont(size=12, weight="bold"),
            command=self.hide_window
        )
        btn_close.pack(side="left")

        # ── 2. SCROLLABLE BODY (Guarantees zero hidden buttons) ───────────────
        self.scroll_body = ctk.CTkScrollableFrame(
            self.root_frame, fg_color="transparent",
            scrollbar_button_color=t["surface_high"],
            scrollbar_button_hover_color=t["accent"]
        )
        self.scroll_body.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        # ── 3. DEVICE SWITCHER PILLS ─────────────────────────────────────────
        self.tabs_bar = ctk.CTkFrame(self.scroll_body, fg_color=t["surface"], corner_radius=16)
        self.tabs_bar.pack(fill="x", pady=(4, 12))
        self.card_frames.append(self.tabs_bar)

        tabs_inner = ctk.CTkFrame(self.tabs_bar, fg_color="transparent")
        tabs_inner.pack(fill="x", padx=5, pady=5)

        tab_items = []
        for dev_id, ctx in self.hub.devices.items():
            model = ctx.model
            label = f"{ctx.name} ({model})" if model else ctx.name
            tab_items.append((dev_id, label))
        tab_items.append(("all", "Both Strips (SYNC ALL)"))

        for dev_id, title_text in tab_items:
            is_cur = (dev_id == self.current_dev_id)
            tbtn = ctk.CTkButton(
                tabs_inner, text=title_text, height=34,
                fg_color=t["surface_raised"] if is_cur else "transparent",
                hover_color=t["surface_high"],
                text_color=t["text_primary"] if is_cur else t["text_secondary"],
                border_width=1 if is_cur else 0,
                border_color=t["accent"] if is_cur else t["border"],
                font=ctk.CTkFont(size=11, weight="bold"),
                corner_radius=12,
                command=lambda d=dev_id: self._select_device_tab(d)
            )
            tbtn.pack(side="left", expand=True, fill="x", padx=3)
            self.tab_buttons[dev_id] = tbtn

        # ── 4. HERO ACTIVE DEVICE / SCENE CARD ───────────────────────────────
        self.hero_card = ctk.CTkFrame(
            self.scroll_body, fg_color=t["hero_tint"],
            corner_radius=18, border_width=1, border_color=t["hero_border"]
        )
        self.hero_card.pack(fill="x", pady=(0, 12))
        self.card_frames.append(self.hero_card)

        hero_inner = ctk.CTkFrame(self.hero_card, fg_color="transparent")
        hero_inner.pack(fill="x", padx=16, pady=16)
        hero_inner.columnconfigure(0, weight=1)

        # Top tag
        self.hero_tag = ctk.CTkLabel(
            hero_inner, text="L900", font=ctk.CTkFont(size=9, weight="bold"),
            fg_color=t["surface_raised"], corner_radius=6,
            text_color=t["accent_glow"], width=46, height=18
        )
        self.hero_tag.grid(row=0, column=0, sticky="w", pady=(0, 4))

        # Main device title
        self.hero_title = ctk.CTkLabel(
            hero_inner, text="Desk Strip (L900-5)",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=t["text_primary"]
        )
        self.hero_title.grid(row=1, column=0, sticky="w")

        # Status indicator
        status_sub = ctk.CTkFrame(hero_inner, fg_color="transparent")
        status_sub.grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.hero_status_dot = ctk.CTkLabel(status_sub, text="●", font=ctk.CTkFont(size=8), text_color="#10b981")
        self.hero_status_dot.pack(side="left", padx=(0, 4))
        self.hero_status_lbl = ctk.CTkLabel(
            status_sub, text="Active", font=ctk.CTkFont(size=11, weight="bold"),
            text_color=t["text_secondary"]
        )
        self.hero_status_lbl.pack(side="left")

        # Large Circular Power Button on right
        self.btn_hero_power = ctk.CTkButton(
            hero_inner, text="⏻", width=50, height=50, corner_radius=25,
            fg_color=t["accent_soft"], hover_color=t["accent"],
            border_width=2, border_color=t["power_glow"],
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=t["text_primary"],
            command=self._handle_power_click
        )
        self.btn_hero_power.grid(row=0, column=1, rowspan=3, sticky="e", padx=(12, 0))

        # ── 5. BRIGHTNESS CARD ───────────────────────────────────────────────
        self.bright_card = ctk.CTkFrame(
            self.scroll_body, fg_color=t["surface"],
            corner_radius=16, border_width=1, border_color=t["border"]
        )
        self.bright_card.pack(fill="x", pady=(0, 12))
        self.card_frames.append(self.bright_card)

        bright_inner = ctk.CTkFrame(self.bright_card, fg_color="transparent")
        bright_inner.pack(fill="x", padx=16, pady=14)

        b_hdr = ctk.CTkFrame(bright_inner, fg_color="transparent")
        b_hdr.pack(fill="x", pady=(0, 8))
        self.lbl_bright_tag = ctk.CTkLabel(
            b_hdr, text="BRIGHTNESS",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]
        )
        self.lbl_bright_tag.pack(side="left")

        self.bright_val_label = ctk.CTkLabel(
            b_hdr, text="50%",
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"),
            text_color=t["accent_glow"]
        )
        self.bright_val_label.pack(side="right")

        # Slider with sun icons
        slider_row = ctk.CTkFrame(bright_inner, fg_color="transparent")
        slider_row.pack(fill="x", pady=(0, 10))

        self.lbl_sun_dim = ctk.CTkLabel(slider_row, text="☼", font=ctk.CTkFont(size=14), text_color=t["text_muted"])
        self.lbl_sun_dim.pack(side="left", padx=(0, 8))

        self.bright_slider = ctk.CTkSlider(
            slider_row, from_=1, to=100,
            command=self._on_brightness_slide,
            progress_color=t["accent"],
            button_color=t["accent_glow"],
            button_hover_color=t["accent"],
            height=16
        )
        self.bright_slider.set(50)
        self.bright_slider.pack(side="left", fill="x", expand=True)

        self.lbl_sun_bright = ctk.CTkLabel(slider_row, text="☀", font=ctk.CTkFont(size=16), text_color=t["accent_glow"])
        self.lbl_sun_bright.pack(side="right", padx=(8, 0))

        # Quick level pills: 15%, 40%, 70%, 100%
        levels_row = ctk.CTkFrame(bright_inner, fg_color="transparent")
        levels_row.pack(fill="x")
        levels_row.columnconfigure((0, 1, 2, 3), weight=1, uniform="lvl")

        for idx, lvl in enumerate([15, 40, 70, 100]):
            qbtn = ctk.CTkButton(
                levels_row, text=f"{lvl}%", height=28,
                fg_color=t["surface_raised"], hover_color=t["surface_high"],
                text_color=t["text_secondary"], font=ctk.CTkFont(size=10, weight="bold"),
                corner_radius=8,
                command=lambda l=lvl: self._set_quick_brightness(l)
            )
            qbtn.grid(row=0, column=idx, padx=3, sticky="ew")
            self.quick_level_buttons[lvl] = qbtn

        # ── 6. LIVE SYNC & REACTIVE CARD ─────────────────────────────────────
        self.sync_card = ctk.CTkFrame(
            self.scroll_body, fg_color=t["surface"],
            corner_radius=16, border_width=1, border_color=t["border"]
        )
        self.sync_card.pack(fill="x", pady=(0, 12))
        self.card_frames.append(self.sync_card)

        sync_inner = ctk.CTkFrame(self.sync_card, fg_color="transparent")
        sync_inner.pack(fill="x", padx=16, pady=14)

        self.lbl_sync_tag = ctk.CTkLabel(
            sync_inner, text="LIVE SYNC & REACTIVE",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]
        )
        self.lbl_sync_tag.pack(anchor="w", pady=(0, 10))

        # Audio Sync & Screen Sync side-by-side cards
        sync_cards_row = ctk.CTkFrame(sync_inner, fg_color="transparent")
        sync_cards_row.pack(fill="x", pady=(0, 10))
        sync_cards_row.columnconfigure((0, 1), weight=1, uniform="sc")

        # Card 1: Audio Reactive
        self.btn_music = ctk.CTkButton(
            sync_cards_row, text="🎵  Audio Reactive\nBass pulse & color cycle",
            fg_color=t["surface_raised"], hover_color=t["surface_high"],
            text_color=t["text_primary"],
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=1, border_color=t["border"],
            corner_radius=12, height=54,
            command=self._handle_music_toggle
        )
        self.btn_music.grid(row=0, column=0, padx=(0, 5), sticky="nsew")

        # Card 2: Screen Sync
        self.btn_scr = ctk.CTkButton(
            sync_cards_row, text="📺  Screen Sync\nAmbiLight display tracking",
            fg_color=t["surface_raised"], hover_color=t["surface_high"],
            text_color=t["text_primary"],
            font=ctk.CTkFont(size=11, weight="bold"),
            border_width=1, border_color=t["border"],
            corner_radius=12, height=54,
            command=self._handle_screen_toggle
        )
        self.btn_scr.grid(row=0, column=1, padx=(5, 0), sticky="nsew")

        # Audio Input Source Dropdown
        audio_src_row = ctk.CTkFrame(sync_inner, fg_color="transparent")
        audio_src_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            audio_src_row, text="🎧 Audio Source:",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=t["text_muted"]
        ).pack(side="left", padx=(0, 8))

        devs = self.hub.get_audio_devices()
        dev_names = [d["name"] for d in devs] or ["Auto-Detect Active Audio"]
        cur_audio = self.hub.audio_device

        self.audio_opt = ctk.CTkOptionMenu(
            audio_src_row, values=dev_names,
            command=self._on_audio_device_selected,
            fg_color=t["surface_raised"],
            button_color=t["surface_high"],
            dropdown_fg_color=t["surface_raised"],
            text_color=t["text_primary"],
            height=28, corner_radius=8
        )
        if cur_audio in dev_names:
            self.audio_opt.set(cur_audio)
        self.audio_opt.pack(side="right", fill="x", expand=True)

        # Two-Axis Visual Styles & Telemetry Grid (Always present, zero clipping)
        self.vstyles_frame = ctk.CTkFrame(sync_inner, fg_color=t["surface_raised"], corner_radius=12)
        self.vstyles_frame.pack(fill="x", pady=(4, 0))

        vst_inner = ctk.CTkFrame(self.vstyles_frame, fg_color="transparent")
        vst_inner.pack(fill="x", padx=12, pady=10)

        vst_hdr = ctk.CTkFrame(vst_inner, fg_color="transparent")
        vst_hdr.pack(fill="x", pady=(0, 6))

        self.gui_section_badge = ctk.CTkLabel(
            vst_hdr, text="VERSE", font=ctk.CTkFont(size=9, weight="bold"),
            fg_color="#10b981", text_color="#ffffff", corner_radius=5, width=48, height=18
        )
        self.gui_section_badge.pack(side="left")

        self.gui_key_pill = ctk.CTkLabel(
            vst_hdr, text="🎼 215° MIN", font=ctk.CTkFont(size=9, weight="bold"),
            text_color=t["accent_glow"]
        )
        self.gui_key_pill.pack(side="left", padx=8)

        self.gui_bpm_lbl = ctk.CTkLabel(
            vst_hdr, text="⚡ 120 BPM",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color="#10b981"
        )
        self.gui_bpm_lbl.pack(side="right")

        # ── AUTO (DIRECTOR) FEATURED CARD ──
        self.btn_auto_mode = ctk.CTkButton(
            vst_inner, text="✨  Auto (Director)  ·  Autonomous Intelligence",
        # ── EXACTLY 4 MODES (Movie, Pulse, Spectrum, Flow) ──
        styles_grid = ctk.CTkFrame(vst_inner, fg_color="transparent")
        styles_grid.pack(fill="x", pady=(0, 8))
        styles_grid.columnconfigure((0, 1), weight=1, uniform="vst")

        base_modes_list = [
            ("movie",    "🎬 Movie",    "Ambilight + Room Fill flare"),
            ("pulse",    "💥 Pulse",    "Gaussian kick ripples & bar rotation"),
            ("spectrum", "📊 Spectrum", "50-band mirror EQ & peak hold"),
            ("flow",     "🌌 Flow",     "2-octave harmonic noise curtains"),
        ]

        for idx, (sid, slabel, sdesc) in enumerate(base_modes_list):
            r, c = divmod(idx, 2)
            card = ctk.CTkFrame(styles_grid, fg_color=t["surface_high"], corner_radius=10, cursor="hand2")
            card.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")

            card_inner = ctk.CTkFrame(card, fg_color="transparent")
            card_inner.pack(fill="both", expand=True, padx=8, pady=6)

            title_lbl = ctk.CTkLabel(
                card_inner, text=slabel, font=ctk.CTkFont(size=10, weight="bold"),
                text_color=t["text_primary"], anchor="w"
            )
            title_lbl.pack(fill="x")

            desc_lbl = ctk.CTkLabel(
                card_inner, text=sdesc, font=ctk.CTkFont(size=8),
                text_color=t["text_muted"], anchor="w"
            )
            desc_lbl.pack(fill="x")

            # Mini live preview bar for visual style card
            prev_canvas = ctk.CTkFrame(card_inner, height=4, fg_color=t["surface_raised"], corner_radius=2)
            prev_canvas.pack(fill="x", pady=(4, 0))

            def _make_click(s=sid):
                return lambda e: self._set_visual_style(s)
            for w in [card, card_inner, title_lbl, desc_lbl, prev_canvas]:
                w.bind("<Button-1>", _make_click())

            self.vstyle_buttons[sid] = card

        # ── CONTROLS: Sensitivity, Brightness Cap, Palette (Auto/Fixed) ──
        tuning_frame = ctk.CTkFrame(vst_inner, fg_color="transparent")
        tuning_frame.pack(fill="x", pady=(2, 4))
        tuning_frame.columnconfigure((0, 1), weight=1)

        # Sensitivity Slider
        sens_box = ctk.CTkFrame(tuning_frame, fg_color="transparent")
        sens_box.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 3))
        s_hdr = ctk.CTkFrame(sens_box, fg_color="transparent")
        s_hdr.pack(fill="x")
        ctk.CTkLabel(s_hdr, text="🎚 Sensitivity:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_sens_val = ctk.CTkLabel(s_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_sens_val.pack(side="right")
        self.gui_sens_slider = ctk.CTkSlider(
            sens_box, from_=0.2, to=3.0, number_of_steps=28,
            command=self._on_audio_sensitivity_change,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=12
        )
        self.gui_sens_slider.set(1.0)
        self.gui_sens_slider.pack(fill="x", pady=(1, 0))

        # Brightness Cap Slider
        cap_box = ctk.CTkFrame(tuning_frame, fg_color="transparent")
        cap_box.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 3))
        cap_hdr = ctk.CTkFrame(cap_box, fg_color="transparent")
        cap_hdr.pack(fill="x")
        ctk.CTkLabel(cap_hdr, text="🔆 Brightness Cap:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_bright_cap_val = ctk.CTkLabel(cap_hdr, text="100%", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_bright_cap_val.pack(side="right")
        self.slider_bright_cap = ctk.CTkSlider(
            cap_box, from_=30, to=100, number_of_steps=70,
            command=self._on_bright_cap_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=12
        )
        self.slider_bright_cap.set(100)
        self.slider_bright_cap.pack(fill="x", pady=(1, 0))

        # Palette: Auto / Fixed
        pal_box = ctk.CTkFrame(tuning_frame, fg_color="transparent")
        pal_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        pal_hdr = ctk.CTkFrame(pal_box, fg_color="transparent")
        pal_hdr.pack(fill="x")
        ctk.CTkLabel(pal_hdr, text="🎨 Palette:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.palette_mode_opt = ctk.CTkOptionMenu(
            pal_hdr, values=["Auto (Key/Chroma)", "Fixed (Current)"],
            command=self._on_palette_mode_selected,
            fg_color=t["surface_high"],
            button_color=t["surface_raised"],
            text_color=t["text_primary"],
            height=20, corner_radius=6, font=ctk.CTkFont(size=9)
        )
        self.palette_mode_opt.set("Auto (Key/Chroma)")
        self.palette_mode_opt.pack(side="right")

        # ── CLICK-TEST VISUAL CALIBRATION & LOOKAHEAD ──
        calib_row = ctk.CTkFrame(vst_inner, fg_color="transparent")
        calib_row.pack(fill="x", pady=(4, 0))

        l_hdr = ctk.CTkFrame(calib_row, fg_color="transparent")
        l_hdr.pack(fill="x")
        ctk.CTkLabel(l_hdr, text="⏱ Latency Lookahead:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_lookahead_val = ctk.CTkLabel(l_hdr, text="0ms", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color="#10b981")
        self.lbl_lookahead_val.pack(side="left", padx=4)

        self.lbl_transition_val = ctk.CTkLabel(l_hdr, text="Transition: 0ms (Punchy)", font=ctk.CTkFont(size=8, weight="bold"), text_color=t["text_secondary"])
        self.lbl_transition_val.pack(side="left", padx=6)

        self.btn_click_test = ctk.CTkButton(
            l_hdr, text="🎯 Click-Test Flash", width=95, height=20,
            fg_color=t["surface_high"], hover_color=t["accent"],
            text_color="#10b981", font=ctk.CTkFont(size=8, weight="bold"),
            corner_radius=4, command=self._toggle_click_test
        )
        self.btn_click_test.pack(side="right")

        # Measured light delay recommendation display
        self.lbl_measured_delay = ctk.CTkLabel(
            calib_row,
            text="Measured light delay: -- ms (Set Voicemeeter A1 delay: ~-- ms)",
            font=ctk.CTkFont(size=8, weight="bold"),
            text_color="#38bdf8",
            anchor="w"
        )
        self.lbl_measured_delay.pack(fill="x", pady=(2, 2))

        self.gui_lookahead_slider = ctk.CTkSlider(
            calib_row, from_=0, to=250, number_of_steps=50,
            command=self._on_lookahead_slide,
            fg_color=t["surface_high"], progress_color="#10b981",
            button_color="#34d399", height=12
        )
        self.gui_lookahead_slider.set(0)
        self.gui_lookahead_slider.pack(fill="x", pady=(1, 0))

        # ── 7. DYNAMIC EFFECTS CARD ──────────────────────────────────────────
        self.fx_card = ctk.CTkFrame(
            self.scroll_body, fg_color=t["surface"],
            corner_radius=16, border_width=1, border_color=t["border"]
        )
        self.fx_card.pack(fill="x", pady=(0, 12))
        self.card_frames.append(self.fx_card)

        fx_inner = ctk.CTkFrame(self.fx_card, fg_color="transparent")
        fx_inner.pack(fill="x", padx=16, pady=14)

        self.fx_header_label = ctk.CTkLabel(
            fx_inner, text="DYNAMIC EFFECTS",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]
        )
        self.fx_header_label.pack(anchor="w", pady=(0, 10))

        self.fx_grid_frame = ctk.CTkFrame(fx_inner, fg_color="transparent")
        self.fx_grid_frame.pack(fill="x")
        self.fx_grid_frame.columnconfigure((0, 1), weight=1, uniform="fx")

        self._render_effects_list()

        # ── 8. PRESETS CARD ──────────────────────────────────────────────────
        self.preset_card = ctk.CTkFrame(
            self.scroll_body, fg_color=t["surface"],
            corner_radius=16, border_width=1, border_color=t["border"]
        )
        self.preset_card.pack(fill="x", pady=(0, 12))
        self.card_frames.append(self.preset_card)

        preset_inner = ctk.CTkFrame(self.preset_card, fg_color="transparent")
        preset_inner.pack(fill="x", padx=16, pady=14)

        self.lbl_presets_tag = ctk.CTkLabel(
            preset_inner, text="PRESETS",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]
        )
        self.lbl_presets_tag.pack(anchor="w", pady=(0, 10))

        presets_grid = ctk.CTkFrame(preset_inner, fg_color="transparent")
        presets_grid.pack(fill="x")
        presets_grid.columnconfigure((0, 1), weight=1, uniform="pr")

        modes_list = list(self.hub.config.get("modes", {}).keys()) or [
            "work", "deep_focus", "coding_night", "reading", "sunset", "dinner", "movie", "sleep"
        ]
        for idx, name in enumerate(modes_list):
            r, c = divmod(idx, 2)
            dot_col = MODE_COLORS.get(name, t["text_muted"])
            display = name.replace("_", " ").title()
            btn = self._make_item_button(presets_grid, display, dot_col, lambda n=name: self._apply_mode(n))
            btn.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
            self.buttons[f"mode_{name}"] = btn

        # ── 9. ADVANCED COLOR WHEEL PICKER BUTTON ────────────────────────────
        self.btn_picker = ctk.CTkButton(
            self.scroll_body, text="🎨  Advanced Color Wheel Picker",
            fg_color=t["surface_raised"], hover_color=t["accent_soft"],
            text_color=t["text_primary"],
            border_width=1, border_color=t["border_glow"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._show_picker,
            corner_radius=14, height=42
        )
        self.btn_picker.pack(fill="x", pady=(0, 12))

        # ── 10. TELEMETRY & DIAGNOSTICS CARD ─────────────────────────────────
        self.diag_card = ctk.CTkFrame(
            self.scroll_body, fg_color=t["surface"],
            corner_radius=14, border_width=1, border_color=t["border"]
        )
        self.diag_card.pack(fill="x", pady=(0, 12))
        self.card_frames.append(self.diag_card)

        diag_inner = ctk.CTkFrame(self.diag_card, fg_color="transparent")
        diag_inner.pack(fill="x", padx=14, pady=10)

        diag_hdr = ctk.CTkFrame(diag_inner, fg_color="transparent")
        diag_hdr.pack(fill="x", pady=(0, 6))
        self.lbl_diag_tag = ctk.CTkLabel(
            diag_hdr, text="SYSTEM TELEMETRY (1s LIVE)",
            font=ctk.CTkFont(size=8, weight="bold"), text_color=t["text_muted"]
        )
        self.lbl_diag_tag.pack(side="left")

        self.gui_diag_status = ctk.CTkLabel(
            diag_hdr, text="● Connected", font=ctk.CTkFont(size=8, weight="bold"), text_color="#10b981"
        )
        self.gui_diag_status.pack(side="right")

        metrics_row = ctk.CTkFrame(diag_inner, fg_color="transparent")
        metrics_row.pack(fill="x")
        metrics_row.columnconfigure((0, 1, 2), weight=1, uniform="m")

        # Metric 1: FPS
        m1 = ctk.CTkFrame(metrics_row, fg_color=t["surface_raised"], corner_radius=6)
        m1.grid(row=0, column=0, padx=2, sticky="nsew")
        ctk.CTkLabel(m1, text="SEND FPS", font=ctk.CTkFont(size=7, weight="bold"), text_color=t["text_muted"]).pack(pady=(4, 0))
        self.gui_fps_val = ctk.CTkLabel(m1, text="--", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#10b981")
        self.gui_fps_val.pack()
        self.gui_render_val = ctk.CTkLabel(m1, text="30 calc", font=ctk.CTkFont(size=7), text_color=t["text_secondary"])
        self.gui_render_val.pack(pady=(0, 3))

        # Metric 2: RTT Latency
        m2 = ctk.CTkFrame(metrics_row, fg_color=t["surface_raised"], corner_radius=6)
        m2.grid(row=0, column=1, padx=2, sticky="nsew")
        ctk.CTkLabel(m2, text="RTT LATENCY", font=ctk.CTkFont(size=7, weight="bold"), text_color=t["text_muted"]).pack(pady=(4, 0))
        self.gui_rtt_val = ctk.CTkLabel(m2, text="-- ms", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color=t["accent_glow"])
        self.gui_rtt_val.pack()
        self.gui_pacing_val = ctk.CTkLabel(m2, text="auto pace", font=ctk.CTkFont(size=7), text_color=t["text_secondary"])
        self.gui_pacing_val.pack(pady=(0, 3))

        # Metric 3: Drops
        m3 = ctk.CTkFrame(metrics_row, fg_color=t["surface_raised"], corner_radius=6)
        m3.grid(row=0, column=2, padx=2, sticky="nsew")
        ctk.CTkLabel(m3, text="DROP RATE", font=ctk.CTkFont(size=7, weight="bold"), text_color=t["text_muted"]).pack(pady=(4, 0))
        self.gui_drop_val = ctk.CTkLabel(m3, text="--%", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#f59e0b")
        self.gui_drop_val.pack()
        ctk.CTkLabel(m3, text="zero lag", font=ctk.CTkFont(size=7), text_color=t["text_secondary"]).pack(pady=(0, 3))

        # ── 11. BOTTOM STATUS BAR ────────────────────────────────────────────
        self.status_bar = ctk.CTkFrame(self.root_frame, height=28, fg_color=t["surface"], corner_radius=0)
        self.status_bar.pack(fill="x", side="bottom")

        port = self.hub.config.get("web", {}).get("port", 8765)
        web_url = f"http://{self.local_ip}:{port}"

        self._bar_dev = ctk.CTkLabel(
            self.status_bar,
            text=f"  ⚡ Dual-Light Hub Ready  ·  📱 Phone Web App: {web_url}",
            font=ctk.CTkFont(family="Consolas", size=9),
            text_color=t["accent_glow"]
        )
        self._bar_dev.pack(side="left", padx=8)

        self._bar_diag = ctk.CTkLabel(
            self.status_bar, text="[Tx: -- FPS · --ms · --% drop]  ",
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
            text_color="#10b981"
        )
        self._bar_diag.pack(side="right", padx=8)

        # Bind mousewheel recursively so scrolling works anywhere over buttons/labels
        self._bind_mousewheel_recursive(self.scroll_body)

        self._sync_view_to_device()
        self.app.after(1000, self._periodic_telemetry_tick)

    def _make_item_button(self, parent, label: str, dot_color: str, cmd):
        t = self.theme
        frame = ctk.CTkFrame(
            parent, fg_color=t["surface_raised"],
            border_width=1, border_color=t["border"],
            corner_radius=10, cursor="hand2"
        )
        frame.bind("<Button-1>", lambda e: cmd())

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=10, pady=7)
        inner.bind("<Button-1>", lambda e: cmd())

        dot = ctk.CTkLabel(inner, text="●", font=ctk.CTkFont(size=8), text_color=dot_color)
        dot.pack(side="left", padx=(0, 6))
        dot.bind("<Button-1>", lambda e: cmd())

        lbl = ctk.CTkLabel(inner, text=label, font=ctk.CTkFont(size=10, weight="bold"), text_color=t["text_primary"])
        lbl.pack(side="left")
        lbl.bind("<Button-1>", lambda e: cmd())

        def on_enter(e):
            frame.configure(fg_color=self.theme["surface_high"])
        def on_leave(e):
            is_active = getattr(frame, "_active", False)
            frame.configure(fg_color=self.theme["accent_soft"] if is_active else self.theme["surface_raised"])

        for w in [frame, inner, dot, lbl]:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

        frame._active = False
        return frame

    def _render_effects_list(self):
        for widget in self.fx_grid_frame.winfo_children():
            widget.destroy()

        is_l930 = False
        if self.current_dev_id in self.hub.devices:
            is_l930 = (self.hub.devices[self.current_dev_id].model == "L930")

        if is_l930:
            self.fx_header_label.configure(text="L930 50-ZONE WRGBIC EFFECTS")
            eff_list = sorted(list(self.hub.get_full_state().get("effects_l930", [])))
        else:
            self.fx_header_label.configure(text="DYNAMIC EFFECTS")
            eff_list = list(self.hub.config.get("effects", {}).keys()) or [
                "ambient_drift", "northern_lights", "fireplace", "sakura", "golden_hour", "candle_flicker", "deep_ocean", "pulse"
            ]

        for idx, name in enumerate(eff_list):
            r, c = divmod(idx, 2)
            dot_col = EFFECT_COLORS.get(name, self.theme["accent"])
            display = name.replace("_", " ").title()
            btn = self._make_item_button(self.fx_grid_frame, display, dot_col, lambda n=name: self._apply_effect(n))
            btn.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
            self.buttons[f"eff_{name}"] = btn

    def _select_device_tab(self, dev_id: str):
        self.current_dev_id = dev_id
        for did, btn in self.tab_buttons.items():
            is_active = (did == dev_id)
            btn.configure(
                fg_color=self.theme["surface_raised"] if is_active else "transparent",
                border_width=1 if is_active else 0,
                border_color=self.theme["accent"] if is_active else self.theme["border"],
                text_color=self.theme["text_primary"] if is_active else self.theme["text_secondary"]
            )
        self._render_effects_list()
        self._sync_view_to_device()

    def _apply_theme(self, theme_key: str):
        if theme_key not in THEMES or theme_key == self.current_theme_key:
            return
        self.current_theme_key = theme_key
        t = THEMES[theme_key]
        self.theme = t

        # Root & Main components
        self.app.configure(fg_color=t["bg"])
        self.root_frame.configure(fg_color=t["bg"])
        self.tabs_bar.configure(fg_color=t["surface"])
        self.hero_card.configure(fg_color=t["hero_tint"], border_color=t["hero_border"])
        self.bright_card.configure(fg_color=t["surface"], border_color=t["border"])
        self.sync_card.configure(fg_color=t["surface"], border_color=t["border"])
        self.vstyles_frame.configure(fg_color=t["surface_raised"])
        self.fx_card.configure(fg_color=t["surface"], border_color=t["border"])
        self.preset_card.configure(fg_color=t["surface"], border_color=t["border"])
        self.btn_picker.configure(fg_color=t["surface_raised"], border_color=t["border_glow"])
        self.diag_card.configure(fg_color=t["surface"], border_color=t["border"])
        self.status_bar.configure(fg_color=t["surface"])

        # Accent glows & buttons
        self.btn_top_power.configure(fg_color=t["accent_soft"], border_color=t["power_glow"])
        self.btn_hero_power.configure(fg_color=t["accent_soft"], border_color=t["power_glow"])
        self.bright_slider.configure(progress_color=t["accent"], button_color=t["accent_glow"], button_hover_color=t["accent"])
        self.bright_val_label.configure(text_color=t["accent_glow"])
        self.hero_tag.configure(text_color=t["accent_glow"])
        self.hero_title.configure(text_color=t["text_primary"])
        self._bar_dev.configure(text_color=t["accent_glow"])

    def _sync_view_to_device(self):
        if self.current_dev_id == "all":
            devs = list(self.hub.devices.values())
            any_on = any(d.state["power"] for d in devs)
            avg_b = sum(d.state["brightness"] for d in devs) // max(1, len(devs))
            label = "Both Sync"
            model_tag = "ALL"
            dev_title = "Both Strips (Sync All)"
        else:
            ctx = self.hub.devices.get(self.current_dev_id)
            if not ctx: return
            any_on = ctx.state["power"]
            avg_b = ctx.state["brightness"]
            label = ctx.state["active_label"]
            model_tag = ctx.model or "L900"
            dev_title = f"{ctx.name} ({model_tag})"

        # Dynamic Theme adaptation matching reference design
        target_theme = get_theme_for_label(label)
        self._apply_theme(target_theme)

        self.bright_slider.set(avg_b)
        self.bright_val_label.configure(text=f"{avg_b}%")
        self.hero_tag.configure(text=model_tag)
        self.hero_title.configure(text=dev_title)

        # Hero Status
        if any_on:
            self.hero_status_dot.configure(text_color="#10b981")
            self.hero_status_lbl.configure(text="Active", text_color=self.theme["text_primary"])
            self.btn_top_power.configure(fg_color=self.theme["accent_soft"], border_color=self.theme["power_glow"], text="⏻")
            self.btn_hero_power.configure(fg_color=self.theme["accent_soft"], border_color=self.theme["power_glow"])
        else:
            self.hero_status_dot.configure(text_color=self.theme["text_muted"])
            self.hero_status_lbl.configure(text="Idle / Off", text_color=self.theme["text_muted"])
            self.btn_top_power.configure(fg_color="#3a1111", border_color="#f43f5e", text="⏻")
            self.btn_hero_power.configure(fg_color="#3a1111", border_color="#f43f5e")

        # Quick level button highlights
        for lvl, btn in self.quick_level_buttons.items():
            is_match = (abs(avg_b - lvl) < 5)
            btn.configure(
                fg_color=self.theme["accent_soft"] if is_match else self.theme["surface_raised"],
                text_color=self.theme["accent_glow"] if is_match else self.theme["text_secondary"]
            )

        is_music = "Audio" in label
        is_screen = "Screen" in label

        self.btn_music.configure(
            fg_color=self.theme["accent_soft"] if is_music else self.theme["surface_raised"],
            border_color=self.theme["accent"] if is_music else self.theme["border"],
            text_color=self.theme["accent_glow"] if is_music else self.theme["text_primary"]
        )
        self.btn_scr.configure(
            fg_color="#0e3557" if is_screen else self.theme["surface_raised"],
            border_color="#06b6d4" if is_screen else self.theme["border"],
            text_color="#a5f3fc" if is_screen else self.theme["text_primary"]
        )

        for key, btn in self.buttons.items():
            active = (key == f"mode_{label}" or key == f"eff_{label}")
            btn._active = active
            btn.configure(
                fg_color=self.theme["accent_soft"] if active else self.theme["surface_raised"],
                border_width=1 if active else 1,
                border_color=self.theme["accent"] if active else self.theme["border"]
            )

    def _on_hub_update(self, full_state: dict):
        try:
            self.app.after(0, self._sync_view_to_device)
        except Exception:
            pass

    def _periodic_telemetry_tick(self):
        try:
            diags = self.hub.get_diagnostics()
            dev_id = self.current_dev_id
            diag = None
            if dev_id == "all":
                keys = list(diags.keys())
                l930_key = next((k for k in keys if self.hub.devices.get(k) and self.hub.devices[k].model == "L930"), None)
                diag = diags.get(l930_key or (keys[0] if keys else None))
            else:
                diag = diags.get(dev_id)

            if diag:
                self.gui_fps_val.configure(text=f"{diag['send_fps']} FPS")
                self.gui_render_val.configure(text=f"{diag['render_fps']} calc")
                self.gui_rtt_val.configure(text=f"{diag['rtt_ms']} ms")
                tot_lat = round(diag.get("total_latency_ms", 0))
                p95_lat = round(diag.get("p95_latency_ms", tot_lat))
                self.gui_pacing_val.configure(text=f"tot: {tot_lat}ms")
                self.gui_drop_val.configure(text=f"{diag['drop_rate_pct']}%")
                st = diag.get("status", "connected").capitalize()
                st_color = "#10b981" if st == "Connected" else ("#f59e0b" if st == "Reconnecting" else "#f43f5e")
                self.gui_diag_status.configure(text=f"● {st}", text_color=st_color)
                self._bar_diag.configure(
                    text=f"  [Tx: {diag['send_fps']} FPS · {tot_lat}ms delay (p95: {p95_lat}ms) · {diag['drop_rate_pct']}% drop]",
                    text_color="#10b981"
                )
                if tot_lat > 0:
                    self.lbl_measured_delay.configure(
                        text=f"Measured light delay: {tot_lat} ms (Set Voicemeeter A1 delay: ~{tot_lat} ms)"
                    )
                else:
                    self.lbl_measured_delay.configure(
                        text="Measured light delay: -- ms (Set Voicemeeter A1 delay: ~-- ms)"
                    )

            # Audio telemetry
            audio_telem = self.hub.get_audio_telemetry()
            dev_telem = audio_telem.get(self.current_dev_id)
            if dev_telem and dev_telem.get("active"):
                bpm = round(dev_telem.get("bpm", 120.0))
                sec = str(dev_telem.get("section", "VERSE")).upper()
                deg = round(dev_telem.get("key_hue", 215.0))
                mode = (dev_telem.get("mode", "maj") or "maj").upper()

                self.gui_bpm_lbl.configure(text=f"⚡ {bpm} BPM", text_color="#10b981")
                self.gui_section_badge.configure(text=sec)
                self.gui_key_pill.configure(text=f"🎼 {deg}° {mode}")

                # Sync active visual style button & cards
                cur_vstyle = dev_telem.get("style", "auto")
                self._update_style_card_selection(cur_vstyle)
                trans = MODE_TRANSITIONS.get(cur_vstyle.lower(), 0)
                trans_desc = "Flow" if trans > 0 else "Punchy"
                self.lbl_transition_val.configure(text=f"Transition: {trans}ms ({trans_desc})")
            else:
                self.gui_bpm_lbl.configure(text="💤 Inactive", text_color=self.theme["text_muted"])
        except Exception:
            pass
        finally:
            try:
                self.app.after(1000, self._periodic_telemetry_tick)
            except Exception:
                pass

    def _on_brightness_slide(self, val):
        v = int(val)
        self.bright_val_label.configure(text=f"{v}%")
        self.hub.set_brightness(self.current_dev_id, v)

    def _set_quick_brightness(self, lvl: int):
        self.bright_slider.set(lvl)
        self.bright_val_label.configure(text=f"{lvl}%")
        self.hub.set_brightness(self.current_dev_id, lvl)
        for qlvl, btn in self.quick_level_buttons.items():
            is_match = (qlvl == lvl)
            btn.configure(
                fg_color=self.theme["accent_soft"] if is_match else self.theme["surface_raised"],
                text_color=self.theme["accent_glow"] if is_match else self.theme["text_secondary"]
            )

    def _on_audio_device_selected(self, choice: str):
        self.hub.set_audio_device(choice)

    def _handle_power_click(self):
        self.hub.set_power(self.current_dev_id)

    def _apply_mode(self, name: str):
        self.hub.apply_mode(self.current_dev_id, name)

    def _apply_effect(self, name: str):
        self.hub.apply_effect(self.current_dev_id, name)

    def _handle_music_toggle(self):
        self.hub.toggle_music(self.current_dev_id)

    def _handle_screen_toggle(self):
        self.hub.toggle_screen(self.current_dev_id)

    def _set_visual_style(self, style_name: str):
        self.hub.set_music_mode(self.current_dev_id, style_name)
        target_theme = get_theme_for_label(style_name)
        self._apply_theme(target_theme)
        self._update_style_card_selection(style_name)
        trans = MODE_TRANSITIONS.get(style_name.lower(), 0)
        trans_desc = "Flow" if trans > 0 else "Punchy"
        self.lbl_transition_val.configure(text=f"Transition: {trans}ms ({trans_desc})")

    def _update_style_card_selection(self, current_style: str):
        c_clean = (current_style or "auto").strip().lower()
        for sid, sbtn in self.vstyle_buttons.items():
            is_act = (sid == c_clean) or (sid == "auto" and c_clean in ("auto", "hybrid", "director"))
            if isinstance(sbtn, ctk.CTkButton):
                sbtn.configure(
                    fg_color=self.theme["accent"] if is_act else self.theme["surface_high"],
                    text_color="#ffffff" if is_act else self.theme["text_secondary"]
                )
            elif isinstance(sbtn, ctk.CTkFrame):
                sbtn.configure(
                    fg_color=self.theme["accent_soft"] if is_act else self.theme["surface_high"],
                    border_width=1 if is_act else 0,
                    border_color=self.theme["accent_glow"] if is_act else "transparent"
                )

    def _toggle_accent(self, name: str):
        self.accent_states[name] = not self.accent_states.get(name, True)
        st = self.accent_states[name]
        btn = self.accent_buttons.get(name)
        if btn:
            btn.configure(
                fg_color=self.theme["accent_soft"] if st else self.theme["surface_high"],
                text_color=self.theme["accent_glow"] if st else self.theme["text_muted"]
            )
        self.hub.set_accent(self.current_dev_id, name, st)

    def _on_speed_slide(self, val: float):
        v = round(float(val), 1)
        self.lbl_speed_val.configure(text=f"{v:.1f}x")
        self.style_speed = v
        self.hub.set_style_params(self.current_dev_id, speed=v)

    def _on_intensity_slide(self, val: float):
        v = round(float(val), 1)
        self.lbl_intensity_val.configure(text=f"{v:.1f}x")
        self.style_intensity = v
        self.hub.set_style_params(self.current_dev_id, intensity=v)

    def _on_bright_cap_slide(self, val: float):
        b = int(val)
        self.lbl_bright_cap_val.configure(text=f"{b}%")
        self.hub.set_style_params(self.current_dev_id, brightness_cap=float(b))

    def _on_palette_mode_selected(self, choice: str):
        mode = "fixed" if "Fixed" in choice else "auto"
        self.style_palette_mode = mode
        self.hub.set_style_params(self.current_dev_id, palette_mode=mode)

    def _toggle_click_test(self):
        self._click_test_active = not getattr(self, "_click_test_active", False)
        if self._click_test_active:
            self.btn_click_test.configure(text="⏹ Stop Flash", text_color="#f43f5e")
            self._run_click_test_pulse()
        else:
            self.btn_click_test.configure(text="🎯 Click-Test Flash", text_color="#10b981")

    def _run_click_test_pulse(self):
        if not getattr(self, "_click_test_active", False):
            return
        try:
            import winsound
            winsound.Beep(1200, 25)
        except Exception:
            pass
        self._click_test_timer = self.app.after(500, self._run_click_test_pulse)

    def _on_audio_sensitivity_change(self, val: float):
        v = round(float(val), 1)
        self.lbl_sens_val.configure(text=f"{v:.1f}x")
        self.hub.set_audio_sensitivity(self.current_dev_id, v)

    def _on_lookahead_slide(self, val: float):
        ms = int(val)
        self.lbl_lookahead_val.configure(text=f"{ms}ms")
        self.hub.set_audio_lookahead(self.current_dev_id, ms)

    def _handle_tap_sync(self):
        now = time.monotonic()
        self._tap_times.append(now)

        if self._tap_timer_id:
            self.app.after_cancel(self._tap_timer_id)

        count = len(self._tap_times)
        if count < 4:
            self.btn_tap_sync.configure(text=f"🎯 {count}/4", text_color=self.theme["accent_glow"])
            self._tap_timer_id = self.app.after(3500, self._reset_tap_sync)
        else:
            diffs = [self._tap_times[i] - self._tap_times[i - 1] for i in range(1, len(self._tap_times))]
            avg_int = sum(diffs) / len(diffs)

            calibrated = 45
            if 0.25 <= avg_int <= 1.2:
                calibrated = min(120, max(20, int(round((avg_int * 80.0) / 5.0) * 5)))

            self.gui_lookahead_slider.set(calibrated)
            self.lbl_lookahead_val.configure(text=f"{calibrated}ms")
            self.hub.set_audio_lookahead(self.current_dev_id, calibrated)

            self.btn_tap_sync.configure(text="✅ Done", text_color="#10b981")
            self._tap_times = []
            self.app.after(2500, self._reset_tap_sync)

    def _reset_tap_sync(self):
        self._tap_times = []
        self.btn_tap_sync.configure(text="🎯 Tap", text_color="#10b981")

    def _show_picker(self):
        if self.active_picker: return
        self.scroll_body.pack_forget()
        self.active_picker = ModernColorPicker(
            self.root_frame,
            on_apply=self._handle_picker_apply,
            on_cancel=self._hide_picker
        )
        self.active_picker.pack(fill="both", expand=True, padx=16, pady=16)

    def _handle_picker_apply(self, h, s, v):
        self.hub.apply_custom_color(self.current_dev_id, h, s, v)
        self._hide_picker()

    def _hide_picker(self):
        if self.active_picker:
            self.active_picker.pack_forget()
            self.active_picker.destroy()
            self.active_picker = None
        self.scroll_body.pack(fill="both", expand=True, padx=16, pady=(0, 6))

    def hide_window(self):
        self.app.withdraw()

    def show_window(self):
        sw, sh = self.app.winfo_screenwidth(), self.app.winfo_screenheight()
        h = min(self.HEIGHT, sh - 80)
        w = min(self.WIDTH, sw - 40)
        x = sw - w - 24
        y = max(24, (sh - h) // 2)
        self.app.geometry(f"{w}x{h}+{x}+{y}")
        self.app.deiconify()
        self.app.lift()
        self.app.focus_force()

    def run(self):
        self.app.mainloop()

    def quit(self):
        try:
            if hasattr(self, "hub") and self.hub:
                self.hub.shutdown()
        except Exception:
            pass
        if callable(self.on_quit):
            try:
                self.on_quit()
            except Exception:
                pass
        self.app.quit()