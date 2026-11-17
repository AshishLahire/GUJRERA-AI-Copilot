"""Before-you-buy project report: cited public facts, questions to ask, buyer rights."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.db.models import Approval, Project, ProjectProgress, Promoter
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.tools.project_report import build_report

AS_OF = date(2026, 6, 1)


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("report") / "r.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        pr = Promoter(name="Test Report Builders", district="Rajkot", is_mock=True)
        s.add(pr)
        s.flush()
        p = Project(rera_no="PR/GJ/RAJKOT/RAJKOT/RUDA/TEST00002/010124", promoter_id=pr.id, name="Test Report Heights",
                    district="Rajkot", project_type="residential", status="ongoing", units=60, reg_date=date(2024, 1, 1),
                    proposed_completion=date(2026, 1, 1), revised_completion=date(2027, 3, 1), actual_completion=None,
                    reg_valid_until=date(2026, 9, 1), is_mock=True)
        s.add(p)
        s.flush()
        for q, pct, due, filed in [("2025-Q1", 30, date(2025, 4, 15), date(2025, 4, 10)),
                                   ("2025-Q2", 35, date(2025, 7, 15), date(2025, 7, 30)),
                                   ("2025-Q3", 35, date(2025, 10, 15), None),
                                   ("2025-Q4", 35, date(2026, 1, 15), None)]:
            s.add(ProjectProgress(project_id=p.id, quarter=q, percent_complete=pct, due_on=due, filed_on=filed, is_mock=True))
        s.add(Approval(project_id=p.id, kind="fire_noc", authority="Fire Department", status="pending", is_mock=True))
        s.add(Approval(project_id=p.id, kind="building_permission", authority="RUDA", status="granted", is_mock=True))
        s.commit()
    yield factory
    engine.dispose()


def _project(s, name: str) -> Project:
    return s.scalar(select(Project).where(Project.name == name))


def test_report_for_a_delayed_project(Session):
    with Session() as s:
        repo = Repository(s, Principal.anonymous())
        rep = build_report(repo, _project(s, "Test Report Heights").id, "en", as_of=AS_OF)
        keys = [g["key"] for g in rep["glance"]]
        assert {"reg_ending", "extended", "overdue", "progress", "qpr_missing", "approvals_pending"} <= set(keys)
        assert rep["overall"] == "bad"
        text = " ".join(g["text"] for g in rep["glance"])
        assert "1 January 2026 to 1 March 2027, 424 days later" in text  # moved, not "late by"
        assert "passed 151 days ago" in text
        assert [q["state"] for q in rep["progress"]] == ["on_time", "late", "missing", "missing"]
        qkeys = [q["key"] for q in rep["questions"]]
        assert qkeys[:4] == ["q_approval", "q_qpr", "q_delay", "q_reg"] and qkeys[-2:] == ["q_account", "q_carpet"]
        assert {c["id"] for r in rep["rights"] for c in r["citations"]} >= {
            "RERA Act, 2016, Section 13", "RERA Act, 2016, Section 18", "RERA Act, 2016, Section 19"}
        for item in rep["glance"] + rep["questions"] + rep["rights"]:
            assert item["citations"] and all(c["id"] for c in item["citations"])


def test_completed_project_and_languages(Session):
    with Session() as s:
        repo = Repository(s, Principal.anonymous())
        done = s.scalar(select(Project).where(Project.status == "completed", Project.actual_completion > Project.proposed_completion))
        rep = build_report(repo, done.id, "en", as_of=AS_OF)
        assert rep["glance"][0]["key"] == "completed_late" and "q_delay" not in [q["key"] for q in rep["questions"]]
        gu = build_report(repo, _project(s, "Test Report Heights").id, "gu", as_of=AS_OF)
        hi = build_report(repo, _project(s, "Test Report Heights").id, "hi", as_of=AS_OF)
        assert any("કલમ 11" in q["text"] for q in gu["questions"]) and any("धारा 11" in q["text"] for q in hi["questions"])


def test_report_has_no_personal_data(Session):
    with Session() as s:
        repo = Repository(s, Principal.anonymous())
        for p in s.scalars(select(Project).limit(40)):
            rep = build_report(repo, p.id, "en")
            assert set(rep["complaints"]) == {"total", "open", "by_category"}  # counts only
            flat = repr(rep).lower()
            assert "complainant" not in flat and "mobile" not in flat and "@" not in flat


def test_chat_and_api(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    with Session() as s:
        pid = _project(s, "Test Report Heights").id
        repo = Repository(s, Principal.anonymous())
        out = respond("Give me a before you buy report for Test Report Heights", ChatState(), repo).to_dict()
        assert out["intent"] == "project_report" and out["cards"][0]["type"] == "report" and out["cards"][0]["project_id"] == pid
        assert respond("Show the quarterly progress report of Test Report Heights", ChatState(), repo).intent != "project_report"
        assert respond("I want to report a complaint against Test Report Heights", ChatState(), repo).intent != "project_report"
        prof = respond("Tell me about Test Report Heights", ChatState(), repo).to_dict()
        assert prof["cards"][0]["project_id"] == pid  # the project card links to the report
        s.rollback()
    body = client.get(f"/api/gujrera/report/project/{pid}", params={"lang": "hi"}).json()
    assert body["project"]["id"] == pid and body["lang"] == "hi" and body["questions"]
    assert client.get("/api/gujrera/report/project/999999").status_code == 404
