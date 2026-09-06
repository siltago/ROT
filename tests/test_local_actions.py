from actions.executor import ActionExecutor
from actions.permissions import PermissionPolicy, auto_deny
from actions.registry import ActionRegistry
from actions.utilities import local
from actions.music import player as music
from brain.decision_engine import DecisionEngine
from brain.models import ActionRequest, IntentType


async def test_time_date_and_status_are_registered_low_risk_actions() -> None:
    registry = ActionRegistry()
    local.register(registry)
    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    for name in ("time.get", "date.get", "system.status"):
        record = await executor.execute(ActionRequest(name=name))
        assert record.outcome is not None and record.outcome.success is True
        assert record.required_confirmation is False


def test_natural_time_question_routes_to_local_action() -> None:
    decision = DecisionEngine().classify("Que horas são?")
    assert decision.type == IntentType.ACTION
    assert decision.actions[0].name == "time.get"


async def test_music_without_query_returns_natural_clarification() -> None:
    registry = ActionRegistry()
    music.register(registry)
    executor = ActionExecutor(registry, PermissionPolicy(confirmation_provider=auto_deny))
    record = await executor.execute(ActionRequest(name="music.play", arguments={"query": ""}))
    assert record.outcome is not None
    assert record.outcome.message == "Qual música você quer ouvir?"


async def test_time_result_contains_clock_scene_context() -> None:
    outcome = await local.get_time("America/Sao_Paulo")
    assert outcome.success
    assert set(("time", "seconds", "date", "weekday", "period", "timezone")) <= outcome.data.keys()
    assert "hora" in outcome.message


def test_time_is_spoken_naturally_in_twelve_hour_form() -> None:
    assert local._spoken_time(21, 13) == "São 9 horas e 13 minutos"
