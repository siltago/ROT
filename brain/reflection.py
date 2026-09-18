"""Self-reflection: how Bob gets better on his own between trainings.

Every N conversation turns he re-reads the recent dialogue and, if
something in how *he* handled it is worth remembering (a tone that landed
badly, a preference the person showed, a phrasing that worked), writes it
down as one short self-note in his persistent identity -- which then rides
along in every later system prompt (see memory/identity.py).

Deliberately conservative, since this is the one place he writes to his own
brain unsupervised:
- one short note at most per reflection, and "NADA" (nothing) is the
  expected answer most of the time;
- it can only add a self_note (capped list, oldest drop off) -- it can't
  touch personality sliders, knowledge, or run actions;
- it runs in the background and never blocks or breaks a turn.
"""
from __future__ import annotations

import asyncio
import logging

from integrations.llm.base import LLMProvider
from memory.identity import IdentityStore

logger = logging.getLogger(__name__)

_MAX_NOTE_CHARS = 180

_SYSTEM = (
    "Você é a parte reflexiva do Bob, um robô doméstico. Leia a conversa "
    "recente e decida se há UMA lição curta sobre como o Bob deve falar ou "
    "agir com essas pessoas daqui pra frente (um tom que funcionou ou "
    "falhou, uma preferência que a pessoa mostrou, um erro dele). Escreva "
    "a lição em primeira pessoa, uma frase, no máximo 150 caracteres, sem "
    "aspas. Se não houver nada realmente útil, responda exatamente: NADA"
)


class SelfReflector:
    def __init__(
        self,
        llm_provider: LLMProvider | None,
        identity: IdentityStore,
        *,
        every_n_turns: int = 12,
    ) -> None:
        self.llm_provider = llm_provider
        self.identity = identity
        self.every_n_turns = every_n_turns
        self._turns_since = 0
        self._running = False

    def note_turn(self, recent_dialogue: str) -> None:
        """Call once per finished turn. Every Nth call kicks off a
        background reflection over `recent_dialogue`; the rest are free."""
        if self.llm_provider is None or self.every_n_turns <= 0:
            return
        self._turns_since += 1
        if self._turns_since < self.every_n_turns or self._running:
            return
        self._turns_since = 0
        try:
            asyncio.get_running_loop().create_task(self.reflect(recent_dialogue))
        except RuntimeError:
            pass  # no running loop (sync caller) -- skip rather than fail the turn

    async def reflect(self, recent_dialogue: str) -> str | None:
        """Runs one reflection. Returns the note it stored, or None."""
        if self.llm_provider is None or not recent_dialogue.strip():
            return None
        self._running = True
        try:
            answer = await self.llm_provider.generate(
                system=_SYSTEM,
                user="Conversa recente:\n" + recent_dialogue,
            )
        except Exception as exc:  # noqa: BLE001 -- best-effort, never break the robot
            logger.warning("Self-reflection failed (%s)", exc)
            return None
        finally:
            self._running = False
        note = answer.strip().strip('"').strip()
        if not note or note.upper().startswith("NADA"):
            return None
        note = note[:_MAX_NOTE_CHARS]
        self.identity.add_self_note(note)
        self.identity.save()
        logger.info("Self-reflection stored a note: %s", note)
        return note
