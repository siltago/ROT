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

logger = logging.getLogger(__name__)


def _describe_outcome(record: ActionRecord) -> str:
    if record.outcome and record.outcome.success:
        return record.outcome.message
    if record.outcome:
        return f"não consegui: {record.outcome.message}"
    return f"'{record.name}' não foi executado"


def _build_system_prompt(context: TurnContext) -> str:
    person_line = (
        f"Você está falando com {context.person.name} (relação: {context.person.relationship})."
        if context.person
        else "Você não sabe com certeza quem está falando."
    )
    return (
        "Você é o cérebro de um robô social/assistente pessoal. "
        "Responda sempre em português do Brasil, em uma ou duas frases, sem markdown.\n"
        f"{person_line}\n"
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
            parts.append(" e ".join(results) + ".")

        if decision.type in (IntentType.DIALOGUE, IntentType.DIALOGUE_AND_ACTION, IntentType.QUESTION):
            parts.append(await self._dialogue_reply(decision, context))
        elif not action_records:
            parts.append("Não tenho certeza do que fazer com isso ainda.")

        reply = " ".join(p for p in parts if p).strip()
        return reply or "Feito."

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
        mood = context.emotion.mood_label()
        if decision.type == IntentType.QUESTION:
            return "Boa pergunta -- ainda não tenho uma resposta elaborada para isso, mas estou anotando."
        if decision.memory_candidate:
            return "Faz sentido, vou guardar isso."
        if mood == "curious":
            return "Interessante, me conta mais."
        return "Entendi."
