"""Turns a Decision + TurnContext + action results into a natural-language
reply.

Dialogue/question turns are handed to an optional LLMProvider for free-form
conversation; action-result phrasing stays local/deterministic (fast, no
external call needed). If no provider is configured, or the provider call
fails, falls back to a deterministic template so a turn never goes
unanswered because of a network hiccup or missing local model.
"""
from __future__ import annotations

import logging

from brain.context import TurnContext
from brain.models import ActionRecord, Decision, IntentType
from integrations.llm.base import LLMProvider
from personality.voice import YBI_VOICE, action_failure, action_success

logger = logging.getLogger(__name__)


def _describe_outcome(record: ActionRecord) -> str:
    if record.outcome and record.outcome.success:
        return action_success(record.outcome.message)
    if record.outcome:
        if record.outcome.message.endswith("?"):
            return record.outcome.message
        return action_failure(record.outcome.message)
    return action_failure(f"{record.name} não foi executado")


def _build_system_prompt(context: TurnContext) -> str:
    person_line = (
        f"Você está falando com {context.person.name} (relação: {context.person.relationship})."
        if context.person
        else "Você não sabe com certeza quem está falando."
    )
    memory_line = ""
    if context.relevant_memories:
        facts = "; ".join(m.text for m in context.relevant_memories)
        memory_line = f"O que você lembra sobre essa pessoa: {facts}. Use isso só quando for natural, sem forçar.\n"
    return (
        f"{YBI_VOICE.prompt()}\n\n"
        "CONTEXTO DESTE TURNO\n"
        f"{person_line}\n"
        f"{memory_line}"
        f"Estado emocional atual: {context.emotion.mood_label()}.\n"
        f"{context.style.as_prompt_fragment()}"
    )


class ResponseEngine:
    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    async def generate(
        self,
        decision: Decision,
        context: TurnContext,
        action_records: list[ActionRecord],
    ) -> str:
        parts: list[str] = []

        if action_records:
            results = [_describe_outcome(r) for r in action_records]
            parts.append(" e ".join(results))

        if decision.type in (IntentType.DIALOGUE, IntentType.DIALOGUE_AND_ACTION, IntentType.QUESTION):
            parts.append(await self._dialogue_reply(decision, context))
        elif not action_records:
            parts.append("Hmm… não entendi direito o que você quer que eu faça.")

        reply = " ".join(p for p in parts if p).strip()
        return reply or "Tô aqui."

    async def _dialogue_reply(self, decision: Decision, context: TurnContext) -> str:
        if self.llm_provider is not None:
            try:
                return await self.llm_provider.generate(
                    system=_build_system_prompt(context),
                    user=decision.raw_text,
                    history=context.recent_dialogue,
                )
            except Exception as exc:  # noqa: BLE001 -- external provider is untrusted-ish, never break the turn
                logger.warning("LLM provider failed (%s), falling back to template reply", exc)

        return self._template_reply(decision, context)

    @staticmethod
    def _template_reply(decision: Decision, context: TurnContext) -> str:
        if decision.raw_text.strip().lower().rstrip("!.") in {"oi", "olá", "ola", "e aí", "e ai"}:
            return "Oi. Eu tava te ouvindo."
        mood = context.emotion.mood_label()
        if decision.type == IntentType.QUESTION:
            return "Essa eu ainda não sei responder direito. Prefiro admitir a inventar."
        if decision.memory_candidate:
            return "Tá, isso é importante. Vou lembrar."
        if mood == "curious":
            return "Hmm… continua, quero entender."
        return "Tô acompanhando."
