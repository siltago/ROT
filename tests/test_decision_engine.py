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


def test_time_question_routes_to_local_action():
    engine = DecisionEngine()
    decision = engine.classify("Que horas são?")
    assert decision.type == IntentType.ACTION
    assert decision.actions[0].name == "time.get"


def test_weather_question_routes_to_validated_action():
    decision = DecisionEngine().classify("Vai chover hoje?")
    assert decision.type == IntentType.ACTION
    assert decision.actions[0].name == "weather.get"
    assert DecisionEngine().classify("Qual a temperatura agora?").actions[0].name == "weather.get"


def test_tomorrow_weather_routes_to_forecast_action() -> None:
    decision = DecisionEngine().classify("Qual a temperatura de amanhã?")
    assert decision.actions[0].name == "weather.forecast"
    assert decision.actions[0].arguments["day_offset"] == 1


def test_explicit_city_routes_to_location_action():
    decision = DecisionEngine().classify("Eu moro em Campinas, SP")
    assert decision.actions[0].name == "weather.set_location"
    assert decision.actions[0].arguments["city"] == "Campinas, SP"


def test_city_only_is_understood_after_location_question():
    decision = DecisionEngine().classify_follow_up(
        "Campinas", "Ainda não sei onde estou. Em qual cidade eu estou?"
    )
    assert decision.actions[0].name == "weather.set_location"
    assert decision.actions[0].arguments["city"] == "Campinas"
    prefixed = DecisionEngine().classify_follow_up(
        "Em Sorocaba.", "Ainda não sei onde estou. Em qual cidade eu estou?"
    )
    assert prefixed.actions[0].arguments["city"] == "Sorocaba"


def test_natural_light_synonym_routes_to_same_action():
    decision = DecisionEngine().classify("Pode acender a luz da sala?")
    assert decision.actions[0].name == "light.turn_on"


def test_music_without_query_remains_structured_for_clarification():
    decision = DecisionEngine().classify("Coloca uma música")
    assert decision.type == IntentType.ACTION
    assert decision.actions[0].name == "music.play"
    assert decision.actions[0].arguments["query"] == ""


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


def test_generic_home_assistant_devices_route_to_safe_actions():
    engine = DecisionEngine()
    cases = [
        ("Ligue o ventilador da sala", "smart_home.turn_on", "ventilador da sala"),
        ("Desligue a TV da sala", "smart_home.turn_off", "TV da sala"),
        ("Abra a cortina do quarto", "smart_home.turn_on", "cortina do quarto"),
        ("Feche a persiana da sala", "smart_home.turn_off", "persiana da sala"),
    ]
    for text, action, target in cases:
        decision = engine.classify(text)
        assert decision.actions[0].name == action
        assert decision.actions[0].arguments["target"].casefold() == target.casefold()


def test_exit_player_is_distinct_from_stopping_playback():
    engine = DecisionEngine()
    for text in ["Sai do player", "Fecha essa tela de música", "Esconde o player"]:
        decision = engine.classify(text)
        assert decision.actions[0].name == "music.hide_player", text


def test_toque_phrasing_of_play_music_is_recognized():
    engine = DecisionEngine()
    decision = engine.classify("Toque uma música x")
    assert decision.actions[0].name == "music.play"
    assert decision.actions[0].arguments["query"] == "x"


def test_resume_is_distinct_from_starting_a_new_song():
    engine = DecisionEngine()
    for text in ["Despausa a música", "Continua a música", "Volta a música"]:
        decision = engine.classify(text)
        assert decision.actions[0].name == "music.resume", text
