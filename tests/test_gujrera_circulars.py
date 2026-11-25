"""Circulars: reading PDFs (with OCR), details, drafts vs published, cited answers in three languages."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gujrera.api.routes import get_session, router
from gujrera.circulars import broken_text_layer, clean_question, detect
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.enforcement import ensure_tables
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.legal.build import _tesseract_cmd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_sample_circulars", ROOT / "scripts" / "make_sample_circulars.py")
samples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(samples)
HAS_OCR = _tesseract_cmd() is not None


# ------------------------------------------------------------------ no database
def test_details_are_read_from_the_first_page():
    en = detect(["Gujarat RERA\nCircular No. GUJRERA/Circular/45/2023\nDate: 05/06/2023\n"
                 "Subject: Display of registration number in advertisements\n1. Every promoter ..."])
    assert en["number"] == "GUJRERA/Circular/45/2023" and en["issued_on"].isoformat() == "2023-06-05"
    assert en["subject"] == "Display of registration number in advertisements" and en["language"] == "en"
    gu = detect(["પરિપત્ર ક્રમાંક: ગુરેરા/૧૨/૨૦૨૪\nતારીખ: ૦૧/૦૨/૨૦૨૪\nવિષય: ત્રિમાસિક પ્રગતિ અહેવાલ બાબત\n૧. દરેક પ્રમોટરે ..."])
    assert gu["issued_on"].isoformat() == "2024-02-01" and gu["subject"].startswith("ત્રિમાસિક") and gu["language"] == "gu"


def test_garbled_gujarati_text_layers_are_detected():
    assert broken_text_layer("ગુજરાત  રિ યલ એչટેટ  નિ યમનકારી સԱામંડળ પ રિ પԋ ԃમાંક વિ ષય ӽહેરાતમાં")
    assert not broken_text_layer("ગુજરાત રિયલ એસ્ટેટ નિયમનકારી સત્તામંડળ પરિપત્ર ક્રમાંક તારીખ વિષય જાહેરાતમાં")
    assert not broken_text_layer("Circular No. 45 dated 05/06/2023 about advertisements")


def test_questions_lose_circular_words_and_filler():
    assert clean_question("What does the circular say about quarterly progress reports?") == "quarterly progress reports"
    assert clean_question("QPR ભરવા અંગે પરિપત્ર શું કહે છે?") == "qpr ભરવા"
    assert clean_question("विज्ञापन में RERA नंबर दिखाने के बारे में परिपत्र") == "विज्ञापन rera नंबर दिखाने"


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def env(tmp_path_factory):
    base: Path = tmp_path_factory.mktemp("circ")
    engine = make_engine(f"sqlite:///{(base / 'd.sqlite').as_posix()}")
    init_db(engine)
    ensure_tables(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    pdfs = {p.name: p for p in samples.make(base / "pdfs")}
    yield TestClient(app), pdfs
    engine.dispose()


def _auth(c, user):
    tok = c.post("/api/gujrera/auth/login", json={"username": user, "password": "gujrera-demo"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _upload(c, h, path):
    r = c.post("/api/gujrera/admin/circulars", files={"file": (path.name, path.read_bytes(), "application/pdf")}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()["circular"]


def test_only_state_officers_manage_circulars(env):
    c, pdfs = env
    f = pdfs["sample_circular_qpr_en.pdf"]
    for user in ("officer_surat", "citizen_01"):
        r = c.post("/api/gujrera/admin/circulars", files={"file": (f.name, f.read_bytes(), "application/pdf")},
                   headers=_auth(c, user))
        assert r.status_code == 403
    h = _auth(c, "officer_state")
    bad = c.post("/api/gujrera/admin/circulars", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}, headers=h)
    assert bad.status_code == 400


def test_upload_review_publish_and_cited_answers(env):
    c, pdfs = env
    h = _auth(c, "officer_state")
    assert c.post("/api/gujrera/chat", json={"message": "latest circulars"}).json()["intent"] == "circular_none"
    qpr = _upload(c, h, pdfs["sample_circular_qpr_en.pdf"])
    assert (qpr["number"], qpr["issued_on"], qpr["status"], qpr["ocr_pages"]) == ("SAMPLE/GUJRERA/2025/07", "2025-07-15", "draft", 0)
    assert "SAMPLE FOR TESTING" not in " ".join(qpr["preview"][0].split("\n")[1:2])

    # a draft is not searchable and its PDF is not public
    ask = {"message": "What does the circular say about quarterly progress reports?"}
    assert c.post("/api/gujrera/chat", json=ask).json()["intent"] == "circular_none"
    assert c.get(f"/api/gujrera/circulars/{qpr['id']}/pdf").status_code == 404
    assert c.get(f"/api/gujrera/circulars/{qpr['id']}/pdf", headers=h).status_code == 200

    # the admin corrects the subject and publishes
    r = c.patch(f"/api/gujrera/admin/circulars/{qpr['id']}", headers=h,
                json={"subject": "Quarterly progress reports: filing by promoters", "status": "published"}).json()
    assert r["circular"]["status"] == "published"
    reply = c.post("/api/gujrera/chat", json=ask).json()
    assert reply["intent"] == "circular" and "SAMPLE/GUJRERA/2025/07" in reply["text"] and "15 Jul 2025" in reply["text"]
    assert "fifteen days" in reply["text"] or "quarterly progress report" in reply["text"]
    src = reply["sources"][0]
    assert src["type"] == "circular" and src["url"] == f"/api/gujrera/circulars/{qpr['id']}/pdf#page=1"
    assert c.get(f"/api/gujrera/circulars/{qpr['id']}/pdf").status_code == 200
    assert [x["id"] for x in c.get("/api/gujrera/circulars").json()["circulars"]] == [qpr["id"]]

    # nothing related: say so instead of quoting a circular
    none = c.post("/api/gujrera/chat", json={"message": "circular about parking charges for visitors"}).json()
    assert none["intent"] == "circular_not_found"


@pytest.mark.skipif(not HAS_OCR, reason="Tesseract OCR is not installed")
def test_scanned_and_gujarati_circulars_are_read_with_ocr(env):
    c, pdfs = env
    h = _auth(c, "officer_state")
    gu = _upload(c, h, pdfs["sample_paripatra_advertisement_gu.pdf"])
    assert gu["ocr_pages"] == 1 and gu["number"] == "SAMPLE/GUJRERA/2025/09" and gu["language"] == "gu"
    assert "જાહેરાત" in (gu["subject"] or "")
    scan = _upload(c, h, pdfs["sample_circular_extension_scanned.pdf"])
    assert scan["ocr_pages"] == 1 and scan["issued_on"] == "2025-11-20"
    for x in (gu, scan):
        c.patch(f"/api/gujrera/admin/circulars/{x['id']}", headers=h, json={"status": "published"})
    for q in ("જાહેરાતમાં QR કોડ બાબત પરિપત્ર", "Is there a circular on showing the RERA number in advertisements?",
              "विज्ञापन में RERA नंबर दिखाने के बारे में परिपत्र"):
        reply = c.post("/api/gujrera/chat", json={"message": q}).json()
        assert reply["intent"] == "circular" and "SAMPLE/GUJRERA/2025/09" in reply["sources"][0]["id"], q
    ext = c.post("/api/gujrera/chat", json={"message": "circular about extension of registration"}).json()
    assert "SAMPLE/GUJRERA/2025/11" in ext["sources"][0]["id"] and "three months" in ext["text"]
    latest = c.post("/api/gujrera/chat", json={"message": "તાજેતરના પરિપત્રો"}).json()
    assert latest["intent"] == "circular_list" and latest["text"].index("2025/11") < latest["text"].index("2025/07")


def test_delete(env):
    c, pdfs = env
    h = _auth(c, "officer_state")
    x = _upload(c, h, pdfs["sample_circular_qpr_en.pdf"])
    assert c.delete(f"/api/gujrera/admin/circulars/{x['id']}", headers=h).json() == {"deleted": x["id"]}
    assert c.get(f"/api/gujrera/circulars/{x['id']}/pdf", headers=h).status_code == 404
