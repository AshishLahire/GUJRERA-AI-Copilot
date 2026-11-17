"""Pull checkable claims out of a property ad, brochure, allotment letter or forward.

Deterministic and rule-based on purpose: every extracted value comes with the
exact text it was read from, so the verdict can show its evidence. Promoter and
project names are not guessed here; they are matched against the registry in
``checks.py``, which is more reliable than free-text name extraction.

Handles English, Gujarati and Hindi keywords and Gujarati/Devanagari digits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from factcheck.lang.normalize import normalize_digits
from gujrera.trust.rera_number import ReraNumber, find_rera_numbers

MONTHS = {
    # English
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
    "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    # Gujarati
    "જાન્યુઆરી": 1, "ફેબ્રુઆરી": 2, "માર્ચ": 3, "એપ્રિલ": 4, "મે": 5, "જૂન": 6, "જુલાઈ": 7,
    "ઓગસ્ટ": 8, "સપ્ટેમ્બર": 9, "ઓક્ટોબર": 10, "નવેમ્બર": 11, "ડિસેમ્બર": 12,
    # Hindi
    "जनवरी": 1, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7,
    "अगस्त": 8, "सितंबर": 9, "अक्टूबर": 10, "नवंबर": 11, "दिसंबर": 12,
}
_MONTH_ALT = "|".join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))

POSSESSION_WORDS = r"(?:possession|handover|hand\s*over|ready\s+(?:to\s+move\s+)?(?:by|in)|completion|પઝેશન|કબજો|પજેશન|पज़ेशन|पजेशन|कब्ज़ा|कब्जा)"
BOOKING_WORDS = r"(?:booking|book\s+(?:now\s+)?(?:with|at|for|by\s+paying)|token|down\s*payment|બુકિંગ|ટોકન|बुकिंग|टोकन)"
RERA_WORDS = re.compile(r"\b(?:G?U?J?\s*RERA|RERA)\b|રેરા|रेरा", re.IGNORECASE)
PROPERTY_WORDS = re.compile(
    r"\b(?:flat|flats|apartment|bhk|villa|plot|plots|shop|shops|office|project|booking|possession|sq\.?\s*ft|"
    r"carpet)\b|ફ્લેટ|પ્લોટ|દુકાન|પ્રોજેક્ટ|ફ્લૅટ|फ्लैट|प्लॉट|दुकान|प्रोजेक्ट",
    re.IGNORECASE,
)

_CURRENCY = r"(?:₹|\brs\.?|\binr\b|રૂ\.?|रु\.?|रुपये)"
_NUM_UNIT = r"\s*(\d+(?:[.,]\d+)*)\s*(lakhs?|lacs?|l|cr|crores?|લાખ|કરોડ|लाख|करोड़|करोड)?(?![a-z])"
_AMOUNT = _CURRENCY + "?" + _NUM_UNIT
_MONEY = _CURRENCY + _NUM_UNIT  # currency sign required
_UNIT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5, "લાખ": 1e5, "लाख": 1e5,
         "cr": 1e7, "crore": 1e7, "crores": 1e7, "કરોડ": 1e7, "करोड़": 1e7, "करोड": 1e7}


@dataclass
class Evidence:
    value: object
    text: str
    start: int
    end: int


@dataclass
class TrustClaim:
    text: str
    project_numbers: list[ReraNumber] = field(default_factory=list)
    agent_numbers: list[ReraNumber] = field(default_factory=list)
    mentions_rera: bool = False
    looks_like_property_offer: bool = False
    possession: Evidence | None = None  # value: date (first day of the stated period)
    booking_percent: Evidence | None = None  # value: float
    booking_amount: Evidence | None = None  # value: float (INR)
    price: Evidence | None = None  # value: float (INR)

    def to_dict(self) -> dict:
        def ev(e: Evidence | None):
            return None if e is None else {"value": e.value, "text": e.text}

        return {
            "project_numbers": [n.normalised for n in self.project_numbers],
            "agent_numbers": [n.normalised for n in self.agent_numbers],
            "mentions_rera": self.mentions_rera,
            "looks_like_property_offer": self.looks_like_property_offer,
            "possession": ev(self.possession),
            "booking_percent": ev(self.booking_percent),
            "booking_amount": ev(self.booking_amount),
            "price": ev(self.price),
        }


def _amount(num: str, unit: str | None) -> float | None:
    try:
        value = float(num.replace(",", ""))
    except ValueError:
        return None
    return value * _UNIT.get((unit or "").lower(), 1.0)


def _possession(text: str) -> Evidence | None:
    """First possession/completion date stated in the text, as the first day of that period."""
    for m in re.finditer(POSSESSION_WORDS, text, re.IGNORECASE):
        window = text[m.end(): m.end() + 60]
        # "Dec 2027", "December, 2027", "ડિસેમ્બર 2027"
        mm = re.search(rf"({_MONTH_ALT})[\s,.'-]*(20\d\d)", window, re.IGNORECASE)
        if mm:
            month = MONTHS[mm.group(1).lower()]
            d = date(int(mm.group(2)), month, 1)
            return Evidence(d, text[m.start(): m.end() + mm.end()].strip(), m.start(), m.end() + mm.end())
        # "12/2027", "12-2027"
        mm = re.search(r"\b(0?[1-9]|1[0-2])\s*[/-]\s*(20\d\d)\b", window)
        if mm:
            d = date(int(mm.group(2)), int(mm.group(1)), 1)
            return Evidence(d, text[m.start(): m.end() + mm.end()].strip(), m.start(), m.end() + mm.end())
        # "2027" alone
        mm = re.search(r"\b(20\d\d)\b", window)
        if mm:
            d = date(int(mm.group(1)), 1, 1)
            return Evidence(d, text[m.start(): m.end() + mm.end()].strip(), m.start(), m.end() + mm.end())
    return None


def _booking(text: str) -> tuple[Evidence | None, Evidence | None]:
    pct = amt = None
    for m in re.finditer(BOOKING_WORDS, text, re.IGNORECASE):
        lo, hi = max(0, m.start() - 25), min(len(text), m.end() + 40)
        window = text[lo:hi]
        if pct is None:
            pm = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%", window)
            if pm:
                pct = Evidence(float(pm.group(1)), window.strip(), lo, hi)
        if amt is None:
            # amount must follow the keyword ("Booking Rs 2 lakh"), so a price stated earlier is not taken
            after = text[m.start():hi]
            am = re.search(_MONEY, after, re.IGNORECASE)
            if am:
                value = _amount(am.group(1), am.group(2))
                if value:
                    amt = Evidence(value, after[: am.end()].strip(), m.start(), m.start() + am.end())
    return pct, amt


def _price(text: str) -> Evidence | None:
    for m in re.finditer(r"(?:price|starting|starts\s+at|onwards|કિંમત|કિમત|कीमत)", text, re.IGNORECASE):
        lo, hi = m.start(), min(len(text), m.end() + 40)
        window = text[lo:hi]
        for am in re.finditer(_AMOUNT, window, re.IGNORECASE):
            if am.group(2):  # require a lakh/crore unit to avoid picking up phone numbers
                value = _amount(am.group(1), am.group(2))
                if value:
                    return Evidence(value, window[: am.end()].strip(), lo, lo + am.end())
    return None


def extract_claim(raw_text: str) -> TrustClaim:
    text = normalize_digits(raw_text or "")
    numbers = find_rera_numbers(text)
    pct, amt = _booking(text)
    return TrustClaim(
        text=text,
        project_numbers=[n for n in numbers if n.kind == "project"],
        agent_numbers=[n for n in numbers if n.kind == "agent"],
        mentions_rera=bool(RERA_WORDS.search(text)),
        looks_like_property_offer=bool(PROPERTY_WORDS.search(text)),
        possession=_possession(text),
        booking_percent=pct,
        booking_amount=amt,
        price=_price(text),
    )
