"""Optional rephrasing of template answers by a self-hosted LLM, behind a citation guard.

The model only rewrites sentences we already built from registry records. Its
output is accepted only if:
- every sentence carries at least one [n] marker, and only markers we supplied;
- every number in the output (dates, counts, percentages, registration codes)
  already appears in the input.
Otherwise the original template answer is returned unchanged. Disabled by
default (GUJRERA_LLM_PHRASING=false); the deck commits to self-hosted models,
so only a local Ollama endpoint is supported.
"""

from __future__ import annotations

import re
from typing import Callable

import httpx

from factcheck.lang.normalize import normalize_digits
from gujrera.config import get_gujrera_settings
from gujrera.chat.orchestrator import Reply

LANG_NAMES = {"en": "English", "gu": "Gujarati", "hi": "Hindi"}
_MARK = re.compile(r"\[(\d+)\]")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")

PROMPT = (
    "Rewrite the facts below as one short, friendly answer in {language} for a home buyer.\n"
    "Rules: use ONLY these facts; do not add any fact, number, date or advice; keep each [n] marker at the "
    "end of the sentence it supports; keep names and registration numbers exactly as written.\n\n"
    "Facts:\n{facts}\n\nAnswer:"
)


def guard(original: str, candidate: str) -> bool:
    """True if the rewritten answer keeps citations and adds no numbers."""
    candidate = candidate.strip()
    if not candidate:
        return False
    allowed_marks = set(_MARK.findall(original))
    sentences = [s for s in re.split(r"(?<=[.!?।])\s+", candidate) if s.strip()]
    for s in sentences:
        marks = set(_MARK.findall(s))
        if not marks or not marks <= allowed_marks:
            return False
    numbers_in = set(_NUM.findall(normalize_digits(_MARK.sub(" ", original))))
    numbers_out = set(_NUM.findall(normalize_digits(_MARK.sub(" ", candidate))))
    return numbers_out <= numbers_in


def ollama_generate(prompt: str) -> str:
    cfg = get_gujrera_settings()
    res = httpx.post(
        f"{cfg.GUJRERA_LLM_BASE_URL.rstrip('/')}/api/chat",
        json={"model": cfg.GUJRERA_LLM_MODEL, "stream": False, "think": False,
              "options": {"temperature": 0},
              "messages": [{"role": "user", "content": prompt}]},
        timeout=cfg.GUJRERA_LLM_TIMEOUT_SECONDS,
    )
    res.raise_for_status()
    return res.json()["message"]["content"]


def make_rephraser(generate: Callable[[str], str] = ollama_generate) -> Callable[[Reply], Reply]:
    def rephrase(reply: Reply) -> Reply:
        data = reply.to_dict()
        cited = [s for s in data["sentences"] if s["refs"]]
        if not cited:
            return reply
        facts = "\n".join(f"- {s['text']} " + " ".join(f"[{r}]" for r in s["refs"][:3]) for s in cited)
        try:
            out = generate(PROMPT.format(language=LANG_NAMES.get(reply.lang, "English"), facts=facts))
        except Exception:  # noqa: BLE001 - any model failure falls back to the template answer
            return reply
        out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()
        if guard(facts, out):
            uncited = " ".join(s["text"] for s in data["sentences"] if not s["refs"])
            reply.text_override = (out + (" " + uncited if uncited else "")).strip()
            reply.phrased_by = "llm"
        return reply

    return rephrase
