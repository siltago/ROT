"""Future vision interface. Not implemented in this phase.

A concrete camera-backed implementation will produce frames consumed by
perception/faces/recognizer.py and any future object/scene detectors. The
brain only ever sees IdentityResult / structured events derived from vision,
never raw frames.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class VisionSource(ABC):
    @abstractmethod
    async def get_frame(self) -> bytes:
        """Return the latest camera frame (encoded image bytes)."""
