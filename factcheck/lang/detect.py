"""Language and script detection for any input text (OCR output, transcript, pasted message).

Two-tier lightweight offline detection:
1. Detect script and distribution by Unicode character range counts.
2. Character share distribution across scripts / languages:
   - Returns primary_language, primary_script, languages_present list with character shares.
3. If Latin script: distinguish English (en) vs Hinglish (hi-Latn) via grammatical Romanized cues.
4. If Devanagari script:
   - Check for out-of-list languages (Nepali, Konkani). If markers match or are unclear, confidence < 0.60,
     flagged as "language uncertain".
   - Disambiguate Hindi (hi) vs Marathi (mr) via characteristic grammatical markers, postpositions, and Marathi 'ळ'.
5. If Bengali script: check for Assamese specific characters (ৰ, ৱ) / markers.
6. If Arabic script: check for Sindhi / Kashmiri characters.
7. For other scripts: direct 1-to-1 mapping.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from factcheck.lang.supported import SUPPORTED_LANGUAGES, LanguageInfo, get_language_info


@dataclass(frozen=True)
class LanguageShare:
    """Share of text attributed to a language."""

    language: str  # Code e.g. "hi", "en", "mr"
    share: float  # 0.0 to 1.0 (share of analyzed characters)
    language_name: str
    script: str


@dataclass(frozen=True)
class LanguageDetectionResult:
    """Result of language and script detection on text."""

    language: str  # Primary language code e.g. "hi", "mr", "en", "hi-Latn", "ur"
    script: str  # Primary ISO script code e.g. "Deva", "Latn", "Arab", "Beng"
    confidence: float  # 0.0 to 1.0
    language_name: str  # Primary English name (e.g. "Hindi", or "language uncertain")
    native_name: str  # Name in native script
    direction: Literal["ltr", "rtl"] = "ltr"
    languages_present: list[LanguageShare] = field(default_factory=list)
    is_uncertain: bool = False
    display_badge: str | None = None  # e.g. "Hindi + English" or "Hindi" or "language uncertain"

    @property
    def primary_language(self) -> str:
        return self.language


# Unicode script character ranges: (start, end, script_code, default_lang)
_SCRIPT_RANGES: list[tuple[int, int, str, str]] = [
    (0x0900, 0x097F, "Deva", "hi"),  # Devanagari (Hindi / Marathi)
    (0x0980, 0x09FF, "Beng", "bn"),  # Bengali / Assamese
    (0x0A00, 0x0A7F, "Guru", "pa"),  # Gurmukhi (Punjabi)
    (0x0A80, 0x0AFF, "Gujr", "gu"),  # Gujarati
    (0x0B00, 0x0B7F, "Orya", "or"),  # Odia
    (0x0B80, 0x0BFF, "Taml", "ta"),  # Tamil
    (0x0C00, 0x0C7F, "Telu", "te"),  # Telugu
    (0x0C80, 0x0CFF, "Knda", "kn"),  # Kannada
    (0x0D00, 0x0D7F, "Mlym", "ml"),  # Malayalam
    (0x0600, 0x06FF, "Arab", "ur"),  # Arabic script (Urdu)
    (0x0750, 0x077F, "Arab", "ur"),  # Arabic Supplement (Urdu letters e.g. ڑ, ڈ, ں)
    (0xFB50, 0xFDFF, "Arab", "ur"),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF, "Arab", "ur"),  # Arabic Presentation Forms-B
    (0x0041, 0x005A, "Latn", "en"),  # Latin uppercase
    (0x0061, 0x007A, "Latn", "en"),  # Latin lowercase
]

# Characteristic Marathi lexical and morphological markers (Devanagari)
_MARATHI_MARKERS = frozenset({
    "आहे", "आहेत", "नाही", "नाहीत", "होते", "होती", "होता",
    "करावे", "करावा", "करावी", "याचे", "त्याचे", "झाले", "झाली",
    "झाला", "केले", "केली", "केला", "म्हणून", "सर्व", "शाळांनी",
    "विद्यार्थ्यांना", "शिक्षकांना", "कार्यालय", "शासन", "निर्णय",
    "परिपत्रक", "दिनांक", "क्रमांक", "महाराष्ट्र", "पुणे", "मुंबई",
    "येथे", "मध्ये", "कडून", "आणि", "किंवा", "तर", "पण",
    "तुमचे", "तुमचा", "तुमची", "तुमच्या", "तुम्हाला",
    "झालेले", "झालेली", "झालेला", "केलेले", "केलेली", "केलेला",
    "द्या", "पाठवा", "भरा", "करा", "घ्या", "होईल", "येईल",
    "नवीन", "पुढील", "खालील", "आज", "फक्त", "लवकर", "आता", "आत्ता",
    "आत्ताच", "वाजेपर्यंत", "वाजल्यापासून", "मिळवण्यासाठी", "टाळण्यासाठी",
    "करण्यासाठी", "तारीख", "उमेदवारांना", "पाहिल्याबद्दल", "पत्राला", "उत्तर",
})

# Suffix pattern for Marathi inflected nouns/adjectives/postpositions
_MR_INFLECTION = re.compile(
    r"[\u0900-\u097F]{2,}(?:चा|ची|चे|च्या|ला|ना|नी|ने|ून|पासून|साठी|बद्दल|नुसार|वर)$"
)

# Characteristic Hindi lexical and morphological markers (Devanagari)
_HINDI_MARKERS = frozenset({
    "है", "हैं", "नहीं", "था", "थी", "थे", "करें", "करेगा",
    "करेगी", "इसका", "उसका", "हुआ", "हुई", "हुए", "किया", "किए",
    "गया", "गई", "गए", "क्योंकि", "लेकिन", "और", "या", "सभी",
    "छात्रों", "विद्यार्थियों", "शिक्षकों", "विद्यालय", "कार्यालय",
    "आदेश", "सूचना", "निदेशालय", "बोर्ड", "द्वारा", "से", "को",
    "का", "के", "की", "में", "पर", "यह", "वह", "इस", "उस",
    "होगा", "होगी", "होगे", "रहा", "रही", "रहे", "दें", "करें",
    "आपका", "आपकी", "आपके", "हमे", "हमें", "उन्हें", "इन्हें", "कहा",
    "नोट", "मैसेज", "सबको", "भेजो",
})

# Out-of-list Devanagari language markers:
# Nepali lexical markers: छ, छन्, छैन, छैनन्, थियो, थिए, भने, गरेको, भएको, गर्नु, सबै, लाई, दिन, दिने, फैलिएको, रहेको, नेपाल, काठमाडौँ
_NEPALI_MARKERS = frozenset({
    "छ", "छन्", "छैन", "छैनन्", "थियो", "थिए", "भने", "गरेको", "भएको", "गर्नु",
    "सबै", "लाई", "बाट", "सँग", "अनि", "पनि", "हुने", "गरेका", "भएका",
    "दिने", "फैलिएको", "रहेको", "रहेका", "नेपाल", "काठमाडौँ", "काठमाडौं",
})

# Konkani / Goan Devanagari markers:
_KONKANI_MARKERS = frozenset({
    "आसा", "आसात", "ना", "नात", "जालो", "जाली", "जाले", "केलो", "केली", "केले",
    "गोय", "गोवा", "तांकां", "हांगा", "म्हणून", "अशें",
})

# Assamese markers in Bengali script:
# Assamese specific characters: ৰ (U+09F0), ৱ (U+09F1)
_ASSAMESE_CHARS = frozenset({"\u09f0", "\u09f1"})
_ASSAMESE_MARKERS = frozenset({
    "আছে", "নাই", "হৈছে", "কৰা", "কৰি", "অসম", "নহয়", "বুলি", "হলে",
})

# Non-Urdu Arabic script markers (Sindhi, Kashmiri)
# Note: گ (0x06AF) is standard Urdu/Persian Gaf and is NOT exclusively Sindhi.
# Exclusively Sindhi letters: ٻ (067B), ڄ (0684), ڃ (0683), ڱ (0680), ڻ (06BB), ٽ (067D), ٺ (067F), ڦ (06A6)
_SINDHI_EXCLUSIVES = frozenset({
    "\u067b", "\u0684", "\u0683", "\u0680", "\u06bb", "\u067d", "\u067f", "\u06a6",
})
# Exclusively Kashmiri letters: ؠ (0620), ۄ (06C4), ؽ (06FD)
_KASHMIRI_EXCLUSIVES = frozenset({
    "\u0620", "\u06c4", "\u06fd",
})

# Hinglish function words / grammatical markers in Latin text
_HINGLISH_GRAMMAR_WORDS = frozenset({
    "hai", "hain", "ho", "raha", "rahi", "rahe",
    "karo", "karein", "karna", "kiya", "kiye", "gaya", "gayi", "gaye",
    "hoga", "hogi", "hoge", "nahi", "nahin", "mat", "bhi", "aur",
    "par", "pe", "se", "ko", "ka", "ke", "ki", "kya", "kyun",
    "kaise", "kab", "kahan", "lekin", "magar", "toh", "ab",
    "bhai", "sab", "sabhi", "aaj", "kal", "suno", "dekho", "bhejo",
    "paisa", "paise", "aapka", "aapki", "aapke", "apna", "apne", "apni",
    "humara", "tumhara", "neeche", "warna", "aaya", "aayi", "aaye",
    "milega", "milegi", "milenge", "badhai", "khushkhabri", "bas",
    "rupay", "baje", "mehenga", "baad", "sach", "chupa", "turant",
})

_INDIC_LOAN_WORDS = frozenset({
    "yojana", "sarkari", "suchna", "pariksha", "pan", "aadhaar", "crore", "lakh", "rupees", "paisa"
})

_WORD_SPLIT_RE = re.compile(r"[\s\.,;:!?'\"()\[\]{}\-–—/\\।]+", re.UNICODE)


def _count_scripts(text: str) -> dict[str, int]:
    """Count characters per script code in text."""
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for start, end, script, _ in _SCRIPT_RANGES:
            if start <= cp <= end:
                counts[script] = counts.get(script, 0) + 1
                break
    return counts


def _detect_devanagari_language(text: str) -> tuple[str, float, bool]:
    """Distinguish Hindi (hi) vs Marathi (mr) or out-of-list (Nepali/Konkani).

    Returns:
        (language_code, confidence, is_uncertain)
    """
    tokens = [t.strip(".,:;!?-\"\'()[]{}।") for t in text.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return "hi", 0.70, False

    # 1. Check for out-of-list Devanagari languages: Nepali or Konkani
    # Uniquely Nepali postpositions / inflection: 'लाई', 'ले' (on non-Hindi stems), 'को' (on non-Hindi stems)
    ne_hits = sum(1 for t in tokens if t in _NEPALI_MARKERS)
    if "विद्यार्थीलाई" in text or "फैलिएको" in text or "छ।" in text or "छैन" in text:
        ne_hits += 2
    for t in tokens:
        if t.endswith("लाई") and len(t) >= 4:
            ne_hits += 1
        if t.endswith("एको") and len(t) >= 4:  # e.g. फैलिएको, गरेको, भएको
            ne_hits += 1

    ko_hits = sum(1 for t in tokens if t in _KONKANI_MARKERS)

    # 2. Hindi vs Marathi scoring
    mr_score = 0.0
    hi_score = 0.0

    for t in tokens:
        if t in _MARATHI_MARKERS:
            mr_score += 2.0
        if t in _HINDI_MARKERS:
            hi_score += 2.0
        if _MR_INFLECTION.match(t):
            if any(t.endswith(sfx) for sfx in ["चा", "ची", "चे", "च्या", "पासून", "साठी", "बद्दल", "नुसार"]):
                mr_score += 1.5
            elif any(t.endswith(sfx) for sfx in ["ना", "नी", "ून", "वर"]):
                mr_score += 0.8

    # Specific Marathi unique character: ळ (U+0933)
    l_char_count = text.count("\u0933")
    mr_score += l_char_count * 3.0

    if (ne_hits >= 2 or ko_hits >= 2) and (hi_score < 4.0 and mr_score < 4.0):
        # Definite Nepali or Konkani: set confidence below 0.6 and flag uncertain
        return "hi", 0.45, True

    if mr_score > hi_score:
        conf = min(0.95, 0.65 + 0.08 * mr_score)
        return "mr", round(conf, 2), False
    elif hi_score > mr_score:
        conf = min(0.95, 0.65 + 0.08 * hi_score)
        return "hi", round(conf, 2), False

    # If both scores are 0 or tied and text has some tokens, check if markers are unclear
    if len(tokens) >= 5 and mr_score == 0 and hi_score == 0:
        return "hi", 0.50, True

    return "hi", 0.70, False


def _detect_latin_language(text: str) -> tuple[str, float]:
    """Distinguish English (en) vs Hinglish (hi-Latn) in Latin text."""
    raw_words = [re.sub(r"[^a-zA-Z]", "", w).lower() for w in text.split()]
    words = [w for w in raw_words if len(w) >= 2]
    if not words:
        return "en", 0.85

    gram_hits = sum(1 for w in words if w in _HINGLISH_GRAMMAR_WORDS)
    loan_hits = sum(1 for w in words if w in _INDIC_LOAN_WORDS)
    ratio = (gram_hits + 0.5 * loan_hits) / len(words)

    # Hinglish requires actual grammatical markers (e.g. verbs, postpositions)
    if gram_hits >= 2 or (gram_hits >= 1 and (gram_hits / len(words)) >= 0.07):
        conf = min(0.95, 0.65 + ratio * 0.5)
        return "hi-Latn", round(conf, 2)
    return "en", 0.85


def _check_out_of_list_script(text: str, script: str) -> tuple[bool, float]:
    """Check if script text matches out-of-list languages (Assamese, Sindhi, Kashmiri)."""
    if script == "Beng":
        # Check for Assamese chars (ৰ, ৱ) or lexical markers
        if any(ch in _ASSAMESE_CHARS for ch in text):
            return True, 0.45
        tokens = [t.strip(".,:;!?-\"\'()[]{}।") for t in text.split()]
        if any(t in _ASSAMESE_MARKERS for t in tokens):
            return True, 0.48
    elif script == "Arab":
        # Check for exclusively Sindhi or Kashmiri characters
        if any(ch in _SINDHI_EXCLUSIVES for ch in text):
            return True, 0.45
        if any(ch in _KASHMIRI_EXCLUSIVES for ch in text):
            return True, 0.45

    return False, 0.90


def detect_language(text: str | None) -> LanguageDetectionResult:
    """Detect primary language, script, character share distribution, and confidence.

    Handles:
    - Multilingual character shares (e.g. Hindi 70%, English 30%)
    - Mixed-language badge formatting ("Hindi + English" when secondary >= 20%)
    - Out-of-list language uncertainty (Nepali, Konkani, Assamese, Sindhi, Kashmiri)
      setting confidence < 0.6 and label "language uncertain".
    """
    if not text or not text.strip():
        en_info = SUPPORTED_LANGUAGES["en"]
        return LanguageDetectionResult(
            language="en",
            script="Latn",
            confidence=0.50,
            language_name=en_info.name,
            native_name=en_info.native_name,
            direction=en_info.direction,
            languages_present=[LanguageShare("en", 1.0, en_info.name, "Latn")],
            is_uncertain=False,
            display_badge=en_info.name,
        )

    norm_text = unicodedata.normalize("NFC", text.strip())
    script_counts = _count_scripts(norm_text)

    if not script_counts:
        en_info = SUPPORTED_LANGUAGES["en"]
        return LanguageDetectionResult(
            language="en",
            script="Latn",
            confidence=0.50,
            language_name=en_info.name,
            native_name=en_info.native_name,
            direction=en_info.direction,
            languages_present=[LanguageShare("en", 1.0, en_info.name, "Latn")],
            is_uncertain=False,
            display_badge=en_info.name,
        )

    total_script_chars = sum(script_counts.values())

    # Map each script present to its detected language code and calculate character shares
    script_lang_map: dict[str, tuple[str, float, bool]] = {}

    for scr, count in script_counts.items():
        if scr == "Deva":
            l_code, l_conf, unc = _detect_devanagari_language(norm_text)
            script_lang_map[scr] = (l_code, l_conf, unc)
        elif scr == "Latn":
            l_code, l_conf = _detect_latin_language(norm_text)
            script_lang_map[scr] = (l_code, l_conf, False)
        elif scr == "Beng":
            is_assamese, conf_val = _check_out_of_list_script(norm_text, "Beng")
            script_lang_map[scr] = ("bn", conf_val, is_assamese)
        elif scr == "Arab":
            is_out, conf_val = _check_out_of_list_script(norm_text, "Arab")
            script_lang_map[scr] = ("ur", conf_val, is_out)
        elif scr == "Telu":
            script_lang_map[scr] = ("te", 0.92, False)
        elif scr == "Taml":
            script_lang_map[scr] = ("ta", 0.92, False)
        elif scr == "Gujr":
            script_lang_map[scr] = ("gu", 0.92, False)
        elif scr == "Knda":
            script_lang_map[scr] = ("kn", 0.92, False)
        elif scr == "Mlym":
            script_lang_map[scr] = ("ml", 0.92, False)
        elif scr == "Guru":
            script_lang_map[scr] = ("pa", 0.92, False)
        elif scr == "Orya":
            script_lang_map[scr] = ("or", 0.92, False)
        else:
            script_lang_map[scr] = ("en", 0.50, False)

    # Build languages_present list with shares
    lang_shares_dict: dict[str, dict] = {}
    for scr, count in script_counts.items():
        l_code, _, _ = script_lang_map[scr]
        share = count / max(total_script_chars, 1)
        if l_code not in lang_shares_dict:
            info = get_language_info(l_code) or SUPPORTED_LANGUAGES["en"]
            lang_shares_dict[l_code] = {
                "language": l_code,
                "share": 0.0,
                "language_name": info.name,
                "script": scr,
            }
        lang_shares_dict[l_code]["share"] += share

    # Sort languages_present descending by share
    languages_present = [
        LanguageShare(
            language=v["language"],
            share=round(v["share"], 3),
            language_name=v["language_name"],
            script=v["script"],
        )
        for v in sorted(lang_shares_dict.values(), key=lambda x: x["share"], reverse=True)
    ]

    # Dominant language & script
    dominant_script, dom_count = max(script_counts.items(), key=lambda kv: kv[1])
    dominant_lang_code, script_conf, is_uncertain = script_lang_map[dominant_script]

    script_ratio = dom_count / max(total_script_chars, 1)

    if is_uncertain:
        final_confidence = min(0.55, script_conf)
        lang_name = "language uncertain"
        native_name = "अज्ञात"
    else:
        final_confidence = round(min(0.98, script_ratio * script_conf), 2)
        info = get_language_info(dominant_lang_code) or SUPPORTED_LANGUAGES["en"]
        lang_name = info.name
        native_name = info.native_name

    primary_info = get_language_info(dominant_lang_code) or SUPPORTED_LANGUAGES["en"]

    # Construct badge display string:
    # "Show 'Hindi + English' in the UI badge when the secondary language is over 20%"
    # Or "language uncertain" when text could be outside SUPPORTED_LANGS or markers are unclear (is_uncertain)
    if is_uncertain:
        display_badge = "language uncertain"
    elif len(languages_present) >= 2 and languages_present[1].share >= 0.20:
        p_name = languages_present[0].language_name
        s_name = languages_present[1].language_name
        display_badge = f"{p_name} + {s_name}"
    elif final_confidence < 0.60:
        display_badge = "language uncertain"
    else:
        display_badge = lang_name

    return LanguageDetectionResult(
        language=dominant_lang_code,
        script=dominant_script,
        confidence=final_confidence,
        language_name=lang_name,
        native_name=native_name,
        direction=primary_info.direction,
        languages_present=languages_present,
        is_uncertain=is_uncertain,
        display_badge=display_badge,
    )
