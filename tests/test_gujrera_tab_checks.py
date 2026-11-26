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


# The use case document's officer questions: each gets the report it asks for.
@pytest.mark.parametrize("question,key", [
    ("How many projects were approved this month?", "projects_registered"),
    ("How many projects were registered this year in Surat?", "projects_registered"),
    ("What percentage of projects are delayed?", "delayed_share"),
    ("કેટલા ટકા પ્રોજેક્ટ વિલંબિત છે?", "delayed_share"),
    ("कितने प्रतिशत प्रोजेक्ट में देरी है?", "delayed_share"),
    ("Show district-wise project registration trends", "registration_trend"),
    ("Monthly trend of project registrations", "registration_trend"),
    ("જિલ્લા મુજબ પ્રોજેક્ટ નોંધણીનો ટ્રેન્ડ બતાવો", "registration_trend"),
    ("How many projects are registered in Ahmedabad?", "projects_by_district"),
])
def test_document_questions_get_their_report(question, key):
    from gujrera.analytics.reports import match_report

    assert match_report(question.lower()).key == key


def test_complaint_trends_still_go_to_the_ai_path():
    from gujrera.analytics.reports import match_report

    assert match_report("monthly trend of complaints") is None


def test_trend_and_share_reports_run_and_summarise(demo_repo):
    from gujrera.analytics.engine import answer
    from gujrera.db.repository import Principal, Repository

    officer = Repository(demo_repo.s, Principal(1, "officer"), audit_sink=lambda _r: None)
    trend = answer("Show district-wise project registration trends", officer, "en")
    assert trend.intent == "analytics" and trend.card["columns"][:3] == ["year", "registrations", "ahmedabad"]
    texts = " ".join(x.text for x in trend.sentences)
    assert "Highest:" in texts and "records go up to" in texts and "Top:" not in texts
    share = answer("What percentage of projects are delayed?", officer, "en")
    assert share.intent == "analytics" and "percent_past_completion" in share.card["columns"]
    assert any(x.text.startswith("Overall:") and "%" in x.text for x in share.sentences)
    month = answer("How many projects were approved this month?", officer, "en")
    assert month.card["columns"] == ["district", "projects_registered"]
    assert any("records go up to" in x.text for x in month.sentences)


@pytest.mark.parametrize("message,name,intent", [
    ("Is Qwzx Plaza registered?", "Qwzx Plaza", "not_found"),  # the model said "check_ad": look the name up
    ("Qwzx Plaza નોંધાયેલ છે?", "Qwzx Plaza", "not_found"),
    ("Is this genuine? 2BHK at Qwzx Plaza, book now for Rs 51,000", "Qwzx Plaza", "trust_check"),
])
def test_is_it_registered_looks_up_the_name(demo_repo, message, name, intent):
    from gujrera.chat.llm_router import Routed
    from gujrera.chat.orchestrator import ChatState, _from_llm_route

    reply = _from_llm_route(Routed("check_ad", name), message, ChatState(), demo_repo, "en")
    assert reply.intent == intent


@pytest.mark.parametrize("english,intent_prefix", [
    ("The builder did not give the flat on the promised date, what can I do?", "legal"),
    ("Who will fix cracks that appear within five years of getting the house?", "legal"),
    ("When will I get possession of my flat?", "need_entity"),  # about one flat: ask which project
])
def test_a_question_with_no_project_about_the_law_is_answered_from_the_law(demo_repo, english, intent_prefix):
    from gujrera.chat.llm_router import Routed
    from gujrera.chat.orchestrator import ChatState, _from_llm_route

    reply = _from_llm_route(Routed("possession", None, english), "बिल्डर ने फ्लैट नहीं दिया", ChatState(), demo_repo, "hi")
    assert reply.intent.startswith(intent_prefix)


@pytest.mark.parametrize("text,start,end", [
    ("complaints received this quarter", date(2026, 10, 1), None),
    ("complaints last quarter", date(2026, 7, 1), date(2026, 10, 1)),
    ("પાછલા ત્રિમાસિકમાં ફરિયાદો", date(2026, 7, 1), date(2026, 10, 1)),
    ("इस तिमाही की शिकायतें", date(2026, 10, 1), None),
])
def test_quarters_are_periods(text, start, end):
    from gujrera.analytics.periods import parse_period

    p = parse_period(text, date(2026, 11, 26))
    assert (p.start, p.end) == (start, end)


def test_complaints_in_a_period_use_the_filing_date():
    from gujrera.analytics.reports import match_report

    r = match_report("how many complaints were received this quarter?")
    assert r.key == "complaints_by_category" and "filed_on >=" in r.sql and r.period is not None


def test_the_guard_accepts_sqlite_date_formatting():
    from gujrera.analytics.sql_guard import guard_sql

    guard_sql("SELECT strftime('%Y-%m', filed_on) AS month, COUNT(*) FROM v_complaint_stats GROUP BY month")


@pytest.mark.parametrize("question,named", [
    ("How many projects has Shilp Developers completed?", True),
    ("what has goyal buildcon built", True),
    ("Which developers have the most complaints?", False),
    ("top builders in Surat", False),
])
def test_a_named_builder_is_not_an_officer_report(question, named):
    from gujrera.chat.orchestrator import _names_a_builder

    assert _names_a_builder(question, None) is named


@pytest.mark.parametrize("scope,question,intent", [
    (None, "projects in Surat", "district_projects"),        # statewide officer
    ("Surat", "projects in Surat", "district_projects"),     # own district
    ("Surat", "projects in Ahmedabad", "analytics_out_of_scope"),  # another district: refused, as in reports
])
def test_officers_get_district_lists_within_their_scope(demo_repo, scope, question, intent):
    from gujrera.chat.orchestrator import ChatState, respond
    from gujrera.db.repository import Principal, Repository

    officer = Repository(demo_repo.s, Principal(1, "officer", district_scope=scope), audit_sink=lambda _r: None)
    assert respond(question, ChatState(), officer).intent == intent
