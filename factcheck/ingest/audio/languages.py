"""All 22 scheduled Indian languages + English, and engine selection rules."""

from __future__ import annotations

import os
from typing import Any

from factcheck.config import get_settings

LANGUAGES: dict[str, str] = {
    "en": "English", "hi": "Hindi", "bn": "Bengali", "mr": "Marathi", "ta": "Tamil",
    "te": "Telugu", "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam", "pa": "Punjabi",
    "ur": "Urdu", "or": "Odia", "as": "Assamese", "ne": "Nepali", "sa": "Sanskrit",
    "sd": "Sindhi", "kok": "Konkani", "mai": "Maithili", "mni": "Manipuri (Meitei)",
    "brx": "Bodo", "sat": "Santali", "doi": "Dogri", "ks": "Kashmiri",
}

# Languages Whisper knows (can auto-detect and transcribe)
WHISPER_SUPPORTED: set[str] = {
    "en", "hi", "bn", "mr", "ta", "te", "gu", "kn", "ml", "pa",
    "ur", "as", "ne", "sa", "sd",
}

# Languages where Whisper is strong enough to be default
WHISPER_STRONG: set[str] = {
    "en", "hi", "mr", "ta", "ur", "pa", "ne",
}

# IndicConformer covers all 22 scheduled languages (excluding English)
INDIC_SUPPORTED: set[str] = set(LANGUAGES) - {"en"}


def get_prefer_indic_set() -> set[str]:
    cfg = get_settings()
    if not cfg.USE_INDIC_CONFORMER:
        return set()
    raw = os.getenv("PREFER_INDIC_FOR", "")
    return {c.strip() for c in raw.split(",") if c.strip()}


def language_name(code: str | None) -> str:
    return LANGUAGES.get(code or "", code or "unknown")


def choose_engine(lang: str, requested: str = "auto") -> str:
    """Return 'whisper' or 'indic' for this language."""
    cfg = get_settings()
    if requested in ("whisper", "indic"):
        if requested == "whisper" and lang not in WHISPER_SUPPORTED:
            return "indic"    # Whisper can't do this language at all
        if requested == "indic" and lang not in INDIC_SUPPORTED:
            return "whisper"  # English cannot run on IndicConformer
        return requested

    # When IndicConformer is enabled, route weak languages and unsupported languages to IndicConformer
    if cfg.USE_INDIC_CONFORMER and lang in INDIC_SUPPORTED:
        if lang in cfg.WHISPER_WEAK_LANGS or lang not in WHISPER_SUPPORTED:
            return "indic"
        prefer_indic = get_prefer_indic_set()
        if lang in prefer_indic:
            return "indic"

    if lang in WHISPER_STRONG or lang not in INDIC_SUPPORTED:
        return "whisper"
    if cfg.USE_INDIC_CONFORMER and lang in INDIC_SUPPORTED:
        return "indic"
    # When IndicConformer is off, fallback to whisper if supported, else indic
    return "whisper" if lang in WHISPER_SUPPORTED else "indic"


def language_options() -> list[dict[str, Any]]:
    """Return selectable language options for UI language dropdown."""
    return [
        {
            "code": code,
            "name": name,
            "auto_detectable": code in WHISPER_SUPPORTED,
            "default_engine": choose_engine(code),
        }
        for code, name in LANGUAGES.items()
    ]
