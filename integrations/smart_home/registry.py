from __future__ import annotations

from collections import defaultdict

from integrations.smart_home.models import SmartHomeDevice, SmartHomeDeviceType


class SmartHomeDeviceRegistry:
    def __init__(self) -> None:
        self._devices: dict[str, SmartHomeDevice] = {}

    def replace_all(self, devices: list[SmartHomeDevice]) -> None:
        self._devices = {device.id: device for device in devices}

    def upsert(self, device: SmartHomeDevice) -> None:
        self._devices[device.id] = device

    def remove(self, device_id: str) -> None:
        self._devices.pop(device_id, None)

    def clear(self) -> None:
        self._devices.clear()

    def get(self, device_id: str) -> SmartHomeDevice | None:
        return self._devices.get(device_id)

    def all(self) -> list[SmartHomeDevice]:
        return list(self._devices.values())

    def by_room(self, room: str) -> list[SmartHomeDevice]:
        room = room.casefold().strip()
        return [device for device in self._devices.values() if (device.room or "").casefold() == room]

    def by_type(self, device_type: SmartHomeDeviceType) -> list[SmartHomeDevice]:
        return [device for device in self._devices.values() if device.type == device_type]

    def grouped_by_room(self) -> dict[str, list[SmartHomeDevice]]:
        grouped: dict[str, list[SmartHomeDevice]] = defaultdict(list)
        for device in self._devices.values():
            grouped[device.room or "Sem cômodo"].append(device)
        return dict(grouped)
