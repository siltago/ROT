"""Validated action surface for music playback."""
from __future__ import annotations

import logging
import re

from actions.registry import ActionRegistry, ActionSpec
from brain.models import ActionOutcome, RiskLevel
from integrations.music.devices import SpotifyDevice, match_devices, sort_for_choice

logger = logging.getLogger(__name__)

# IdentityState.preferences key for "always play here without asking".
DEVICE_PREFERENCE_KEY = "music.device"
# Spoken instead of a device when the user wants to be asked every time.
_ASK_EVERY_TIME = ("perguntar", "sempre perguntar", "ask")


def _choice_outcome(devices: list[SpotifyDevice]) -> ActionOutcome:
    """The "onde você quer ouvir?" question -- unsuccessful on purpose (the
    music has NOT started), with the options in `data["choice"]` so
    brain/choice.py can match the answer and re-run music.play."""
    ordered = sort_for_choice(devices)
    labels = [d.label for d in ordered]
    spoken = ", ".join(labels[:-1]) + f" ou {labels[-1]}" if len(labels) > 1 else labels[0]
    return ActionOutcome(
        success=False,
        message=f"Onde você quer ouvir? Tô vendo: {spoken}?",
        data={"choice": {
            "param": "device",
            "remember_key": DEVICE_PREFERENCE_KEY,
            "options": [
                {"label": d.label, "value": d.name, "aliases": list(d.aliases)}
                for d in ordered
            ],
        }},
    )


# "... no PC", "... na sala", "... pelo celular" at the end of a request.
_TRAILING_DEVICE = re.compile(
    r"^(?P<query>.+?)\s+(?:no|na|em|pelo|pela|pro|pra|para\s+o|para\s+a)\s+(?:meu\s+|minha\s+|o\s+|a\s+)?(?P<ref>[^,]+)$",
    re.IGNORECASE,
)


def _split_trailing_device(query: str, devices: list[SpotifyDevice]) -> tuple[str, str]:
    """The fast regex path hands over "Metallica no celular" as one query.
    If its tail names one of the known devices, split it off so Spotify
    searches for the song, not for "no celular"."""
    found = _TRAILING_DEVICE.match(query.strip())
    if found and match_devices(found.group("ref"), devices):
        return found.group("query").strip(), found.group("ref").strip()
    return query, ""


def register(registry: ActionRegistry, service=None, identity=None) -> None:
    async def play_music(query: str, device: str = "") -> ActionOutcome:
        if not query.strip():
            return ActionOutcome(success=False, message="Qual música você quer ouvir?")
        if service is None or not service.spotify.configured:
            return ActionOutcome(success=False, message="O Spotify ainda não está conectado ao Bob.")

        # Where to play: an explicit device wins; else a remembered
        # preference; else ask -- but only when there is genuinely a choice
        # (more than one device logged in). With zero or one device, or if
        # Spotify's device list can't be read right now (rate limit...), it
        # behaves exactly as before and lets Spotify pick.
        try:
            devices = await service.devices()
        except Exception:  # noqa: BLE001 -- never let device discovery block playing music
            logger.warning("Could not list Spotify devices; letting Spotify choose", exc_info=True)
            devices = []
        target: SpotifyDevice | None = None
        reference = device.strip()
        if not reference and devices:
            query, reference = _split_trailing_device(query, devices)
        if reference and devices:
            matches = match_devices(reference, devices)
            if len(matches) == 1:
                target = matches[0]
            elif len(matches) > 1:
                return _choice_outcome(matches)
            else:
                names = ", ".join(d.label for d in sort_for_choice(devices))
                return ActionOutcome(
                    success=False,
                    message=f"Não achei '{reference}' entre os aparelhos com Spotify aberto: {names}.",
                )
        elif len(devices) == 1:
            target = devices[0]
        elif len(devices) > 1:
            preferred = identity.state.preferences.get(DEVICE_PREFERENCE_KEY, "") if identity else ""
            preferred_matches = match_devices(preferred, devices) if preferred else []
            if len(preferred_matches) == 1:
                target = preferred_matches[0]
            else:
                return _choice_outcome(devices)

        track = await service.play(query, target.id if target else None)
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

    async def set_default_device(device: str) -> ActionOutcome:
        """Toca sempre no PC / usa o celular como padrão -- remembers where
        music should go without asking; "perguntar" goes back to asking
        every time."""
        if identity is None:
            return ActionOutcome(success=False, message="Não consigo guardar preferências agora.")
        wanted = device.strip()
        if wanted.casefold() in _ASK_EVERY_TIME:
            identity.state.preferences.pop(DEVICE_PREFERENCE_KEY, None)
            identity.save()
            return ActionOutcome(success=True, message="Combinado, vou perguntar onde tocar sempre")
        if not wanted:
            return ActionOutcome(success=False, message="Em qual aparelho você quer que eu toque por padrão?")
        # Store the *name* when it matches a known device (stable across
        # pc/computador phrasings), else the words as said.
        stored = wanted
        try:
            matches = match_devices(wanted, await service.devices()) if service is not None else []
        except Exception:  # noqa: BLE001
            matches = []
        if len(matches) == 1:
            stored = matches[0].name
        identity.state.preferences[DEVICE_PREFERENCE_KEY] = stored
        identity.save()
        return ActionOutcome(success=True, message=f"Fechado, agora toco no {stored} sem perguntar")

    registry.register(
        ActionSpec(
            name="music.default_device",
            description="Remember which device music should play on by default, so it is not asked "
                        "every time (toca sempre no PC, usa o celular como padrão). device is the "
                        "device (pc, celular, tablet, caixa, or its name); use 'perguntar' to go back "
                        "to asking every time.",
            handler=set_default_device,
            parameters={"device": str},
            risk_level=RiskLevel.LOW,
            timeout_seconds=12,
        )
    )
    registry.register(
        ActionSpec(
            name="music.play",
            description="Play a NEW song/artist/playlist by name. Optional 'device' argument: which "
                        "device to play on (toca X no PC, no celular) -- omit it if not said; Bob "
                        "asks where when several devices are available. The query can be just a band/"
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
