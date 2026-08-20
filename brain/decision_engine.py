"""Classifies user input into an intent type and, when applicable, structured
action requests.

Low-latency-first design: a deterministic local rule router handles clearly
structured commands (fast path). Anything ambiguous or purely conversational
falls through to DIALOGUE and is handled downstream by the response engine
(which may call an LLM). This keeps common smart-home/robot commands fast
and cheap while still allowing free-form conversation.

This module NEVER touches hardware or integrations directly -- it only
produces a Decision for the planner/executor to act on.
"""
from __future__ import annotations

import re

from brain.models import ActionRequest, Decision, IntentType

# (regex, action_name, arg_extractor) -- ordered, first match wins.
# arg_extractor takes the regex Match and returns a kwargs dict.
_RULES: list[tuple[re.Pattern, str, "callable"]] = [
    (
        re.compile(r"\bliga(?:r)? a?\s*luz\s*(?:d[aoe]\s*)?(?P<room>[\wçãõáéíóú ]*)", re.IGNORECASE),
        "light.turn_on",
        lambda m: {"room": (m.group("room") or "").strip() or "sala"},
    ),
    (
        re.compile(r"\bdesliga(?:r)? a?\s*luz\s*(?:d[aoe]\s*)?(?P<room>[\wçãõáéíóú ]*)", re.IGNORECASE),
        "light.turn_off",
        lambda m: {"room": (m.group("room") or "").strip() or "sala"},
    ),
    (
        re.compile(r"ar[\s-]?condicionado.*?(?P<temp>\d+)\s*graus?|coloca(?:r)? o ar em (?P<temp2>\d+)", re.IGNORECASE),
        "climate.set_temperature",
        lambda m: {"temperature": float(m.group("temp") or m.group("temp2"))},
    ),
    (
        re.compile(r"toca(?:r)?\s+(?:a\s+)?m[uú]sica\s*(?P<query>.*)|play\s+(?P<query2>.*)", re.IGNORECASE),
        "music.play",
        lambda m: {"query": (m.group("query") or m.group("query2") or "").strip() or "favorites"},
    ),
    (
        re.compile(r"para(?:r)? (?:a\s+)?m[uú]sica|stop music", re.IGNORECASE),
        "music.stop",
        lambda m: {},
    ),
    (
        re.compile(r"destrava(?:r)?\s+(?:a\s+)?porta\s*(?:d[aoe]\s*)?(?P<door>[\wçãõáéíóú ]*)|unlock.*door", re.IGNORECASE),
        "door.unlock",
        lambda m: {"door": (m.groupdict().get("door") or "").strip() or "principal"},
    ),
]

_QUESTION_MARKERS = ("?", "quem ", "o que ", "qual ", "quando ", "onde ", "por que ", "why", "what", "who", "when", "where")

_PREFERENCE_MARKERS = (
    "gosto", "prefiro", "não gosto", "odeio", "adoro", "costumo",
    "like", "prefer", "hate", "love",
)


def _looks_like_question(text: str) -> bool:
    t = text.strip().lower()
    return t.endswith("?") or any(t.startswith(m) for m in _QUESTION_MARKERS)


def _looks_like_preference(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in _PREFERENCE_MARKERS)


class DecisionEngine:
    """Deterministic-first intent classifier + action extractor.

    A future version can add an LLM-backed fallback classifier for inputs
    the rule router can't confidently handle; the Decision contract here
    is designed to accommodate that without changing callers.
    """

    def classify(self, text: str) -> Decision:
        text = text.strip()
        if not text:
            return Decision(type=IntentType.AMBIGUOUS, confidence=0.0, raw_text=text)

        matched_actions: list[ActionRequest] = []
        for pattern, action_name, extractor in _RULES:
            match = pattern.search(text)
            if match:
                matched_actions.append(ActionRequest(name=action_name, arguments=extractor(match)))
                break  # fast path: one clear action per turn for now

        has_dialogue_content = self._has_extra_dialogue(text, bool(matched_actions))

        if matched_actions and has_dialogue_content:
            return Decision(
                type=IntentType.DIALOGUE_AND_ACTION,
                confidence=0.9,
                actions=matched_actions,
                raw_text=text,
            )
        if matched_actions:
            return Decision(
                type=IntentType.ACTION,
                confidence=0.97,
                actions=matched_actions,
                raw_text=text,
            )
        if _looks_like_question(text):
            return Decision(type=IntentType.QUESTION, confidence=0.8, raw_text=text)
        if _looks_like_preference(text):
            return Decision(
                type=IntentType.DIALOGUE,
                confidence=0.75,
                memory_candidate=text,
                raw_text=text,
            )
        return Decision(type=IntentType.DIALOGUE, confidence=0.6, raw_text=text)

    @staticmethod
    def _has_extra_dialogue(text: str, matched: bool) -> bool:
        """Heuristic: if the sentence has clearly more content than the
        action phrase itself (e.g. 'está quente aqui, coloca o ar em 22'),
        treat it as DIALOGUE_AND_ACTION rather than pure ACTION."""
        if not matched:
            return False
        return "," in text or len(text.split()) > 8
