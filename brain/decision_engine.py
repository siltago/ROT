"""Deterministic, low-latency intent classification and action proposals."""
from __future__ import annotations

import re
from collections.abc import Callable

from brain.models import ActionRequest, Decision, IntentType

Extractor = Callable[[re.Match[str]], dict]

_RULES: list[tuple[re.Pattern[str], str, Extractor]] = [
    (
        re.compile(r"\b(?:eu\s+)?(?:moro|estou|fico)\s+em\s+(?P<city>[\wçãõáéíóúàâêô\s,-]+)|\bminha cidade (?:é|e)\s+(?P<city2>[\wçãõáéíóúàâêô\s,-]+)", re.I),
        "weather.set_location",
        lambda m: {"city": (m.group("city") or m.group("city2") or "").strip().rstrip(".?!")},
    ),
    (re.compile(r"\b(?:que horas (?:são|sao)|qual (?:é|e) a hora|me diz as horas)\b", re.I), "time.get", lambda m: {}),
    (re.compile(r"\b(?:que dia (?:é|e) hoje|qual (?:é|e) a data|data de hoje)\b", re.I), "date.get", lambda m: {}),
    (re.compile(r"\b(?:(?:temperatura|tempo|previs[aã]o)(?:\s+do\s+tempo)?.*amanh[aã]|amanh[aã].*(?:temperatura|tempo|previs[aã]o))\b", re.I), "weather.forecast", lambda m: {"day_offset": 1}),
    (re.compile(r"\b(?:como (?:está|esta) o tempo|previs[aã]o do tempo|vai chover|qual (?:(?:é|e) )?a temperatura|temperatura (?:agora|hoje)|quantos graus)\b", re.I), "weather.get", lambda m: {}),
    (re.compile(r"\b(?:como está o sistema|status do sistema|você está funcionando)\b", re.I), "system.status", lambda m: {}),
    (
        re.compile(r"\b(?:liga(?:r)?|acende(?:r)?)\s+(?:a\s+)?(?:luz|lâmpada|lampada)\s*(?:d[aoe]\s*)?(?P<room>[\wçãõáéíóú ]*)", re.I),
        "light.turn_on", lambda m: {"room": (m.group("room") or "").strip().rstrip(".?!") or "sala"},
    ),
    (
        re.compile(r"\b(?:desliga(?:r)?|apaga(?:r)?)\s+(?:a\s+)?(?:luz|lâmpada|lampada)\s*(?:d[aoe]\s*)?(?P<room>[\wçãõáéíóú ]*)", re.I),
        "light.turn_off", lambda m: {"room": (m.group("room") or "").strip().rstrip(".?!") or "sala"},
    ),
    (
        re.compile(r"\b(?:lig(?:a|ar|ue)|ativ(?:a|ar|e))\s+(?:a|o)?\s*(?P<target>(?:tv|televisão|televisao|ventilador|tomada|interruptor|aspirador)(?:\s+d[aoe]\s+[\wçãõáéíóú ]+|\s+aqui)?)", re.I),
        "smart_home.turn_on", lambda m: {"target": m.group("target").strip().rstrip(".?!")},
    ),
    (
        re.compile(r"\b(?:deslig(?:a|ar|ue)|desativ(?:a|ar|e))\s+(?:a|o)?\s*(?P<target>(?:tv|televisão|televisao|ventilador|tomada|interruptor|aspirador)(?:\s+d[aoe]\s+[\wçãõáéíóú ]+|\s+aqui)?)", re.I),
        "smart_home.turn_off", lambda m: {"target": m.group("target").strip().rstrip(".?!")},
    ),
    (
        re.compile(r"\b(?:abre|abra|abrir)\s+(?:a\s+)?(?P<target>(?:cortina|persiana)(?:\s+d[aoe]\s+[\wçãõáéíóú ]+|\s+aqui)?)", re.I),
        "smart_home.turn_on", lambda m: {"target": m.group("target").strip().rstrip(".?!")},
    ),
    (
        re.compile(r"\b(?:fecha|feche|fechar)\s+(?:a\s+)?(?P<target>(?:cortina|persiana)(?:\s+d[aoe]\s+[\wçãõáéíóú ]+|\s+aqui)?)", re.I),
        "smart_home.turn_off", lambda m: {"target": m.group("target").strip().rstrip(".?!")},
    ),
    (
        re.compile(r"(?:deixa|coloca)\s+(?P<target>(?:a\s+)?(?:luz|lâmpada|lampada|abajur|led)(?:\s+d[aoe]\s+[\wçãõáéíóú ]+|\s+aqui)?)\s+(?:em|a)\s+(?P<value>\d{1,3})%", re.I),
        "smart_home.set_brightness", lambda m: {"target": m.group("target").strip(), "value": min(100, int(m.group("value")))},
    ),
    (
        re.compile(r"ar[\s-]?condicionado.*?(?P<temp>\d+)\s*graus?|coloca(?:r)? o ar em (?P<temp2>\d+)", re.I),
        "climate.set_temperature", lambda m: {"temperature": float(m.group("temp") or m.group("temp2"))},
    ),
    (
        re.compile(
            r"(?:toca(?:r)?|toque|coloca(?:r)?)\s+(?:uma\s+|a\s+)?música\s*"
            # Bails out of this fast/free path (letting it fall through to
            # the LLM router instead) for two shapes it can't handle: the
            # robot choosing for itself ("do seu gosto") -- which needs
            # actual judgment, not a literal string handed to Spotify's
            # search -- and a multi-song request ("X e depois Y") --
            # which needs more than one action. Without this, both used to
            # get their trailing words captured verbatim as the search
            # query and handed straight to Spotify, which is exactly why
            # "toca uma música do seu gosto" failed instead of the robot
            # ever getting a chance to actually decide something.
            r"(?!.*\bdo\s+seu\s+gosto\b)(?!.*\bque\s+(?:vc|voc[eê])\s+(?:gosta|goste|quiser|escolher)\b)"
            r"(?!.*\be\s+depois\b)(?!.*\be\s+em\s+seguida\b)(?!.*\bseguido\s+de\b)"
            r"(?P<query>.*)|play\s+(?P<query2>.*)", re.I),
        "music.play", lambda m: {"query": (m.group("query") or m.group("query2") or "").strip()},
    ),
    (re.compile(r"para(?:r)? (?:a\s+)?m[uú]sica|stop music", re.I), "music.stop", lambda m: {}),
    (
        re.compile(r"\b(?:volt[ae] a\s*m[uú]sica|volt[ae] com a\s*m[uú]sica|despausa(?:r)?(?:\s+a\s*m[uú]sica)?|"
                   r"continua(?:r)?(?:\s+a\s*m[uú]sica)?|retoma(?:r)?(?:\s+a\s*m[uú]sica)?)\b", re.I),
        "music.resume", lambda m: {},
    ),
    (
        re.compile(r"\b(?:sa(?:i|ir)|fech(?:a|ar|e)|esconde(?:r)?|tira(?:r)?)\b.*\bplayer\b|"
                   r"\b(?:fech(?:a|ar|e)|esconde(?:r)?|tira(?:r)?)\b.*\b(?:tela|cena)\s+(?:d[ae]\s+)?m[uú]sica\b", re.I),
        "music.hide_player", lambda m: {},
    ),
    (re.compile(r"destrava(?:r)?\s+(?:a\s+)?porta\s*(?:d[aoe]\s*)?(?P<door>[\wçãõáéíóú ]*)|unlock.*door", re.I), "door.unlock", lambda m: {"door": (m.groupdict().get("door") or "").strip() or "principal"}),
]

