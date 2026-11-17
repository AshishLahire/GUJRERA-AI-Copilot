"""Unit and integration tests for the voice note intake / ASR pipeline."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from factcheck.api.app import app
from factcheck.config import get_settings
from factcheck.forensics import run_forensics
from factcheck.ingest.audio.languages import choose_engine, language_name, language_options
from factcheck.ingest.audio.transcribe import compute_audio_cache_key, transcribe_audio
from factcheck.schemas import ClaimResult, ExtractedFields, OCRResult

api_app_mod = sys.modules["factcheck.api.app"]
REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_CLIP = REPO_ROOT / "data" / "eval" / "asr" / "test_audio" / "en_free_laptop.ogg"


def test_audio_languages_and_options():
    opts = language_options()
    assert len(opts) >= 23
    codes = {o["code"] for o in opts}
    assert "hi" in codes
    assert "en" in codes
    assert "ta" in codes
    assert language_name("hi") == "Hindi"
    assert choose_engine("hi", "auto") == "whisper"


def test_audio_duration_limit_rejection(tmp_path):
    dummy_wav = tmp_path / "long_audio.wav"
    dummy_wav.write_bytes(b"RIFF dummy audio data")

    # Mock decode_audio to simulate 181 seconds of 16kHz audio
    fake_samples = np.zeros(181 * 16000, dtype=np.float32)

    with patch("factcheck.ingest.audio.transcribe.decode_audio", return_value=fake_samples):
        with pytest.raises(ValueError, match="exceeds the maximum allowed limit of 180s"):
            transcribe_audio(dummy_wav, use_cache=False)


def test_api_upload_rejects_invalid_audio_extension():
    client = TestClient(app)
    fake_file = io.BytesIO(b"not an audio file")
    resp = client.post(
        "/api/transcribe/upload",
        files={"file": ("fake_doc.pdf", fake_file, "application/pdf")},
    )
    assert resp.status_code == 400
    assert "Unsupported audio format" in resp.json()["error"]


def test_api_upload_rejects_audio_exceeding_max_audio_mb(monkeypatch):
    client = TestClient(app)
    cfg = get_settings()

    # Temporarily set MAX_AUDIO_MB to a tiny limit (0.0001 MB ~ 100 bytes)
    monkeypatch.setattr(cfg, "MAX_AUDIO_MB", 0.0001)

    fake_audio = io.BytesIO(b"A" * 500)
    resp = client.post(
        "/api/transcribe/upload",
        files={"file": ("clip.mp3", fake_audio, "audio/mpeg")},
    )
    assert resp.status_code == 400
    assert "exceeds the" in resp.json()["error"]


def test_audio_needs_confirmation_on_low_confidence(tmp_path):
    dummy_wav = tmp_path / "low_conf.wav"
    dummy_wav.write_bytes(b"dummy audio")

    fake_samples = np.zeros(16000, dtype=np.float32)

    class FakeInfo:
        language = "hi"
        language_probability = 0.45  # Below 0.70 threshold
        all_language_probs = [("hi", 0.45), ("mr", 0.30), ("bn", 0.15)]

    fake_segments = []

    with patch("factcheck.ingest.audio.transcribe.decode_audio", return_value=fake_samples), \
         patch("factcheck.ingest.audio.transcribe._whisper", return_value=(fake_segments, FakeInfo())), \
         patch("factcheck.ingest.audio.transcribe._whisper_text", return_value=("परीक्षण संदेश", [])):

        res = transcribe_audio(dummy_wav, use_cache=False)
        assert res["detection"]["needs_confirmation"] is True
        assert "Not sure about the language" in res["detection"]["message"]


def test_audio_manual_language_override(tmp_path):
    dummy_wav = tmp_path / "manual_lang.wav"
    dummy_wav.write_bytes(b"dummy audio")

    fake_samples = np.zeros(16000, dtype=np.float32)

    with patch("factcheck.ingest.audio.transcribe.decode_audio", return_value=fake_samples), \
         patch("factcheck.ingest.audio.transcribe._whisper_text", return_value=("Manual Hindi text", [])):

        res = transcribe_audio(dummy_wav, language="hi", use_cache=False)
        assert res["detection"]["mode"] == "manual"
        assert res["detection"]["needs_confirmation"] is False
        assert res["language"] == "hi"


def test_audio_forensics_skips_document_layout_rules():
    ocr_result = OCRResult(
        image_hash="test_audio_hash",
        final_text="Government of India notification deposit 5000 rupees to 987654321012 immediately",
        engine_used="whisper_small",
        valid=True,
        fields=ExtractedFields(
            reference_numbers=[],
            dates=[],
            phone_numbers=[],
            emails=[],
            urls=[],
            rupee_amounts=["5000"],
            subject=None,
        ),
        from_cache=False,
        markdown_stripped=False,
        time_ms=500,
        note=None,
        error=None,
    )

    # When is_audio=True, document checks (missing letterhead, missing signatory, etc.) must not fire
    forensics = run_forensics(ocr_result, is_audio=True)
    cue_ids = {f.cue_id for f in forensics.findings}

    assert "missing_letterhead" not in cue_ids
    assert "missing_signatory" not in cue_ids
    assert "missing_date" not in cue_ids
    assert "missing_reference_no" not in cue_ids


def test_audio_upload_and_pipeline_end_to_end_mock_llm(monkeypatch):
    if not SAMPLE_CLIP.exists():
        pytest.skip("Sample test audio clip missing from data/eval/asr/test_audio")

    client = TestClient(app)

    # Mock claim extraction to ensure zero external API calls
    mock_claim = ClaimResult(
        canonical_claim_en="Government provides free laptops to all college students.",
        claim_language="en",
        claimed_issuer="Government of India",
        action="distribution",
        effective_date=None,
        amounts=[],
        audience="students",
        claim_type="rumour",
        confidence=0.9,
        from_cache=True,
        status_note=None,
        error=None,
    )
    monkeypatch.setattr(api_app_mod, "extract_claim", lambda *args, **kwargs: mock_claim)

    clip_bytes = SAMPLE_CLIP.read_bytes()
    resp = client.post(
        "/api/transcribe/upload",
        files={"file": (SAMPLE_CLIP.name, clip_bytes, "audio/ogg")},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["is_audio"] is True
    assert "job_id" in data
    assert "audio_url" in data
    assert "transcription" in data
    assert "forensics" in data
    assert "matches" in data
    assert "verdict" in data
    assert data["transcription"]["language"] in {"en", "hi"}
    assert len(data["transcription"]["text"]) > 0

    # Test re-transcription endpoint with language override
    retrans_resp = client.post(
        f"/api/transcribe/{data['job_id']}/language",
        data={"language": "en", "allow_fallback": "false"},
    )
    assert retrans_resp.status_code == 200
    retrans_data = retrans_resp.json()
    assert retrans_data["transcription"]["language"] == "en"
    assert retrans_data["transcription"]["detection"]["mode"] == "manual"


def test_weak_language_warning_and_confidence_lowered(monkeypatch, tmp_path):
    client = TestClient(app)

    mock_transcription = {
        "text": "ಇದು ಪರೀಕ್ಷಾರ್ಥ ಧ್ವನಿಮುದ್ರಣ ಸಂದೇಶವಾಗಿದೆ.",
        "language": "kn",
        "language_name": "Kannada",
        "engine": "whisper",
        "detection": {"mode": "auto", "confidence": 0.85, "needs_confirmation": False},
        "duration_seconds": 3.5,
        "segments": [],
        "text_en": None,
        "empty": False,
        "error": False,
        "notes": [],
    }
    monkeypatch.setattr(api_app_mod, "transcribe_audio", lambda *args, **kwargs: dict(mock_transcription))

    mock_claim = ClaimResult(
        canonical_claim_en="Test Kannada voice note claim.",
        claim_language="kn",
        claimed_issuer="Government",
        action="notification",
        confidence=0.88,
        claim_type="rumour",
    )
    monkeypatch.setattr(api_app_mod, "extract_claim", lambda *args, **kwargs: mock_claim.model_copy())

    fake_wav = tmp_path / "test_kn.wav"
    fake_wav.write_bytes(b"RIFF dummy audio")

    resp = client.post(
        "/api/transcribe/upload",
        files={"file": ("test_kn.wav", fake_wav.read_bytes(), "audio/wav")},
        data={"allow_fallback": "true"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Verify weak-language warning
    assert "weak_language_warning" in data["transcription"]
    assert "Kannada" in data["transcription"]["weak_language_warning"]
    assert "IndicConformer" in data["transcription"]["weak_language_warning"]

    # Verify claim-extraction confidence is capped / lowered
    assert data["claim"]["confidence"] <= 0.35

    # Verify verdict reason notes the low quality
    assert "Speech recognition quality for Kannada is low with the current engine" in data["verdict"]["reason"]
    assert "claim extraction confidence lowered" in data["verdict"]["reason"]



def test_indic_conformer_routing_and_warning_removal():
    cfg = get_settings()
    assert cfg.USE_INDIC_CONFORMER is True

    # Weak languages route to indic
    for lang in ["kn", "te", "ml", "bn", "gu"]:
        assert choose_engine(lang, "auto") == "indic"

    # Unsupported languages route to indic
    assert choose_engine("or", "auto") == "indic"

    # Strong languages route to whisper
    for lang in ["en", "hi", "mr", "ta", "ur", "pa"]:
        assert choose_engine(lang, "auto") == "whisper"


def test_indic_conformer_transcription_removes_weak_warning_and_fires_own_keywords(monkeypatch, tmp_path):
    client = TestClient(app)

    # When transcribed by IndicConformer in native Telugu script
    mock_transcription = {
        "text": "ప్రభుత్వం అందరికీ ఉచిత గ్యాస్ సిలిండర్ ఇస్తుంది.",
        "language": "te",
        "language_name": "Telugu",
        "engine": "indic",
        "detection": {"mode": "auto", "confidence": 0.95, "needs_confirmation": False},
        "duration_seconds": 4.0,
        "segments": [],
        "text_en": None,
        "empty": False,
        "error": False,
        "notes": [],
    }
    monkeypatch.setattr(api_app_mod, "transcribe_audio", lambda *args, **kwargs: dict(mock_transcription))

    fake_wav = tmp_path / "test_te.wav"
    fake_wav.write_bytes(b"RIFF dummy audio")

    resp = client.post(
        "/api/transcribe/upload",
        files={"file": ("test_te.wav", fake_wav.read_bytes(), "audio/wav")},
        data={"allow_fallback": "false"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Weak-language warning should be REMOVED when IndicConformer is used
    assert "weak_language_warning" not in data["transcription"]
    assert data["transcript_transliterated"] is False

    # Own-language forensic checks fire on native script
    cues = [f["cue_id"] for f in data["forensics"]["findings"]]
    assert "too_good_offer" in cues
