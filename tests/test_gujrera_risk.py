"""Project risk early warning: explainable signals, officer-only access, district scope."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gujrera.analytics.risk import HIGH, score_projects, summary
from gujrera.api.routes import get_session, router
from gujrera.auth import issue_token
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.db.models import Approval, AuditLog, Project, ProjectProgress, Promoter, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate

AS_OF = date(2026, 6, 1)


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("risk") / "r.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        # A project built to trip known signals, by a promoter with a clean record elsewhere.
        clean = Promoter(name="Test Clean Builders", district="Rajkot", is_mock=True)
        s.add(clean)
        s.flush()
        p = Project(rera_no="PR/GJ/RAJKOT/RAJKOT/RUDA/TEST00001/010124", promoter_id=clean.id, name="Test Stalled Towers",
                    district="Rajkot", project_type="residential", status="ongoing", units=40, reg_date=date(2024, 1, 1),
                    proposed_completion=date(2026, 1, 1), revised_completion=None, actual_completion=None,
                    reg_valid_until=date(2026, 9, 1), is_mock=True)
        s.add(p)
        s.flush()
        for q, pct, due, filed in [("2024-Q1", 10, date(2024, 4, 15), date(2024, 4, 10)),
                                   ("2024-Q2", 20, date(2024, 7, 15), date(2024, 7, 10)),
                                   ("2024-Q3", 22, date(2024, 10, 15), date(2024, 10, 10)),
                                   ("2024-Q4", 23, date(2025, 1, 15), date(2025, 1, 10)),
                                   ("2025-Q1", 23.5, date(2025, 4, 15), date(2025, 4, 10)),
                                   ("2025-Q2", 23.5, date(2025, 7, 15), None),
                                   ("2025-Q3", 23.5, date(2025, 10, 15), None)]:
            s.add(ProjectProgress(project_id=p.id, quarter=q, percent_complete=pct, due_on=due, filed_on=filed, is_mock=True))
        s.add(Approval(project_id=p.id, kind="fire_noc", authority="Fire", status="pending", is_mock=True))
        s.commit()
    yield factory
    engine.dispose()


def _user(s, username: str) -> Repository:
    return Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == username))))


def test_signals_and_score_for_a_known_project(Session):
    with Session() as s:
        risks = score_projects(_user(s, "officer_state"), "en", as_of=AS_OF)
        r = next(x for x in risks if x.name == "Test Stalled Towers")
        pts = {sg.code: sg.points for sg in r.signals}
        # 23.5% built at the last filed report; 100% of the time to 1 Jan 2026 used: gap >= 30
        assert pts["pace"] == 25 and r.expected_percent == 100.0
        # last five filed reports: 10 -> 23.5 over 4 quarters = 3.4 points a quarter; 76.5 points left
        # takes ~22.7 quarters from 31 Mar 2025, i.e. late 2030, far more than 12 months past 1 Jan 2026
        assert pts["projection"] == 20 and r.projected_finish.year == 2030
        assert pts["past_due"] == 5  # 151 days late
        assert pts["qpr"] == 20  # two reports overdue
        assert pts["registration"] == 10  # ends 1 Sep 2026, 92 days, far from done
        assert pts["approvals"] == 5
        assert "extended" not in pts and "promoter_orders" not in pts and "promoter_delays" not in pts
        assert r.score == min(100, sum(pts.values())) and r.band == HIGH
        assert all(sg.citations for sg in r.signals)  # every signal points at a record
        assert any("Section 11" in sg.text for sg in r.signals if sg.code == "qpr")
        assert risks == sorted(risks, key=lambda x: (-x.score, x.name))


def test_stalled_progress_is_flagged():
    from gujrera.analytics.risk import _quarter_end

    assert _quarter_end("2025-Q2") == date(2025, 6, 30) and _quarter_end("2025-Q4") == date(2025, 12, 31)


def test_text_in_gujarati_and_hindi(Session):
    with Session() as s:
        for lang, word in (("gu", "કલમ 11"), ("hi", "धारा 11")):
            r = next(x for x in score_projects(_user(s, "officer_state"), lang, as_of=AS_OF) if x.name == "Test Stalled Towers")
            assert any(word in sg.text for sg in r.signals)


def test_officers_only_and_district_scope(Session):
    with Session() as s:
        for username in ("citizen_01", "dev_001", "agent_001"):
            with pytest.raises(AccessDenied):
                score_projects(_user(s, username), "en")
        with pytest.raises(AccessDenied):
            score_projects(Repository(s, Principal.anonymous()), "en")
        surat = score_projects(_user(s, "officer_surat"), "en", district="Ahmedabad")  # asks for another district
        assert surat and {r.district for r in surat} == {"Surat"}
        state = score_projects(_user(s, "officer_state"), "en")
        ongoing = s.scalar(select(func.count()).select_from(Project).where(Project.status == "ongoing"))
        assert len(state) == ongoing and summary(state)["projects"] == ongoing
        assert s.scalar(select(AuditLog.action).order_by(AuditLog.id.desc())) == "risk_watchlist"
        s.rollback()


def test_chat_for_officers_only(Session):
    with Session() as s:
        out = respond("Which projects are at high risk?", ChatState(), _user(s, "officer_state")).to_dict()
        assert out["intent"] == "risk" and out["cards"][0]["type"] == "risk" and out["cards"][0]["summary"]
        one = respond("What is the risk for Test Stalled Towers?", ChatState(), _user(s, "officer_state")).to_dict()
        assert one["intent"] == "risk" and "Test Stalled Towers" in one["text"]
        surat = respond("show me the risk watchlist for Ahmedabad", ChatState(), _user(s, "officer_surat")).to_dict()
        assert "in Surat" in surat["text"] and "Ahmedabad" not in surat["text"]
        buyer = respond("Is Test Stalled Towers risky?", ChatState(), Repository(s, Principal.anonymous())).to_dict()
        assert buyer["intent"] != "risk" and not any(c.get("type") == "risk" for c in buyer["cards"])
        s.rollback()


def test_api_requires_officer(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    with Session() as s:
        officer = issue_token(s.scalar(select(User).where(User.username == "officer_surat")))
        dev = issue_token(s.scalar(select(User).where(User.username == "dev_001")))
    assert client.get("/api/gujrera/risk/projects").status_code == 403
    assert client.get("/api/gujrera/risk/projects", headers={"Authorization": f"Bearer {dev}"}).status_code == 403
    body = client.get("/api/gujrera/risk/projects", params={"district": "Rajkot", "lang": "gu"},
                      headers={"Authorization": f"Bearer {officer}"}).json()
    assert body["district_scope"] == "Surat" and {i["district"] for i in body["items"]} == {"Surat"}
    assert body["summary"]["projects"] == len(body["items"])
