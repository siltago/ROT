from __future__ import annotations

import asyncio
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
        # Track ids already offered ("vi que você está ouvindo em <device>,
        # quer que eu abra aqui?") this run -- asked once per track, whether
        # accepted or declined, so the sync loop never nags on every poll.
        self._offered_tracks: set[str] = set()

    def should_offer(self, track_id: str) -> bool:
        """True the first time this track is seen playing elsewhere; marks
        it offered immediately so concurrent/rapid poll ticks can't both
        see "not yet offered" and each trigger their own prompt."""
        if not track_id or track_id in self._offered_tracks:
            return False
        self._offered_tracks.add(track_id)
        return True

    async def play(self, query: str) -> PlaybackState | None:
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
            track = await self.spotify.play(query)
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
