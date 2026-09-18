from __future__ import annotations

import asyncio, base64, json, random, re, time, urllib.error, urllib.parse, urllib.request
from contextlib import suppress
from integrations.music.devices import SpotifyDevice
from integrations.music.models import PlaybackState


class SpotifyError(RuntimeError):
    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        # Spotify's own `Retry-After` header on a 429, in seconds, when it
        # sent one -- the real, authoritative backoff window instead of a
        # guess. None when absent or the error wasn't a 429.
        self.retry_after = retry_after


# Strips leading connector words ("da banda X", "do grupo X" -> "X") from a
# play query -- Spotify's search is a fuzzy full-text match, and filler
# words measurably hurt its relevance (verified live: "da banda Metallica"
# turned up an unrelated track that a plain "Metallica" search didn't).
# Applied once here so every caller benefits regardless of whether the
# query came from a regex capture or the LLM action router.
_QUERY_FILLER_PREFIX = re.compile(r"^(?:da\s+banda\s+|do\s+grupo\s+|d[ao]s?\s+)+", re.I)


class SpotifyProvider:
    """Spotify Web API client. OAuth secrets never leave the brain."""
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, *, timeout: float = 8) -> None:
        self.client_id, self.client_secret, self.refresh_token = client_id, client_secret, refresh_token
        self.timeout, self._access_token, self._expires_at = timeout, "", 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    async def current(self) -> PlaybackState | None:
        if not self.configured:
            return None
        data = await self._request("GET", "/v1/me/player/currently-playing")
        if not data or not data.get("item"):
            return None
        item, album = data["item"], data["item"].get("album") or {}
        images = album.get("images") or []
        device = data.get("device") or {}
        return PlaybackState(str(item.get("id") or ""), str(item.get("name") or ""),
            ", ".join(a.get("name", "") for a in item.get("artists", []) if a.get("name")),
            str(album.get("name") or ""), str(images[0].get("url") if images else ""),
            int(data.get("progress_ms") or 0), int(item.get("duration_ms") or 0),
            bool(data.get("is_playing")), int(time.time() * 1000),
            str(device.get("name") or ""))

    async def devices(self) -> list[SpotifyDevice]:
        """Every device currently logged into this Spotify account that
        Spotify Connect can play on (a device appears as soon as its
        Spotify app is running, even paused or in the background)."""
        if not self.configured:
            return []
        data = await self._request("GET", "/v1/me/player/devices")
        result = []
        for raw in (data or {}).get("devices") or []:
            if not raw.get("id") or raw.get("is_restricted"):
                continue
            result.append(SpotifyDevice(
                id=str(raw["id"]),
                name=str(raw.get("name") or ""),
                type=str(raw.get("type") or ""),
                is_active=bool(raw.get("is_active")),
                volume_percent=raw.get("volume_percent"),
            ))
        return result

    async def play(self, query: str, device_id: str | None = None) -> PlaybackState | None:
        cleaned = _QUERY_FILLER_PREFIX.sub("", query).strip() or query
        # limit=10 (not 1): the top match is what actually plays -- the
        # rest are only a pool for the queue below, so a request never
        # gets ignored in favor of Spotify's own artist-wide shuffle pick.
        # (An earlier version played the whole matched track's *artist*
        # context on shuffle instead of the requested track itself, so
        # asking for one specific song could start playing a completely
        # different one by the same artist -- exactly the "toca uma coisa
        # e ele toca outra" bug this fixes.)
        found = await self._request("GET", "/v1/search?" + urllib.parse.urlencode({"q": cleaned, "type": "track", "limit": 10}))
        items = ((found or {}).get("tracks") or {}).get("items") or []
        if not items:
            raise SpotifyError("Não encontrei essa música no Spotify.")
        track = items[0]
        await self._start_playback({"uris": [track["uri"]]}, device_id)
        # Spotify removed its public recommendations/"radio" endpoint
        # entirely in late 2024 (for every app, not a permission gap) --
        # queueing a few more of this same search's other matches is the
        # closest still-available way to keep playing after the requested
        # track instead of stopping dead after just the one song.
        extras = items[1:]
        random.shuffle(extras)
        for extra in extras[:4]:
            with suppress(SpotifyError):
                await self._request("POST", f"/v1/me/player/queue?uri={urllib.parse.quote(extra['uri'])}")
        await asyncio.sleep(.35)
        return await self.current()

    async def pause(self) -> None:
        await self._ignore_already_in_state("PUT", "/v1/me/player/pause")

    async def resume(self) -> None:
        """Resumes whatever was paused -- no query, no new search. Distinct
        from `play(query)`, which always starts a specific track."""
        try:
            await self._request("PUT", "/v1/me/player/play")
        except SpotifyError as exc:
            if "403" in str(exc):
                return
            if "NO_ACTIVE_DEVICE" in str(exc):
                await self._retry_on_available_device({})
                return
            raise

    async def _start_playback(self, body: dict, device_id: str | None = None) -> None:
        """PUT /v1/me/player/play, retried against a specific device if
        Spotify says nothing is currently active. A device shows up in
        `/v1/me/player/devices` as soon as its Spotify app/client is
        running at all (even paused, even in the background) -- Spotify
        just won't pick one on its own without an explicit device_id, so
        this is what actually saves "toca X" from failing any time nothing
        happens to already be the active device."""
        if device_id:
            # An explicit target (the user chose where to listen): Spotify
            # wakes/transfers to that device itself.
            path = "/v1/me/player/play?" + urllib.parse.urlencode({"device_id": device_id})
            await self._request("PUT", path, body)
            return
        try:
            await self._request("PUT", "/v1/me/player/play", body)
        except SpotifyError as exc:
            if "NO_ACTIVE_DEVICE" not in str(exc):
                raise
            await self._retry_on_available_device(body)

    async def _retry_on_available_device(self, body: dict) -> None:
        devices_response = await self._request("GET", "/v1/me/player/devices")
        devices = (devices_response or {}).get("devices") or []
        if not devices:
            raise SpotifyError("Não achei nenhum aparelho com o Spotify aberto pra tocar.")
        device_id = devices[0]["id"]
        path = "/v1/me/player/play?" + urllib.parse.urlencode({"device_id": device_id})
        await self._request("PUT", path, body or None)

    async def _ignore_already_in_state(self, method: str, path: str) -> None:
        # Asking Spotify to pause an already-paused track (or resume an
        # already-playing one) is a real, documented Spotify behavior that
        # returns HTTP 403 "Restriction violated" -- it's not a failure,
        # it's just already true, so it's swallowed here rather than
        # surfaced as an error up the stack.
        try:
            await self._request(method, path)
        except SpotifyError as exc:
            if "403" not in str(exc):
                raise

    async def _token(self) -> str:
        if self._access_token and time.monotonic() < self._expires_at - 30:
            return self._access_token
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        req = urllib.request.Request("https://accounts.spotify.com/api/token",
            data=urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": self.refresh_token}).encode(),
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
        data = await asyncio.to_thread(self._open_json, req)
        self._access_token, self._expires_at = data["access_token"], time.monotonic() + int(data.get("expires_in", 3600))
        return self._access_token

    async def _request(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request("https://api.spotify.com" + path,
            data=json.dumps(body).encode() if body is not None else None, method=method,
            headers={"Authorization": f"Bearer {await self._token()}", "Content-Type": "application/json"})
        try:
            return await asyncio.to_thread(self._open_json, req)
        except urllib.error.HTTPError as exc:
            if exc.code == 204: return None
            retry_after = None
            if exc.code == 429:
                with suppress(TypeError, ValueError):
                    retry_after = float(exc.headers.get("Retry-After")) if exc.headers else None
            raise SpotifyError(
                f"Spotify respondeu HTTP {exc.code}: {exc.read().decode(errors='replace')[:180]}",
                retry_after=retry_after,
            ) from exc

    def _open_json(self, req):
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            raw = response.read()
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # Not every endpoint returns JSON on success -- queueing a
                # track (POST /v1/me/player/queue), for one, returns an
                # opaque non-JSON token. A 2xx with an unparseable body is
                # still a success; callers that don't need the body (like
                # queueing) never look at this return value anyway.
                return None
