from brain.events import EventBus
from brain.world_state import WorldState


def test_event_bus_publish_and_unsubscribe() -> None:
    received = []
    bus = EventBus()
    unsubscribe = bus.subscribe("user_spoke", received.append)
    bus.publish("user_spoke", {"text": "oi"})
    unsubscribe()
    bus.publish("user_spoke", {"text": "de novo"})
    assert len(received) == 1
    assert received[0].data["text"] == "oi"


def test_world_state_marks_and_finishes_turn() -> None:
    world = WorldState()
    world.mark_user_turn("person_1")
    assert world.processing is True
    assert world.current_person == "person_1"
    world.finish_turn()
    assert world.processing is False
    assert world.last_interaction_at is not None
