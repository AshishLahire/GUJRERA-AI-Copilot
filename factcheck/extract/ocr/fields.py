"""Regex extraction of reference numbers, dates, phone numbers, emails, URLs, and amounts."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from factcheck.lang.normalize import INDIC_DIGITS_TRANS, normalize_digits, normalize_text
from factcheck.schemas import ExtractedFields

# Watermark lines and fragments found on 06_synthetic_forgeries images
_WATERMARK_LINE_RE = re.compile(
    r"(?im)^.*(?:"
    r"SYNTHETIC\s*[-–—]?\s*NOT\s+A\s+REAL\s+DOCUMENT"
    r"|NOT\s+A\s+REAL\s+DOCUMENT"
    r"|FOR\s+DETECTOR\s+TRAINING"
    r"|SYNTHETIC\s+SAMPLE"
    r").*$"
)
_WATERMARK_INLINE_RE = re.compile(
    r"(?i)(?:"
    r"SYNTHETIC\s*[-–—:]?\s*NOT\s+A\s+REAL\s+DOCUMENT(?:\s*[-–—:]?\s*FOR\s+DETECTOR\s+TRAINING)?"
    r"|NOT\s+A\s+REAL\s+DOCUMENT"
    r"|FOR\s+DETECTOR\s+TRAINING(?:\s+ONLY)?"
    r")"
)


DEVANAGARI_DIGITS_TRANS = INDIC_DIGITS_TRANS

HINDI_PREFIX_MAPPING: dict[str, str] = {
    "शैक्ष": "Acad",
    "िैक्ष": "Acad",
    "शैक्षणिक": "Acad",
    "अकाद": "Acad",
    "अकादमिक": "Acad",
}

CLEAN_HINDI_PREFIX_RE = re.compile(
    r"^(?:(?:"
    r"(?:परिपत्र|पत्रांक|क्रमांक|आदेश|संदर्भ)\s*(?:स[ां]*ख्या|सं\.?)?|स[ां]*ख्या|सं\.?"
    r"|(?:পরিপত্র|স্মারক|নথি|চিঠি|সূত্র)\s*(?:নম্বর|নং\.?)?|নম্বর|নং\.?"
    r"|(?:પરિપત્ર|સંદર્ભ|પત્ર|જાહેરનામું)\s*(?:ક્રમાંક|સંખ્યા)?|ક્રમાંક|સંખ્યા"
    r"|(?:சுற்றறிக்கை|குறிப்பு|கடித)\s*(?:எண்)?|எண்"
    r"|(?:సర్క్యులర్|రిఫరెన్స్|లేఖ)\s*(?:నంబర్|సంఖ్య)?|సంఖ్య|నంబర్|క్రమ\s*సంఖ్య"
    r"|(?:ಸುತ್ತೋಲೆ|ಉಲ್ಲೇಖ|ಪತ್ರದ)\s*(?:ಸಂಖ್ಯೆ|ಕ್ರಮಾಂಕ)?|ಸಂಖ್ಯೆ|ಕ್ರಮಾಂಕ"
    r"|(?:സർക്കുലർ|പരാമർശം|കത്ത്)\s*(?:നമ്പർ)?|നമ്പർ"
    r"|(?:ਸਰਕੂਲਰ|ਹਵਾਲਾ|ਪੱਤਰ)\s*(?:ਨੰਬਰ)?|ਨੰਬਰ"
    r"|(?:ପରିପତ୍ର|ସନ୍ଦର୍ଭ|ଚିଠି)\s*(?:ସଂଖ୍ୟା|କ୍ରମାଙ୍କ)?|ସଂଖ୍ୟା|କ୍ରମାଙ୍କ"
    r"|(?:سرکلر|حوالہ|خط)\s*(?:نمبر)?|نمبر"
    r")\s*[:\-]?\s*)",
    re.IGNORECASE,
)
CLEAN_MULTILINGUAL_PREFIX_RE = CLEAN_HINDI_PREFIX_RE



@lru_cache(maxsize=1)
def _load_registry_hindi_prefix_mappings() -> dict[str, str]:
    mappings = dict(HINDI_PREFIX_MAPPING)
    reg_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "dataset"
        / "03_issuer_registry"
        / "issuers.json"
    )
    if reg_path.exists():
        try:
            data = json.loads(reg_path.read_text(encoding="utf-8"))
            for issuer in data.get("issuers", []):
                m = issuer.get("hindi_reference_prefix_mapping")
                if isinstance(m, dict):
                    mappings.update(m)
        except Exception:
            pass
    return mappings

def _is_ref_date_or_amount(num_slash: str, text: str, match_start: int, match_end: int) -> bool:
    """Reject plain number/number references that look like dates or amounts."""
    parts = num_slash.split("/")
    if len(parts) != 2:
        return True
    try:
        n1 = int(parts[0])
        n2 = int(parts[1])
    except ValueError:
        return True
    if n1 <= 31 and n2 <= 12:
        return True
    if n1 <= 31 and (1900 <= n2 <= 2099):
        return True
    if (1900 <= n1 <= 2099) and n2 <= 31:
        return True
    prefix = text[max(0, match_start - 15) : match_start]
    suffix = text[match_end : min(len(text), match_end + 15)]
    if re.search(r"(?:₹|Rs\.?|INR|रु\.?)\s*$", prefix, re.IGNORECASE):
        return True
    if suffix.startswith("/-"):
        return True
    return False

def normalize_reference_number(raw_ref: str) -> str:
    """Normalize reference number: convert all Indic digits to ASCII, strip Hindi prefixes, and map prefix abbreviations (e.g. शैक्ष -> Acad)."""
    s = normalize_text(raw_ref, convert_digits=True).strip()
    s = re.sub(r"\s+", " ", s)
    s = CLEAN_HINDI_PREFIX_RE.sub("", s).strip()
    s = re.sub(
        r"^(?:(?:Circular|Cir|Order|Ref(?:erence)?|File|Letter|Notification)\s*\.?\s*)?(?:No\.?|Ref)\s*[:\-]?\s*",
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()
    for hi_pre, en_pre in _load_registry_hindi_prefix_mappings().items():
        if s.startswith(hi_pre):
            s = en_pre + s[len(hi_pre):]
            break
        if s.startswith(f"{hi_pre}-") or s.startswith(f"{hi_pre}/"):
            s = en_pre + s[len(hi_pre):]
            break
    return s.strip()

# Reference number patterns (ordered from specific to general)
_REF_PATTERNS: list[re.Pattern[str]] = [
    # Multilingual Indic reference patterns across scripts (Devanagari, Bengali, Gujarati, Tamil, Telugu, Kannada, Malayalam, Gurmukhi, Odia, Arabic/Urdu):
    re.compile(
        r"(?:(?:"
        r"परिपत्र\s+संख्या|परिपत्र\s+सं\.?|परिपत्र|पत्रांक|क्रमांक|संदर्भ|संख्या|सं\."
        r"|পরিপত্র\s+নম্বর|পরিপত্র\s+নং\.?|পরিপত্র|স্মারক\s+নম্বর|স্মারক\s+নং\.?|স্মারক|নথি\s+নম্বর|নথি|চিঠি\s+নম্বর|চিঠি|সূত্র"
        r"|પરિપત્ર\s+ક્રમાંક|પરિપત્ર\s+સંખ્યા|પરિપત્ર|સંદર્ભ|પત્ર\s+ક્રમાંક|ક્રમાંક|સંખ્યા"
        r"|சுற்றறிக்கை\s+எண்|சுற்றறிக்கை|குறிப்பு\s+எண்|குறிப்பு|கடித\s+எண்|எண்"
        r"|సర్క్యులర్\s+నంబర్|సర్క్యులర్\s+సంఖ్య|సర్క్యులర్|రిఫరెన్స్|లేఖ\s+సంఖ్య|సంఖ్య|నంబర్|క్రమ\s+సంఖ్య"
        r"|ಸುತ್ತೋಲೆ\s+ಸಂಖ್ಯೆ|ಸುತ್ತೋಲೆ|ಉಲ್ಲೇಖ|ಪತ್ರದ\s+ಸಂಖ್ಯೆ|ಸಂಖ್ಯೆ|ಕ್ರಮಾಂಕ"
        r"|സർക്കുലർ\s+നമ്പർ|സർക്കുലർ|പരാമർശം|കത്ത്\s+നമ്പർ|നമ്പർ"
        r"|ਸਰਕੂਲਰ\s+ਨੰਬਰ|ਸਰਕੂਲਰ|ਹਵਾਲਾ|ਪੱਤਰ\s+ਨੰਬਰ|ਨੰਬਰ"
        r"|ପରିପତ୍ର\s+ସଂଖ୍ୟା|ପରିପତ୍ର|ସନ୍ଦର୍ଭ|ଚିଠି\s+ନମ୍ବର|ସଂଖ୍ୟା|କ୍ରମାଙ୍କ"
        r"|سرکلر\s+نمبر|سرکلر|حوالہ|خط\s+نمبر|نمبر"
        r")\s*[:\-]?\s*)"
        r"([A-Za-z0-9\u0600-\u0D7F][A-Za-z0-9\u0600-\u0D7F/()._\-]{1,40})"
    ),
    # 2. Standalone Devanagari circular refs: शैक्ष-55/2026, िैक्ष-55/2026, शैक्ष-५५/२०२६
    re.compile(
        r"\b(?:(?:CBSE|क\s*े?\s*मा\s*मि\s*बो)/)?(?:शैक्ष|िैक्ष|शैक्षणिक|अकादमिक)-[0-9०-९]+/[0-9०-९]{4}\b"
    ),

    # RBI circular & department numbers: RBI/2026-27/299, RBI/FED/2026-27/298, RBI/2025-26/45
    re.compile(r"\bRBI/(?:[A-Z]+/)?\d{4}-\d{2}/\d+\b"),
    # RBI department refs: DOR.ORG.REC.22/21.06.050/2026-27
    re.compile(
        r"\b(?:DOR|DoR|DOS|FED)[A-Za-z.]*\.[A-Za-z.]*(?:No\.)?\d+/[\d.\-]+/\d{4}-\d{2}\b"
    ),
    # A.P. (DIR Series) Circular No. 28/2026-27
    re.compile(
        r"\bA\.P\.\s*\(DIR\s+Series\)\s*Circular\.?\s*No\.?\s*\d+(?:/\d{4}-\d{2})?\b",
        re.IGNORECASE,
    ),
    # Gazette S.O. / G.S.R. forms: S.O. 4268(E), G.S.R. 123(E)
    re.compile(r"\b(?:S\.O\.|G\.S\.R\.)\s*\d+\s*\([A-Z]\)", re.IGNORECASE),
    # Railway Board RBE No. 101/2026
    re.compile(r"\bRBE\s*No\.?\s*\d+/\d{4}\b", re.IGNORECASE),
    # CBSE & synthetic academic circulars: CBSE/Acad-67/2026, CEB/Acad-768/2026, Acad-67/2026
    re.compile(r"\b(?:(?:CBSE|CEB)/)?Acad-\d+/\d{4}\b"),
    # Synthetic & agency slash references: NFRA/2024-25/260, TCA/QoS/954/2024, RSM/2025-26/104
    re.compile(
        r"\b(?:NFRA|CEB|TCA|RSM|SEBI|TRAI|UGC|AICTE|MHA|MEA|MOD|MOF|IB|I4C)"
        r"/[A-Za-z0-9.\-]+/\d+(?:/\d{2,4})?\b"
    ),
    # Explicit "Ref. No:" / "Reference No." / "Reg. No:" / "F. No." / "File No."
    re.compile(
        r"(?:(?:Ref(?:erence)?|Reg(?:istration)?|File|Circular|Order|Letter|Notification)\s*\.?\s*No\.?|F\s*\.?\s*No\.?)"
        r"\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9/()._\-]{2,40})",
        re.IGNORECASE,
    ),
    # Standalone "No. ..." forms: No. 68/2024/GOVT, No.68/03, No. E(P&A)II/2026/PLB-1
    re.compile(
        r"\b(No\.\s*(?:[A-Za-z0-9()]+\s*)?[A-Za-z0-9()_\-]+/[A-Za-z0-9()/.\-]+)\b"
    ),
    # Plain "number/number" references following labels (No., Order No., F. No., File No., Letter No., etc.)
    # or standalone on its own line after header (e.g. 163/0224)
    re.compile(
        r"(?i)(?:"
        r"(?:(?:Order\s+No|Order|F\.?\s*No|File\s+No|Letter\s+No|Ref(?:erence)?\s*(?:No)?|Circular\s*(?:No)?|Notification\s*(?:No)?)\.?\b|\bNo\.?)\s*[:\-–—]?\s*"
        r"|(?:^|\n)\s*"
        r")"
        r"(\d{2,6}/\d{2,6})\b"
        r"(?!\s*/\s*\d)"
    ),
]

_DATE_PATTERNS: list[re.Pattern[str]] = [
    # YYYY-MM-DD
    re.compile(r"\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b"),
    # DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    re.compile(
        r"\b(?:0?[1-9]|[12]\d|3[01])[/.\\-](?:0?[1-9]|1[0-2])[/.\\-](?:19|20)\d{2}\b"
    ),
    # Month DD, YYYY (e.g., October 23, 2026)
    re.compile(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2},?\s+(?:19|20)\d{2}\b",
        re.IGNORECASE,
    ),
    # DD Month YYYY (e.g., 23 October 2026, 23 Oct, 2026)
    re.compile(
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r",?\s+(?:19|20)\d{2}\b",
        re.IGNORECASE,
    ),
]

_PHONE_RE = re.compile(
    r"(?:(?:\+91|91|0)[\-\s]?)?[6-9]\d{4}[\-\s]?\d{5}\b"
    r"|\b1800[\-\s]?\d{3}[\-\s]?\d{4}\b"
)

UPI_ID_RE = re.compile(
    r"\b[a-zA-Z0-9.\-_]{2,64}@[a-zA-Z]{2,24}\b(?!\.[a-zA-Z])",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

_URL_RE = re.compile(
    r"(?<![A-Za-z0-9@/_.\-])(?:"
    r"https?://[^\s<>\"')]+"
    r"|www\.[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?:/[^\s<>\"')]*)?"
    r"|(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:gov\.[A-Za-z]{2,3}|nic\.[A-Za-z]{2,3}|org\.in|ac\.in|res\.in|edu\.in|co\.in|net\.in|ind\.in"
    r"|gov|nic|com|org|net|in|is|co|io|me|info|biz|online|site|xyz|inc|example)"
    r"(?:/[A-Za-z0-9._~:/?#\[\]@!$&'*+,;=%\-]*)?"
    r")(?![A-Za-z0-9_.\-])",
    re.IGNORECASE,
)

_ABBREV_FIRST_LABELS = {
    "no",
    "dt",
    "dr",
    "mr",
    "mrs",
    "ms",
    "shri",
    "smt",
    "rs",
    "re",
    "sec",
    "para",
    "vol",
    "pt",
    "fig",
    "ch",
    "cl",
    "art",
    "viz",
    "etc",
    "vs",
    "ref",
    "reg",
    "sub",
    "sl",
    "sr",
    "st",
}

_DEFAULT_OFFICIAL_DOMAINS: tuple[str, ...] = (
    "bankofindia.co.in",
    "bharatpetroleum.in",
    "bsnl.co.in",
    "cbse.gov.in",
    "cbseacademic.nic.in",
    "commerce.gov.in",
    "cybercrime.gov.in",
    "delhipolice.gov.in",
    "education.gov.in",
    "egazette.gov.in",
    "employmentnews.gov.in",
    "exams.nta.ac.in",
    "factcheck.pib.gov.in",
    "finmin.gov.in",
    "gov.in",
    "hindustanpetroleum.com",
    "i4c.mha.gov.in",
    "incometax.gov.in",
    "india.gov.in",
    "indianairforce.nic.in",
    "indianarmy.nic.in",
    "indiannursingcouncil.org",
    "indianrailways.gov.in",
    "iocl.com",
    "labour.gov.in",
    "lpgvitarakchayan.in",
    "mea.gov.in",
    "meity.gov.in",
    "mha.gov.in",
    "mib.gov.in",
    "mnre.gov.in",
    "mod.gov.in",
    "moef.gov.in",
    "mohfw.gov.in",
    "mopng.gov.in",
    "morth.nic.in",
    "msde.gov.in",
    "msme.gov.in",
    "mudra.org.in",
    "mygov.in",
    "natboard.edu.in",
    "nbe.edu.in",
    "nic.in",
    "nta.ac.in",
    "parivahan.gov.in",
    "petrolpumpdealerchayan.in",
    "pib.gov.in",
    "pmkusum.mnre.gov.in",
    "powermin.gov.in",
    "rbi.org.in",
    "sachet.rbi.org.in",
    "sci.gov.in",
    "sebi.gov.in",
    "skillindiadigital.gov.in",
    "trai.gov.in",
    "ugc.gov.in",
)

_DEFAULT_FRAUDULENT_DOMAINS: tuple[str, ...] = (
    "brs.inc",
    "bsnltowerindia.com",
    "heightveda.com",
    "indraprasthagasdealer.com",
    "kbkbgov.online",
    "nchmr.com",
    "nchmrvacancy.com",
    "niyukti.org",
    "nrdrm.com",
    "nrdrmvacancy.com",
    "nrrms.com",
    "nrrmsvacancy.in",
    "petrolpump-ksk.com",
    "rashtriyavikasyojna.org",
    "sarvashikshaabyi.com",
    "sarvashikshaabhiyan.com",
)


@lru_cache(maxsize=1)
def _load_registry_domain_sets() -> tuple[frozenset[str], frozenset[str]]:
    """Load official_domains and known_fraudulent_websites from 03_issuer_registry/issuers.json."""
    official = set(_DEFAULT_OFFICIAL_DOMAINS)
    fraudulent = set(_DEFAULT_FRAUDULENT_DOMAINS)
    reg_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "dataset"
        / "03_issuer_registry"
        / "issuers.json"
    )
    if reg_path.exists():
        try:
            data = json.loads(reg_path.read_text(encoding="utf-8"))
            for issuer in data.get("issuers", []):
                for dom in issuer.get("official_domains", []):
                    official.add(dom.strip().lower().removeprefix("www."))
            for dom in data.get("known_fraudulent_websites", {}).get("domains", []):
                fraudulent.add(dom.strip().lower().removeprefix("www."))
        except Exception:
            pass
    return frozenset(official), frozenset(fraudulent)

_RUPEE_RE = re.compile(
    r"(?:₹|Rs\.?|INR|रु\.?)\s*\d[\d,]*(?:\.\d{1,2})?"
    r"(?:\s*(?:lakh|lakhs|crore|crores|thousand|लाख|करोड़))?",
    re.IGNORECASE,
)

_SUBJECT_RE = re.compile(
    r"(?im)^\s*(?:Subject|Sub|विषय)\s*[:\-–—]\s*(.+?)\s*$"
)


def strip_synthetic_watermark(text: str) -> str:
    """Remove synthetic watermark lines and partial fragments from OCR text."""
    if not text:
        return ""
    cleaned = _WATERMARK_INLINE_RE.sub("", text)
    cleaned = _WATERMARK_LINE_RE.sub("", cleaned)
    lines: list[str] = []
    for line in cleaned.splitlines():
        s = line.strip()
        # Filter isolated fragments like "SYNTHETIC -" or "- NOT A REAL DOCUMENT"
        if re.fullmatch(
            r"(?i)[-–—\s]*(?:SYNTHETIC|NOT\s+A\s+REAL|REAL\s+DOCUMENT|DETECTOR\s+TRAINING)[-–—\s]*",
            s,
        ):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = item.strip().rstrip(".,;:")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _dedupe_substring_references(refs: list[str]) -> list[str]:
    """Drop any reference number that is a substring of another reference number in ``refs``."""
    unique = _dedupe_preserve_order(refs)
    return [
        r
        for r in unique
        if not any(r != other and r in other for other in unique)
    ]


def _levenshtein_distance(a: str, b: str) -> int:
    """Compute character edit distance between ``a`` and ``b``."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _ref_prefix(ref: str) -> str:
    """Extract normalized prefix before the first digit sequence."""
    m = re.match(r"^([^\d]+)", ref.strip())
    return re.sub(r"\s+", " ", m.group(1)).strip().lower() if m else ""


