"""Persisted physical needs, distinct from EmotionalState (mood, decays
toward a baseline) and DriveState (behavioral motivations, not
persisted): hunger and boredom -- energy/valence/irritation still live
in EmotionalState. See the plan doc for the full picture.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from memory.repository import Repository


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


class NeedsState(BaseModel):
    hunger: float = Field(default=0.2, ge=0.0, le=1.0)
    boredom: float = Field(default=0.0, ge=0.0, le=1.0)
    # How much less random his chess/checkers moves are -- see
    # api/server.py's _ACTIVE_IDLE_KINDS handling and the tablet's
    # idle_chess_overlay.dart/idle_checkers_overlay.dart, which fetch
    # this once per game and bias move selection with it. Not a real
    # chess engine -- just "prefers captures, avoids obvious blunders"
    # more often as this rises.
    game_skill: float = Field(default=0.0, ge=0.0, le=1.0)
    # The drawable subject (one of doodle_subject's curated keys) tied to
    # whatever he last "read" about -- consumed (cleared) the next time
    # /idle/doodle_subject is asked, so a reading session sets up what he
    # tries to draw next, one-shot.
    last_read_subject: str | None = None
    # The human-readable topic of the last reading lesson (e.g.
    # "sarcasmo") -- unlike last_read_subject, this one isn't consumed;
    # it just sits here so "o que você está lendo?" has something real
    # to answer with (see brain/agent.py's current_activity threading).
    last_read_topic: str | None = None


class NeedsStore:
    """Persists a single NeedsState document via any Repository (Supabase
    in production, see app/main.py's build_needs_repository) -- the same
    "singleton document" shape SkillLibrary uses for a list of skills,
    just always addressing the one fixed id since there's only ever one
    robot's needs to track.
    """

    _DOC_ID = "singleton"

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        try:
            record = self.repository.get(self._DOC_ID)
        except Exception:
            # Most likely the sql/002_robot_needs.sql migration hasn't
            # been run against this Supabase project yet -- degrade to a
            # fresh in-memory default rather than taking the whole agent
            # down at boot over one missing table.
            logging.getLogger(__name__).warning(
                "Could not load robot_needs from the repository (has "
                "sql/002_robot_needs.sql been run yet?) -- starting from "
                "a default NeedsState instead."
            )
            record = None
        self.state = NeedsState(**record) if record else NeedsState()

    def save(self) -> None:
        data = self.state.model_dump()
        data["id"] = self._DOC_ID
        try:
            if self.repository.get(self._DOC_ID) is None:
                self.repository.add(data)
            else:
                self.repository.update(self._DOC_ID, data)
        except Exception:
            logging.getLogger(__name__).warning("Could not persist robot_needs (table missing?)")


class NeedsEngine:
    """Applies time-based growth and feeding events to a NeedsStore. Same
    apply/advance/save shape as emotions.engine.EmotionalEngine, so the
    two read the same at call sites."""

    # How long (hours), left completely unattended, hunger takes to go
    # from empty to full on its own.
    HOURS_TO_FULL_HUNGER = 6.0
    # How long (hours), left idle with nothing engaging going on, boredom
    # takes to go from empty to full -- much faster than hunger, boredom
    # is meant to be the "notice something's off" attribute on a much
    # shorter timescale.
    HOURS_TO_FULL_BOREDOM = 0.5
    # How fast boredom drains while actually engaged in an idle activity
    # from the "active" cluster (games, doodling, humming) -- playing
    # should visibly relieve it, not just slow its growth.
    HOURS_TO_EMPTY_BOREDOM_WHILE_ENGAGED = 0.15

    def __init__(self, store: NeedsStore) -> None:
        self.store = store

    @property
    def state(self) -> NeedsState:
        return self.store.state

    def advance(self, elapsed_seconds: float, *, engaged: bool = False) -> NeedsState:
        """Grows hunger with real elapsed time -- call once per cognition
        tick, same pattern as DriveEngine.advance. Boredom grows the same
        way while [engaged] is False (nothing engaging happening), and
        actively drains while it's True (an active-cluster idle vignette
        -- see api/server.py's _ACTIVE_IDLE_KINDS -- is genuinely
        showing)."""
        if elapsed_seconds <= 0:
            return self.store.state
        hours = elapsed_seconds / 3600
        self.store.state.hunger = _clamp01(
            self.store.state.hunger + hours / self.HOURS_TO_FULL_HUNGER
        )
        if engaged:
            self.store.state.boredom = _clamp01(
                self.store.state.boredom - hours / self.HOURS_TO_EMPTY_BOREDOM_WHILE_ENGAGED
            )
        else:
            self.store.state.boredom = _clamp01(
                self.store.state.boredom + hours / self.HOURS_TO_FULL_BOREDOM
            )
        return self.store.state

    def feed(self, amount: float = 0.35) -> NeedsState:
        self.store.state.hunger = _clamp01(self.store.state.hunger - amount)
        return self.store.state

    # Small, deliberately slow -- "gets a little less random each time he
    # plays a match through", not "solves chess in an afternoon".
    GAME_SKILL_GAIN_PER_MATCH = 0.015

    def record_game_result(self) -> NeedsState:
        self.store.state.game_skill = _clamp01(
            self.store.state.game_skill + self.GAME_SKILL_GAIN_PER_MATCH
        )
        return self.store.state

    def set_last_read_subject(self, subject: str | None) -> NeedsState:
        self.store.state.last_read_subject = subject
        return self.store.state

    def set_last_read_topic(self, topic: str | None) -> NeedsState:
        self.store.state.last_read_topic = topic
        return self.store.state

    def consume_last_read_subject(self) -> str | None:
        subject = self.store.state.last_read_subject
        self.store.state.last_read_subject = None
        return subject

    def save(self) -> None:
        self.store.save()
