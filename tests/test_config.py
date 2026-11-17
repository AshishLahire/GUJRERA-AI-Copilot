"""Smoke test: config imports and defaults load."""

from pathlib import Path

import pytest

from factcheck.config import Settings

SETTING_NAMES = [
    "OFFLINE_MODE",
    "OCR_ENGINE_PREFERENCE",
    "LOCAL_LLM_MODEL",
    "OLLAMA_ENABLED",
    "OLLAMA_BASE_URL",
    "VLM_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_TIMEOUT_SECONDS",
    "GEMINI_MEDIA_RESOLUTION",
    "API_DAILY_CALL_LIMIT",
    "OCR_LANGUAGES",
    "TIER1_CONFIDENCE_THRESHOLD",
    "CACHE_DB_PATH",
    "MAX_IMAGE_LONG_SIDE",
]


def test_settings_defaults_load(monkeypatch):
    # Isolate from the developer's shell environment and local .env file.
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)

    s = Settings(_env_file=None)

    assert s.OFFLINE_MODE is False
    assert s.OCR_ENGINE_PREFERENCE == "gemini_first"
    assert s.LOCAL_LLM_MODEL == "qwen3-vl:4b"
    assert s.OLLAMA_ENABLED is True
    assert s.OLLAMA_BASE_URL == "http://localhost:11434"
    assert s.VLM_MODEL == "qwen3-vl:8b"
    assert s.GEMINI_API_KEY is None
    assert s.GEMINI_MODEL == "gemini-3.5-flash-lite"
    assert s.GEMINI_TIMEOUT_SECONDS == 30
    assert s.GEMINI_MEDIA_RESOLUTION == "default"
    assert s.API_DAILY_CALL_LIMIT == 50
    assert s.OCR_LANGUAGES == ["hi", "en"]
    assert s.TIER1_CONFIDENCE_THRESHOLD == 0.80
    assert s.CACHE_DB_PATH == Path("data/cache/ocr_cache.sqlite")
    assert s.MAX_IMAGE_LONG_SIDE == 1600


@pytest.mark.parametrize("raw", ["hi,en", '["hi","en"]', ' hi , en ', '["hi", "en"]'])
def test_ocr_languages_parse_from_env(monkeypatch, raw):
    monkeypatch.setenv("OCR_LANGUAGES", raw)

    s = Settings(_env_file=None)

    assert s.OCR_LANGUAGES == ["hi", "en"]
