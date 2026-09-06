"""Formats the registered-actions catalog used in LLM prompts -- shared by
`brain/action_router.py` (deciding which action to run) and
`skills/teaching_prompt.py` (deciding what a new skill's `call_action`
steps are allowed to reference), so both always see the exact same list.
"""
from __future__ import annotations

from actions.registry import ActionSpec


def format_catalog(specs: list[ActionSpec]) -> str:
    return "\n".join(
        f"- {spec.name}: {spec.description} (parâmetros: {', '.join(spec.parameters) or 'nenhum'})"
        for spec in specs
    )
