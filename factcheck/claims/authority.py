"""Resolve the free-text issuing authority returned by Stage 3 to an issuer registry id.

Ported from members_4_5/authority.py. Stage 2 (`forensics.checks.detect_issuer`) scores a whole
document by letterhead position; this module instead resolves a short authority *name* such as
"Reserve Bank", "Nirmala Sitharaman" or "कौशल भारत" coming out of the claim LLM.

The alias table is built from `forensics.rules.ISSUER_ALIASES` (document aliases, incl. regional
scripts) plus claim-level extras below (heads of ministries, scheme names, short English forms).
The extras are kept here, not in ISSUER_ALIASES, so forensic issuer detection and its evaluated
risk scores are unchanged.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from factcheck.forensics.rules import ISSUER_ALIASES, load_issuer_registry

# Claim-level aliases added after testing the members_4_5 extractor on the PIB benchmark.
CLAIM_EXTRA_ALIASES: dict[str, list[str]] = {
    "RBI": ["reserve bank"],
    "SEBI": ["securities and exchange board"],
    "CBSE": ["central board of secondary"],
    "I4C": ["indian cyber crime coordination center", "cyber crime coordination"],
    "MUDRA": ["pm mudra", "micro units development", "मुद्रा"],
    "TRAI": ["telecom regulatory authority"],
    "BSNL": ["bharat sanchar nigam"],
    "MOE": ["education ministry", "shiksha mantralaya", "free laptop scheme", "new education policy"],
    "NBE": ["nbe", "nbems"],
    "NTA": ["nta", "national testing agency"],
    "UGC": ["ugc", "university grants commission"],
    "RRB": ["rrb", "railway recruitment", "indian railways", "ministry of railways", "railway board",
            "रेल मंत्रालय", "रेलवे भर्ती"],
    "MOF": ["finance ministry", "nirmala sitharaman", "department of financial services", "वित्त मंत्रालय"],
    "MOP": ["power ministry", "विद्युत मंत्रालय", "ऊर्जा मंत्रालय"],
    "MOL": ["ministry of labor", "labour ministry", "epfo", "rojgar yojana", "rozgar yojana",
            "रोजगार योजना", "श्रम मंत्रालय"],
    "MSDE": ["msde", "skill india", "ministry of skill development", "kaushal bharat", "kushal bharat", "कौशल भारत"],
    "OMC": ["indian oil", "bharat petroleum", "hindustan petroleum", "oil marketing compan",
            "ministry of petroleum", "petroleum and natural gas", "indane", "bharatgas", "bharat gas",
            "hp gas", "भारत गैस", "इंडेन"],
    "ITD": ["income tax department", "income-tax department", "income tax dept", "income tax", "cbdt",
            "e-pan", "epan", "आयकर विभाग"],
    "MOD": ["ministry of defense", "defence ministry", "indian army", "indian navy", "indian air force",
            "rajnath singh", "chief of army staff", "रक्षा मंत्रालय"],
    "MEA": ["external affairs ministry"],
    "MHA": ["home ministry", "amit shah", "गृह मंत्रालय", "अमित शाह"],
    "MOHFW": ["health ministry", "national health mission", "cghs", "राष्ट्रीय स्वास्थ्य मिशन", "स्वास्थ्य मंत्रालय"],
    "MSME": ["ministry of micro small"],
    "MORTH": ["ministry of road transport", "parivahan", "echallan", "e-challan", "nitin gadkari",
              "नितिन गडकरी", "सड़क परिवहन"],
    "MIB": ["information and broadcasting"],
    "MOCI": ["ministry of commerce"],
    "MNRE": ["ministry of new and renewable", "pm-kusum", "pm kusum"],
    "MEITY": ["ministry of electronics", "digital india", "डिजिटल इंडिया"],
    "MOEFCC": ["ministry of environment"],
    "SCI": ["supreme court"],
}

# A type of organisation is not a name. Treat these as "not stated" so every language agrees.
GENERIC_AUTHORITIES = {
    "bank", "banks", "the bank", "a bank", "petroleum company", "petroleum companies", "oil company",
    "oil companies", "telecom company", "telecom companies", "company", "companies", "police",
    "officials", "authorities", "the authorities", "government agency", "department",
    "not stated", "none", "unknown", "n/a",
}


def _normalise(text: str) -> str:
    # NFKC folds stylised Unicode (e.g. mathematical bold "𝐏𝐌") back to plain letters.
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).lower()).strip()


@lru_cache(maxsize=1)
def _compiled_aliases() -> tuple[tuple[int, str, re.Pattern[str]], ...]:
    registry = load_issuer_registry()
    compiled: list[tuple[int, str, re.Pattern[str]]] = []
    for issuer_id in set(ISSUER_ALIASES) | set(CLAIM_EXTRA_ALIASES):
        if issuer_id not in registry:
            continue
        aliases = ISSUER_ALIASES.get(issuer_id, []) + CLAIM_EXTRA_ALIASES.get(issuer_id, [])
        for alias in {_normalise(a) for a in aliases if a and a.strip()}:
            pat = re.compile(r"(?<![\w])" + re.escape(alias) + r"(?![\w])")
            compiled.append((len(alias), issuer_id, pat))
    compiled.sort(key=lambda t: -t[0])
    return tuple(compiled)


def resolve_issuer(name: str | None) -> str | None:
    """Return the registry issuer_id for an authority name, or None when nothing matches.

    When several issuers are named ("MUDRA / Ministry of Finance") the one named first wins; at the
    same position the longest alias wins, so "Reserve Bank of India" beats "Bank of India".
    """
    if not name or not name.strip():
        return None
    text = _normalise(name)
    best: tuple[int, int, str] | None = None  # (start, -alias_len, issuer_id)
    for alias_len, issuer_id, pat in _compiled_aliases():
        m = pat.search(text)
        if m:
            cand = (m.start(), -alias_len, issuer_id)
            if best is None or cand < best:
                best = cand
    return best[2] if best else None


def normalise_authority(name: str | None) -> tuple[str | None, str | None]:
    """Return (display name, issuer_id).

    Known issuers get their official English name from the registry; generic types of organisation
    become (None, None); unknown names are returned unchanged with issuer_id None.
    """
    if not name or not name.strip():
        return None, None
    if _normalise(name).rstrip(".") in GENERIC_AUTHORITIES:
        return None, None
    issuer_id = resolve_issuer(name)
    if issuer_id:
        entry = load_issuer_registry().get(issuer_id, {})
        return entry.get("name_en", issuer_id), issuer_id
    return name.strip(), None
