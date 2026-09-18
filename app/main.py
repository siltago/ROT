"""CLI entry point: text-based conversation with the Robot Brain.

This is the first validation harness for the whole architecture -- no
microphone, no camera, no real hardware. Swap SimulatorHardware for
ESP32Hardware later and nothing above hardware/ needs to change.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from actions.alexa import placeholder as alexa_actions
from actions.executor import ActionExecutor
from actions.music import player as music_actions
from actions.permissions import PermissionPolicy, auto_deny
from actions.registry import ActionRegistry
from actions.robot import movement as robot_actions
from actions.robot import device as device_actions
from actions.robot import learning as learning_actions
from actions.robot import play as play_actions
from actions.smart_home import lights as light_actions
from actions.smart_home import security as security_actions
from actions.smart_home import devices as smart_home_actions
from actions.utilities import local as utility_actions
from actions.utilities import weather as weather_actions
from app.config import settings
from brain.action_router import LlmActionRouter
from brain.agent import RobotAgent
from brain.context import ContextBuilder
from brain.decision_engine import DecisionEngine
from brain.planner import Planner
from brain.reflection import SelfReflector
from brain.response_engine import ResponseEngine
from emotions.engine import EmotionalEngine
from emotions.needs import NeedsEngine, NeedsStore
from emotions.state import EmotionalStateStore
from hardware.simulator import SimulatorHardware
from integrations.llm.base import LLMProvider
from integrations.llm.openai_provider import OpenAIProvider
from integrations.weather.open_meteo import OpenMeteoWeatherProvider
from integrations.music.service import MusicExperienceService
from integrations.music.spotify import SpotifyProvider
from integrations.smart_home.provider import SmartHomeProvider
from integrations.smart_home.service import SmartHomeService
from integrations.smart_home.home_assistant_provider import HomeAssistantProvider
from memory.identity import IdentityStore
from memory.long_term import LongTermMemory
from memory.people import PeopleDirectory
from memory.repository import InMemoryRepository, JsonFileRepository, Repository
from memory.short_term import ShortTermMemory
from personality.personality import Personality
from skills.interpreter import SkillInterpreter
from skills.registrar import SkillRegistrar
from skills.store import SkillLibrary
from brain.skill_learning import SkillTeacher

logger = logging.getLogger(__name__)

Speak = Callable[[str], Awaitable[None]]


async def confirm_in_terminal(spec, arguments) -> bool:
    args_str = ", ".join(f"{k}={v}" for k, v in arguments.items())
    answer = input(f"[Confirm] Run '{spec.name}({args_str})'? [y/N] ").strip().lower()
    return answer in ("y", "yes", "s", "sim")


async def _cli_speak(text: str) -> None:
    print(f"\nRobot > {text}\n")


def build_skills_repository() -> Repository:
    """Supabase-backed when configured (see sql/001_learned_skills.sql and
    .env.example); falls back to a non-persistent in-memory store so the
    rest of the app still runs before that's set up -- learned skills just
    won't survive a restart until it is."""
    if settings.supabase_url and settings.supabase_key:
        from supabase import create_client

        from memory.supabase_repository import SupabaseRepository

        client = create_client(settings.supabase_url, settings.supabase_key)
        return SupabaseRepository(client, table_name="learned_skills")
    logger.warning("SUPABASE_URL/SUPABASE_KEY not set -- learned skills won't persist across restarts")
    return InMemoryRepository()


def build_needs_repository() -> Repository:
    """Same shape as build_skills_repository() -- Supabase-backed when
    configured, falling back to a non-persistent in-memory store so the
    rest of the app still runs before that's set up (hunger just won't
    survive a restart until it is)."""
    if settings.supabase_url and settings.supabase_key:
        from supabase import create_client

        from memory.supabase_repository import SupabaseRepository

        client = create_client(settings.supabase_url, settings.supabase_key)
        return SupabaseRepository(client, table_name="robot_needs")
    logger.warning("SUPABASE_URL/SUPABASE_KEY not set -- robot needs won't persist across restarts")
    return InMemoryRepository()


def build_identity_repository() -> Repository:
    """Same shape as build_needs_repository() -- Supabase-backed when
    configured, falling back to a non-persistent in-memory store so the
    rest of the app still runs before that's set up (Bob's self-identity
    just resets to the hardcoded default on every restart until it is)."""
    if settings.supabase_url and settings.supabase_key:
        from supabase import create_client

        from memory.supabase_repository import SupabaseRepository

        client = create_client(settings.supabase_url, settings.supabase_key)
        return SupabaseRepository(client, table_name="robot_identity")
    logger.warning("SUPABASE_URL/SUPABASE_KEY not set -- robot identity won't persist across restarts")
    return InMemoryRepository()


