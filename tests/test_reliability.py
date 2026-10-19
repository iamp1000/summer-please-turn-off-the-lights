from __future__ import annotations
import asyncio
import pytest
from src.device import is_session_timeout, LightController
from src.device_l930 import L930Controller

def test_session_timeout_detection():
    # Verify various Tapo / KLAP session timeout exception patterns
    class TapoMockError(Exception):
        pass

    assert is_session_timeout(TapoMockError("Error: SESSION_TIMEOUT (-1003)"))
    assert is_session_timeout(TapoMockError("TapoException: Invalid authentication credentials"))
    assert is_session_timeout(TapoMockError("HTTP 401 Unauthorized token_expired"))
    assert is_session_timeout(TapoMockError("Handshake failure code -1501"))
    assert not is_session_timeout(TapoMockError("Connection refused by peer"))
    assert not is_session_timeout(TapoMockError("Temporary DNS failure"))

@pytest.mark.asyncio
async def test_auto_reauth_on_session_timeout():
    loop = asyncio.get_running_loop()
    ctrl = LightController("127.0.0.1", "test@test.com", "secret", dev_id="mock_l900", loop=loop)

    connect_calls = 0
    send_attempts = 0

    class FakeDevice:
        is_on = True

        async def update(self):
            pass

        async def turn_on(self):
            pass

        async def turn_off(self):
            pass

        async def set_hue_saturation(self, h, s):
            pass

        async def set_brightness(self, b):
            nonlocal send_attempts
            send_attempts += 1
            if send_attempts == 1:
                # First attempt raises SESSION_TIMEOUT
                raise Exception("SESSION_TIMEOUT -1003")
            # Second attempt succeeds after reauth
            return True

    async def fake_connect(config):
        nonlocal connect_calls
        connect_calls += 1
        return FakeDevice()

    # Monkeypatch connect
    import src.device as dev_mod
    original_connect = dev_mod.connect
    dev_mod.connect = fake_connect

    try:
        await ctrl.connect()
        assert connect_calls == 1

        # Transmit frame should encounter session timeout, auto-reauth, and retry successfully
        success = await ctrl.transmit_frame({"h": 120, "s": 100, "b": 80})
        assert success is True
        assert connect_calls == 2  # Reconnected!
        assert ctrl.diagnostics.reconnect_count == 2
    finally:
        dev_mod.connect = original_connect


@pytest.mark.asyncio
async def test_l930_clean_shutdown_and_power_off_safety():
    """Verify that power off and clean shutdown disable active effects (enable=0) and purge queues."""
    loop = asyncio.get_running_loop()
    ctrl = L930Controller("127.0.0.1", "test@test.com", "secret", dev_id="mock_l930", loop=loop)

    effect_calls = []
    power_calls = []
    client_closed = False

    class FakeClient:
        async def close(self):
            nonlocal client_closed
            client_closed = True

    class FakeDevice:
        is_on = True
        client = FakeClient()

        async def update(self):
            pass

        async def turn_on(self):
            power_calls.append("on")

        async def turn_off(self):
            power_calls.append("off")

        async def set_light_effect(self, effect):
            effect_calls.append(effect)

    async def fake_connect(config):
        return FakeDevice()

    import src.device_l930 as dev_l930_mod
    orig_connect = dev_l930_mod.connect
    dev_l930_mod.connect = fake_connect

    try:
        await ctrl.connect()
        # Submit a pending frame to verify clear_frames() purges it
        ctrl.submit_frame({"segments": [[100, 100, 100]] * 50, "brightness": 100})
        assert ctrl.frame_sender._pending_frame is not None

        # Turn off: must clear pending frames and disable active effect (enable=0)
        await ctrl.turn_off()
        assert ctrl.frame_sender._pending_frame is None
        assert "off" in power_calls
        assert len(effect_calls) >= 1
        assert effect_calls[-1].enable == 0

        # Now test clean_shutdown(): must disable effect, turn off, and close client
        effect_calls.clear()
        power_calls.clear()
        await ctrl.connect()
        ctrl.submit_frame({"segments": [[50, 50, 50]] * 50, "brightness": 50})
        await ctrl.clean_shutdown()

        assert ctrl.frame_sender._pending_frame is None
        assert len(effect_calls) >= 1
        assert effect_calls[-1].enable == 0
        assert "off" in power_calls
        assert client_closed is True
        assert ctrl._device is None
        assert ctrl.diagnostics.status == "disconnected"
    finally:
        dev_l930_mod.connect = orig_connect

