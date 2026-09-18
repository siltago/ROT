"""Bob's persistent self-identity -- who he is, what he's for day to day,
and a growing list of things he's learned about himself over time.

This is distinct from everything else memory/personality/ already track:
- memory/long_term.py stores facts *about people* Bob talks to.
- personality/personality.py stores numeric trait sliders (how much humor,
  sarcasm, etc.) -- not a readable description of his role.
- personality/voice.py's VoiceContract is a fixed, hand-written style rule
  ("how Bob talks") -- it never changes and isn't persisted as data.

IdentityState is the literal, readable self-concept: a home robot, what he
actually focuses on day to day, and self_notes -- an append-only, capped
list that accumulates over time instead of being reset on every deploy.
Injected into every system prompt (see brain/response_engine.py) so Bob
always "remembers" what he is, even across restarts.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from memory.repository import Repository

logger = logging.getLogger(__name__)

DEFAULT_WHO = (
    "Sou o Bob, um robô de uso doméstico -- moro dentro de casa e sou uma "
    "presença do dia a dia de quem mora aqui, não um assistente de nuvem genérico."
)

DEFAULT_FOCUS_AREAS: tuple[str, ...] = (
    "reconhecer e cuidar de tarefas simples do dia a dia da casa",
    "tocar e controlar música (Spotify)",
    "responder sobre o clima e a previsão do tempo",
    "controlar luzes, segurança e outros dispositivos da casa (smart home)",
    "lembrar coisas importantes sobre quem mora aqui e ser companhia de verdade",
)

# Append-only self_notes cap -- unbounded growth would eventually bloat
# every single system prompt; a few dozen recent self-observations is
# plenty to feel like accumulated memory without doing that.
_MAX_SELF_NOTES = 30


# Knowledge is the "trainable" part of his brain: topic -> guidance the LLM
# reads every turn. Seeded from personality/seed_knowledge.py, then grown by
# voice teaching and by his own self-reflection. Capped so the prompt can't
# grow forever; the newest entries win.
_MAX_KNOWLEDGE = 40
# How many knowledge entries actually go into each system prompt.
_PROMPT_KNOWLEDGE = 24
_MAX_KNOWLEDGE_TEXT = 300


class KnowledgeEntry(BaseModel):
    topic: str
    text: str


class IdentityState(BaseModel):
    who: str = DEFAULT_WHO
    focus_areas: list[str] = Field(default_factory=lambda: list(DEFAULT_FOCUS_AREAS))
    # Things Bob has "learned about himself" over time (e.g. via
    # IdentityStore.add_self_note) -- newest last, distinct from
    # memory/long_term.py's per-person facts. Kept short and factual on
    # purpose; this isn't a diary, it's context for the next system prompt.
    self_notes: list[str] = Field(default_factory=list)
    knowledge: list[KnowledgeEntry] = Field(default_factory=list)
    # Which SEED_VERSION of personality/seed_knowledge.py was last applied,
    # so editing the seed re-injects it once instead of on every boot.
    seed_version: int = 0
    # Small durable preferences Bob has learned about how this home likes
    # things done (e.g. {"music.device": "DESKTOP-ABC"}), as opposed to
    # `knowledge`, which is guidance the LLM reads. Read by actions.
    preferences: dict[str, str] = Field(default_factory=dict)


class IdentityStore:
    """Persists a single IdentityState document via any Repository
    (Supabase in production, see app/main.py's build_identity_repository)
    -- same "singleton document" shape NeedsStore/SkillLibrary use, since
    there's only ever one robot's identity to track."""

    _DOC_ID = "singleton"

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        try:
            record = self.repository.get(self._DOC_ID)
        except Exception:
            # Most likely sql/003_robot_identity.sql hasn't been run
            # against this Supabase project yet -- degrade to the default
            # identity rather than taking the whole agent down at boot
            # over one missing table.
            logger.warning(
                "Could not load robot_identity from the repository (has "
                "sql/003_robot_identity.sql been run yet?) -- starting "
                "from the default IdentityState instead."
            )
            record = None
        self.state = IdentityState(**record) if record else IdentityState()
        self.apply_seed()

    def apply_seed(self) -> bool:
        """Injects personality/seed_knowledge.py once per SEED_VERSION.
        Topics already present (e.g. taught or refined later) are left
        alone -- the seed never overwrites something learned. Returns
        True if anything changed."""
        from personality.seed_knowledge import SEED_KNOWLEDGE, SEED_VERSION

        if self.state.seed_version >= SEED_VERSION:
            return False
        existing = {entry.topic.casefold() for entry in self.state.knowledge}
        for topic, text in SEED_KNOWLEDGE:
            if topic.casefold() not in existing:
                self.state.knowledge.append(KnowledgeEntry(topic=topic, text=text))
        self.state.seed_version = SEED_VERSION
        self.save()
        return True

    def save(self) -> None:
        data = self.state.model_dump()
        data["id"] = self._DOC_ID
        try:
            if self.repository.get(self._DOC_ID) is None:
                self.repository.add(data)
            else:
                self.repository.update(self._DOC_ID, data)
        except Exception:
            logger.warning("Could not persist robot_identity (table missing?)")

    def add_self_note(self, note: str) -> None:
        """Appends a new self-observation, trimming the oldest once the
        cap is hit -- this is the "building memory over time" part:
        each call makes the very next system prompt (and every one after,
        until it ages out) reflect it."""
        clean = note.strip()
        if not clean:
            return
        self.state.self_notes.append(clean)
        if len(self.state.self_notes) > _MAX_SELF_NOTES:
            self.state.self_notes = self.state.self_notes[-_MAX_SELF_NOTES:]

    def add_knowledge(self, topic: str, text: str) -> None:
        """Teaches (or refines) one piece of guidance. Same topic replaces
        the old text and moves it to the newest position, so re-teaching
        something is how you correct it."""
        clean_topic = topic.strip()[:60]
        clean_text = text.strip()[:_MAX_KNOWLEDGE_TEXT]
        if not clean_topic or not clean_text:
            return
        key = clean_topic.casefold()
        self.state.knowledge = [
            entry for entry in self.state.knowledge if entry.topic.casefold() != key
        ]
        self.state.knowledge.append(KnowledgeEntry(topic=clean_topic, text=clean_text))
        if len(self.state.knowledge) > _MAX_KNOWLEDGE:
            self.state.knowledge = self.state.knowledge[-_MAX_KNOWLEDGE:]

    def as_prompt_fragment(self) -> str:
        """The block injected into every system prompt -- who Bob is, what
        he actually focuses on, and whatever he's accumulated about
        himself so far."""
        lines = [f"QUEM VOCÊ É\n{self.state.who}"]
        if self.state.focus_areas:
            lines.append("Foco do dia a dia: " + "; ".join(self.state.focus_areas) + ".")
        if self.state.knowledge:
            recent = self.state.knowledge[-_PROMPT_KNOWLEDGE:]
            lines.append(
                "O que você sabe e aprendeu (aplique com naturalidade, com suas "
                "próprias palavras):\n"
                + "\n".join(f"- {entry.topic}: {entry.text}" for entry in recent)
            )
        if self.state.self_notes:
            lines.append(
                "O que você já aprendeu sobre si mesmo com o tempo: "
                + "; ".join(self.state.self_notes) + "."
            )
        return "\n".join(lines)
