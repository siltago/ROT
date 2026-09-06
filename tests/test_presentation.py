from brain.agent import TurnResult
from brain.models import ActionOutcome, ActionRecord, Decision, IntentType
from brain.presentation import PresentationPlanner


def _result(action: str | None = None, data: dict | None = None) -> TurnResult:
    records = []
    if action is not None:
        records.append(ActionRecord(
            id="a1",
            name=action,
            arguments={},
            outcome=ActionOutcome(success=True, data=data or {}),
        ))
    return TurnResult(
        reply="ok",
        decision=Decision(type=IntentType.QUESTION, confidence=1),
        action_records=records,
    )


def test_short_conversation_keeps_face() -> None:
    assert PresentationPlanner().plan(_result()) is None


def test_time_action_becomes_temporary_full_screen_clock() -> None:
    scene = PresentationPlanner().plan(_result("time.get", {"time": "15:42"}))
    assert scene is not None
    assert scene.kind == "clock"
    assert scene.data == {"time": "15:42"}
    assert not scene.persistent
    assert scene.duration_ms == 3000


def test_weather_condition_selects_procedural_rain_scene() -> None:
    scene = PresentationPlanner().plan(_result(
        "weather.get", {"condition": "heavy rain", "temperature": 21}
    ))
    assert scene is not None
    assert scene.kind == "weather"
    assert scene.variant == "rain"


def test_clear_weather_at_night_never_shows_sun() -> None:
    scene = PresentationPlanner().plan(_result(
        "weather.get", {"condition": "clear", "temperature": 15, "is_dark": True}
    ))
    assert scene is not None
    assert scene.variant == "night"


def test_music_scene_stays_until_playback_changes() -> None:
    scene = PresentationPlanner().plan(_result("music.play", {"query": "Clair de Lune"}))
    assert scene is not None
    assert scene.kind == "music"
    assert scene.persistent
    assert scene.duration_ms is None
