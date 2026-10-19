from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from src.webapp import create_app

class MockHub:
    def __init__(self, auth_enabled: bool = False, token: str = "secret-pass-123"):
        self.config = {
            "web": {
                "auth_enabled": auth_enabled,
                "token": token if auth_enabled else None
            }
        }
        self.audio_device = "auto"

    def subscribe(self, callback):
        pass

    def get_full_state(self):
        return {"devices": {}, "modes": []}

    def get_diagnostics(self):
        return {}

    def get_audio_devices(self):
        return []

def test_web_open_mode():
    hub = MockHub(auth_enabled=False)
    app = create_app(hub)
    client = TestClient(app)

    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json()["auth_enabled"] is False

    res_state = client.get("/api/state")
    assert res_state.status_code == 200

def test_web_token_auth_mode():
    hub = MockHub(auth_enabled=True, token="my-safe-token")
    app = create_app(hub)
    client = TestClient(app)

    # 1. Without token -> 401 Unauthorized
    res_unauth = client.get("/api/state")
    assert res_unauth.status_code == 401

    # 2. With wrong token -> 401 Unauthorized
    res_wrong = client.get("/api/state", headers={"Authorization": "Bearer wrong-token"})
    assert res_wrong.status_code == 401

    # 3. With Bearer token in Authorization header -> 200 OK
    res_bearer = client.get("/api/state", headers={"Authorization": "Bearer my-safe-token"})
    assert res_bearer.status_code == 200

    # 4. With X-Auth-Token header -> 200 OK
    res_x = client.get("/api/state", headers={"X-Auth-Token": "my-safe-token"})
    assert res_x.status_code == 200

    # 5. With ?token= query parameter -> 200 OK
    res_param = client.get("/api/state?token=my-safe-token")
    assert res_param.status_code == 200

    # 6. /api/auth/status is always public
    res_status = client.get("/api/auth/status")
    assert res_status.status_code == 200
    assert res_status.json()["auth_enabled"] is True
