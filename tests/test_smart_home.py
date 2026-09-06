from __future__ import annotations

from typing import Any

import pytest

from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy, auto_deny
from actions.registry import ActionRegistry
from actions.smart_home import devices as smart_home_actions
from brain.models import ActionRequest
from integrations.smart_home.models import SmartHomeCapability, SmartHomeCommandResult, SmartHomeDevice, SmartHomeDeviceType, SmartHomeErrorCode
from integrations.smart_home.provider import SmartHomeProvider
from integrations.smart_home.registry import SmartHomeDeviceRegistry
from integrations.smart_home.resolver import SmartHomeTargetResolver
from integrations.smart_home.service import SmartHomeService
from integrations.smart_home.home_assistant_provider import HomeAssistantProvider, _HttpResponse


def device(identifier: str, name: str = "Luz principal", room: str = "quarto", *, primary: bool = False, online: bool = True) -> SmartHomeDevice:
    return SmartHomeDevice(identifier, identifier, "home_assistant", name, "home_1", "Minha casa", room, SmartHomeDeviceType.LIGHT, online, frozenset({SmartHomeCapability.ON_OFF, SmartHomeCapability.BRIGHTNESS}), "light", primary)


class MockProvider(SmartHomeProvider):
    def __init__(self, devices: list[SmartHomeDevice], *, connected: bool = True) -> None:
        self.devices, self._connected, self.calls = devices, connected, []

    @property
    def provider_id(self) -> str:
        return "mock_home_assistant"

    @property
    def connected(self) -> bool:
        return self._connected

    async def list_devices(self) -> list[SmartHomeDevice]:
        return self.devices

    async def execute(self, request_id: str, action: str, device_id: str, value: Any = None) -> SmartHomeCommandResult:
        self.calls.append((request_id, action, device_id, value))
        if not self.connected:
            return SmartHomeCommandResult(False, request_id, SmartHomeErrorCode.PROVIDER_OFFLINE, "Não consegui acessar a casa agora.")
        return SmartHomeCommandResult(True, request_id, message="ok", provider_latency_ms=12)


def test_device_registry_add_update_remove_group_and_search() -> None:
    registry = SmartHomeDeviceRegistry()
    registry.upsert(device("one"))
    registry.upsert(device("two", "Luz sala", "sala"))
    registry.upsert(device("one", "Abajur"))
    assert registry.get("one").name == "Abajur"
    assert len(registry.by_type(SmartHomeDeviceType.LIGHT)) == 2
    assert registry.by_room("QUARTO")[0].id == "one"
    assert set(registry.grouped_by_room()) == {"quarto", "sala"}
    registry.remove("one")
    assert registry.get("one") is None


def test_target_resolver_room_here_primary_and_ambiguity() -> None:
    registry = SmartHomeDeviceRegistry()
    registry.replace_all([device("main", primary=True), device("lamp", "Abajur")])
    resolver = SmartHomeTargetResolver(registry)
    assert resolver.resolve("luz do quarto").devices[0].id == "main"
    assert resolver.resolve("luz aqui", current_room="quarto").devices[0].id == "main"
    registry.replace_all([device("a", "Abajur"), device("b", "LED cama"), device("c", "Luz teto")])
    assert resolver.resolve("luz do quarto").clarification_required


def test_collective_target_returns_all_compatible_devices() -> None:
    registry = SmartHomeDeviceRegistry()
    registry.replace_all([device("a", "Luz teto"), device("b", "Abajur")])
    resolved = SmartHomeTargetResolver(registry).resolve("apaga todas as luzes do quarto")
    assert {item.id for item in resolved.devices} == {"a", "b"}


@pytest.mark.asyncio
async def test_action_executor_calls_provider_exactly_once() -> None:
    provider = MockProvider([device("main", primary=True)])
    service = SmartHomeService(provider)
    await service.synchronize()
    registry = ActionRegistry()
    smart_home_actions.register(registry, service)
    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    record = await executor.execute(ActionRequest(name="smart_home.turn_on", arguments={"target": "luz do quarto"}))
    assert record.outcome.success
    assert len(provider.calls) == 1
    assert provider.calls[0][1:] == ("turn_on", "main", None)


@pytest.mark.asyncio
async def test_provider_and_device_offline_are_structured_failures() -> None:
    offline_provider = MockProvider([device("main", primary=True)], connected=False)
    service = SmartHomeService(offline_provider)
    await service.synchronize()
    assert (await service.execute("turn_on", "luz do quarto")).error_code == SmartHomeErrorCode.PROVIDER_OFFLINE
    device_offline = MockProvider([device("main", primary=True, online=False)])
    service = SmartHomeService(device_offline)
    await service.synchronize()
    assert (await service.execute("turn_on", "luz do quarto")).error_code == SmartHomeErrorCode.DEVICE_OFFLINE


@pytest.mark.asyncio
async def test_home_assistant_discovers_varied_entities_and_executes_service() -> None:
    provider = HomeAssistantProvider("http://homeassistant.local:8123", "secret")
    calls: list[tuple[str, str, dict | None]] = []

    async def request(method: str, path: str, payload: dict | None = None) -> _HttpResponse:
        calls.append((method, path, payload))
        if path == "/api/states":
            return _HttpResponse(200, [
                {"entity_id": "light.sala", "state": "on", "attributes": {"friendly_name": "Luz sala", "brightness": 120}},
                {"entity_id": "climate.quarto", "state": "cool", "attributes": {"friendly_name": "Ar quarto", "current_temperature": 24}},
                {"entity_id": "sensor.temperatura", "state": "24", "attributes": {"friendly_name": "Temperatura"}},
            ])
        return _HttpResponse(200, [])

    provider._request = request  # type: ignore[method-assign]
    devices = await provider.list_devices()
    assert {item.type for item in devices} == {SmartHomeDeviceType.LIGHT, SmartHomeDeviceType.AIR_CONDITIONER, SmartHomeDeviceType.SENSOR}
    result = await provider.execute("request-1", "set_brightness", "light.sala", 45)
    assert result.success
    assert calls[-1] == ("POST", "/api/services/light/turn_on", {"entity_id": "light.sala", "brightness_pct": 45})


@pytest.mark.asyncio
async def test_home_assistant_without_token_fails_closed() -> None:
    provider = HomeAssistantProvider("http://homeassistant.local:8123", "")
    result = await provider.execute("request-2", "turn_on", "light.sala")
    assert result.error_code == SmartHomeErrorCode.PROVIDER_OFFLINE
