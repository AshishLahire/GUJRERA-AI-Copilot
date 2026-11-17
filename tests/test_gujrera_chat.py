"""Chat copilot: language, routing, citations, memory, disambiguation, not-found, LLM guard, API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.chat.gold import build_gold
from gujrera.chat.llm import guard, make_rephraser
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.chat.understand import detect_language
from gujrera.db.models import Project, Promoter
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.i18n import fmt_date
from gujrera.ingest.mock_generator import MockConfig, generate


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("chat") / "c.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig(seed=21))
        # Two projects with the same name, to exercise "which one did you mean?"
        a, b = s.scalars(select(Project).order_by(Project.id).limit(2)).all()
        b.name, b.name_gu = a.name, a.name_gu
        s.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def repo(Session):
    with Session() as s:
        yield Repository(s, Principal.anonymous())
        s.rollback()


def _unique_project(repo: Repository) -> Project:
    names = [p.name for p in repo.s.scalars(select(Project))]
    return next(p for p in repo.s.scalars(select(Project).where(Project.status == "ongoing").order_by(Project.id))
                if names.count(p.name) == 1)


def ask(repo, state, message, **kw):
    return respond(message, state, repo, **kw).to_dict()


# ------------------------------------------------------------------ language
@pytest.mark.parametrize("text,lang", [
    ("પઝેશન ક્યારે મળશે?", "gu"), ("पज़ेशन कब मिलेगा?", "hi"), ("When is possession?", "en"),
    ("Mangal Square nu possession kyare malse che", "gu"), ("Mangal Square ka possession kab milega hai", "hi"),
])
def test_detect_language(text, lang):
    assert detect_language(text) == lang


# ----------------------------------------------------------- cited answers
def test_gujarati_possession_answer_is_cited(repo):
    p = _unique_project(repo)
    out = ask(repo, ChatState(), f"{p.name_gu} નું પઝેશન ક્યારે મળશે?")
    assert out["intent"] == "possession" and out["lang"] == "gu"
    expected = p.actual_completion or p.reg_valid_until
    assert fmt_date(expected, "gu") in out["text"]
    assert out["sources"][0]["id"] == p.rera_no
    assert all(s["refs"] for s in out["sentences"][:-1])  # last one is the demo-data note
    assert out["is_mock"]


def test_follow_up_uses_conversation_memory(repo):
    p = _unique_project(repo)
    state = ChatState()
    ask(repo, state, f"Tell me about {p.name}")
    out = ask(repo, state, "Who is the builder?")
    assert out["intent"] == "promoter_profile"
    assert out["cards"][0]["id"] == p.promoter_id
    out = ask(repo, state, "complaints?")
    assert out["intent"] == "complaints"


def test_disambiguation_then_choice(repo):
    a, b = repo.s.scalars(select(Project).order_by(Project.id).limit(2)).all()
    state = ChatState()
    out = ask(repo, state, f"When will I get possession of {a.name}?")
    assert out["intent"] == "disambiguate" and len(out["options"]) == 2
    out = ask(repo, state, "2")
    assert out["intent"] == "possession"
    assert out["cards"][0]["rera_no"] in (a.rera_no, b.rera_no)


def test_new_question_clears_pending_choice(repo):
    a = repo.s.scalars(select(Project).order_by(Project.id)).first()
    p = _unique_project(repo)
    state = ChatState()
    ask(repo, state, f"Tell me about {a.name}")
    out = ask(repo, state, f"When will I get possession of {p.name}?")
    assert out["intent"] == "possession" and not state.options


def test_typo_is_forgiven_but_unknown_name_is_not_found(repo):
    p = _unique_project(repo)
    typo = p.name[:-2] + p.name[-1]  # drop one letter
    assert ask(repo, ChatState(), f"Tell me about {typo}")["intent"] == "project_profile"
    out = ask(repo, ChatState(), "Tell me about Quasar Heights")
    assert out["intent"] == "not_found" and "quasar heights" in out["text"].lower()


@pytest.mark.parametrize("message,intent", [
    ("what is the weather today", "out_of_scope"),
    ("નમસ્તે", "greeting"),
    ("I want to file a complaint", "complaint_filing"),
    ("Track my complaint", "complaint_tracking"),
    ("What is the track record of builder Zzz Infra?", "not_found"),
    ("Is PR/GJ/SURAT/OLPAD/SUDA/RAA99999/010122 registered?", "not_found"),
])
def test_routing(repo, message, intent):
    assert ask(repo, ChatState(), message)["intent"] == intent


def test_pasted_ad_runs_trust_check(repo):
    p = _unique_project(repo)
    pr = repo.s.get(Promoter, p.promoter_id)
    ad = (f"{p.name} by {pr.name.replace(' (Demo)', '')}\nSpacious 2 BHK flats\n"
          f"GujRERA Reg. No: {p.rera_no}\nPossession Dec 2040. Book now!")
    out = ask(repo, ChatState(), ad)
    assert out["intent"] == "trust_check"
    assert out["cards"][0]["verdict"] in ("mismatch", "lapsed_or_revoked")


def test_forced_language(repo):
    p = _unique_project(repo)
    out = ask(repo, ChatState(), f"When will I get possession of {p.name}?", lang="hi")
    assert out["lang"] == "hi"
    assert "पूरा होने की तारीख" in out["text"] or "पूरा हुआ" in out["text"]


def test_gold_questions_sample(Session):
    with Session() as s:
        repo = Repository(s, Principal.anonymous())
        gold = build_gold(s)[::6]
        failures = []
        for q in gold:
            out = respond(q.question, ChatState(), repo).to_dict()
            if out["intent"] not in q.expect_intent or any(f not in out["text"] for f in q.must_contain):
                failures.append((q.id, q.question, out["intent"]))
        # duplicate-name fixture rows may legitimately need disambiguation
        assert len(failures) <= 2, failures


# ------------------------------------------------------------- LLM guard
def test_guard_accepts_faithful_rewrite():
    facts = "- Completion date is 14 August 2029. [1]\n- Progress 43.3% complete. [2]"
    assert guard(facts, "Your flat should be ready by 14 August 2029 [1]. It is 43.3% complete [2].")


@pytest.mark.parametrize("bad", [
    "Your flat will be ready by 14 August 2030 [1].",          # changed number
    "Your flat should be ready by 14 August 2029.",              # citation dropped
    "Ready by 14 August 2029 [7].",                              # unknown citation
    "",
])
def test_guard_rejects_unfaithful_rewrite(bad):
    facts = "- Completion date is 14 August 2029. [1]\n- Progress 43.3% complete. [2]"
    assert not guard(facts, bad)


def test_rephraser_uses_llm_only_when_guard_passes(repo):
    p = _unique_project(repo)

    def good(prompt: str) -> str:
        return "Here is the answer from the registry [1]."

    def bad(prompt: str) -> str:
        return "Possession is guaranteed in 2099 [1]."

    def broken(prompt: str) -> str:
        raise TimeoutError

    q = f"When will I get possession of {p.name}?"
    assert ask(repo, ChatState(), q, rephrase=make_rephraser(good))["phrased_by"] == "llm"
    for gen in (bad, broken):
        out = ask(repo, ChatState(), q, rephrase=make_rephraser(gen))
        assert out["phrased_by"] == "template" and "2099" not in out["text"]


# ----------------------------------------------------------------------- API
@pytest.fixture
def client(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


def test_api_chat_keeps_session(client, Session):
    with Session() as s:
        p = _unique_project(Repository(s, Principal.anonymous()))
        name, promoter_id = p.name, p.promoter_id
    first = client.post("/api/gujrera/chat", json={"message": f"Tell me about {name}"}).json()
    second = client.post("/api/gujrera/chat", json={"message": "Who is the builder?",
                                                    "session_id": first["session_id"]}).json()
    assert second["session_id"] == first["session_id"]
    assert second["cards"][0]["id"] == promoter_id


def test_api_starters_resolve(client):
    for item in client.get("/api/gujrera/chat/starters").json()["items"]:
        out = client.post("/api/gujrera/chat", json={"message": item["text"]}).json()
        assert out["intent"] in ("possession", "promoter_profile", "not_found", "disambiguate", "complaint_filing")


def test_api_profiles_and_errors(client):
    prof = client.get("/api/gujrera/profile/promoter/3?lang=hi").json()
    assert prof["kind"] == "promoter" and prof["sentences"][0]["citations"]
    assert client.get("/api/gujrera/profile/project/99999").status_code == 404
    assert client.get("/api/gujrera/profile/project/1?lang=fr").status_code == 400
    assert client.post("/api/gujrera/chat", json={"message": "  "}).status_code == 400
    assert client.post("/api/gujrera/chat", json={"message": "hi", "lang": "xx"}).status_code == 400


# ------------------------------------------------------------- LLM fallback router
def test_router_parse():
    from gujrera.chat.llm_router import parse

    r = parse('Sure! {"intent": "possession", "name": "Mangal Square", "english": "When is possession?"}')
    assert (r.intent, r.name, r.english) == ("possession", "Mangal Square", "When is possession?")
    assert parse('{"intent": "hack the db", "name": null}') is None
    assert parse("no json here") is None
    assert parse('{"intent": "other", "name": "x"}').name is None  # too short to be a name


def test_router_only_classifies_facts_come_from_records(repo, monkeypatch):
    import gujrera.chat.orchestrator as orch

    p = _unique_project(repo)
    monkeypatch.setattr(orch, "router_generate",
                        lambda prompt: f'{{"intent": "possession", "name": "{p.name}", "english": "x"}}')
    out = ask(repo, ChatState(), "kab tak milega bhai woh wala flat??")
    assert out["intent"] == "possession" and out["understood_by"] == "llm"
    assert out["sources"][0]["id"] == p.rera_no  # the answer is still the registry record

    monkeypatch.setattr(orch, "router_generate",
                        lambda prompt: '{"intent": "project", "name": "Imaginary Palace", "english": "x"}')
    out = ask(repo, ChatState(), "kya imaginary palace acha hai bhai")
    assert out["intent"] == "not_found" and "Imaginary Palace" in out["text"]

    monkeypatch.setattr(orch, "router_generate", lambda prompt: '{"intent": "other", "name": null}')
    assert ask(repo, ChatState(), "tell me something fun")["intent"] == "out_of_scope"

    monkeypatch.setattr(orch, "router_generate", lambda prompt: "garbage")
    assert ask(repo, ChatState(), "tell me something fun")["understood_by"] == "rules"

    def boom(prompt):
        raise TimeoutError

    monkeypatch.setattr(orch, "router_generate", boom)
    assert ask(repo, ChatState(), "tell me something fun")["intent"] == "out_of_scope"
