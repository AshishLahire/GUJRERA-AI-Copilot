"""Date phrases in officer questions, in Gujarati, Hindi and English.

"last six months", "છેલ્લા છ મહિનામાં", "पिछले 6 महीने", "this financial year", "આ નાણાકીય વર્ષ",
"since January", "જાન્યુઆરીથી", "in 2025" ... -> a start date (and an end date where needed).

Dates are computed here, never copied from the question, so they are safe to put in SQL as ISO literals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18, "twenty-four": 24,
    "એક": 1, "બે": 2, "ત્રણ": 3, "ચાર": 4, "પાંચ": 5, "છ": 6, "સાત": 7, "આઠ": 8, "નવ": 9, "દસ": 10, "બાર": 12,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छ": 6, "सात": 7, "आठ": 8,
    "नौ": 9, "दस": 10, "बारह": 12,
}
_GU_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯०१२३४५६७८९", "01234567890123456789")
UNITS = {  # word stem -> days per unit (months and years are handled by calendar arithmetic)
    "day": "d", "days": "d", "દિવસ": "d", "दिन": "d", "दिनों": "d",
    "week": "w", "weeks": "w", "અઠવાડિયા": "w", "અઠવાડિયું": "w", "हफ्ते": "w", "हफ़्ते": "w", "हफ्तों": "w", "सप्ताह": "w",
    "month": "m", "months": "m", "મહિના": "m", "મહિનો": "m", "મહિનામાં": "m", "महीने": "m", "महीना": "m", "महीनों": "m", "माह": "m",
    "year": "y", "years": "y", "વર્ષ": "y", "વર્ષમાં": "y", "साल": "y", "सालों": "y", "वर्ष": "y", "वर्षों": "y",
}
LAST = ("last", "past", "previous", "છેલ્લા", "છેલ્લાં", "છેલ્લી", "પાછલા", "पिछले", "पिछली", "पिछला", "बीते", "गत")
MONTHS = {
    1: ("january", "jan", "જાન્યુઆરી", "जनवरी"), 2: ("february", "feb", "ફેબ્રુઆરી", "फरवरी"),
    3: ("march", "mar", "માર્ચ", "मार्च"), 4: ("april", "apr", "એપ્રિલ", "अप्रैल"), 5: ("may", "મે", "मई"),
    6: ("june", "jun", "જૂન", "जून"), 7: ("july", "jul", "જુલાઈ", "जुलाई"), 8: ("august", "aug", "ઓગસ્ટ", "अगस्त"),
    9: ("september", "sep", "sept", "સપ્ટેમ્બર", "सितंबर"), 10: ("october", "oct", "ઓક્ટોબર", "अक्टूबर"),
    11: ("november", "nov", "નવેમ્બર", "नवंबर"), 12: ("december", "dec", "ડિસેમ્બર", "दिसंबर"),
}


@dataclass(frozen=True)
class Period:
    start: date
    end: date | None  # exclusive; None = up to today
    span: tuple[int, int]  # where the phrase is in the (lower-cased) question

    def sql(self, column: str) -> str:
        cond = f"{column} >= '{self.start.isoformat()}'"
        return cond + (f" AND {column} < '{self.end.isoformat()}'" if self.end else "")

    def describe(self, lang: str) -> str:
        last = (self.end - timedelta(days=1)) if self.end else None
        if lang == "gu":
            return f"{self.start.strftime('%d-%m-%Y')} થી" + (f" {last.strftime('%d-%m-%Y')} સુધી" if last else " આજ સુધી")
        if lang == "hi":
            return f"{self.start.strftime('%d-%m-%Y')} से" + (f" {last.strftime('%d-%m-%Y')} तक" if last else " आज तक")
        return f"from {self.start.strftime('%d %b %Y')}" + (f" to {last.strftime('%d %b %Y')}" if last else " to today")


def _months_back(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 - n, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return date(year, month, 28)


def _fy_start(today: date) -> date:
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


_NUM = r"(\d{1,3}|[a-z\-]+|[઀-૿ऀ-ॿ]+)"


def parse_period(text: str, today: date | None = None) -> Period | None:
    """The first date phrase in the question, or None."""
    today = today or date.today()
    t = text.lower().translate(_GU_DIGITS)

    # this / current / last financial year
    m = re.search(r"\b(this|current|last|previous)\s+(?:financial|fiscal)\s+year\b|\bthis\s+fy\b|\blast\s+fy\b", t) \
        or re.search(r"(આ|ચાલુ|ગયા|ગત|પાછલા)\s*નાણાકીય\s*વર્ષ\S*", t) \
        or re.search(r"(इस|चालू|पिछले|गत)\s*(?:वित्तीय|वित्त)\s*वर्ष\S*", t)
    if m:
        start = _fy_start(today)
        word = (m.group(1) or "")
        if any(w in m.group(0) for w in ("last", "previous", "last fy", "ગયા", "ગત", "પાછલા", "पिछले", "गत")) \
                or word in ("last", "previous"):
            return Period(date(start.year - 1, 4, 1), start, m.span())
        return Period(start, None, m.span())

    # last N days/weeks/months/years (number may be a word, or missing: "last month")
    candidates = []
    for lw in LAST:
        candidates += [(m, m.group(1), m.group(2)) for m in re.finditer(rf"{re.escape(lw)}\s+{_NUM}\s+(\S+)", t)]
        candidates += [(m, None, m.group(1)) for m in re.finditer(rf"{re.escape(lw)}\s+(\S+)", t)]
    for m, num_tok, unit_tok in sorted(candidates, key=lambda c: (c[0].start(), c[1] is None)):
        unit = UNITS.get(unit_tok.strip(".,?!")) or next(
            (u for k, u in UNITS.items() if unit_tok.startswith(k) and not k.isascii()), None)
        if not unit:
            continue
        n = 1 if num_tok is None else (int(num_tok) if num_tok.isdigit() else NUMBER_WORDS.get(num_tok))
        if not n or n > 120:
            continue
        if unit == "d":
            start = today - timedelta(days=n)
        elif unit == "w":
            start = today - timedelta(weeks=n)
        elif unit == "m":
            start = _months_back(today, n)
        else:
            start = _months_back(today, 12 * n)
        return Period(start, None, m.span())

    # this quarter / last quarter
    m = re.search(r"\b(this|current|last|previous)\s+quarter\b|(આ|ચાલુ|ગયા|ગત|પાછલા)\s*ત્રિમાસ\S*|(इस|चालू|पिछली|पिछले|गत)\s*तिमाही", t)
    if m:
        q_start = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
        if any(w in m.group(0) for w in ("last", "previous", "ગયા", "ગત", "પાછલા", "पिछली", "पिछले", "गत")):
            prev = _months_back(q_start, 3)
            return Period(prev, q_start, m.span())
        return Period(q_start, None, m.span())

    # this month / this year
    m = re.search(r"\bthis\s+month\b|આ\s*મહિન\S*|इस\s*महीने", t)
    if m:
        return Period(today.replace(day=1), None, m.span())
    m = re.search(r"\bthis\s+year\b|આ\s*વર્ષ\S*|इस\s*(?:साल|वर्ष)", t)
    if m:
        return Period(date(today.year, 1, 1), None, m.span())

    # since <month> [year]
    for month, names in MONTHS.items():
        for name in names:
            pat = (rf"\bsince\s+{name}\b(?:\s+(\d{{4}}))?" if name.isascii()
                   else rf"{re.escape(name)}(?:\s*(\d{{4}}))?\s*(?:થી|से)")
            m = re.search(pat, t)
            if m:
                year = int(m.group(1)) if m.group(1) else (today.year if month <= today.month else today.year - 1)
                return Period(date(year, month, 1), None, m.span())

    # in / during <year>
    m = re.search(r"\b(?:in|during)\s+(20\d{2})\b|(20\d{2})\s*(?:માં|में)", t)
    if m:
        year = int(m.group(1) or m.group(2))
        return Period(date(year, 1, 1), date(year + 1, 1, 1), m.span())
    return None


def without_period(text: str, period: Period | None) -> str:
    """The question with the date phrase removed, so words like "month" do not change which report is used."""
    if not period:
        return text
    t = text.lower().translate(_GU_DIGITS)
    a, b = period.span
    return t[:a] + " " + t[b:]
