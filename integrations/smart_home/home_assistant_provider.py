from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from integrations.smart_home.models import (
    SmartHomeCapability,
    SmartHomeCommandResult,
    SmartHomeDevice,
    SmartHomeDeviceType,
    SmartHomeErrorCode,
)
from integrations.smart_home.provider import SmartHomeProvider


_DOMAIN_TYPES = {
    "light": SmartHomeDeviceType.LIGHT,
    "switch": SmartHomeDeviceType.SWITCH,
    "input_boolean": SmartHomeDeviceType.SWITCH,
    "fan": SmartHomeDeviceType.FAN,
    "climate": SmartHomeDeviceType.AIR_CONDITIONER,
    "media_player": SmartHomeDeviceType.TV,
    "cover": SmartHomeDeviceType.BLIND,
    "lock": SmartHomeDeviceType.LOCK,
    "sensor": SmartHomeDeviceType.SENSOR,
    "binary_sensor": SmartHomeDeviceType.SENSOR,
    "vacuum": SmartHomeDeviceType.OTHER,
}


def _capabilities(domain: str, attributes: dict[str, Any]) -> frozenset[SmartHomeCapability]:
    values: set[SmartHomeCapability] = set()
    if domain in {"light", "switch", "input_boolean", "fan", "media_player", "vacuum"}:
        values.add(SmartHomeCapability.ON_OFF)
    if domain == "light" and ("brightness" in attributes or attributes.get("supported_color_modes")):
        values.add(SmartHomeCapability.BRIGHTNESS)
    if domain == "light" and attributes.get("supported_color_modes"):
        values.update({SmartHomeCapability.COLOR, SmartHomeCapability.COLOR_TEMPERATURE})
    if domain == "climate":
        values.update({SmartHomeCapability.ON_OFF, SmartHomeCapability.TEMPERATURE_SETPOINT})
        if "current_temperature" in attributes:
            values.add(SmartHomeCapability.CURRENT_TEMPERATURE)
    if domain == "fan":
        values.add(SmartHomeCapability.FAN_SPEED)
    if domain == "cover":
        values.add(SmartHomeCapability.OPEN_CLOSE)
    if domain == "lock":
        values.add(SmartHomeCapability.LOCK_UNLOCK)
    return frozenset(values)


@dataclass(frozen=True)
class _HttpResponse:
    status: int
    body: Any


class HomeAssistantProvider(SmartHomeProvider):
    """Local Home Assistant REST client.

    The long-lived token stays in the brain process and is never sent to the
    tablet or to an ESP32. Network I/O is moved off the asyncio event loop.
    """

    def __init__(self, base_url: str, token: str, *, timeout_seconds: float = 4.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.timeout_seconds = timeout_seconds

    @property
    def provider_id(self) -> str:
        return "home_assistant"

    @property
    def connected(self) -> bool:
        return bool(self.base_url and self.token)

    async def list_devices(self) -> list[SmartHomeDevice]:
        if not self.connected:
            return []
        try:
            response = await self._request("GET", "/api/states")
        except (asyncio.TimeoutError, HTTPError, URLError, OSError):
            return []
        if response.status != 200 or not isinstance(response.body, list):
            return []
        devices: list[SmartHomeDevice] = []
        for state in response.body:
            entity_id = str(state.get("entity_id", ""))
            domain, separator, _ = entity_id.partition(".")
            if not separator or domain not in _DOMAIN_TYPES:
                continue
            attributes = dict(state.get("attributes") or {})
            name = str(attributes.get("friendly_name") or entity_id)
            current_state = str(state.get("state", "unknown"))
            devices.append(SmartHomeDevice(
                id=f"home_assistant:{entity_id}",
                provider_id=entity_id,
                provider=self.provider_id,
                name=name,
                structure_id="home_assistant",
                structure_name="Casa",
                room=str(attributes.get("room") or attributes.get("area_name") or "") or None,
                type=_DOMAIN_TYPES[domain],
                online=current_state not in {"unavailable", "unknown"},
                capabilities=_capabilities(domain, attributes),
                provider_type=domain,
                is_primary=bool(attributes.get("robot_primary", False)),
            ))
        return devices

    async def execute(self, request_id: str, action: str, device_id: str, value: Any = None) -> SmartHomeCommandResult:
        if not self.connected:
            return SmartHomeCommandResult(False, request_id, SmartHomeErrorCode.PROVIDER_OFFLINE, "Home Assistant não está configurado.")
        started = time.monotonic()
        try:
            if action == "get_state":
                response = await self._request("GET", f"/api/states/{device_id}")
            else:
                domain, separator, _ = device_id.partition(".")
                if not separator:
                    raise ValueError("entity_id inválido")
                service, payload = self._service_call(domain, action, device_id, value)
                response = await self._request("POST", f"/api/services/{domain}/{service}", payload)
            latency = (time.monotonic() - started) * 1000
            if response.status < 200 or response.status >= 300:
                return SmartHomeCommandResult(False, request_id, SmartHomeErrorCode.COMMAND_FAILED, f"Home Assistant respondeu HTTP {response.status}.", provider_latency_ms=latency)
            state = response.body if isinstance(response.body, dict) else {"response": response.body}
            return SmartHomeCommandResult(True, request_id, message="Pronto.", state=state, provider_latency_ms=latency)
        except asyncio.TimeoutError:
            return SmartHomeCommandResult(False, request_id, SmartHomeErrorCode.TIMEOUT, "Home Assistant demorou para responder.")
        except (HTTPError, URLError, OSError) as exc:
            return SmartHomeCommandResult(False, request_id, SmartHomeErrorCode.PROVIDER_OFFLINE, f"Não consegui acessar o Home Assistant: {exc}")
        except (TypeError, ValueError) as exc:
            return SmartHomeCommandResult(False, request_id, SmartHomeErrorCode.CAPABILITY_UNSUPPORTED, str(exc))

    def _service_call(self, domain: str, action: str, device_id: str, value: Any) -> tuple[str, dict[str, Any]]:
        payload: dict[str, Any] = {"entity_id": device_id}
        if action in {"turn_on", "turn_off"}:
            if domain == "cover":
                return ("open_cover" if action == "turn_on" else "close_cover"), payload
            if domain == "lock":
                return ("unlock" if action == "turn_on" else "lock"), payload
            return action, payload
        if action == "set_brightness" and domain == "light":
            payload["brightness_pct"] = max(0, min(100, int(value)))
            return "turn_on", payload
        if action == "set_temperature" and domain == "climate":
            payload["temperature"] = float(value)
            return "set_temperature", payload
        raise ValueError(f"{domain} não suporta a ação {action}")

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> _HttpResponse:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._request_sync, method, path, payload),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            raise asyncio.TimeoutError from exc

    def _request_sync(self, method: str, path: str, payload: dict[str, Any] | None) -> _HttpResponse:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read()
            return _HttpResponse(response.status, json.loads(raw) if raw else {})
