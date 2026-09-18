"""Spotify Connect devices: what Bob can play on, and how to refer to them.

Bob keeps a picture of every device logged into the user's Spotify account
(phone, PC, speaker, TV, the tablet itself...) so "toca X" can ask *where*
to play instead of guessing -- and so "toca no PC" / "no celular" can be
matched from natural speech without anyone hand-writing a name list.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class SpotifyDevice:
    id: str
    name: str
    type: str  # Spotify's own: Computer, Smartphone, Tablet, Speaker, TV, CastAudio...
    is_active: bool = False
    volume_percent: int | None = None

    @property
    def label(self) -> str:
        """How Bob says it out loud: "computador DESKTOP-AB1", "celular
        Galaxy S23" -- the kind first, since that's how people think of
        their devices; the raw name after it, since it's what tells two
        of the same kind apart."""
        kind = _KIND_PT.get(self.type.casefold(), "")
        return f"{kind} {self.name}".strip() if kind else self.name

    @property
    def aliases(self) -> tuple[str, ...]:
        return _KIND_ALIASES.get(self.type.casefold(), ())


_KIND_PT: dict[str, str] = {
    "computer": "computador",
    "smartphone": "celular",
    "tablet": "tablet",
    "speaker": "caixa de som",
    "castaudio": "caixa de som",
    "castvideo": "TV",
    "tv": "TV",
    "avr": "receiver",
    "stb": "TV box",
    "gameconsole": "console",
    "automobile": "carro",
}

_KIND_ALIASES: dict[str, tuple[str, ...]] = {
    "computer": ("pc", "computador", "notebook", "laptop", "desktop", "computer"),
    "smartphone": ("celular", "telefone", "smartphone", "phone", "iphone", "android"),
    "tablet": ("tablet", "aqui"),
    "speaker": ("caixa", "caixinha", "caixa de som", "som", "speaker", "alexa", "echo"),
    "castaudio": ("caixa", "caixinha", "caixa de som", "som", "chromecast", "cast"),
    "castvideo": ("tv", "televisao", "chromecast", "cast"),
    "tv": ("tv", "televisao"),
    "gameconsole": ("console", "playstation", "xbox"),
    "automobile": ("carro",),
}


def normalize(text: str) -> str:
    """Lowercase, accent-free, punctuation-free -- so "Televisão!" and
    "televisao" compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _has_word(haystack: str, needle: str) -> bool:
    return bool(needle) and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def match_devices(reference: str, devices: list[SpotifyDevice]) -> list[SpotifyDevice]:
    """Every device `reference` could mean. An exact mention of a device's
    own name wins outright (it's the most specific thing anyone can say);
    otherwise its kind ("pc", "celular"...) matches, which can be several
    devices of the same kind -- the caller decides whether that needs a
    follow-up question."""
    ref = normalize(reference)
    if not ref:
        return []
    by_name = [d for d in devices if _has_word(ref, normalize(d.name))]
    if by_name:
        return by_name
    return [d for d in devices if any(_has_word(ref, alias) for alias in d.aliases)]


def sort_for_choice(devices: list[SpotifyDevice]) -> list[SpotifyDevice]:
    """Active device first -- it's the natural default if someone answers
    "tanto faz" -- then by name so the spoken order is stable."""
    return sorted(devices, key=lambda d: (not d.is_active, d.name.casefold()))
