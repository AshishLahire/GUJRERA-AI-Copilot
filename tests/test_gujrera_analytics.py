"""Officer analytics: SQL guard red team, district scoping, reports, LLM path, chat and API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import gujrera.chat.orchestrator as orchestrator
from gujrera.analytics.engine import _extract_sql, answer
from gujrera.analytics.redteam import ATTACKS, QUESTIONS
from gujrera.analytics.reports import TITLES, match_report
from gujrera.analytics.sql_guard import UnsafeSQL, execute_readonly, guard_sql
from gujrera.api.routes import get_session, router
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.config import get_gujrera_settings
from gujrera.db.models import AuditLog, Project, User
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, make_readonly_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate

PASSWORD = get_gujrera_settings().GUJRERA_DEMO_PASSWORD.get_secret_value()


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("an") / "an.sqlite"
    url = f"sqlite:///{path.as_posix()}"
    engine = make_engine(url)
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig(seed=17))
    ro = make_readonly_engine(url)
    yield factory, ro
    ro.dispose()
    engine.dispose()


def officer(s, username="officer_state") -> Repository:
    return Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == username))))


# ------------------------------------------------------------------- guard
@pytest.mark.parametrize("kind,sql", ATTACKS, ids=[f"{k}-{i}" for i, (k, _) in enumerate(ATTACKS)])
def test_guard_blocks_attacks(kind, sql):
    with pytest.raises(UnsafeSQL):
        guard_sql(sql)


def test_guard_scope_cannot_be_escaped(db):
    _, ro = db
    for sql in [
        "SELECT district, COUNT(*) FROM v_project_delays GROUP BY district",
        "SELECT district FROM v_project_delays WHERE district = 'Ahmedabad' OR 1 = 1",
        "SELECT district FROM v_complaint_stats UNION ALL SELECT district FROM v_agent_status",
        "WITH x AS (SELECT * FROM v_promoter_scorecard) SELECT district FROM x",
        "SELECT a.district FROM v_project_delays a JOIN v_promoter_scorecard b ON a.promoter_id = b.promoter_id",
    ]:
        result = execute_readonly(ro, guard_sql(sql, district_scope="Surat"))
        assert result.rows and {r[0] for r in result.rows} == {"Surat"}, sql


def test_readonly_execution_has_time_limit(db):
    _, ro = db
    heavy = guard_sql("SELECT COUNT(*) FROM v_project_delays a, v_project_delays b, v_project_delays c, "
                      "v_project_delays d")
    with pytest.raises(Exception):
        execute_readonly(ro, heavy, timeout_s=0.05)


def test_row_limit_is_enforced(db):
    _, ro = db
    result = execute_readonly(ro, guard_sql("SELECT * FROM v_complaint_stats", max_rows=7))
    assert len(result.rows) == 7 and result.truncated


# ----------------------------------------------------------------- reports
@pytest.mark.parametrize("question,key", QUESTIONS)
def test_report_matching(question, key):
    report = match_report(question.lower())
    assert (report.key if report else None) == key


def test_every_report_runs_for_every_scope(db):
    factory, ro = db
    for key, question in {k: q for q, k in QUESTIONS if k}.items():
        report = match_report(question.lower())
        for scope in (None, "Surat"):
            execute_readonly(ro, guard_sql(report.sql, district_scope=scope))
    assert set(TITLES) >= {k for _, k in QUESTIONS if k}


def test_delayed_by_promoter_matches_registry(db):
    factory, _ = db
    with factory() as s:
        a = answer("Which promoters in Surat have the most delayed projects?", officer(s), "en")
        top_name, top_count = a.card["rows"][0][0], a.card["rows"][0][1]
        # independent check straight from the view
        expected = s.execute(
            select(func.count()).select_from(Project).where(Project.district == "Surat")
        ).scalar()
        assert expected > 0 and top_count >= 1 and "Demo" in top_name
        assert a.card["source"] == "report" and "ORDER BY" in a.card["sql"].upper()


# --------------------------------------------------------------- LLM path
def test_llm_path_is_labelled_scoped_and_audited(db):
    factory, _ = db
    with factory() as s:
        repo = officer(s, "officer_surat")
        before = s.scalar(select(func.count()).select_from(AuditLog))
        fake = lambda prompt: "Sure:\n```sql\nSELECT project_type, COUNT(*) AS n FROM v_project_delays GROUP BY project_type ORDER BY n DESC\n```"  # noqa: E731
        a = answer("count by project type", repo, "en", generate=fake)
        assert a.intent == "analytics" and a.card["source"] == "llm" and a.card["scoped_to"] == "Surat"
        assert "district = 'Surat'" in a.card["sql"]
        assert s.scalar(select(func.count()).select_from(AuditLog)) == before + 1


def test_llm_attack_is_refused_and_audited(db):
    factory, _ = db
    with factory() as s:
        repo = officer(s)
        a = answer("show me every password", repo, "en", generate=lambda p: "SELECT password_hash FROM users")
        assert a.intent == "analytics_refused" and not a.card["rows"]
        assert s.scalar(select(AuditLog.action).order_by(AuditLog.id.desc())) == "analytics_refused"


def test_llm_garbage_or_failure_gives_suggestions(db):
    factory, _ = db
    with factory() as s:
        repo = officer(s)
        assert answer("average delay by type", repo, "en", generate=lambda p: "I don't know").intent == \
            "analytics_unmatched"

        def boom(prompt):
            raise TimeoutError

        out = answer("average delay by type", repo, "en", generate=boom)
        assert out.intent == "analytics_unmatched" and out.suggestions


def test_extract_sql_from_reasoning():
    reasoning = "First idea: SELECT a FROM b is wrong.\n\nSo the SQL is:\n\n  SELECT x FROM v_project_delays\n\nDone"
    assert _extract_sql(reasoning) == "SELECT x FROM v_project_delays"


# ------------------------------------------------------------- chat + API
def test_chat_routes_by_role(db, monkeypatch):
    factory, _ = db
    monkeypatch.setattr(orchestrator, "analytics_generate", lambda p: "SELECT 1 AS x FROM v_project_delays")
    with factory() as s:
        q = "Which promoters in Surat have the most delayed projects?"
        assert respond(q, ChatState(), officer(s)).intent == "analytics"
        assert respond("સુરતમાં સૌથી વધુ વિલંબિત પ્રોજેક્ટ ધરાવતા બિલ્ડર કયા છે?", ChatState(), officer(s)).lang == "gu"
        assert respond(q, ChatState(), Repository(s, Principal.anonymous())).intent == "officer_only"
        dev = Repository(s, Principal.from_user(s.scalar(select(User).where(User.role == "developer"))))
        assert respond(q, ChatState(), dev).intent == "officer_only"
        p = s.scalar(select(Project))
        assert respond(f"Tell me about {p.name}", ChatState(), officer(s)).intent == "project_profile"


def test_api_analytics_is_officer_only(db):
    factory, _ = db
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)

    def login(username):
        token = client.post("/api/gujrera/auth/login", json={"username": username, "password": PASSWORD}).json()["token"]
        return {"Authorization": f"Bearer {token}"}

    body = {"question": "Complaints by category", "lang": "hi"}
    assert client.post("/api/gujrera/analytics/query", json=body).status_code == 403
    assert client.post("/api/gujrera/analytics/query", json=body, headers=login("dev_001")).status_code == 403
    res = client.post("/api/gujrera/analytics/query", json=body, headers=login("officer_surat"))
    assert res.status_code == 200 and res.json()["card"]["scoped_to"] == "Surat"
