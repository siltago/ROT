from brain.decision_engine import DecisionEngine
from brain.models import IntentType


def test_pure_action_is_classified_as_action():
    engine = DecisionEngine()
    decision = engine.classify("Liga a luz da sala.")
    assert decision.type == IntentType.ACTION
    assert decision.actions[0].name == "light.turn_on"
    assert decision.actions[0].arguments["room"] == "sala"


def test_explicit_command_with_extra_context_is_dialogue_and_action():
    engine = DecisionEngine()
    decision = engine.classify("Está quente aqui, coloca o ar em 22.")
    assert decision.type == IntentType.DIALOGUE_AND_ACTION
    assert decision.actions[0].name == "climate.set_temperature"
    assert decision.actions[0].arguments["temperature"] == 22.0


def test_ambient_observation_without_command_is_dialogue_not_action():
    engine = DecisionEngine()
    decision = engine.classify("Está muito quente aqui.")
    assert decision.type == IntentType.DIALOGUE
    assert decision.actions == []


def test_preference_statement_is_flagged_as_memory_candidate():
    engine = DecisionEngine()
    decision = engine.classify("Gosto mais quando a sala fica escura.")
    assert decision.type == IntentType.DIALOGUE
    assert decision.memory_candidate is not None


def test_question_is_classified_as_question():
    engine = DecisionEngine()
    decision = engine.classify("Que horas são?")
    assert decision.type == IntentType.QUESTION


def test_empty_input_is_ambiguous():
    engine = DecisionEngine()
    decision = engine.classify("   ")
    assert decision.type == IntentType.AMBIGUOUS
    assert decision.confidence == 0.0


def test_unlock_door_command_is_recognized():
    engine = DecisionEngine()
    decision = engine.classify("Destrava a porta principal.")
    assert decision.type == IntentType.ACTION
    assert decision.actions[0].name == "door.unlock"
