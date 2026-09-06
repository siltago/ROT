"""Validated action surface for music playback."""
from __future__ import annotations

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel


def register(registry: ActionRegistry, service=None) -> None:
    async def play_music(query: str) -> ActionOutcome:
        if not query.strip():
            return ActionOutcome(success=False, message="Qual música você quer ouvir?")
        if service is None or not service.spotify.configured:
            return ActionOutcome(success=False, message="O Spotify ainda não está conectado ao Bob.")
        track = await service.play(query)
        # Built from the PlaybackState `play()` itself just returned, not a
        # fresh `/currently-playing` lookup -- Spotify's own state can lag
        # a beat right after a command (especially one that just woke up a
        # previously inactive device), so a second, independent query here
        # could still answer with the *previous* track and show its photo
        # for a moment instead of the one that was just requested.
        data = await service.payload_for(track) if track else None
        return ActionOutcome(success=track is not None,
            message=f"Tocando {track.title}" if track else "Não consegui iniciar a música.", data=data or {})

    async def stop_music() -> ActionOutcome:
        if service is None or not service.spotify.configured:
            return ActionOutcome(success=False, message="O Spotify ainda não está conectado ao Bob.")
        await service.pause()
        return ActionOutcome(success=True, message="Pausei a música")

    async def resume_music() -> ActionOutcome:
        """Continues whatever was paused -- distinct from `play_music`,
        which always starts a *specific* track by name. Without this as
        its own action, "volta"/"continua"/"despausa" had nothing to match
        that actually resumed playback."""
        if service is None or not service.spotify.configured:
            return ActionOutcome(success=False, message="O Spotify ainda não está conectado ao Bob.")
        await service.resume()
        return ActionOutcome(success=True, message="Voltando a música")

    async def show_now_playing() -> ActionOutcome:
        """Both "what's playing" and "open the player" land here: whether
        Spotify is already playing (anywhere -- the robot itself, the
        user's phone, their PC...) or the user just wants the visual scene
        up, the answer is the same lookup, and showing the scene is a
        reasonable side effect of "what's playing" either way."""
        if service is None or not service.spotify.configured:
            return ActionOutcome(success=False, message="O Spotify ainda não está conectado ao Bob.")
        payload = await service.current_payload()
        if payload is None:
            return ActionOutcome(success=False, message="Não tem nada tocando no Spotify agora.")
        service.presenting = True
        title, artist = payload.get("title", ""), payload.get("artist", "")
        message = f"Tocando {title}" + (f", de {artist}" if artist else "")
        return ActionOutcome(success=True, message=message, data=payload)

    async def hide_player() -> ActionOutcome:
        """Closes the on-screen scene WITHOUT touching actual playback --
        distinct from `stop_music`, which pauses Spotify itself. Without
        this as its own action, a request to just close the screen had
        nothing better to match than `show_now_playing`, which immediately
        reopens it -- the exact "sai e volta na hora" bug this exists to
        fix. `TabletBrainBridge.process_text` already dismisses the scene
        message at the start of every turn; this only has to stop the sync
        loop from bringing it right back on the next poll tick."""
        if service is not None:
            service.presenting = False
        return ActionOutcome(success=True, message="Saindo do modo player")

    registry.register(
        ActionSpec(
            name="music.play",
            description="Play a NEW song/artist/playlist by name. The query can be just a band/"
                        "artist name with no specific song named ('toca Metallica') -- Spotify's own "
                        "search picks a popular track for that artist, so still call this rather than "
                        "answering conversationally with a song suggestion. Do NOT use this to resume "
                        "something already paused with no new song named ('volta', 'continua', "
                        "'despausa'); that's music.resume.",
            handler=play_music,
            parameters={"query": str},
            risk_level=RiskLevel.LOW,
            timeout_seconds=20,
        )
    )
    registry.register(
        ActionSpec(
            name="music.stop",
            description="Pause the actual Spotify playback (not just the on-screen scene) -- "
                        "use for 'para a música', 'pausa a música'. Do NOT use this just to close "
                        "the screen while leaving the music playing; that's music.hide_player.",
            handler=stop_music,
            parameters={},
            risk_level=RiskLevel.LOW,
            timeout_seconds=12,
        )
    )
    registry.register(
        ActionSpec(
            name="music.resume",
            description="Resume/continue whatever track was already paused -- no query, no new "
                        "search. Use for 'volta', 'continua', 'despausa', 'retoma a música'. Do NOT "
                        "use music.play for this (it always starts a new search).",
            handler=resume_music,
            parameters={},
            risk_level=RiskLevel.LOW,
            timeout_seconds=12,
        )
    )
    registry.register(
        ActionSpec(
            name="music.now_playing",
            description="OPEN (or reopen) the on-screen music player/lyrics scene and say what's "
                        "currently playing -- use for 'que música é essa', 'abre o player', 'mostra "
                        "o que tá tocando'. Do NOT use this to close/hide the scene.",
            handler=show_now_playing,
            parameters={},
            risk_level=RiskLevel.LOW,
            timeout_seconds=12,
        )
    )
    registry.register(
        ActionSpec(
            name="music.hide_player",
            description="CLOSE/hide the on-screen music player or lyrics scene, leaving the actual "
                        "music still playing in the background -- use for 'sai do player', 'fecha "
                        "essa tela', 'esconde a música', 'tira isso da tela'.",
            handler=hide_player,
            parameters={},
            risk_level=RiskLevel.LOW,
            timeout_seconds=5,
        )
    )
