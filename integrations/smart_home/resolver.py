from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from integrations.smart_home.models import SmartHomeDevice, SmartHomeDeviceType
from integrations.smart_home.registry import SmartHomeDeviceRegistry


@dataclass(frozen=True)
class SmartHomeTargetSet:
    devices: tuple[SmartHomeDevice, ...] = ()
    clarification_required: bool = False
    clarification: str | None = None


_TYPE_ALIASES = {
    SmartHomeDeviceType.LIGHT: ("luz", "luzes", "lampada", "lampadas", "abajur", "led"),
    SmartHomeDeviceType.AIR_CONDITIONER: ("ar", "ar condicionado", "climatizador"),
    SmartHomeDeviceType.THERMOSTAT: ("termostato",),
    SmartHomeDeviceType.TV: ("tv", "televisao"),
    SmartHomeDeviceType.FAN: ("ventilador",),
    SmartHomeDeviceType.OUTLET: ("tomada",),
    SmartHomeDeviceType.SWITCH: ("interruptor",),
    SmartHomeDeviceType.BLIND: ("persiana", "cortina"),
    SmartHomeDeviceType.LOCK: ("fechadura", "porta"),
    SmartHomeDeviceType.SENSOR: ("sensor",),
    SmartHomeDeviceType.OTHER: ("aspirador", "robo aspirador"),
}


def normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


class SmartHomeTargetResolver:
    def __init__(self, registry: SmartHomeDeviceRegistry) -> None:
        self.registry = registry

    def resolve(self, phrase: str, *, current_room: str | None = None, collective: bool | None = None) -> SmartHomeTargetSet:
        text = normalize(phrase)
        inferred_type = next((kind for kind, aliases in _TYPE_ALIASES.items() if any(re.search(rf"\b{re.escape(alias)}\b", text) for alias in aliases)), None)
        room = normalize(current_room) if current_room and re.search(r"\b(aqui|este comodo|nesse comodo)\b", text) else None
        if room is None:
            room = next((normalize(device.room or "") for device in self.registry.all() if device.room and re.search(rf"\b{re.escape(normalize(device.room))}\b", text)), None)
        candidates = self.registry.all()
        if inferred_type:
            candidates = [device for device in candidates if device.type == inferred_type or (inferred_type == SmartHomeDeviceType.AIR_CONDITIONER and device.type == SmartHomeDeviceType.THERMOSTAT)]
        if room:
            candidates = [device for device in candidates if normalize(device.room or "") == room]
        exact_name = [device for device in candidates if normalize(device.name) in text]
        if exact_name:
            candidates = exact_name
        wants_many = collective if collective is not None else bool(re.search(r"\b(todas|todos|tudo|as luzes)\b", text))
        if wants_many:
            return SmartHomeTargetSet(tuple(candidates), not bool(candidates), "Não encontrei dispositivos compatíveis." if not candidates else None)
        if len(candidates) == 1:
            return SmartHomeTargetSet((candidates[0],))
        primary = [device for device in candidates if device.is_primary or "principal" in normalize(device.name)]
        if len(primary) == 1:
            return SmartHomeTargetSet((primary[0],))
        if not candidates:
            return SmartHomeTargetSet(clarification_required=True, clarification="Não encontrei esse dispositivo.")
        names = ", ".join(device.name for device in candidates[:4])
        return SmartHomeTargetSet(clarification_required=True, clarification=f"Qual deles: {names}?")
