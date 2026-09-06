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
        tone = "mais reservado e direto, mas ainda paciente e respeitoso"
    elif emotion.valence > 0.6:
        tone = "caloroso e animado, sem exagero"
    elif emotion.valence < 0.3:
        tone = "baixo e gentil"
    else:
        tone = "atento e natural"

    familiarity = person.familiarity if person else 0.0
    trust = person.trust if person else 0.0
    warmth = "próximo e informal" if familiarity > 0.6 else "amigável, sem intimidade forçada"

    playfulness_score = (personality.humor + emotion.curiosity) / 2
    if personality.sarcasm > 0.5 and trust > 0.5:
        playfulness = "brincalhão, com provocação leve e rara"
    elif playfulness_score > 0.6:
        playfulness = "curioso e levemente brincalhão"
    else:
        playfulness = "direto, sem tentar fazer graça"

    verbosity = "concise" if personality.verbosity < 0.5 else "elaborative"

    notes = []
    if personality.formality < 0.35:
        notes.append("use linguagem informal e natural")
    if personality.confidence < 0.4:
        notes.append("admita incerteza sem inventar; confiança não significa fingir certeza")
    if person and person.relationship == "friend":
        notes.append("fale como alguém próximo, sem virar servil ou invasivo")
    if emotion.energy < 0.3:
        notes.append("energia baixa: responda de forma ainda mais curta e suave")

    return StyleGuide(
        tone=tone,
        warmth=warmth,
        playfulness=playfulness,
        verbosity=verbosity,
        notes=notes,
    )
