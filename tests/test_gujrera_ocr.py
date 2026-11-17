"""Gujarati OCR on uploaded ads (Tesseract guj+hin+eng) feeding the trust check.

Fixture images in tests/fixtures/gujrera_ads/ were rendered from the .html files next to
them with Microsoft Edge (correct Gujarati shaping). They refer to the seed-2016 mock project
"Mangal Square" (MOCK00009), so the test uses the default mock data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gujrera.api.routes import get_session, router
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.trust.ocr import ocr_file, tesseract_available
from gujrera.trust.rera_number import find_rera_numbers
from gujrera.trust.service import check_document

ADS = Path(__file__).parent / "fixtures" / "gujrera_ads"
needs_tesseract = pytest.mark.skipif(not tesseract_available(), reason="Tesseract with Gujarati not installed")


def test_wrapped_registration_number_is_joined():
    found = find_rera_numbers("GujRERA Reg. No: PR/GJ/SURAT/SURAT\n\nCITY/SUDA/MOCK00009/240723")
    assert [n.normalised for n in found] == ["PR/GJ/SURAT/SURAT CITY/SUDA/MOCK00009/240723"]


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path = tmp_path_factory.mktemp("ocr") / "o.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())  # default seed: Mangal Square is MOCK00009
    yield factory
    engine.dispose()


@needs_tesseract
def test_gujarati_text_is_read():
    out = ocr_file(ADS / "genuine_gu.png")
    assert out.engine == "tesseract" and out.confidence and out.confidence > 70
    for word in ("મંગલ સ્ક્વેર", "પઝેશન", "ડિસેમ્બર", "PR/GJ/SURAT"):
        assert word in out.text


@needs_tesseract
@pytest.mark.parametrize("image,verdicts", [
    ("genuine_gu.png", ("verified", "registered_with_warnings")),
    ("fake_gu.png", ("not_found",)),
    ("late_en.png", ("mismatch",)),
])
def test_uploaded_ads_get_right_verdict(Session, image, verdicts):
    with Session() as s:
        report = check_document(ADS / image, Repository(s, Principal.anonymous()))
    assert report["verdict"] in verdicts, (report["verdict"], report["ocr"]["text"])
    assert report["ocr"]["engine"] == "tesseract" and not report["ocr"]["low_confidence"]


@needs_tesseract
def test_fake_ad_flags_payment_to_account(Session):
    with Session() as s:
        report = check_document(ADS / "fake_gu.png", Repository(s, Principal.anonymous()))
    assert any(c["id"] == "forensic_payment_to_account" for c in report["checks"])


@needs_tesseract
def test_upload_endpoint(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    with open(ADS / "genuine_gu.png", "rb") as fh:
        res = client.post("/api/gujrera/trust/upload", files={"file": ("ad.png", fh, "image/png")})
    assert res.status_code == 200 and res.json()["ocr"]["engine"] == "tesseract"
