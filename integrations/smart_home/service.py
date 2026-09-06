from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from integrations.smart_home.models import SmartHomeCapability, SmartHomeCommandResult, SmartHomeErrorCode, SmartHomeMetrics
from integrations.smart_home.provider import SmartHomeProvider
from integrations.smart_home.registry import SmartHomeDeviceRegistry
from integrations.smart_home.resolver import SmartHomeTargetResolver


_REQUIRED = {"set_brightness": SmartHomeCapability.BRIGHTNESS, "set_temperature": SmartHomeCapability.TEMPERATURE_SETPOINT}
_POWER_CAPABILITIES = {SmartHomeCapability.ON_OFF, SmartHomeCapability.OPEN_CLOSE, SmartHomeCapability.LOCK_UNLOCK, SmartHomeCapability.MEDIA_POWER}


class SmartHomeService:
    def __init__(self, provider: SmartHomeProvider, registry: SmartHomeDeviceRegistry | None = None) -> None:
        self.provider = provider
        self.registry = registry or SmartHomeDeviceRegistry()
        self.resolver = SmartHomeTargetResolver(self.registry)
        self.metrics = SmartHomeMetrics()
        self.current_room: str | None = None

    async def synchronize(self) -> list:
        devices = await self.provider.list_devices()
        self.registry.replace_all(devices)
        self.metrics.mark_sync()
        return devices

    async def execute(self, action: str, target: str, *, value: Any = None, current_room: str | None = None, collective: bool | None = None) -> SmartHomeCommandResult:
        started = time.monotonic()
        if not self.provider.connected:
            return SmartHomeCommandResult(False, str(uuid4()), SmartHomeErrorCode.PROVIDER_OFFLINE, "Home Assistant não está configurado ou disponível.")
        if not self.registry.all():
            await self.synchronize()
        mark = time.monotonic()
        resolved = self.resolver.resolve(target, current_room=current_room or self.current_room, collective=collective)
        self.metrics.target_resolution_latency_ms = (time.monotonic() - mark) * 1000
        if resolved.clarification_required:
            return SmartHomeCommandResult(False, str(uuid4()), SmartHomeErrorCode.AMBIGUOUS_TARGET, resolved.clarification or "Qual dispositivo?")
        required = _REQUIRED.get(action)
        results = []
        for device in resolved.devices:
            if not device.online:
                return SmartHomeCommandResult(False, str(uuid4()), SmartHomeErrorCode.DEVICE_OFFLINE, f"{device.name} está offline.")
            if action in {"turn_on", "turn_off"} and not (device.capabilities & _POWER_CAPABILITIES):
                return SmartHomeCommandResult(False, str(uuid4()), SmartHomeErrorCode.CAPABILITY_UNSUPPORTED, f"{device.name} não suporta esse comando.")
            if required and required not in device.capabilities:
                return SmartHomeCommandResult(False, str(uuid4()), SmartHomeErrorCode.CAPABILITY_UNSUPPORTED, f"{device.name} não suporta esse comando.")
            request_id = str(uuid4())
            mark = time.monotonic()
            result = await self.provider.execute(request_id, action, device.provider_id, value)
            self.metrics.provider_roundtrip_latency_ms += (time.monotonic() - mark) * 1000
            results.append(result)
            if not result.success:
                break
        final = results[-1] if results else SmartHomeCommandResult(False, str(uuid4()), SmartHomeErrorCode.DEVICE_NOT_FOUND, "Não encontrei esse dispositivo.")
        self.metrics.last_action, self.metrics.last_target = action, target
        self.metrics.last_result = "SUCCESS" if final.success else (final.error_code.value if final.error_code else "FAILED")
        self.metrics.provider_command_latency_ms = final.provider_latency_ms or 0.0
        self.metrics.total_action_latency_ms = (time.monotonic() - started) * 1000
        if final.success:
            return SmartHomeCommandResult(True, final.request_id, message="Pronto.", state={"devices": [d.id for d in resolved.devices]}, provider_latency_ms=final.provider_latency_ms)
        return final
