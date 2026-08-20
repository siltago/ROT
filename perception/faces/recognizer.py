"""Future face-recognition interface. Not implemented in this phase.

When implemented, a concrete FaceRecognizer will take a camera frame and
return an IdentityResult, same contract as any other IdentityResolver. The
brain will not need to change.
"""
from __future__ import annotations

from brain.models import IdentityResult
from perception.identity.resolver import IdentityResolver


class FaceRecognizer(IdentityResolver):
    """Placeholder. Real implementation (e.g. embeddings + nearest-neighbor
    match against stored face vectors in data/people/) comes in a later
    phase, once a camera is attached."""

    async def resolve(self, frame: bytes | None = None, **_) -> IdentityResult:
        raise NotImplementedError("Face recognition is not implemented in this phase.")
