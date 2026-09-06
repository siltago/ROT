from brain.behaviors import (
    BehaviorEngine,
    BehaviorProposal,
    InitiativeConfig,
    InitiativeEngine,
)
from brain.world_state import WorldState


def test_behavior_engine_generates_proposals_without_executing() -> None:
    proposals = BehaviorEngine().evaluate("user_session_started", WorldState())
    assert proposals == [BehaviorProposal("greet_user", 0.9, "Cumprimente brevemente.")]
    assert proposals[0].proposed_action is None


def test_initiative_respects_disabled_user_busy_priority_and_cooldown() -> None:
    proposal = BehaviorProposal("ask_followup", 0.8)
    world = WorldState()
    assert InitiativeEngine(InitiativeConfig(enabled=False)).select([proposal], world) is None

    world.user_speaking = True
    assert InitiativeEngine().select([proposal], world) is None
    world.user_speaking = False

    engine = InitiativeEngine(InitiativeConfig(level=0.4, minimum_priority=0.65, cooldown_seconds=120))
    assert engine.select([BehaviorProposal("low", 0.4)], world, now=100) is None
    assert engine.select([proposal], world, now=100) == proposal
    assert engine.select([proposal], world, now=150) is None
    assert engine.select([proposal], world, now=221) == proposal
