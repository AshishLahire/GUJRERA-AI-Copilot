"""Quarterly report assistant: drafts, checks (Sections 11 and 4(2)(l)(D)), filing, access."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.auth import hash_password, issue_token
from gujrera.db.models import Project, ProjectProgress, Promoter, QprSubmission, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.selfservice.qpr import check, draft, due_date, overview, submit

AS_OF = date(2026, 11, 17)
GOOD = {"units_booked": 20, "garages_booked": 5, "collected_total": 2e7, "deposited_total": 1.5e7,
        "withdrawn_total": 1e7, "project_cost": 1e8}


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("qpr") / "q.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        pr = Promoter(name="Test QPR Builders", district="Rajkot", is_mock=True)
        s.add(pr)
        s.flush()
        s.add(User(username="dev_qpr", role="developer", promoter_id=pr.id, password_hash=hash_password("x", iterations=1000)))
        p = Project(rera_no="PR/GJ/RAJKOT/RAJKOT/RUDA/TEST00004/010124", promoter_id=pr.id, name="Test QPR Heights",
                    district="Rajkot", project_type="residential", status="ongoing", units=80, reg_date=date(2025, 1, 1),
                    proposed_completion=date(2027, 6, 30), reg_valid_until=date(2027, 12, 31), is_mock=True)
        s.add(p)
        s.flush()
        for q, pct, filed in [("2025-Q1", 5, date(2025, 4, 10)), ("2025-Q2", 10, date(2025, 7, 10)),
                              ("2025-Q3", None, None), ("2025-Q4", 20, date(2026, 1, 12)),
                              ("2026-Q1", 25, date(2026, 4, 10)), ("2026-Q2", 30, date(2026, 7, 14))]:
            s.add(ProjectProgress(project_id=p.id, quarter=q, percent_complete=pct or 0, due_on=due_date(q), filed_on=filed, is_mock=True))
        s.commit()
    yield factory
    engine.dispose()


def _repo(s, username: str | None) -> Repository:
    if username is None:
        return Repository(s, Principal.anonymous())
    return Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == username))))


def _pid(s) -> int:
    return s.scalar(select(Project.id).where(Project.name == "Test QPR Heights"))


def test_overview_and_draft(Session):
    with Session() as s:
        repo = _repo(s, "dev_qpr")
        projects = overview(repo, as_of=AS_OF)["projects"]
        assert [p["name"] for p in projects] == ["Test QPR Heights"]  # own ongoing projects only
        p = projects[0]
        assert [o["quarter"] for o in p["overdue"]] == ["2025-Q3"] and p["to_file"][:2] == ["2025-Q3", "2026-Q3"]
        assert p["next_due"] == {"quarter": "2026-Q4", "due_on": "2027-01-15"}
        d = draft(repo, _pid(s), "2026-Q3", as_of=AS_OF)
        assert d["previous"] == {"quarter": "2026-Q2", "percent": 30} and d["prefill"]["percent_complete"] == 30
        with pytest.raises(ValueError):
            draft(repo, _pid(s), "2026-Q4", as_of=AS_OF)  # quarter not over
        for other in ("dev_001", "officer_state", "citizen_01", None):
            with pytest.raises(AccessDenied):
                draft(_repo(s, other), _pid(s), "2026-Q3", as_of=AS_OF)


def _codes(issues, level="error"):
    return {i["code"] for i in issues if i["level"] == level}


def test_checks(Session):
    with Session() as s:
        repo, pid = _repo(s, "dev_qpr"), _pid(s)
        ok = check(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 34}, as_of=AS_OF)
        assert not _codes(ok)
        assert _codes(check(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 28}, as_of=AS_OF)) == {"percent_down"}
        # back-filled 2025-Q3 must sit between 10% (2025-Q2) and 20% (2025-Q4)
        assert "percent_above_later" in _codes(check(repo, pid, "2025-Q3", {**GOOD, "percent_complete": 25}, as_of=AS_OF))
        backfill = check(repo, pid, "2025-Q3", {**GOOD, "percent_complete": 15, "withdrawn_total": 1e7}, as_of=AS_OF)
        assert not _codes(backfill) and "pace" not in _codes(backfill, "warning")  # later reports show the pace
        assert "units" in _codes(check(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 34, "units_booked": 81}, as_of=AS_OF))
        assert "deposit_short" in _codes(check(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 34, "deposited_total": 1.3e7}, as_of=AS_OF))
        assert "withdraw_over" in _codes(check(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 34, "withdrawn_total": 1.6e7, "deposited_total": 1.5e7}, as_of=AS_OF))
        ahead = check(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 30, "withdrawn_total": 3.5e7, "deposited_total": 3.6e7,
                                             "collected_total": 4e7}, as_of=AS_OF)
        msg = next(i["text"] for i in ahead if i["code"] == "withdraw_ahead")
        assert "₹3,00,00,000" in msg and "engineer, an architect and a chartered accountant" in msg
        assert "account_missing" in _codes(check(repo, pid, "2026-Q3", {"percent_complete": 34, "units_booked": 20}, as_of=AS_OF))
        warn = check(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 31}, as_of=AS_OF)  # 1 point a quarter: late finish
        assert {"pace", "late"} <= _codes(warn, "warning")
        assert any("Section 6" in c["id"] for i in warn if i["code"] == "pace" for c in i["citations"])
        assert "percent_jump" in _codes(check(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 60}, as_of=AS_OF), "warning")


def test_submit(Session):
    with Session() as s:
        repo, pid = _repo(s, "dev_qpr"), _pid(s)
        bad = submit(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 28}, as_of=AS_OF)
        assert bad["filed"] is False and s.scalar(select(QprSubmission.id)) is None
        res = submit(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 34}, as_of=AS_OF)
        assert res["filed"] and res["receipt"].startswith(f"QPR-{pid:04d}-2026-Q3") and res["late"]
        row = s.scalar(select(ProjectProgress).where(ProjectProgress.project_id == pid, ProjectProgress.quarter == "2026-Q3"))
        assert row.filed_on == AS_OF and row.percent_complete == 34
        back = submit(repo, pid, "2025-Q3", {**GOOD, "percent_complete": 15, "withdrawn_total": 1e7}, as_of=AS_OF)
        assert back["filed"] and s.scalar(select(ProjectProgress.filed_on).where(
            ProjectProgress.project_id == pid, ProjectProgress.quarter == "2025-Q3")) == AS_OF
        with pytest.raises(ValueError):
            submit(repo, pid, "2026-Q3", {**GOOD, "percent_complete": 35}, as_of=AS_OF)  # already filed
        assert overview(repo, as_of=AS_OF)["projects"][0]["overdue"] == []
        s.rollback()


def test_api(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    with Session() as s:
        mine = issue_token(s.scalar(select(User).where(User.username == "dev_qpr")))
        other = issue_token(s.scalar(select(User).where(User.username == "dev_001")))
        pid = _pid(s)
    h = {"Authorization": f"Bearer {mine}"}
    assert client.get("/api/gujrera/qpr/overview").status_code == 403
    assert client.get(f"/api/gujrera/qpr/{pid}/2025-Q3/draft", headers={"Authorization": f"Bearer {other}"}).status_code == 403
    assert client.get(f"/api/gujrera/qpr/{pid}/2025-Q7/draft", headers=h).status_code == 422
    issues = client.post(f"/api/gujrera/qpr/{pid}/2025-Q3/check", headers=h, json={"percent_complete": 12}).json()["issues"]
    assert "units_missing" in {i["code"] for i in issues}
