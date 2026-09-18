"""Generic "which one do you mean?" -- Bob asks, the next thing said answers.

Any action can turn an ambiguous request into a question instead of a
guess: it returns an unsuccessful ActionOutcome whose message is the
question (ending in "?") and whose `data["choice"]` describes the options
(see `PendingChoice.from_outcome_data`). RobotAgent stores that as the
pending choice; the *next* user turn is matched against the options
first. A match re-runs the same action with the chosen value filled in,
so the action itself stays a plain function -- it never has to know it
was answered.

Built for "toca X" -> "onde você quer ouvir?" but deliberately unaware of
music: the same thing works for "acende a luz" -> "qual luz?", the TV, etc.

Rules that keep it from getting in the way:
- an answer that doesn't match anything just drops the question and is
  handled as a brand-new request (nobody gets trapped in a menu);
- a choice expires on its own if nobody answers;
- "cancela"/"deixa pra lá" cancels it; "tanto faz" takes the first option.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from integrations.music.devices import normalize

CHOICE_TTL_SECONDS = 60.0

_CANCEL = ("cancela", "cancelar", "deixa pra la", "deixa quieto", "esquece", "nenhum", "nao quero")
_ANY = ("tanto faz", "qualquer", "voce escolhe", "escolhe voce", "escolhe ai", "pode ser qualquer")
# "sempre no PC" / "de agora em diante" -> also remember the answer.
_REMEMBER = ("sempre", "padrao", "de agora em diante", "daqui pra frente", "toda vez")
_ORDINALS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("primeiro", "primeira", "1", "um"), 0),
    (("segundo", "segunda", "2", "dois"), 1),
    (("terceiro", "terceira", "3", "tres"), 2),
    (("quarto", "quarta", "4", "quatro"), 3),
)


@dataclass(frozen=True)
class ChoiceOption:
    label: str
    value: str
    aliases: tuple[str, ...] = ()


@dataclass
class PendingChoice:
    action: str
    arguments: dict[str, Any]
    param: str
    options: list[ChoiceOption]
    # If set, "sempre..." in the answer stores the picked value under this
    # preference key (see IdentityState.preferences).
    remember_key: str | None = None
    created_at: float = field(default_factory=time.monotonic)

    @classmethod
    def from_outcome_data(cls, action: str, arguments: dict[str, Any], data: dict[str, Any]) -> "PendingChoice | None":
        raw = data.get("choice")
        if not isinstance(raw, dict):
            return None
        options = [
            ChoiceOption(
                label=str(o.get("label", "")),
                value=str(o.get("value", "")),
                aliases=tuple(str(a) for a in o.get("aliases", ())),
            )
            for o in raw.get("options", [])
            if o.get("value")
        ]
        if len(options) < 2 or not raw.get("param"):
            return None
        return cls(
            action=action,
            arguments=dict(arguments),
            param=str(raw["param"]),
            options=options,
            remember_key=raw.get("remember_key"),
        )

    def expired(self) -> bool:
        return time.monotonic() - self.created_at > CHOICE_TTL_SECONDS


@dataclass(frozen=True)
class ChoiceAnswer:
    kind: str  # "picked" | "cancelled" | "no_match"
    option: ChoiceOption | None = None
    remember: bool = False


def _has_word(haystack: str, needle: str) -> bool:
    import re

    return bool(needle) and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def resolve(choice: PendingChoice, text: str) -> ChoiceAnswer:
    """Matches a spoken answer against the options -- by name/alias, by
    ordinal ("o segundo"), or by intent ("tanto faz" = first, "deixa" =
    cancel). Anything else is `no_match` (the caller treats it as a new
    request)."""
    said = normalize(text)
    if not said:
        return ChoiceAnswer("no_match")
    remember = any(_has_word(said, normalize(word)) for word in _REMEMBER)

    if any(_has_word(said, word) for word in _CANCEL):
        return ChoiceAnswer("cancelled")
    if any(_has_word(said, word) for word in _ANY):
        return ChoiceAnswer("picked", choice.options[0], remember)

    hits = [
        option for option in choice.options
        if _has_word(said, normalize(option.value))
        or any(_has_word(said, normalize(alias)) for alias in option.aliases)
    ]
    if len(hits) == 1:
        return ChoiceAnswer("picked", hits[0], remember)
    if len(hits) > 1:
        return ChoiceAnswer("no_match")

    for words, index in _ORDINALS:
        if index < len(choice.options) and any(_has_word(said, w) for w in words):
            return ChoiceAnswer("picked", choice.options[index], remember)
    return ChoiceAnswer("no_match")


class ChoiceState:
    """The (at most one) question Bob is currently waiting on."""

    def __init__(self) -> None:
        self.pending: PendingChoice | None = None

    @property
    def active(self) -> bool:
        if self.pending is not None and self.pending.expired():
            self.pending = None
        return self.pending is not None

    def ask(self, choice: PendingChoice) -> None:
        self.pending = choice

    def clear(self) -> None:
        self.pending = None
