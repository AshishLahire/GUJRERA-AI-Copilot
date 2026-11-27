"""The department's internal records through the onboarding console: complaints, orders with penalties,
notices, scrutiny and defaults. Each is checked on a copy, loaded, matched to its project by RERA number,
and then answers the officials' sample questions."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gujrera.api.routes import get_session, router
from gujrera.db.models import AuthorityNotice, Complaint, ComplianceEvent, Order, OrderPenalty, Project, ProjectScrutiny
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.enforcement import ensure_tables
from gujrera.ingest.mock_generator import MockConfig, generate


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("onbi") / "d.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    ensure_tables(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
        ahd = s.scalar(select(Project.rera_no).where(Project.district == "Ahmedabad").order_by(Project.id).limit(1))
        srt = s.scalar(select(Project.rera_no).where(Project.district == "Surat").order_by(Project.id).limit(1))
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    c = TestClient(app)
    c.factory, c.ahd, c.srt = factory, ahd, srt
    yield c
    engine.dispose()


def _auth(c, user):
    return {"Authorization": "Bearer " + c.post("/api/gujrera/auth/login",
                                                json={"username": user, "password": "gujrera-demo"}).json()["token"]}


def _load(c, h, name, text, expect_kind):
    up = c.post("/api/gujrera/admin/imports", files={"file": (name, text.encode())}, headers=h).json()
    sheet = up["sheets"][0]
    assert sheet["suggested_kind"] == expect_kind, sheet["suggested_kind"]
    body = {"sheet": sheet["name"], "kind": expect_kind, "mapping": sheet["kinds"][expect_kind]["mapping"]}
    chk = c.post(f"/api/gujrera/admin/imports/{up['run']['id']}/check", json=body, headers=h).json()
    ld = c.post(f"/api/gujrera/admin/imports/{up['run']['id']}/load", json=body, headers=h).json()
    assert (chk["inserted"], chk["rejected"]) == (ld["inserted"], ld["rejected"]) and ld["saved"]
    again = c.post(f"/api/gujrera/admin/imports/{up['run']['id']}/load", json=body, headers=h).json()
    assert again["inserted"] == 0 and again["unchanged"] == ld["inserted"]  # loading twice adds nothing
    return ld


def _ask(c, h, question):
    return c.post("/api/gujrera/analytics/query", json={"question": question}, headers=h).json()


def _count(c, model, *where):
    with c.factory() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def test_complaints_load_and_reach_the_desk(env):
    c, h = env, _auth(env, "officer_state")
    today = date.today()
    csv = ("Complaint No,RERA Registration No,Date of Filing,Complaint Type,Status,Relief Sought,Next Hearing Date,Complainant Phone\n"
           f"CMP/A/2026/9001,{c.ahd},{(today - timedelta(days=70)).strftime('%d/%m/%Y')},Delay in possession,Hearing listed,"
           f"Refund with interest,{(today + timedelta(days=5)).strftime('%d/%m/%Y')},9876543210\n"
           f"CMP/A/2026/9002,{c.srt},{(today - timedelta(days=10)).strftime('%d/%m/%Y')},Breach of agreement for sale,New,,,\n"
           f"CMP/A/2026/9003,PR/GJ/NOWHERE/X/Y/RAA00001/010120,{today.strftime('%d/%m/%Y')},Delay,New,,,\n")
    ld = _load(c, h, "complaints.csv", csv, "complaint")
    assert (ld["inserted"], ld["rejected"]) == (2, 1) and "not in the registry" in ld["errors"][0]["error"]
    with c.factory() as s:
        one = s.scalar(select(Complaint).where(Complaint.ref_no == "CMP/A/2026/9001"))
        assert (one.category, one.status, one.relief, one.is_mock) == ("possession_delay", "hearing_scheduled", "refund_with_interest", False)
        assert one.hearing_on == today + timedelta(days=5) and one.district == "Ahmedabad" and one.events
        assert s.scalar(select(Complaint.category).where(Complaint.ref_no == "CMP/A/2026/9002")) == "agreement_violation"
        assert "9876543210" not in (one.summary or "")  # an unmapped column (a phone) is never read
    queue = c.get("/api/gujrera/complaints/triage?lang=en", headers=h).json()["items"]
    assert any(i["ref_no"] == "CMP/A/2026/9001" for i in queue)
    assert any(x["ref_no"] == "CMP/A/2026/9001" for x in c.get("/api/gujrera/complaints/hearings", headers=h).json()["items"])


def test_orders_with_penalties_answer_the_penalty_question(env):
    c, h = env, _auth(env, "officer_state")
    before = len(_ask(c, h, "Penalty orders with amounts")["card"]["rows"])
    issued = (date.today() - timedelta(days=20)).strftime("%d-%m-%Y")
    csv = ("Order No,Order Type,Order Date,RERA Registration No,Complaint No,Penalty Amount,Penalty Paid,Direction\n"
           f"ORD/2026/501,Penalty order,{issued},{c.ahd},,\"Rs 2,50,000\",No,Penalty for delay in QPR filing\n"
           f"ORD/2026/502,Final order,{issued},,CMP/A/2026/9001,,,Refund with interest within 45 days\n"
           f"ORD/2026/503,Penalty order,{issued},{c.ahd},,two lakh,No,\n")
    ld = _load(c, h, "orders.csv", csv, "order")
    assert (ld["inserted"], ld["rejected"]) == (2, 1) and "not a number" in ld["errors"][0]["error"]
    with c.factory() as s:
        pen = s.scalar(select(OrderPenalty).join(Order, Order.id == OrderPenalty.order_id).where(Order.order_no == "ORD/2026/501"))
        assert pen.amount == 250000 and pen.paid is False
        final = s.scalar(select(Order).where(Order.order_no == "ORD/2026/502"))
        assert final.order_type == "complaint_order" and final.complaint_id and final.project_id
    rows = _ask(c, h, "Penalty orders with amounts")["card"]["rows"]
    assert len(rows) == before + 1 and any(r[0] == "ORD/2026/501" for r in rows)


def test_notices_scrutiny_and_defaults_answer_the_sample_questions(env):
    c, h = env, _auth(env, "officer_state")
    recent = (date.today() - timedelta(days=30)).strftime("%d/%m/%Y")
    scrutiny_before = len(_ask(c, h, "Projects under scrutiny in Ahmedabad")["card"]["rows"])
    _load(c, h, "scrutiny.csv", "RERA Registration No,Application Type,Current Stage,Application Date\n"
                                f"{c.ahd},Extension of registration,Under scrutiny,{recent}\n", "scrutiny")
    assert len(_ask(c, h, "Projects under scrutiny in Ahmedabad")["card"]["rows"]) == scrutiny_before + 1

    notices_before = _count(c, AuthorityNotice)
    ld = _load(c, h, "notices.csv", "Notice No,RERA Registration No,Notice Type,Notice Date,Status\n"
                                    f"NOT/2026/77,{c.ahd},Show Cause Notice,{recent},Issued\n", "notice")
    assert ld["inserted"] == 1 and _count(c, AuthorityNotice) == notices_before + 1
    rows = _ask(c, h, "Developers issued notices in the last six months")["card"]["rows"]
    assert any(r[-1] == "issued" or "show_cause" in r for r in rows)

    defaults_before = _count(c, ComplianceEvent)
    ld = _load(c, h, "defaults.csv", "RERA Registration No,Default Type,Period,Date of Default\n"
                                     f"{c.ahd},QPR not submitted,2026-Q2,{recent}\n"
                                     f"{c.ahd},Late delivery of flats,2026-Q2,{recent}\n", "default")
    assert (ld["inserted"], ld["rejected"]) == (1, 1) and "unknown default type" in ld["errors"][0]["error"]
    with c.factory() as s:
        e = s.scalar(select(ComplianceEvent).order_by(ComplianceEvent.id.desc()).limit(1))
        assert (e.event_type, e.period, e.is_mock) == ("qpr_not_filed", "2026-Q2", False)
    assert _count(c, ComplianceEvent) == defaults_before + 1
    assert _ask(c, h, "Defaulting developers in Ahmedabad in the last six months")["card"]["rows"]
    assert _count(c, ProjectScrutiny, ProjectScrutiny.is_mock.is_(False)) == 1


def test_only_the_state_admin_loads_internal_records(env):
    c = env
    for user in ("officer_surat", "citizen_01"):
        r = c.post("/api/gujrera/admin/imports", files={"file": ("n.csv", b"Notice No,RERA Registration No\n")},
                   headers=_auth(c, user))
        assert r.status_code == 403
