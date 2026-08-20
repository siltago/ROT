"""Central configuration: paths and env-driven settings.

No secrets live in code -- values come from environment variables (loaded
from .env in development). Nothing here should import brain/personality/etc;
this module is pure config so it can be imported first, before anything
else, without circular-import risk.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = DATA_DIR
    people_dir: Path = DATA_DIR / "people"
    memories_dir: Path = DATA_DIR / "memories"
    state_dir: Path = DATA_DIR / "state"

    people_file: Path = DATA_DIR / "people" / "people.json"
    memories_file: Path = DATA_DIR / "memories" / "memories.json"
    personality_file: Path = DATA_DIR / "state" / "personality.json"
    emotional_state_file: Path = DATA_DIR / "state" / "emotion.json"

    short_term_max_turns: int = int(os.getenv("SHORT_TERM_MAX_TURNS", "20"))
    verbose_hardware: bool = os.getenv("VERBOSE_HARDWARE", "true").lower() != "false"

    llm_enabled: bool = os.getenv("LLM_ENABLED", "true").lower() != "false"
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


settings = Settings()
