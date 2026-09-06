"""Deterministic contextual behaviors that only propose responses/actions."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from brain.cognition_config import CognitionConfig
from brain.context_evaluator import ContextEvaluator, DerivedContext
from brain.drives import DriveState
from brain.events import EventType, RobotEvent
from brain.world_state import WorldState


class ProposalType(StrEnum):
    COMMENT = "comment"
    QUESTION = "question"
    SUGGESTION = "suggestion"
    ACTION = "action"


@dataclass(frozen=True)
class BehaviorProposal:
    # First four fields preserve the v0.1 constructor.
    name: str
    priority: float
    response_hint: str | None = None
    proposed_action: str | None = None
    type: ProposalType = ProposalType.COMMENT
    confidence: float = 1.0
    reason: str = ""
    requires_llm: bool = False
    id: str = field(default_factory=lambda: str(uuid4()), compare=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc), compare=False)
    expires_at: datetime | None = field(default=None, compare=False)

    @property
    def behavior_name(self) -> str:
        return self.name

    @property
    def suggested_action(self) -> str | None:
        return self.proposed_action

    @property
    def suggested_response(self) -> str | None:
        return self.response_hint

    def expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and (now or datetime.now(timezone.utc)) >= self.expires_at


@dataclass(frozen=True)
class BehaviorContext:
    world_state: WorldState
    derived_context: DerivedContext
    emotional_state: Any = None
    drives: DriveState = field(default_factory=DriveState)
    personality: Any = None
    recent_events: tuple[RobotEvent, ...] = ()


class ContextualBehavior(Protocol):
    name: str

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None: ...


def _proposal(name: str, priority: float, response: str, reason: str, config: CognitionConfig, *, type: ProposalType = ProposalType.COMMENT, confidence: float = 0.9, action: str | None = None, requires_llm: bool = False) -> BehaviorProposal:
    return BehaviorProposal(name, max(0.0, min(1.0, priority)), response, action, type, confidence, reason, requires_llm, expires_at=datetime.now(timezone.utc) + timedelta(seconds=config.proposal_ttl_seconds))


class GreetingBehavior:
    name = "GreetingBehavior"

    def __init__(self, config: CognitionConfig) -> None:
        self.config = config

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None:
        if event.type not in (EventType.PERSON_DETECTED, EventType.USER_RETURNED) or context.world_state.user_speaking:
            return None
        person = str(event.data.get("person_id") or "unknown")
        return _proposal(self.name, 0.82, f"Olá, {person}! Que bom ver você.", "person_arrived", self.config, confidence=float(event.data.get("confidence", 0.9)))


class WeatherBehavior:
    name = "WeatherBehavior"

    def __init__(self, config: CognitionConfig) -> None:
        self.config = config

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None:
        if event.type not in (EventType.WEATHER_UPDATED, EventType.TEMPERATURE_CHANGED):
            return None
        current = context.world_state.environment.temperature
        previous = context.world_state.environment.previous_temperature
        if current is None:
            return None
        delta = abs(current - previous) if previous is not None else float(event.data.get("delta", 0))
        if delta < self.config.significant_temperature_delta and event.type == EventType.TEMPERATURE_CHANGED:
            return None
        if context.derived_context.environment_hot:
            text, reason = "Esquentou bastante por aqui.", "environment_hot"
        elif context.derived_context.environment_cold:
            text, reason = "Está ficando bem frio por aqui.", "environment_cold"
        else:
            text, reason = "A temperatura mudou por aqui.", "temperature_changed"
        return _proposal(self.name, 0.42 + min(delta / 20, 0.18), text, reason, self.config, confidence=0.92)


class IdleBehavior:
    name = "IdleBehavior"

    def __init__(self, config: CognitionConfig) -> None:
        self.config = config

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None:
        if event.type != EventType.IDLE_TIMEOUT or not context.derived_context.social_opportunity:
            return None
        priority = 0.32 + 0.35 * context.drives.social
        return _proposal(self.name, priority, "Quer conversar sobre alguma coisa?", "long_idle_with_user_present", self.config, type=ProposalType.QUESTION)


class PlayfulIdleBehavior:
    """Entertains itself when idle -- doesn't need anyone present, unlike
    IdleBehavior (which tries to pull a present human into conversation)."""

    name = "PlayfulIdleBehavior"

    def __init__(self, config: CognitionConfig) -> None:
        self.config = config

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None:
        if event.type != EventType.IDLE_TIMEOUT:
            return None
        idle_seconds = float(event.data.get("idle_seconds", 0))
        if idle_seconds < self.config.playful_idle_seconds:
            return None
        priority = 0.30 + 0.35 * context.drives.playfulness
        return _proposal(self.name, priority, None, "self_entertainment", self.config, type=ProposalType.ACTION, action="idle.play")


class SleepBehavior:
    """Proposes dozing off once tired (drives.rest) and idle for a while."""

    name = "SleepBehavior"

    def __init__(self, config: CognitionConfig) -> None:
        self.config = config

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None:
        if event.type != EventType.IDLE_TIMEOUT:
            return None
        idle_seconds = float(event.data.get("idle_seconds", 0))
        if idle_seconds < self.config.sleep_idle_seconds or context.drives.rest < self.config.sleepy_rest_threshold:
            return None
        priority = 0.40 + 0.40 * context.drives.rest
        return _proposal(self.name, priority, "Vou tirar uma soneca...", "tired_and_idle", self.config, type=ProposalType.ACTION, action="robot.sleep", confidence=0.85)


class CuriosityBehavior:
    name = "CuriosityBehavior"

    def __init__(self, config: CognitionConfig) -> None:
        self.config = config

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None:
        if event.type not in (EventType.UNKNOWN_PERSON_DETECTED, EventType.NEW_OBJECT_DETECTED, EventType.UNUSUAL_EVENT):
            return None
        novelty = max(0.0, min(1.0, float(event.data.get("novelty", 0.8))))
        priority = 0.30 + 0.30 * context.drives.curiosity + 0.20 * novelty
        return _proposal(self.name, priority, "O que é isso? Fiquei curioso.", "novel_event", self.config, type=ProposalType.QUESTION, confidence=novelty)


class SocialBehavior:
    name = "SocialBehavior"

    def __init__(self, config: CognitionConfig) -> None:
        self.config = config

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None:
        if event.type == EventType.CONVERSATION_ENDED and context.world_state.people_present:
            return _proposal(self.name, 0.34 + 0.25 * context.drives.social, "Gostei de conversar com você.", "conversation_ended", self.config)
        return None


class HelpfulnessBehavior:
    name = "HelpfulnessBehavior"

    def __init__(self, config: CognitionConfig) -> None:
        self.config = config

    def evaluate(self, event: RobotEvent, context: BehaviorContext) -> BehaviorProposal | None:
        text = str(event.data.get("text", "")).lower()
        if event.type != EventType.USER_SPOKE or not any(term in text for term in ("tá escuro", "ta escuro", "está escuro", "esta escuro")):
            return None
        priority = 0.45 + 0.25 * context.drives.helpfulness
        return _proposal(self.name, priority, "Quer que eu acenda a luz?", "clear_help_opportunity", self.config, type=ProposalType.SUGGESTION, action="light.turn_on")


class BehaviorEngine:
    def __init__(self, config: CognitionConfig = CognitionConfig(), behaviors: list[ContextualBehavior] | None = None) -> None:
        self.config = config
        self.behaviors = behaviors or [GreetingBehavior(config), WeatherBehavior(config), IdleBehavior(config), PlayfulIdleBehavior(config), SleepBehavior(config), CuriosityBehavior(config), SocialBehavior(config), HelpfulnessBehavior(config)]

    def evaluate(self, event: RobotEvent | EventType | str, context: BehaviorContext | WorldState) -> list[BehaviorProposal]:
        # Compatibility mappings from v0.1 names.
        aliases = {"user_session_started": EventType.PERSON_DETECTED, "conversation_interesting": EventType.UNUSUAL_EVENT}
        if not isinstance(event, RobotEvent):
            raw = str(event)
            if raw == "user_session_started":
                return [BehaviorProposal("greet_user", 0.9, "Cumprimente brevemente.")]
            kind = aliases.get(raw, EventType(raw) if raw in EventType._value2member_map_ else EventType.UNUSUAL_EVENT)
            event = RobotEvent(type=kind, data={"person_id": "usuário"} if raw == "user_session_started" else {})
        if isinstance(context, WorldState):
            context = BehaviorContext(context, ContextEvaluator(self.config).evaluate(context))
        return [proposal for behavior in self.behaviors if (proposal := behavior.evaluate(event, context)) is not None]


class ProposalArbiter:
    def select(self, proposals: list[BehaviorProposal], context: BehaviorContext, *, now: datetime | None = None) -> BehaviorProposal | None:
        now = now or datetime.now(timezone.utc)
        if context.derived_context.user_busy or not context.derived_context.initiative_allowed:
            return None
        eligible = [p for p in proposals if not p.expired(now)]
        return max(eligible, key=lambda p: (p.priority * p.confidence, p.priority), default=None)


@dataclass(frozen=True)
class InitiativeConfig:
    enabled: bool = True
    level: float = 0.4
    minimum_priority: float = 0.35
    cooldown_seconds: float = 120
    max_per_hour: int = 4
    behavior_cooldowns: dict[str, float] = field(default_factory=dict)


class InitiativeState(StrEnum):
    IDLE = "idle"
    EVALUATING = "evaluating"
    PROPOSAL_READY = "proposal_ready"
    SUPPRESSED = "suppressed"
    EXECUTING = "executing"
    COOLDOWN = "cooldown"


@dataclass
class InitiativeMetrics:
    proposals_created: int = 0
    proposals_suppressed: int = 0
    initiatives_executed: int = 0
    initiative_llm_calls: int = 0


class InitiativeEngine:
    def __init__(self, config: InitiativeConfig = InitiativeConfig()) -> None:
        self.config = config
        self.state = InitiativeState.IDLE
        self.metrics = InitiativeMetrics()
        self._last_at: float | None = None
        self._last_by_behavior: dict[str, float] = {}
        self._accepted: list[float] = []

    def select(self, proposals: list[BehaviorProposal], world: WorldState, *, now: float | None = None, derived: DerivedContext | None = None) -> BehaviorProposal | None:
        timestamp = time.monotonic() if now is None else now
        self.state = InitiativeState.EVALUATING
        self.metrics.proposals_created += len(proposals)
        blocked = not self.config.enabled or world.user_speaking or world.robot_speaking or world.processing or (derived is not None and (derived.quiet_period or not derived.initiative_allowed))
        self._accepted = [value for value in self._accepted if timestamp - value < 3600]
        if blocked or len(self._accepted) >= self.config.max_per_hour or (self._last_at is not None and timestamp - self._last_at < self.config.cooldown_seconds):
            return self._suppress(len(proposals))
        eligible = []
        effective_minimum = max(self.config.minimum_priority, 1.0 - self.config.level)
        for proposal in proposals:
            cooldown = self.config.behavior_cooldowns.get(proposal.name, 0)
            last = self._last_by_behavior.get(proposal.name)
            if proposal.expired() or proposal.priority < effective_minimum or (last is not None and timestamp - last < cooldown):
                continue
            eligible.append(proposal)
        if not eligible:
            return self._suppress(len(proposals))
        selected = max(eligible, key=lambda p: (p.priority * p.confidence, p.priority))
        self._last_at = timestamp
        self._last_by_behavior[selected.name] = timestamp
        self._accepted.append(timestamp)
        self.state = InitiativeState.PROPOSAL_READY
        return selected

    def mark_started(self) -> None:
        self.state = InitiativeState.EXECUTING

    def mark_completed(self, proposal: BehaviorProposal) -> None:
        self.metrics.initiatives_executed += 1
        self.metrics.initiative_llm_calls += int(proposal.requires_llm)
        self.state = InitiativeState.COOLDOWN

    def _suppress(self, count: int) -> None:
        self.metrics.proposals_suppressed += count
        self.state = InitiativeState.SUPPRESSED
        return None
