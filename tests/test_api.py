"""Tests for the FastAPI backend (health, samples, upload validation, PDF page-1 rendering, and 503 handling)."""

from __future__ import annotations

import io
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from factcheck.api.app import app
from factcheck.schemas import ExtractedFields, OCRResult

api_app_mod = sys.modules["factcheck.api.app"]


def test_api_health_endpoint_returns_status_without_secrets():
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert isinstance(data["ollama_enabled"], bool)
    assert isinstance(data["gemini_configured"], bool)
    assert isinstance(data["daily_api_calls_used"], int)
    assert isinstance(data["daily_api_call_limit"], int)
    # Must never expose any API key value
    assert "GEMINI_API_KEY" not in resp.text
    assert "AIza" not in resp.text


def test_api_samples_endpoint_returns_demo_entries():
    client = TestClient(app)
    resp = client.get("/api/samples")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 20
    assert len(data["items"]) == 20

    groups = {item["group"] for item in data["items"]}
    assert groups == {"fake", "genuine", "synthetic"}

    first = data["items"][0]
    assert first["id"] == "FN-TG-01595"
    assert first["demo_order"] == 1
    assert first["talking_point"]
    assert "language" in first
    assert "thumbnail_url" in first
    assert first["thumbnail_url"].startswith("/api/samples/")
    assert "filename" in first
    assert "\\" not in first["filename"]


def test_api_upload_rejects_txt_file(monkeypatch):
    def _fail_ocr(*args, **kwargs):
        raise AssertionError("run_ocr must not be called for rejected file types")

    monkeypatch.setattr(api_app_mod, "run_ocr", _fail_ocr)

    client = TestClient(app)
    resp = client.post(
        "/api/ocr/upload",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        data={"allow_fallback": "false"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "error" in body
    assert "Unsupported file type" in body["error"]


def test_api_upload_pdf_converts_first_page_and_sets_note(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api_app_mod, "UPLOADS_DIR", tmp_path)

    captured_paths: list[Path] = []

    def _mock_run_ocr(image_path: Path, **kwargs) -> OCRResult:
        captured_paths.append(Path(image_path))
        return OCRResult(
            image_hash="abc123hash",
            final_text="CENTRAL BOARD OF SECONDARY EDUCATION\nCircular No: Acad-67/2026",
            engine_used="gemini:gemini-3.5-flash-lite",
            valid=True,
            fields=ExtractedFields(reference_numbers=["Acad-67/2026"]),
            from_cache=True,
            markdown_stripped=False,
            time_ms=12.5,
        )

    monkeypatch.setattr(api_app_mod, "run_ocr", _mock_run_ocr)

    buf = io.BytesIO()
    im = Image.new("RGB", (300, 200), color=(250, 250, 250))
    im.save(buf, format="PDF", resolution=72.0)
    pdf_bytes = buf.getvalue()

    client = TestClient(app)
    resp = client.post(
        "/api/ocr/upload",
        files={"file": ("circular.pdf", pdf_bytes, "application/pdf")},
        data={"allow_fallback": "false"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["note"] is not None and "page 1" in data["note"].lower()
    assert len(captured_paths) == 1
    assert captured_paths[0].suffix.lower() == ".png"
    assert data["width"] > 0 and data["height"] > 0


def test_api_maps_503_to_gemini_busy(monkeypatch):
    def _mock_503(*args, **kwargs) -> OCRResult:
        return OCRResult(
            image_hash="h",
            final_text="",
            engine_used="gemini:gemini-3.5-flash-lite",
            valid=False,
            error="Gemini API error: 503 UNAVAILABLE",
        )

    monkeypatch.setattr(api_app_mod, "run_ocr", _mock_503)
    monkeypatch.setattr("factcheck.pipeline.run_ocr", _mock_503)  # sample endpoint goes through the shared pipeline

    client = TestClient(app)
    resp = client.post("/api/ocr/sample/FN-TG-01999?allow_fallback=true")
    assert resp.status_code == 503
    assert resp.json() == {"error": "Gemini busy, try again"}


def test_api_sample_simulate_unseen_toggle():
    """FN-TG-01999: with simulate_unseen=false it is debunked by its own record;
    with simulate_unseen=true, its debunk is excluded, yielding unverified."""
    client = TestClient(app)

    # Toggle OFF
    resp_off = client.post(
        "/api/ocr/sample/FN-TG-01999?allow_fallback=false&simulate_unseen=false"
    )
    assert resp_off.status_code == 200
    data_off = resp_off.json()
    assert data_off["verdict"] is not None
    assert data_off["verdict"]["verdict_key"] == "debunked"
    assert data_off["simulate_unseen"] is False
    assert any(
        m["doc_id"] == "FN-TG-01999" for m in data_off["matches"]["debunks"]
    )

    # Toggle ON
    resp_on = client.post(
        "/api/ocr/sample/FN-TG-01999?allow_fallback=false&simulate_unseen=true"
    )
    assert resp_on.status_code == 200
    data_on = resp_on.json()
    assert data_on["verdict"] is not None
    assert data_on["verdict"]["verdict_key"] == "unverified"
    assert data_on["simulate_unseen"] is True
    assert all(
        m["doc_id"] != "FN-TG-01999" for m in data_on["matches"]["debunks"]
    )

