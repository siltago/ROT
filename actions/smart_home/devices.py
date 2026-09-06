"""Safe ActionRegistry handlers backed by the provider-neutral service."""
from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel
from integrations.smart_home.service import SmartHomeService


def register(registry: ActionRegistry, service: SmartHomeService) -> None:
    async def run(action: str, target: str, value=None) -> ActionOutcome:
        result = await service.execute(action, target, value=value)
        return ActionOutcome(success=result.success, message=result.message, data={"request_id": result.request_id, "error_code": result.error_code.value if result.error_code else None, "state": result.state})

    async def turn_on(target: str) -> ActionOutcome:
        return await run("turn_on", target)
    async def turn_off(target: str) -> ActionOutcome:
        return await run("turn_off", target)
    async def set_brightness(target: str, value: int) -> ActionOutcome:
        return await run("set_brightness", target, value)
    async def set_temperature(target: str, value: float) -> ActionOutcome:
        return await run("set_temperature", target, value)
    async def get_state(target: str) -> ActionOutcome:
        return await run("get_state", target)
    async def list_devices() -> ActionOutcome:
        devices = await service.synchronize()
        return ActionOutcome(success=True, message=f"Encontrei {len(devices)} dispositivos.", data={"devices": [d.id for d in devices]})
    async def legacy_turn_on(room: str) -> ActionOutcome:
        return await run("turn_on", f"luz {room}")
    async def legacy_turn_off(room: str) -> ActionOutcome:
        return await run("turn_off", f"luz {room}")
    async def legacy_temperature(temperature: float) -> ActionOutcome:
        return await run("set_temperature", "ar condicionado aqui", temperature)

    for name, handler, parameters in [
        ("smart_home.turn_on", turn_on, {"target": str}),
        ("smart_home.turn_off", turn_off, {"target": str}),
        ("smart_home.set_brightness", set_brightness, {"target": str, "value": int}),
        ("smart_home.set_temperature", set_temperature, {"target": str, "value": float}),
        ("smart_home.get_state", get_state, {"target": str}),
        ("smart_home.list_devices", list_devices, {}),
        ("light.turn_on", legacy_turn_on, {"room": str}),
        ("light.turn_off", legacy_turn_off, {"room": str}),
        ("climate.set_temperature", legacy_temperature, {"temperature": float}),
    ]:
        registry.register(ActionSpec(name=name, description=f"Provider-neutral smart home operation: {name}", handler=handler, parameters=parameters, risk_level=RiskLevel.LOW, requires_confirmation=False, timeout_seconds=5.0, permissions=["smart_home.control"]))
