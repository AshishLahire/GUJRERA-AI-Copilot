"""Agreement-for-sale checker against the model agreement (Gujarat RERA Rules, Annexure A) and the Act."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gujrera.api.routes import get_session, router
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.tools.agreement import check, extract_text, report
from gujrera.tools.agreement_samples import FAIR, ONE_SIDED

NUM = "PR/GJ/SURAT/SURAT CITY/SUDA/MOCK00009/240723"


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("agr") / "a.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
    yield factory
    engine.dispose()


def _status(text: str, repo=None) -> dict[str, str]:
    return {f.id: f.status for f in check(text, repo)["findings"]}


def test_samples(Session):
    with Session() as s:
        repo = Repository(s, Principal.anonymous())
        bad = _status(ONE_SIDED, repo)
        assert {k for k, v in bad.items() if v == "fail"} == {
            "carpet_area", "area_variation", "escalation", "interest_delay", "delay_excuses", "refund_on_default",
            "termination", "plan_changes", "defect_liability", "advance_limit", "complaint_right"}
        assert bad["possession_date"] == "warn" and bad["project_account"] == "warn" and bad["rera_number"] == "pass"
        good = _status(FAIR, repo)
        assert set(good.values()) == {"pass"} and len(good) == 13
        r = report(ONE_SIDED, repo, "gu")
        assert r["findings"][0]["status"] == "fail" and r["findings"][0]["title"] != r["findings"][0]["title_en"]
        assert all(f["citations"] for f in r["findings"])


@pytest.mark.parametrize("clause,check_id,want", [
    ("The carpet area may vary by up to 3% after the occupancy certificate.", "area_variation", "pass"),
    ("The carpet area may vary by up to 5% after the occupancy certificate.", "area_variation", "fail"),
    ("If the Promoter fails to hand over possession it shall pay interest at 10.95% per annum. The Allottee shall pay "
     "interest at 18% per annum on delayed payments.", "interest_equal", "fail"),
    ("If the Promoter fails to hand over possession it shall pay interest at 10.95% per annum. The Allottee shall pay "
     "interest at 10.95% per annum on delayed payments.", "interest_equal", "pass"),
    ("The Promoter shall give possession on or before 30 June 2027.", "possession_date", "pass"),
    ("Possession is expected by June 2027, subject to completion.", "possession_date", "warn"),
    ("Any structural defect notified within five years from possession shall be rectified.", "defect_liability", "pass"),
    ("Defects reported within 18 months of possession shall be rectified.", "defect_liability", "fail"),
    ("The Allottee shall pay 10% of the price as booking amount.", "advance_limit", "pass"),
    ("On allotment 30% of the price shall be paid as advance.", "advance_limit", "fail"),
    ("Delay caused by non-availability of cement or steel shall extend the time for possession.", "delay_excuses", "fail"),
    ("On cancellation the Promoter may forfeit 15% of the price.", "termination", "warn"),
    ("The Purchaser waives the right to approach any authority or forum.", "complaint_right", "fail"),
])
def test_single_clauses(clause, check_id, want):
    text = f"AGREEMENT FOR SALE between the Promoter and the Allottee for a flat. GujRERA No. {NUM}.\n{clause}\n"
    assert _status(text).get(check_id) == want


def test_registration_number(Session):
    with Session() as s:
        repo = Repository(s, Principal.anonymous())
        assert _status("AGREEMENT FOR SALE between the Promoter and the Allottee.", repo)["rera_number"] == "fail"
        fake = "AGREEMENT FOR SALE. GujRERA No. PR/GJ/SURAT/SURAT CITY/SUDA/RAA99999/240723. Promoter and Allottee."
        assert _status(fake, repo)["rera_number"] == "fail"


def test_extract_text_reads_every_page_and_releases_the_file(tmp_path):
    fitz = pytest.importorskip("fitz")
    pdf = tmp_path / "agreement.pdf"
    doc = fitz.open()
    half = len(ONE_SIDED) // 2
    for part in (ONE_SIDED[:half], ONE_SIDED[half:]):
        doc.new_page().insert_textbox(fitz.Rect(40, 40, 560, 800), part, fontsize=9)
    doc.save(str(pdf))
    doc.close()
    text, how = extract_text(pdf)
    assert how == "pdf-text" and "sole arbitrator" in text and "super built-up" in text  # page 2 and page 1
    os.remove(pdf)  # not locked (Windows)
    txt = tmp_path / "a.txt"
    txt.write_text(FAIR, encoding="utf-8")
    assert extract_text(txt)[0] == FAIR


def test_api_and_chat(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    assert client.get("/api/gujrera/agreement/samples").json()["fair"] == FAIR
    assert client.post("/api/gujrera/agreement/check", json={"text": "short"}).status_code == 400
    body = client.post("/api/gujrera/agreement/check", json={"text": ONE_SIDED, "lang": "hi"}).json()
    assert body["counts"]["fail"] == 11 and body["project"]["name"] == "Mangal Square"
    up = client.post("/api/gujrera/agreement/upload", files={"file": ("a.txt", FAIR.encode("utf-8"), "text/plain")}).json()
    assert up["counts"]["fail"] == 0 and up["read_as"] == "text"
    assert client.post("/api/gujrera/agreement/upload", files={"file": ("a.exe", b"x" * 300, "application/octet-stream")}).status_code == 400
    with Session() as s:
        repo = Repository(s, Principal.anonymous())
        out = respond(ONE_SIDED, ChatState(), repo).to_dict()
        assert out["intent"] == "agreement_check" and out["cards"][0]["counts"]["fail"] == 11
        assert respond("Can you check my agreement?", ChatState(), repo).intent == "agreement_check"
        s.rollback()


def test_sentences_keep_abbreviations():
    from gujrera.tools.agreement import sentences

    assert sentences("Flat No. B-402 costs Rs. 62,00,000. Possession on or before 30 June 2027.") == [
        "Flat No. B-402 costs Rs. 62,00,000.", "Possession on or before 30 June 2027."]
