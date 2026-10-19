from __future__ import annotations

import colorsys
import math
import numpy as np
import customtkinter as ctk
from PIL import Image, ImageTk


def _hsv_array_to_rgb(H: np.ndarray, S: np.ndarray, V: np.ndarray) -> np.ndarray:
    """Vectorized HSV to RGB conversion."""
    i = (H * 6.0).astype(int)
    f = H * 6.0 - i
    p = V * (1.0 - S)
    q = V * (1.0 - f * S)
    t = V * (1.0 - (1.0 - f) * S)
    i = i % 6
    r = np.select([i==0, i==1, i==2, i==3, i==4, i==5], [V, q, p, p, t, V], default=V)
    g = np.select([i==0, i==1, i==2, i==3, i==4, i==5], [t, V, V, q, p, p], default=V)
    b = np.select([i==0, i==1, i==2, i==3, i==4, i==5], [p, p, t, V, V, q], default=V)
    return np.stack([r, g, b], axis=-1).astype(np.float32)


class ModernColorPicker(ctk.CTkFrame):
    def __init__(self, master=None, on_apply=None, on_cancel=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_apply_cb = on_apply
        self.on_cancel_cb = on_cancel

        self.hue = 0.0          # 0.0 - 1.0
        self.sat = 1.0          # 0.0 - 1.0
        self.val = 0.8          # 0.0 - 1.0
        self.current_style = "Wheel"

        self.preset_swatches = [
            ("#FF3B30", 0, 100),
            ("#FF9500", 35, 100),
            ("#FFCC00", 48, 100),
            ("#34C759", 130, 100),
            ("#00C7BE", 175, 100),
            ("#007AFF", 215, 100),
            ("#5856D6", 245, 90),
            ("#AF52DE", 280, 100),
            ("#FF2D55", 345, 100),
            ("#FFFFFF", 0, 0),
        ]

        self._cached_wheel_val = None
        self._cached_wheel_tk = None
        self._cached_slider_hue = None
        self._cached_slider_tk = None
        self._img_canvas_id = None

        self._build_ui()
        self.update_all_displays()

    def _build_ui(self):
        self.container = ctk.CTkFrame(self, fg_color="#121218", border_color="#2c2c38", border_width=1, corner_radius=16)
        self.container.pack(padx=16, pady=16, fill="both", expand=True)

        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_columnconfigure(1, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

        # ── LEFT PANEL: VISUAL INTERACTION (WHEEL OR SLIDERS CANVAS) ────────
        left_panel = ctk.CTkFrame(self.container, fg_color="transparent")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=24, pady=20)

        header = ctk.CTkFrame(left_panel, fg_color="transparent")
        header.pack(fill="x", pady=(0, 10))

        back_btn = ctk.CTkButton(
            header, text="← Back to Dashboard", width=140, height=32,
            fg_color="#1a1a24", hover_color="#222230", text_color="#eeeef5",
            font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
            command=self.on_cancel_cb
        )
        back_btn.pack(side="left")

        # Visual Display Area
        self.canvas_frame = ctk.CTkFrame(left_panel, fg_color="#171720", corner_radius=12)
        self.canvas_frame.pack(fill="x", pady=(10, 15))

        self.canvas = ctk.CTkCanvas(self.canvas_frame, width=256, height=256, bg="#171720", highlightthickness=0)
        self.canvas.pack(pady=10)
        self.canvas.bind("<B1-Motion>", self._handle_canvas_drag)
        self.canvas.bind("<Button-1>", self._handle_canvas_drag)

        # Quick Palette Swatches
        ctk.CTkLabel(left_panel, text="PRESET SWATCHES", font=ctk.CTkFont(size=10, weight="bold"), text_color="#6b6b78").pack(anchor="w", pady=(8, 4))
        swatch_row = ctk.CTkFrame(left_panel, fg_color="transparent")
        swatch_row.pack(fill="x")

        for hex_code, h_deg, s_pct in self.preset_swatches:
            btn = ctk.CTkButton(
                swatch_row, text="", width=26, height=26,
                fg_color=hex_code, hover_color=hex_code, corner_radius=6,
                command=lambda h=h_deg/360.0, s=s_pct/100.0: self._select_preset_hsv(h, s)
            )
            btn.pack(side="left", padx=3, pady=2)

        # ── RIGHT PANEL: CONTROLS & NUMERICALS ──────────────────────────────
        right_panel = ctk.CTkFrame(self.container, fg_color="transparent")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)

        # Style Tabs (Wheel vs Sliders)
        self.tabs = ctk.CTkSegmentedButton(
            right_panel, values=["Wheel", "Sliders"],
            selected_color="#7c6ef5", unselected_color="#1a1a24",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_style_tab_switch
        )
        self.tabs.pack(fill="x", pady=(0, 20))
        self.tabs.set("Wheel")

        # Preview Swatch + Hex Input Row
        prev_row = ctk.CTkFrame(right_panel, fg_color="transparent")
        prev_row.pack(fill="x", pady=(0, 20))

        self.color_preview = ctk.CTkFrame(prev_row, width=64, height=44, fg_color="#FF3B30", corner_radius=10)
        self.color_preview.pack(side="left", padx=(0, 14))

        self.hex_entry = ctk.CTkEntry(
            prev_row, font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            text_color="#f2f2f5", fg_color="#1a1a24", border_color="#3a3a48",
            width=130, height=44, corner_radius=8
        )
        self.hex_entry.insert(0, "#FF3B30")
        self.hex_entry.pack(side="left")
        self.hex_entry.bind("<Return>", self._on_hex_submit)
        self.hex_entry.bind("<FocusOut>", self._on_hex_submit)

        # Slider Controls Container
        self.sliders_container = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.sliders_container.pack(fill="x", expand=True)

        # 1. HUE SLIDER
        self.hue_row = ctk.CTkFrame(self.sliders_container, fg_color="transparent")
        self.hue_row.pack(fill="x", pady=6)
        h_meta = ctk.CTkFrame(self.hue_row, fg_color="transparent")
        h_meta.pack(fill="x")
        ctk.CTkLabel(h_meta, text="HUE", font=ctk.CTkFont(size=10, weight="bold"), text_color="#888899").pack(side="left")
        self.hue_lbl = ctk.CTkLabel(h_meta, text="0°", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#7c6ef5")
        self.hue_lbl.pack(side="right")
        self.hue_slider = ctk.CTkSlider(self.hue_row, from_=0, to=360, command=self._on_hue_slider, progress_color="#7c6ef5", button_color="#9d92ff")
        self.hue_slider.pack(fill="x", pady=(2, 0))
        self.hue_slider.set(0)

        # 2. SATURATION SLIDER
        self.sat_row = ctk.CTkFrame(self.sliders_container, fg_color="transparent")
        self.sat_row.pack(fill="x", pady=6)
        s_meta = ctk.CTkFrame(self.sat_row, fg_color="transparent")
        s_meta.pack(fill="x")
        ctk.CTkLabel(s_meta, text="SATURATION", font=ctk.CTkFont(size=10, weight="bold"), text_color="#888899").pack(side="left")
        self.sat_lbl = ctk.CTkLabel(s_meta, text="100%", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#7c6ef5")
        self.sat_lbl.pack(side="right")
        self.sat_slider = ctk.CTkSlider(self.sat_row, from_=0, to=100, command=self._on_sat_slider, progress_color="#7c6ef5", button_color="#9d92ff")
        self.sat_slider.pack(fill="x", pady=(2, 0))
        self.sat_slider.set(100)

        # 3. BRIGHTNESS / VALUE SLIDER
        self.val_row = ctk.CTkFrame(self.sliders_container, fg_color="transparent")
        self.val_row.pack(fill="x", pady=6)
        v_meta = ctk.CTkFrame(self.val_row, fg_color="transparent")
        v_meta.pack(fill="x")
        ctk.CTkLabel(v_meta, text="BRIGHTNESS", font=ctk.CTkFont(size=10, weight="bold"), text_color="#888899").pack(side="left")
        self.val_lbl = ctk.CTkLabel(v_meta, text="80%", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#7c6ef5")
        self.val_lbl.pack(side="right")
        self.val_slider = ctk.CTkSlider(self.val_row, from_=1, to=100, command=self._on_val_slider, progress_color="#7c6ef5", button_color="#9d92ff")
        self.val_slider.pack(fill="x", pady=(2, 0))
        self.val_slider.set(80)

        # Numerical RGB row
        rgb_row = ctk.CTkFrame(right_panel, fg_color="#171720", corner_radius=8)
        rgb_row.pack(fill="x", pady=(14, 20))
        self.rgb_lbl = ctk.CTkLabel(rgb_row, text="R: 255  G: 59  B: 48", font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color="#9a9aa8")
        self.rgb_lbl.pack(pady=8)

        # Apply Button
        apply_btn = ctk.CTkButton(
            right_panel, text="✓  Apply Color to Light",
            fg_color="#28a745", hover_color="#218838", text_color="#ffffff",
            font=ctk.CTkFont(size=14, weight="bold"), height=44, corner_radius=10,
            command=self._apply_and_close
        )
        apply_btn.pack(fill="x", side="bottom")

        self.cursor_id = self.canvas.create_oval(-6, -6, 6, 6, outline="white", width=2)

    def _on_style_tab_switch(self, style: str):
        self.current_style = style
        if style == "Wheel":
            self.hue_row.pack_forget()
        else:
            self.hue_row.pack(fill="x", pady=6, before=self.sat_row)
        self.update_all_displays()

    def _select_preset_hsv(self, h, s):
        self.hue = h
        self.sat = s
        self.update_all_displays()

    def _on_hue_slider(self, val):
        self.hue = float(val) / 360.0
        self.update_all_displays()

    def _on_sat_slider(self, val):
        self.sat = float(val) / 100.0
        self.update_all_displays()

    def _on_val_slider(self, val):
        self.val = max(0.01, float(val) / 100.0)
        self.update_all_displays()

    def _handle_canvas_drag(self, event):
        x, y = event.x, event.y
        if self.current_style == "Wheel":
            dx, dy = x - 128, y - 128
            dist = math.sqrt(dx * dx + dy * dy)
            if dist == 0: return
            dist = min(120.0, dist)
            self.sat = dist / 120.0
            angle = math.atan2(dy, dx)
            self.hue = ((angle + math.pi) / (2 * math.pi)) % 1.0
        else:
            # Sliders box: x is Saturation (0..255), y is 1 - Value (0..255)
            x_clamped = max(0, min(255, x))
            y_clamped = max(0, min(255, y))
            self.sat = x_clamped / 255.0
            self.val = max(0.01, 1.0 - (y_clamped / 255.0))
        self.update_all_displays()

    def update_all_displays(self):
        # 1. Update sliders
        self.hue_slider.set(int(self.hue * 360))
        self.hue_lbl.configure(text=f"{int(self.hue * 360)}°")

        self.sat_slider.set(int(self.sat * 100))
        self.sat_lbl.configure(text=f"{int(self.sat * 100)}%")

        self.val_slider.set(int(self.val * 100))
        self.val_lbl.configure(text=f"{int(self.val * 100)}%")

        # 2. RGB & Hex
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.val)
        ri, gi, bi = int(r * 255), int(g * 255), int(b * 255)
        hex_str = f"#{ri:02X}{gi:02X}{bi:02X}"

        self.color_preview.configure(fg_color=hex_str)
        self.hex_entry.delete(0, "end")
        self.hex_entry.insert(0, hex_str)
        self.rgb_lbl.configure(text=f"R: {ri}   G: {gi}   B: {bi}")

        # 3. Canvas render
        self._render_canvas()

    def _render_canvas(self):
        SIZE = 256

        if self.current_style == "Wheel":
            val_rounded = round(self.val, 2)
            if self._cached_wheel_tk is None or self._cached_wheel_val != val_rounded:
                xs = np.arange(SIZE) - 128
                ys = np.arange(SIZE) - 128
                DX, DY = np.meshgrid(xs, ys)
                DIST = np.sqrt(DX**2 + DY**2)
                MASK = DIST <= 120

                H = ((np.arctan2(DY, DX) + math.pi) / (2 * math.pi))
                S = np.clip(DIST / 120.0, 0.0, 1.0)
                V = np.full_like(H, self.val)

                rgb = _hsv_array_to_rgb(H, S, V)
                alpha = (MASK * 255).astype(np.uint8)
                rgba = np.dstack([
                    (rgb[:, :, 0] * 255).astype(np.uint8),
                    (rgb[:, :, 1] * 255).astype(np.uint8),
                    (rgb[:, :, 2] * 255).astype(np.uint8),
                    alpha,
                ])
                img = Image.fromarray(rgba, "RGBA")
                self._cached_wheel_tk = ImageTk.PhotoImage(img)
                self._cached_wheel_val = val_rounded

            current_tk = self._cached_wheel_tk

            # Cursor position
            angle = (self.hue * 2 * math.pi) - math.pi
            dist = self.sat * 120
            cx = int(128 + math.cos(angle) * dist)
            cy = int(128 + math.sin(angle) * dist)
        else:
            hue_rounded = round(self.hue, 2)
            if self._cached_slider_tk is None or self._cached_slider_hue != hue_rounded:
                xs = np.linspace(0.0, 1.0, SIZE)
                ys = np.linspace(1.0, 0.0, SIZE)
                S, V = np.meshgrid(xs, ys)
                H = np.full_like(S, self.hue)
                rgb = _hsv_array_to_rgb(H, S, V)
                img = Image.fromarray((rgb * 255).astype(np.uint8), "RGB")
                self._cached_slider_tk = ImageTk.PhotoImage(img)
                self._cached_slider_hue = hue_rounded

            current_tk = self._cached_slider_tk

            cx = int(self.sat * 255)
            cy = int((1.0 - self.val) * 255)

        if self._img_canvas_id is None:
            self._img_canvas_id = self.canvas.create_image(0, 0, image=current_tk, anchor="nw", tags="gradient")
        else:
            self.canvas.itemconfig(self._img_canvas_id, image=current_tk)

        self.canvas.coords(self.cursor_id, cx-6, cy-6, cx+6, cy+6)
        self.canvas.tag_raise(self.cursor_id)

    def _on_hex_submit(self, event=None):
        val = self.hex_entry.get().strip().lstrip("#")
        if len(val) == 6:
            try:
                r = int(val[0:2], 16) / 255.0
                g = int(val[2:4], 16) / 255.0
                b = int(val[4:6], 16) / 255.0
                h, s, v = colorsys.rgb_to_hsv(r, g, b)
                self.hue = h
                self.sat = s
                self.val = v
                self.update_all_displays()
            except Exception:
                pass

    def _apply_and_close(self):
        if self.on_apply_cb:
            h_deg = int(self.hue * 360)
            s_pct = int(self.sat * 100)
            b_pct = int(self.val * 100)
            self.on_apply_cb(h_deg, s_pct, b_pct)
