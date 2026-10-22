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
    "party": 0,
    "club": 0,
    "chill": 500,
    "lofi": 500,
    "edm": 0,
    "drop": 0,
    "edm_drop": 0,
    "bass_bounce": 0,
    "bounce": 0,
    "center_burst": 0,
    "burst": 0,
    "twinkle": 150,
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
    # Creative Original Designs (L930 WRGBIC)
    "oil_slick":           "#06b6d4",
    "silk_ribbons":        "#ec4899",
    "nebula_bloom":        "#8b5cf6",
    "holographic_moire":   "#3b82f6",
    "bioluminescent_tide": "#0ea5e9",
    "ember_drift":         "#f97316",
    "cyberpunk":           "#d946ef",
    # Reworked L930 & L900 Effects
    "tide":             "#00c7be",
    "drift":            "#7c6ef5",
    "dusk":             "#c084fc",
    "breathe":          "#f59e0b",
    "starfield":        "#38bdf8",
    "embers":           "#ea580c",
    "lava_lamp":        "#ff4500",
    "golden_hour":      "#ffcc44",
    "hearth":           "#f97316",
    "comet":            "#af52de",
    "cyber_chase":      "#ec4899",
    "vaporwave_neon":   "#f43f5e",
    "sonar_sweep":      "#10b981",
    "neon_heartbeat":   "#e11d48",
    "lantern_sweep":    "#fbbf24",
    "aurora":           "#34c759",
    "deep_ocean":       "#0284c7",
    "sunrise":          "#f39c12",
    "sunset":           "#e67e22",
    "flicker":          "#f1c40f",
    "ocean":            "#00c7be",
    "raindrop":         "#00d2ff",
    "lightning":        "#5856d6",
    "police":           "#007aff",
    "candy_cane":       "#ff3b30",
    "haunted_mansion":  "#8b5cf6",
    "rainbow":          "#ff3b30",
    "ambient_drift":    "#aa88ff",
    "fireplace":        "#ff6622",
    "ocean_waves":      "#0088ff",
    "color_breath":     "#f59e0b",
    "candle_flicker":   "#ff9933",
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


from src.window_layout import responsive_window_geometry


