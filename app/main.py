"""CLI entry point: text-based conversation with the Robot Brain.

This is the first validation harness for the whole architecture -- no
microphone, no camera, no real hardware. Swap SimulatorHardware for
ESP32Hardware later and nothing above hardware/ needs to change.
"""
from __future__ import annotations

import asyncio

from actions.alexa import placeholder as alexa_actions
from actions.executor import ActionExecutor
from actions.music import player as music_actions
from actions.permissions import PermissionPolicy, auto_deny
from actions.registry import ActionRegistry
from actions.robot import movement as robot_actions
from actions.smart_home import lights as light_actions
from actions.smart_home import security as security_actions
from app.config import settings
from brain.agent import RobotAgent
from brain.context import ContextBuilder
from brain.decision_engine import DecisionEngine
from brain.planner import Planner
from brain.response_engine import ResponseEngine
from emotions.engine import EmotionalEngine
from emotions.state import EmotionalStateStore
from hardware.simulator import SimulatorHardware
from integrations.llm.base import LLMProvider
from integrations.llm.ollama_provider import OllamaProvider
from memory.long_term import LongTermMemory
from memory.people import PeopleDirectory
from memory.repository import JsonFileRepository
from memory.short_term import ShortTermMemory
from personality.personality import Personality


async def confirm_in_terminal(spec, arguments) -> bool:
    args_str = ", ".join(f"{k}={v}" for k, v in arguments.items())
    answer = input(f"[Confirm] Run '{spec.name}({args_str})'? [y/N] ").strip().lower()
    return answer in ("y", "yes", "s", "sim")


def build_llm_provider() -> LLMProvider | None:
    if not settings.llm_enabled:
        return None
    if settings.llm_provider == "ollama":
        return OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_base_url)
    raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'")


def build_agent(*, hardware=None, interactive_confirmation: bool = True) -> RobotAgent:
    hardware = hardware or SimulatorHardware(verbose=settings.verbose_hardware)

    registry = ActionRegistry()
    light_actions.register(registry)
    security_actions.register(registry)
    music_actions.register(registry)
    alexa_actions.register(registry)
    robot_actions.register(registry, hardware)

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

    response_engine = ResponseEngine(llm_provider=build_llm_provider())

    return RobotAgent(
        decision_engine=decision_engine,
        planner=planner,
        executor=executor,
        context_builder=context_builder,
        response_engine=response_engine,
        personality=personality,
        emotional_engine=emotional_engine,
        people=people,
        long_term=long_term,
        short_term=short_term,
    )


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
