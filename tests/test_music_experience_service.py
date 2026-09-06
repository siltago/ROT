import asyncio

import pytest

from integrations.music.models import PlaybackState
from integrations.music.service import MusicExperienceService


class SlowSpotify:
    """A play() that takes a moment to resolve, standing in for the real
    multi-step (search + PUT + queue + confirm) network round-trip."""
    def __init__(self, *, result: PlaybackState | None, raises: Exception | None = None) -> None:
        self.result = result
        self.raises = raises
        self.presenting_seen_mid_call: bool | None = None

    async def play(self, query: str):
        # Simulate the concurrent sync loop's ambient-offer poll landing
        # while this call is still in flight.
        await asyncio.sleep(0)
        self.presenting_seen_mid_call = self.service.presenting  # type: ignore[attr-defined]
        if self.raises is not None:
            raise self.raises
        return self.result


@pytest.mark.asyncio
async def test_presenting_is_true_before_the_network_call_completes() -> None:
    # Regression test: `presenting` used to flip only *after* spotify.play()
    # fully returned, leaving a window where a concurrent ambient-offer poll
    # sees `presenting=False` while the robot's own track is already
    # audible, and misreads its own playback as "someone else's session".
    track = PlaybackState("t1", "One", "Metallica", "", "", 0, 1000, True, 0)
    spotify = SlowSpotify(result=track)
    service = MusicExperienceService(spotify)
    spotify.service = service  # type: ignore[attr-defined]

    assert service.presenting is False
    result = await service.play("Metallica")

    assert spotify.presenting_seen_mid_call is True
    assert service.presenting is True
    assert result is track


@pytest.mark.asyncio
async def test_presenting_resets_on_failure() -> None:
    spotify = SlowSpotify(result=None, raises=RuntimeError("boom"))
    service = MusicExperienceService(spotify)
    spotify.service = service  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError):
        await service.play("Metallica")

    assert service.presenting is False


class NoLyrics:
    async def synchronized(self, track):
        return []


class RecordingSpotify:
    """Tracks whether `current()` was called -- payload_for must never
    trigger it."""
    def __init__(self) -> None:
        self.current_calls = 0

    async def current(self):
        self.current_calls += 1
        return None


@pytest.mark.asyncio
async def test_payload_for_never_re_queries_spotify() -> None:
    # Regression test: building the scene from a fresh `/currently-playing`
    # call right after `play()` could still answer with the *previous*
    # track for a beat (Spotify's own state lags right after a command,
    # more so right after waking a previously inactive device) -- showing
    # its photo instead of the one that was just requested. payload_for
    # must build the scene from the PlaybackState already in hand instead.
    spotify = RecordingSpotify()
    service = MusicExperienceService(spotify, lyrics=NoLyrics())
    track = PlaybackState("t1", "Enter Sandman", "Metallica", "", "", 0, 1000, True, 0)

    payload = await service.payload_for(track)

    assert spotify.current_calls == 0
    assert payload["track_id"] == "t1"
    assert payload["title"] == "Enter Sandman"
    assert payload["mode"] == "player"


@pytest.mark.asyncio
async def test_presenting_resets_when_nothing_was_found() -> None:
    spotify = SlowSpotify(result=None)
    service = MusicExperienceService(spotify)
    spotify.service = service  # type: ignore[attr-defined]

    result = await service.play("uma música que não existe")

    assert result is None
    assert service.presenting is False
