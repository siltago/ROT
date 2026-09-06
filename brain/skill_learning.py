"""Orchestrates one skill-teaching attempt at a time: from the LLM router
spotting a teachable request, through an optional clarifying question,
through the actual "teaching" LLM call, to either saving+registering the
new skill immediately (low risk) or asking the user to approve it once
(medium/high risk).

State lives on `RobotAgent` (see `brain/agent.py`), not on a tablet-only
`DeviceSession`, specifically so this works identically whether the turn
came from `app/main.py`'s CLI loop or `api/server.py`'s tablet bridge --
both already just call `agent.process_turn(text)` per turn.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable

from integrations.llm.base import LLMProvider
from brain.models import RiskLevel
from personality.voice import learning_confirm
from skills.models import LearnedSkillRecord
from skills.registrar import SkillRegistrar
from skills.teaching_prompt import TeachingError, build_prompt, parse_teaching_response, validate_call_actions_exist

logger = logging.getLogger(__name__)

Speak = Callable[[str], Awaitable[None]]


class SkillTeachStatus(Enum):
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_APPROVAL = "ready_for_approval"
    LEARNED = "learned"
    FAILED = "failed"


@dataclass
class SkillTeachResult:
    status: SkillTeachStatus
    message: str
    record: LearnedSkillRecord | None = None


@dataclass
class SkillLearningState:
    """At most one skill-teaching attempt in flight per agent (v1 scope)."""
    active: bool = False
    original_utterance: str = ""
    clarifying_question: str | None = None
    awaiting_approval: bool = False
    pending_record: LearnedSkillRecord | None = None

    def reset(self) -> None:
        self.active = False
        self.original_utterance = ""
        self.clarifying_question = None
        self.awaiting_approval = False
        self.pending_record = None


class SkillTeacher:
    def __init__(
        self, *, llm_provider: LLMProvider | None, registrar: SkillRegistrar,
        speak_resolver: Callable[[], Speak],
    ) -> None:
        self.llm_provider = llm_provider
        self.registrar = registrar
        self.speak_resolver = speak_resolver

    async def start(self, utterance: str) -> SkillTeachResult:
        return await self._teach(utterance, utterance)

    async def continue_with_answer(self, original_utterance: str, clarifying_question: str, answer: str) -> SkillTeachResult:
        combined = (
            f"Pedido original: {original_utterance}\n"
            f"Pergunta feita ao usuário: {clarifying_question}\n"
            f"Resposta do usuário: {answer}"
        )
        result = await self._teach(combined, original_utterance)
        if result.status is SkillTeachStatus.NEEDS_CLARIFICATION:
            # v1 supports exactly one clarification round -- asking again
            # would risk an unbounded back-and-forth, so this attempt is
            # abandoned rather than looped.
            logger.info("Skill teaching asked for a second clarification; giving up for this attempt")
            return SkillTeachResult(SkillTeachStatus.FAILED, "Ainda não entendi direito, deixa pra lá por enquanto.")
        return result

    def approve(self, record: LearnedSkillRecord) -> None:
        self.registrar.skill_library.add(record)
        self.registrar.register_learned(record, speak_resolver=self.speak_resolver)

    async def _teach(self, prompt_user_text: str, original_utterance: str) -> SkillTeachResult:
        if self.llm_provider is None:
            return SkillTeachResult(SkillTeachStatus.FAILED, "Não consigo aprender coisas novas agora.")
        specs = self.registrar.registry.all()
        try:
            raw = await self.llm_provider.generate(system=build_prompt(specs), user=prompt_user_text)
        except Exception:
            logger.warning("Skill teaching call failed", exc_info=True)
            return SkillTeachResult(SkillTeachStatus.FAILED, "Não consegui aprender isso agora.")

        try:
            question, record = parse_teaching_response(raw, original_utterance)
            if record is not None:
                validate_call_actions_exist(record, {spec.name for spec in specs})
        except TeachingError:
            logger.warning("Skill teaching response failed validation", exc_info=True)
            return SkillTeachResult(SkillTeachStatus.FAILED, "Não consegui aprender isso direito, melhor não arriscar.")

        if question is not None:
            return SkillTeachResult(SkillTeachStatus.NEEDS_CLARIFICATION, question)

        assert record is not None
        if record.risk_level is RiskLevel.LOW:
            self.approve(record)
            return SkillTeachResult(SkillTeachStatus.LEARNED, f"Aprendi: {record.description}.", record=record)
        return SkillTeachResult(SkillTeachStatus.READY_FOR_APPROVAL, learning_confirm(record.description), record=record)
