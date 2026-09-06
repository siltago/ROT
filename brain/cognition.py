"""Event-oriented orchestration for bounded proactive cognition."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from brain.behaviors import BehaviorContext, BehaviorEngine, BehaviorProposal, InitiativeConfig, InitiativeEngine, ProposalArbiter
from brain.cognition_config import CognitionConfig
from brain.context_evaluator import ContextEvaluator, DerivedContext
from brain.drives import DriveEngine
from brain.events import EventBus, EventType, RobotEvent
from brain.world_state import WorldState, WorldStateReducer


@dataclass
class CognitionMetrics:
    events_processed: int = 0
    event_processing_latency_ms: float = 0.0
    context_evaluation_latency_ms: float = 0.0
    behavior_evaluation_latency_ms: float = 0.0
    proposal_arbitration_latency_ms: float = 0.0
    initiative_decision_latency_ms: float = 0.0
    total_proactive_response_latency_ms: float = 0.0


@dataclass
class CognitionResult:
    event: RobotEvent
    context: DerivedContext
    proposals: list[BehaviorProposal]
    selected: BehaviorProposal | None
    suppressed: bool
    metrics: dict[str, Any] = field(default_factory=dict)


class CognitionEngine:
    def __init__(self, *, config: CognitionConfig = CognitionConfig(), world_state: WorldState | None = None, event_bus: EventBus | None = None, emotional_state: Any = None, personality: Any = None) -> None:
        self.config = config
        self.world_state = world_state or WorldState()
        self.event_bus = event_bus or EventBus()
        self.reducer = WorldStateReducer(self.world_state)
        self.context_evaluator = ContextEvaluator(config)
        self.drive_engine = DriveEngine(config=config)
        self.behavior_engine = BehaviorEngine(config)
        self.arbiter = ProposalArbiter()
        self.initiative_engine = InitiativeEngine(InitiativeConfig(enabled=config.initiative_enabled, level=1.0, minimum_priority=config.minimum_proposal_priority, cooldown_seconds=config.global_cooldown_seconds, max_per_hour=config.max_initiatives_per_hour, behavior_cooldowns=config.behavior_cooldowns))
        self.emotional_state = emotional_state
        self.personality = personality
        self.recent_events: deque[RobotEvent] = deque(maxlen=20)
        self.metrics = CognitionMetrics()

    async def process_event(self, event: RobotEvent) -> CognitionResult:
        started = time.monotonic()
        self.reducer.apply(event)
        self.drive_engine.apply_event(event)
        self.recent_events.append(event)
        await self.event_bus.publish_async(event)

        mark = time.monotonic()
        derived = self.context_evaluator.evaluate(self.world_state)
        self.metrics.context_evaluation_latency_ms = (time.monotonic() - mark) * 1000
        context = BehaviorContext(self.world_state, derived, self.emotional_state, self.drive_engine.state, self.personality, tuple(self.recent_events))

        mark = time.monotonic()
        proposals = self.behavior_engine.evaluate(event, context)
        self.metrics.behavior_evaluation_latency_ms = (time.monotonic() - mark) * 1000
        for proposal in proposals:
            await self.event_bus.publish_async(EventType.INITIATIVE_PROPOSED, {"proposal_id": proposal.id, "behavior": proposal.name, "priority": proposal.priority}, source="cognition")

        mark = time.monotonic()
        arbitrated = self.arbiter.select(proposals, context)
        self.metrics.proposal_arbitration_latency_ms = (time.monotonic() - mark) * 1000
        mark = time.monotonic()
        selected = self.initiative_engine.select([arbitrated] if arbitrated else [], self.world_state, derived=derived)
        self.metrics.initiative_decision_latency_ms = (time.monotonic() - mark) * 1000
        if selected:
            await self.event_bus.publish_async(EventType.INITIATIVE_STARTED, {"proposal_id": selected.id, "behavior": selected.name}, source="cognition")
        elif proposals:
            await self.event_bus.publish_async(EventType.INITIATIVE_SUPPRESSED, {"proposal_ids": [p.id for p in proposals]}, source="cognition")

        total = (time.monotonic() - started) * 1000
        self.metrics.events_processed += 1
        self.metrics.event_processing_latency_ms = total
        self.metrics.total_proactive_response_latency_ms = total
        return CognitionResult(event, derived, proposals, selected, bool(proposals and not selected), self.metrics_snapshot())

    async def complete_initiative(self, proposal: BehaviorProposal) -> None:
        self.initiative_engine.mark_completed(proposal)
        completed = RobotEvent(type=EventType.INITIATIVE_COMPLETED, source="cognition", data={"proposal_id": proposal.id, "behavior": proposal.name})
        self.drive_engine.apply_event(completed)
        await self.event_bus.publish_async(completed)

    def metrics_snapshot(self) -> dict[str, Any]:
        values = asdict(self.metrics)
        values.update(asdict(self.initiative_engine.metrics))
        values["initiatives_per_hour"] = len(self.initiative_engine._accepted)
        values["llm_calls_from_initiative"] = self.initiative_engine.metrics.initiative_llm_calls
        return values
