from __future__ import annotations
import sys
import os

# Under pythonw.exe, sys.stdout and sys.stderr are None; redirect to devnull to prevent NoneType write errors
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    except Exception:
        pass

import webbrowser
from pathlib import Path
import atexit
import yaml

from src.event_loop import BackgroundLoop
from src.hotkeys import HotkeyManager
from src.hub import LightHub
from src.webapp import start_web_server
from src.tray import TrayApp
from src.gui import TapoGUI, get_local_ip
from src.config_schema import validate_config
from dotenv import load_dotenv

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
CRASH_LOG_PATH = Path(__file__).resolve().parent.parent / "crash.log"


def _log_crash(msg: str):
    try:
        import time
        with open(CRASH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _uncaught_handler(ex_type, ex_val, ex_tb):
    import traceback
    tb_str = "".join(traceback.format_exception(ex_type, ex_val, ex_tb))
    _log_crash(f"UNHANDLED EXCEPTION:\n{tb_str}")
    sys.__excepthook__(ex_type, ex_val, ex_tb)


sys.excepthook = _uncaught_handler


def load_config() -> dict:
    load_dotenv(ENV_PATH)
    if not CONFIG_PATH.exists():
        print(f"CRITICAL: Configuration file missing at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)
    try:
        validate_config(raw_config)
    except Exception as e:
        print(f"ERROR: config.yaml validation faulted!\n{e}")
        sys.exit(1)
    return raw_config


def main():
    config = load_config()

    email = os.getenv("TAPO_EMAIL")
    password = os.getenv("TAPO_PASSWORD")
    if not email or not password:
        print("ERROR: Authentication variables missing in .env container.")
        sys.exit(1)

    # 1. Background Event Loop Runner
    loop_runner = BackgroundLoop()
    loop_runner.start()

    # 2. Central Light Hub (manages L900 and L930 simultaneously)
    hub = LightHub(config, loop_runner)
    hub.start_connections()

    # 3. Launch Web Server in Background Thread
    web_cfg = config.get("web", {})
    web_host = web_cfg.get("host", "0.0.0.0")
    web_port = web_cfg.get("port", 8765)
    local_ip = get_local_ip()
    try:
        start_web_server(hub, host=web_host, port=web_port)
        print("\n" + "=" * 50)
        print(">> Tapo Dual-Light Controller Running")
        print(f">> Phone Web App Available at: http://{local_ip}:{web_port}")
        print(f">> Local Dashboard at:         http://localhost:{web_port}")
        print("=" * 50 + "\n")
    except Exception as ex:
        print(f"[Warning] Web server start error: {ex}")

    # 4. Graceful Shutdown Handler
    _quitting = False

    def on_quit():
        nonlocal _quitting
        if _quitting:
            return
        _quitting = True
        print("\nShutdown sequence engaged. Releasing threads gracefully...")
        try:
            hotkeys.unregister_all()
        except Exception:
            pass
        try:
            hub.shutdown()
        except Exception:
            pass
        try:
            tray.stop()
        except Exception:
            pass
        try:
            loop_runner.stop()
        except Exception:
            pass
        try:
            if hasattr(gui, "app") and gui.app:
                gui.app.after(0, gui.app.destroy)
        except Exception:
            pass
        # Immediate clean exit to avoid lingering background daemon threads
        os._exit(0)

    atexit.register(on_quit)

    # 5. Hotkeys Configuration
    hotkeys = HotkeyManager()
    mapped_combos = {}
    for action_key, combo in config.get("hotkeys", {}).items():
        if action_key == "toggle_power":
            mapped_combos[combo] = lambda: hub.set_power("all")
        elif action_key == "brightness_up":
            mapped_combos[combo] = lambda: [
                hub.set_brightness(d, min(100, ctx.state["brightness"] + 10))
                for d, ctx in hub.devices.items()
            ]
        elif action_key == "brightness_down":
            mapped_combos[combo] = lambda: [
                hub.set_brightness(d, max(1, ctx.state["brightness"] - 10))
                for d, ctx in hub.devices.items()
            ]
        elif action_key == "interactive_music":
            mapped_combos[combo] = lambda: hub.toggle_music("all")
        elif action_key == "interactive_screen":
            mapped_combos[combo] = lambda: hub.toggle_screen("all")
        elif action_key.startswith("mode_"):
            m_target = action_key.replace("mode_", "")
            mapped_combos[combo] = lambda t=m_target: hub.apply_mode("all", t)
        elif action_key.startswith("effect_"):
            e_target = action_key.replace("effect_", "")
            mapped_combos[combo] = lambda t=e_target: hub.apply_effect("all", t)

    try:
        hotkeys.register_all(mapped_combos)
    except Exception as e:
        print(f"[Hotkeys] Warning: {e}")

    # 6. Desktop GUI Instance
    gui = TapoGUI(hub, on_quit=on_quit)

    def show_dashboard():
        def _do():
            try:
                gui.show_window()
            except Exception:
                pass
        gui.app.after(0, _do)

    # 7. System Tray Application
    from src.effects_l930 import CUSTOM_EFFECTS, CREATIVE_EFFECTS
    # Keep the tray menu focused on the L900's ambient set plus the curated L930
    # originals/spatial experiments; stock Tapo duplicates are intentionally omitted.
    l900_ambient_effects = {
        "ambient_drift", "fireplace", "golden_hour",
        "ocean_waves", "color_breath", "candle_flicker",
    }
    all_eff_names = sorted(l900_ambient_effects | set(CUSTOM_EFFECTS))
    tray = TrayApp(
        mode_names=list(config.get("modes", {}).keys()),
        effect_names=all_eff_names,
        creative_effects=CREATIVE_EFFECTS,
        on_mode_apply=lambda m: hub.apply_mode("all", m),
        on_effect_apply=lambda e: hub.apply_effect("all", e),
        on_toggle_power=lambda: hub.set_power("all"),
        on_music_toggle=lambda: hub.toggle_music("all"),
        on_screen_toggle=lambda: hub.toggle_screen("all"),
        on_show_dashboard=show_dashboard,
        on_hide_dashboard=lambda: gui.app.after(0, gui.hide_window),
        on_quit=on_quit,
    )
    tray.run()

    # 8. Start GUI Event Loop
    show_dashboard()
    gui.run()


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        import traceback
        _log_crash(f"TOP-LEVEL EXCEPTION IN MAIN:\n{traceback.format_exc()}")
        raise
