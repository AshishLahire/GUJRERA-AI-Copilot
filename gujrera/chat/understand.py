"""Language, intent and entity detection for chat messages.

Deterministic on purpose: it runs in milliseconds on CPU, behaves the same way
every time, and can be tested. A local LLM can be added later as a fallback
router for messages these rules do not understand.
"""

from __future__ import annotations

from functools import lru_cache

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
    "promoter": ("builder", "developer", "promoter", "builders", "developers", "promoters", "બિલ્ડર", "ડેવલપર", "પ્રમોટર", "बिल्डर", "डेवलपर",
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
              "am i entitled", "if the builder", "if the promoter", "what can i do", "what should i do",
              "who will fix", "who must fix", "who will repair", "who must repair",
              "what are my options", "what are my rights",
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


PROCEDURE_WORDS = ("how do i", "how to", "how can i", "how should i", "procedure", "process for", "steps to",
                   "કેવી રીતે", "પ્રક્રિયા", "कैसे", "प्रक्रिया")


# What a RERA procedure is about; "how do I cook dal" is not one.
PROCEDURE_TOPICS = ("qpr", "quarterly", "progress report", "registration", "register", "extension", "renew",
                    "agent", "rera", "project", "promoter", "apply", "application", "file", "filing", "form",
                    "નોંધણી", "રજીસ્ટ્રેશન", "મુદત", "એજન્ટ", "અરજી", "ફાઈલ", "ફાઇલ", "ભરવ", "રેરા", "પ્રોજેક્ટ",
                    "पंजीकरण", "रजिस्ट्रेशन", "विस्तार", "एजेंट", "आवेदन", "दाखिल", "भर", "रेरा", "प्रोजेक्ट")


def asks_procedure(text_lc: str) -> bool:
    """"How do I file a QPR?": the steps the law sets, not the asker's own records."""
    return any(_has(text_lc, w) for w in PROCEDURE_WORDS) and any(_has(text_lc, w) for w in PROCEDURE_TOPICS)


def detect_intents(text_lc: str) -> set[str]:
    intents = {intent for intent, words in INTENT_WORDS.items() if any(_has(text_lc, w) for w in words)}
    if asks_procedure(text_lc):
        intents.add("legal")  # how-to questions on QPR, extension, agent registration: Act, Rules, circulars
    return intents


DISTRICT_WORDS = {
    "ahmedabad": "Ahmedabad", "અમદાવાદ": "Ahmedabad", "अहमदाबाद": "Ahmedabad",
    "surat": "Surat", "સુરત": "Surat", "सूरत": "Surat",
    "vadodara": "Vadodara", "baroda": "Vadodara", "વડોદરા": "Vadodara", "वडोदरा": "Vadodara",
    "rajkot": "Rajkot", "રાજકોટ": "Rajkot", "राजकोट": "Rajkot",
    "gandhinagar": "Gandhinagar", "ગાંધીનગર": "Gandhinagar", "गांधीनगर": "Gandhinagar",
    "bhavnagar": "Bhavnagar", "ભાવનગર": "Bhavnagar", "भावनगर": "Bhavnagar",
}


def _core(name: str | None) -> str:
    name = re.sub(r"\s+", " ", name or "")  # the registry has names with double spaces
    return re.sub(r"\s*\((?:demo|ડેમો)\)\s*$", "", name, flags=re.IGNORECASE).strip().lower()


def _spaced(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _score(variant: str, text_lc: str) -> float:
    if len(variant) < 4:
        return 0.0
    if re.search(rf"(?<![\w]){re.escape(variant)}(?![\w])", text_lc):
        return 100.0
    if len(variant) >= 8 and stem_present(variant, text_lc):
        # Every word of the name must be (nearly) a word of the question: typos pass ("mangal sqare"), but
        # "Sunrise Skyz" is not in "sunrise skyline towers".
        q_words = _WORD.findall(text_lc)
        for w in _WORD.findall(variant):
            if len(w) >= 3 and not any(fuzz.ratio(w, q) >= 80 for q in q_words):
                return 0.0
        # "RHYTHM SKY" inside "the rhythm skyline": a candidate, but below the name written in full
        return min(99.0, float(fuzz.partial_ratio(variant, text_lc)))
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
    return " ".join(_LATIN_FIX.get(w, w) for w in "".join(out).split(" "))


# English words common in project names, as Hindi and Gujarati speech-to-text spell them, after the letter
# mapping above: their sound keys differ from the English ("rejidensi" -> "rjdns", "residency" -> "rsdns").
_LATIN_FIX = {
    "rejidensi": "residency", "rejidensy": "residency", "rejidansi": "residency",
    "rejidenshi": "residency", "resijensi": "residency", "rejijensi": "residency",
    "skvayar": "square", "skvayr": "square", "skveyar": "square", "skvear": "square", "skver": "square",
    "skvar": "square", "skvair": "square",
    "haits": "heights", "haights": "heights", "haaits": "heights", "hights": "heights",
    "kvins": "queens", "kvin": "queen",
}


# Words in many project names. A name made only of these (and numbers), such as "86 Residency", is matched by
# sound only if written out in full: otherwise "બ્લૂ લગૂન રેસિડેન્સી" (a made-up "Blue Lagoon Residency") would
# be answered as the real project "86 Residency".
GENERIC_NAME_WORDS = """residency residence residences heights height towers tower homes home apartment apartments
park plaza city greens green enclave avenue complex arcade square villa villas bungalow bungalows bunglows palace
skyline sky view hub mall market point house houses nagar society township estate gardens garden residential
commercial shops shop flats flat tenament tenaments duplex rowhouse row ews lig mig plots plot business centre
center corporate hights avenue elegance paradise royal galaxy""".split()


@lru_cache(maxsize=1)
def _generic_sounds() -> frozenset[str]:
    return frozenset(sound_key(w) for w in GENERIC_NAME_WORDS)


def _sounds_contained(name: str, query_key: list[str]) -> bool:
    """All words of the name, by sound, appear in a row in the query (used for Gujarati/Hindi questions
    about names the registry has only in English). Short names are skipped to avoid false matches, and so
    are names made only of generic words and numbers."""
    nk = sound_key(name).split()
    if not nk or len("".join(nk)) < 5:
        return False
    if re.search(r"\d", name):
        return False  # the sound key drops numbers: "86 Residency" would match any "... Residency"
    if all(w in _generic_sounds() for w in nk) and len(nk) == 1:
        return False  # a one-word generic name ("Residency") is not matched by sound
    return any(query_key[i:i + len(nk)] == nk for i in range(len(query_key) - len(nk) + 1))


@dataclass
class _Entry:
    kind: str
    id: int
    label: str
    district: str
    variants: tuple[str, ...]  # lower-cased name, Gujarati name, Gujarati name in Hindi script
    core: str  # name without "(Demo)", for sound matching
    sounds: tuple[str, ...] | None  # sound key words of the English name (Gujarati/Hindi speech spells names
    # its own way: "प्लाजा" is not the registry's Gujarati "પ્લાઝા", but both sound like "plaza")
    sound_all: str = ""  # sound key of the name, for "did you mean ...?"


@dataclass
class _NameIndex:
    entries: list[_Entry]
    by_prefix: dict[str, set[int]]  # word start -> entry positions (Latin: 4 letters; Indic: 2 letters)
    by_sound: dict[str, set[int]]  # first sound-key word -> entry positions


_INDEX: dict[tuple, _NameIndex] = {}
_WORD = re.compile(r"[\w\u0900-\u097F\u0A80-\u0AFF]+")


def _prefixes(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(text):
        if w.isdigit():
            continue
        n = 2 if _INDIC.search(w) else 4
        out.add(w[:n])
    return out


def _name_index(session: Session) -> _NameIndex:
    """Names of all projects and promoters, built once per data version: with ~17,000 projects the
    question is compared only with names that share a word start, not with every name in turn."""
    from sqlalchemy import func

    bind = session.get_bind()
    key = (str(bind.url), session.scalar(select(func.count(Project.id))), session.scalar(select(func.max(Project.id))),
           session.scalar(select(func.count(Promoter.id))), session.scalar(select(func.max(Promoter.id))))
    hit = _INDEX.get(key)
    if hit:
        return hit
    entries: list[_Entry] = []
    for p in session.scalars(select(Promoter).where(Promoter.promoter_type != "unknown")):
        entries.append(_Entry("promoter", p.id, p.name, p.district,
                              (_core(p.name), _core(p.name_gu), gu_to_deva(_core(p.name_gu))), _core(p.name),
                              tuple(sound_key(_core(p.name)).split())))
    for p in session.scalars(select(Project)):
        entries.append(_Entry("project", p.id, p.name, p.district,
                              (_spaced(p.name), _spaced(p.name_gu), _spaced(gu_to_deva(p.name_gu))), _core(p.name),
                              tuple(sound_key(_core(p.name)).split())))
    by_prefix: dict[str, set[int]] = {}
    by_sound: dict[str, set[int]] = {}
    for i, e in enumerate(entries):
        e.sound_all = sound_key(e.core)
        for v in e.variants:
            for pre in _prefixes(v):
                by_prefix.setdefault(pre, set()).add(i)
        if e.sounds:
            by_sound.setdefault(e.sounds[0], set()).add(i)
    idx = _NameIndex(entries, by_prefix, by_sound)
    _INDEX.clear()
    _INDEX[key] = idx
    return idx


# Words that can sit next to a one-word project name in a question without being part of another name.
_AROUND_NAME = set("""of about in at for the is a an and or to on by from with near what when where which who how
tell me show give list details detail info information status project projects scheme society flat flats rera
gujrera number registration registered possession date completion builder promoter developer check please
ka ki ke ko me mein nu ni no na ma maa thi che chhe nā""".split()) | {
    "નું", "ની", "નો", "ના", "માં", "થી", "છે", "વિશે", "નુ", "का", "की", "के", "को", "में", "से", "है", "बारे"}


def _stands_alone(word: str, text_lc: str) -> bool:
    """A one-word name ("MEADOWS") must not be the tail or head of a longer name in the question
    ("Zenith Meadows"): its neighbours must be ordinary words, districts or the ends of the question."""
    from gujrera.analytics.reports import DISTRICT_WORDS

    words = _WORD.findall(text_lc)
    for i, w in enumerate(words):
        if w != word:
            continue
        neighbours = [words[j] for j in (i - 1, i + 1) if 0 <= j < len(words)]
        if all(n in _AROUND_NAME or n in DISTRICT_WORDS or n.isdigit() or len(n) < 3 for n in neighbours):
            return True
    return False


def find_candidates(session: Session, text_lc: str, threshold: float = FUZZY_THRESHOLD) -> list[Candidate]:
    text_lc = _spaced(text_lc)
    idx = _name_index(session)
    # Gujarati/Hindi question, English-only registry name: compare by sound.
    latin_key = sound_key(indic_to_latin(text_lc)).split() if _INDIC.search(text_lc) else []
    pool: set[int] = set()
    for pre in _prefixes(text_lc) | _prefixes(gu_to_deva(text_lc)):
        pool |= idx.by_prefix.get(pre, set())
    for k in latin_key:
        pool |= idx.by_sound.get(k, set())
    found: list[Candidate] = []
    for i in sorted(pool):
        e = idx.entries[i]
        name, gu, deva = e.variants
        score = max(_score(name, text_lc), _score(gu, text_lc), _score(deva, text_lc))
        if score < threshold and latin_key and e.sounds is not None and _sounds_contained(e.core, latin_key):
            score = threshold + 1
        if score >= threshold and len(_WORD.findall(name)) == 1 and name in _WORD.findall(text_lc) \
                and not _stands_alone(name, text_lc):
            continue  # "Zenith Meadows" is not the project called "MEADOWS"
        if score >= threshold:
            found.append(Candidate(e.kind, e.id, e.label, score, e.district))
    if found:
        best = max(c.score for c in found)
        found = [c for c in found if c.score >= best - 0.5]
        # "Bansari Skyview" names BANSARI SKYVIEW, not also the project called SKYVIEW.
        names = {c.id: _core(c.label) for c in found}
        found = [c for c in found if not any(o.id != c.id and names[c.id] != names[o.id]
                                             and re.search(rf"(?<!\w){re.escape(names[c.id])}(?!\w)", names[o.id])
                                             for o in found)]
    return sorted(found, key=lambda c: (-c.score, c.kind, c.id))


_SOUND_RULES = [(r"ph", "f"), (r"[qc]k|ck|q", "k"), (r"c(?=[eiy])", "s"), (r"c", "k"), (r"g(?=[eiy])", "j"),
                (r"z", "j"), (r"v", "w"), (r"x", "ks"), (r"h", ""), (r"[aeiouy]", ""), (r"(.)\1+", r"\1")]


@lru_cache(maxsize=65536)
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
    from rapidfuzz import process

    q = _core(query)
    if len(q) < 5:
        return []
    idx = _name_index(session)
    best: dict[int, float] = {}
    for v in range(3):  # English name, Gujarati name, Gujarati name in Hindi script: one fast batch each
        choices = [e.variants[v] if v < 2 else e.variants[2] for e in idx.entries]
        if v == 1:
            choices = [_core(c) for c in choices]
        for _, score, i in process.extract(q, choices, scorer=fuzz.ratio, score_cutoff=min_score, limit=None):
            best[i] = max(best.get(i, 0), score)
    if re.search(r"[a-z]", q):
        qk = sound_key(q)
        if qk:
            # Narrow to names whose sound key could pass, then apply the exact sound-alike rule.
            near = process.extract(qk, [e.sound_all for e in idx.entries], scorer=fuzz.partial_ratio,
                                   score_cutoff=SOUND_THRESHOLD - 10, limit=200)
            for _, _, i in near:
                if i not in best and _sound_score(q, idx.entries[i].core) >= SOUND_THRESHOLD:
                    best[i] = float(min_score)
    out = [Candidate(idx.entries[i].kind, idx.entries[i].id, idx.entries[i].label, float(s), idx.entries[i].district)
           for i, s in best.items()]
    return sorted(out, key=lambda c: (-c.score, c.kind != "project", c.id))[:limit]


@lru_cache(maxsize=1024)
def _whole_word(w: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z]){re.escape(w)}(?![a-z])")


def _leftover(text_lc: str, intents: set[str]) -> str:
    cleaned = text_lc
    for intent in intents:
        for w in INTENT_WORDS[intent]:
            if w in ("builders", "developers", "promoters"):
                continue  # part of the name: "Suvarna Builders"
            if re.fullmatch(r"[a-z ]+", w):  # whole English words only: "builder" must not leave "s" of "builders"
                cleaned = _whole_word(w).sub(" ", cleaned)
            else:
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
