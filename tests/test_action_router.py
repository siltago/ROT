import json

import pytest

from actions.registry import ActionRegistry, ActionSpec
from brain.action_router import LlmActionRouter
from brain.models import ActionOutcome, IntentType
from integrations.llm.base import LLMProvider


class FakeLLM(LLMProvider):
    def __init__(self, response: str) -> None:
        self.response = response

    async def generate(self, *, system: str, user: str, history: str = "") -> str:
        return self.response


async def _noop(**kwargs) -> ActionOutcome:
    return ActionOutcome(success=True, message="ok")


def _registry_with_one_action() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(ActionSpec(name="music.play", description="toca música", handler=_noop, parameters={"query": str}))
    return registry


@pytest.mark.asyncio
async def test_matched_action_is_unaffected_by_the_learnable_addition() -> None:
    llm = FakeLLM(json.dumps({"action": "music.play", "arguments": {"query": "Metallica"}}))
    router = LlmActionRouter(llm, _registry_with_one_action())

    outcome = await router.route("toca Metallica")

    assert outcome.decision is not None
    assert outcome.decision.type is IntentType.ACTION
    assert outcome.decision.actions[0].name == "music.play"
    assert outcome.learnable_hint is None


@pytest.mark.asyncio
async def test_plain_dialogue_is_unaffected_by_the_learnable_addition() -> None:
    llm = FakeLLM(json.dumps({"action": None}))
    router = LlmActionRouter(llm, _registry_with_one_action())

    outcome = await router.route("oi, tudo bem?")

    assert outcome.decision is None
    assert outcome.learnable_hint is None


@pytest.mark.asyncio
async def test_learnable_request_surfaces_a_hint_without_inventing_an_action() -> None:
    llm = FakeLLM(json.dumps({"action": None, "learnable": True, "skill_hint": "timer"}))
    router = LlmActionRouter(llm, _registry_with_one_action())

    outcome = await router.route("coloque um timer de 15 minutos")

    assert outcome.decision is None
    assert outcome.learnable_hint == "timer"
