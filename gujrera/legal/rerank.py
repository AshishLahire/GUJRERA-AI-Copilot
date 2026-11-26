"""Let the self-hosted model pick which retrieved provision answers the question.

Search ranks provisions by similarity, and near-ties are common ("Section 17 or 18?"). The model reads the
question (in any language) and the top candidates' titles and plain descriptions, and replies with one
number. It can only reorder what search found; it never adds a provision. Anything unexpected in its reply
leaves the search order as it was.
"""

from __future__ import annotations

import re
from typing import Callable

from gujrera.legal.glossary import english_terms
from gujrera.legal.plain import PLAIN
from gujrera.legal.search import Hit

PROMPT = """A home buyer in Gujarat asked a question (it may be in Gujarati, Hindi or English).
Which ONE of these legal provisions answers it best? Choose the provision that deals specifically with the
question's subject; choose a general one (such as the rights and duties of allottees) only when the question
is about rights or duties in general. Reply with its number only.

Question: {question}{terms}

{candidates}

Number:"""


def _describe(h: Hit) -> str:
    plain = " ".join(t for t in PLAIN.get((h.chunk["kind"], h.chunk["number"]), []) if t.isascii())
    about = plain or " ".join(h.chunk["text"].split())[:220]
    return f"{h.label}: {h.chunk['title']}. {about}"


def rerank(question: str, hits: list[Hit], generate: Callable[[str], str], *, k: int = 5) -> list[Hit]:
    if len(hits) < 2 or any(h.exact for h in hits):
        return hits
    top = hits[:k]
    listing = "\n".join(f"{i}. {_describe(h)}" for i, h in enumerate(top, 1))
    terms = english_terms(question)
    hint = f"\nKey terms in English: {terms}" if terms and not question.isascii() else ""
    try:
        raw = generate(PROMPT.format(question=question[:400], terms=hint, candidates=listing))
    except Exception:  # noqa: BLE001 - model unavailable: keep the search order
        return hits
    reply = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    m = re.match(r"\(?([1-9])\b", reply) if len(reply) <= 40 else None  # a number, not a sentence
    if not m or not 1 <= int(m.group(1)) <= len(top):
        return hits
    chosen = int(m.group(1)) - 1
    if chosen == 0:
        return hits
    return [top[chosen], *top[:chosen], *top[chosen + 1:], *hits[k:]]