class TapoGUI:
    """
    Modern glassmorphic desktop GUI matching reference screenshots exactly.
    100% responsive, fully scrollable, zero hidden buttons, with dynamic
    atmospheric themes for Ambient Drift, Northern Lights, Fireplace, Sakura,
    Golden Hour, and Deep Ocean.
    """

    def __init__(self, hub, on_quit):
        self.hub = hub
        self.on_quit = on_quit
        
        self.dev_keys = list(hub.devices.keys())
        # Default to L930 device if present, ensuring all 50-zone addressable effects are visible
        l930_key = next((k for k, ctx in hub.devices.items() if getattr(ctx, "model", "") == "L930"), None)
        self.current_dev_id = l930_key or (self.dev_keys[0] if self.dev_keys else "all")
        self.current_theme_key = "ambient_drift"
        self.theme = THEMES[self.current_theme_key]

        self.app = ctk.CTk()
        self.app.title("Summer — Light Control Hub")
        self.app.resizable(True, True)
        screen_w, screen_h = self.app.winfo_screenwidth(), self.app.winfo_screenheight()
        _, _, _, _, min_w, min_h = responsive_window_geometry(screen_w, screen_h)
        self.app.minsize(min_w, min_h)
        # Native Windows chrome provides standard minimize, maximize and resize controls.
        # The tray icon remains active independently while this window is hidden.
        self.app.configure(fg_color=self.theme["bg"])

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
        self._responsive_grids = []
        self._resize_job = None
        self.active_picker = None
        self.local_ip = get_local_ip()

        # Tap Sync calibration state
        self._tap_times = []
        self._tap_timer_id = None

        # Clean window controls (Escape or header Close button hides to tray)
        self.app.bind("<Escape>", lambda e: self.hide_window())
        # Closing the window hides it to the tray; Quit remains explicit in the tray menu.
        self.app.protocol("WM_DELETE_WINDOW", self.hide_window)

        # Global mousewheel listening ensures smooth scrolling regardless of widget hovered
        self.app.bind_all("<MouseWheel>", self._on_global_mousewheel)
        self.app.bind_all("<Button-4>", lambda e: self._on_mousewheel_linux(-1))
        self.app.bind_all("<Button-5>", lambda e: self._on_mousewheel_linux(1))

        self._build_ui()
        self.app.bind("<Configure>", self._on_window_configure, add="+")
        self.hub.subscribe(self._on_hub_update)

    def _on_global_mousewheel(self, event):
        """Dispatches smooth mousewheel scrolling across all children inside the window."""
        try:
            if self.app.state() == "withdrawn" or self.active_picker is not None:
                return
            x, y = self.app.winfo_pointerxy()
            wx, wy = self.app.winfo_rootx(), self.app.winfo_rooty()
            ww, wh = self.app.winfo_width(), self.app.winfo_height()
            if not (wx <= x <= wx + ww and wy <= y <= wy + wh):
                return
            delta = getattr(event, "delta", 0)
            if delta:
                units = int(-1 * (delta / 40))
                if units == 0:
                    units = -1 if delta > 0 else 1
                self.scroll_body._parent_canvas.yview_scroll(units, "units")
        except Exception:
            pass

    def _on_mousewheel_linux(self, direction: int):
        """Scroll handler for X11 systems using Button-4/5."""
        try:
            if self.app.state() == "withdrawn" or self.active_picker is not None:
                return
            self.scroll_body._parent_canvas.yview_scroll(direction * 3, "units")
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
        """Recursive binding fallback to guarantee scroll responsiveness on dynamic subframes."""
        def _on_wheel(e):
            try:
                if self.active_picker is not None:
                    return
                delta = getattr(e, "delta", 0)
                if delta:
                    units = int(-1 * (delta / 40))
                    if units == 0:
                        units = -1 if delta > 0 else 1
                    self.scroll_body._parent_canvas.yview_scroll(units, "units")
            except Exception:
                pass
        try:
            widget.bind("<MouseWheel>", _on_wheel)
            widget.bind("<Button-4>", lambda e: self._on_mousewheel_linux(-1))
            widget.bind("<Button-5>", lambda e: self._on_mousewheel_linux(1))
        except Exception:
            pass
        try:
            for child in widget.winfo_children():
                self._bind_mousewheel_recursive(child)
        except Exception:
            pass

    def _register_responsive_grid(self, grid):
        """Register a card/button grid for responsive column reflow."""
        if grid not in self._responsive_grids:
            self._responsive_grids.append(grid)

    def _on_window_configure(self, event=None):
        """Debounce resize events so reflow does not compete with Tk drawing."""
        if event is not None and getattr(event, "widget", None) is not self.app:
            return
        if self._resize_job is not None:
            try:
                self.app.after_cancel(self._resize_job)
            except Exception:
                pass
        try:
            self._resize_job = self.app.after(90, self._reflow_responsive_grids)
        except Exception:
            self._resize_job = None

    def _reflow_responsive_grids(self):
        self._resize_job = None
        for grid in list(self._responsive_grids):
            try:
                if not grid.winfo_exists():
                    self._responsive_grids.remove(grid)
                    continue
                width = max(1, grid.winfo_width())
                columns = 1 if width < 470 else (2 if width < 820 else 3)
                for col in range(3):
                    grid.columnconfigure(col, weight=1 if col < columns else 0, minsize=0, uniform=f"responsive_{id(grid)}" if col < columns else "")
                children = [child for child in grid.winfo_children()
                            if str(child.winfo_manager()) == "grid"]
                for index, child in enumerate(children):
                    child.grid_configure(row=index // columns, column=index % columns, sticky="nsew")
            except Exception:
                continue

    def _build_ui(self):
        t = self.theme
        self.root_frame = ctk.CTkFrame(
            self.app, fg_color=t["bg"], corner_radius=14,
            border_width=1, border_color=t["border"]
        )
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

        # Native window decorations handle move, resize, minimize and maximize.
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
            btn_box, text="Tray", width=52, height=34, corner_radius=10,
            fg_color=t["surface_raised"], hover_color=t["surface_high"],
            text_color=t["text_secondary"], font=ctk.CTkFont(size=10, weight="bold"),
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

        # ── 50-Segment Rounded LED Strip with Ambient Bloom ──────────────────
        strip_box = ctk.CTkFrame(self.hero_card, fg_color=t["surface_raised"], corner_radius=12)
        strip_box.pack(fill="x", padx=16, pady=(0, 14))

        strip_hdr = ctk.CTkFrame(strip_box, fg_color="transparent")
        strip_hdr.pack(fill="x", padx=10, pady=(6, 2))
        self.lbl_strip_tag = ctk.CTkLabel(
            strip_hdr, text="50-ZONE ADDRESSABLE CANVAS",
            font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]
        )
        self.lbl_strip_tag.pack(side="left")

        self.lbl_strip_stats = ctk.CTkLabel(
            strip_hdr, text="IC 0 ··· IC 49",
            font=ctk.CTkFont(family="Consolas", size=9), text_color=t["accent_glow"]
        )
        self.lbl_strip_stats.pack(side="right")

        import tkinter as tk
        self.strip_canvas = tk.Canvas(
            strip_box,
            height=28,
            bg="#07090e",
            highlightthickness=0,
            bd=0
        )
        self.strip_canvas.pack(fill="x", padx=8, pady=(0, 8))
        self.strip_canvas.bind("<Motion>", self._on_strip_canvas_hover)
        self.strip_canvas.bind("<Leave>", self._on_strip_canvas_leave)
        self._last_rendered_segments = None

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

        # ── LIVE AUDIO MONITOR (Spectrum Visualizer + Onset / Kick / Snare / Hat Meters) ──
        self.audio_monitor_frame = ctk.CTkFrame(vst_inner, fg_color=t["surface_high"], corner_radius=10)
        self.audio_monitor_frame.pack(fill="x", pady=(0, 8))
        mon_inner = ctk.CTkFrame(self.audio_monitor_frame, fg_color="transparent")
        mon_inner.pack(fill="x", padx=10, pady=8)

        # Header with Diagnostic Metrics (BPM + Conf, Noise Floor, Outgoing Tx FPS)
        mon_hdr = ctk.CTkFrame(mon_inner, fg_color="transparent")
        mon_hdr.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            mon_hdr, text="LIVE AUDIO MONITOR",
            font=ctk.CTkFont(size=8, weight="bold"), text_color=t["text_muted"]
        ).pack(side="left")

        self.lbl_mon_meta = ctk.CTkLabel(
            mon_hdr,
            text="BPM: 120 (0%) · Floor: -52dB · Tx: 0 FPS",
            font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
            text_color=t["accent_glow"]
        )
        self.lbl_mon_meta.pack(side="right")

        # Live 16-band Spectrum Mini Bar Chart Canvas
        import tkinter as tk
        self.spectrum_canvas = tk.Canvas(
            mon_inner, height=32, bg="#06080d", highlightthickness=0, bd=0
        )
        self.spectrum_canvas.pack(fill="x", pady=(2, 6))

        # Transient Meters Grid: Onset, Kick, Snare, Hat
        meters_row = ctk.CTkFrame(mon_inner, fg_color="transparent")
        meters_row.pack(fill="x")
        meters_row.columnconfigure((0, 1, 2, 3), weight=1, uniform="m")

        # 1. Onset
        m_on = ctk.CTkFrame(meters_row, fg_color="transparent")
        m_on.grid(row=0, column=0, padx=2, sticky="ew")
        m_on_hdr = ctk.CTkFrame(m_on, fg_color="transparent")
        m_on_hdr.pack(fill="x")
        ctk.CTkLabel(m_on_hdr, text="ONSET", font=ctk.CTkFont(size=7, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_meter_onset = ctk.CTkLabel(m_on_hdr, text="0.0", font=ctk.CTkFont(family="Consolas", size=7), text_color="#38bdf8")
        self.lbl_meter_onset.pack(side="right")
        self.bar_meter_onset = ctk.CTkProgressBar(m_on, height=6, progress_color="#38bdf8", fg_color=t["surface_raised"])
        self.bar_meter_onset.set(0.0)
        self.bar_meter_onset.pack(fill="x", pady=(1, 0))

        # 2. Kick
        m_k = ctk.CTkFrame(meters_row, fg_color="transparent")
        m_k.grid(row=0, column=1, padx=2, sticky="ew")
        m_k_hdr = ctk.CTkFrame(m_k, fg_color="transparent")
        m_k_hdr.pack(fill="x")
        ctk.CTkLabel(m_k_hdr, text="KICK", font=ctk.CTkFont(size=7, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_meter_kick = ctk.CTkLabel(m_k_hdr, text="0.0", font=ctk.CTkFont(family="Consolas", size=7), text_color="#f43f5e")
        self.lbl_meter_kick.pack(side="right")
        self.bar_meter_kick = ctk.CTkProgressBar(m_k, height=6, progress_color="#f43f5e", fg_color=t["surface_raised"])
        self.bar_meter_kick.set(0.0)
        self.bar_meter_kick.pack(fill="x", pady=(1, 0))

        # 3. Snare
        m_s = ctk.CTkFrame(meters_row, fg_color="transparent")
        m_s.grid(row=0, column=2, padx=2, sticky="ew")
        m_s_hdr = ctk.CTkFrame(m_s, fg_color="transparent")
        m_s_hdr.pack(fill="x")
        ctk.CTkLabel(m_s_hdr, text="SNARE", font=ctk.CTkFont(size=7, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_meter_snare = ctk.CTkLabel(m_s_hdr, text="0.0", font=ctk.CTkFont(family="Consolas", size=7), text_color="#fbbf24")
        self.lbl_meter_snare.pack(side="right")
        self.bar_meter_snare = ctk.CTkProgressBar(m_s, height=6, progress_color="#fbbf24", fg_color=t["surface_raised"])
        self.bar_meter_snare.set(0.0)
        self.bar_meter_snare.pack(fill="x", pady=(1, 0))

        # 4. Hat
        m_h = ctk.CTkFrame(meters_row, fg_color="transparent")
        m_h.grid(row=0, column=3, padx=2, sticky="ew")
        m_h_hdr = ctk.CTkFrame(m_h, fg_color="transparent")
        m_h_hdr.pack(fill="x")
        ctk.CTkLabel(m_h_hdr, text="HAT", font=ctk.CTkFont(size=7, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_meter_hat = ctk.CTkLabel(m_h_hdr, text="0.0", font=ctk.CTkFont(family="Consolas", size=7), text_color="#10b981")
        self.lbl_meter_hat.pack(side="right")
        self.bar_meter_hat = ctk.CTkProgressBar(m_h, height=6, progress_color="#10b981", fg_color=t["surface_raised"])
        self.bar_meter_hat.set(0.0)
        self.bar_meter_hat.pack(fill="x", pady=(1, 0))

        # ── AUTO (DIRECTOR) FEATURED CARD ──
        self.btn_auto_mode = ctk.CTkButton(
            vst_inner, text="✨  Auto (Director)  ·  Autonomous Intelligence",
            fg_color=t["accent"], hover_color=t["accent_soft"],
            text_color="#ffffff", font=ctk.CTkFont(size=10, weight="bold"),
            height=30, corner_radius=8,
            command=lambda: self._set_visual_style("auto")
        )
        self.btn_auto_mode.pack(fill="x", pady=(0, 8))
        self.vstyle_buttons["auto"] = self.btn_auto_mode

        # ── Visualizer Modes Grid (Party, Chill, EDM, Movie, Pulse, Spectrum, Flow) ──
        styles_grid = ctk.CTkFrame(vst_inner, fg_color="transparent")
        styles_grid.pack(fill="x", pady=(0, 8))
        self._register_responsive_grid(styles_grid)
        styles_grid.columnconfigure((0, 1), weight=1, uniform="vst")

        base_modes_list = [
            ("party",        "🎉 Party",    "High-energy club strobe & bursts"),
            ("chill",        "☕ Chill",    "Velvety warm breathing ambers"),
            ("edm",          "💥 EDM",      "Bass-triggered white flash strikes"),
            ("movie",        "🎬 Movie",    "Ambilight + Room Fill flare"),
            ("pulse",        "⚡ Pulse",    "Gaussian kick ripples & bar rotation"),
            ("spectrum",     "📊 Spectrum", "50-band mirror EQ & peak hold"),
            ("flow",         "🌊 Flow",     "2-octave harmonic noise curtains"),
            ("bass_bounce",  "🏀 Bounce",   "Inward sub-bass edge fills"),
            ("center_burst", "💫 Burst",    "Outward ripple shockwaves"),
            ("twinkle",      "✨ Twinkle",  "Treble sparkles & ambient velvet"),
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

        # Equalizer Layout (Mirrored 50-Band vs Segmented Staccato VU)
        eq_row = ctk.CTkFrame(vst_inner, fg_color="transparent")
        eq_row.pack(fill="x", pady=(2, 6))
        ctk.CTkLabel(eq_row, text="Equalizer Layout:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.opt_eq_layout = ctk.CTkSegmentedButton(
            eq_row, values=["Mirrored 50-Band", "Segmented Staccato VU"],
            command=self._on_eq_layout_change,
            height=22, font=ctk.CTkFont(size=9, weight="bold"),
            selected_color=t["accent"], selected_hover_color=t["accent_soft"]
        )
        self.opt_eq_layout.set("Mirrored 50-Band")
        self.opt_eq_layout.pack(side="right")

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
            pal_hdr, values=["Auto (Key/Chroma)", "Album Art (Windows Media)", "Fixed (Current)"],
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
        self._register_responsive_grid(presets_grid)
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
        self.app.after(100, self._periodic_strip_preview_tick)

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
        # Clean up stale effect button references before destroying widgets
        self.buttons = {k: v for k, v in self.buttons.items() if not k.startswith("eff_")}

        for widget in self.fx_grid_frame.winfo_children():
            widget.destroy()

        is_l930 = False
        if self.current_dev_id in self.hub.devices:
            is_l930 = (self.hub.devices[self.current_dev_id].model == "L930")
        elif self.current_dev_id == "all":
            is_l930 = any(getattr(ctx, "model", "") == "L930" for ctx in self.hub.devices.values())

        t = self.theme

        # ── Parameter Controls Row (Speed, Brightness, Palette) ──
        fx_ctrls = ctk.CTkFrame(self.fx_grid_frame, fg_color=t["surface_raised"], corner_radius=10)
        fx_ctrls.pack(fill="x", pady=(0, 10))
        fc_inner = ctk.CTkFrame(fx_ctrls, fg_color="transparent")
        fc_inner.pack(fill="x", padx=10, pady=8)

        # Row 1: Speed & Brightness
        sb_row = ctk.CTkFrame(fc_inner, fg_color="transparent")
        sb_row.pack(fill="x", pady=(0, 4))
        sb_row.columnconfigure((0, 1), weight=1)

        # Speed
        sp_box = ctk.CTkFrame(sb_row, fg_color="transparent")
        sp_box.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        sp_hdr = ctk.CTkFrame(sp_box, fg_color="transparent")
        sp_hdr.pack(fill="x")
        ctk.CTkLabel(sp_hdr, text="⚡ Speed:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_speed = ctk.CTkLabel(sp_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_speed.pack(side="right")
        self.slider_fx_speed = ctk.CTkSlider(
            sp_box, from_=0.2, to=3.0, number_of_steps=28,
            command=self._on_fx_speed_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=12
        )
        self.slider_fx_speed.set(1.0)
        self.slider_fx_speed.pack(fill="x", pady=(1, 0))

        # Palette
        pal_box = ctk.CTkFrame(sb_row, fg_color="transparent")
        pal_box.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        pal_hdr = ctk.CTkFrame(pal_box, fg_color="transparent")
        pal_hdr.pack(fill="x")
        ctk.CTkLabel(pal_hdr, text="🎨 Palette:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        pal_names = ["sunset", "forest", "fire", "pastel", "tide", "dusk", "ember", "warm_mono"]
        self.opt_fx_pal = ctk.CTkOptionMenu(
            pal_box, values=pal_names,
            command=self._on_fx_palette_selected,
            fg_color=t["surface_high"], button_color=t["surface_raised"],
            text_color=t["text_primary"], height=20, corner_radius=6,
            font=ctk.CTkFont(size=9)
        )
        self.opt_fx_pal.set("sunset")
        self.opt_fx_pal.pack(fill="x", pady=(4, 0))

        # Row 2: Dynamic Effect-Specific Tuning Sliders Container
        self.fx_specific_frame = ctk.CTkFrame(fc_inner, fg_color="transparent")
        self.fx_specific_frame.pack(fill="x", pady=(4, 0))
        self.fx_specific_frame.columnconfigure((0, 1), weight=1)

        # 1. Tail Length Slider Box
        self.box_fx_tail = ctk.CTkFrame(self.fx_specific_frame, fg_color="transparent")
        tail_hdr = ctk.CTkFrame(self.box_fx_tail, fg_color="transparent")
        tail_hdr.pack(fill="x")
        ctk.CTkLabel(tail_hdr, text="☄ Tail Length:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_tail = ctk.CTkLabel(tail_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_tail.pack(side="right")
        self.slider_fx_tail = ctk.CTkSlider(
            self.box_fx_tail, from_=0.3, to=3.0, number_of_steps=27,
            command=self._on_fx_tail_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=12
        )
        self.slider_fx_tail.set(1.0)
        self.slider_fx_tail.pack(fill="x", pady=(1, 0))

        # 2. Particle Density Slider Box
        self.box_fx_density = ctk.CTkFrame(self.fx_specific_frame, fg_color="transparent")
        dens_hdr = ctk.CTkFrame(self.box_fx_density, fg_color="transparent")
        dens_hdr.pack(fill="x")
        ctk.CTkLabel(dens_hdr, text="✨ Density:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_density = ctk.CTkLabel(dens_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_density.pack(side="right")
        self.slider_fx_density = ctk.CTkSlider(
            self.box_fx_density, from_=0.2, to=3.0, number_of_steps=28,
            command=self._on_fx_density_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=12
        )
        self.slider_fx_density.set(1.0)
        self.slider_fx_density.pack(fill="x", pady=(1, 0))

        # 3. Wave Width Slider Box
        self.box_fx_width = ctk.CTkFrame(self.fx_specific_frame, fg_color="transparent")
        width_hdr = ctk.CTkFrame(self.box_fx_width, fg_color="transparent")
        width_hdr.pack(fill="x")
        ctk.CTkLabel(width_hdr, text="🌊 Wave Width:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_width = ctk.CTkLabel(width_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_width.pack(side="right")
        self.slider_fx_width = ctk.CTkSlider(
            self.box_fx_width, from_=0.3, to=3.0, number_of_steps=27,
            command=self._on_fx_width_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=12
        )
        self.slider_fx_width.set(1.0)
        self.slider_fx_width.pack(fill="x", pady=(1, 0))

        # 4. Flash Strength Slider Box
        self.box_fx_flash = ctk.CTkFrame(self.fx_specific_frame, fg_color="transparent")
        flash_hdr = ctk.CTkFrame(self.box_fx_flash, fg_color="transparent")
        flash_hdr.pack(fill="x")
        ctk.CTkLabel(flash_hdr, text="⚡ Flash Pwr:", font=ctk.CTkFont(size=9, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_flash = ctk.CTkLabel(flash_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_flash.pack(side="right")
        self.slider_fx_flash = ctk.CTkSlider(
            self.box_fx_flash, from_=0.2, to=2.5, number_of_steps=23,
            command=self._on_fx_flash_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=12
        )
        self.slider_fx_flash.set(1.0)
        self.slider_fx_flash.pack(fill="x", pady=(1, 0))

        # Refresh visible controls based on active effect
        self._update_effect_specific_controls()

        # Search remains outside the generated buttons and is restored after rebuilds.
        search_wrap = ctk.CTkFrame(self.fx_grid_frame, fg_color="transparent")
        search_wrap.pack(fill="x", pady=(0, 8))
        self.effect_search_entry = ctk.CTkEntry(
            search_wrap, placeholder_text="Search effects by name or behavior…",
            height=30, corner_radius=8, border_color=t["border"],
            fg_color=t["surface_raised"], text_color=t["text_primary"],
            placeholder_text_color=t["text_muted"],
        )
        self.effect_search_entry.pack(fill="x")
        saved_query = getattr(self, "_effect_search_text", "")
        if saved_query:
            self.effect_search_entry.insert(0, saved_query)
        self.effect_search_entry.bind("<KeyRelease>", self._filter_effect_buttons)
        self._effect_group_grids = {}
        self._effect_group_labels = {}

        if is_l930:
            self.fx_header_label.configure(text="L930 50-ZONE WRGBIC EFFECTS")
            full_st = self.hub.get_full_state()
            catalog = full_st.get("effects_catalog", {})

            # Curated shelf: Creative (7), Core (22), Advanced (10), Seasonal (2), Novelty (1)
            groups = {
                "Creative Original Designs": [k for k, v in catalog.items() if v.get("category") == "creative"],
                "Core Effects": [k for k, v in catalog.items() if v.get("category") == "core"],
                "Advanced Effects": [k for k, v in catalog.items() if v.get("category") == "advanced"],
                "Seasonal": [k for k, v in catalog.items() if v.get("category") == "seasonal"],
                "Novelty (⚠️ Rapid Flashing)": [k for k, v in catalog.items() if v.get("category") == "novelty"],
            }

            for grp_name, eff_names in groups.items():
                if not eff_names:
                    continue

                is_occasional = grp_name in ("Seasonal", "Novelty (⚠️ Rapid Flashing)")
                grp_hdr_frame = ctk.CTkFrame(self.fx_grid_frame, fg_color="transparent")
                grp_hdr_frame.pack(fill="x", pady=(6, 4))

                hdr_text = f"▼  {grp_name.upper()} ({len(eff_names)})" if not is_occasional else f"▶  {grp_name.upper()} ({len(eff_names)}) (COLLAPSED)"
                grp_lbl = ctk.CTkLabel(
                    grp_hdr_frame, text=hdr_text,
                    font=ctk.CTkFont(size=8, weight="bold"),
                    text_color=t["text_muted"], anchor="w"
                )
                grp_lbl.pack(side="left")

                grid = ctk.CTkFrame(self.fx_grid_frame, fg_color="transparent")
                grid.pack(fill="x", pady=(0, 6))
                self._register_responsive_grid(grid)
                grid.columnconfigure((0, 1), weight=1, uniform="fx")
                self._effect_group_grids[grp_name] = grid
                self._effect_group_labels[grp_name] = grp_lbl

                if is_occasional:
                    # Initially collapse occasional groups out of default shelf
                    grid.pack_forget()
                    def _toggle_occasional(lbl=grp_lbl, g=grid, gn=grp_name, n=len(eff_names)):
                        if g.winfo_ismapped():
                            g.pack_forget()
                            lbl.configure(text=f"▶  {gn.upper()} ({n}) (COLLAPSED)")
                        else:
                            g.pack(fill="x", pady=(0, 6))
                            lbl.configure(text=f"▼  {gn.upper()} ({n})")
                    grp_hdr_frame.bind("<Button-1>", lambda e, fn=_toggle_occasional: fn())
                    grp_lbl.bind("<Button-1>", lambda e, fn=_toggle_occasional: fn())

                for idx, name in enumerate(eff_names):
                    r, c = divmod(idx, 2)
                    dot_col = EFFECT_COLORS.get(name, self.theme["accent"])
                    display = name.replace("_", " ").title()
                    btn = self._make_item_button(grid, display, dot_col, lambda n=name: self._apply_effect(n))
                    btn.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
                    self.buttons[f"eff_{name}"] = btn
        else:
            self.fx_header_label.configure(text="L900 SLOW AMBIENT EFFECTS")
            eff_list = [
                "ambient_drift", "fireplace", "golden_hour", "ocean_waves", "color_breath", "candle_flicker"
            ]
            grid = ctk.CTkFrame(self.fx_grid_frame, fg_color="transparent")
            grid.pack(fill="x")
            self._register_responsive_grid(grid)
            grid.columnconfigure((0, 1), weight=1, uniform="fx")

            for idx, name in enumerate(eff_list):
                r, c = divmod(idx, 2)
                dot_col = EFFECT_COLORS.get(name, self.theme["accent"])
                display = name.replace("_", " ").title()
                btn = self._make_item_button(grid, display, dot_col, lambda n=name: self._apply_effect(n))
                btn.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
                self.buttons[f"eff_{name}"] = btn

        # Re-bind mousewheel on newly generated effect controls & cards
        self._bind_mousewheel_recursive(self.fx_grid_frame)

    def _filter_effect_buttons(self, event=None):
        """Filter effect buttons using labels, groups and catalog descriptions."""
        try:
            query = self.effect_search_entry.get().strip().lower()
            self._effect_search_text = query
            catalog = self.hub.get_full_state().get("effects_catalog", {})
            matching_groups = set()
            for key, button in list(self.buttons.items()):
                if not key.startswith("eff_"):
                    continue
                name = key[4:]
                meta = catalog.get(name, {})
                haystack = f"{name} {meta.get('desc', '')} {meta.get('group', '')}".lower()
                cat = meta.get("category", "")
                grp_target = (
                    "Creative Original Designs" if cat == "creative"
                    else "Core Effects" if cat == "core"
                    else "Advanced Effects" if cat == "advanced"
                    else "Seasonal" if cat == "seasonal"
                    else "Novelty (⚠️ Rapid Flashing)" if cat == "novelty"
                    else ""
                )
                if query in haystack:
                    button.grid()
                    if grp_target:
                        matching_groups.add(grp_target)
                else:
                    button.grid_remove()

            # Reveal a collapsed group when search matches one of its effects.
            for group_name, group_grid in getattr(self, "_effect_group_grids", {}).items():
                group_label = self._effect_group_labels.get(group_name)
                if query and group_name in matching_groups:
                    if not group_grid.winfo_ismapped():
                        group_grid.pack(fill="x", pady=(0, 6))
                    if group_label:
                        group_label.configure(text=f"▼  {group_name.upper()}")
                elif group_name in ("Seasonal", "Novelty (⚠️ Rapid Flashing)"):
                    group_grid.pack_forget()
                    if group_label:
                        group_label.configure(text=f"▶  {group_name.upper()} (COLLAPSED)")
        except Exception:
            pass

    def _on_fx_speed_slide(self, val: float):
        v = round(float(val), 2)
        self.lbl_fx_speed.configure(text=f"{v}x")
        dev_ctx = self.hub.devices.get(self.current_dev_id)
        if dev_ctx and hasattr(dev_ctx.fx_engine, "set_parameters"):
            dev_ctx.fx_engine.set_parameters(speed=v)

    def _on_fx_palette_selected(self, pal_name: str):
        dev_ctx = self.hub.devices.get(self.current_dev_id)
        if dev_ctx and hasattr(dev_ctx.fx_engine, "set_parameters"):
            dev_ctx.fx_engine.set_parameters(palette_name=pal_name)

    def _on_fx_tail_slide(self, val: float):
        v = round(float(val), 2)
        self.lbl_fx_tail.configure(text=f"{v}x")
        self.hub.set_effect_params(self.current_dev_id, tail_length=v)

    def _on_fx_density_slide(self, val: float):
        v = round(float(val), 2)
        self.lbl_fx_density.configure(text=f"{v}x")
        self.hub.set_effect_params(self.current_dev_id, particle_density=v)

    def _on_fx_width_slide(self, val: float):
        v = round(float(val), 2)
        self.lbl_fx_width.configure(text=f"{v}x")
        self.hub.set_effect_params(self.current_dev_id, wave_width=v)

    def _on_fx_flash_slide(self, val: float):
        v = round(float(val), 2)
        self.lbl_fx_flash.configure(text=f"{v}x")
        self.hub.set_effect_params(self.current_dev_id, flash_strength=v)

    def _update_effect_specific_controls(self, effect_name: Optional[str] = None):
        """Dynamically reveals only the sliders supported by the selected effect."""
        try:
            if not hasattr(self, "fx_specific_frame"):
                return
            dev = self.hub.devices.get(self.current_dev_id)
            eff = effect_name or (dev.state.get("active_label", "") if dev else "") or ""
            eff_clean = eff.lower().strip()

            catalog = self.hub.get_full_state().get("effects_catalog", {})
            meta = catalog.get(eff_clean, {})
            supported = set(meta.get("supported_controls", ["speed", "brightness"]))

            # Unpack all specific boxes first
            for box in (self.box_fx_tail, self.box_fx_density, self.box_fx_width, self.box_fx_flash):
                box.grid_remove()

            visible_count = 0
            if "tail_length" in supported:
                r, c = divmod(visible_count, 2)
                self.box_fx_tail.grid(row=r, column=c, sticky="ew", padx=(0 if c == 0 else 4, 4 if c == 0 else 0), pady=2)
                visible_count += 1

            if "particle_density" in supported:
                r, c = divmod(visible_count, 2)
                self.box_fx_density.grid(row=r, column=c, sticky="ew", padx=(0 if c == 0 else 4, 4 if c == 0 else 0), pady=2)
                visible_count += 1

            if "wave_width" in supported:
                r, c = divmod(visible_count, 2)
                self.box_fx_width.grid(row=r, column=c, sticky="ew", padx=(0 if c == 0 else 4, 4 if c == 0 else 0), pady=2)
                visible_count += 1

            if "flash_strength" in supported:
                r, c = divmod(visible_count, 2)
                self.box_fx_flash.grid(row=r, column=c, sticky="ew", padx=(0 if c == 0 else 4, 4 if c == 0 else 0), pady=2)
                visible_count += 1

            if visible_count > 0:
                self.fx_specific_frame.pack(fill="x", pady=(4, 0))
            else:
                self.fx_specific_frame.pack_forget()
        except Exception:
            pass

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
        self.root_frame.configure(fg_color=t["bg"], border_color=t["border"])
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

        for key, btn in list(self.buttons.items()):
            try:
                if not btn.winfo_exists():
                    self.buttons.pop(key, None)
                    continue
                active = (key == f"mode_{label}" or key == f"eff_{label}")
                btn._active = active
                btn.configure(
                    fg_color=self.theme["accent_soft"] if active else self.theme["surface_raised"],
                    border_width=1 if active else 1,
                    border_color=self.theme["accent"] if active else self.theme["border"]
                )
            except Exception:
                self.buttons.pop(key, None)

        self._update_effect_specific_controls(label)

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

                # Update Live Audio Monitor meters and spectrum
                onset_val = float(dev_telem.get("onset", 0.0))
                kick_val = float(dev_telem.get("kick", 0.0))
                snare_val = float(dev_telem.get("snare", 0.0))
                hat_val = float(dev_telem.get("hat", 0.0))
                conf_pct = int(round(float(dev_telem.get("confidence", 0.0)) * 100))
                noise_f = float(dev_telem.get("noise_floor", 0.005))
                noise_db = int(round(20 * math.log10(max(1e-5, noise_f))))
                send_fps = float(dev_telem.get("send_fps", (diag.get("send_fps", 0.0) if diag else 0.0)))

                self.bar_meter_onset.set(max(0.0, min(1.0, onset_val)))
                self.lbl_meter_onset.configure(text=f"{onset_val:.2f}")

                self.bar_meter_kick.set(max(0.0, min(1.0, kick_val)))
                self.lbl_meter_kick.configure(text=f"{kick_val:.2f}")

                self.bar_meter_snare.set(max(0.0, min(1.0, snare_val)))
                self.lbl_meter_snare.configure(text=f"{snare_val:.2f}")

                self.bar_meter_hat.set(max(0.0, min(1.0, hat_val)))
                self.lbl_meter_hat.configure(text=f"{hat_val:.2f}")

                self.lbl_mon_meta.configure(
                    text=f"BPM: {bpm} ({conf_pct}%) · Floor: {noise_db}dB · Tx: {send_fps:.1f} FPS"
                )

                # Render mini 16-band spectrum canvas
                raw_spec = dev_telem.get("spectrum", [])
                self._draw_audio_spectrum(raw_spec)

                # Sync active visual style button & cards
                cur_vstyle = dev_telem.get("style", "auto")
                self._update_style_card_selection(cur_vstyle)
                trans = MODE_TRANSITIONS.get(cur_vstyle.lower(), 0)
                trans_desc = "Flow" if trans > 0 else "Punchy"
                self.lbl_transition_val.configure(text=f"Transition: {trans}ms ({trans_desc})")
            else:
                self.gui_bpm_lbl.configure(text="💤 Inactive", text_color=self.theme["text_muted"])
                self.lbl_mon_meta.configure(text="BPM: -- (0%) · Floor: -- · Tx: 0 FPS")
                self.bar_meter_onset.set(0.0)
                self.bar_meter_kick.set(0.0)
                self.bar_meter_snare.set(0.0)
                self.bar_meter_hat.set(0.0)
                self.lbl_meter_onset.configure(text="0.0")
                self.lbl_meter_kick.configure(text="0.0")
                self.lbl_meter_snare.configure(text="0.0")
                self.lbl_meter_hat.configure(text="0.0")
                self._draw_audio_spectrum([])
        except Exception:
            pass
        finally:
            try:
                self.app.after(1000, self._periodic_telemetry_tick)
            except Exception:
                pass

    def _periodic_strip_preview_tick(self):
        try:
            if self.app.state() != "withdrawn":
                segs = self.hub.get_zone_preview(self.current_dev_id)
                self._draw_strip_preview(segs)
        except Exception:
            pass
        finally:
            try:
                self.app.after(80, self._periodic_strip_preview_tick)
            except Exception:
                pass

    def _draw_rounded_block(self, x0: float, y0: float, x1: float, y1: float, radius: float = 2.0, **kwargs):
        """Draws a smooth rounded rectangular LED pixel block on the canvas."""
        r = min(radius, (x1 - x0) / 2.0, (y1 - y0) / 2.0)
        pts = [
            x0 + r, y0,
            x1 - r, y0,
            x1, y0,
            x1, y0 + r,
            x1, y1 - r,
            x1, y1,
            x1 - r, y1,
            x0 + r, y1,
            x0, y1,
            x0, y1 - r,
            x0, y0 + r,
            x0, y0,
        ]
        return self.strip_canvas.create_polygon(pts, smooth=True, **kwargs)

    def _create_or_update_canvas_items(self, cw: float, ch: float):
        """Creates or repositions canvas items once, re-using them without flicker."""
        if getattr(self, "_canvas_geom", None) == (cw, ch) and getattr(self, "_canvas_items", None):
            return
        self._canvas_geom = (cw, ch)
        self.strip_canvas.delete("all")
        self._canvas_items = {"leds": []}

        num_zones = 50
        margin = 6.0
        avail_w = cw - 2 * margin
        step = avail_w / float(num_zones)
        bw = max(2.5, step - 1.5)
        bh = 13.0
        cy = ch / 2.0
        y0 = cy - bh / 2.0
        y1 = cy + bh / 2.0

        # Dark sleek recessed channel track
        self._canvas_items["track"] = self.strip_canvas.create_rectangle(
            margin - 2, cy - 8, cw - margin + 2, cy + 8,
            fill="#0b0d14", outline="#171a24", width=1
        )

        for i in range(num_zones):
            x0 = margin + i * step
            x1 = x0 + bw

            # Bloom 1 (Outer Subsurface Diffuse Glow)
            b1 = self._draw_rounded_block(
                x0 - 2.5, y0 - 4.5, x1 + 2.5, y1 + 4.5,
                radius=3.5, fill="", outline="", state="hidden"
            )
            # Bloom 2 (Saturated Inner Neon Halo)
            b2 = self._draw_rounded_block(
                x0 - 1.2, y0 - 2.2, x1 + 1.2, y1 + 2.2,
                radius=2.5, fill="", outline="", state="hidden"
            )
            # Core LED Block
            blk = self._draw_rounded_block(
                x0, y0, x1, y1, radius=2.0, fill="#131620", outline=""
            )
            # Specular Lens Reflection Line
            sp = self.strip_canvas.create_line(
                x0 + 0.8, y0 + 1.5, x1 - 0.8, y0 + 1.5,
                fill="", width=1, state="hidden"
            )

            self._canvas_items["leds"].append({
                "b1": b1,
                "b2": b2,
                "blk": blk,
                "sp": sp
            })

    def _draw_strip_preview(self, segments: Optional[List[List[int]]] = None):
        if not hasattr(self, "strip_canvas") or not self.strip_canvas:
            return
        try:
            cw = self.strip_canvas.winfo_width()
            ch = self.strip_canvas.winfo_height()
            if cw <= 10:
                cw = 320
            if ch <= 10:
                ch = 28

            self._create_or_update_canvas_items(cw, ch)

            is_powered = True
            dev = self.hub.devices.get(self.current_dev_id)
            if dev and not dev.state.get("power", True):
                is_powered = False

            num_zones = 50
            led_items = self._canvas_items.get("leds", [])

            # Update Canvas Header Tag with accurate preview source
            if hasattr(self, "lbl_strip_tag") and self.lbl_strip_tag:
                active_label = (dev.state.get("active_label", "") if dev else "") or ""
                eff_name = active_label.lower().strip()
                if "audio" in eff_name:
                    self.lbl_strip_tag.configure(text="50-ZONE PREVIEW · [LIVE AUDIO STREAMED 1:1]")
                elif "screen" in eff_name:
                    self.lbl_strip_tag.configure(text="50-ZONE PREVIEW · [AMBILIGHT LIVE STREAM 1:1]")
                elif eff_name in ("sunrise", "sunset", "flicker", "ocean", "raindrop", "lightning", "candy_cane", "haunted_mansion", "rainbow_native"):
                    self.lbl_strip_tag.configure(text="50-ZONE PREVIEW · [HARDWARE APPROXIMATION]")
                elif hasattr(dev, "fx_engine") and getattr(dev.fx_engine, "_active_kind", None) == "firmware":
                    self.lbl_strip_tag.configure(text="50-ZONE PREVIEW · [FIRMWARE PATTERN]")
                elif hasattr(dev, "fx_engine") and getattr(dev.fx_engine, "_active_kind", None) == "streamed_slow":
                    self.lbl_strip_tag.configure(text="50-ZONE PREVIEW · [PROCEDURAL STREAMED 1:1]")
                else:
                    self.lbl_strip_tag.configure(text="50-ZONE ADDRESSABLE CANVAS")

            if not is_powered or not segments or len(segments) == 0:
                self._last_rendered_segments = None
                for i in range(min(num_zones, len(led_items))):
                    items = led_items[i]
                    self.strip_canvas.itemconfig(items["b1"], state="hidden")
                    self.strip_canvas.itemconfig(items["b2"], state="hidden")
                    self.strip_canvas.itemconfig(items["blk"], fill="#131620", state="normal")
                    self.strip_canvas.itemconfig(items["sp"], state="hidden")
                return

            if getattr(self, "_last_rendered_segments", None) == segments:
                return
            self._last_rendered_segments = [list(x) for x in segments]
            from src.pipeline import tapo_hsv_to_rgb

            for i in range(min(num_zones, len(segments), len(led_items))):
                items = led_items[i]
                seg = segments[i]
                h, s, v = int(seg[0]), int(seg[1]), int(seg[2])
                r, g, b = tapo_hsv_to_rgb(h, s, v)

                r_255 = max(0, min(255, int(r * 255)))
                g_255 = max(0, min(255, int(g * 255)))
                b_255 = max(0, min(255, int(b * 255)))
                core_hex = f"#{r_255:02x}{g_255:02x}{b_255:02x}"

                # 1. Update Core Block
                self.strip_canvas.itemconfig(items["blk"], fill=core_hex, state="normal")

                # 2. Ambient Bloom Halos
                if v > 8:
                    b1_r = int(r_255 * 0.18)
                    b1_g = int(g_255 * 0.18)
                    b1_b = int(b_255 * 0.18)
                    self.strip_canvas.itemconfig(
                        items["b1"], fill=f"#{b1_r:02x}{b1_g:02x}{b1_b:02x}", state="normal"
                    )

                    b2_r = int(r_255 * 0.42)
                    b2_g = int(g_255 * 0.42)
                    b2_b = int(b_255 * 0.42)
                    self.strip_canvas.itemconfig(
                        items["b2"], fill=f"#{b2_r:02x}{b2_g:02x}{b2_b:02x}", state="normal"
                    )
                else:
                    self.strip_canvas.itemconfig(items["b1"], state="hidden")
                    self.strip_canvas.itemconfig(items["b2"], state="hidden")

                # 3. Micro Specular Reflection
                if v > 45:
                    spec_r = min(255, r_255 + 60)
                    spec_g = min(255, g_255 + 60)
                    spec_b = min(255, b_255 + 60)
                    self.strip_canvas.itemconfig(
                        items["sp"], fill=f"#{spec_r:02x}{spec_g:02x}{spec_b:02x}", state="normal"
                    )
                else:
                    self.strip_canvas.itemconfig(items["sp"], state="hidden")
        except Exception:
            pass

    def _draw_audio_spectrum(self, spectrum: List[float]):
        """Renders a responsive 16-bar EQ chart on self.spectrum_canvas."""
        if not hasattr(self, "spectrum_canvas") or not self.spectrum_canvas:
            return
        try:
            cw = self.spectrum_canvas.winfo_width()
            ch = self.spectrum_canvas.winfo_height()
            if cw <= 10:
                cw = 320
            if ch <= 5:
                ch = 32

            self.spectrum_canvas.delete("all")
            num_bars = 16
            margin = 4.0
            gap = 2.0
            avail_w = cw - 2 * margin - (num_bars - 1) * gap
            bar_w = max(2.0, avail_w / float(num_bars))

            # Downsample from 50 bands (or whatever length) to 16 display bars
            bars_vals = [0.0] * num_bars
            if spectrum and len(spectrum) > 0:
                spec_len = len(spectrum)
                for b_idx in range(num_bars):
                    s_start = int(b_idx * spec_len / num_bars)
                    s_end = max(s_start + 1, int((b_idx + 1) * spec_len / num_bars))
                    sub = spectrum[s_start:s_end]
                    bars_vals[b_idx] = float(max(sub)) if sub else 0.0

            # Gradient colors: bass (cyan/blue) -> mid (teal/green) -> treble (amber/magenta)
            bar_colors = [
                "#06b6d4", "#0ea5e9", "#38bdf8", "#60a5fa",
                "#34d399", "#10b981", "#059669", "#84cc16",
                "#eab308", "#f59e0b", "#f97316", "#fb923c",
                "#f43f5e", "#ec4899", "#d946ef", "#a855f7"
            ]

            for i in range(num_bars):
                val = max(0.02, min(1.0, bars_vals[i]))
                bar_h = max(2.0, val * (ch - 4.0))
                x0 = margin + i * (bar_w + gap)
                x1 = x0 + bar_w
                y1 = ch - 2.0
                y0 = y1 - bar_h

                col = bar_colors[i % len(bar_colors)]
                self.spectrum_canvas.create_rectangle(
                    x0, y0, x1, y1,
                    fill=col, outline="", width=0
                )
        except Exception:
            pass

    def _on_strip_canvas_hover(self, event):
        try:
            if not getattr(self, "_last_rendered_segments", None) or not hasattr(self, "strip_canvas"):
                return
            cw = self.strip_canvas.winfo_width()
            margin = 6.0
            avail_w = cw - 2 * margin
            if avail_w <= 0:
                return
            step = avail_w / 50.0
            idx = int((event.x - margin) / step)
            if 0 <= idx < len(self._last_rendered_segments):
                seg = self._last_rendered_segments[idx]
                h, s, v = int(seg[0]), int(seg[1]), int(seg[2])
                self.lbl_strip_stats.configure(text=f"IC #{idx} · {h}° {s}% {v}%")
        except Exception:
            pass

    def _on_strip_canvas_leave(self, event):
        try:
            self.lbl_strip_stats.configure(text="IC 0 ··· IC 49")
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
        self._update_effect_specific_controls(name)

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

    def _on_eq_layout_change(self, choice: str):
        layout = "segmented" if "Segmented" in choice else "mirrored"
        targets = [self.hub.devices[self.current_dev_id]] if self.current_dev_id in self.hub.devices else list(self.hub.devices.values())
        for ctx in targets:
            if hasattr(ctx.audio_sync, "_styles"):
                spec = ctx.audio_sync._styles.get("spectrum")
                if spec and hasattr(spec, "set_params"):
                    spec.set_params(layout=layout)

    def _update_style_card_selection(self, current_style: str):
        c_clean = (current_style or "auto").strip().lower()
        for sid, sbtn in self.vstyle_buttons.items():
            is_act = (
                (sid == c_clean) or
                (sid == "auto" and c_clean in ("auto", "hybrid", "director")) or
                (sid == "spectrum" and c_clean in ("spectrum", "segmented", "segmented_vu", "staccato")) or
                (sid == "party" and c_clean in ("party", "club")) or
                (sid == "chill" and c_clean in ("chill", "lofi", "calm")) or
                (sid == "edm" and c_clean in ("edm", "drop", "edm_drop"))
            )
            if isinstance(sbtn, ctk.CTkButton):
                sbtn.configure(
                    fg_color=self.theme["accent"] if is_act else self.theme["surface_high"],
                    text_color="#ffffff" if is_act else self.theme["text_secondary"]
                )
            elif isinstance(sbtn, ctk.CTkFrame):
                sbtn.configure(
                    fg_color=self.theme["accent_soft"] if is_act else self.theme["surface_high"],
                    border_width=1 if is_act else 0,
                    border_color=self.theme["accent_glow"] if is_act else self.theme["border"]
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
        if "Album Art" in choice:
            mode = "album_art"
        elif "Fixed" in choice:
            mode = "fixed"
        else:
            mode = "auto"
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
        """Hide the desktop window without stopping the tray-resident app."""
        try:
            self.app.withdraw()
        except Exception:
            pass

    def show_window(self):
        """Pop the persistent desktop window out of the tray at a screen-aware size."""
        if not getattr(self, "_has_positioned", False):
            sw, sh = self.app.winfo_screenwidth(), self.app.winfo_screenheight()
            width, height, x, y, min_w, min_h = responsive_window_geometry(sw, sh)
            self.app.minsize(min_w, min_h)
            self.app.geometry(f"{width}x{height}+{x}+{y}")
            self._has_positioned = True
        self.app.deiconify()
        self.app.lift()
        try:
            self.app.focus_force()
        except Exception:
            pass
        self._on_window_configure()

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
        try:
            self.app.destroy()
        except Exception:
            pass