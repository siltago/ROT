"""Transport-independent command/result protocol for future ESP32 integration.

This defines the wire format only. No transport (WiFi/serial/BLE) is
implemented yet -- that will live in hardware/esp32.py once real firmware
exists. Keeping the protocol separate lets us validate/serialize commands
without any physical device connected.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class Command(BaseModel):
    version: int = 1
    id: str
    type: Literal["command"] = "command"
    action: str
    params: dict[str, Any] = Field(default_factory=dict)


class CommandResult(BaseModel):
    version: int = 1
    id: str
    type: Literal["result"] = "result"
    success: bool
    error: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
