from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class SmartHomeDeviceType(StrEnum):
    LIGHT = "light"
    SWITCH = "switch"
    OUTLET = "outlet"
    THERMOSTAT = "thermostat"
    AIR_CONDITIONER = "air_conditioner"
    TV = "tv"
    FAN = "fan"
    BLIND = "blind"
    LOCK = "lock"
    SENSOR = "sensor"
    OTHER = "other"


class SmartHomeCapability(StrEnum):
    ON_OFF = "on_off"
    BRIGHTNESS = "brightness"
    COLOR = "color"
    COLOR_TEMPERATURE = "color_temperature"
    TEMPERATURE_SETPOINT = "temperature_setpoint"
    CURRENT_TEMPERATURE = "current_temperature"
    FAN_SPEED = "fan_speed"
    OPEN_CLOSE = "open_close"
    LOCK_UNLOCK = "lock_unlock"
    MEDIA_POWER = "media_power"


class SmartHomeErrorCode(StrEnum):
    PROVIDER_OFFLINE = "SMART_HOME_PROVIDER_OFFLINE"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    AMBIGUOUS_TARGET = "CLARIFICATION_REQUIRED"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    TIMEOUT = "SMART_HOME_TIMEOUT"
    COMMAND_FAILED = "SMART_HOME_COMMAND_FAILED"


@dataclass(frozen=True)
class SmartHomeDevice:
    id: str
    provider_id: str
    provider: str
    name: str
    structure_id: str | None
    structure_name: str | None
    room: str | None
    type: SmartHomeDeviceType
    online: bool
    capabilities: frozenset[SmartHomeCapability] = frozenset()
    provider_type: str | None = None
    is_primary: bool = False


@dataclass(frozen=True)
class SmartHomeCommandResult:
    success: bool
    request_id: str
    error_code: SmartHomeErrorCode | None = None
    message: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    provider_latency_ms: float | None = None


@dataclass
class SmartHomeMetrics:
    last_sync_at: datetime | None = None
    last_action: str | None = None
    last_target: str | None = None
    last_result: str | None = None
    target_resolution_latency_ms: float = 0.0
    provider_roundtrip_latency_ms: float = 0.0
    provider_command_latency_ms: float = 0.0
    total_action_latency_ms: float = 0.0

    def mark_sync(self) -> None:
        self.last_sync_at = datetime.now(timezone.utc)
