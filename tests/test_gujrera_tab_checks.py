"""Regressions found by checking every tab: complaint categories, samples on public records."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gujrera.api.routes import get_session, router
from gujrera.complaints.rules import classify
from gujrera.db.models import Project, Promoter
from gujrera.db.session import init_db, make_engine, session_factory


@pytest.mark.parametrize("story,expected", [
    ("The possession has been delayed beyond the promised date in the agreement.", "possession_delay"),
    ("પઝેશનમાં વિલંબ થયો છે, કરાર મુજબ તારીખ વીતી ગઈ", "possession_delay"),
    ("Builder is demanding extra charges not in the agreement", "agreement_violation"),
    ("બિલ્ડરે કરારનો ભંગ કર્યો", "agreement_violation"),
    ("अनुबंध का उल्लंघन किया", "agreement_violation"),
    ("No agreement was signed but they took 30%", "agreement_violation"),
])
def test_the_word_agreement_alone_is_not_a_breach(story, expected):
    assert classify(story)[0] == expected


@pytest.fixture()
def public_client(tmp_path: Path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'p.sqlite').as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        prom = Promoter(name="Promoter not in imported records", promoter_type="unknown", district="Surat",
                        source_url="https://gujrera.gujarat.gov.in/", is_mock=False)
        s.add(prom)
        s.flush()
        s.add(Project(rera_no="PR/GJ/SURAT/SURAT CITY/SUDA/RAA70001/010120", name="REAL TOWER", promoter_id=prom.id,
                      district="Surat", taluka="Surat City", project_type="residential", status="ongoing", units=10,
                      reg_date=date(2020, 1, 1), proposed_completion=date(2029, 4, 30), reg_valid_until=date(2029, 4, 30),
                      source_url="https://gujrera.gujarat.gov.in/", is_mock=False))
        s.commit()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    engine.dispose()


def test_public_records_get_honest_samples(public_client):
    c = public_client
    items = c.get("/api/gujrera/trust/samples").json()["items"]
    assert {i["kind"] for i in items} == {"not_found", "no_number"}
    assert all("REAL TOWER" not in i["text"] for i in items)  # never built around a real project
    for it in items:
        assert c.post("/api/gujrera/trust/text", json={"text": it["text"]}).json()["verdict"] in it["expected"]
    agr = c.get("/api/gujrera/agreement/samples").json()
    assert agr["note"] and "made-up project" in agr["note"]


@pytest.fixture()
def demo_repo(tmp_path: Path):
    from gujrera.db.repository import Principal, Repository
    from gujrera.ingest.mock_generator import MockConfig, generate

    engine = make_engine(f"sqlite:///{(tmp_path / 'd.sqlite').as_posix()}")
    init_db(engine)
    with session_factory(engine)() as s:
        generate(s, MockConfig())
        s.commit()
        yield Repository(s, Principal.anonymous(), audit_sink=lambda _r: None)
    engine.dispose()


def _say_all(repo, messages):
    from gujrera.chat.orchestrator import ChatState, respond

    state, out = ChatState(), []
    for m in messages:
        out.append(respond(m, state, repo).to_dict())
    return out, state


@pytest.mark.parametrize("question,intent", [
    ("Approved projects in Surat", "district_projects"),
    ("When will I get possession of Mangal Square?", "possession"),
    ("Can a builder take 20% before the agreement?", "legal"),
])
def test_a_new_question_leaves_an_open_complaint_form(demo_repo, question, intent):
    out, state = _say_all(demo_repo, ["I want to file a complaint", question])
    assert out[-1]["intent"] == intent and out[-1]["text"].startswith("I've set your complaint form aside")
    assert state.complaint is None


def test_answers_stay_in_the_complaint_form(demo_repo):
    out, state = _say_all(demo_repo, ["I want to file a complaint", "Mangal Square",
                                      "The possession has been delayed beyond the promised date. Why is it late?",
                                      "Refund with interest", "Test Buyer"])
    assert all(r["intent"].startswith("complaint_") for r in out) and state.complaint is not None
