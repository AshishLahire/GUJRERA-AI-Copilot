"""Complaint category detection, form choice and field validation.

Form rule (verify against the Gujarat Real Estate Rules, 2017 before the pilot):
    Form A: complaint to the Authority, RERA Act Section 31 (all reliefs except compensation)
    Form B: compensation claim to the adjudicating officer, Section 71
"""

from __future__ import annotations

import re

from factcheck.lang.normalize import normalize_digits

CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "possession_delay": ("possession", "delay", "delayed", "not handed", "handover", "late", "still not ready",
                         "પઝેશન", "વિલંબ", "મોડું", "કબજો", "पज़ेशन", "पजेशन", "कब्जा", "कब्ज़ा", "देरी"),
    "refund": ("refund", "money back", "cancel my booking", "withdraw", "return my money",
               "રિફંડ", "પૈસા પાછા", "रिफंड", "पैसे वापस"),
    "structural_defect": ("crack", "cracks", "leak", "leakage", "seepage", "defect", "damp", "plaster",
                          "તિરાડ", "લીકેજ", "ખામી", "ભેજ", "दरार", "रिसाव", "सीलन", "खराबी"),
    "plan_deviation": ("plan changed", "deviation", "extra floor", "layout changed", "changed the plan",
                       "different from plan", "પ્લાન બદલ", "નકશો બદલ", "नक्शा बदल", "प्लान बदल"),
    "false_advertisement": ("brochure", "advertis", "promised in the ad", "misleading",
                            "જાહેરાત", "બ્રોશર", "विज्ञापन", "ब्रोशर"),
    "amenities_not_provided": ("amenit", "club house", "clubhouse", "parking", "garden", "lift", "swimming",
                               "સુવિધા", "પાર્કિંગ", "લિફ્ટ", "सुविधा", "पार्किंग", "लिफ्ट"),
    "agreement_violation": ("extra payment", "extra charges", "demanding more", "agreement", "escalation",
                            "વધારાના પૈસા", "વધારાનો ચાર્જ", "કરાર", "अतिरिक्त भुगतान", "अतिरिक्त शुल्क",
                            "अनुबंध"),
    "agent_misconduct": ("agent", "broker", "એજન્ટ", "દલાલ", "एजेंट", "दलाल"),
    "compensation": ("compensation", "damages", "loss", "વળતર", "નુકસાન", "मुआवजा", "नुकसान"),
}
# When several categories match, the earlier one in this list wins.
PRIORITY = ("refund", "structural_defect", "plan_deviation", "false_advertisement", "agent_misconduct",
            "amenities_not_provided", "agreement_violation", "compensation", "possession_delay")

RELIEF_WORDS: dict[str, tuple[str, ...]] = {
    "possession_with_interest": ("possession", "interest", "પઝેશન", "કબજો", "कब्जा", "पज़ेशन"),
    "refund_with_interest": ("refund", "money back", "રિફંડ", "પૈસા પાછા", "रिफंड", "पैसे वापस"),
    "rectification": ("repair", "fix", "rectif", "correct", "સમારકામ", "મરામત", "मरम्मत", "ठीक"),
    "compensation": ("compensation", "damages", "વળતર", "मुआवजा"),
}
DEFAULT_RELIEF = {
    "possession_delay": "possession_with_interest",
    "refund": "refund_with_interest",
    "structural_defect": "rectification",
    "plan_deviation": "rectification",
    "amenities_not_provided": "rectification",
    "compensation": "compensation",
}

_MOBILE_RE = re.compile(r"^(?:\+?91[\s-]?|0)?([6-9]\d{9})$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
SKIP_WORDS = {"skip", "no", "none", "na", "n/a", "-", "છોડો", "નથી", "ના", "छोड़ें", "नहीं", "छोड़ो"}
CANCEL_WORDS = {"cancel", "stop", "quit", "exit", "રદ", "રદ કરો", "बंद", "रद्द", "रद्द करें"}


def classify(text: str) -> list[str]:
    """Categories mentioned in the text, most specific first."""
    lc = text.lower()
    hits = {cat for cat, words in CATEGORY_WORDS.items() if any(w in lc for w in words)}
    return [c for c in PRIORITY if c in hits]


def match_relief(text: str) -> str | None:
    lc = text.lower()
    for relief, words in RELIEF_WORDS.items():
        if any(w in lc for w in words):
            return relief
    return None


def form_for(relief: str | None) -> str:
    return "B" if relief == "compensation" else "A"


def clean_mobile(text: str) -> str | None:
    digits = re.sub(r"[\s()-]", "", normalize_digits(text or ""))
    m = _MOBILE_RE.match(digits)
    return m.group(1) if m else None


def clean_email(text: str) -> str | None:
    value = (text or "").strip()
    return value if _EMAIL_RE.match(value) else None


def clean_name(text: str) -> str | None:
    value = re.sub(r"\s+", " ", (text or "").strip())
    letters = sum(ch.isalpha() for ch in value)
    if letters < 3 or any(ch.isdigit() for ch in value) or len(value) > 80:
        return None
    return value


def is_skip(text: str) -> bool:
    return (text or "").strip().lower() in SKIP_WORDS


def is_cancel(text: str) -> bool:
    return (text or "").strip().lower() in CANCEL_WORDS


def mask_mobile(mobile: str) -> str:
    return mobile[:2] + "xxxxxx" + mobile[-2:]
