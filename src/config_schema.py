from __future__ import annotations
import secrets
from typing import Dict, Optional, List, Tuple
from pydantic import BaseModel, Field, model_validator


class DeviceCalibrationConfig(BaseModel):
    model_config = {"extra": "forbid"}
    curve_exponent: float = 1.8
    white_balance: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    min_brightness: int = Field(default=0, ge=0, le=100)
    transition_ms: int = Field(default=0, ge=0, le=1000)


class TapoDeviceConfig(BaseModel):
    model_config = {"extra": "forbid"}
    ip: str
    name: str
    model: Optional[str] = "L900"   # "L900" or "L930"
    calibration: Optional[DeviceCalibrationConfig] = None


class TapoConfig(BaseModel):
    model_config = {"extra": "forbid"}
    devices: Dict[str, TapoDeviceConfig]


class WebConfig(BaseModel):
    model_config = {"extra": "forbid"}
    port: int = 8765
    host: str = "0.0.0.0"
    auth_enabled: bool = False
    auth_token: Optional[str] = None
    token: Optional[str] = None

    @model_validator(mode="after")
    def enforce_host_security(self) -> WebConfig:
        if self.host == "0.0.0.0":
            # If bound to 0.0.0.0, require token auth by default for LAN protection
            self.auth_enabled = True
            if not self.token and not self.auth_token:
                generated = secrets.token_urlsafe(24)
                self.token = generated
                print(f"\n[SECURITY] Web host is 0.0.0.0: Generated default LAN access token: {generated}\n")
        return self


class ModeConfig(BaseModel):
    model_config = {"extra": "forbid"}
    brightness: int = Field(ge=0, le=100)
    color_temp: Optional[int] = Field(None, ge=1800, le=7000)
    hue: Optional[int] = Field(None, ge=0, le=360)
    saturation: Optional[int] = Field(None, ge=0, le=100)


class EffectConfig(BaseModel):
    model_config = {"extra": "forbid"}
    brightness_min: int = Field(ge=0, le=100)
    brightness_max: int = Field(ge=0, le=100)
    color_speed: float = 1.0
    brightness_speed: float = 1.0
    palette: Optional[List[Tuple[int, int]]] = None   # [hue, saturation] pairs
    wave_shape: Optional[str] = "sine"                # sine|triangle|sawtooth|random
    pulse_color: Optional[Tuple[int, int]] = None     # [hue, saturation] for single-color pulse
    strobe_hz: Optional[float] = None                 # strobe frequency override
    flicker: Optional[bool] = False                   # fast-tick candle mode


class AudioConfig(BaseModel):
    model_config = {"extra": "forbid"}
    device: Optional[str] = None
    sensitivity: Optional[float] = 1.0
    style: Optional[str] = "auto"
    accents: Optional[List[str]] = Field(default_factory=lambda: ["beat_flash", "hat_sparkle", "build_tension", "drop_bloom"])
    output_delay_ms: Optional[int] = 0
    l900_mode: Optional[str] = "style" # "style" or "composite"


class ScreenSyncConfig(BaseModel):
    model_config = {"extra": "forbid"}
    monitor_index: Optional[int] = 1
    profile: Optional[str] = "balanced"


class AppConfig(BaseModel):
    model_config = {"extra": "forbid"}
    tapo: TapoConfig
    modes: Dict[str, ModeConfig]
    effects: Dict[str, EffectConfig]
    hotkeys: Dict[str, str]
    web: WebConfig = Field(default_factory=WebConfig)
    audio: Optional[AudioConfig] = None
    screen_sync: Optional[ScreenSyncConfig] = None
    calibration: Optional[Dict[str, DeviceCalibrationConfig]] = None


def validate_config(raw_config: dict) -> AppConfig:
    return AppConfig(**raw_config)
