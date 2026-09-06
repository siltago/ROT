from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlaybackState:
    track_id: str
    title: str
    artist: str
    album: str
    artwork_url: str
    progress_ms: int
    duration_ms: int
    is_playing: bool
    observed_at_ms: int
    device_name: str = ""

    def payload(self) -> dict:
        return {"track_id": self.track_id, "title": self.title, "artist": self.artist,
                "album": self.album, "artwork_url": self.artwork_url,
                "progress_ms": self.progress_ms, "duration_ms": self.duration_ms,
                "is_playing": self.is_playing, "observed_at_ms": self.observed_at_ms,
                "device_name": self.device_name}


@dataclass(frozen=True)
class LyricLine:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class VisualCue:
    start_ms: int
    end_ms: int
    text: str
    emphasis: str = "normal"
    layout: str = "center"
    scale: float = 1.0
    words: list[str] = field(default_factory=list)
    # Classified per line (not once for the whole track) so the typography
    # actually alternates as the song itself moves between, say, an angry
    # verse and a tender chorus -- see `_classify_mood_from_lyrics`.
    mood: str = "bright"

    def payload(self) -> dict:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms, "text": self.text,
                "emphasis": self.emphasis, "layout": self.layout, "scale": self.scale,
                "words": self.words, "mood": self.mood}
