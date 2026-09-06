from datetime import datetime, timedelta, timezone

import pytest

from brain.behaviors import BehaviorContext, BehaviorProposal, InitiativeConfig, InitiativeEngine, ProposalArbiter
from brain.cognition import CognitionEngine
from brain.cognition_config import CognitionConfig
from brain.context_evaluator import ContextEvaluator
from brain.drives import DriveEngine, DriveState
from brain.events import EventBus, EventType, RobotEvent
from brain.world_state import WorldState, WorldStateReducer


@pytest.mark.asyncio
async def test_event_bus_routes_isolates_async_errors_and_unsubscribes() -> None:
    bus, received = EventBus(), []

    async def broken(_: RobotEvent) -> None:
        raise RuntimeError("subscriber failure")

    unsubscribe = bus.subscribe(EventType.PERSON_DETECTED, lambda event: received.append(event.id))
    bus.subscribe(EventType.PERSON_DETECTED, broken)
    bus.subscribe(EventType.WEATHER_UPDATED, lambda event: received.append("wrong"))
    first = await bus.publish_async(EventType.PERSON_DETECTED, {"person_id": "joao"})
    unsubscribe()
    await bus.publish_async(EventType.PERSON_DETECTED, {"person_id": "maria"})
    assert received == [first.id]
    assert bus.handler_errors == 2


def test_world_state_reducer_handles_people_speech_and_weather() -> None:
    world, reducer = WorldState(), WorldStateReducer(WorldState())
    world = reducer.state
    reducer.apply(RobotEvent(type=EventType.PERSON_DETECTED, data={"person_id": "joao"}))
    reducer.apply(RobotEvent(type=EventType.USER_STARTED_SPEAKING))
    reducer.apply(RobotEvent(type=EventType.WEATHER_UPDATED, data={"temperature": 32, "condition": "sunny"}))
    assert world.people_present == {"joao"} and world.user_speaking
    assert world.environment.temperature == 32
    reducer.apply(RobotEvent(type=EventType.USER_STOPPED_SPEAKING))
    reducer.apply(RobotEvent(type=EventType.PERSON_LOST, data={"person_id": "joao"}))
    assert not world.user_speaking and not world.people_present


def test_context_evaluator_derives_hot_and_user_availability() -> None:
    world = WorldState(current_person_id="joao")
    world.people_present.add("joao")
    world.environment.temperature, world.time.hour = 32, 14
    context = ContextEvaluator().evaluate(world)
    assert context.environment_hot and context.user_available
    world.user_speaking = True
    assert not ContextEvaluator().evaluate(world).user_available


def test_drive_clamp_decay_idle_novelty_and_rest() -> None:
    engine = DriveEngine(DriveState(curiosity=0.95, social=0.95, helpfulness=1, playfulness=0, rest=0.95))
    engine.apply_event(RobotEvent(type=EventType.NEW_OBJECT_DETECTED))
    assert engine.state.curiosity == 1.0
    before = engine.state.social
    engine.apply_event(RobotEvent(type=EventType.IDLE_TIMEOUT, data={"idle_seconds": 3600}))
    assert engine.state.social >= before
    engine.advance(3600, active=True)
    assert engine.state.rest == 1.0 and engine.state.curiosity < 1.0


def test_arbiter_selects_highest_weighted_valid_proposal() -> None:
    world = WorldState(current_person_id="joao")
    world.people_present.add("joao")
    world.time.hour = 14
    context = BehaviorContext(world, ContextEvaluator().evaluate(world))
    proposals = [BehaviorProposal("WeatherBehavior", 0.4), BehaviorProposal("GreetingBehavior", 0.8), BehaviorProposal("IdleBehavior", 0.3)]
    assert ProposalArbiter().select(proposals, context).name == "GreetingBehavior"


def test_initiative_suppression_priority_cooldown_and_hour_limit() -> None:
    world, proposal = WorldState(), BehaviorProposal("GreetingBehavior", 0.8)
    world.user_speaking = True
    assert InitiativeEngine().select([proposal], world, now=10) is None
    world.user_speaking, world.robot_speaking = False, True
    assert InitiativeEngine().select([proposal], world, now=10) is None
    world.robot_speaking = False
    engine = InitiativeEngine(InitiativeConfig(minimum_priority=0.7, level=1, cooldown_seconds=100, max_per_hour=1))
    assert engine.select([BehaviorProposal("low", 0.2)], world, now=10) is None
    assert engine.select([proposal], world, now=20) == proposal
    assert engine.select([proposal], world, now=200) is None


@pytest.mark.asyncio
async def test_e2e_greeting_then_per_behavior_cooldown() -> None:
    config = CognitionConfig(global_cooldown_seconds=0, quiet_period_start_hour=24, behavior_cooldowns={"GreetingBehavior": 1800})
    cognition = CognitionEngine(config=config)
    event = lambda: RobotEvent(type=EventType.PERSON_DETECTED, data={"person_id": "joao", "confidence": 0.99})
    first, second = await cognition.process_event(event()), await cognition.process_event(event())
    assert first.selected is not None and first.selected.name == "GreetingBehavior"
    assert first.selected.proposed_action is None and second.selected is None


@pytest.mark.asyncio
async def test_e2e_weather_comments_but_never_executes_action() -> None:
    cognition = CognitionEngine(config=CognitionConfig(global_cooldown_seconds=0, quiet_period_start_hour=24))
    cognition.world_state.current_person_id = "joao"
    cognition.world_state.people_present.add("joao")
    cognition.world_state.environment.temperature = 25
    result = await cognition.process_event(RobotEvent(type=EventType.TEMPERATURE_CHANGED, data={"previous": 25, "temperature": 33}))
    assert result.proposals[0].name == "WeatherBehavior"
    assert result.proposals[0].proposed_action is None


@pytest.mark.asyncio
async def test_small_temperature_change_creates_no_proposal() -> None:
    cognition = CognitionEngine(config=CognitionConfig(global_cooldown_seconds=0, quiet_period_start_hour=24))
    cognition.world_state.environment.temperature = 25
    result = await cognition.process_event(RobotEvent(type=EventType.TEMPERATURE_CHANGED, data={"previous": 25, "temperature": 25.2}))
    assert result.proposals == []


@pytest.mark.asyncio
async def test_idle_is_suppressed_while_user_speaks_and_allowed_afterwards() -> None:
    cognition = CognitionEngine(config=CognitionConfig(global_cooldown_seconds=0, idle_social_seconds=900, quiet_period_start_hour=24))
    cognition.world_state.current_person_id = "joao"
    cognition.world_state.people_present.add("joao")
    cognition.world_state.activity.last_interaction_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    cognition.world_state.user_speaking = True
    blocked = await cognition.process_event(RobotEvent(type=EventType.IDLE_TIMEOUT, data={"idle_seconds": 1200}))
    assert blocked.selected is None
    cognition.world_state.user_speaking = False
    allowed = await cognition.process_event(RobotEvent(type=EventType.IDLE_TIMEOUT, data={"idle_seconds": 1200}))
    assert allowed.proposals and allowed.selected is not None
    assert not allowed.selected.requires_llm
