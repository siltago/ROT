"""Core data models shared across the brain, actions, and perception layers.

These types are the contract between subsystems. Perception, decision-making,
and execution all speak these models instead of reaching into each other's
internals.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntentType(str, Enum):
    DIALOGUE = "DIALOGUE"
    ACTION = "ACTION"
    DIALOGUE_AND_ACTION = "DIALOGUE_AND_ACTION"
    QUESTION = "QUESTION"
    MEMORY = "MEMORY"
    AMBIGUOUS = "AMBIGUOUS"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionRequest(BaseModel):
    """An action the decision engine wants performed, before validation."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    """Structured output of the DecisionEngine for a single user turn."""

    type: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    actions: list[ActionRequest] = Field(default_factory=list)
    memory_candidate: Optional[str] = None
    reasoning_summary: Optional[str] = None
    raw_text: str = ""


class ActionOutcome(BaseModel):
    success: bool
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class ActionRecord(BaseModel):
    """A logged, executed (or rejected) action for observability."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    required_confirmation: bool = False
    confirmed: bool = False
    outcome: Optional[ActionOutcome] = None
    timestamp: datetime = Field(default_factory=utcnow)


class IdentityResult(BaseModel):
    """Result of resolving 'who is speaking/present' -- from voice or vision."""

    person_id: Optional[str] = None
    confidence: float = 0.0
    source: str = "unknown"  # e.g. "voice", "face", "manual"


class Turn(BaseModel):
    """One exchange in a conversation."""

    speaker: str  # "user" or "robot"
    text: str
    person_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=utcnow)


class BrainEvent(BaseModel):
    """A structured observability event -- never raw model chain-of-thought."""

    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utcnow)
