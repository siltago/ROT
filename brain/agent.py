"""Top-level orchestrator: wires perception -> identity -> decision ->
planning -> permission/execution -> response for a single user turn.

This is the only module that calls across brain/personality/emotions/memory/
actions in sequence. Callers (app/main.py, future api/) just call
`RobotAgent.process_turn(...)`; they never touch the subsystems directly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from actions.executor import ActionExecutor
from brain.action_router import LlmActionRouter
from brain.context import ContextBuilder
from brain.behaviors import BehaviorEngine, BehaviorProposal, InitiativeEngine
from brain.choice import ChoiceState, PendingChoice, resolve as resolve_choice
from brain.decision_engine import DecisionEngine
from brain.cognition import CognitionEngine
from brain.events import EventBus, EventType
from brain.models import ActionRecord, ActionRequest, BrainEvent, Decision, IntentType, Turn
from brain.planner import Planner
from brain.reflection import SelfReflector
from brain.response_engine import ResponseEngine
from brain.skill_learning import SkillLearningState, SkillTeacher, SkillTeachResult, SkillTeachStatus
from brain.world_state import WorldState
from emotions.engine import EmotionalEngine
from emotions.events import EmotionEvent
from emotions.needs import NeedsEngine, NeedsStore
from memory.identity import IdentityStore
from memory.long_term import LongTermMemory, MemoryKind, MemoryRecord, score_candidate
from memory.people import PeopleDirectory, PersonProfile
from memory.repository import InMemoryRepository
from memory.short_term import ShortTermMemory
from perception.speech.yes_no import classify_yes_no
from personality.personality import Personality
from personality.voice import learning_clarify

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
    behavior_proposals: list[BehaviorProposal] = field(default_factory=list)


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
        needs_engine: NeedsEngine | None = None,
        identity_store: IdentityStore | None = None,
        reflector: SelfReflector | None = None,
        people: PeopleDirectory,
        long_term: LongTermMemory,
        short_term: ShortTermMemory,
        event_sink: EventSink = print_event_sink,
        world_state: WorldState | None = None,
        event_bus: EventBus | None = None,
        behavior_engine: BehaviorEngine | None = None,
        initiative_engine: InitiativeEngine | None = None,
        action_router: LlmActionRouter | None = None,
        skill_teacher: SkillTeacher | None = None,
    ) -> None:
        self.decision_engine = decision_engine
        self.action_router = action_router
        self.skill_teacher = skill_teacher
        self.learning_state = SkillLearningState()
        # The one "which do you mean?" question Bob may be waiting on (see
        # brain/choice.py) -- lives on the agent, not a tablet session, so it
        # works the same from the CLI.
        self.choice_state = ChoiceState()
        self.planner = planner
        self.executor = executor
        self.context_builder = context_builder
        self.response_engine = response_engine
        self.personality = personality
        self.emotional_engine = emotional_engine
        # Falls back to a non-persistent store rather than requiring every
        # caller (tests included) to wire one up -- production always
        # passes a real one (see app/main.py's build_needs_repository).
        self.needs_engine = needs_engine or NeedsEngine(NeedsStore(InMemoryRepository()))
        # Falls back the same way needs_engine does -- tests and any
        # caller that doesn't care about identity still get a working
        # agent, just with the hardcoded default self-concept instead of
        # a persisted one.
        self.identity_store = identity_store or IdentityStore(InMemoryRepository())
        # Optional: learns from recent conversations on its own (see
        # brain/reflection.py). None = no self-learning, e.g. in tests.
        self.reflector = reflector
        self.people = people
        self.long_term = long_term
        self.short_term = short_term
        self.event_sink = event_sink
        self.world_state = world_state or WorldState()
        self.event_bus = event_bus or EventBus()
        self.behavior_engine = behavior_engine or BehaviorEngine()
        self.initiative_engine = initiative_engine or InitiativeEngine()
        self.cognition = CognitionEngine(
            world_state=self.world_state,
            event_bus=self.event_bus,
            emotional_state=self.emotional_engine.state,
            personality=self.personality.traits,
        )

    async def process_turn(
        self, text: str, person_id: str | None = None, *, current_activity: str | None = None,
        device_status: str | None = None,
    ) -> TurnResult:
        start = time.monotonic()
        # Captured *before* mark_user_turn resets last_interaction_at to
        # now -- this is "how bored was I right up until this message
        # interrupted me", which is what should color this reply's tone,
        # not "how long since the message that's currently being handled".
        last_interaction = self.world_state.activity.last_interaction_at or self.world_state.activity.active_since
        idle_seconds_before_turn = (datetime.now(timezone.utc) - last_interaction).total_seconds()
        self.world_state.mark_user_turn(person_id)
        self.event_bus.publish(EventType.USER_SPOKE, {"person_id": person_id or "unknown", "text": text})

        self.emotional_engine.decay()

        person = self.people.get_or_create(person_id) if person_id else None

        # A skill-teaching attempt in progress owns the next turn entirely
        # (a clarifying answer or a yes/no approval) -- it never goes
        # through the normal decision/planner/executor/dialogue pipeline,
        # same principle as api/server.py's pending_music_offer intercepting
        # a transcript before wake-word handling. Lives on the agent (not a
        # tablet-only DeviceSession) so this works identically from the CLI.
        if self.learning_state.active:
            self.short_term.add(Turn(speaker="user", text=text, person_id=person_id))
            reply = await self._continue_learning(text)
            return self._learning_turn_result(text, reply, person, person_id)

        previous_turns = self.short_term.recent(1)
        previous_robot_text = (
            previous_turns[0].text
            if previous_turns and previous_turns[0].speaker == "robot"
            else None
        )
        self.short_term.add(Turn(speaker="user", text=text, person_id=person_id))

        intent_started = time.monotonic()
        decision = None
        # If Bob just asked "which one?", this turn is the answer: a match
        # re-runs the same action with the chosen value (skipping intent
        # classification entirely); "cancela" drops it; anything unrelated
        # drops the question and is handled as a normal new request.
        if self.choice_state.active:
            pending = self.choice_state.pending
            answer = resolve_choice(pending, text)
            self.choice_state.clear()
            if answer.kind == "cancelled":
                return self._learning_turn_result(text, "Beleza, deixei quieto.", person, person_id)
            if answer.kind == "picked" and answer.option is not None:
                if answer.remember and pending.remember_key:
                    self.identity_store.state.preferences[pending.remember_key] = answer.option.value
                    self.identity_store.save()
                decision = Decision(
                    type=IntentType.ACTION,
                    confidence=1.0,
                    raw_text=text,
                    actions=[ActionRequest(
                        name=pending.action,
                        arguments={**pending.arguments, pending.param: answer.option.value},
                    )],
                )
        if decision is None:
            decision = self.decision_engine.classify_follow_up(text, previous_robot_text)
        # The regex rules only recognize phrasings someone already thought to
        # write a pattern for. Rather than growing that list forever, an
        # utterance that regex saw as plain dialogue (no clear command) gets
        # one shot at real understanding from the LLM before settling for
        # "just talk back" -- this is what lets "entra no player" or "toque
        # a música X" work without a hand-written rule for every way to say
        # them, while every previously-recognized phrasing stays instant and
        # free (no LLM call at all).
        if (
            decision.type in (IntentType.DIALOGUE, IntentType.AMBIGUOUS, IntentType.QUESTION)
            and decision.memory_candidate is None
            and self.action_router is not None
        ):
            outcome = await self.action_router.route(text)
            if outcome.decision is not None:
                decision = outcome.decision
            elif outcome.learnable_hint is not None and self.skill_teacher is not None:
                # Nothing in the registry covers this, but the phrasing
                # reads like something Bob could reasonably be taught
                # ("coloque um timer") rather than plain chit-chat -- start
                # a teaching attempt instead of just shrugging it off as
                # unrecognized dialogue.
                result = await self.skill_teacher.start(text)
                reply = self._apply_teach_result(result, original_utterance=text)
                return self._learning_turn_result(text, reply, person, person_id)
        intent_latency_ms = round((time.monotonic() - intent_started) * 1000, 1)

        context = self.context_builder.build(
            person=person,
            personality=self.personality.traits,
            emotion=self.emotional_engine.state,
            hunger=self.needs_engine.state.hunger,
            idle_seconds=idle_seconds_before_turn,
            current_activity=current_activity,
            identity_text=self.identity_store.as_prompt_fragment(),
            device_status=device_status,
        )

        planning_started = time.monotonic()
        plan = self.planner.plan(decision)
        planning_latency_ms = round((time.monotonic() - planning_started) * 1000, 1)
        action_started = time.monotonic()
        action_records = await self.executor.execute_many(plan.valid_actions)
        action_latency_ms = round((time.monotonic() - action_started) * 1000, 1)

        for record in action_records:
            # An action that answered with a question instead of acting
            # ("onde você quer ouvir?") leaves that question pending.
            if record.outcome and not record.outcome.success:
                asked = PendingChoice.from_outcome_data(record.name, record.arguments, record.outcome.data)
                if asked is not None:
                    self.choice_state.ask(asked)
            event = EmotionEvent.SUCCESSFUL_ACTION if record.outcome and record.outcome.success else EmotionEvent.FAILED_ACTION
            self.emotional_engine.apply_event(event)
            self.event_bus.publish(
                EventType.ACTION_COMPLETED if record.outcome and record.outcome.success else EventType.ACTION_FAILED,
                {"action": record.name, "success": bool(record.outcome and record.outcome.success)},
            )

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

        response_started = time.monotonic()
        reply = await self.response_engine.generate(decision, context, action_records)
        response_latency_ms = round((time.monotonic() - response_started) * 1000, 1)
        self.short_term.add(Turn(speaker="robot", text=reply, person_id=person_id))
        if self.reflector is not None:
            self.reflector.note_turn(self.short_term.as_context_text(10))

        latency_ms = round((time.monotonic() - start) * 1000, 1)
        behavior_event = (
            "conversation_interesting"
            if decision.type in (IntentType.DIALOGUE, IntentType.QUESTION)
            else "user_command"
        )
        behavior_proposals = self.behavior_engine.evaluate(behavior_event, self.world_state)

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
                    "intent_latency_ms": intent_latency_ms,
                    "planning_latency_ms": planning_latency_ms,
                    "action_latency_ms": action_latency_ms,
                    "response_latency_ms": response_latency_ms,
                    "behavior_proposals": ", ".join(p.name for p in behavior_proposals) or "none",
                },
            )
        )

        self.emotional_engine.save()
        self.world_state.finish_turn()
        self.event_bus.publish(EventType.ROBOT_RESPONSE_FINISHED, {"person_id": person_id or "unknown"})

        return TurnResult(
            reply=reply,
            decision=decision,
            action_records=action_records,
            person=person,
            behavior_proposals=behavior_proposals,
        )

    def propose_initiative(self, event_type: str) -> BehaviorProposal | None:
        proposals = self.behavior_engine.evaluate(event_type, self.world_state)
        return self.initiative_engine.select(proposals, self.world_state)

    async def _continue_learning(self, text: str) -> str:
        """The turn following either a clarifying question or an approval
        request -- interprets `text` against whichever one is pending."""
        state = self.learning_state
        if state.awaiting_approval:
            answer = classify_yes_no(text)
            if answer is True and state.pending_record is not None and self.skill_teacher is not None:
                self.skill_teacher.approve(state.pending_record)
                reply = f"Aprendi: {state.pending_record.description}."
            elif answer is False:
                reply = "Combinado, não vou aprender isso."
            else:
                # An approval question got an unclear answer -- never guess
                # consent for something the system itself flagged as
                # needing a yes.
                reply = "Não entendi se era pra aprender ou não, vou deixar quieto por enquanto."
            state.reset()
            return reply

        if self.skill_teacher is None:
            state.reset()
            return "Não consigo aprender coisas novas agora."
        result = await self.skill_teacher.continue_with_answer(
            state.original_utterance, state.clarifying_question or "", text,
        )
        return self._apply_teach_result(result, original_utterance=state.original_utterance)

    def _apply_teach_result(self, result: SkillTeachResult, *, original_utterance: str) -> str:
        state = self.learning_state
        if result.status is SkillTeachStatus.NEEDS_CLARIFICATION:
            state.active = True
            state.original_utterance = original_utterance
            state.clarifying_question = result.message
            state.awaiting_approval = False
            state.pending_record = None
            return learning_clarify(result.message)
        if result.status is SkillTeachStatus.READY_FOR_APPROVAL:
            state.active = True
            state.original_utterance = original_utterance
            state.awaiting_approval = True
            state.pending_record = result.record
            return result.message
        # LEARNED or FAILED both end the attempt.
        state.reset()
        return result.message

    def _learning_turn_result(self, text: str, reply: str, person: PersonProfile | None, person_id: str | None) -> TurnResult:
        self.short_term.add(Turn(speaker="robot", text=reply, person_id=person_id))
        self.emotional_engine.save()
        self.world_state.finish_turn()
        self.event_bus.publish(EventType.ROBOT_RESPONSE_FINISHED, {"person_id": person_id or "unknown"})
        decision = Decision(type=IntentType.QUESTION, confidence=0.9, raw_text=text)
        return TurnResult(reply=reply, decision=decision, person=person)
