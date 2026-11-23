"""Citizen assistant: the department's sample questions (EVAL_QUESTIONS.md C1-C8), Gujarati first."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from gujrera.authority_seed import seed_authority
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.db.models import Agent, Project
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("citizen") / "c.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
        seed_authority(s)
    yield factory
    engine.dispose()


def _ask(s, q, state=None):
    return respond(q, state or ChatState(), Repository(s, Principal.anonymous())).to_dict()


@pytest.mark.parametrize("q,lang", [("અમદાવાદના બોપલ વિસ્તારમાં RERA માન્ય પ્રોજેક્ટ કયા છે?", "gu"),
                                    ("Which RERA-approved projects are in Bopal, Ahmedabad?", "en"),
                                    ("बोपल में RERA पंजीकृत प्रोजेक्ट कौन से हैं?", "hi")])
def test_projects_in_a_locality(Session, q, lang):
    with Session() as s:
        expected = {p.rera_no for p in s.scalars(select(Project).where(Project.locality == "Bopal"))}
        out = _ask(s, q)
    assert out["intent"] == "locality_projects" and out["lang"] == lang
    assert {x["id"] for x in out["sources"] if x["type"] == "project"} == expected and expected
    if lang == "gu":
        assert out["text"].startswith("બોપલ:") and "ડેમો" not in out["text"]


def test_follow_up_filters_the_previous_list(Session):
    with Session() as s:
        st = ChatState()
        first = _ask(s, "Which RERA-approved projects and developers are in Shela?", st)
        assert first["intent"] == "locality_projects"
        out = _ask(s, "આમાંથી કયા પ્રોજેક્ટ 2024 પછી નોંધાયા?", st)
        expected = {p.rera_no for p in s.scalars(select(Project).where(Project.locality == "Shela"))
                    if p.reg_date.year >= 2025}
        assert out["intent"] == "list_filter"
        assert {x["id"] for x in out["sources"] if x["type"] == "project"} == expected


def test_follow_up_without_a_list_explains_what_to_do(Session):
    with Session() as s:
        out = _ask(s, "Which of these are ongoing?")
        gu = _ask(s, "આમાંથી કયા ચાલુ છે?")
    assert out["intent"] == "list_needed" and "Ask for one first" in out["text"]
    assert gu["intent"] == "list_needed" and gu["lang"] == "gu"


@pytest.mark.parametrize("q", ["સુરતમાં નોંધાયેલા એજન્ટ કોણ છે?", "Who are the registered agents in Surat?"])
def test_agents_in_a_district(Session, q):
    with Session() as s:
        n = len(s.scalars(select(Agent).where(Agent.district == "Surat")).all())
        out = _ask(s, q)
    assert out["intent"] == "agent_list" and f"{n} " in out["text"]
    assert all(x["type"] in ("agent", "agent_registry") for x in out["sources"])


def test_made_up_project_is_not_found(Session):
    with Session() as s:
        for q in ("ક્વાસર હાઇટ્સ વિશે માહિતી આપો", "Tell me about Quasar Heights"):
            out = _ask(s, q)  # "not found", or "did you mean ...?" - never an answer about another project
            assert out["intent"] in ("not_found", "did_you_mean")
            assert not [x for x in out["sources"] if x["type"] == "project"]


def test_completion_date_by_registration_number(Session):
    with Session() as s:
        p = s.scalar(select(Project).where(Project.status == "ongoing").order_by(Project.id))
        out = _ask(s, f"{p.rera_no} વાળા પ્રોજેક્ટની પૂર્ણ થવાની તારીખ શું છે?")
    assert out["sources"][0]["id"] == p.rera_no and out["lang"] == "gu"
