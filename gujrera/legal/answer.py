"""Answer law questions from the RERA Act, Gujarat Rules and orders (retrieval-augmented).

1. Retrieve the relevant provisions (``gujrera.legal.search``).
2. Say which provision applies, in the user's language (template, always correct).
3. Ask the self-hosted LLM to summarise ONLY those provisions, in English, with a [n] marker
   per sentence. The summary is kept only if every sentence is cited and it adds no number
   that is not in the provisions (``gujrera.chat.llm.guard``). Otherwise the provision is quoted.
4. Always add that this is information from the law, not legal advice.

Summaries are English because the 7B model's Gujarati/Hindi output was unusable in testing;
translating the checked English summary (IndicTrans2) is the planned next step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from gujrera.chat.llm import guard, ollama_generate
from gujrera.config import get_gujrera_settings
from gujrera.legal.search import Hit, default_index
from gujrera.profile.summarise import Sentence

S = {
    "lead": {
        "en": "The relevant provision is {label}: {title}.",
        "gu": "સંબંધિત જોગવાઈ {label} છે: {title}.",
        "hi": "संबंधित प्रावधान {label} है: {title}।",
    },
    "also": {
        "en": "Also relevant: {labels}.",
        "gu": "આ પણ સંબંધિત છે: {labels}.",
        "hi": "यह भी संबंधित है: {labels}।",
    },
    "english_summary": {
        "en": "",
        "gu": "અંગ્રેજીમાં સારાંશ:",
        "hi": "अंग्रेज़ी में सारांश:",
    },
    "quote": {
        "en": "The text says: “{excerpt}”",
        "gu": "કાયદાનું લખાણ (અંગ્રેજીમાં): “{excerpt}”",
        "hi": "कानून का पाठ (अंग्रेज़ी में): “{excerpt}”",
    },
    "not_legal_advice": {
        "en": "This is information from the law, not legal advice.",
        "gu": "આ કાયદામાંથી માહિતી છે, કાનૂની સલાહ નથી.",
        "hi": "यह कानून से जानकारी है, कानूनी सलाह नहीं।",
    },
    "not_found": {
        "en": "I couldn't find this in the RERA Act, the Gujarat RERA Rules or the orders available to me.",
        "gu": "મને ઉપલબ્ધ RERA કાયદા, ગુજરાત RERA નિયમો કે આદેશોમાં આ મળ્યું નથી.",
        "hi": "मुझे उपलब्ध RERA अधिनियम, गुजरात RERA नियमों या आदेशों में यह नहीं मिला।",
    },
    "no_index": {
        "en": "The legal texts have not been indexed yet (run scripts/build_gujrera_legal_index.py).",
        "gu": "કાયદાના લખાણ હજુ ઇન્ડેક્સ થયા નથી.",
        "hi": "कानून के पाठ अभी इंडेक्स नहीं हुए हैं।",
    },
}

PROMPT = (
    "Answer the home buyer's question in English, in at most 4 short sentences, using ONLY the sources "
    "below. End every sentence with the [n] of the source it comes from. Do not add any number, date, "
    "section or rule that is not in the sources. If the sources do not answer the question, say so.\n\n"
    "Question: {question}\n\nSources:\n{sources}\n\nAnswer:"
)


def s(key: str, lang: str, **values: Any) -> str:
    entry = S[key]
    return entry.get(lang, entry["en"]).format(**values)


@dataclass
class LegalAnswer:
    intent: str
    sentences: list[Sentence]
    card: dict[str, Any] | None = None


def _excerpt(text: str, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def answer(question: str, lang: str, *, generate: Callable[[str], str] | None = None,
           use_llm: bool | None = None, search_query: str | None = None) -> LegalAnswer:
    index = default_index()
    if index is None:
        return LegalAnswer("legal_unavailable", [Sentence(s("no_index", lang), [], "legal_no_index")])
    settings = get_gujrera_settings()
    use_llm = settings.GUJRERA_RAG_LLM if use_llm is None else use_llm
    hits: list[Hit] = index.search(search_query or question, k=5)
    if hits and (use_llm or generate is not None):
        from gujrera.legal.rerank import rerank

        hits = rerank(question, hits, generate or ollama_generate)  # the model picks which provision answers it
    hits = hits[:3]
    if not hits:
        return LegalAnswer("legal_not_found", [Sentence(s("not_found", lang), [], "legal_not_found")])

    top = hits[0]
    sentences = [Sentence(s("lead", lang, label=top.label, title=top.chunk["title"]), [top.citation()], "legal_lead")]
    others = [h for h in hits[1:] if h.label != top.label]
    if others:
        sentences.append(Sentence(s("also", lang, labels="; ".join(h.label for h in others)),
                                  [h.citation() for h in others], "legal_also"))

    summary_by = "quote"
    if use_llm or generate is not None:
        sources = "\n\n".join(f"[{i}] {h.label} ({h.chunk['title']}): {_excerpt(h.chunk['text'], 1100)}"
                              for i, h in enumerate(hits, 1))
        try:
            raw = (generate or ollama_generate)(PROMPT.format(question=question, sources=sources))
        except Exception:  # noqa: BLE001 - model down or slow: quote instead
            raw = ""
        raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
        if raw and guard(sources, raw):
            if lang != "en":
                sentences.append(Sentence(s("english_summary", lang), [], "legal_english_note"))
            for part in re.split(r"(?<=[.!?])\s+(?=\S)", raw):
                refs = [int(n) for n in re.findall(r"\[(\d+)\]", part) if 1 <= int(n) <= len(hits)]
                text = re.sub(r"\s*\[\d+\]", "", part).strip()
                if text:
                    sentences.append(Sentence(text, [hits[r - 1].citation() for r in refs], "legal_summary"))
            summary_by = "llm"
    if summary_by == "quote":
        sentences.append(Sentence(s("quote", lang, excerpt=_excerpt(top.chunk["text"])), [top.citation()],
                                  "legal_quote"))
    sentences.append(Sentence(s("not_legal_advice", lang), [], "legal_disclaimer"))
    card = {
        "type": "legal", "summary_by": summary_by,
        "hits": [{"label": h.label, "title": h.chunk["title"], "kind": h.chunk["kind"], "page": h.chunk.get("page"),
                  "excerpt": _excerpt(h.chunk["text"], 600), "score": round(h.cosine, 3)} for h in hits],
    }
    return LegalAnswer("legal", sentences, card)
