"""Tests for fully offline mode (OFFLINE_MODE=True).

Asserts that no Gemini calls or network requests to Google GenAI are ever made.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from factcheck.claims.extractor import _call_gemini_claim_llm, extract_claim
from factcheck.config import Settings
from factcheck.extract.ocr.engines import run_gemini_fallback
from factcheck.extract.ocr.runner import run_ocr


def _make_dummy_image(path: Path) -> bytes:
    im = Image.new("RGB", (100, 50), color=(255, 255, 255))
    im.save(path, format="PNG")
    return path.read_bytes()


def test_offline_mode_direct_gemini_ocr_raises():
    settings = Settings(OFFLINE_MODE=True, GEMINI_API_KEY="dummy-key")
    with pytest.raises(RuntimeError, match="Gemini OCR calls are blocked because OFFLINE_MODE=True"):
        run_gemini_fallback(b"fake_image_bytes", settings=settings)


def test_offline_mode_direct_gemini_claim_raises():
    settings = Settings(OFFLINE_MODE=True, GEMINI_API_KEY="dummy-key")
    with pytest.raises(RuntimeError, match="Gemini claim extraction calls are blocked because OFFLINE_MODE=True"):
        _call_gemini_claim_llm("Some OCR text", settings=settings)


def test_offline_mode_run_ocr_zero_gemini_calls(tmp_path: Path, monkeypatch):
    """Even if allow_gemini_fallback=True is passed, offline mode forces fallback off and never calls Gemini."""
    img_path = tmp_path / "offline_test.png"
    _make_dummy_image(img_path)

    settings = Settings(
        OFFLINE_MODE=True,
        OCR_ENGINE_PREFERENCE="qwen_first",
        OLLAMA_ENABLED=True,
        GEMINI_API_KEY="dummy-key",
        CACHE_DB_PATH=tmp_path / "cache.sqlite",
    )

    # Mock Ollama VLM to return valid OCR text (text, engine, error)
    mock_ollama_vlm = MagicMock(return_value=("Government of India\nCircular Ref: ABC/123/2026\nOfficial Notice", "ollama:qwen3-vl:4b", None))
    monkeypatch.setattr("factcheck.extract.ocr.runner.run_ollama_vlm", mock_ollama_vlm)

    # Mock Gemini fallback to raise if ever called
    mock_gemini = MagicMock(side_effect=AssertionError("Gemini fallback must NEVER be called in offline mode"))
    monkeypatch.setattr("factcheck.extract.ocr.runner.run_gemini_fallback", mock_gemini)

    res = run_ocr(img_path, allow_gemini_fallback=True, settings=settings)

    assert res.valid is True
    assert "ABC/123/2026" in res.final_text
    assert mock_ollama_vlm.called
    assert mock_gemini.call_count == 0


def test_offline_mode_ocr_failure_does_not_call_gemini(tmp_path: Path, monkeypatch):
    """If local engine fails/returns invalid, in offline mode Gemini fallback must still NOT be called."""
    img_path = tmp_path / "offline_fail.png"
    _make_dummy_image(img_path)

    settings = Settings(
        OFFLINE_MODE=True,
        OCR_ENGINE_PREFERENCE="qwen_first",
        OLLAMA_ENABLED=True,
        GEMINI_API_KEY="dummy-key",
        CACHE_DB_PATH=tmp_path / "cache.sqlite",
    )

    # Mock local engine returning invalid short text (text, engine, error)
    mock_ollama_vlm = MagicMock(return_value=("short", "ollama:qwen3-vl:4b", None))
    monkeypatch.setattr("factcheck.extract.ocr.runner.run_ollama_vlm", mock_ollama_vlm)

    mock_gemini = MagicMock(side_effect=AssertionError("Gemini fallback must NEVER be called in offline mode"))
    monkeypatch.setattr("factcheck.extract.ocr.runner.run_gemini_fallback", mock_gemini)

    res = run_ocr(img_path, allow_gemini_fallback=True, settings=settings)

    assert res.valid is False
    assert mock_gemini.call_count == 0


def test_offline_mode_extract_claim_zero_gemini_calls(tmp_path: Path, monkeypatch):
    """In offline mode, claim extraction uses Ollama and never calls Gemini."""
    settings = Settings(
        OFFLINE_MODE=True,
        LOCAL_LLM_MODEL="qwen3-vl:4b",
        GEMINI_API_KEY="dummy-key",
        CACHE_DB_PATH=tmp_path / "cache.sqlite",
    )

    mock_claim_json = json.dumps({
        "claimed_issuer": "Reserve Bank of India",
        "action": "RBI updates lending rates",
        "amounts": ["Rs 500"],
        "effective_date": "2026-10-23",
        "canonical_claim_en": "RBI updates lending rates",
        "claim_type": "official_notice",
        "rationale": "Notice states lending rates",
    })

    mock_ollama_claim = MagicMock(return_value=mock_claim_json)
    monkeypatch.setattr("factcheck.claims.extractor._call_ollama_claim_llm", mock_ollama_claim)

    mock_gemini_claim = MagicMock(side_effect=AssertionError("Gemini claim LLM must NEVER be called in offline mode"))
    monkeypatch.setattr("factcheck.claims.extractor._call_gemini_claim_llm", mock_gemini_claim)

    claim = extract_claim("Unique test text for offline claim extraction", settings=settings)

    assert claim.claimed_issuer_id == "RBI"
    assert claim.canonical_claim_en == "RBI updates lending rates"
    assert mock_ollama_claim.called
    assert mock_gemini_claim.call_count == 0
