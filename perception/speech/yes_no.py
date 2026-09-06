"""Deliberately local/deterministic, not LLM-routed -- a yes/no answer to
something the robot itself just asked is a narrow, low-stakes
classification that doesn't need real intelligence, and keeping it
free/instant matters here exactly like the wake word itself does.

Shared by every "robot asked a yes/no question, waiting for the mic to
pick up the answer" flow -- originally written for the Spotify "quer que
eu abra o player aqui?" offer (api/server.py), reused as-is for approving
a newly learned skill (brain/skill_learning.py).
"""
from __future__ import annotations

_AFFIRMATIVE_WORDS = {
    "sim", "pode", "claro", "quero", "manda", "bora", "isso", "abre", "abrir",
    "positivo", "aham", "uhum", "beleza", "show", "vai", "sí",
}
_NEGATIVE_WORDS = {
    "não", "nao", "deixa", "depois", "agora não", "agora nao", "negativo",
    "para", "pare", "nunca",
}


def classify_yes_no(text: str) -> bool | None:
    normalized = text.lower().strip().rstrip(".!?")
    words = set(normalized.split())
    if words & _NEGATIVE_WORDS:
        return False
    if words & _AFFIRMATIVE_WORDS:
        return True
    return None
