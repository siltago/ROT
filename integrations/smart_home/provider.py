from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from integrations.smart_home.models import SmartHomeCommandResult, SmartHomeDevice


class SmartHomeProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    async def list_devices(self) -> list[SmartHomeDevice]: ...

    @abstractmethod
    async def execute(self, request_id: str, action: str, device_id: str, value: Any = None) -> SmartHomeCommandResult: ...

    async def disconnect(self) -> None:
        return None
