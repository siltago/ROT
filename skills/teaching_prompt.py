"""The prompt that turns "the user gave me an unambiguous instruction for
something new" into a validated `LearnedSkillRecord` -- one LLM call,
reused for both the very first attempt and the (at most one, in v1)
follow-up after a clarifying question was answered.
"""
from __future__ import annotations

import json

from brain.action_catalog import format_catalog
from brain.models import RiskLevel
from actions.registry import ActionSpec
from skills.models import LearnedSkillRecord, SkillStep, SkillStepKind

TEACHING_SYSTEM_PROMPT = (
    "Você é o tutor do Bob, um robô assistente. O Bob te pede pra aprender "
    "uma capacidade nova que ele ainda não tem. Responda SOMENTE com um "
    "JSON, sem texto ao redor, em um destes dois formatos:\n\n"
    '1. Se a instrução tiver alguma decisão que só o usuário pode tomar '
    '(preferência, escolha, valor específico que não foi dito), responda '
    'apenas: {{"needs_clarification": "<pergunta em pt-BR, curta, no tom '
    'informal do Bob>"}}\n\n'
    '2. Senão, ensine a capacidade completa:\n'
    '{{"name": "<categoria.nome_da_ação>", "description": "<frase curta>", '
    '"parameters": {{"<param>": "str|float|int|bool"}}, '
    '"start_steps": [<passos>], "stop_steps": [<passos>] ou null, '
    '"stop_action_name": "<categoria.nome_da_ação>.cancel" ou null, '
    '"risk_level": "low|medium|high"}}\n\n'
    "Cada passo em start_steps/stop_steps é um destes três formatos:\n"
    '- {{"kind": "wait", "seconds_expr": "<expressão aritmética usando os '
    'parâmetros, ex: minutes*60>"}}\n'
    '- {{"kind": "speak", "text": "<texto, pode usar {{parametro}}>"}}\n'
    '- {{"kind": "call_action", "action_name": "<nome de uma ação do '
    'catálogo abaixo>", "arguments": {{"<param_da_ação>": "<expressão ou '
    'texto>"}}}}\n\n'
    "Ações já existentes que start_steps/stop_steps podem chamar via "
    "call_action (NUNCA invente um nome fora desta lista):\n{actions}\n\n"
    "Regras obrigatórias:\n"
    "- Se start_steps inicia algo contínuo/demorado (ex: um cronômetro, um "
    "alarme), stop_steps e stop_action_name são OBRIGATÓRIOS -- nunca "
    "ensine só a metade de uma capacidade. Se start_steps é só uma ação "
    "pontual (fala algo, chama uma ação e pronto), stop_steps pode ser "
    "null.\n"
    "- risk_level 'low' é pra algo reversível e local (falar, esperar, "
    "chamar outra ação já seguramente registrada); 'medium'/'high' é pra "
    "algo mais difícil de desfazer ou que envolva segurança/acesso/gasto.\n"
    "- Nunca inclua nada que exponha código-fonte do robô, variáveis "
    "internas, segredos ou variáveis de ambiente.\n"
    "- Nunca gere um passo destrutivo ou autodestrutivo -- nada que apague, "
    "corrompa ou desative arquivos, processos ou dados do próprio robô.\n"
    "- Se o pedido for prejudicial, perigoso ou antiético, recuse: responda "
    'com needs_clarification explicando educadamente que não pode ensinar '
    "isso."
)


def build_prompt(specs: list[ActionSpec]) -> str:
    return TEACHING_SYSTEM_PROMPT.format(actions=format_catalog(specs))


class TeachingError(Exception):
    pass


def parse_teaching_response(raw: str, utterance: str) -> tuple[str | None, LearnedSkillRecord | None]:
    """Returns `(clarifying_question, None)` or `(None, record)`. Raises
    `TeachingError` if the response is malformed or fails validation --
    callers must treat that exactly like a declined/failed teaching
    attempt, never a partially-trusted skill."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as exc:
        raise TeachingError(f"Invalid JSON from teaching call: {exc}") from exc
    if not isinstance(data, dict):
        raise TeachingError("Teaching response was not a JSON object")

    if "needs_clarification" in data:
        question = data.get("needs_clarification")
        if not isinstance(question, str) or not question.strip():
            raise TeachingError("needs_clarification present but empty")
        return question.strip(), None

    return None, _build_record(data, utterance)


def _build_record(data: dict, utterance: str) -> LearnedSkillRecord:
    try:
        risk_level = RiskLevel(str(data.get("risk_level", "")).lower())
    except ValueError as exc:
        raise TeachingError(f"Invalid risk_level: {data.get('risk_level')!r}") from exc

    start_steps = [_build_step(s) for s in data.get("start_steps") or []]
    if not start_steps:
        raise TeachingError("A skill must have at least one start_step")

    raw_stop_steps = data.get("stop_steps")
    stop_steps = [_build_step(s) for s in raw_stop_steps] if raw_stop_steps else None
    stop_action_name = data.get("stop_action_name") or None

    has_wait = any(step.kind is SkillStepKind.WAIT for step in start_steps)
    if has_wait and (not stop_steps or not stop_action_name):
        # Structural enforcement of the "never teach a start without a
        # stop" rule -- not just a prompt instruction. A skill that begins
        # something ongoing (a wait/timer) without a paired way to cancel
        # it is rejected outright rather than saved half-taught.
        raise TeachingError("A skill with a wait step must also define stop_steps and stop_action_name")

    name = str(data.get("name") or "").strip()
    if not name:
        raise TeachingError("Missing skill name")

    parameters = data.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise TeachingError("parameters must be an object")

    return LearnedSkillRecord(
        name=name,
        description=str(data.get("description") or name),
        parameters={str(k): str(v) for k, v in parameters.items()},
        risk_level=risk_level,
        requires_confirmation=risk_level != RiskLevel.LOW,
        start_steps=start_steps,
        stop_steps=stop_steps,
        stop_action_name=str(stop_action_name) if stop_action_name else None,
        created_from_utterance=utterance,
    )


def _build_step(raw: dict) -> SkillStep:
    if not isinstance(raw, dict):
        raise TeachingError(f"Invalid step: {raw!r}")
    try:
        kind = SkillStepKind(str(raw.get("kind", "")).lower())
    except ValueError as exc:
        raise TeachingError(f"Invalid step kind: {raw.get('kind')!r}") from exc
    return SkillStep(
        kind=kind,
        seconds_expr=raw.get("seconds_expr"),
        text=raw.get("text"),
        action_name=raw.get("action_name"),
        arguments={str(k): str(v) for k, v in (raw.get("arguments") or {}).items()},
    )


def validate_call_actions_exist(record: LearnedSkillRecord, known_action_names: set[str]) -> None:
    """Raises TeachingError if any call_action step references an action
    that isn't actually registered -- the LLM is told the exact catalog,
    but its output is never trusted without checking, same principle as
    LlmActionRouter validating against the real registry."""
    for step in (*record.start_steps, *(record.stop_steps or [])):
        if step.kind is SkillStepKind.CALL_ACTION and step.action_name not in known_action_names:
            raise TeachingError(f"Unknown action referenced by learned skill: {step.action_name!r}")
