"""Data shapes for a skill Bob has been "taught" by the LLM.

A learned skill is a JSON "recipe" -- a small, fixed, safe vocabulary of
steps (see `SkillStepKind`), never raw LLM-generated Python. See
`skills/interpreter.py` for why, and `PROJECT.md`/the plan notes for the
full "Bob is a child, OpenAI is the tutor" rationale.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from brain.models import RiskLevel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SkillStepKind(str, Enum):
    WAIT = "wait"
    SPEAK = "speak"
    CALL_ACTION = "call_action"
    # Reserved for a future world-state-writing step -- not implemented
    # yet (the interpreter raises NotImplementedError if it's ever hit).
    # Kept in the enum now so a stored recipe's shape never needs to
    # change just to add support for it later.
    SET_STATE = "set_state"


class SkillStep(BaseModel):
    kind: SkillStepKind
    # WAIT: an arithmetic expression over the skill's own declared
    # parameters, e.g. "minutes*60" -- resolved by the interpreter's safe
    # evaluator, never Python `eval()`.
    seconds_expr: Optional[str] = None
    # SPEAK: plain text, may reference parameters via "{param}" (resolved
    # with str.format, not code).
    text: Optional[str] = None
    # CALL_ACTION: the target must already be a registered ActionSpec name
    # (hand-coded or a previously learned skill) -- validated at teach time.
    action_name: Optional[str] = None
    # Each value is itself an expression resolved against the skill's
    # parameters before the call, same as seconds_expr.
    arguments: dict[str, str] = Field(default_factory=dict)


class LearnedSkillRecord(BaseModel):
    id: str = ""
    name: str
    description: str
    # Parameter name -> type name ("str"/"float"/"int"/"bool"), mirrors
    # ActionSpec.parameters but JSON-serializable.
    parameters: dict[str, str] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    start_steps: list[SkillStep] = Field(default_factory=list)
    # Paired "how to stop/undo what start_steps began" -- required
    # whenever start_steps begins something ongoing (validated at teach
    # time, see skills/teaching_prompt.py). None only for one-shot skills
    # that don't start anything to later stop.
    stop_steps: Optional[list[SkillStep]] = None
    # If stop_steps is set, it's also registered as its own callable
    # action under this name (e.g. "utility.timer.cancel").
    stop_action_name: Optional[str] = None
    created_from_utterance: str = ""
    # Not used by anything in v1 except being incremented on failure --
    # left in place so a future revision-on-failure loop doesn't need a
    # schema migration.
    version: int = 1
    failure_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)

    def model_dump_json_safe(self) -> dict[str, Any]:
        """`model_dump(mode="json")` but as a plain dict -- what actually
        gets handed to a Repository (JSON-serializable, no datetime/enum
        objects), matching how `MemoryRecord`/`PersonProfile` are stored
        elsewhere in this codebase."""
        return self.model_dump(mode="json")
