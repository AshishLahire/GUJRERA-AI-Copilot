"""Held-out test set endpoints and the PDF text-layer path (zero API calls)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from factcheck.api.app import TESTSET_DIR, app
from factcheck.extract.ocr.runner import read_pdf_text_layer
from factcheck.pipeline import decide_without_archive, run_document_pipeline

pytestmark = pytest.mark.skipif(
    not (TESTSET_DIR / "manifest.json").exists(), reason="run scripts/build_testset.py first"
)


def test_list_testset_has_all_groups() -> None:
    data = TestClient(app).get("/api/testset").json()
    labels = {it["label"] for it in data["items"]}
    assert {"real", "fake", "synthetic_clean", "synthetic_forged"} <= labels
    assert all(it["thumbnail_url"].startswith("/api/testset/") for it in data["items"])


def test_testset_image_and_original_and_404() -> None:
    client = TestClient(app)
    assert client.get("/api/testset/TF-01/image").status_code == 200
    assert client.get("/api/testset/TF-01/image?original=true").status_code == 200
    assert client.get("/api/testset/NOPE/image").status_code == 404


def test_born_digital_pdf_uses_text_layer() -> None:
    text = read_pdf_text_layer(TESTSET_DIR / "real" / "TR-02.pdf")
    assert text and "RBI/2026-27/291" in text


def test_genuine_circular_verifies_with_and_without_archive() -> None:
    run = run_document_pipeline(
        TESTSET_DIR / "real" / "TR-02.pdf", allow_fallback=False, image_for_visual=TESTSET_DIR / "real" / "TR-02.png"
    )
    assert run.raw.engine_used == "pdf_text_layer"
    assert run.verdict.verdict_key == "matches_official"
    assert decide_without_archive(run).verdict_key == "matches_official"


def test_run_endpoint_returns_test_item() -> None:
    data = TestClient(app).post("/api/testset/TR-02/run?allow_fallback=false&simulate_unseen=true").json()
    assert data["test_item"]["label"] == "real"
    assert data["simulate_unseen"] is True
    assert data["verdict"]["verdict_key"] == "matches_official"
    assert Path(data["image_url"]).name == "image"
