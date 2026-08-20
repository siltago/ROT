import pytest

from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy
from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, ActionRequest, RiskLevel


async def _ok_handler(room: str) -> ActionOutcome:
    return ActionOutcome(success=True, message=f"ok:{room}")


async def _failing_handler() -> ActionOutcome:
    raise RuntimeError("boom")


def _registry_with(spec: ActionSpec) -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(spec)
    return registry


@pytest.mark.asyncio
async def test_executes_registered_low_risk_action_without_confirmation():
    registry = _registry_with(
        ActionSpec(
            name="light.turn_on",
            description="turn on light",
            handler=_ok_handler,
            parameters={"room": str},
            risk_level=RiskLevel.LOW,
            requires_confirmation=False,
        )
    )
    executor = ActionExecutor(registry, PermissionPolicy())

    record = await executor.execute(ActionRequest(name="light.turn_on", arguments={"room": "sala"}))

    assert record.outcome.success is True
    assert record.outcome.message == "ok:sala"
    assert record.confirmed is True


@pytest.mark.asyncio
async def test_unknown_action_fails_without_raising():
    registry = ActionRegistry()
    executor = ActionExecutor(registry, PermissionPolicy())

    record = await executor.execute(ActionRequest(name="does.not.exist", arguments={}))

    assert record.outcome.success is False
    assert "Unknown action" in record.outcome.message


@pytest.mark.asyncio
async def test_invalid_arguments_are_rejected_before_execution():
    registry = _registry_with(
        ActionSpec(
            name="light.turn_on",
            description="turn on light",
            handler=_ok_handler,
            parameters={"room": str},
        )
    )
    executor = ActionExecutor(registry, PermissionPolicy())

    record = await executor.execute(ActionRequest(name="light.turn_on", arguments={}))

    assert record.outcome.success is False
    assert "Missing required parameter" in record.outcome.message


@pytest.mark.asyncio
async def test_high_risk_action_denied_without_confirmation():
    registry = _registry_with(
        ActionSpec(
            name="door.unlock",
            description="unlock door",
            handler=_ok_handler,
            parameters={"room": str},
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
        )
    )
    executor = ActionExecutor(registry, PermissionPolicy())  # default confirmation_provider = auto_deny

    record = await executor.execute(ActionRequest(name="door.unlock", arguments={"room": "principal"}))

    assert record.outcome.success is False
    assert record.confirmed is False
    assert record.required_confirmation is True


@pytest.mark.asyncio
async def test_high_risk_action_executes_when_confirmed():
    registry = _registry_with(
        ActionSpec(
            name="door.unlock",
            description="unlock door",
            handler=_ok_handler,
            parameters={"room": str},
            risk_level=RiskLevel.HIGH,
            requires_confirmation=True,
        )
    )

    async def always_confirm(spec, arguments) -> bool:
        return True

    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=always_confirm))

    record = await executor.execute(ActionRequest(name="door.unlock", arguments={"room": "principal"}))

    assert record.outcome.success is True
    assert record.confirmed is True


@pytest.mark.asyncio
async def test_handler_exception_is_captured_as_failed_outcome():
    registry = _registry_with(
        ActionSpec(
            name="broken.action",
            description="always raises",
            handler=_failing_handler,
            parameters={},
        )
    )
    executor = ActionExecutor(registry, PermissionPolicy())

    record = await executor.execute(ActionRequest(name="broken.action", arguments={}))

    assert record.outcome.success is False
    assert "boom" in record.outcome.message
