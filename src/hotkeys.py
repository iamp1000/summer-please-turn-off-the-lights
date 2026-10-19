"""
Registers global (system-wide) keyboard shortcuts and maps them to callbacks.

Uses the `keyboard` library. On Linux this typically needs root (or the
`uinput` group set up) to read the raw input devices -- if that's not an
option for you, swap this module's internals for `pynput.keyboard.GlobalHotKeys`,
which has a similar callback-per-combo model and doesn't need root on X11
(Wayland global-hotkey support is spottier for both libraries).
"""

from __future__ import annotations

import keyboard


class HotkeyManager:
    def __init__(self):
        self._registered = []

    def register(self, combo: str, callback):
        """combo: e.g. 'ctrl+alt+1'. callback: no-arg callable."""
        keyboard.add_hotkey(combo, callback)
        self._registered.append(combo)

    def register_all(self, combo_to_callback: dict):
        for combo, callback in combo_to_callback.items():
            self.register(combo, callback)

    def unregister_all(self):
        for combo in self._registered:
            try:
                keyboard.remove_hotkey(combo)
            except KeyError:
                pass
        self._registered.clear()
