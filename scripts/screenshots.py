"""
scripts/screenshots.py
Captures high-resolution 1280x800 screenshots of the Tapo Light Hub web dashboard
in each of the four modes (Pulse, Spectrum, Flow, Movie) using Playwright.
Automatically blurs any tokens, passwords, and local device IP addresses.
"""
from __future__ import annotations

import asyncio
import http.server
import json
import os
import socketserver
import threading
from pathlib import Path
from playwright.async_api import async_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
ASSETS_DIR = PROJECT_ROOT / "assets"
PORT = 8792


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress logging


def get_mock_state(vstyle: str) -> dict:
    return {
        "connected": True,
        "token_protected": True,
        "active_device": "strip2",
        "composite_mode": "off",
        "circadian_active": False,
        "devices": {
            "strip1": {
                "name": "Desk Monitor (L900-5)",
                "model": "L900",
                "ip": "192.168.1.145",
                "power": True,
                "brightness": 65,
                "active_label": f"Music: {vstyle.capitalize()}",
                "hsv": [32, 45, 65],
            },
            "strip2": {
                "name": "Bed Backboard (L930)",
                "model": "L930",
                "ip": "192.168.1.146",
                "power": True,
                "brightness": 70,
                "active_label": f"Music: {vstyle.capitalize()}",
                "hsv": [215, 85, 70],
            },
        },
        "diagnostics": {
            "strip2": {
                "fps": 8.0,
                "rtt_ms": 78.4,
                "total_latency_ms": 94.2,
                "median_latency_ms": 91.5,
                "p95_latency_ms": 118.0,
                "frames_sent": 1420,
                "frames_dropped": 12,
                "error_count": 0,
                "reconnect_count": 0,
                "status": "connected",
            }
        },
        "music": {
            "active": True,
            "vstyle": vstyle,
            "bpm": 124.0,
            "key": "A min",
            "section": "VERSE",
            "energy": 0.68,
            "kick": 0.45,
            "sensitivity": 1.0,
            "lookahead_ms": 40.0,
        },
    }


async def capture_mode_screenshots():
    ASSETS_DIR.mkdir(exist_ok=True)

    # 1. Start quiet HTTP static server
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), QuietHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"Local dashboard server listening on http://127.0.0.1:{PORT}")

    modes = ["pulse", "spectrum", "flow", "movie"]

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1.5,
        )

        for mode in modes:
            page = await context.new_page()

            # Mock API status route
            state_data = get_mock_state(mode)

            async def handle_status(route):
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(state_data),
                )

            await page.route("**/api/status", handle_status)
            await page.route("**/api/device/**", lambda r: r.fulfill(status=200, body="{}"))
            await page.route("**/api/music/**", lambda r: r.fulfill(status=200, body="{}"))
            await page.route("**/api/composite/**", lambda r: r.fulfill(status=200, body="{}"))

            # Navigate to web dashboard
            await page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")

            # Enable visualizer section and select target mode button
            js_code = """
                (targetMode) => {
                    const vBtns = document.getElementById("visualizerModes");
                    if (vBtns) vBtns.style.display = "block";
                    
                    document.querySelectorAll("#vstyleButtons button").forEach(b => {
                        if (b.dataset.vstyle === targetMode) {
                            b.classList.add("active");
                        } else {
                            b.classList.remove("active");
                        }
                    });

                    // Draw sample spectrum bar on canvas
                    const canvas = document.getElementById("audioSpectrumCanvas");
                    if (canvas) {
                        const ctx = canvas.getContext("2d");
                        ctx.clearRect(0, 0, canvas.width, canvas.height);
                        const n = 50;
                        const w = canvas.width / n;
                        for (let i = 0; i < n; i++) {
                            const h = Math.sin(i * 0.2) * 15 + 20;
                            ctx.fillStyle = `hsl(${i * 6 + 180}, 85%, 60%)`;
                            ctx.fillRect(i * w, canvas.height - h, w - 1, h);
                        }
                    }

                    // Draw 50-zone hardware preview bar
                    const zoneCanvas = document.getElementById("zonePreviewCanvas");
                    if (zoneCanvas) {
                        const ctx = zoneCanvas.getContext("2d");
                        const n = 50;
                        const zw = zoneCanvas.width / n;
                        for (let i = 0; i < n; i++) {
                            ctx.fillStyle = `hsl(${i * 7 + 200}, 90%, 65%)`;
                            ctx.fillRect(i * zw, 0, zw - 1, zoneCanvas.height);
                        }
                    }

                    // Blur tokens and device IPs
                    const blurStyle = document.createElement("style");
                    blurStyle.innerHTML = `
                        #authTokenInput, .auth-token, [data-ip], .ip-addr {
                            filter: blur(8px) !important;
                        }
                    `;
                    document.head.appendChild(blurStyle);

                    // Scan and blur any visible IP text
                    document.querySelectorAll("*").forEach(el => {
                        if (el.children.length === 0 && /\b(?:192\.168|10\.\d+|172\.\d+)\b/.test(el.innerText)) {
                            el.style.filter = "blur(6px)";
                        }
                    });
                }
            """
            await page.evaluate(js_code, mode)

            await page.wait_for_timeout(400)

            out_path = ASSETS_DIR / f"dashboard_{mode}.png"
            await page.screenshot(path=str(out_path), full_page=False)
            print(f"Captured screenshot: {out_path}")
            await page.close()

        await browser.close()

    httpd.shutdown()
    print("All mode screenshots captured successfully!")


def main():
    asyncio.run(capture_mode_screenshots())


if __name__ == "__main__":
    main()
