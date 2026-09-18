from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from integrations.music.devices import SpotifyDevice
from integrations.music.lyrics import LrclibProvider
from integrations.music.models import PlaybackState, VisualCue
from integrations.music.spotify import SpotifyProvider
from integrations.music.visual_planner import TypographicPlanner, classify_mood


class MusicExperienceService:
    def __init__(self, spotify: SpotifyProvider, lyrics: LrclibProvider | None = None) -> None:
        self.spotify, self.lyrics, self.planner = spotify, lyrics or LrclibProvider(), TypographicPlanner()
        self._plans: dict[str, list[VisualCue]] = {}
        self._moods: dict[str, str] = {}
        self._lock = asyncio.Lock()
        # True only while the robot itself is the one presenting music on the
        # tablet -- set on a robot-initiated `play`, cleared on `pause`/wake.
        # Without this, the tablet would mirror whatever happens to be
        # playing on the user's own Spotify session (phone, PC...) any time
        # it's on, which is not something the user asked the robot to show.
        self.presenting = False
        # Whether the last poll tick saw ambient playback (elsewhere)
        # still going, and when the "quer que eu abra o player aqui?"
        # offer was last made -- together these define one "listening
        # session": ask once per session (not once per track, so a new
        # song starting mid-session never re-prompts), and only ask again
        # either after a genuine gap in playback or once real time has
        # passed. See `should_offer`.
        self._ambient_playing = False
        self._last_offer_at: datetime | None = None
        self._re_offer_after = timedelta(hours=2)
        # The device list changes rarely (someone opens/closes Spotify on
        # a phone) but every fetch counts against Spotify's tight
        # Development-Mode quota -- so it's only fetched when someone asks
        # to play something, and reused for a short while.
        self._devices: list[SpotifyDevice] = []
        self._devices_at = 0.0
        self._devices_ttl = 45.0

    async def devices(self, *, force: bool = False) -> list[SpotifyDevice]:
        """Devices available to play on, cached briefly. Raises whatever
        the provider raises (e.g. a rate limit) -- callers that can carry
        on without the list should catch it."""
        if not force and self._devices and time.monotonic() - self._devices_at < self._devices_ttl:
            return self._devices
        self._devices = await self.spotify.devices()
        self._devices_at = time.monotonic()
        return self._devices

    def should_offer(self, is_playing: bool) -> bool:
        """Whether to prompt to open the player right now for playback
        happening elsewhere. Call once per poll tick with whether ambient
        playback is currently active, regardless of whether an offer ends
        up being shown -- that's what lets a real gap in playback (the
        source pausing, or switching off) be told apart from just the
        track changing, which is the whole point: a new song within an
        already-answered session should stay silent.
        """
        now = datetime.now(timezone.utc)
        if not is_playing:
            self._ambient_playing = False
            return False
        if self._ambient_playing:
            stale = (
                self._last_offer_at is None
                or now - self._last_offer_at >= self._re_offer_after
            )
            if not stale:
                return False
        self._ambient_playing = True
        self._last_offer_at = now
        return True

    async def play(self, query: str, device_id: str | None = None) -> PlaybackState | None:
        # Set *before* the (multi-step, network-bound) call below, not
        # after -- the sync loop's ambient-offer check runs concurrently
        # on its own poll tick, and with this flag only flipping once
        # spotify.play() fully returns, a poll landing in that window sees
        # `presenting` still False while the very track this robot itself
        # just started is already audible, and misreads it as "someone
        # else's session" -- producing the exact "vi que você está ouvindo
        # em outro dispositivo" prompt right on top of the robot's own
        # freshly started playback.
        self.presenting = True
        try:
            track = await (self.spotify.play(query, device_id) if device_id else self.spotify.play(query))
        except Exception:
            self.presenting = False
            raise
        if track is None:
            self.presenting = False
        return track

    async def pause(self) -> None:
        await self.spotify.pause()
        self.presenting = False

    async def resume(self) -> None:
        await self.spotify.resume()
        self.presenting = True

    async def current_payload(self) -> dict | None:
        track = await self.spotify.current()
        if track is None: return None
        return await self.payload_for(track)

    async def payload_for(self, track: PlaybackState) -> dict:
        """Builds the scene payload for an *already known* PlaybackState --
        used right after `play()` so the scene shown is guaranteed to be
        the track that was just started, not whatever a fresh
        `/currently-playing` call happens to answer with. Spotify's own
        state takes a moment to catch up after a command (especially when
        that command just woke up a previously inactive device), so a
        second, independent lookup right afterward can still come back
        stale and show the *previous* track's photo for a beat -- this
        avoids that lookup entirely instead of racing it.
        """
        async with self._lock:
            if track.track_id not in self._plans:
                lines = await self.lyrics.synchronized(track)
                self._plans[track.track_id] = self.planner.plan(track.track_id, lines) if lines else []
                # Whole-track mood, used only as Player Mode's fallback (no
                # lyrics to classify per line there). Lyric Mode uses each
                # cue's own mood instead -- see `TypographicPlanner.plan`.
                self._moods[track.track_id] = classify_mood(lines)
            cues = self._plans[track.track_id]
            mood = self._moods[track.track_id]
        return {**track.payload(), "mode": "lyrics" if cues else "player", "mood": mood,
                "visual_cues": [cue.payload() for cue in cues]}
