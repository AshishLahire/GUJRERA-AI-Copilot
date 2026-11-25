"""Follow-up refinements to an officer's last report, so a report can be narrowed in a few words.

"Projects under scrutiny in Ahmedabad" → "only Bopal" → "last 3 months" → "in Vadodara instead" → "top 5"

A short follow-up that is not a question of its own, and names a district, a locality, a date range or a
"top N", is merged into the previous question: the old district, locality, period or count is replaced and
the new one added. The merged question then goes through the normal path (standard report, district scope,
SQL guard, audit), so a refinement can never see more than the officer could ask for directly.
Gujarati, Hindi and English; the follow-up may be in a different language from the question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from gujrera.analytics.periods import _GU_DIGITS, parse_period, without_period
from gujrera.analytics.reports import DISTRICT_WORDS, find_district, find_locality, match_report

_TOP = re.compile(r"\btop\s+(\d{1,3})\b|(?<![\d/])(\d{1,3})\s*(?:સૌથી|सबसे)")
_TOP_ANY = re.compile(r"\btop\s+\d{1,3}\b")
MAX_WORDS = 10


@dataclass
class Refined:
    question: str  # the merged question that is answered
    changes: list[dict[str, str]]  # what the follow-up changed: {"kind": "district"|..., "value": ...}


def _drop_words(text: str, words: list[str]) -> str:
    for w in sorted(words, key=len, reverse=True):
        if w.isascii():
            text = re.sub(rf"(?<![a-z]){re.escape(w)}(?![a-z])", " ", text)
        else:
            text = text.replace(w, " ")
    return text


def _district_words(district: str) -> list[str]:
    return [w for w, d in DISTRICT_WORDS.items() if d == district]


def _locality_words(locality: str) -> list[str]:
    from gujrera.authority_seed import locality_names

    return [w for w, name in locality_names().items() if name == locality]


def refine(previous: str | None, followup: str) -> Refined | None:
    """The previous question narrowed by the follow-up, or None if the follow-up stands on its own."""
    f = (followup or "").strip().lower().translate(_GU_DIGITS)
    if not previous or not f or len(f.split()) > MAX_WORDS:
        return None
    if match_report(f):  # a full question of its own
        return None
    period = parse_period(f)
    rest = without_period(f, period)
    district = find_district(rest)
    locality = find_locality(rest)
    top = _TOP.search(rest)
    if not (period or district or locality or top):
        return None

    q = previous.strip().lower().translate(_GU_DIGITS)
    changes: list[dict[str, str]] = []
    if period:
        q = without_period(q, parse_period(q))
        a, b = period.span
        phrase = f[a:b].strip()
        q = f"{q} {phrase}"
        changes.append({"kind": "period", "value": phrase})
    if district:
        old = find_district(q)
        if old and old != district:
            q = _drop_words(q, _district_words(old))
        old_loc = find_locality(q)
        if old_loc:  # a locality belongs to its old district: drop it with the district
            q = _drop_words(q, _locality_words(old_loc))
        if find_district(q) != district:
            q = f"{q} in {district.lower()}"
        changes.append({"kind": "district", "value": district})
    if locality:
        old_loc = find_locality(q)
        if old_loc and old_loc != locality:
            q = _drop_words(q, _locality_words(old_loc))
        if find_locality(q) != locality:
            q = f"{q} in {locality.lower()}"
        changes.append({"kind": "locality", "value": locality})
    if top:
        n = top.group(1) or top.group(2)
        q = _TOP_ANY.sub(" ", q)
        q = f"top {n} {q}"
        changes.append({"kind": "top", "value": n})
    q = re.sub(r"\s+", " ", q).strip()
    q = re.sub(r"\b(in|for)(?:\s+(?:in|for)\b)+", r"\1", q)  # "in in surat" after a district was dropped
    q = re.sub(r"\b(?:in|for)\s*$", "", q).strip()
    if not match_report(q):  # the previous question was not a standard report: do not guess
        return None
    return Refined(q, changes)
