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
    voices_dir: Path = DATA_DIR / "voices"

    people_file: Path = DATA_DIR / "people" / "people.json"
    memories_file: Path = DATA_DIR / "memories" / "memories.json"
    personality_file: Path = DATA_DIR / "state" / "personality.json"
    emotional_state_file: Path = DATA_DIR / "state" / "emotion.json"
    location_file: Path = DATA_DIR / "state" / "location.json"

    short_term_max_turns: int = int(os.getenv("SHORT_TERM_MAX_TURNS", "20"))
    verbose_hardware: bool = os.getenv("VERBOSE_HARDWARE", "true").lower() != "false"

    llm_enabled: bool = os.getenv("LLM_ENABLED", "true").lower() != "false"
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini-2026-03-17")
    openai_timeout: float = float(os.getenv("OPENAI_TIMEOUT", "30"))
    stt_provider: str = os.getenv("STT_PROVIDER", "openai_realtime")
    stt_model: str = os.getenv("OPENAI_STT_MODEL", "gpt-live-transcribe")
    stt_timeout: float = float(os.getenv("STT_TIMEOUT", "12"))

    api_host: str = os.getenv("ROBOT_API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("ROBOT_API_PORT", "8000"))
    debug_events_enabled: bool = os.getenv("DEBUG_EVENTS_ENABLED", "false").lower() == "true"
    cognition_tick_seconds: float = float(os.getenv("COGNITION_TICK_SECONDS", "30"))

    robot_location_name: str = os.getenv("ROBOT_LOCATION_NAME", "")
    robot_latitude: str = os.getenv("ROBOT_LATITUDE", "")
    robot_longitude: str = os.getenv("ROBOT_LONGITUDE", "")
    robot_timezone: str = os.getenv("ROBOT_TIMEZONE", "America/Sao_Paulo")
    weather_timeout: float = float(os.getenv("WEATHER_TIMEOUT", "6"))

    spotify_client_id: str = os.getenv("SPOTIFY_CLIENT_ID", "")
    spotify_client_secret: str = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    spotify_refresh_token: str = os.getenv("SPOTIFY_REFRESH_TOKEN", "")
    spotify_timeout: float = float(os.getenv("SPOTIFY_TIMEOUT", "8"))
    music_poll_seconds: float = float(os.getenv("MUSIC_POLL_SECONDS", "1"))

    home_assistant_url: str = os.getenv("HOME_ASSISTANT_URL", "http://homeassistant.local:8123")
    home_assistant_token: str = os.getenv("HOME_ASSISTANT_TOKEN", "")
    home_assistant_timeout: float = float(os.getenv("HOME_ASSISTANT_TIMEOUT", "4"))

    # Persists learned skills (see skills/) -- the only thing backed by a
    # real database rather than a local JSON file, since it's meant to grow
    # and be queried as the robot "learns" more over time. See
    # sql/001_learned_skills.sql for the table this expects.
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")

    piper_enabled: bool = os.getenv("PIPER_ENABLED", "false").lower() == "true"
    piper_voice_path: Path = Path(os.getenv("PIPER_VOICE_PATH", str(DATA_DIR / "voices" / "pt_BR-faber-medium.onnx")))
    # "Robot voice" tuning -- all adjustable without touching code. Prosody
    # (how Piper itself speaks) vs. the post-processing effect (ring
    # modulation + bitcrush) are separate knobs; turn either down/off
    # independently while dialing in a taste.
    piper_noise_scale: float = float(os.getenv("PIPER_NOISE_SCALE", "0.5"))
    piper_noise_w_scale: float = float(os.getenv("PIPER_NOISE_W_SCALE", "0.5"))
    piper_length_scale: float = float(os.getenv("PIPER_LENGTH_SCALE", "1.0"))
    # Raises/lowers the whole voice (formants included -- large values start
    # sounding like a sped-up/slowed-down version of the same voice rather
    # than a genuinely different one). 0 = untouched.
    piper_pitch_shift_semitones: float = float(os.getenv("PIPER_PITCH_SHIFT_SEMITONES", "0"))
    piper_ring_mod_hz: float = float(os.getenv("PIPER_RING_MOD_HZ", "45"))
    # Overt robotic buzz layered on top of the voice; off by default (0) --
    # the default target is a normal-sounding voice with its own character,
    # not a Dalek/GLaDOS-style distortion. Raise for that effect instead.
    piper_ring_mod_wet: float = float(os.getenv("PIPER_RING_MOD_WET", "0"))
    # Number of amplitude quantization steps; 0 disables the bitcrush entirely.
    piper_bitcrush_levels: int = int(os.getenv("PIPER_BITCRUSH_LEVELS", "0"))


settings = Settings()
