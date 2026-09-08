from emotions.state import EmotionalState
from personality.personality import PersonalityTraits
from personality.style import build_style_guide
from personality.voice import YBI_VOICE


def test_low_verbosity_produces_concise_style_instruction() -> None:
    guide = build_style_guide(PersonalityTraits(verbosity=0.2), EmotionalState(), None)
    assert guide.verbosity == "concise"
    assert "informal" in guide.as_prompt_fragment()


def test_humor_never_enters_action_execution_contract() -> None:
    traits = PersonalityTraits(humor=1.0)
    assert not hasattr(traits, "execute")


def test_bob_voice_is_stable_and_not_corporate() -> None:
    prompt = YBI_VOICE.prompt()
    assert "Bob" in prompt
    assert "não um assistente corporativo" in prompt
    assert "Como posso ajudar?" in prompt
    assert "nunca afirme que uma ação física aconteceu" in prompt


def test_high_hunger_adds_a_style_note() -> None:
    guide = build_style_guide(PersonalityTraits(), EmotionalState(), None, hunger=0.9)
    assert any("fome" in note for note in guide.notes)


def test_low_hunger_adds_no_hunger_note() -> None:
    guide = build_style_guide(PersonalityTraits(), EmotionalState(), None, hunger=0.1)
    assert not any("fome" in note for note in guide.notes)


def test_very_low_energy_adds_a_sleepy_grumble_note() -> None:
    guide = build_style_guide(PersonalityTraits(), EmotionalState(energy=0.1), None)
    assert any("sono" in note for note in guide.notes)


def test_hunger_and_idle_together_add_an_impatience_note() -> None:
    guide = build_style_guide(
        PersonalityTraits(), EmotionalState(), None, hunger=0.8, idle_seconds=1000,
    )
    assert any("tédio" in note for note in guide.notes)


def test_hunger_alone_without_idle_does_not_add_the_impatience_note() -> None:
    guide = build_style_guide(
        PersonalityTraits(), EmotionalState(), None, hunger=0.8, idle_seconds=10,
    )
    assert not any("tédio" in note for note in guide.notes)


def test_current_activity_adds_a_note_mentioning_it() -> None:
    guide = build_style_guide(
        PersonalityTraits(), EmotionalState(), None, current_activity="lendo sobre sarcasmo",
    )
    assert any("lendo sobre sarcasmo" in note for note in guide.notes)


def test_no_current_activity_adds_no_activity_note() -> None:
    guide = build_style_guide(PersonalityTraits(), EmotionalState(), None)
    assert not any("está fazendo" in note for note in guide.notes)
