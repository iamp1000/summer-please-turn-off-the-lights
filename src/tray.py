from __future__ import annotations

import pystray
from PIL import Image, ImageDraw

def _make_icon_image(color=(255, 140, 0)):
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, size - 8, size - 8), fill=color)
    return img

class TrayApp:
    def __init__(self, mode_names, effect_names, on_mode_apply, on_effect_apply, on_toggle_power, on_music_toggle, on_screen_toggle, on_show_dashboard, on_quit, creative_effects=None, on_hide_dashboard=None):
        self._mode_names = mode_names
        self._effect_names = effect_names
        self._creative_effects = creative_effects or []
        self._on_mode_apply = on_mode_apply
        self._on_effect_apply = on_effect_apply
        self._on_toggle_power = on_toggle_power
        self._on_music_toggle = on_music_toggle
        self._on_screen_toggle = on_screen_toggle
        self._on_show_dashboard = on_show_dashboard
        self._on_hide_dashboard = on_hide_dashboard
        self._on_quit = on_quit
        self._icon = None

    def _build_menu(self):
        def create_mode_action(mode_name):
            return lambda icon, item: self._on_mode_apply(mode_name)
            
        def create_effect_action(effect_name):
            return lambda icon, item: self._on_effect_apply(effect_name)

        creative_items = [
            pystray.MenuItem(name.replace("_", " ").title(), create_effect_action(name))
            for name in self._creative_effects
        ]

        mode_items = [
            pystray.MenuItem(name.replace("_", " ").title(), create_mode_action(name))
            for name in self._mode_names
        ]
        
        effect_items = [
            pystray.MenuItem(name.replace("_", " ").title(), create_effect_action(name))
            for name in self._effect_names
        ]

        menu_items = [
            pystray.MenuItem("Pop Out / Show Window", lambda icon, item: self._on_show_dashboard(), default=True),
        ]
        if callable(self._on_hide_dashboard):
            menu_items.append(
                pystray.MenuItem("Hide Window to Tray", lambda icon, item: self._on_hide_dashboard())
            )
        menu_items.extend([
            pystray.MenuItem("Toggle Power", lambda icon, item: self._on_toggle_power()),
            pystray.Menu.SEPARATOR,
        ])
        if creative_items:
            menu_items.append(pystray.MenuItem("Creative Experiences (L930)", pystray.Menu(*creative_items)))
        menu_items.extend([
            pystray.MenuItem("Organic Effects", pystray.Menu(*effect_items)),
            pystray.MenuItem("Static Vibes", pystray.Menu(*mode_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Music Reactive", lambda icon, item: self._on_music_toggle()),
            pystray.MenuItem("Screen Sync", lambda icon, item: self._on_screen_toggle()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda icon, item: self._quit()),
        ])

        return pystray.Menu(*menu_items)

    def _quit(self):
        try:
            self.stop()
        except Exception:
            pass
        if callable(self._on_quit):
            try:
                self._on_quit()
            except Exception:
                pass

    def stop(self):
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

    def run(self):
        self._icon = pystray.Icon(
            "tapo-light-control",
            icon=_make_icon_image(),
            title="Tapo Light Control",
            menu=self._build_menu(),
        )
        self._icon.run_detached()
