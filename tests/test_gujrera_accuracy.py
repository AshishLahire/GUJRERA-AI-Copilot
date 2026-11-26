"""Accuracy console: feedback and its review queue, the test set (generated, imported, from feedback), runs."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gujrera.accuracy import judge
from gujrera.api.routes import get_session, router
from gujrera.db.models import AuditLog, Complaint, TestCase
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.enforcement import ensure_tables
from gujrera.ingest.mock_generator import MockConfig, generate


def test_judging():
    case = TestCase(question="q", lang="gu", expect_intent="possession|project_profile",
                    must_contain=json.dumps(["૧૫ સપ્ટેમ્બર 2026"]), must_not_contain=json.dumps(["could not find"]),
                    expected_source="PR/GJ")
    good = {"intent": "possession", "lang": "gu", "text": "15 સપ્ટેમ્બર 2026 ના રોજ", "sources": [{"id": "PR/GJ/X"}]}
    assert judge(case, good) == (True, [])  # Gujarati digits match ASCII digits
    ok, problems = judge(case, {"intent": "legal", "lang": "en", "text": "I could not find it", "sources": []})
    assert ok is False and len(problems) == 5
    assert judge(TestCase(question="q", must_contain="[]", must_not_contain="[]"), good) == (None, [])  # review by hand


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    base: Path = tmp_path_factory.mktemp("acc")
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
    c = TestClient(app)
    c.factory = factory
    yield c
    engine.dispose()


def _auth(c, user):
    tok = c.post("/api/gujrera/auth/login", json={"username": user, "password": "gujrera-demo"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_only_state_officers_use_the_console_but_anyone_gives_feedback(env):
    c = env
    for user in ("officer_surat", "citizen_01"):
        h = _auth(c, user)
        for path in ("/api/gujrera/admin/tests", "/api/gujrera/admin/feedback", "/api/gujrera/admin/tests/runs"):
            assert c.get(path, headers=h).status_code == 403
        assert c.post("/api/gujrera/admin/tests/run", headers=h).status_code == 403
    r = c.post("/api/gujrera/feedback", json={"question": "Is Mangal Square delayed?", "answer": "Yes", "rating": "up"})
    assert r.status_code == 200 and r.json()["status"] == "noted"  # a thumbs up needs no review
    assert c.post("/api/gujrera/feedback", json={"question": "x", "rating": "meh"}).status_code == 400


def test_feedback_becomes_a_test_case(env):
    c = env
    h = _auth(c, "officer_state")
    fb = c.post("/api/gujrera/feedback", headers=_auth(c, "citizen_01"),
                json={"question": "When will I get possession of Xyz Towers?", "answer": "I could not find it",
                      "rating": "down", "reason": "should_have_found", "comment": "It is on the portal",
                      "intent": "not_found", "lang": "en", "sources": []}).json()
    queue = c.get("/api/gujrera/admin/feedback", headers=h).json()
    assert queue["counts"]["new"] >= 1 and queue["reasons"]["should_have_found"] >= 1
    item = next(f for f in queue["feedback"] if f["id"] == fb["id"])
    assert item["role"] == "citizen" and item["comment"] == "It is on the portal"
    case = c.post(f"/api/gujrera/admin/feedback/{fb['id']}/to-test", headers=h,
                  json={"question": "ignored", "must_not_contain": "could not find"}).json()
    assert case["origin"] == "feedback" and case["question"] == "When will I get possession of Xyz Towers?"
    assert case["must_not_contain"] == ["could not find"] and "should_have_found" in case["note"]
    assert c.get("/api/gujrera/admin/feedback", headers=h).json()["counts"].get("added") == 1
    other = c.post("/api/gujrera/feedback", json={"question": "tell me a joke", "answer": "…", "rating": "down"}).json()
    assert c.post(f"/api/gujrera/admin/feedback/{other['id']}/dismiss", headers=h).json()["status"] == "dismissed"


def test_import_generate_and_run(env):
    c = env
    h = _auth(c, "officer_state")
    gen = c.post("/api/gujrera/admin/tests/generate", headers=h).json()
    assert gen["generated"] == 300 and gen["by_lang"] == {"gu": 100, "hi": 100, "en": 100}
    again = c.post("/api/gujrera/admin/tests/generate", headers=h).json()
    assert again["generated"] == 300  # replaces, does not pile up
    csv_text = ("question,language,role,must_contain,expected_answer,category\n"
                "Can a builder take 20% before the agreement?,en,citizen,Section 13,,law\n"
                "Which promoters have the most delayed projects?,en,officer,,A ranked list,officer reports\n"
                ",en,citizen,,,bad row\n"
                "I want to file a complaint,en,citizen,,,complaints\n")
    imp = c.post("/api/gujrera/admin/tests/import", headers=h, files={"file": ("dept_tests.csv", csv_text.encode())}).json()
    assert imp["added"] == 3 and imp["rejected"] == 1 and imp["errors"][0]["row"] == 4
    assert c.post("/api/gujrera/admin/tests/import", headers=h, files={"file": ("x.txt", b"q")}).status_code == 400
    listing = c.get("/api/gujrera/admin/tests", headers=h).json()
    assert listing["by_origin"] == {"generated": 300, "imported": 3, "feedback": 1}
    assert listing["by_role"]["officer"] == 1

    with c.factory() as s:
        complaints_before = s.scalar(select(func.count()).select_from(Complaint))
        audit_before = s.scalar(select(func.count()).select_from(AuditLog))
    run = c.post("/api/gujrera/admin/tests/run", headers=h).json()["run"]
    assert c.post("/api/gujrera/admin/tests/run", headers=h).status_code in (200, 400)  # one run at a time
    deadline = time.time() + 600
    while True:
        d = c.get(f"/api/gujrera/admin/tests/runs/{run['id']}", headers=h).json()
        if d["run"]["status"] != "running" or time.time() > deadline:
            break
        time.sleep(1)
    r = d["run"]
    assert r["status"] == "done" and r["total"] == 304 and r["done"] == 304
    assert r["unjudged"] == 2  # the model-answer-only officer case and the complaint case are shown for review
    assert r["summary"]["lang"]["gu"] == {"total": 100, "judged": 100, "passed": 100}
    assert r["summary"]["origin"]["generated"]["passed"] == 300
    fails = d["results"]
    assert any("could not find" in p for x in fails for p in x["problems"])  # the feedback case fails as it should
    assert r["accuracy"] is not None and r["accuracy"] >= 99
    review = c.get(f"/api/gujrera/admin/tests/runs/{run['id']}?show=unjudged", headers=h).json()["results"]
    assert {x["category"] for x in review} == {"officer reports", "complaints"} and review[0]["answer"]
    with c.factory() as s:  # a run leaves no trace in the data or the audit log
        assert s.scalar(select(func.count()).select_from(Complaint)) == complaints_before
        assert s.scalar(select(func.count()).select_from(AuditLog)) <= audit_before + 3
    csv_out = c.get(f"/api/gujrera/admin/tests/runs/{run['id']}/csv", headers=h).text
    assert csv_out.lstrip("﻿").startswith("case,question") and csv_out.count("\n") >= 305
    assert c.get("/api/gujrera/admin/tests/runs", headers=h).json()["runs"][0]["id"] == run["id"]
    s_ = r["summary"]  # the POC measures a run adds
    assert s_["consistency"]["checked"] == 50 and s_["consistency"]["pct"] >= 98
    assert s_["outcomes"]["all"]["total"] > 0 and s_["latency_by_role"]["citizen"]["n"] > 0


def test_an_older_database_gets_the_settings_table(tmp_path):
    from sqlalchemy import inspect, text

    engine = make_engine(f"sqlite:///{(tmp_path / 'old.sqlite').as_posix()}")
    init_db(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE app_settings"))
    ensure_tables(engine)
    assert "app_settings" in inspect(engine).get_table_names()
    engine.dispose()


def test_poc_measures(env):
    from gujrera.accuracy import outcome

    assert [outcome(i) for i in ("possession", "not_found", "need_entity", "greeting", "analytics")] == \
        ["answered", "unanswered", "clarified", None, "answered"]
    c = env
    h = _auth(c, "officer_state")
    for q in ("When will I get possession of Mangal Square?", "When will I get possession of Qwzx Plaza?", "hello"):
        c.post("/api/gujrera/chat", json={"message": q})
    c.post("/api/gujrera/analytics/query", headers=h, json={"question": "Projects and delays by district"})
    with c.factory() as s:  # the outcome and time are kept, never the question
        detail = s.scalars(select(AuditLog.detail).where(AuditLog.action == "chat_reply")).all()
    assert detail and all("Mangal" not in d and '"ms"' in d for d in detail)
    m = c.get("/api/gujrera/admin/poc-metrics", headers=h).json()
    citizen = m["live"]["outcomes"]["citizen"]
    assert citizen["total"] >= 2 and citizen["answered"] >= 1 and citizen["unanswered"] >= 1  # "hello" is left out
    assert m["live"]["reports"]["n"] >= 1 and m["report_speedup"] is None
    assert m["test_run"]["consistency"]["checked"] == 50
    m = c.post("/api/gujrera/admin/poc-metrics/manual-time", headers=h, json={"minutes": 45}).json()
    assert m["manual_report_minutes"] == 45 and m["report_speedup"] > 1
    assert c.post("/api/gujrera/admin/poc-metrics/manual-time", headers=h, json={"minutes": -3}).status_code == 400
    assert c.get("/api/gujrera/admin/poc-metrics", headers=_auth(c, "officer_surat")).status_code == 403
