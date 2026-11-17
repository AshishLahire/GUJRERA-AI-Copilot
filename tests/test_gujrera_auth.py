"""Login, tokens, lockout and role-scoped self-service."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gujrera.api.routes import SESSIONS, get_session, router
from gujrera.auth import LoginError, LoginLimiter, authenticate, hash_password, issue_token, read_token, verify_password
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.config import get_gujrera_settings
from gujrera.db.models import Complaint, DueNotice, Promoter, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.selfservice.summary import fmt_inr, promoter_summary

PASSWORD = get_gujrera_settings().GUJRERA_DEMO_PASSWORD.get_secret_value()


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("auth") / "a.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig(seed=13))
    yield factory
    engine.dispose()


@pytest.fixture
def s(Session):
    with Session() as session:
        yield session
        session.rollback()


def _dev_with_dues(s) -> User:
    pid = s.scalars(select(DueNotice.promoter_id).where(DueNotice.status == "pending")).first()
    return s.scalar(select(User).where(User.promoter_id == pid))


# ------------------------------------------------------------------ passwords
def test_password_hashing():
    stored = hash_password("s3cret", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$") and "s3cret" not in stored
    assert verify_password("s3cret", stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("s3cret", None) and not verify_password("s3cret", "garbage")
    assert hash_password("same", iterations=1000) != hash_password("same", iterations=1000)  # random salt


# --------------------------------------------------------------------- tokens
def test_token_round_trip_tamper_and_expiry(s):
    user = s.scalar(select(User).where(User.username == "dev_001"))
    token = issue_token(user)
    assert read_token(token, s).id == user.id
    body, sig = token.split(".")
    assert read_token(f"{body}.{sig[:-2]}xx", s) is None
    assert read_token("not-a-token", s) is None
    hours = get_gujrera_settings().GUJRERA_TOKEN_HOURS
    assert read_token(token, s, now=time.time() + hours * 3600 + 5) is None


def test_token_rejected_after_role_change(s):
    user = s.scalar(select(User).where(User.username == "dev_002"))
    token = issue_token(user)
    user.role = "citizen"
    s.flush()
    assert read_token(token, s) is None


# --------------------------------------------------------------------- login
def test_authenticate_and_lockout(s):
    limiter = LoginLimiter()
    assert authenticate(s, "DEV_001 ", PASSWORD, limiter).username == "dev_001"
    with pytest.raises(LoginError) as unknown:
        authenticate(s, "nobody", PASSWORD, limiter)
    with pytest.raises(LoginError) as wrong:
        authenticate(s, "dev_001", "wrong", limiter)
    assert str(unknown.value) == str(wrong.value)  # no hint whether the username exists
    for _ in range(4):
        with pytest.raises(LoginError):
            authenticate(s, "dev_001", "wrong", limiter)
    with pytest.raises(LoginError) as locked:
        authenticate(s, "dev_001", PASSWORD, limiter)  # even the right password is refused while locked
    assert locked.value.locked


# ---------------------------------------------------------------- self-service
def test_promoter_summary_only_own_data(s):
    dev = _dev_with_dues(s)
    repo = Repository(s, Principal.from_user(dev))
    summary = promoter_summary(repo, "en")
    own_pending = s.scalar(select(func.count()).select_from(DueNotice).where(
        DueNotice.promoter_id == dev.promoter_id, DueNotice.status == "pending", DueNotice.kind != "notice"))
    assert len(summary.card["dues"]) == own_pending
    cited = [int(c["id"]) for x in summary.sentences for c in x.citations if c["type"] == "due_notice"]
    assert cited and {s.get(DueNotice, i).promoter_id for i in cited} == {dev.promoter_id}
    with pytest.raises(AccessDenied):
        promoter_summary(Repository(s, Principal.anonymous()), "en")


def test_fmt_inr():
    assert fmt_inr(1234567) == "12,34,567" and fmt_inr(999) == "999" and fmt_inr(100000) == "1,00,000"


def test_chat_self_service_by_role(s):
    dev = _dev_with_dues(s)
    other = s.scalar(select(Promoter).where(Promoter.id != dev.promoter_id))
    dev_repo = Repository(s, Principal.from_user(dev))
    assert respond("What are my dues?", ChatState(), dev_repo).intent == "self_service"
    assert respond("મારી બાકી ચુકવણી", ChatState(), dev_repo).lang == "gu"
    out = respond(f"show dues of {other.name.replace(' (Demo)', '')}", ChatState(), dev_repo)
    assert out.intent == "access_denied"
    anon = Repository(s, Principal.anonymous())
    assert respond("what are my dues?", ChatState(), anon).intent == "login_required"
    agent = Repository(s, Principal.from_user(s.scalar(select(User).where(User.role == "agent"))))
    assert respond("my registration status", ChatState(), agent).intent == "self_service"
    # public questions are unaffected by login
    assert respond("Any complaints on Zzz Unknown Towers?", ChatState(), dev_repo).intent == "not_found"


def test_logged_in_citizen_lists_and_tracks_own_complaints(s):
    cid = s.scalars(select(Complaint.complainant_user_id).where(Complaint.complainant_user_id.is_not(None))).first()
    citizen = Repository(s, Principal.from_user(s.get(User, cid)))
    out = respond("my complaints", ChatState(), citizen).to_dict()
    mine = s.scalars(select(Complaint.ref_no).where(Complaint.complainant_user_id == cid)).all()
    assert out["intent"] == "complaint_list" and all(ref in out["text"] for ref in mine)
    others = s.scalars(select(Complaint.ref_no).where(Complaint.complainant_user_id != cid)).first()
    assert others not in out["text"]
    # own complaint: no tracking code needed
    assert respond(f"status of {mine[0]}", ChatState(), citizen).intent == "complaint_status"


def test_filing_while_logged_in_links_the_complaint(s):
    user = s.scalar(select(User).where(User.username == "citizen_03"))
    repo = Repository(s, Principal.from_user(user))
    project = s.scalar(select(Promoter)).projects[0]
    state = ChatState()
    for msg in [f"I want to file a complaint. Possession of my flat in {project.name} is delayed by a year.",
                "1", "Asha Shah", "9876543210", "skip", "skip", "1", "1"]:
        out = respond(msg, state, repo).to_dict()
    ref = out["cards"][0]["ref_no"]
    assert s.scalar(select(Complaint.complainant_user_id).where(Complaint.ref_no == ref)) == user.id
    assert respond(f"status of {ref}", ChatState(), repo).intent == "complaint_status"


# ----------------------------------------------------------------------- API
@pytest.fixture
def client(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


def _login(client, username):
    res = client.post("/api/gujrera/auth/login", json={"username": username, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}, res.json()["user"]


def test_api_login_me_and_summary(client):
    headers, user = _login(client, "dev_003")
    assert user["role"] == "developer" and user["organisation"]
    assert client.get("/api/gujrera/auth/me", headers=headers).json()["user"]["username"] == "dev_003"
    summary = client.get("/api/gujrera/self-service/summary?lang=hi", headers=headers).json()
    assert summary["card"]["role"] == "developer" and summary["sentences"]
    assert client.get("/api/gujrera/self-service/summary").status_code == 403
    citizen_headers, _ = _login(client, "citizen_02")
    assert client.get("/api/gujrera/self-service/summary", headers=citizen_headers).status_code == 403
    assert client.get("/api/gujrera/auth/me", headers={"Authorization": "Bearer x.y"}).status_code == 401
    assert client.post("/api/gujrera/chat", json={"message": "hi"},
                       headers={"Authorization": "Bearer x.y"}).status_code == 401


def test_api_wrong_password(client):
    res = client.post("/api/gujrera/auth/login", json={"username": "dev_004", "password": "nope"})
    assert res.status_code == 401 and "password" not in res.json().get("token", "")


def test_chat_session_is_bound_to_its_user(client):
    a_headers, _ = _login(client, "dev_006")
    first = client.post("/api/gujrera/chat", json={"message": "what are my dues?"}, headers=a_headers).json()
    b_headers, _ = _login(client, "dev_007")
    second = client.post("/api/gujrera/chat", json={"message": "what are my dues?",
                                                    "session_id": first["session_id"]}, headers=b_headers).json()
    assert second["session_id"] != first["session_id"]
    anon = client.post("/api/gujrera/chat", json={"message": "hello", "session_id": first["session_id"]}).json()
    assert anon["session_id"] != first["session_id"]
    assert SESSIONS.get(first["session_id"], owner=None)[0] != first["session_id"]
