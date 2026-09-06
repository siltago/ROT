import pytest

from integrations.music.spotify import SpotifyError, SpotifyProvider


@pytest.mark.asyncio
async def test_play_strips_connector_words_before_searching() -> None:
    provider = SpotifyProvider("id", "secret", "refresh")
    seen_queries: list[str] = []

    async def fake_request(method, path, body=None):
        if "/v1/search" in path:
            seen_queries.append(path)
            return {"tracks": {"items": [{"id": "t1", "uri": "spotify:track:t1", "name": "One",
                                            "duration_ms": 1000, "artists": [{"id": "a1", "name": "Metallica"}],
                                            "album": {"name": "", "images": []}}]}}
        if path == "/v1/me/player/currently-playing":
            return {"item": {"id": "t1", "name": "One", "duration_ms": 1000,
                              "artists": [{"name": "Metallica"}], "album": {"name": "", "images": []}},
                    "progress_ms": 0, "is_playing": True}
        return None

    provider._request = fake_request  # type: ignore[method-assign]
    await provider.play("da banda Metallica")

    assert len(seen_queries) == 1
    # The literal connector words must not reach Spotify's search query --
    # verified live that they measurably hurt relevance (sometimes to the
    # point of an apparent "no results" failure for a query that works
    # fine once the filler is stripped).
    assert "da+banda" not in seen_queries[0] and "da%20banda" not in seen_queries[0]
    assert "Metallica" in seen_queries[0]


def _fake_search_response(count: int) -> dict:
    return {"tracks": {"items": [
        {"id": f"t{i}", "uri": f"spotify:track:t{i}", "name": f"Track {i}",
         "duration_ms": 1000, "artists": [{"id": "a1", "name": "Metallica"}],
         "album": {"name": "", "images": []}}
        for i in range(count)
    ]}}


@pytest.mark.asyncio
async def test_play_starts_the_exact_requested_track_not_a_shuffled_pick() -> None:
    # Regression test: an earlier version played the matched track's whole
    # *artist* context on shuffle instead of the requested track itself, so
    # asking for one specific song could start playing a completely
    # different one by the same artist ("toca uma coisa e ele toca outra").
    provider = SpotifyProvider("id", "secret", "refresh")
    play_calls: list[dict] = []
    queued_uris: list[str] = []

    async def fake_request(method, path, body=None):
        if "/v1/search" in path:
            return _fake_search_response(6)
        if path == "/v1/me/player/play":
            play_calls.append(body)
            return None
        if path.startswith("/v1/me/player/queue"):
            queued_uris.append(path.split("uri=")[1])
            return None
        if path == "/v1/me/player/currently-playing":
            return {"item": {"id": "t0", "name": "Track 0", "duration_ms": 1000,
                              "artists": [{"name": "Metallica"}], "album": {"name": "", "images": []}},
                    "progress_ms": 0, "is_playing": True}
        return None

    provider._request = fake_request  # type: ignore[method-assign]
    await provider.play("Metallica")

    # The exact top match plays immediately -- never the artist's shuffled
    # catalog at large.
    assert play_calls == [{"uris": ["spotify:track:t0"]}]
    # Continuation comes from queueing a few of the search's other matches
    # instead, so playback doesn't just stop after the one song.
    assert 1 <= len(queued_uris) <= 4
    assert "spotify%3Atrack%3At0" not in queued_uris


@pytest.mark.asyncio
async def test_play_retries_on_an_available_device_when_none_is_active() -> None:
    # "No active device" doesn't mean nothing is available -- a device
    # shows up in /v1/me/player/devices as soon as its Spotify client is
    # merely running (even paused, even backgrounded); Spotify just won't
    # pick one on its own without an explicit device_id.
    provider = SpotifyProvider("id", "secret", "refresh")
    play_attempts: list[str] = []

    async def fake_request(method, path, body=None):
        if "/v1/search" in path:
            return {"tracks": {"items": [{"id": "t1", "uri": "spotify:track:t1", "name": "One",
                                            "duration_ms": 1000, "artists": [{"id": "a1", "name": "Metallica"}],
                                            "album": {"name": "", "images": []}}]}}
        if path == "/v1/me/player/shuffle?state=true":
            return None
        if path == "/v1/me/player/play":
            play_attempts.append(path)
            raise SpotifyError('Spotify respondeu HTTP 404: {"error": {"reason": "NO_ACTIVE_DEVICE"}}')
        if path == "/v1/me/player/devices":
            return {"devices": [{"id": "device-1", "is_active": False}]}
        if path.startswith("/v1/me/player/play?"):
            play_attempts.append(path)
            return None
        if path == "/v1/me/player/currently-playing":
            return {"item": {"id": "t1", "name": "One", "duration_ms": 1000,
                              "artists": [{"name": "Metallica"}], "album": {"name": "", "images": []}},
                    "progress_ms": 0, "is_playing": True}
        return None

    provider._request = fake_request  # type: ignore[method-assign]
    await provider.play("Metallica")

    assert play_attempts == ["/v1/me/player/play", "/v1/me/player/play?device_id=device-1"]


@pytest.mark.asyncio
async def test_play_fails_clearly_when_truly_no_device_exists_anywhere() -> None:
    provider = SpotifyProvider("id", "secret", "refresh")

    async def fake_request(method, path, body=None):
        if "/v1/search" in path:
            return {"tracks": {"items": [{"id": "t1", "uri": "spotify:track:t1", "name": "One",
                                            "duration_ms": 1000, "artists": [{"id": "a1", "name": "Metallica"}],
                                            "album": {"name": "", "images": []}}]}}
        if path == "/v1/me/player/shuffle?state=true":
            return None
        if path == "/v1/me/player/play":
            raise SpotifyError('Spotify respondeu HTTP 404: {"error": {"reason": "NO_ACTIVE_DEVICE"}}')
        if path == "/v1/me/player/devices":
            return {"devices": []}
        return None

    provider._request = fake_request  # type: ignore[method-assign]
    with pytest.raises(SpotifyError, match="aparelho"):
        await provider.play("Metallica")
