"""LLM fallback for questions the keyword rules do not understand.

The self-hosted model only classifies the question and copies out the name it mentions,
as JSON. It never supplies facts: the name is matched against the registry exactly as a
typed name would be, and the answer is built from records. Anything malformed is ignored.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

from gujrera.chat.llm import ollama_generate
from gujrera.config import get_gujrera_settings

INTENTS = ("project", "possession", "promoter", "complaints", "legal", "file_complaint", "track_complaint",
           "check_ad", "greeting", "other")

PROMPT = """You route questions for the GUJRERA (Gujarat real estate regulator) assistant.
The question may be in Gujarati, Hindi, English or a mix. Reply with JSON only, no other text:
{{"intent": "<one of: {intents}>", "name": "<project, builder or agent name exactly as written in the question, or null>", "english": "<the question in plain English>"}}

Intents:
- project: details about a housing project
- possession: when a project will be completed or handed over
- promoter: about a builder, developer or promoter
- complaints: how many complaints a project or builder has
- legal: a question about RERA law, buyers' rights, rules, interest, refunds, penalties
- file_complaint: the user wants to file a complaint
- track_complaint: the user wants the status of their complaint
- check_ad: the user asks if an ad, offer or RERA number is genuine
- greeting: hello, thanks, help
- other: anything else

Question: {question}
JSON:"""


@dataclass
class Routed:
    intent: str
    name: str | None
    english: str | None = None


def parse(raw: str) -> Routed | None:
    m = re.search(r"\{.*?\}", raw or "", flags=re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    intent = str(data.get("intent", "")).strip().lower()
    if intent not in INTENTS:
        return None
    name = data.get("name")
    name = str(name).strip() if name not in (None, "", "null") else None
    if name and (len(name) > 80 or len(name) < 3):
        name = None
    english = data.get("english")
    english = str(english).strip()[:300] if isinstance(english, str) and english.strip() else None
    return Routed(intent, name, english)


def route(question: str, generate: Callable[[str], str] | None = None) -> Routed | None:
    if generate is None and not get_gujrera_settings().GUJRERA_LLM_ROUTER:
        return None
    try:
        raw = (generate or ollama_generate)(PROMPT.format(intents=", ".join(INTENTS), question=question[:500]))
    except Exception:  # noqa: BLE001 - model unavailable: keep the rule-based answer
        return None
    return parse(raw)
