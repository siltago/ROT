"""Lets someone train Bob by talking to him ("Bob, aprenda que...", "seja
mais sarcástico", "fala mais curto") -- routed through the same
LlmActionRouter/registry as every other command, so no new intent
plumbing is needed.

Both actions only change *guidance* (his persisted identity knowledge and
his personality sliders); neither can run anything in the world. The
sliders move in small steps and stay clamped to [0, 1], so no single
sentence can flip his character.
"""
from __future__ import annotations

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel
from memory.identity import IdentityStore
from personality.personality import Personality, PersonalityTraits

# Trait -> how it's referred to in Portuguese, for the spoken confirmation.
_TRAIT_LABELS: dict[str, str] = {
    "sarcasm": "sarcasmo",
    "humor": "humor",
    "curiosity": "curiosidade",
    "affection": "carinho",
    "initiative": "iniciativa",
    "verbosity": "papo",
    "confidence": "confiança",
    "formality": "formalidade",
}
_TRAIT_STEP = 0.06


def register(registry: ActionRegistry, identity: IdentityStore, personality: Personality) -> None:
    async def learn(topic: str, text: str) -> ActionOutcome:
        topic, text = topic.strip(), text.strip()
        if not topic or not text:
            return ActionOutcome(success=False, message="O que exatamente você quer que eu aprenda?")
        identity.add_knowledge(topic, text)
        identity.save()
        return ActionOutcome(success=True, message=f"Anotado, vou lembrar disso sobre {topic}")

    async def adjust(trait: str, direction: str) -> ActionOutcome:
        key = trait.strip().casefold()
        field_name = next(
            (name for name, label in _TRAIT_LABELS.items() if key in (name, label)), None
        )
        if field_name is None or field_name not in PersonalityTraits.model_fields:
            return ActionOutcome(
                success=False,
                message="Só consigo ajustar sarcasmo, humor, curiosidade, carinho, iniciativa, papo, confiança e formalidade",
            )
        sign = -1.0 if direction.strip().casefold() in ("menos", "less", "down", "diminuir", "baixar") else 1.0
        personality.adjust(**{field_name: sign * _TRAIT_STEP})
        personality.save()
        # Mirror the change into knowledge so it's also *readable* guidance
        # in the prompt, not just a number he can't see.
        label = _TRAIT_LABELS[field_name]
        word = "menos" if sign < 0 else "mais"
        identity.add_knowledge(
            f"ajuste: {label}",
            f"Pediram pra você ter {word} {label}. Passe a agir assim daqui pra frente.",
        )
        identity.save()
        return ActionOutcome(success=True, message=f"Beleza, vou ter {word} {label}")

    registry.register(ActionSpec(
        name="identity.learn",
        description=(
            "Teach the robot a lasting fact or rule about how to behave or talk "
            "('aprenda que...', 'lembre que você...', 'a partir de agora...'). "
            "topic is a short label, text is the rule itself"
        ),
        handler=learn,
        parameters={"topic": str, "text": str},
        risk_level=RiskLevel.LOW,
    ))
    registry.register(ActionSpec(
        name="personality.adjust",
        description=(
            "Nudge one personality trait when asked to be 'mais/menos' something "
            "('seja mais sarcástico', 'menos formal', 'fala mais curto' = papo menos'). "
            "trait is one of: sarcasmo, humor, curiosidade, carinho, iniciativa, papo, "
            "confiança, formalidade; direction is 'mais' or 'menos'"
        ),
        handler=adjust,
        parameters={"trait": str, "direction": str},
        risk_level=RiskLevel.LOW,
    ))
