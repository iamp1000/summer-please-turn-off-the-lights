from __future__ import annotations
import asyncio
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Set, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

from src.logger import log

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


class PowerRequest(BaseModel):
    power: bool | None = None


class BrightnessRequest(BaseModel):
    brightness: int


class ModeRequest(BaseModel):
    mode: str


class EffectRequest(BaseModel):
    effect: str


class ColorRequest(BaseModel):
    h: int
    s: int
    v: int


class MusicModeRequest(BaseModel):
    mode: str


class AudioSelectRequest(BaseModel):
    device: str


class AudioSensitivityRequest(BaseModel):
    sensitivity: float


class AudioLookaheadRequest(BaseModel):
    lookahead_ms: float


class CompositeModeRequest(BaseModel):
    mode: str


class PresetRequest(BaseModel):
    name: str


def create_app(hub) -> FastAPI:
    active_websockets: Set[WebSocket] = set()

    # Security configuration
    web_cfg = hub.config.get("web", {})
    expected_token = os.getenv("TAPO_WEB_TOKEN") or web_cfg.get("auth_token") or web_cfg.get("token")
    auth_enabled = bool(web_cfg.get("auth_enabled", False) or (expected_token is not None and str(expected_token).strip() != ""))

    if auth_enabled:
        log.info("[Security] Web dashboard token authentication is ENABLED.")
    else:
        log.info("[Security] Web dashboard token authentication is DISABLED (open LAN access).")

    def verify_auth(request: Request):
        if not auth_enabled:
            return True

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            if token == expected_token:
                return True

        x_token = request.headers.get("X-Auth-Token")
        if x_token and x_token.strip() == expected_token:
            return True

        query_token = request.query_params.get("token")
        if query_token and query_token.strip() == expected_token:
            return True

        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing access token")

    # Broadcast state updates to all connected phones / web clients
    async def broadcast_state(st: dict):
        dead_sockets = set()
        for ws in list(active_websockets):
            try:
                await ws.send_json(st)
            except Exception:
                dead_sockets.add(ws)
        for ws in dead_sockets:
            active_websockets.discard(ws)

    main_loop = None

    def hub_state_listener(st: dict):
        nonlocal main_loop
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast_state(st), main_loop)

    hub.subscribe(hub_state_listener)

    # Periodic 1-second telemetry push for real send FPS, RTT, and live audio DSP
    async def telemetry_ticker():
        while True:
            await asyncio.sleep(1.0)
            if active_websockets:
                diag = hub.get_diagnostics()
                audio_telem = hub.get_audio_telemetry()
                zone_prev = hub.get_zone_preview()
                dead_sockets = set()
                for ws in list(active_websockets):
                    try:
                        await ws.send_json({
                            "type": "telemetry",
                            "diagnostics": diag,
                            "audio": audio_telem,
                            "zone_preview": zone_prev
                        })
                    except Exception:
                        dead_sockets.add(ws)
                for ws in dead_sockets:
                    active_websockets.discard(ws)

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI):
        nonlocal main_loop
        main_loop = asyncio.get_running_loop()
        ticker_task = asyncio.create_task(telemetry_ticker())
        yield
        ticker_task.cancel()

    app = FastAPI(title="Tapo Light Control Hub", lifespan=lifespan)

    # ── Public Endpoints ──────────────────────────────────────────────────────

    @app.get("/api/auth/status")
    def auth_status():
        return {
            "auth_enabled": auth_enabled,
        }

    @app.get("/api/auth/verify")
    def verify_token_endpoint(_: bool = Depends(verify_auth)):
        return {"status": "ok", "authenticated": True}

    # ── Authenticated API Endpoints ───────────────────────────────────────────

    @app.get("/api/state", dependencies=[Depends(verify_auth)])
    def get_state():
        return hub.get_full_state()

    @app.get("/api/diagnostics", dependencies=[Depends(verify_auth)])
    def get_diagnostics():
        return hub.get_diagnostics()

    @app.get("/api/audio/devices", dependencies=[Depends(verify_auth)])
    def get_audio_devices():
        return {
            "devices": hub.get_audio_devices(),
            "selected": hub.audio_device,
        }

    @app.post("/api/audio/select", dependencies=[Depends(verify_auth)])
    def select_audio_device(req: AudioSelectRequest):
        hub.set_audio_device(req.device)
        return {"status": "ok", "selected": req.device}

    @app.post("/api/device/{dev_id}/power", dependencies=[Depends(verify_auth)])
    def set_power(dev_id: str, req: PowerRequest):
        hub.set_power(dev_id, req.power)
        return {"status": "ok"}

    @app.post("/api/device/{dev_id}/brightness", dependencies=[Depends(verify_auth)])
    def set_brightness(dev_id: str, req: BrightnessRequest):
        hub.set_brightness(dev_id, req.brightness)
        return {"status": "ok"}

    @app.post("/api/device/{dev_id}/mode", dependencies=[Depends(verify_auth)])
    def apply_mode(dev_id: str, req: ModeRequest):
        hub.apply_mode(dev_id, req.mode)
        return {"status": "ok"}

    @app.post("/api/device/{dev_id}/effect", dependencies=[Depends(verify_auth)])
    def apply_effect(dev_id: str, req: EffectRequest):
        hub.apply_effect(dev_id, req.effect)
        return {"status": "ok"}

    @app.post("/api/device/{dev_id}/music", dependencies=[Depends(verify_auth)])
    def toggle_music(dev_id: str):
        hub.toggle_music(dev_id)
        return {"status": "ok"}

    @app.post("/api/device/{dev_id}/music/mode", dependencies=[Depends(verify_auth)])
    def set_music_mode(dev_id: str, req: MusicModeRequest):
        hub.set_music_mode(dev_id, req.mode)
        return {"status": "ok"}

    @app.post("/api/device/{dev_id}/music/sensitivity", dependencies=[Depends(verify_auth)])
    def set_music_sensitivity(dev_id: str, req: AudioSensitivityRequest):
        hub.set_audio_sensitivity(dev_id, req.sensitivity)
        return {"status": "ok", "sensitivity": req.sensitivity}

    @app.post("/api/device/{dev_id}/music/lookahead", dependencies=[Depends(verify_auth)])
    def set_music_lookahead(dev_id: str, req: AudioLookaheadRequest):
        hub.set_audio_lookahead(dev_id, req.lookahead_ms)
        return {"status": "ok", "lookahead_ms": req.lookahead_ms}

    @app.get("/api/audio/telemetry", dependencies=[Depends(verify_auth)])
    def get_audio_telemetry():
        return hub.get_audio_telemetry()

    @app.post("/api/device/{dev_id}/screen", dependencies=[Depends(verify_auth)])
    def toggle_screen(dev_id: str):
        hub.toggle_screen(dev_id)
        return {"status": "ok"}

    @app.post("/api/device/{dev_id}/color", dependencies=[Depends(verify_auth)])
    def apply_color(dev_id: str, req: ColorRequest):
        hub.apply_custom_color(dev_id, req.h, req.s, req.v)
        return {"status": "ok"}

    @app.post("/api/composite/mode", dependencies=[Depends(verify_auth)])
    def set_composite_mode(req: CompositeModeRequest):
        hub.set_composite_mode(req.mode)
        return {"status": "ok", "mode": req.mode}

    @app.get("/api/composite/mode", dependencies=[Depends(verify_auth)])
    def get_composite_mode():
        return {"mode": hub.composite_mgr.mode}

    @app.post("/api/circadian/toggle", dependencies=[Depends(verify_auth)])
    def toggle_circadian():
        enabled = hub.toggle_circadian()
        return {"status": "ok", "circadian_enabled": enabled}

    @app.get("/api/presets", dependencies=[Depends(verify_auth)])
    def list_presets():
        return {"presets": hub.preset_mgr.list_presets()}

    @app.post("/api/presets/apply", dependencies=[Depends(verify_auth)])
    def apply_preset(req: PresetRequest):
        ok = hub.apply_preset(req.name)
        return {"status": "ok" if ok else "not_found"}

    @app.post("/api/presets/save", dependencies=[Depends(verify_auth)])
    def save_preset(req: PresetRequest):
        res = hub.save_preset(req.name)
        return {"status": "ok", "preset": res}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
        if auth_enabled:
            header_auth = websocket.headers.get("Authorization")
            query_tok = token or websocket.query_params.get("token")
            matched = False
            if header_auth and header_auth.startswith("Bearer "):
                matched = (header_auth.split(" ", 1)[1].strip() == expected_token)
            elif query_tok and query_tok.strip() == expected_token:
                matched = True

            if not matched:
                await websocket.close(code=4401)
                return

        await websocket.accept()
        active_websockets.add(websocket)
        try:
            # Send initial full state immediately upon connecting
            await websocket.send_json(hub.get_full_state())
            while True:
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            active_websockets.discard(websocket)
        except Exception:
            active_websockets.discard(websocket)

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def index():
        index_file = WEB_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Web app UI loading..."}

    return app


def start_web_server(hub, host: str = "0.0.0.0", port: int = 8765):
    """Launches the FastAPI server in a background thread."""
    app = create_app(hub)
    server_config = uvicorn.Config(app=app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(server_config)

    thread = threading.Thread(target=server.run, daemon=True, name="TapoWebServer")
    thread.start()
    return server
