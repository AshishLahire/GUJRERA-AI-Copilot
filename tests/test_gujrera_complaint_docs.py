"""A complaint's hearing and documents: the officer fixes the hearing, the buyer sees it; the buyer adds
evidence with the reference number and tracking code (or logged in); officers see it within their district."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.complaints import documents as docs_mod
from gujrera.complaints.adapter import ComplaintDraft, MockComplaintAdapter
from gujrera.db.models import AuditLog, Project, User
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.enforcement import ensure_tables
from gujrera.ingest.mock_generator import MockConfig, generate

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def env(tmp_path: Path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'd.sqlite').as_posix()}")
    init_db(engine)
    ensure_tables(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        surat = s.scalar(select(Project).where(Project.district == "Surat").limit(1))
        citizen = s.scalar(select(User).where(User.username == "citizen_01"))
        adapter = MockComplaintAdapter(s)
        anon = adapter.submit(ComplaintDraft(project_id=surat.id, description="Possession delayed by two years.",
                                             category="possession_delay", relief="refund_interest", name="Test Buyer",
                                             mobile="9876543210", consent=True))
        own = adapter.submit(ComplaintDraft(project_id=surat.id, description="Extra parking charges demanded.",
                                            category="agreement_violation", relief="refund_interest", name="Citizen One",
                                            mobile="9876500000", consent=True, user_id=citizen.id))
        s.commit()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    c = TestClient(app)
    c.factory, c.anon, c.own = factory, anon, own
    docs_mod._WRONG.clear()
    yield c
    engine.dispose()


def _auth(c, user):
    tok = c.post("/api/gujrera/auth/login", json={"username": user, "password": "gujrera-demo"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _id(c, ref):
    with c.factory() as s:
        from gujrera.db.models import Complaint

        return s.scalar(select(Complaint.id).where(Complaint.ref_no == ref))


def test_the_tracking_code_opens_a_complaint_and_wrong_codes_are_limited(env):
    c, ref, code = env, env.anon.ref_no, env.anon.tracking_code
    assert c.post("/api/gujrera/complaints/lookup", json={"ref": ref}).status_code == 403  # no code
    assert c.post("/api/gujrera/complaints/lookup", json={"ref": "MOCK-CMP-1999-99999", "code": "123456"}).status_code == 404
    v = c.post("/api/gujrera/complaints/lookup", json={"ref": ref.lower(), "code": code}).json()
    assert v["ref_no"] == ref and v["status"] == "filed" and v["documents"] == [] and v["can_add_documents"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert c.post("/api/gujrera/complaints/lookup", json={"ref": ref, "code": wrong}).status_code == 403
    r = c.post("/api/gujrera/complaints/lookup", json={"ref": ref, "code": code})
    assert r.status_code == 403 and "Too many" in r.json()["detail"]  # locked for an hour, even with the right code


def test_the_buyer_adds_documents_and_only_real_files_are_kept(env):
    c, ref, code = env, env.anon.ref_no, env.anon.tracking_code
    up = lambda name, data, **kw: c.post("/api/gujrera/complaints/documents",  # noqa: E731
                                         data={"ref": ref, "code": code, **kw}, files={"file": (name, data)})
    r = up("Agreement for sale.pdf", PDF, note="Signed agreement")
    assert r.status_code == 200 and r.json()["added_by"] == "complainant" and r.json()["note"] == "Signed agreement"
    assert up("receipt.png", PNG).status_code == 200
    assert "already attached" in up("copy.pdf", PDF).json()["detail"]
    assert "does not look like a PDF" in up("fake.pdf", b"MZ\x90\x00 not a pdf").json()["detail"]
    assert "PDF, JPG or PNG" in up("tool.exe", b"MZ").json()["detail"]
    assert "larger than 10 MB" in up("big.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024)).json()["detail"]
    assert c.post("/api/gujrera/complaints/documents", data={"ref": ref},
                  files={"file": ("a.pdf", PDF)}).status_code == 403  # no code
    v = c.post("/api/gujrera/complaints/lookup", json={"ref": ref, "code": code}).json()
    assert [d["filename"] for d in v["documents"]] == ["Agreement for sale.pdf", "receipt.png"]
    got = c.post(f"/api/gujrera/complaints/documents/{v['documents'][0]['id']}/file", json={"ref": ref, "code": code})
    assert got.status_code == 200 and got.content == PDF and got.headers["content-type"] == "application/pdf"
    other = env.own.ref_no  # a document id from one complaint does not open through another
    assert c.post(f"/api/gujrera/complaints/documents/{v['documents'][0]['id']}/file",
                  json={"ref": other, "code": env.own.tracking_code}).status_code == 404
    for i in range(8):
        assert up(f"p{i}.pdf", PDF + bytes([i])).status_code == 200
    assert "at most 10" in up("p11.pdf", PDF + b"x").json()["detail"]
    with c.factory() as s:  # the audit log records the upload, not the file
        rows = s.scalars(select(AuditLog.detail).where(AuditLog.action == "complaint_document_added")).all()
        assert len(rows) == 10 and all("Agreement" not in r for r in rows)


def test_the_logged_in_buyer_needs_no_code_and_sees_only_their_own(env):
    c = env
    h = _auth(c, "citizen_01")
    mine = c.get("/api/gujrera/complaints/mine", headers=h).json()["complaints"]
    assert [x["ref_no"] for x in mine] == [env.own.ref_no]
    assert c.post("/api/gujrera/complaints/documents", headers=h, data={"ref": env.own.ref_no},
                  files={"file": ("letter.pdf", PDF)}).status_code == 200
    assert c.post("/api/gujrera/complaints/lookup", headers=h, json={"ref": env.anon.ref_no}).status_code == 403
    assert c.get("/api/gujrera/complaints/mine").json() == {"complaints": []}  # not logged in


def test_hearing_fixed_by_the_officer_reaches_the_buyer(env):
    c, ref, code = env, env.anon.ref_no, env.anon.tracking_code
    cid = _id(c, ref)
    h = _auth(c, "officer_surat")
    on = (date.today() + timedelta(days=9)).isoformat()
    r = c.post(f"/api/gujrera/complaints/{cid}/status", headers=h,
               json={"status": "hearing_scheduled", "hearing_on": on, "hearing_place": "GujRERA office, Gandhinagar, Court 2"})
    assert r.status_code == 200
    v = c.post("/api/gujrera/complaints/lookup", json={"ref": ref, "code": code, "lang": "en"}).json()
    assert v["hearing"]["upcoming"] and v["hearing"]["days_to"] == 9
    assert v["hearing"]["text"].startswith("Next hearing:") and "in 9 days, at GujRERA office" in v["hearing"]["text"]
    gu = c.post("/api/gujrera/complaints/lookup", json={"ref": ref, "code": code, "lang": "gu"}).json()
    assert "આગામી સુનાવણી" in gu["hearing"]["text"]
    # the chat says it too
    chat = c.post("/api/gujrera/chat", json={"message": f"status of my complaint {ref}"}).json()
    chat = c.post("/api/gujrera/chat", json={"message": code, "session_id": chat["session_id"]}).json()
    assert chat["intent"] == "complaint_status" and "Next hearing:" in chat["text"]
    assert chat["cards"][0]["hearing"]["place"] == "GujRERA office, Gandhinagar, Court 2"
    # the officer's desk and brief list it; officer can add a hearing notice and open the buyer's papers
    assert any(x["ref_no"] == ref and x["days_to"] == 9 for x in c.get("/api/gujrera/complaints/hearings", headers=h).json()["items"])
    assert any(x["ref_no"] == ref for x in c.get("/api/gujrera/officer/dashboard", headers=h).json()["hearings"])
    note = c.post(f"/api/gujrera/complaints/{cid}/documents", headers=h, data={"note": "Hearing notice"},
                  files={"file": ("notice.pdf", PDF)}).json()
    assert note["added_by"] == "officer"
    b = c.get(f"/api/gujrera/complaints/{cid}/brief", headers=h).json()
    assert b["hearing"]["place"].startswith("GujRERA office") and b["documents"][0]["filename"] == "notice.pdf"
    assert c.get(f"/api/gujrera/complaints/{cid}/documents/{note['id']}", headers=h).content == PDF


def test_other_districts_and_buyers_cannot_see_it(env):
    c = env
    cid = _id(c, env.anon.ref_no)
    other = _auth(c, "officer_ahmedabad")
    assert c.get(f"/api/gujrera/complaints/{cid}/brief", headers=other).status_code in (403, 404)
    assert c.post(f"/api/gujrera/complaints/{cid}/documents", headers=other,
                  files={"file": ("x.pdf", PDF)}).status_code == 404
    assert c.post("/api/gujrera/complaints/lookup", headers=other, json={"ref": env.anon.ref_no}).status_code == 403
    assert c.get("/api/gujrera/complaints/hearings", headers=_auth(c, "citizen_01")).status_code == 403


def test_filing_in_chat_says_documents_can_be_added(env):
    from gujrera.complaints.strings import s

    assert "My complaint page" in s("add_documents", "en")


def test_an_older_database_gets_the_hearing_columns(tmp_path):
    from sqlalchemy import inspect, text

    engine = make_engine(f"sqlite:///{(tmp_path / 'old.sqlite').as_posix()}")
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE complaint_documents"))
        conn.execute(text("ALTER TABLE complaints DROP COLUMN hearing_place"))
        conn.execute(text("ALTER TABLE complaints DROP COLUMN hearing_on"))
    ensure_tables(engine)
    insp = inspect(engine)
    assert "complaint_documents" in insp.get_table_names()
    assert {"hearing_on", "hearing_place"} <= {c["name"] for c in insp.get_columns("complaints")}
    engine.dispose()
