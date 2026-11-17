"""Complaint filing and tracking: rules, mock workflow adapter, chat flow, API."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gujrera.api.routes import get_session, router
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.complaints.adapter import ComplaintDraft, MockComplaintAdapter
from gujrera.complaints.rules import classify, clean_email, clean_mobile, clean_name, form_for
from gujrera.db.models import Complaint, MockPortalSubmission, Project
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("cmp") / "c.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig(seed=8))
    yield factory
    engine.dispose()


@pytest.fixture
def repo(Session):
    with Session() as s:
        yield Repository(s, Principal.anonymous())


def _project(repo) -> Project:
    return repo.s.scalars(select(Project).where(Project.status == "ongoing").order_by(Project.id)).first()


def _submissions(repo) -> int:
    return repo.s.scalar(select(func.count()).select_from(MockPortalSubmission))


def talk(repo, state, *messages):
    out = None
    for m in messages:
        out = respond(m, state, repo).to_dict()
    return out


STORY = "I want to file a complaint. Possession of my flat in {p} was promised for 2025 but it is still not ready."


# ---------------------------------------------------------------------- rules
@pytest.mark.parametrize("raw,ok", [
    ("9876543210", "9876543210"), ("+91 98765 43210", "9876543210"), ("098765-43210", "9876543210"),
    ("૯૮૭૬૫૪૩૨૧૦", "9876543210"), ("5876543210", None), ("98765", None), ("abc", None),
])
def test_clean_mobile(raw, ok):
    assert clean_mobile(raw) == ok


def test_clean_email_and_name():
    assert clean_email("a.b@example.org") == "a.b@example.org"
    assert clean_email("not an email") is None
    assert clean_name("રમેશ પટેલ") == "રમેશ પટેલ"
    assert clean_name("R2D2") is None and clean_name("ab") is None


def test_classify_priority_and_form():
    assert classify("brochure promised a swimming pool")[0] == "false_advertisement"
    assert classify("दीवारों में दरार है")[0] == "structural_defect"
    assert classify("nothing relevant here") == []
    assert form_for("compensation") == "B" and form_for("refund_with_interest") == "A"


# -------------------------------------------------------------------- adapter
def test_adapter_requires_consent_and_completeness(repo):
    adapter = MockComplaintAdapter(repo.s)
    draft = ComplaintDraft(project_id=_project(repo).id, description="Flat not handed over yet.",
                           category="possession_delay", relief="possession_with_interest",
                           name="Ramesh Patel", mobile="9876543210")
    with pytest.raises(ValueError):
        adapter.submit(draft)
    draft.consent = True
    result = adapter.submit(draft)
    assert result.ref_no.startswith("MOCK-CMP-") and len(result.tracking_code) == 6 and result.is_mock

    c = repo.s.scalar(select(Complaint).where(Complaint.ref_no == result.ref_no))
    # The copilot's own table keeps no contact details and no plain tracking code.
    row = json.dumps({col.key: str(getattr(c, col.key)) for col in Complaint.__table__.columns})
    assert "9876543210" not in row and "Ramesh" not in row and result.tracking_code not in row
    assert c.channel == "copilot" and c.form == "A"
    payload = json.loads(repo.s.scalar(select(MockPortalSubmission.payload_json)
                                       .where(MockPortalSubmission.ref_no == result.ref_no)))
    assert payload["complainant"]["mobile"] == "9876543210" and payload["consent"] is True

    assert adapter.status(result.ref_no, "000000" if result.tracking_code != "000000" else "111111") is None
    assert adapter.status(result.ref_no, result.tracking_code).status == "filed"


# ------------------------------------------------------------------ chat flow
def test_full_filing_in_hindi(repo):
    p = _project(repo)
    state = ChatState()
    before = _submissions(repo)
    out = talk(repo, state, f"मुझे शिकायत दर्ज करनी है। {p.name} में मेरे फ्लैट का पज़ेशन 2025 में मिलना था लेकिन अभी तक नहीं मिला।")
    assert out["intent"] == "complaint_filing" and out["lang"] == "hi"
    assert any(p.rera_no in s for s in [x["text"] for x in out["sentences"]])
    out = talk(repo, state, "1", "रमेश पटेल", "98765 43210", "skip", "skip", "1")
    assert out["intent"] == "complaint_review" and out["lang"] == "hi"
    assert out["cards"][0]["form"] == "A"
    out = talk(repo, state, "1")
    assert out["intent"] == "complaint_submitted" and _submissions(repo) == before + 1
    card = out["cards"][0]
    out = talk(repo, ChatState(), f"{card['ref_no']} {card['tracking_code']}")
    assert out["intent"] == "complaint_status" and out["cards"][0]["status"] == "filed"


def test_compensation_goes_to_form_b(repo):
    p = _project(repo)
    state = ChatState()
    talk(repo, state, STORY.format(p=p.name))
    flow = state.complaint
    n = next(o["n"] for o in flow.options if o["id"] == "compensation")
    out = talk(repo, state, str(n), "Ramesh Patel", "9876543210", "skip", "skip", "1")
    assert out["cards"][0]["form"] == "B"


def test_cancel_and_no_consent_submit_nothing(repo):
    p = _project(repo)
    before = _submissions(repo)
    state = ChatState()
    out = talk(repo, state, STORY.format(p=p.name), "1", "cancel")
    assert out["intent"] == "complaint_cancelled" and state.complaint is None
    state = ChatState()
    out = talk(repo, state, STORY.format(p=p.name), "1", "Ramesh Patel", "9876543210", "skip", "skip", "2")
    assert out["intent"] == "complaint_cancelled" and state.complaint is None
    assert _submissions(repo) == before


def test_invalid_input_is_reasked(repo):
    p = _project(repo)
    state = ChatState()
    out = talk(repo, state, STORY.format(p=p.name), "1", "Ramesh Patel", "12345")
    assert state.complaint.awaiting == "mobile" and "valid 10-digit" in out["text"]
    out = talk(repo, state, "9876543210", "not-an-email")
    assert state.complaint.awaiting == "email" and "doesn't look right" in out["text"]


def test_edit_from_review(repo):
    p = _project(repo)
    state = ChatState()
    talk(repo, state, STORY.format(p=p.name), "1", "Ramesh Patel", "9876543210", "skip", "skip", "1")
    assert state.complaint.awaiting == "review"
    talk(repo, state, "2")  # change something
    name_option = next(o["n"] for o in state.complaint.options if o["id"] == "name")
    talk(repo, state, str(name_option))
    assert state.complaint.awaiting == "name"
    out = talk(repo, state, "Ramesh Kumar Patel")
    assert out["intent"] == "complaint_review"
    assert any(f["value"] == "Ramesh Kumar Patel" for f in out["cards"][0]["fields"])


def test_asks_for_project_when_not_named(repo):
    p = _project(repo)
    state = ChatState()
    out = talk(repo, state, "File a complaint")
    assert state.complaint.awaiting == "project"
    out = talk(repo, state, "Some Unknown Towers")
    assert state.complaint.awaiting == "project" and "couldn't find" in out["text"]
    talk(repo, state, p.rera_no)
    assert state.complaint.draft.project_id == p.id


def test_tracking_lockout_and_unknown_refs(repo):
    p = _project(repo)
    state = ChatState()
    out = talk(repo, state, STORY.format(p=p.name), "1", "Ramesh Patel", "9876543210", "skip", "skip", "1", "1")
    ref, code = out["cards"][0]["ref_no"], out["cards"][0]["tracking_code"]
    wrong = "123456" if code != "123456" else "654321"
    state = ChatState()
    talk(repo, state, f"status of {ref}")
    for _ in range(3):
        out = talk(repo, state, wrong)
    assert "Too many wrong codes" in out["text"]
    out = talk(repo, state, f"{ref} {code}")  # correct code is refused once locked
    assert out["intent"] == "complaint_tracking" and "Too many" in out["text"]

    seeded = repo.s.scalars(select(Complaint.ref_no).where(Complaint.tracking_code_hash.is_(None))).first()
    assert "not filed through GujRERA Saathi" in talk(repo, ChatState(), f"status of {seeded}")["text"]
    assert "couldn't find" in talk(repo, ChatState(), "status of MOCK-CMP-2099-99999")["text"]


def test_tracking_ends_when_user_asks_something_else(repo):
    p = _project(repo)
    state = ChatState()
    talk(repo, state, "Track my complaint")
    assert state.tracking is not None
    out = talk(repo, state, f"When will I get possession of {p.name}?")
    assert out["intent"] == "possession" and state.tracking is None


# ----------------------------------------------------------------------- API
def test_api_filing_round_trip(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as s:
            yield s
            s.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    with Session() as s:
        name = s.scalars(select(Project.name).where(Project.status == "ongoing").order_by(Project.id)).first()
    sid = None
    for msg in [STORY.format(p=name), "1", "Ramesh Patel", "9876543210", "skip", "skip", "1", "1"]:
        out = client.post("/api/gujrera/chat", json={"message": msg, "session_id": sid}).json()
        sid = out["session_id"]
    assert out["intent"] == "complaint_submitted"
    ref, code = out["cards"][0]["ref_no"], out["cards"][0]["tracking_code"]
    status = client.post("/api/gujrera/chat", json={"message": f"status {ref} {code}"}).json()
    assert status["intent"] == "complaint_status"
