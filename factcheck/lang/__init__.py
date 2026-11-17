"""Pramaan Language Package.

Single source of truth for language metadata, script detection, and Unicode/digit normalization.
"""

from __future__ import annotations

from factcheck.lang.detect import LanguageDetectionResult, detect_language
from factcheck.lang.normalize import INDIC_DIGITS_TRANS, normalize_digits, normalize_text
from factcheck.lang.supported import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_LANGS,
    LanguageInfo,
    get_language_info,
    is_rtl,
)

__all__ = [
    "SUPPORTED_LANGUAGES",
    "SUPPORTED_LANGS",
    "LanguageInfo",
    "LanguageDetectionResult",
    "get_language_info",
    "is_rtl",
    "detect_language",
    "normalize_digits",
    "normalize_text",
    "INDIC_DIGITS_TRANS",
]
