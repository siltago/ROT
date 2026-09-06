"""LLM-backed action selection for phrasing the regex rules don't cover.

`DecisionEngine` (brain/decision_engine.py) stays exactly as it is: a fast,
free, zero-latency first pass that recognizes common, previously-seen
phrasings via regex. This module is only consulted when that first pass
found nothing actionable -- so it never adds latency or cost to a command
that was already recognized -- and asks the LLM itself to pick a real,
already-registered action (or none) for whatever the user actually said.

This exists specifically so the set of things the robot can be told to do
in natural language doesn't have to grow one hand-written regex at a time
forever ("ei bob, entre no player", "que música está tocando" -- endless
phrasings of things that already have an action). The LLM decides; this
module only validates that decision against the real action registry
before it's allowed to run anything.

It also doubles as the entry point for teaching Bob something new: when
nothing in the catalog matches AND the phrasing reads like a request for a
capability that could reasonably be taught (not just chit-chat or a
question about something else), the same JSON response can say so instead
of `action: null` -- see `learnable_hint` on `RouterOutcome` and
`brain/skill_learning.py`, which is what actually does the teaching.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from actions.registry import ActionRegistry
from brain.action_catalog import format_catalog
from brain.models import ActionRequest, Decision, IntentType
from integrations.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_SYSTEM_TEMPLATE = (
    "Você decide se uma frase dita a um robô assistente deve disparar uma "
    "das ações abaixo, ou nenhuma.\n\n"
    "Ações disponíveis:\n{actions}\n\n"
    "Responda SOMENTE com um JSON no formato exato, sem texto ao redor. Três "
    "formatos possíveis:\n"
    '1. Ação reconhecida: {{"action": "<nome>", "arguments": {{...}}}}\n'
    '2. Nada a ver com uma ação (bate-papo, pergunta sobre outro assunto): '
    '{{"action": null}}\n'
    '3. A frase pede uma capacidade nova, que nenhuma ação acima cobre, mas '
    'que faria sentido o robô aprender a fazer (ex: "coloque um timer", '
    '"crie um lembrete") -- NÃO invente uma ação pra isso, em vez disso '
    'responda: {{"action": null, "learnable": true, "skill_hint": '
    '"<nome curto da capacidade, ex: timer>"}}\n\n'
    'Nunca invente um nome de ação fora da lista pra usar no formato 1. '
    'Preencha "arguments" só com os parâmetros pedidos por essa ação -- '
    "omita os que não foram ditos."
)


@dataclass
class RouterOutcome:
    decision: Decision | None
    # Set only for shape 3 above -- a short, LLM-proposed name for the new
    # capability, e.g. "timer". None for both "matched an action" and
    # "nothing to do here" -- callers must not treat those two cases the
    # same way (see brain/agent.py process_turn).
    learnable_hint: str | None = None


class LlmActionRouter:
    def __init__(self, llm_provider: LLMProvider | None, registry: ActionRegistry) -> None:
        self.llm_provider = llm_provider
        self.registry = registry

    async def route(self, text: str) -> RouterOutcome:
        """Returns a RouterOutcome. `.decision` is set if the LLM picked a
        real, valid, registered action. `.learnable_hint` is set if
        nothing matched but the phrasing looks like a teachable new
        capability. Both are None if the LLM is unavailable, picked
        nothing, or the response didn't check out -- callers should fall
        back to plain dialogue handling in that case, exactly as if this
        had never been called."""
        empty = RouterOutcome(decision=None, learnable_hint=None)
        if self.llm_provider is None:
            return empty
        specs = self.registry.all()
        if not specs:
            return empty
        try:
            raw = await self.llm_provider.generate(
                system=_SYSTEM_TEMPLATE.format(actions=format_catalog(specs)),
                user=text,
            )
        except Exception:
            logger.warning("LLM action routing failed", exc_info=True)
            return empty
        name, arguments, learnable_hint = self._parse(raw)
        if name is None:
            return RouterOutcome(decision=None, learnable_hint=learnable_hint)
        if self.registry.get(name) is None:
            logger.warning("LLM proposed an unknown action: %r", name)
            return empty
        errors = self.registry.validate_arguments(name, arguments)
        if errors:
            logger.warning("LLM proposed invalid arguments for %s: %s", name, errors)
            return empty
        logger.info("LLM-routed action: %s(%r)", name, arguments)
        decision = Decision(
            type=IntentType.ACTION,
            confidence=0.7,
            actions=[ActionRequest(name=name, arguments=arguments)],
            raw_text=text,
        )
        return RouterOutcome(decision=decision, learnable_hint=None)

    @staticmethod
    def _parse(raw: str) -> tuple[str | None, dict, str | None]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        try:
            data = json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            return None, {}, None
        if not isinstance(data, dict):
            return None, {}, None
        name = data.get("action")
        if not isinstance(name, str) or not name:
            hint = data.get("skill_hint")
            learnable = data.get("learnable") is True and isinstance(hint, str) and hint.strip()
            return None, {}, hint.strip() if learnable else None
        arguments = data.get("arguments")
        return name, arguments if isinstance(arguments, dict) else {}, None
