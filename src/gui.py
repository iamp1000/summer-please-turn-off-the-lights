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

# Keep the surfaces neutral and restrained across themes. Themes now change the
# accent family, not every background panel, which improves hierarchy and contrast.
for _palette in THEMES.values():
    _palette.update({
        "bg": "#0d1017",
        "surface": "#151923",
        "surface_raised": "#1c2230",
        "surface_high": "#252c3b",
        "border": "#30394a",
        "text_primary": "#f2f4f8",
        "text_secondary": "#b1bacb",
        "text_muted": "#7f8aa0",
    })

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
                    grid.columnconfigure(
                        col, weight=1 if col < columns else 0, minsize=0,
                        uniform=f"responsive_{id(grid)}" if col < columns else ""
                    )
                children = [child for child in grid.winfo_children() if str(child.winfo_manager()) == "grid"]
                for index, child in enumerate(children):
                    child.grid_configure(row=index // columns, column=index % columns, sticky="nsew")
            except Exception:
                continue

        # Collapse the rail to icon-only navigation on narrower windows.
        try:
            compact = self.app.winfo_width() < 980
            if compact != getattr(self, "_nav_compact", False):
                self._nav_compact = compact
                self.nav_rail.configure(width=68 if compact else 194)
                self.nav_eyebrow.configure(text="GO" if compact else "WORKSPACE", anchor="center" if compact else "w")
                self.nav_device_note.configure(
                    text=f"{len(self.hub.devices)}" if compact else f"{len(self.hub.devices)} device(s) configured\nLAN controls active",
                    anchor="center" if compact else "w", wraplength=42 if compact else 156
                )
                for page, button in self.nav_buttons.items():
                    glyph, label = self._nav_items[page]
                    button.configure(text=glyph if compact else f"{glyph}   {label}", anchor="center" if compact else "w")
        except Exception:
            pass

    def _build_ui(self):
        """Build the redesigned desktop workspace with clear, separate pages."""
        t = self.theme
        sw, sh = self.app.winfo_screenwidth(), self.app.winfo_screenheight()
        width = min(max(680, int(sw * 0.86)), max(680, sw - 24))
        height = min(max(620, int(sh * 0.88)), max(620, sh - 36))
        x, y = max(0, (sw - width) // 2), max(0, (sh - height) // 2)
        _, _, _, _, min_w, min_h = responsive_window_geometry(sw, sh)
        self.app.minsize(min_w, min_h)
        self.app.geometry(f"{width}x{height}+{x}+{y}")
        self._has_positioned = True
        self.app.configure(fg_color=t["bg"])

        self.buttons = {}
        self.tab_buttons = {}
        self.vstyle_buttons = {}
        self.accent_buttons = {}
        self.quick_level_buttons = {}
        self.card_frames = []
        self._responsive_grids = []
        self._resize_job = None

        self.root_frame = ctk.CTkFrame(self.app, fg_color=t["bg"], corner_radius=0)
        self.root_frame.pack(fill="both", expand=True)

        # Top bar: one restrained brand block and the two global actions.
        self.header = ctk.CTkFrame(self.root_frame, fg_color=t["bg"], corner_radius=0, height=78)
        self.header.pack(fill="x", padx=22, pady=(14, 10))
        self.header.grid_columnconfigure(1, weight=1)

        logo = ctk.CTkFrame(
            self.header, width=44, height=44, corner_radius=10,
            fg_color=t["surface_raised"], border_width=1, border_color=t["border"]
        )
        logo.grid(row=0, column=0, rowspan=2, padx=(0, 12), sticky="w")
        logo.grid_propagate(False)
        self.header_icon_lbl = ctk.CTkLabel(
            logo, text="✦", font=ctk.CTkFont(size=22, weight="bold"),
            text_color=t["accent_glow"]
        )
        self.header_icon_lbl.place(relx=0.5, rely=0.5, anchor="center")

        self.header_title = ctk.CTkLabel(
            self.header, text="Summer  /  Light Control",
            font=ctk.CTkFont(size=20, weight="bold"), text_color=t["text_primary"]
        )
        self.header_title.grid(row=0, column=1, sticky="w")
        status_line = ctk.CTkFrame(self.header, fg_color="transparent")
        status_line.grid(row=1, column=1, sticky="w", pady=(2, 0))
        self.header_status_dot = ctk.CTkLabel(
            status_line, text="●", font=ctk.CTkFont(size=10), text_color="#35d399"
        )
        self.header_status_dot.pack(side="left", padx=(0, 6))
        self.header_status_lbl = ctk.CTkLabel(
            status_line, text="Local control  ·  Ready",
            font=ctk.CTkFont(size=12), text_color=t["text_secondary"]
        )
        self.header_status_lbl.pack(side="left")

        actions = ctk.CTkFrame(self.header, fg_color="transparent")
        actions.grid(row=0, column=2, rowspan=2, sticky="e")
        self.btn_top_power = ctk.CTkButton(
            actions, text="⏻  Power", width=94, height=38, corner_radius=8,
            fg_color=t["accent_soft"], hover_color=t["accent"],
            border_width=1, border_color=t["accent"], text_color=t["text_primary"],
            font=ctk.CTkFont(size=12, weight="bold"), command=self._handle_power_click
        )
        self.btn_top_power.pack(side="left", padx=(0, 8))
        self.btn_hide = ctk.CTkButton(
            actions, text="Hide to tray", width=104, height=38, corner_radius=8,
            fg_color=t["surface_raised"], hover_color=t["surface_high"],
            border_width=1, border_color=t["border"], text_color=t["text_secondary"],
            font=ctk.CTkFont(size=12, weight="bold"), command=self.hide_window
        )
        self.btn_hide.pack(side="left")

        # Workspace is split into a stable navigation rail and a page viewport.
        self.workspace = ctk.CTkFrame(self.root_frame, fg_color="transparent")
        self.workspace.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        self.nav_rail = ctk.CTkFrame(
            self.workspace, width=194, fg_color=t["surface"],
            corner_radius=10, border_width=1, border_color=t["border"]
        )
        self.nav_rail.pack(side="left", fill="y", padx=(0, 12))
        self.nav_rail.pack_propagate(False)
        self.nav_eyebrow = ctk.CTkLabel(
            self.nav_rail, text="WORKSPACE", anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=t["text_muted"]
        )
        self.nav_eyebrow.pack(fill="x", padx=16, pady=(20, 12))

        self.nav_buttons = {}
        self._nav_items = {
            "overview": ("⌂", "Overview"),
            "music": ("♫", "Music reactive"),
            "effects": ("✦", "Effects"),
            "diagnostics": ("⌁", "Diagnostics"),
        }
        for page_key, (glyph, label) in self._nav_items.items():
            button = ctk.CTkButton(
                self.nav_rail, text=f"{glyph}   {label}", height=42,
                fg_color=t["accent_soft"] if page_key == "overview" else "transparent",
                hover_color=t["surface_high"], text_color=t["text_primary"] if page_key == "overview" else t["text_secondary"],
                border_width=1 if page_key == "overview" else 0,
                border_color=t["accent"] if page_key == "overview" else t["border"],
                corner_radius=8, anchor="w", font=ctk.CTkFont(size=13, weight="bold"),
                command=lambda p=page_key: self._switch_page(p)
            )
            button.pack(fill="x", padx=8, pady=3)
            self.nav_buttons[page_key] = button

        spacer = ctk.CTkFrame(self.nav_rail, fg_color="transparent", height=12)
        spacer.pack(fill="x", expand=True)
        ctk.CTkFrame(self.nav_rail, height=1, fg_color=t["border"]).pack(fill="x", padx=14, pady=(4, 12))
        ctk.CTkLabel(
            self.nav_rail, text="LOCAL FIRST", anchor="w",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=t["accent_glow"]
        ).pack(fill="x", padx=16, pady=(0, 4))
        self.nav_device_note = ctk.CTkLabel(
            self.nav_rail,
            text=f"{len(self.hub.devices)} device(s) configured\nLAN controls active",
            justify="left", anchor="w", wraplength=156,
            font=ctk.CTkFont(size=11), text_color=t["text_muted"]
        )
        self.nav_device_note.pack(fill="x", padx=16, pady=(0, 18))

        self.main_column = ctk.CTkFrame(self.workspace, fg_color="transparent")
        self.main_column.pack(side="left", fill="both", expand=True)

        # The device selector stays visible while navigating between pages.
        self.tabs_bar = ctk.CTkFrame(
            self.main_column, fg_color=t["surface"], corner_radius=8,
            border_width=1, border_color=t["border"]
        )
        self.tabs_bar.pack(fill="x", pady=(0, 10))
        tabs_inner = ctk.CTkFrame(self.tabs_bar, fg_color="transparent")
        tabs_inner.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(
            tabs_inner, text="CONTROL TARGET", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=t["text_muted"]
        ).pack(side="left", padx=(4, 12))
        target_buttons = ctk.CTkFrame(tabs_inner, fg_color="transparent")
        target_buttons.pack(side="left", fill="x", expand=True)
        target_items = []
        for dev_id, ctx in self.hub.devices.items():
            model = getattr(ctx, "model", "")
            label = f"{ctx.name}  ·  {model}" if model else ctx.name
            target_items.append((dev_id, label))
        target_items.append(("all", "Both strips"))
        for dev_id, title_text in target_items:
            selected = dev_id == self.current_dev_id
            btn = ctk.CTkButton(
                target_buttons, text=title_text, height=34,
                fg_color=t["accent_soft"] if selected else "transparent",
                hover_color=t["surface_high"],
                text_color=t["text_primary"] if selected else t["text_secondary"],
                border_width=1 if selected else 0,
                border_color=t["accent"] if selected else t["border"],
                font=ctk.CTkFont(size=12, weight="bold"), corner_radius=7,
                command=lambda d=dev_id: self._select_device_tab(d)
            )
            btn.pack(side="left", fill="x", expand=True, padx=3)
            self.tab_buttons[dev_id] = btn

        self.content_area = ctk.CTkFrame(self.main_column, fg_color="transparent")
        self.content_area.pack(fill="both", expand=True)
        scroll_kwargs = {
            "fg_color": "transparent",
            "scrollbar_button_color": t["surface_high"],
            "scrollbar_button_hover_color": t["accent"],
            "corner_radius": 0,
        }
        self.page_views = {
            key: ctk.CTkScrollableFrame(self.content_area, **scroll_kwargs)
            for key in ("overview", "music", "effects", "diagnostics")
        }

        def page_heading(page, eyebrow, title, description):
            heading = ctk.CTkFrame(page, fg_color="transparent")
            heading.pack(fill="x", padx=4, pady=(12, 16))
            ctk.CTkLabel(
                heading, text=eyebrow.upper(), anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"), text_color=t["accent_glow"]
            ).pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(
                heading, text=title, anchor="w",
                font=ctk.CTkFont(size=25, weight="bold"), text_color=t["text_primary"]
            ).pack(fill="x")
            ctk.CTkLabel(
                heading, text=description, anchor="w", wraplength=1000,
                font=ctk.CTkFont(size=13), text_color=t["text_secondary"]
            ).pack(fill="x", pady=(4, 0))

        def make_card(parent, background=None, hero=False):
            frame = ctk.CTkFrame(
                parent, fg_color=background or t["surface"], corner_radius=9,
                border_width=1, border_color=t["hero_border"] if hero else t["border"]
            )
            frame.pack(fill="x", padx=2, pady=(0, 12))
            self.card_frames.append(frame)
            return frame

        def card_heading(parent, title, subtitle=None):
            top = ctk.CTkFrame(parent, fg_color="transparent")
            top.pack(fill="x", padx=18, pady=(16, 12))
            ctk.CTkLabel(
                top, text=title, anchor="w",
                font=ctk.CTkFont(size=15, weight="bold"), text_color=t["text_primary"]
            ).pack(fill="x")
            if subtitle:
                ctk.CTkLabel(
                    top, text=subtitle, anchor="w", wraplength=1000,
                    font=ctk.CTkFont(size=12), text_color=t["text_muted"]
                ).pack(fill="x", pady=(3, 0))
            return top

        # ── OVERVIEW ────────────────────────────────────────────────────────
        overview = self.page_views["overview"]
        page_heading(
            overview, "At a glance", "Your lights, under control",
            "Choose a strip, set the room brightness, or jump into a saved scene."
        )

        self.hero_card = make_card(overview, background=t["hero_tint"], hero=True)
        hero_top = ctk.CTkFrame(self.hero_card, fg_color="transparent")
        hero_top.pack(fill="x", padx=20, pady=(18, 15))
        hero_top.grid_columnconfigure(0, weight=1)
        tag_row = ctk.CTkFrame(hero_top, fg_color="transparent")
        tag_row.grid(row=0, column=0, sticky="w", pady=(0, 7))
        self.hero_tag = ctk.CTkLabel(
            tag_row, text="L930", fg_color=t["surface_raised"], corner_radius=5,
            padx=9, pady=4, font=ctk.CTkFont(size=10, weight="bold"),
            text_color=t["accent_glow"]
        )
        self.hero_tag.pack(side="left")
        self.hero_title = ctk.CTkLabel(
            hero_top, text="Light strip", anchor="w",
            font=ctk.CTkFont(size=24, weight="bold"), text_color=t["text_primary"]
        )
        self.hero_title.grid(row=1, column=0, sticky="w")
        status_row = ctk.CTkFrame(hero_top, fg_color="transparent")
        status_row.grid(row=2, column=0, sticky="w", pady=(5, 0))
        self.hero_status_dot = ctk.CTkLabel(
            status_row, text="●", font=ctk.CTkFont(size=11), text_color="#35d399"
        )
        self.hero_status_dot.pack(side="left", padx=(0, 6))
        self.hero_status_lbl = ctk.CTkLabel(
            status_row, text="Active", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=t["text_secondary"]
        )
        self.hero_status_lbl.pack(side="left")
        self.btn_hero_power = ctk.CTkButton(
            hero_top, text="⏻", width=52, height=52, corner_radius=9,
            fg_color=t["accent_soft"], hover_color=t["accent"],
            border_width=1, border_color=t["accent"],
            font=ctk.CTkFont(size=23, weight="bold"), text_color=t["text_primary"],
            command=self._handle_power_click
        )
        self.btn_hero_power.grid(row=0, column=1, rowspan=3, sticky="e", padx=(16, 0))

        strip_box = ctk.CTkFrame(
            self.hero_card, fg_color="#10141d", corner_radius=7,
            border_width=1, border_color=t["border"]
        )
        strip_box.pack(fill="x", padx=18, pady=(0, 18))
        strip_header = ctk.CTkFrame(strip_box, fg_color="transparent")
        strip_header.pack(fill="x", padx=12, pady=(10, 6))
        self.lbl_strip_tag = ctk.CTkLabel(
            strip_header, text="LIVE STRIP PREVIEW", anchor="w",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=t["text_muted"]
        )
        self.lbl_strip_tag.pack(side="left")
        self.lbl_strip_stats = ctk.CTkLabel(
            strip_header, text="ZONE 01 — 50", anchor="e",
            font=ctk.CTkFont(size=10), text_color=t["accent_glow"]
        )
        self.lbl_strip_stats.pack(side="right")
        import tkinter as tk
        self.strip_canvas = tk.Canvas(
            strip_box, height=38, bg="#090b10", highlightthickness=0, bd=0
        )
        self.strip_canvas.pack(fill="x", padx=12, pady=(0, 12))
        self.strip_canvas.bind("<Motion>", self._on_strip_canvas_hover)
        self.strip_canvas.bind("<Leave>", self._on_strip_canvas_leave)
        self._last_rendered_segments = None

        self.bright_card = make_card(overview)
        brightness_header = ctk.CTkFrame(self.bright_card, fg_color="transparent")
        brightness_header.pack(fill="x", padx=18, pady=(16, 6))
        ctk.CTkLabel(
            brightness_header, text="Brightness", anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"), text_color=t["text_primary"]
        ).pack(side="left")
        self.bright_val_label = ctk.CTkLabel(
            brightness_header, text="50%", font=ctk.CTkFont(size=16, weight="bold"),
            text_color=t["accent_glow"]
        )
        self.bright_val_label.pack(side="right")
        brightness_slider_row = ctk.CTkFrame(self.bright_card, fg_color="transparent")
        brightness_slider_row.pack(fill="x", padx=18, pady=(0, 12))
        self.lbl_sun_dim = ctk.CTkLabel(
            brightness_slider_row, text="DIM", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=t["text_muted"]
        )
        self.lbl_sun_dim.pack(side="left", padx=(0, 10))
        self.bright_slider = ctk.CTkSlider(
            brightness_slider_row, from_=1, to=100, height=18,
            progress_color=t["accent"], button_color=t["accent_glow"],
            button_hover_color=t["accent"], fg_color=t["surface_high"],
            command=self._on_brightness_slide
        )
        self.bright_slider.set(50)
        self.bright_slider.pack(side="left", fill="x", expand=True)
        self.lbl_sun_bright = ctk.CTkLabel(
            brightness_slider_row, text="BRIGHT", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=t["text_muted"]
        )
        self.lbl_sun_bright.pack(side="left", padx=(10, 0))
        levels_row = ctk.CTkFrame(self.bright_card, fg_color="transparent")
        levels_row.pack(fill="x", padx=18, pady=(0, 16))
        for idx, level in enumerate((15, 40, 70, 100)):
            button = ctk.CTkButton(
                levels_row, text=f"{level}%", height=32, corner_radius=7,
                fg_color=t["surface_raised"], hover_color=t["surface_high"],
                text_color=t["text_secondary"], border_width=1, border_color=t["border"],
                font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda v=level: self._set_quick_brightness(v)
            )
            button.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else 6, 0))
            self.quick_level_buttons[level] = button

        self.preset_card = make_card(overview)
        card_heading(self.preset_card, "Saved scenes", "One click applies a static scene to the selected strip.")
        presets_grid = ctk.CTkFrame(self.preset_card, fg_color="transparent")
        presets_grid.pack(fill="x", padx=14, pady=(0, 16))
        self._register_responsive_grid(presets_grid)
        for col in range(3):
            presets_grid.columnconfigure(col, weight=1, uniform="scenes")
        modes_list = list(self.hub.config.get("modes", {}).keys()) or [
            "work", "deep_focus", "coding_night", "reading", "sunset", "dinner", "movie", "sleep"
        ]
        for idx, name in enumerate(modes_list):
            row, col = divmod(idx, 3)
            label = name.replace("_", " ").title()
            button = self._make_item_button(
                presets_grid, label, MODE_COLORS.get(name, t["accent"]),
                lambda n=name: self._apply_mode(n)
            )
            button.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            self.buttons[f"mode_{name}"] = button

        self.btn_picker = ctk.CTkButton(
            overview, text="＋   Open colour studio", height=44, corner_radius=8,
            fg_color=t["surface_raised"], hover_color=t["surface_high"],
            border_width=1, border_color=t["border"], text_color=t["text_primary"],
            font=ctk.CTkFont(size=13, weight="bold"), command=self._show_picker
        )
        self.btn_picker.pack(fill="x", padx=2, pady=(0, 16))

        # ── MUSIC REACTIVE ──────────────────────────────────────────────────
        music = self.page_views["music"]
        page_heading(
            music, "Live performance", "Make the lights listen",
            "Audio and screen analysis, reactive looks, sensitivity and timing controls."
        )

        self.sync_card = make_card(music)
        card_heading(self.sync_card, "Live inputs", "Choose one reactive source at a time, or switch between them as needed.")
        sync_body = ctk.CTkFrame(self.sync_card, fg_color="transparent")
        sync_body.pack(fill="x", padx=16, pady=(0, 16))
        sync_body.grid_columnconfigure((0, 1), weight=1, uniform="sync")
        self.btn_music = ctk.CTkButton(
            sync_body, text="♫  AUDIO REACTIVE\nFollow bass, mids, highs and rhythm",
            height=64, corner_radius=8, fg_color=t["surface_raised"],
            hover_color=t["surface_high"], border_width=1, border_color=t["border"],
            text_color=t["text_primary"], font=ctk.CTkFont(size=13, weight="bold"),
            command=self._handle_music_toggle
        )
        self.btn_music.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 12))
        self.btn_scr = ctk.CTkButton(
            sync_body, text="▣  SCREEN SYNC\nTrack the dominant colours on screen",
            height=64, corner_radius=8, fg_color=t["surface_raised"],
            hover_color=t["surface_high"], border_width=1, border_color=t["border"],
            text_color=t["text_primary"], font=ctk.CTkFont(size=13, weight="bold"),
            command=self._handle_screen_toggle
        )
        self.btn_scr.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 12))

        source_row = ctk.CTkFrame(sync_body, fg_color="transparent")
        source_row.grid(row=1, column=0, columnspan=2, sticky="ew")
        source_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            source_row, text="Audio input", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_secondary"]
        ).grid(row=0, column=0, padx=(0, 14), sticky="w")
        audio_devices = self.hub.get_audio_devices()
        audio_names = [d["name"] for d in audio_devices] or ["Auto-Detect Active Audio"]
        current_audio = self.hub.audio_device
        self.audio_opt = ctk.CTkOptionMenu(
            source_row, values=audio_names, command=self._on_audio_device_selected,
            fg_color=t["surface_raised"], button_color=t["surface_high"],
            dropdown_fg_color=t["surface_raised"], text_color=t["text_primary"],
            height=34, corner_radius=7, font=ctk.CTkFont(size=12)
        )
        if current_audio in audio_names:
            self.audio_opt.set(current_audio)
        self.audio_opt.grid(row=0, column=1, sticky="ew")

        self.vstyles_frame = ctk.CTkFrame(
            music, fg_color=t["surface"], corner_radius=9,
            border_width=1, border_color=t["border"]
        )
        self.vstyles_frame.pack(fill="x", padx=2, pady=(0, 12))
        vstyles_inner = ctk.CTkFrame(self.vstyles_frame, fg_color="transparent")
        vstyles_inner.pack(fill="x", padx=16, pady=16)
        vstyles_header = ctk.CTkFrame(vstyles_inner, fg_color="transparent")
        vstyles_header.pack(fill="x", pady=(0, 12))
        header_left = ctk.CTkFrame(vstyles_header, fg_color="transparent")
        header_left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            header_left, text="Visual style", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=t["text_primary"]
        ).pack(fill="x")
        ctk.CTkLabel(
            header_left, text="Pick the way the strip responds to the track.",
            anchor="w", font=ctk.CTkFont(size=12), text_color=t["text_muted"]
        ).pack(fill="x", pady=(3, 0))
        self.gui_section_badge = ctk.CTkLabel(
            vstyles_header, text="WAITING", corner_radius=6,
            fg_color=t["surface_high"], text_color=t["accent_glow"],
            padx=9, pady=5, font=ctk.CTkFont(size=11, weight="bold")
        )
        self.gui_section_badge.pack(side="right", padx=(10, 0))
        self.gui_key_pill = ctk.CTkLabel(
            vstyles_header, text="Key —", corner_radius=6,
            fg_color=t["surface_high"], text_color=t["text_secondary"],
            padx=9, pady=5, font=ctk.CTkFont(size=11, weight="bold")
        )
        self.gui_key_pill.pack(side="right", padx=(0, 8))
        self.gui_bpm_lbl = ctk.CTkLabel(
            vstyles_inner, text="Inactive", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_muted"]
        )
        self.gui_bpm_lbl.pack(fill="x", pady=(0, 8))

        self.audio_monitor_frame = ctk.CTkFrame(
            vstyles_inner, fg_color=t["surface_raised"], corner_radius=7,
            border_width=1, border_color=t["border"]
        )
        self.audio_monitor_frame.pack(fill="x", pady=(0, 14))
        monitor_inner = ctk.CTkFrame(self.audio_monitor_frame, fg_color="transparent")
        monitor_inner.pack(fill="x", padx=12, pady=12)
        monitor_header = ctk.CTkFrame(monitor_inner, fg_color="transparent")
        monitor_header.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            monitor_header, text="LIVE SIGNAL", font=ctk.CTkFont(size=10, weight="bold"),
            text_color=t["text_muted"]
        ).pack(side="left")
        self.lbl_mon_meta = ctk.CTkLabel(
            monitor_header, text="BPM: —  ·  Floor: —  ·  Tx: 0 FPS",
            font=ctk.CTkFont(size=10), text_color=t["text_secondary"]
        )
        self.lbl_mon_meta.pack(side="right")
        self.spectrum_canvas = tk.Canvas(
            monitor_inner, height=104, bg="#0c1119", highlightthickness=0, bd=0
        )
        self.spectrum_canvas.pack(fill="x", pady=(0, 10))

        meters_row = ctk.CTkFrame(monitor_inner, fg_color="transparent")
        meters_row.pack(fill="x")
        meters_row.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="meters")
        for index, (key, label, color) in enumerate((
            ("onset", "ONSET", "#60a5fa"),
            ("kick", "KICK", "#a78bfa"),
            ("snare", "SNARE", "#fb7185"),
            ("hat", "HI-HAT", "#34d399"),
        )):
            cell = ctk.CTkFrame(meters_row, fg_color="transparent")
            cell.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 10, 0))
            top = ctk.CTkFrame(cell, fg_color="transparent")
            top.pack(fill="x", pady=(0, 5))
            ctk.CTkLabel(
                top, text=label, font=ctk.CTkFont(size=10, weight="bold"),
                text_color=t["text_muted"]
            ).pack(side="left")
            value_label = ctk.CTkLabel(
                top, text="0.00", font=ctk.CTkFont(size=11, weight="bold"),
                text_color=t["text_primary"]
            )
            value_label.pack(side="right")
            meter = ctk.CTkProgressBar(
                cell, height=8, corner_radius=4, fg_color=t["surface_high"], progress_color=color
            )
            meter.set(0)
            meter.pack(fill="x")
            setattr(self, f"lbl_meter_{key}", value_label)
            setattr(self, f"bar_meter_{key}", meter)

        self.btn_auto_mode = ctk.CTkButton(
            vstyles_inner, text="✦   Auto Director   ·   Let the music choose",
            height=44, corner_radius=8, fg_color=t["accent"],
            hover_color=t["accent_soft"], text_color="#ffffff",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._set_visual_style("auto")
        )
        self.btn_auto_mode.pack(fill="x", pady=(0, 10))
        self.vstyle_buttons["auto"] = self.btn_auto_mode

        styles_grid = ctk.CTkFrame(vstyles_inner, fg_color="transparent")
        styles_grid.pack(fill="x", pady=(0, 12))
        self._register_responsive_grid(styles_grid)
        for col in range(3):
            styles_grid.columnconfigure(col, weight=1, uniform="visual-styles")
        style_items = [
            ("party", "✹  Party", "High energy"),
            ("chill", "◌  Chill", "Slow, soft movement"),
            ("edm", "ϟ  EDM", "Bass-led impact"),
            ("movie", "▣  Movie", "Cinematic ambience"),
            ("pulse", "ϟ  Pulse", "Kick ripples"),
            ("spectrum", "▥  Spectrum", "Frequency display"),
            ("flow", "≈  Flow", "Organic colour motion"),
            ("bass_bounce", "↔  Bounce", "Sub-bass movement"),
            ("center_burst", "✺  Burst", "Outward waves"),
            ("twinkle", "✧  Twinkle", "Subtle high-end sparkle"),
        ]
        for index, (style_id, title, description) in enumerate(style_items):
            row, col = divmod(index, 3)
            style_button = ctk.CTkButton(
                styles_grid, text=f"{title}\n{description}", anchor="w",
                height=62, corner_radius=7, fg_color=t["surface_high"],
                hover_color=t["accent_soft"], border_width=1, border_color=t["border"],
                text_color=t["text_secondary"], font=ctk.CTkFont(size=12, weight="bold"),
                command=lambda name=style_id: self._set_visual_style(name)
            )
            style_button.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            self.vstyle_buttons[style_id] = style_button

        eq_row = ctk.CTkFrame(vstyles_inner, fg_color="transparent")
        eq_row.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            eq_row, text="Spectrum layout", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=t["text_secondary"]
        ).pack(side="left")
        self.opt_eq_layout = ctk.CTkSegmentedButton(
            eq_row, values=["Mirrored 50-Band", "Segmented Staccato VU"],
            command=self._on_eq_layout_change, height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            selected_color=t["accent"], selected_hover_color=t["accent_soft"]
        )
        self.opt_eq_layout.set("Mirrored 50-Band")
        self.opt_eq_layout.pack(side="right")

        tuning_card = make_card(music)
        card_heading(tuning_card, "Response tuning", "Adjust how strongly the signal moves the lights and how bright effects can get.")
        tuning_inner = ctk.CTkFrame(tuning_card, fg_color="transparent")
        tuning_inner.pack(fill="x", padx=18, pady=(0, 16))
        tuning_inner.grid_columnconfigure((0, 1), weight=1, uniform="tuning")
        sensitivity_box = ctk.CTkFrame(tuning_inner, fg_color="transparent")
        sensitivity_box.grid(row=0, column=0, sticky="ew", padx=(0, 12), pady=(0, 12))
        sensitivity_header = ctk.CTkFrame(sensitivity_box, fg_color="transparent")
        sensitivity_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            sensitivity_header, text="Sensitivity", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=t["text_secondary"]
        ).pack(side="left")
        self.lbl_sens_val = ctk.CTkLabel(
            sensitivity_header, text="1.0×", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=t["accent_glow"]
        )
        self.lbl_sens_val.pack(side="right")
        self.gui_sens_slider = ctk.CTkSlider(
            sensitivity_box, from_=0.2, to=3.0, number_of_steps=28, height=16,
            command=self._on_audio_sensitivity_change, fg_color=t["surface_high"],
            progress_color=t["accent"], button_color=t["accent_glow"], button_hover_color=t["accent"]
        )
        self.gui_sens_slider.set(1.0)
        self.gui_sens_slider.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            sensitivity_box, text="Lower = subtle  ·  Higher = more reactive",
            font=ctk.CTkFont(size=11), text_color=t["text_muted"]
        ).pack(anchor="w")

        cap_box = ctk.CTkFrame(tuning_inner, fg_color="transparent")
        cap_box.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=(0, 12))
        cap_header = ctk.CTkFrame(cap_box, fg_color="transparent")
        cap_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            cap_header, text="Brightness cap", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=t["text_secondary"]
        ).pack(side="left")
        self.lbl_bright_cap_val = ctk.CTkLabel(
            cap_header, text="100%", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=t["accent_glow"]
        )
        self.lbl_bright_cap_val.pack(side="right")
        self.slider_bright_cap = ctk.CTkSlider(
            cap_box, from_=30, to=100, number_of_steps=70, height=16,
            command=self._on_bright_cap_slide, fg_color=t["surface_high"],
            progress_color=t["accent"], button_color=t["accent_glow"], button_hover_color=t["accent"]
        )
        self.slider_bright_cap.set(100)
        self.slider_bright_cap.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            cap_box, text="A ceiling for audio-reactive brightness",
            font=ctk.CTkFont(size=11), text_color=t["text_muted"]
        ).pack(anchor="w")

        palette_row = ctk.CTkFrame(tuning_inner, fg_color="transparent")
        palette_row.grid(row=1, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(
            palette_row, text="Palette source", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=t["text_secondary"]
        ).pack(side="left")
        self.palette_mode_opt = ctk.CTkOptionMenu(
            palette_row, values=["Auto (Key/Chroma)", "Album Art (Windows Media)", "Fixed (Current)"],
            command=self._on_palette_mode_selected, fg_color=t["surface_raised"],
            button_color=t["surface_high"], text_color=t["text_primary"],
            height=34, corner_radius=7, font=ctk.CTkFont(size=12)
        )
        self.palette_mode_opt.set("Auto (Key/Chroma)")
        self.palette_mode_opt.pack(side="right")

        latency_card = make_card(music)
        card_heading(latency_card, "Timing & calibration", "A little lookahead can compensate for output delay.")
        latency_inner = ctk.CTkFrame(latency_card, fg_color="transparent")
        latency_inner.pack(fill="x", padx=18, pady=(0, 16))
        latency_header = ctk.CTkFrame(latency_inner, fg_color="transparent")
        latency_header.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            latency_header, text="Latency lookahead", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=t["text_secondary"]
        ).pack(side="left")
        self.lbl_lookahead_val = ctk.CTkLabel(
            latency_header, text="0 ms", font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#34d399"
        )
        self.lbl_lookahead_val.pack(side="left", padx=(8, 0))
        self.lbl_transition_val = ctk.CTkLabel(
            latency_header, text="Transition: 0 ms", font=ctk.CTkFont(size=11),
            text_color=t["text_muted"]
        )
        self.lbl_transition_val.pack(side="left", padx=(12, 0))
        self.btn_click_test = ctk.CTkButton(
            latency_header, text="Run click test", width=120, height=32,
            fg_color=t["surface_raised"], hover_color=t["surface_high"],
            text_color=t["text_primary"], font=ctk.CTkFont(size=11, weight="bold"),
            border_width=1, border_color=t["border"], corner_radius=7,
            command=self._toggle_click_test
        )
        self.btn_click_test.pack(side="right")
        self.lbl_measured_delay = ctk.CTkLabel(
            latency_inner, text="Measured light delay: — ms",
            font=ctk.CTkFont(size=11), text_color=t["text_muted"], anchor="w"
        )
        self.lbl_measured_delay.pack(fill="x", pady=(0, 8))
        self.gui_lookahead_slider = ctk.CTkSlider(
            latency_inner, from_=0, to=250, number_of_steps=50, height=16,
            command=self._on_lookahead_slide, fg_color=t["surface_high"],
            progress_color="#34d399", button_color="#6ee7b7"
        )
        self.gui_lookahead_slider.set(0)
        self.gui_lookahead_slider.pack(fill="x")
        self.btn_tap_sync = ctk.CTkButton(
            latency_inner, text="Tap 4 beats to calibrate", height=34, corner_radius=7,
            fg_color=t["surface_raised"], hover_color=t["surface_high"],
            border_width=1, border_color=t["border"], text_color=t["text_secondary"],
            font=ctk.CTkFont(size=11, weight="bold"), command=self._handle_tap_sync
        )
        self.btn_tap_sync.pack(anchor="e", pady=(10, 0))

        accents_row = ctk.CTkFrame(latency_inner, fg_color="transparent")
        accents_row.pack(fill="x", pady=(14, 0))
        accent_names = [
            ("beat_flash", "Beat accents"),
            ("hat_sparkle", "Hi-hat sparkle"),
            ("build_tension", "Build tension"),
            ("drop_bloom", "Drop bloom"),
        ]
        self.accent_states = getattr(self, "accent_states", {
            "beat_flash": True, "hat_sparkle": True, "build_tension": True, "drop_bloom": True
        })
        for index, (accent_id, label) in enumerate(accent_names):
            accent_button = ctk.CTkButton(
                accents_row, text=label, height=32, corner_radius=7,
                fg_color=t["accent_soft"], hover_color=t["surface_high"],
                border_width=1, border_color=t["border"], text_color=t["text_primary"],
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda name=accent_id: self._toggle_accent(name)
            )
            accent_button.pack(side="left", fill="x", expand=True, padx=(0 if index == 0 else 6, 0))
            self.accent_buttons[accent_id] = accent_button

        # ── EFFECTS ─────────────────────────────────────────────────────────
        effects = self.page_views["effects"]
        page_heading(
            effects, "Atmosphere library", "Give the room a different texture",
            "Original animated fields for the L930 and gentle ambient looks for the L900."
        )
        self.fx_card = make_card(effects)
        self.fx_header_label = ctk.CTkLabel(
            self.fx_card, text="EFFECTS", anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=t["text_primary"]
        )
        self.fx_header_label.pack(fill="x", padx=18, pady=(16, 4))
        self.fx_grid_frame = ctk.CTkFrame(self.fx_card, fg_color="transparent")
        self.fx_grid_frame.pack(fill="x", padx=12, pady=(8, 16))
        self._render_effects_list()

        # ── DIAGNOSTICS ─────────────────────────────────────────────────────
        diagnostics = self.page_views["diagnostics"]
        page_heading(
            diagnostics, "System health", "Performance & connection",
            "Watch network timing and frame delivery without crowding the lighting controls."
        )
        self.diag_card = make_card(diagnostics)
        diag_top = ctk.CTkFrame(self.diag_card, fg_color="transparent")
        diag_top.pack(fill="x", padx=18, pady=(18, 12))
        ctk.CTkLabel(
            diag_top, text="Transport telemetry", font=ctk.CTkFont(size=16, weight="bold"),
            text_color=t["text_primary"]
        ).pack(side="left")
        self.gui_diag_status = ctk.CTkLabel(
            diag_top, text="● Connecting", font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#fbbf24"
        )
        self.gui_diag_status.pack(side="right")

        metrics_row = ctk.CTkFrame(self.diag_card, fg_color="transparent")
        metrics_row.pack(fill="x", padx=14, pady=(0, 16))
        metrics_row.grid_columnconfigure((0, 1, 2), weight=1, uniform="metrics")
        metric_specs = [
            ("send", "SEND RATE", "--", "#34d399"),
            ("rtt", "ROUND-TRIP", "-- ms", t["accent_glow"]),
            ("drop", "FRAME DROPS", "--%", "#fbbf24"),
        ]
        for index, (key, label, initial, color) in enumerate(metric_specs):
            metric = ctk.CTkFrame(
                metrics_row, fg_color=t["surface_raised"], corner_radius=8,
                border_width=1, border_color=t["border"]
            )
            metric.grid(row=0, column=index, sticky="nsew", padx=4)
            ctk.CTkLabel(
                metric, text=label, font=ctk.CTkFont(size=10, weight="bold"),
                text_color=t["text_muted"]
            ).pack(anchor="w", padx=14, pady=(14, 5))
            value = ctk.CTkLabel(
                metric, text=initial, font=ctk.CTkFont(size=24, weight="bold"),
                text_color=color
            )
            value.pack(anchor="w", padx=14)
            if key == "send":
                self.gui_fps_val = value
                self.gui_render_val = ctk.CTkLabel(
                    metric, text="Render: — calc", font=ctk.CTkFont(size=11),
                    text_color=t["text_secondary"]
                )
                self.gui_render_val.pack(anchor="w", padx=14, pady=(4, 14))
            elif key == "rtt":
                self.gui_rtt_val = value
                self.gui_pacing_val = ctk.CTkLabel(
                    metric, text="Total: — ms", font=ctk.CTkFont(size=11),
                    text_color=t["text_secondary"]
                )
                self.gui_pacing_val.pack(anchor="w", padx=14, pady=(4, 14))
            else:
                self.gui_drop_val = value
                ctk.CTkLabel(
                    metric, text="Lower is better", font=ctk.CTkFont(size=11),
                    text_color=t["text_secondary"]
                ).pack(anchor="w", padx=14, pady=(4, 14))

        details = make_card(diagnostics)
        card_heading(details, "Connection notes")
        info = ctk.CTkFrame(details, fg_color="transparent")
        info.pack(fill="x", padx=18, pady=(0, 18))
        for label, value in (
            ("Control path", "Local network  ·  no per-frame cloud round trip"),
            ("Web dashboard", f"http://{self.local_ip}:{self.hub.config.get('web', {}).get('port', 8765)}"),
            ("Configured devices", ", ".join(getattr(ctx, "name", key) for key, ctx in self.hub.devices.items()) or "None"),
        ):
            row = ctk.CTkFrame(info, fg_color="transparent")
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(
                row, text=label, width=150, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_muted"]
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=value, anchor="w", wraplength=760,
                font=ctk.CTkFont(size=12), text_color=t["text_secondary"]
            ).pack(side="left", fill="x", expand=True)

        # Persistent status bar along the bottom edge.
        self.status_bar = ctk.CTkFrame(self.root_frame, height=32, fg_color=t["surface"], corner_radius=0)
        self.status_bar.pack(fill="x", side="bottom")
        port = self.hub.config.get("web", {}).get("port", 8765)
        web_url = f"http://{self.local_ip}:{port}"
        self._bar_dev = ctk.CTkLabel(
            self.status_bar, text=f"  Summer Light Hub  ·  Phone dashboard: {web_url}",
            font=ctk.CTkFont(size=10), text_color=t["text_muted"], anchor="w"
        )
        self._bar_dev.pack(side="left", padx=10)
        self._bar_diag = ctk.CTkLabel(
            self.status_bar, text="TX  — FPS  ·  — ms  ·  —% drop",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="#34d399", anchor="e"
        )
        self._bar_diag.pack(side="right", padx=10)

        self._switch_page("overview")
        self._sync_view_to_device()
        self._bind_mousewheel_recursive(self.scroll_body)
        self.app.after(900, self._periodic_telemetry_tick)
        self.app.after(120, self._periodic_strip_preview_tick)

    def _switch_page(self, page_name: str):
        """Switch the visible workspace page without rebuilding its controls."""
        if page_name not in getattr(self, "page_views", {}):
            return
        for page in self.page_views.values():
            try:
                page.pack_forget()
            except Exception:
                pass
        self.scroll_body = self.page_views[page_name]
        self.scroll_body.pack(fill="both", expand=True)
        self.active_page = page_name
        for key, button in getattr(self, "nav_buttons", {}).items():
            selected = key == page_name
            try:
                button.configure(
                    fg_color=self.theme["accent_soft"] if selected else "transparent",
                    text_color=self.theme["text_primary"] if selected else self.theme["text_secondary"],
                    border_width=1 if selected else 0,
                    border_color=self.theme["accent"] if selected else self.theme["border"]
                )
            except Exception:
                pass
        self._bind_mousewheel_recursive(self.scroll_body)

    def _make_item_button(self, parent, label: str, dot_color: str, cmd):
        t = self.theme
        frame = ctk.CTkFrame(
            parent, fg_color=t["surface_raised"],
            border_width=1, border_color=t["border"],
            corner_radius=8, cursor="hand2"
        )
        frame.bind("<Button-1>", lambda e: cmd())

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=12, pady=10)
        inner.bind("<Button-1>", lambda e: cmd())

        dot = ctk.CTkLabel(inner, text="●", font=ctk.CTkFont(size=10), text_color=dot_color)
        dot.pack(side="left", padx=(0, 6))
        dot.bind("<Button-1>", lambda e: cmd())

        lbl = ctk.CTkLabel(inner, text=label, font=ctk.CTkFont(size=13, weight="bold"), text_color=t["text_primary"])
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
        ctk.CTkLabel(sp_hdr, text="⚡ Speed:", font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_speed = ctk.CTkLabel(sp_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_speed.pack(side="right")
        self.slider_fx_speed = ctk.CTkSlider(
            sp_box, from_=0.2, to=3.0, number_of_steps=28,
            command=self._on_fx_speed_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=14
        )
        self.slider_fx_speed.set(1.0)
        self.slider_fx_speed.pack(fill="x", pady=(1, 0))

        # Palette
        pal_box = ctk.CTkFrame(sb_row, fg_color="transparent")
        pal_box.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        pal_hdr = ctk.CTkFrame(pal_box, fg_color="transparent")
        pal_hdr.pack(fill="x")
        ctk.CTkLabel(pal_hdr, text="🎨 Palette:", font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        pal_names = ["sunset", "forest", "fire", "pastel", "tide", "dusk", "ember", "warm_mono"]
        self.opt_fx_pal = ctk.CTkOptionMenu(
            pal_box, values=pal_names,
            command=self._on_fx_palette_selected,
            fg_color=t["surface_high"], button_color=t["surface_raised"],
            text_color=t["text_primary"], height=30, corner_radius=6,
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
        ctk.CTkLabel(tail_hdr, text="☄ Tail Length:", font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_tail = ctk.CTkLabel(tail_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_tail.pack(side="right")
        self.slider_fx_tail = ctk.CTkSlider(
            self.box_fx_tail, from_=0.3, to=3.0, number_of_steps=27,
            command=self._on_fx_tail_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=14
        )
        self.slider_fx_tail.set(1.0)
        self.slider_fx_tail.pack(fill="x", pady=(1, 0))

        # 2. Particle Density Slider Box
        self.box_fx_density = ctk.CTkFrame(self.fx_specific_frame, fg_color="transparent")
        dens_hdr = ctk.CTkFrame(self.box_fx_density, fg_color="transparent")
        dens_hdr.pack(fill="x")
        ctk.CTkLabel(dens_hdr, text="✨ Density:", font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_density = ctk.CTkLabel(dens_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_density.pack(side="right")
        self.slider_fx_density = ctk.CTkSlider(
            self.box_fx_density, from_=0.2, to=3.0, number_of_steps=28,
            command=self._on_fx_density_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=14
        )
        self.slider_fx_density.set(1.0)
        self.slider_fx_density.pack(fill="x", pady=(1, 0))

        # 3. Wave Width Slider Box
        self.box_fx_width = ctk.CTkFrame(self.fx_specific_frame, fg_color="transparent")
        width_hdr = ctk.CTkFrame(self.box_fx_width, fg_color="transparent")
        width_hdr.pack(fill="x")
        ctk.CTkLabel(width_hdr, text="🌊 Wave Width:", font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_width = ctk.CTkLabel(width_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_width.pack(side="right")
        self.slider_fx_width = ctk.CTkSlider(
            self.box_fx_width, from_=0.3, to=3.0, number_of_steps=27,
            command=self._on_fx_width_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=14
        )
        self.slider_fx_width.set(1.0)
        self.slider_fx_width.pack(fill="x", pady=(1, 0))

        # 4. Flash Strength Slider Box
        self.box_fx_flash = ctk.CTkFrame(self.fx_specific_frame, fg_color="transparent")
        flash_hdr = ctk.CTkFrame(self.box_fx_flash, fg_color="transparent")
        flash_hdr.pack(fill="x")
        ctk.CTkLabel(flash_hdr, text="⚡ Flash Pwr:", font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text_muted"]).pack(side="left")
        self.lbl_fx_flash = ctk.CTkLabel(flash_hdr, text="1.0x", font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=t["accent_glow"])
        self.lbl_fx_flash.pack(side="right")
        self.slider_fx_flash = ctk.CTkSlider(
            self.box_fx_flash, from_=0.2, to=2.5, number_of_steps=23,
            command=self._on_fx_flash_slide,
            fg_color=t["surface_high"], progress_color=t["accent"],
            button_color=t["accent_glow"], height=14
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

            # Curated shelf: original atmospheric fields plus a few spatial experiments.
            # Stock Tapo modes, aliases, repetitive chases and flashing novelties stay hidden.
            creative_names = (
                "oil_slick", "silk_ribbons", "nebula_bloom",
                "holographic_moire", "ember_drift",
            )
            spatial_names = (
                "spiral_vortex", "gravity_slosh", "lissajous_orbit",
                "planar_wind", "vaporwave_neon",
            )
            groups = {
                "Creative Original Designs": [name for name in creative_names if name in catalog],
                "Spatial Experiments": [name for name in spatial_names if name in catalog],
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
                    font=ctk.CTkFont(size=11, weight="bold"),
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
                grp_target = (
                    "Creative Original Designs"
                    if name in {"oil_slick", "silk_ribbons", "nebula_bloom", "holographic_moire", "ember_drift"}
                    else "Spatial Experiments"
                    if name in {"spiral_vortex", "gravity_slosh", "lissajous_orbit", "planar_wind", "vaporwave_neon"}
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
        """Update accent colours without repainting the entire UI as one glow."""
        if theme_key not in THEMES or theme_key == self.current_theme_key:
            return
        self.current_theme_key = theme_key
        self.theme = THEMES[theme_key]
        t = self.theme

        for name in ("app",):
            widget = getattr(self, name, None)
            if widget:
                try:
                    widget.configure(fg_color=t["bg"])
                except Exception:
                    pass
        for name in ("root_frame", "header"):
            widget = getattr(self, name, None)
            if widget:
                try:
                    widget.configure(fg_color=t["bg"])
                except Exception:
                    pass
        for name in ("nav_rail", "tabs_bar", "bright_card", "sync_card", "fx_card", "preset_card", "diag_card", "status_bar", "vstyles_frame"):
            widget = getattr(self, name, None)
            if widget:
                try:
                    widget.configure(fg_color=t["surface"], border_color=t["border"])
                except Exception:
                    try:
                        widget.configure(fg_color=t["surface"])
                    except Exception:
                        pass
        for name in ("hero_card",):
            widget = getattr(self, name, None)
            if widget:
                try:
                    widget.configure(fg_color=t["hero_tint"], border_color=t["hero_border"])
                except Exception:
                    pass
        for name in ("btn_top_power", "btn_hero_power"):
            widget = getattr(self, name, None)
            if widget:
                try:
                    widget.configure(fg_color=t["accent_soft"], border_color=t["accent"])
                except Exception:
                    pass
        for name in ("bright_slider", "gui_sens_slider", "slider_bright_cap", "gui_lookahead_slider"):
            widget = getattr(self, name, None)
            if widget:
                try:
                    widget.configure(
                        fg_color=t["surface_high"], progress_color=t["accent"],
                        button_color=t["accent_glow"], button_hover_color=t["accent"]
                    )
                except Exception:
                    pass
        for name in ("bright_val_label", "hero_tag", "gui_key_pill", "lbl_sens_val", "lbl_bright_cap_val"):
            widget = getattr(self, name, None)
            if widget:
                try:
                    widget.configure(text_color=t["accent_glow"])
                except Exception:
                    pass
        for key, button in getattr(self, "nav_buttons", {}).items():
            try:
                selected = key == getattr(self, "active_page", "overview")
                button.configure(
                    fg_color=t["accent_soft"] if selected else "transparent",
                    text_color=t["text_primary"] if selected else t["text_secondary"],
                    border_width=1 if selected else 0,
                    border_color=t["accent"] if selected else t["border"]
                )
            except Exception:
                pass
        for key, button in getattr(self, "tab_buttons", {}).items():
            try:
                selected = key == self.current_dev_id
                button.configure(
                    fg_color=t["accent_soft"] if selected else "transparent",
                    text_color=t["text_primary"] if selected else t["text_secondary"],
                    border_width=1 if selected else 0,
                    border_color=t["accent"] if selected else t["border"]
                )
            except Exception:
                pass
        for widget in getattr(self, "card_frames", []):
            try:
                if widget is self.hero_card:
                    widget.configure(fg_color=t["hero_tint"], border_color=t["hero_border"])
                else:
                    widget.configure(border_color=t["border"])
            except Exception:
                pass

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
        if self.active_picker:
            return
        try:
            self.content_area.pack_forget()
        except Exception:
            pass
        self.active_picker = ModernColorPicker(
            self.main_column, on_apply=self._handle_picker_apply, on_cancel=self._hide_picker
        )
        self.active_picker.pack(fill="both", expand=True, padx=2, pady=(0, 2))

    def _handle_picker_apply(self, h, s, v):
        self.hub.apply_custom_color(self.current_dev_id, h, s, v)
        self._hide_picker()

    def _hide_picker(self):
        if self.active_picker:
            self.active_picker.pack_forget()
            self.active_picker.destroy()
            self.active_picker = None
        try:
            self.content_area.pack(fill="both", expand=True)
        except Exception:
            pass

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