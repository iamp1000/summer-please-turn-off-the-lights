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
    def __init__(self, mode_names, effect_names, on_mode_apply, on_effect_apply, on_toggle_power, on_music_toggle, on_screen_toggle, on_show_dashboard, on_quit):
        self._mode_names = mode_names
        self._effect_names = effect_names
        self._on_mode_apply = on_mode_apply
        self._on_effect_apply = on_effect_apply
        self._on_toggle_power = on_toggle_power
        self._on_music_toggle = on_music_toggle
        self._on_screen_toggle = on_screen_toggle
        self._on_show_dashboard = on_show_dashboard
        self._on_quit = on_quit
        self._icon = None

    def _build_menu(self):
        def create_mode_action(mode_name):
            return lambda icon, item: self._on_mode_apply(mode_name)
            
        def create_effect_action(effect_name):
            return lambda icon, item: self._on_effect_apply(effect_name)

        mode_items = [
            pystray.MenuItem(name.replace("_", " ").title(), create_mode_action(name))
            for name in self._mode_names
        ]
        
        effect_items = [
            pystray.MenuItem(name.replace("_", " ").title(), create_effect_action(name))
            for name in self._effect_names
        ]

        return pystray.Menu(
            pystray.MenuItem("Show Dashboard", lambda icon, item: self._on_show_dashboard(), default=True),
            pystray.MenuItem("Toggle Power", lambda icon, item: self._on_toggle_power()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Static Vibes", pystray.Menu(*mode_items)),
            pystray.MenuItem("Organic Effects", pystray.Menu(*effect_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Music Reactive", lambda icon, item: self._on_music_toggle()),
            pystray.MenuItem("Screen Sync", lambda icon, item: self._on_screen_toggle()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda icon, item: self._quit()),
        )

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