def build_llm_provider() -> LLMProvider | None:
    if not settings.llm_enabled:
        return None
    if settings.llm_provider == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            timeout=settings.openai_timeout,
        )
    raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'")


def build_agent(
    *, hardware=None, interactive_confirmation: bool = True,
    smart_home_provider: SmartHomeProvider | None = None,
    speak_resolver: Callable[[], Speak] | None = None,
) -> RobotAgent:
    hardware = hardware or SimulatorHardware(verbose=settings.verbose_hardware)

    registry = ActionRegistry()
    # Built up front (not with the other stores below) because the music
    # actions read its remembered preferences (e.g. default playback device).
    identity_store = IdentityStore(build_identity_repository())
    security_actions.register(registry)
    music_service = MusicExperienceService(SpotifyProvider(
        settings.spotify_client_id, settings.spotify_client_secret,
        settings.spotify_refresh_token, timeout=settings.spotify_timeout,
    ))
    music_actions.register(registry, music_service, identity_store)
    alexa_actions.register(registry)
    robot_actions.register(registry, hardware)
    play_actions.register(registry)
    device_status = device_actions.DeviceStatusSource()
    device_actions.register(registry, device_status)
    weather_provider = OpenMeteoWeatherProvider(
        float(settings.robot_latitude) if settings.robot_latitude else None,
        float(settings.robot_longitude) if settings.robot_longitude else None,
        settings.robot_location_name,
        timeout=settings.weather_timeout,
        repository=JsonFileRepository(settings.location_file),
    )
    utility_actions.register(registry, settings.robot_timezone, weather_provider)
    weather_actions.register(registry, weather_provider, settings.robot_location_name)
    smart_home_service = SmartHomeService(smart_home_provider or HomeAssistantProvider(
        settings.home_assistant_url,
        settings.home_assistant_token,
        timeout_seconds=settings.home_assistant_timeout,
    ))
    smart_home_actions.register(registry, smart_home_service)

    permissions = PermissionPolicy(
        confirmation_provider=confirm_in_terminal if interactive_confirmation else auto_deny
    )
    executor = ActionExecutor(registry, permissions)
    planner = Planner(registry)
    decision_engine = DecisionEngine()

    people = PeopleDirectory(JsonFileRepository(settings.people_file))
    long_term = LongTermMemory(JsonFileRepository(settings.memories_file))
    short_term = ShortTermMemory(max_turns=settings.short_term_max_turns)
    context_builder = ContextBuilder(short_term, long_term)

    personality = Personality.load(settings.personality_file)
    emotional_engine = EmotionalEngine(EmotionalStateStore.load(settings.emotional_state_file))
    needs_engine = NeedsEngine(NeedsStore(build_needs_repository()))
    learning_actions.register(registry, identity_store, personality)

    llm_provider = build_llm_provider()
    response_engine = ResponseEngine(llm_provider=llm_provider)
    action_router = LlmActionRouter(llm_provider, registry)

    resolved_speak = speak_resolver or (lambda: _cli_speak)
    skill_library = SkillLibrary(build_skills_repository())
    skill_interpreter = SkillInterpreter(registry=registry, executor=executor)
    skill_registrar = SkillRegistrar(registry, skill_interpreter, skill_library)
    # Every previously learned skill becomes a real ActionSpec again, right
    # here, before the agent ever processes a turn -- from that point on
    # it's indistinguishable from a hand-coded action (same registry, same
    # ActionExecutor path), and the LLM is never asked to re-teach it.
    skill_registrar.load_all(speak_resolver=resolved_speak)
    skill_teacher = SkillTeacher(llm_provider=llm_provider, registrar=skill_registrar, speak_resolver=resolved_speak)

    agent = RobotAgent(
        decision_engine=decision_engine,
        planner=planner,
        executor=executor,
        context_builder=context_builder,
        response_engine=response_engine,
        personality=personality,
        emotional_engine=emotional_engine,
        needs_engine=needs_engine,
        identity_store=identity_store,
        reflector=SelfReflector(llm_provider, identity_store),
        people=people,
        long_term=long_term,
        short_term=short_term,
        action_router=action_router,
        skill_teacher=skill_teacher,
    )
    agent.smart_home_service = smart_home_service
    agent.device_status = device_status
    agent.music_service = music_service
    agent.skill_library = skill_library
    return agent


async def run_cli() -> None:
    agent = build_agent()
    print("Robot Brain -- CLI mode. Digite 'sair' para encerrar.\n")
    while True:
        try:
            text = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in ("sair", "exit", "quit"):
            break

        print()
        result = await agent.process_turn(text)
        print(f"\nRobot > {result.reply}\n")


def main() -> None:
    asyncio.run(run_cli())


if __name__ == "__main__":
    main()
