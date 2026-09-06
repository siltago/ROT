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
