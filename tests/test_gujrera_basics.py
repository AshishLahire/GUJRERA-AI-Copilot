"""Everyday questions: what RERA is, thanks, pending complaints, projects in a district, Hindi-script names."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from gujrera.chat.orchestrator import ChatState, respond
from gujrera.chat.understand import gu_to_deva
from gujrera.db.models import Project, User
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("basics") / "b.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
    yield factory
    engine.dispose()


def _ask(s, message, username=None):
    repo = Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == username)))) if username \
        else Repository(s, Principal.anonymous())
    return respond(message, ChatState(), repo).to_dict()


def test_gujarati_to_hindi_script():
    assert gu_to_deva("મંગલ સ્ક્વેર") == "मंगल स्क्वेर"
    assert gu_to_deva("Mangal 12") == "Mangal 12"


def test_hindi_script_project_names(Session):
    with Session() as s:
        p = s.scalar(select(Project).where(Project.name == "Mangal Square"))
        for q in (f"{gu_to_deva(p.name_gu)} का पज़ेशन कब मिलेगा?", "मंगल स्क्वेयर का पज़ेशन कब मिलेगा?"):
            out = _ask(s, q)
            assert out["intent"] == "possession" and out["lang"] == "hi"
            assert out["sources"][0]["id"] == p.rera_no


def test_about_rera_and_thanks(Session):
    with Session() as s:
        for q, lang in (("What is RERA?", "en"), ("રેરા શું છે?", "gu"), ("RERA क्या है?", "hi")):
            out = _ask(s, q)
            assert out["intent"] == "about_rera" and out["lang"] == lang
            assert {"RERA Act, 2016, Section 3", "RERA Act, 2016, Section 31"} <= {x["id"] for x in out["sources"]}
        assert _ask(s, "thank you")["intent"] == "thanks" and _ask(s, "धन्यवाद")["intent"] == "thanks"
        assert _ask(s, "What is the RERA number of Mangal Square?")["intent"] != "about_rera"


def test_pending_complaints(Session):
    with Session() as s:
        assert _ask(s, "pending complaints", "citizen_01")["intent"] == "complaint_list"
        assert _ask(s, "pending complaints")["intent"] == "complaint_tracking"  # asks for the reference
        assert _ask(s, "How many complaints are there against Mangal Square?")["intent"] == "complaints"


def test_projects_in_a_district(Session):
    with Session() as s:
        out = _ask(s, "Show me projects in Surat")
        assert out["intent"] == "district_projects" and out["cards"][0]["district"] == "Surat"
        total = s.scalar(select(Project.id).where(Project.district == "Surat"))
        assert total and "registered projects" in out["text"]
        delayed = _ask(s, "delayed projects in Surat")
        assert "past their originally promised date" in delayed["text"]
        assert _ask(s, "સુરતમાં કયા પ્રોજેક્ટ છે?")["lang"] == "gu"
        assert _ask(s, "unregistered projects in Surat")["intent"] == "enforcement_info"
        assert _ask(s, "Which promoters in Surat have the most delayed projects?")["intent"] == "officer_only"
        assert _ask(s, "complaints by district", "officer_state")["intent"] == "analytics"  # officers keep analytics
