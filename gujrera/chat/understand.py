"""Language, intent and entity detection for chat messages.

Deterministic on purpose: it runs in milliseconds on CPU, behaves the same way
every time, and can be tested. A local LLM can be added later as a fallback
router for messages these rules do not understand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from factcheck.lang.normalize import normalize_digits
from gujrera.db.models import Project, Promoter
from gujrera.trust.checks import stem_present
from gujrera.trust.rera_number import ReraNumber, find_rera_numbers

# Romanised Gujarati / Hindi words, for "Gujlish" and "Hinglish" input.
ROMAN_GU = {"che", "chhe", "kyare", "malse", "maļse", "shu", "su", "nu", "ni", "kevi", "vishe", "mate", "kem"}
ROMAN_HI = {"hai", "kab", "milega", "kya", "kaun", "kaise", "batao", "ke", "ka", "ki", "mein", "hain", "bare"}

INTENT_WORDS: dict[str, tuple[str, ...]] = {
    "possession": ("possession", "handover", "hand over", "completion", "complete", "completed", "ready",
                   "when will", "deadline", "પઝેશન", "કબજો", "ક્યારે", "પૂર્ણ", "kyare", "malse",
                   "कब्जा", "कब्ज़ा", "पज़ेशन", "पजेशन", "कब", "पूरा", "kab", "milega"),
    "promoter": ("builder", "developer", "promoter", "બિલ્ડર", "ડેવલપર", "પ્રમોટર", "बिल्डर", "डेवलपर",
                 "प्रमोटर", "track record", "history"),
    "complaint_file": ("file a complaint", "register a complaint", "lodge", "my complaint", "my complaints", "complaint status",
                       "track my complaint", "track complaint", "complain", "raise a complaint",
                       "ફરિયાદ નોંધ", "મારી ફરિયાદ", "ફરિયાદ કરવી", "ફરિયાદની સ્થિતિ",
                       "शिकायत दर्ज", "मेरी शिकायत", "शिकायत करनी", "शिकायत की स्थिति"),
    "complaints": ("complaint", "complaints", "ફરિયાદ", "शिकायत"),
    "trust": ("genuine", "fake", "real or", "legit", "verify", "is this", "scam", "fraud", "check this",
              "સાચું", "સાચો", "નકલી", "ખોટું", "असली", "नकली", "फर्जी", "सही है"),
    "legal": ("section", "rule", "rules", "rera act", "the act", "law", "legal", "legally", "my rights",
              "rights of", "entitled", "allowed to", "can the builder", "can a builder", "can the promoter",
              "can a promoter", "is it legal", "what does rera", "rera say", "obligation", "can i get",
              "am i entitled", "if the builder", "if the promoter", "what can i do",
              # interest / refund for delay: a law question (Section 18) unless a project is named,
              # in which case the chat calculates it instead
              "interest for", "get interest", "refund", "money back", "વ્યાજ", "રિફંડ", "ब्याज", "रिफंड",
              "કલમ", "નિયમ", "કાયદો", "કાયદા", "અધિકાર", "મને મળે", "મળી શકે", "લઈ શકે", "કરી શકે",
              "धारा", "नियम", "कानून", "अधिकार", "हक", "मिल सकता", "मिलेगा क्या", "सकता है", "क्या मुझे"),
    "agent": ("agent", "broker", "એજન્ટ", "દલાલ", "एजेंट", "दलाल"),
    "greeting": ("hello", "hi", "namaste", "namaskar", "help", "નમસ્તે", "મદદ", "नमस्ते", "मदद"),
}
STOPWORDS = {
    "the", "a", "an", "of", "for", "about", "tell", "me", "what", "is", "are", "when", "will", "i", "get",
    "my", "in", "on", "project", "projects", "please", "show", "give", "details", "info", "information",
    "status", "how", "many", "does", "do", "have", "has", "any", "who", "which", "can", "you", "flat",
    "flats", "by", "this", "that", "it", "to", "and", "or", "with", "from", "record", "check",
}


# Words that suggest the user is naming a project, builder or agent.
NAME_HINTS = (
    "residency", "heights", "towers", "tower", "greens", "park", "avenue", "enclave", "plaza", "homes",
    "apartments", "developers", "developer", "builders", "builder", "infra", "realty", "constructions",
    "about", "વિશે", "ટાવર્સ", "રેસિડેન્સી", "હાઇટ્સ", "ડેવલપર્સ", "બિલ્ડર્સ", "बारे", "टावर्स", "रेजिडेंसी",
    "डेवलपर्स", "बिल्डर्स",
)


@dataclass
class Candidate:
    kind: str  # project | promoter
    id: int
    label: str
    score: float
    district: str


@dataclass
class Understanding:
    lang: str
    intents: set[str]
    project_numbers: list[ReraNumber] = field(default_factory=list)
    agent_numbers: list[ReraNumber] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    districts: set[str] = field(default_factory=set)
    leftover: str = ""
    looks_like_ad: bool = False
    names_something: bool = False


def detect_language(text: str) -> str:
    gu = sum(1 for ch in text if "઀" <= ch <= "૿")
    hi = sum(1 for ch in text if "ऀ" <= ch <= "ॿ")
    if gu or hi:
        return "gu" if gu >= hi else "hi"
    words = set(re.findall(r"[a-z]+", text.lower()))
    rg, rh = len(words & ROMAN_GU), len(words & ROMAN_HI)
    if max(rg, rh) >= 2:
        return "gu" if rg > rh else "hi"
    return "en"


def _has(text_lc: str, phrase: str) -> bool:
    if re.fullmatch(r"[a-z ]+", phrase):
        return re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", text_lc) is not None
    return phrase in text_lc


def detect_intents(text_lc: str) -> set[str]:
    return {intent for intent, words in INTENT_WORDS.items() if any(_has(text_lc, w) for w in words)}


DISTRICT_WORDS = {
    "ahmedabad": "Ahmedabad", "અમદાવાદ": "Ahmedabad", "अहमदाबाद": "Ahmedabad",
    "surat": "Surat", "સુરત": "Surat", "सूरत": "Surat",
    "vadodara": "Vadodara", "baroda": "Vadodara", "વડોદરા": "Vadodara", "वडोदरा": "Vadodara",
    "rajkot": "Rajkot", "રાજકોટ": "Rajkot", "राजकोट": "Rajkot",
    "gandhinagar": "Gandhinagar", "ગાંધીનગર": "Gandhinagar", "गांधीनगर": "Gandhinagar",
    "bhavnagar": "Bhavnagar", "ભાવનગર": "Bhavnagar", "भावनगर": "Bhavnagar",
}


def _core(name: str | None) -> str:
    return re.sub(r"\s*\((?:demo|ડેમો)\)\s*$", "", name or "", flags=re.IGNORECASE).strip().lower()


def _score(variant: str, text_lc: str) -> float:
    if len(variant) < 4:
        return 0.0
    if re.search(rf"(?<![\w]){re.escape(variant)}(?![\w])", text_lc):
        return 100.0
    if len(variant) >= 8 and stem_present(variant, text_lc):
        return float(fuzz.partial_ratio(variant, text_lc))
    return 0.0


# Fuzzy matching only forgives small typos ("Mangal Sqare"). A lower threshold let unknown names
# such as "Quasar Heights" match a real project ("Kesar Heights"), which is worse than "not found".
FUZZY_THRESHOLD = 94


# Gujarati and Devanagari Unicode blocks are parallel (U+0A80.. and U+0900..): a Gujarati name maps letter for
# letter to Hindi script (મંગલ સ્ક્વેર -> मंगल स्क्वेर), so names typed in Hindi match the registry's Gujarati names.
_GU_START, _GU_END, _GU_TO_DEVA = 0x0A80, 0x0AFF, 0x0A80 - 0x0900


def gu_to_deva(text: str | None) -> str:
    return "".join(chr(ord(ch) - _GU_TO_DEVA) if _GU_START <= ord(ch) <= _GU_END else ch for ch in (text or ""))


# Rough Hindi-script -> Latin letters, only for matching names (Gujarati is first mapped to Hindi script).
# Public GUJRERA records name projects in English only, so "બંસરી સ્કાયવ્યુ" must find "BANSARI SKYVIEW".
_DEVA_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
}
_DEVA_VOWELS = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri", "ए": "e", "ऐ": "ai",
                "ओ": "o", "औ": "au", "ऍ": "e", "ऑ": "o"}
_DEVA_MATRAS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o",
                "ौ": "au", "ॅ": "e", "ॉ": "o"}
_VIRAMA, _NUKTA = "्", "़"
_INDIC = re.compile(r"[ऀ-ॿ઀-૿]")


def indic_to_latin(text: str | None) -> str:
    """'બંસરી સ્કાયવ્યુ' -> 'bansari skayvyu'. Approximate; compare with sound_key, never show to users."""
    s = gu_to_deva(text)
    out: list[str] = []
    for i, ch in enumerate(s):
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if nxt == _NUKTA:
            nxt = s[i + 2] if i + 2 < len(s) else ""
        if ch in _DEVA_CONS:
            out.append({"ज": "z", "फ": "f"}.get(ch, _DEVA_CONS[ch]) if s[i + 1:i + 2] == _NUKTA else _DEVA_CONS[ch])
            if nxt not in _DEVA_MATRAS and nxt != _VIRAMA and nxt and not nxt.isspace() and nxt in _DEVA_CONS.keys() | {"ं", "ँ", "ः"}:
                out.append("a")  # inherent vowel inside a word; dropped at the end of a word
        elif ch in _DEVA_VOWELS:
            out.append(_DEVA_VOWELS[ch])
        elif ch in _DEVA_MATRAS:
            out.append(_DEVA_MATRAS[ch])
        elif ch in ("ं", "ँ"):
            out.append("n")
        elif ch == "ः":
            out.append("h")
        elif ch in (_VIRAMA, _NUKTA):
            continue
        else:
            out.append(ch)
    return "".join(out)


def _sounds_contained(name: str, query_key: list[str]) -> bool:
    """All words of the name, by sound, appear in a row in the query (used for Gujarati/Hindi questions
    about names the registry has only in English). Short names are skipped to avoid false matches."""
    nk = sound_key(name).split()
    if not nk or len("".join(nk)) < 5:
        return False
    return any(query_key[i:i + len(nk)] == nk for i in range(len(query_key) - len(nk) + 1))


def find_candidates(session: Session, text_lc: str, threshold: float = FUZZY_THRESHOLD) -> list[Candidate]:
    found: list[Candidate] = []
    # Gujarati/Hindi question, English-only registry name: compare by sound.
    latin_key = sound_key(indic_to_latin(text_lc)).split() if _INDIC.search(text_lc) else []
    for p in session.scalars(select(Promoter).where(Promoter.promoter_type != "unknown")):
        score = max(_score(_core(p.name), text_lc), _score(_core(p.name_gu), text_lc),
                    _score(gu_to_deva(_core(p.name_gu)), text_lc))
        if score < threshold and latin_key and not p.name_gu and _sounds_contained(_core(p.name), latin_key):
            score = threshold + 1
        if score >= threshold:
            found.append(Candidate("promoter", p.id, p.name, score, p.district))
    for p in session.scalars(select(Project)):
        score = max(_score(p.name.lower(), text_lc), _score((p.name_gu or "").lower(), text_lc),
                    _score(gu_to_deva(p.name_gu).lower(), text_lc))
        if score < threshold and latin_key and not p.name_gu and _sounds_contained(_core(p.name), latin_key):
            score = threshold + 1
        if score >= threshold:
            found.append(Candidate("project", p.id, p.name, score, p.district))
    if found:
        best = max(c.score for c in found)
        found = [c for c in found if c.score >= best - 0.5]
    return sorted(found, key=lambda c: (-c.score, c.kind, c.id))


_SOUND_RULES = [(r"ph", "f"), (r"[qc]k|ck|q", "k"), (r"c(?=[eiy])", "s"), (r"c", "k"), (r"g(?=[eiy])", "j"),
                (r"z", "j"), (r"v", "w"), (r"x", "ks"), (r"h", ""), (r"[aeiouy]", ""), (r"(.)\1+", r"\1")]


def sound_key(text: str) -> str:
    """Consonant skeleton of romanised words, so speech-to-text spellings of Gujarati names line up:
    "Mongol arcade" / "Mangal Arcade" -> "mngl rkd", "Gerner" / "Girnar" -> "jrnr", "sovarna" / "Suvarna"
    -> "swrn". Only for Latin script; returns "" otherwise."""
    words = re.findall(r"[a-z]+", text.lower())
    out = []
    for w in words:
        for pat, rep in _SOUND_RULES:
            w = re.sub(pat, rep, w)
        if w:
            out.append(w)
    return " ".join(out)


def _sound_score(query: str, name: str) -> float:
    """Best sound-alike match of the name against same-length word windows of the query."""
    n = sound_key(name)
    words = sound_key(query).split()
    if len(n.replace(" ", "")) < 4 or not words:
        return 0.0
    k = len(n.split())
    first = n.split()[0]
    best = 0.0
    for size in {max(1, k - 1), k, k + 1}:
        for i in range(max(1, len(words) - size + 1)):
            window = words[i:i + size]
            # The first word is the distinctive one ("Aangan" in "Aangan Residency"); it must start with the
            # same sound, so "lagoon residency" is not offered "Aangan Residency".
            if window[0][0] != first[0]:
                continue
            best = max(best, fuzz.ratio(" ".join(window), n))
    return best


SOUND_THRESHOLD = 86


def suggest_names(session: Session, query: str, min_score: float = 85, limit: int = 3) -> list[Candidate]:
    """Registry names close to an unmatched name, for "did you mean ...?" (never answered automatically).
    Spelling distance catches typos; for Latin script a sound-alike comparison also catches names that
    speech-to-text wrote the way they sound ("Mongol arcade" for Mangal Arcade)."""
    q = _core(query)
    if len(q) < 5:
        return []
    latin = re.search(r"[a-z]", q) is not None
    out: list[Candidate] = []
    for p in session.scalars(select(Project)):
        score = max(fuzz.ratio(q, p.name.lower()), fuzz.ratio(q, (p.name_gu or "").lower()),
                    fuzz.ratio(q, gu_to_deva(p.name_gu)))
        if latin and score < min_score and _sound_score(q, p.name) >= SOUND_THRESHOLD:
            score = min_score
        if score >= min_score:
            out.append(Candidate("project", p.id, p.name, float(score), p.district))
    for p in session.scalars(select(Promoter)):
        score = max(fuzz.ratio(q, _core(p.name)), fuzz.ratio(q, _core(p.name_gu)), fuzz.ratio(q, gu_to_deva(_core(p.name_gu))))
        if latin and score < min_score and _sound_score(q, _core(p.name)) >= SOUND_THRESHOLD:
            score = min_score
        if score >= min_score:
            out.append(Candidate("promoter", p.id, p.name, float(score), p.district))
    return sorted(out, key=lambda c: -c.score)[:limit]


def _leftover(text_lc: str, intents: set[str]) -> str:
    cleaned = text_lc
    for intent in intents:
        for w in INTENT_WORDS[intent]:
            cleaned = cleaned.replace(w, " ")
    words = [w for w in re.findall(r"[\w઀-૿ऀ-ॿ]+", cleaned)
             if w not in STOPWORDS and w not in ROMAN_GU and w not in ROMAN_HI]
    return " ".join(words)[:60].strip()


def understand(session: Session, message: str) -> Understanding:
    text = normalize_digits(message or "")
    text_lc = re.sub(r"\s+", " ", text.lower()).strip()
    numbers = find_rera_numbers(text)
    intents = detect_intents(text_lc)
    u = Understanding(
        lang=detect_language(text),
        intents=intents,
        project_numbers=[n for n in numbers if n.kind == "project"],
        agent_numbers=[n for n in numbers if n.kind == "agent"],
        districts={d for k, d in DISTRICT_WORDS.items() if _has(text_lc, k)},
        looks_like_ad=len(text) > 140 or text.count("\n") >= 2,
        names_something=any(_has(text_lc, h) for h in NAME_HINTS)
        or re.search(r"(?<=\s)[A-Z][a-z]+", text) is not None,
    )
    if not numbers:
        u.candidates = find_candidates(session, text_lc)
        u.leftover = _leftover(text_lc, intents)
    return u