def _find_near_duplicate_references(refs: list[str]) -> list[list[str]]:
    """Return pairs ``[a, b]`` of extracted references that share the same prefix and differ by 1-2 chars."""
    pairs: list[list[str]] = []
    n = len(refs)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = refs[i], refs[j]
            pref_a = _ref_prefix(a)
            pref_b = _ref_prefix(b)
            if not pref_a or pref_a != pref_b:
                continue
            dist = _levenshtein_distance(a.lower(), b.lower())
            if 1 <= dist <= 2:
                pairs.append([a, b])
    return pairs


def _normalize_hostname(url_or_domain: str) -> str:
    """Extract normalized lowercase hostname (without scheme, path, port, or leading www.)."""
    s = url_or_domain.strip()
    s = re.sub(r"^https?://", "", s, flags=re.IGNORECASE)
    s = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].split(":", 1)[0]
    s = s.lower().strip(".")
    if s.startswith("www."):
        s = s[4:]
    return s


def _is_valid_extracted_url_or_domain(raw: str) -> bool:
    """Reject false-positive domain matches on decimals, abbreviations, or reference codes."""
    if re.search(r"/\d{4}-\d{2}\b", raw):
        return False
    host = _normalize_hostname(raw)
    if "." not in host:
        return False
    labels = host.split(".")
    if any(not lbl for lbl in labels):
        return False
    first = labels[0]
    tld = labels[-1]
    if not re.search(r"[a-z]", first) or not re.fullmatch(r"[a-z]{2,10}", tld):
        return False
    if first in _ABBREV_FIRST_LABELS:
        return False
    has_scheme_or_www = raw.lower().startswith(("http://", "https://", "www."))
    has_path = "/" in re.sub(r"^https?://", "", raw, flags=re.IGNORECASE)
    if len(first) < 2 and not (has_scheme_or_www or (has_path and host == "t.me")):
        return False
    return True


