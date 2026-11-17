"""Complaint triage and hearing briefs for officers (60-day disposal, Section 29(4))."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.auth import issue_token
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.complaints.triage import brief, triage, update_status
from gujrera.db.models import Complaint, ComplaintEvent, Project, Promoter, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate

AS_OF = date(2026, 6, 1)


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("triage") / "t.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        pr = Promoter(name="Test Desk Builders", district="Rajkot", is_mock=True)
        s.add(pr)
        s.flush()
        p = Project(rera_no="PR/GJ/RAJKOT/RAJKOT/RUDA/TEST00003/010124", promoter_id=pr.id, name="Test Desk Towers",
                    district="Rajkot", project_type="residential", status="ongoing", units=40, reg_date=date(2023, 1, 1),
                    proposed_completion=date(2025, 1, 1), reg_valid_until=date(2027, 1, 1), is_mock=True)
        s.add(p)
        s.flush()
        for ref, days_ago, status, cat in [("TEST-CMP-1", 200, "under_scrutiny", "possession_delay"),
                                            ("TEST-CMP-2", 50, "filed", "refund"),
                                            ("TEST-CMP-3", 5, "filed", "structural_defect")]:
            c = Complaint(ref_no=ref, project_id=p.id, promoter_id=pr.id, form="A", category=cat, summary=f"{cat} test",
                          district="Rajkot", filed_on=AS_OF - timedelta(days=days_ago), status=status, is_mock=True)
            s.add(c)
            s.flush()
            s.add(ComplaintEvent(complaint_id=c.id, at=c.filed_on, status="filed", note="Complaint registered"))
        s.commit()
    yield factory
    engine.dispose()


def _repo(s, username: str | None) -> Repository:
    if username is None:
        return Repository(s, Principal.anonymous())
    return Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == username))))


def test_reasons_points_and_order(Session):
    with Session() as s:
        out = triage(_repo(s, "officer_state"), "en", as_of=AS_OF)
        mine = {i["ref_no"]: i for i in out["items"] if i["ref_no"].startswith("TEST-")}
        one, two, three = mine["TEST-CMP-1"], mine["TEST-CMP-2"], mine["TEST-CMP-3"]
        r1 = {r["code"]: r["points"] for r in one["reasons"]}
        assert r1["overdue"] == 50 and one["days_left"] == -140  # 140 days past, Section 29(4)
        assert r1["group"] == 15 and r1["project_delay"] == 10  # 2 others; project 516 days past its date
        assert "Section 29(4)" in one["reasons"][0]["text"]
        r2 = {r["code"]: r["points"] for r in two["reasons"]}
        assert r2["due_soon"] == 25 and r2["not_scrutinised"] == 10 and two["days_left"] == 10
        assert "due_soon" not in {r["code"] for r in three["reasons"]} and "not_scrutinised" not in {r["code"] for r in three["reasons"]}
        assert one["sections"] == ["Section 18", "Section 19"] and three["sections"] == ["Section 14"]
        scores = [i["score"] for i in out["items"]]
        assert scores == sorted(scores, reverse=True)
        group = next(g for g in out["groups"] if g["project"] == "Test Desk Towers")
        assert group["complaints"] == ["TEST-CMP-1", "TEST-CMP-2", "TEST-CMP-3"]
        assert out["summary"]["open"] == len(out["items"])
        s.rollback()


def test_officers_only_and_district(Session):
    with Session() as s:
        for u in (None, "citizen_01", "dev_001", "agent_001"):
            with pytest.raises(AccessDenied):
                triage(_repo(s, u))
        surat = triage(_repo(s, "officer_surat"), as_of=AS_OF, district="Rajkot")
        assert {i["district"] for i in surat["items"]} == {"Surat"}
        test_id = s.scalar(select(Complaint.id).where(Complaint.ref_no == "TEST-CMP-1"))
        assert brief(_repo(s, "officer_surat"), test_id) is None  # Rajkot complaint, Surat officer
        s.rollback()


def test_brief_contents(Session):
    with Session() as s:
        cid = s.scalar(select(Complaint.id).where(Complaint.ref_no == "TEST-CMP-1"))
        b = brief(_repo(s, "officer_state"), cid, "en", as_of=AS_OF)
        assert b["complaint"]["due_by"] == (AS_OF - timedelta(days=200) + timedelta(days=60)).isoformat()
        assert [x["section"] for x in b["sections"]] == ["18", "19"] and "29(4)" in b["forum_law"]
        assert {o["ref_no"] for o in b["other_open"]} == {"TEST-CMP-2", "TEST-CMP-3"}
        assert b["project"]["glance"] and b["points_to_put"]
        decided = s.scalar(select(Complaint).where(Complaint.category == "possession_delay", Complaint.status == "disposed"))
        assert b["precedents"]["category_decided"] >= 1 and sum(b["precedents"]["category_outcomes"].values()) == b["precedents"]["category_decided"]
        assert decided is not None
        s.rollback()


def test_status_updates_reach_the_buyers_timeline(Session):
    with Session() as s:
        officer = _repo(s, "officer_state")
        c = s.scalar(select(Complaint).where(Complaint.ref_no == "TEST-CMP-2"))
        with pytest.raises(ValueError):
            update_status(officer, c.id, "disposed", today=AS_OF)  # filed cannot jump to disposed
        with pytest.raises(ValueError):
            update_status(officer, c.id, "hearing_scheduled", hearing_on=AS_OF - timedelta(days=1), today=AS_OF)
        out = update_status(officer, c.id, "hearing_scheduled", hearing_on=AS_OF + timedelta(days=14),
                            note="Both parties to attend", today=AS_OF)
        assert out["status"] == "hearing_scheduled" and "Hearing on 2026-06-15" in out["timeline"][-1]["note"]
        with pytest.raises(ValueError):
            update_status(officer, c.id, "disposed", today=AS_OF)  # needs an outcome
        done = update_status(officer, c.id, "disposed", outcome="allowed", today=AS_OF)
        assert done["outcome"] == "allowed" and c.closed_on == AS_OF
        # the same timeline an authorised viewer of the complaint sees
        shown = Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == "officer_state")))).complaint_status("TEST-CMP-2")
        assert [e["status"] for e in shown["events"]][-2:] == ["hearing_scheduled", "disposed"]
        with pytest.raises(AccessDenied):
            update_status(_repo(s, "dev_001"), c.id, "withdrawn")
        s.rollback()


def test_chat_and_api(Session):
    with Session() as s:
        out = respond("Which complaints are overdue?", ChatState(), _repo(s, "officer_state")).to_dict()
        assert out["intent"] == "complaint_triage" and out["cards"][0]["type"] == "triage"
        assert respond("Which complaints are overdue?", ChatState(), _repo(s, "dev_001")).intent != "complaint_triage"
        officer = issue_token(s.scalar(select(User).where(User.username == "officer_state")))
        cid = s.scalar(select(Complaint.id).where(Complaint.ref_no == "TEST-CMP-3"))
        s.rollback()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    h = {"Authorization": f"Bearer {officer}"}
    assert client.get("/api/gujrera/complaints/triage").status_code == 403
    assert client.get("/api/gujrera/complaints/triage", headers=h).json()["summary"]["open"] > 0
    assert client.get(f"/api/gujrera/complaints/{cid}/brief", headers=h).json()["complaint"]["ref_no"] == "TEST-CMP-3"
    bad = client.post(f"/api/gujrera/complaints/{cid}/status", json={"status": "disposed"}, headers=h)
    assert bad.status_code == 400
    ok = client.post(f"/api/gujrera/complaints/{cid}/status", json={"status": "under_scrutiny"}, headers=h)
    assert ok.status_code == 200 and ok.json()["status"] == "under_scrutiny"
