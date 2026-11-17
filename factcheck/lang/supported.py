"""Pramaan Language Foundation: canonical language definitions and metadata.

Source of truth for all supported languages across Pramaan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TextDirection = Literal["ltr", "rtl"]


@dataclass(frozen=True)
class LanguageInfo:
    """Metadata for a supported language."""

    code: str
    name: str  # English name
    native_name: str  # Name in native script
    script_code: str  # ISO 15924 script code or short name
    digit_range: tuple[int, int] | None  # (start_codepoint, end_codepoint) or None if uses ASCII / shared
    direction: TextDirection = "ltr"


# Canonical list of supported languages (plus hi-Latn for Hinglish)
SUPPORTED_LANGUAGES: dict[str, LanguageInfo] = {
    "en": LanguageInfo(
        code="en",
        name="English",
        native_name="English",
        script_code="Latn",
        digit_range=None,  # 0030-0039 standard ASCII
        direction="ltr",
    ),
    "hi": LanguageInfo(
        code="hi",
        name="Hindi",
        native_name="हिन्दी",
        script_code="Deva",
        digit_range=(0x0966, 0x096F),  # ०-९
        direction="ltr",
    ),
    "bn": LanguageInfo(
        code="bn",
        name="Bengali",
        native_name="বাংলা",
        script_code="Beng",
        digit_range=(0x09E6, 0x09EF),  # ০-৯
        direction="ltr",
    ),
    "mr": LanguageInfo(
        code="mr",
        name="Marathi",
        native_name="मराठी",
        script_code="Deva",
        digit_range=(0x0966, 0x096F),  # ०-९ (Devanagari digits)
        direction="ltr",
    ),
    "te": LanguageInfo(
        code="te",
        name="Telugu",
        native_name="తెలుగు",
        script_code="Telu",
        digit_range=(0x0C66, 0x0C6F),  # ౦-౯
        direction="ltr",
    ),
    "ta": LanguageInfo(
        code="ta",
        name="Tamil",
        native_name="தமிழ்",
        script_code="Taml",
        digit_range=(0x0BE6, 0x0BEF),  # ௦-௯
        direction="ltr",
    ),
    "gu": LanguageInfo(
        code="gu",
        name="Gujarati",
        native_name="ગુજરાતી",
        script_code="Gujr",
        digit_range=(0x0AE6, 0x0AEF),  # ૦-૯
        direction="ltr",
    ),
    "kn": LanguageInfo(
        code="kn",
        name="Kannada",
        native_name="ಕನ್ನಡ",
        script_code="Knda",
        digit_range=(0x0CE6, 0x0CEF),  # ೦-೯
        direction="ltr",
    ),
    "ml": LanguageInfo(
        code="ml",
        name="Malayalam",
        native_name="മലയാളം",
        script_code="Mlym",
        digit_range=(0x0D66, 0x0D6F),  # ൦-൯
        direction="ltr",
    ),
    "pa": LanguageInfo(
        code="pa",
        name="Punjabi",
        native_name="ਪੰਜਾਬੀ",
        script_code="Guru",
        digit_range=(0x0A66, 0x0A6F),  # ੦-੯
        direction="ltr",
    ),
    "or": LanguageInfo(
        code="or",
        name="Odia",
        native_name="ଓଡ଼ିଆ",
        script_code="Orya",
        digit_range=(0x0B66, 0x0B6F),  # ୦-୯
        direction="ltr",
    ),
    "ur": LanguageInfo(
        code="ur",
        name="Urdu",
        native_name="اردو",
        script_code="Arab",
        digit_range=(0x06F0, 0x06F9),  # ۰-۹ (Extended Arabic-Indic / Urdu digits; also covers 0660-0669)
        direction="rtl",
    ),
    "hi-Latn": LanguageInfo(
        code="hi-Latn",
        name="Hinglish",
        native_name="Hinglish",
        script_code="Latn",
        digit_range=None,
        direction="ltr",
    ),
}

# Tuple of all supported language codes in canonical order
SUPPORTED_LANGS: tuple[str, ...] = tuple(SUPPORTED_LANGUAGES.keys())


def get_language_info(code: str | None) -> LanguageInfo | None:
    """Look up language metadata by code (case-insensitive, normalized)."""
    if not code:
        return None
    normalized = code.strip()
    if normalized.lower() == "hi-latn" or normalized.lower() == "hinglish":
        return SUPPORTED_LANGUAGES.get("hi-Latn")
    return SUPPORTED_LANGUAGES.get(normalized.lower())


def is_rtl(code: str | None) -> bool:
    """Return True if the language uses right-to-left text direction (e.g. Urdu)."""
    info = get_language_info(code)
    return bool(info and info.direction == "rtl")
