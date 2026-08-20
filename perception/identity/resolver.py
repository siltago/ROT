"""Identity resolution interface: 'who is this'.

The brain only ever consumes an IdentityResult (person_id + confidence). It
never knows whether identity came from voice, a face embedding, or a manual
CLI login. Concrete resolvers plug in later without touching the brain.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from brain.models import IdentityResult


class IdentityResolver(ABC):
    @abstractmethod
    async def resolve(self, **inputs) -> IdentityResult:
        """Resolve identity from whatever inputs this resolver supports
        (audio embedding, camera frame, manual id, ...)."""


class ManualIdentityResolver(IdentityResolver):
    """Trivial resolver for CLI/text mode: identity is whatever was passed in."""

    async def resolve(self, person_id: str | None = None, **_) -> IdentityResult:
        if person_id:
            return IdentityResult(person_id=person_id, confidence=1.0, source="manual")
        return IdentityResult(person_id=None, confidence=0.0, source="manual")
