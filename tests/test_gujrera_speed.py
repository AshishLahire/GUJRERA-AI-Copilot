"""Response time: one connection and a cache for the AI model, warm-up at startup, and the builder question
on public records (which used to load every project in the registry)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from gujrera.db.models import AuditLog, Complaint, Project, Promoter
from gujrera.db.session import init_db, make_engine, session_factory


class _FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):  # noqa: A002
        self.calls.append((url, json))

        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self_inner):
                return {"message": {"content": f"answer to {json['messages'][0]['content']}"}} if "messages" in json else {}

        return R()


def test_the_same_prompt_is_answered_from_the_cache(monkeypatch):
    from gujrera.chat import llm

    fake = _FakeClient()
    monkeypatch.setattr(llm, "llm_client", lambda: fake)
    llm.clear_cache()
    assert llm.ollama_generate("q1") == llm.ollama_generate("q1") == "answer to q1"
    assert llm.ollama_generate("q2") == "answer to q2"
    assert len(fake.calls) == 2  # q1 once, q2 once
    assert llm.load_model() and fake.calls[-1][1].get("keep_alive")  # loading sends no prompt
    llm.clear_cache()


@pytest.fixture()
def public_engine(tmp_path: Path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'p.sqlite').as_posix()}")
    init_db(engine)
    with session_factory(engine)() as s:
        prom = Promoter(name="Promoter not in imported records", promoter_type="unknown", district="Surat",
                        source_url="https://gujrera.gujarat.gov.in/", is_mock=False)
        s.add(prom)
        s.flush()
        for i, name in enumerate(("REAL TOWER", "OTHER HEIGHTS")):
            s.add(Project(rera_no=f"PR/GJ/SURAT/SURAT CITY/SUDA/RAA7000{i}/010120", name=name, promoter_id=prom.id,
                          district="Surat", taluka="Surat City", project_type="residential", status="ongoing", units=10,
                          reg_date=date(2020, 1, 1), proposed_completion=date(2029, 4, 30),
                          reg_valid_until=date(2029, 4, 30), source_url="https://gujrera.gujarat.gov.in/", is_mock=False))
        s.commit()
    yield engine
    engine.dispose()


@pytest.mark.parametrize("question,lang", [
    ("Who is the builder of REAL TOWER?", "en"),
    ("Is the developer of Real Tower trustworthy?", "en"),
])
def test_public_records_do_not_name_the_builder(public_engine, question, lang):
    from gujrera.chat.orchestrator import ChatState, respond
    from gujrera.db.repository import Principal, Repository

    with session_factory(public_engine)() as s:
        repo = Repository(s, Principal.anonymous(), audit_sink=lambda _r: None)
        state = ChatState()
        r = respond(question, state, repo).to_dict()
        assert r["intent"] == "builder_not_named"
        assert "do not name the builder of REAL TOWER" in r["text"] and "Promoter not in imported records" not in r["text"]
        assert "REAL TOWER is" in r["text"]  # the project's own record follows
        follow = respond("When will it be completed?", state, repo).to_dict()
        assert follow["intent"] == "possession" and "30 April 2029" in follow["text"]


def test_named_builders_still_get_their_record(tmp_path):
    from gujrera.chat.orchestrator import ChatState, respond
    from gujrera.db.repository import Principal, Repository
    from gujrera.ingest.mock_generator import MockConfig, generate

    engine = make_engine(f"sqlite:///{(tmp_path / 'd.sqlite').as_posix()}")
    init_db(engine)
    with session_factory(engine)() as s:
        generate(s, MockConfig())
        s.commit()
        repo = Repository(s, Principal.anonymous(), audit_sink=lambda _r: None)
        assert respond("Who is the builder of Mangal Square?", ChatState(), repo).intent == "promoter_profile"
    engine.dispose()


def test_warm_up_answers_the_suggested_questions_and_writes_nothing(public_engine, monkeypatch):
    from gujrera import warmup
    from gujrera.chat import llm

    loaded = []
    monkeypatch.setattr(llm, "load_model", lambda model=None: loaded.append(model) or True)
    with session_factory(public_engine)() as s:
        before = (s.scalar(select(func.count()).select_from(AuditLog)), s.scalar(select(func.count()).select_from(Complaint)))
    status = warmup.warm(public_engine)
    assert status["state"] == "ready" and loaded
    assert isinstance(status["steps"]["suggested_questions"], float)  # every question answered without error
    with session_factory(public_engine)() as s:
        after = (s.scalar(select(func.count()).select_from(AuditLog)), s.scalar(select(func.count()).select_from(Complaint)))
    assert after == before


def test_warm_up_is_off_when_disabled(monkeypatch):
    from gujrera import warmup

    assert warmup.start(lambda: None) is False  # tests run with GUJRERA_WARMUP=false
