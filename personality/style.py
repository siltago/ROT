"""Turns personality + emotion + relationship into concrete response-style
hints for the response engine, instead of one giant hand-written prompt.
"""
from __future__ import annotations

from dataclasses import dataclass

from emotions.state import EmotionalState
from memory.people import PersonProfile
from personality.personality import PersonalityTraits


@dataclass
class StyleGuide:
    tone: str
    warmth: str
    playfulness: str
    verbosity: str
    notes: list[str]

    def as_prompt_fragment(self) -> str:
        """Compact instruction block to hand the LLM, not a personality essay."""
        lines = [
            f"tone: {self.tone}",
            f"warmth: {self.warmth}",
            f"playfulness: {self.playfulness}",
            f"verbosity: {self.verbosity}",
        ]
        lines.extend(self.notes)
        return "\n".join(lines)


def build_style_guide(
    personality: PersonalityTraits,
    emotion: EmotionalState,
    person: PersonProfile | None,
) -> StyleGuide:
    # Tone driven mostly by emotional valence + irritation.
    if emotion.irritation > 0.6:
        tone = "curt, patient but clearly wants space"
    elif emotion.valence > 0.6:
        tone = "warm, upbeat"
    elif emotion.valence < 0.3:
        tone = "subdued, gentle"
    else:
        tone = "neutral, attentive"

    familiarity = person.familiarity if person else 0.0
    trust = person.trust if person else 0.0
    warmth = "close and informal" if familiarity > 0.6 else "friendly but measured"

    playfulness_score = (personality.humor + emotion.curiosity) / 2
    if personality.sarcasm > 0.5 and trust > 0.5:
        playfulness = "playful, occasional light sarcasm"
    elif playfulness_score > 0.6:
        playfulness = "playful, curious"
    else:
        playfulness = "mostly straightforward"

    verbosity = "concise" if personality.verbosity < 0.5 else "elaborative"

    notes = []
    if person and person.relationship == "friend":
        notes.append("speak as a trusted friend would")
    if emotion.energy < 0.3:
        notes.append("low energy -- keep replies short")

    return StyleGuide(
        tone=tone,
        warmth=warmth,
        playfulness=playfulness,
        verbosity=verbosity,
        notes=notes,
    )
