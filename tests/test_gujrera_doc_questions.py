"""The example questions in GUJRERA's use case document, asked by the role the document gives them to."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from gujrera.chat.orchestrator import ChatState, respond
from gujrera.db.models import Project, ProjectScrutiny, Promoter
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.legal.numbers import spoken_numbers


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("docq") / "d.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig(seed=8))
        project = s.scalars(select(Project).order_by(Project.id)).first()
        s.add(ProjectScrutiny(project_id=project.id, subject="extension", stage="query_raised",
                              opened_on=date(2026, 10, 1), officer_note="INTERNAL NOTE: do not show", is_mock=True))
        s.commit()
    yield factory
    engine.dispose()


def ask(Session, principal: Principal, question: str) -> dict:
    with Session() as s:
        out = respond(question, ChatState(), Repository(s, principal)).to_dict()
        s.rollback()
    return out


@pytest.fixture(scope="module")
def promoter(Session) -> Principal:
    with Session() as s:
        project = s.scalars(select(Project).order_by(Project.id)).first()
        return Principal(role="developer", promoter_id=project.promoter_id, user_id=None)


@pytest.mark.parametrize("q", ["How many projects are delayed?", "કેટલા પ્રોજેક્ટ વિલંબિત છે?",
                               "कितने प्रोजेक्ट देरी से चल रहे हैं?"])
def test_citizen_delay_count_from_public_data(Session, q):
    out = ask(Session, Principal.anonymous(), q)
    assert out["intent"] == "analytics"
    assert "v_project_delays" in out["cards"][0]["sql"]  # the public registry only


def test_citizen_still_refused_internal_reports(Session):
    for q in ("Which projects are under scrutiny?", "Penalty orders with amounts"):
        assert ask(Session, Principal.anonymous(), q)["intent"] == "officer_only"


def test_developer_completed_count(Session):
    with Session() as s:
        name = s.scalars(select(Promoter.name).where(Promoter.promoter_type != "unknown").order_by(Promoter.id)).first()
    out = ask(Session, Principal.anonymous(), f"How many projects has {name.replace(' (Demo)', '')} completed?")
    assert out["intent"] == "promoter_profile"


@pytest.mark.parametrize("template", ["Are there complaints against {n}?", "Complaints against the builder {n}"])
def test_complaints_against_a_named_builder(Session, template):
    """"Developers" or "Builders" in the name must not turn a complaints question into a general profile."""
    with Session() as s:
        name = s.scalars(select(Promoter.name).where(Promoter.name.like("%Builders%") | Promoter.name.like("%Developers%"))
                         .order_by(Promoter.id)).first()
    out = ask(Session, Principal.anonymous(), template.format(n=name.replace(" (Demo)", "")))
    assert out["intent"] == "complaints"


@pytest.mark.parametrize("q", ["What is the status of my application?", "મારી અરજીની સ્થિતિ શું છે?",
                               "मेरे आवेदन की स्थिति क्या है?"])
def test_promoter_application_status(Session, promoter, q):
    out = ask(Session, promoter, q)
    assert out["intent"] == "self_service"
    assert "INTERNAL NOTE" not in json.dumps(out, default=str)  # officer notings never reach the promoter
    assert any(w in out["text"] for w in ("raised a query", "પ્રશ્ન ઉઠાવ્યો", "प्रश्न उठाया"))


@pytest.mark.parametrize("q", ["Have I received any notices?", "શું મને કોઈ નોટિસ મળી છે?", "क्या मुझे कोई नोटिस मिला है?"])
def test_promoter_own_notices(Session, promoter, q):
    assert ask(Session, promoter, q)["intent"] == "self_service"


@pytest.mark.parametrize("q", ["Which documents are pending?", "કયા દસ્તાવેજ બાકી છે?", "कौन से दस्तावेज़ लंबित हैं?"])
def test_promoter_pending_documents(Session, promoter, q):
    out = ask(Session, promoter, q)
    assert out["intent"] == "self_service"
    assert "₹" not in out["text"]  # documents, not money owed


@pytest.mark.parametrize("role", ["citizen", "developer"])
@pytest.mark.parametrize("q", ["How do I file a QPR?", "QPR ભરવાની પ્રક્રિયા શું છે?", "QPR कैसे भरें?"])
def test_qpr_procedure_is_a_law_question(Session, promoter, role, q):
    p = promoter if role == "developer" else Principal.anonymous()
    out = ask(Session, p, q)
    assert out["intent"] == "legal"  # never the complaint form
    assert "Section 11" in out["text"]


def test_applications_are_the_promoters_own(Session):
    with Session() as s:
        with pytest.raises(AccessDenied):
            Repository(s, Principal.anonymous()).own_applications()


@pytest.mark.parametrize("said,expected", [
    ("रेरा कानून की धारा अठारह क्या कहती है", "धारा 18"), ("કલમ અઢાર શું કહે છે", "કલમ 18"),
    ("what does section eighteen say", "section 18"), ("section forty-one", "section 41"), ("નિયમ સાત", "નિયમ 7"),
    ("section on refunds", "section on refunds"),
])
def test_spoken_section_numbers(said, expected):
    assert expected in spoken_numbers(said)