_QUESTION_MARKERS = ("?", "quem ", "o que ", "qual ", "quando ", "onde ", "por que ", "why", "what", "who", "when", "where")
_PREFERENCE_MARKERS = ("gosto", "prefiro", "não gosto", "odeio", "adoro", "costumo", "like", "prefer", "hate", "love")


class DecisionEngine:
    def classify_follow_up(self, text: str, previous_robot_text: str | None) -> Decision:
        cleaned = text.strip()
        previous = (previous_robot_text or "").casefold()
        if "em qual cidade eu estou" in previous and 2 <= len(cleaned) <= 80:
            city = re.sub(
                r"^(?:em|na cidade de|cidade de)\s+",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip().rstrip(".?!")
            return Decision(
                type=IntentType.ACTION,
                confidence=0.98,
                actions=[ActionRequest(name="weather.set_location", arguments={"city": city})],
                raw_text=cleaned,
            )
        return self.classify(cleaned)

    def classify(self, text: str) -> Decision:
        text = text.strip()
        if not text:
            return Decision(type=IntentType.AMBIGUOUS, confidence=0.0, raw_text=text)
        actions: list[ActionRequest] = []
        for pattern, action_name, extractor in _RULES:
            if match := pattern.search(text):
                actions.append(ActionRequest(name=action_name, arguments=extractor(match)))
                break
        if actions:
            kind = IntentType.DIALOGUE_AND_ACTION if "," in text or len(text.split()) > 8 else IntentType.ACTION
            return Decision(type=kind, confidence=0.9 if kind == IntentType.DIALOGUE_AND_ACTION else 0.97, actions=actions, raw_text=text)
        lowered = text.lower()
        if lowered.endswith("?") or any(lowered.startswith(marker) for marker in _QUESTION_MARKERS):
            return Decision(type=IntentType.QUESTION, confidence=0.8, raw_text=text)
        if any(marker in lowered for marker in _PREFERENCE_MARKERS):
            return Decision(type=IntentType.DIALOGUE, confidence=0.75, memory_candidate=text, raw_text=text)
        return Decision(type=IntentType.DIALOGUE, confidence=0.6, raw_text=text)

    @staticmethod
    def _has_extra_dialogue(text: str, matched: bool) -> bool:
        return matched and ("," in text or len(text.split()) > 8)
