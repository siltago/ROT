"""Top-level orchestrator: wires perception -> identity -> decision ->
planning -> permission/execution -> response for a single user turn.

This is the only module that calls across brain/personality/emotions/memory/
actions in sequence. Callers (app/main.py, future api/) just call
`RobotAgent.process_turn(...)`; they never touch the subsystems directly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from actions.executor import ActionExecutor
from brain.context import ContextBuilder
from brain.decision_engine import DecisionEngine
from brain.models import ActionRecord, BrainEvent, Decision, IntentType, Turn
from brain.planner import Planner
from brain.response_engine import ResponseEngine
from emotions.engine import EmotionalEngine
from emotions.events import EmotionEvent
from memory.long_term import LongTermMemory, MemoryKind, MemoryRecord, score_candidate
from memory.people import PeopleDirectory, PersonProfile
from memory.short_term import ShortTermMemory
from personality.personality import Personality

EventSink = Callable[[BrainEvent], None]


def print_event_sink(event: BrainEvent) -> None:
    """Default observability sink: structured, human-readable lines.

    Never prints raw model chain-of-thought -- only the structured decision
    fields already present on the event.
    """
    lines = [f"{k.upper()}: {v}" for k, v in event.data.items()]
    print("\n".join(lines))


@dataclass
class TurnResult:
    reply: str
    decision: Decision
    action_records: list[ActionRecord] = field(default_factory=list)
    person: PersonProfile | None = None


class RobotAgent:
    def __init__(
        self,
        *,
        decision_engine: DecisionEngine,
        planner: Planner,
        executor: ActionExecutor,
        context_builder: ContextBuilder,
        response_engine: ResponseEngine,
        personality: Personality,
        emotional_engine: EmotionalEngine,
        people: PeopleDirectory,
        long_term: LongTermMemory,
        short_term: ShortTermMemory,
        event_sink: EventSink = print_event_sink,
    ) -> None:
        self.decision_engine = decision_engine
        self.planner = planner
        self.executor = executor
        self.context_builder = context_builder
        self.response_engine = response_engine
        self.personality = personality
        self.emotional_engine = emotional_engine
        self.people = people
        self.long_term = long_term
        self.short_term = short_term
        self.event_sink = event_sink

    async def process_turn(self, text: str, person_id: str | None = None) -> TurnResult:
        start = time.monotonic()

        self.emotional_engine.decay()

        person = self.people.get_or_create(person_id) if person_id else None

        self.short_term.add(Turn(speaker="user", text=text, person_id=person_id))

        decision = self.decision_engine.classify(text)

        context = self.context_builder.build(
            person=person,
            personality=self.personality.traits,
            emotion=self.emotional_engine.state,
        )

        plan = self.planner.plan(decision)
        action_records = await self.executor.execute_many(plan.valid_actions)

        for record in action_records:
            event = EmotionEvent.SUCCESSFUL_ACTION if record.outcome and record.outcome.success else EmotionEvent.FAILED_ACTION
            self.emotional_engine.apply_event(event)

        if decision.memory_candidate:
            importance = score_candidate(decision.memory_candidate)
            self.long_term.remember(
                MemoryRecord(
                    kind=MemoryKind.SEMANTIC,
                    text=decision.memory_candidate,
                    person_id=person.id if person else None,
                    importance=importance,
                )
            )

        reply = await self.response_engine.generate(decision, context, action_records)
        self.short_term.add(Turn(speaker="robot", text=reply, person_id=person_id))

        latency_ms = round((time.monotonic() - start) * 1000, 1)

        self.event_sink(
            BrainEvent(
                event="turn_processed",
                data={
                    "person": person.id if person else "unknown",
                    "intent": decision.type.value,
                    "confidence": decision.confidence,
                    "mood": self.emotional_engine.state.mood_label(),
                    "plan": ", ".join(
                        f"{a.name}({', '.join(f'{k}={v}' for k, v in a.arguments.items())})"
                        for a in plan.valid_actions
                    ) or "none",
                    "confirmation": any(r.required_confirmation for r in action_records),
                    "execution": (
                        "n/a" if not action_records
                        else "success" if all(r.outcome and r.outcome.success for r in action_records)
                        else "partial_or_failed"
                    ),
                    "latency_ms": latency_ms,
                },
            )
        )

        self.emotional_engine.save()

        return TurnResult(reply=reply, decision=decision, action_records=action_records, person=person)