def _is_suspicious_domain(url_or_domain: str) -> str | None:
    """Return the normalized domain if it is suspicious (lookalike, non-.gov.in/.nic.in gov/nic, or known fraudulent)."""
    host = _normalize_hostname(url_or_domain)
    if not host or "." not in host:
        return None
    official_domains, fraudulent_domains = _load_registry_domain_sets()

    # 1. Listed in known_fraudulent_websites
    if host in fraudulent_domains or any(
        host.endswith("." + fd) for fd in fraudulent_domains
    ):
        return host

    # Any valid official .gov.in or .nic.in domain (and exact registry domains or their subdomains) are never flagged
    if (
        host in official_domains
        or host.endswith(".gov.in")
        or host.endswith(".nic.in")
        or any(host.endswith("." + off) for off in official_domains)
    ):
        return None

    # 2. Contains "gov" or "nic" but does not end in ".gov.in" or ".nic.in"
    if "gov" in host or "nic" in host:
        return host

    # 3. Within edit distance 2 of a known official domain from 03_issuer_registry
    for off in official_domains:
        if 1 <= _levenshtein_distance(host, off) <= 2:
            return host

    return None


def extract_fields(text: str, *, strip_watermark: bool = True) -> ExtractedFields:
    """Extract reference numbers, dates, phones, emails, URLs, suspicious domains, amounts, and subject."""
    working = strip_synthetic_watermark(text) if strip_watermark else (text or "")
    if not working:
        return ExtractedFields()
    # Normalize working copy to NFC and Indic digits to ASCII for regex matching
    working = normalize_text(working, convert_digits=True)

    refs: list[str] = []
    ref_spans: list[tuple[int, int]] = []
    for pat in _REF_PATTERNS:
        for m in pat.finditer(working):
            val = m.group(1) if m.lastindex else m.group(0)
            cleaned_val = re.sub(r"\s+", " ", val).strip()
            if re.fullmatch(r"\d{1,6}/\d{1,6}", cleaned_val):
                if _is_ref_date_or_amount(cleaned_val, working, m.start(), m.end()):
                    continue
            refs.append(cleaned_val)
            ref_spans.append(m.span())

    dates: list[str] = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(working):
            dates.append(re.sub(r"\s+", " ", m.group(0)).strip())

    phones = [
        re.sub(r"\s+", " ", m.group(0)).strip() for m in _PHONE_RE.finditer(working)
    ]
    emails = [m.group(0).strip() for m in _EMAIL_RE.finditer(working)]
    upi_ids = [
        m.group(0).strip().rstrip(".,;)")
        for m in UPI_ID_RE.finditer(working)
    ]
    upi_ids = [u for u in upi_ids if u not in emails and not any(u in em for em in emails)]

    # Exclude email domains and reference number spans from URL/domain matches
    email_spans = [m.span() for m in _EMAIL_RE.finditer(working)]
    urls: list[str] = []
    for m in _URL_RE.finditer(working):
        start, end = m.span()
        if start > 0 and working[start - 1] == "@":
            continue
        if any(not (end <= es or start >= ee) for es, ee in email_spans):
            continue
        if any(not (end <= rs or start >= re_) for rs, re_ in ref_spans):
            continue
        candidate = m.group(0).strip().rstrip(".,;)")
        if _is_valid_extracted_url_or_domain(candidate):
            urls.append(candidate)

    deduped_urls = _dedupe_preserve_order(urls)
    suspicious: list[str] = []
    for u in deduped_urls:
        flagged_host = _is_suspicious_domain(u)
        if flagged_host is not None:
            suspicious.append(flagged_host)

    amounts = [
        re.sub(r"\s+", " ", m.group(0)).strip() for m in _RUPEE_RE.finditer(working)
    ]

    subject: str | None = None
    sub_match = _SUBJECT_RE.search(working)
    if sub_match:
        subject = re.sub(r"\s+", " ", sub_match.group(1)).strip().rstrip(".")

    deduped_refs = _dedupe_substring_references(refs)
    normalized_refs: list[str] = []
    all_refs: list[str] = list(deduped_refs)
    for r in deduped_refs:
        norm = normalize_reference_number(r)
        if norm:
            normalized_refs.append(norm)
            if norm not in all_refs:
                all_refs.append(norm)
    all_refs = _dedupe_preserve_order(all_refs)
    normalized_refs = _dedupe_preserve_order(normalized_refs)
    near_dupes = _find_near_duplicate_references(all_refs)

    return ExtractedFields(
        reference_numbers=all_refs,
        normalized_reference_numbers=normalized_refs,
        near_duplicate_references=near_dupes,
        dates=_dedupe_preserve_order(dates),
        phone_numbers=_dedupe_preserve_order(phones),
        emails=_dedupe_preserve_order(emails),
        upi_ids=_dedupe_preserve_order(upi_ids),
        urls=deduped_urls,
        suspicious_domains=_dedupe_preserve_order(suspicious),
        rupee_amounts=_dedupe_preserve_order(amounts),
        subject=subject,
    )
