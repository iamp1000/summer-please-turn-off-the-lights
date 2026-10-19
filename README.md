<div align="center">

# ✨ Tapo Control Hub 

**A blazing-fast, local-first desktop controller for TP-Link Tapo RGB strips.**

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-2c2c33.svg?style=for-the-badge)](https://github.com/TomSchimansky/CustomTkinter)
[![License: MIT](https://img.shields.io/badge/License-MIT-success.svg?style=for-the-badge)](#)

Ditch the phone app and control your lighting directly from your desktop. Built for speed and aesthetics, this hub bypasses cloud latency by communicating directly with your local network API.

</div>

---

## 🚀 Features

* **Sleek Modern GUI:** A beautiful, dark-mode launcher interface built with `customtkinter`, featuring smooth color pickers and organized libraries for modes and effects.
* **Zero Cloud Latency:** Uses local network communication via `plugp100`. Immediate response times and completely functional offline.
* **Global Hotkeys:** Never break your flow. Control power, brightness, and modes using system-wide keyboard shortcuts—perfect for when you're typing away at 125 WPM and don't want to touch the mouse.
* **Premium Animation Engine:** 
  * Custom effects with customizable color palettes and sine-wave brightness phasing.
  * Smooth 600ms crossfading between static modes for a high-end feel.
  * Gamma-corrected dimming curves so low-light transitions are buttery smooth.
* **Resilient Connectivity:** Automatic background reconnection with exponential backoff and desktop toast notifications if your Wi-Fi drops.
* **System Tray Integration:** Runs quietly in the background with a minimalist tray app.

## 🔌 Supported Hardware
Optimized and tested for Tapo RGB LED strips, specifically:
* **Tapo L900** series
* **Tapo L930** series

## 💻 OS Compatibility
Works flawlessly across different environments:
* **Windows**
* **Arch Linux** (Note: `keyboard` hotkeys may require `sudo` or `uinput` group configuration depending on your display server).

---

## 🛠️ Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/iamp1000/tapo-control-hub.git
cd tapo-control-hub
```

### 2. Set Up a Virtual Environment & Install Dependencies
It is highly recommended to use a virtual environment to isolate your packages.

```bash
# Create environment
python -m venv venv

# Activate environment
# On Windows:
venv\Scripts\activate
# On Linux:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```
*(Ensure your requirements.txt includes: customtkinter, plugp100, keyboard, pystray, pyyaml, python-dotenv, plyer, pydantic, and Pillow)*

### 3. Configure Authentication Environment Variables
Create a `.env` file in the root directory of the project to securely pass your TP-Link cloud account details (used strictly for local token exchange validation):

```env
TAPO_EMAIL=your_tapo_email@example.com
TAPO_PASSWORD=your_secure_password
```

### 4. Create Your Configuration (config.yaml)
Create a `config.yaml` file in the root folder. The application automatically validates this file on startup using strict pydantic schemas.

```yaml
tapo:
  devices:
    strip1:
      ip: "192.168.1.145" # Replace with your light strip's static local IP
      name: "Desk Setup"

modes:
  work:
    brightness: 85
    color_temp: 4200      # Supports kelvin values between 1800 and 7000
  coding_night:
    brightness: 25
    hue: 265              # 0-360 degrees
    saturation: 85        # 0-100%
  chill:
    brightness: 40
    hue: 25
    saturation: 75

effects:
  synthwave:
    brightness_min: 20
    brightness_max: 90
    color_speed: 1.2
    brightness_speed: 0.8
    palette: [[280, 100], [320, 100], [200, 90]] # List of [hue, saturation] pairs
  aurora:
    brightness_min: 40
    brightness_max: 70
    color_speed: 0.5
    brightness_speed: 0.3
    palette: [[140, 90], [190, 100], [240, 85]]

hotkeys:
  toggle_power: "ctrl+shift+p"
  mode_coding_night: "ctrl+shift+["
  mode_work: "ctrl+shift+]"
```

## 🎮 Usage
Launch the background application thread and the control dashboard surface by running:

```bash
python -m src.main
```

**Desktop Operations:**
* **The Dashboard Launcher:** Toggle hardware settings on the fly, adjust precise custom brightness sliders, or click individual mode tiles to crossfade gracefully.
* **The System Tray:** Clicking the X button on the window smoothly minimizes the hub to your OS system tray (pystray), running quietly in the background without stealing your workflow resources. Right-click the icon to quickly swap presets or cleanly terminate the app.

## 🧠 Architectural Deep-Dive
This project avoids monolithic blocks by utilizing an asynchronous service engine driving a highly decoupled, stateful GUI layer.

```text
                  ┌────────────────────────┐
                  │    Global Hotkeys      │
                  │   & System Tray UI     │ (Synchronous OS Threads)
                  └───────────┬────────────┘
                              │ Schedules Coroutine
                              ▼
 ┌─────────────┐  ┌────────────────────────┐  Requests  ┌───────────────────┐
 │ CustomTkinter│─►│     BackgroundLoop     │───────────►│  StateDispatcher  │
 │ UI Surface  │  │ (Dedicated Async Thread)│           │ (LIFO Input Queue)│
 └─────────────┘  └────────────────────────┘            └─────────┬─────────┘
                              ▲                                   │
                              │ Executes Next Valid State         │ Atomically
                              │                                   ▼ Drops Floods
                  ┌───────────┴────────────┐            ┌───────────────────┐
                  │    AnimationEngine     │◄───────────│  LightController  │
                  │ (Sine/Palette Blends)  │            │ (Local plugp100)  │
                  └────────────────────────┘            └───────────────────┘
```

### 1. The Sync-to-Async Bridge (`src/event_loop.py`)
The underlying `plugp100` API is entirely asynchronous, while desktop interface modules like `pystray` and `keyboard` are blocking/synchronous. To prevent locking the main GUI event loop, `BackgroundLoop` spawns a dedicated, persistent background thread managing an isolated `asyncio` event loop. Sync triggers safely route execution packages using `asyncio.run_coroutine_threadsafe`.

### 2. High-Frequency Anti-Choke Queue (`src/main.py`)
To keep up with rapid hotkey mashing or swift slider manipulation, the `StateDispatcher` functions as a single-item Last-In-First-Out (LIFO) queue execution worker. If multiple state mutations are queued within milliseconds, it intelligently flushes out older outdated network payloads, dispatching only the newest target state to avoid throttling the Tapo device interface.

### 3. Kinematic Animations & Crossfades (`src/modes.py` & `src/effects.py`)
* **Kinematic Crossfading:** Rather than abrupt updates, changing profiles triggers a 600ms linear interpolator tracking short-path vector angles across the 360-degree color wheel, preventing ugly flashes.
* **Dynamic Palette Shifting:** The `AnimationEngine` continuously interpolates distance matrices between arrays of custom HSL pairs, feeding synchronized, phase-shifted sine waves into the brightness channels.

## 🔧 Troubleshooting
**Linux (Arch / Ubuntu) Hotkey Permissions**
Because the `keyboard` module monitors hardware device layers globally to catch background shortcuts, it reads directly from `/dev/input/`.

**Fix 1:** Run the app using sudo:
```bash
sudo venv/bin/python -m src.main
```
**Fix 2 (Recommended):** Setup a `uinput` rule or add your active shell user to your system's `input` group to execute without escalating your permissions boundaries permanently.

**Connection Timeout and Dropouts**
If your environment drops connection logs frequently due to aggressive router lease-times:
The core layer incorporates exponential backoff configurations. It will attempt re-authentication sequentially (1s, 2s, 4s, up to 60s) while leveraging `plyer` to push an OS notification banner directly to your desktop action center when the device recovers.
