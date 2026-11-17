"""Project watch: alerts from dated registry records, unread state, buyers only, digest hand-off."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.auth import issue_token
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.db.models import Order, Project, ProjectProgress, Promoter, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.watch import (MAX_WATCHES, MockNotifier, add_watch, digest, mark_seen, my_watches, project_events,
                           remove_watch, unread_count)

AS_OF = date(2026, 6, 1)


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("watch") / "w.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        pr = Promoter(name="Test Watch Builders", district="Rajkot", is_mock=True)
        s.add(pr)
        s.flush()
        p = Project(rera_no="PR/GJ/RAJKOT/RAJKOT/RUDA/TEST00005/010124", promoter_id=pr.id, name="Test Watch Park",
                    district="Rajkot", project_type="residential", status="ongoing", units=40, reg_date=date(2024, 1, 1),
                    proposed_completion=date(2026, 3, 31), revised_completion=date(2027, 3, 31),
                    reg_valid_until=date(2026, 8, 1), is_mock=True)
        s.add(p)
        s.flush()
        for q, pct, due, filed in [("2025-Q3", 40, date(2025, 10, 15), date(2025, 10, 10)),
                                   ("2025-Q4", 38, date(2026, 1, 15), date(2026, 1, 12)),
                                   ("2026-Q1", 38, date(2026, 4, 15), None)]:
            s.add(ProjectProgress(project_id=p.id, quarter=q, percent_complete=pct, due_on=due, filed_on=filed, is_mock=True))
        s.add(Order(order_no="TEST-ORD-2026-00001", order_type="extension_order", project_id=p.id, promoter_id=pr.id,
                    issued_on=date(2026, 3, 20), summary="Registration extended.", is_mock=True))
        s.commit()
    yield factory
    engine.dispose()


def _repo(s, username: str | None) -> Repository:
    if username is None:
        return Repository(s, Principal.anonymous())
    return Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == username))))


def _pid(s) -> int:
    return s.scalar(select(Project.id).where(Project.name == "Test Watch Park"))


def test_events_from_dated_records(Session):
    with Session() as s:
        p = s.get(Project, _pid(s))
        ev = project_events(s, p, "en", since=date(2025, 6, 1), today=AS_OF)
        kinds = [(e["date"], e["kind"], e["tone"]) for e in ev]
        assert ("2026-04-15", "qpr_missed", "bad") in kinds
        assert ("2026-03-20", "extension", "warn") in kinds
        assert ("2026-05-03", "reg_ending", "warn") in kinds  # 90 days before 1 Aug 2026
        down = next(e for e in ev if e["date"] == "2026-01-12")
        assert down["tone"] == "bad" and "down from 40" in down["text"]
        assert [e["date"] for e in ev] == sorted((e["date"] for e in ev), reverse=True)
        assert all(e["citations"] for e in ev)
        assert all(e["date"] <= AS_OF.isoformat() for e in ev)  # nothing from the future
        assert project_events(s, p, "en", since=AS_OF + timedelta(days=1), today=AS_OF + timedelta(days=5)) == []
        gu = project_events(s, p, "gu", since=date(2025, 6, 1), today=AS_OF)
        assert any("કલમ 11" in e["text"] for e in gu)


def test_watch_unread_and_access(Session):
    with Session() as s:
        buyer, pid = _repo(s, "citizen_02"), _pid(s)
        for other in (None, "dev_001", "officer_state"):
            with pytest.raises(AccessDenied):
                add_watch(_repo(s, other), pid, today=AS_OF)
        assert add_watch(buyer, pid, today=date(2026, 1, 1))["created"]
        assert not add_watch(buyer, pid, today=AS_OF)["created"]  # idempotent
        w = my_watches(buyer, "en", as_of=AS_OF)
        mine = next(x for x in w["watches"] if x["project_id"] == pid)
        assert mine["unread"] == sum(e["date"] > "2026-01-01" for e in mine["events"]) >= 3
        assert unread_count(buyer, as_of=AS_OF) == w["unread"]
        assert unread_count(_repo(s, "citizen_03"), as_of=AS_OF) == 0  # someone else's watches are not mine
        mark_seen(buyer, pid, today=AS_OF)
        assert next(x for x in my_watches(buyer, "en", as_of=AS_OF)["watches"] if x["project_id"] == pid)["unread"] == 0
        assert remove_watch(buyer, pid) and not remove_watch(buyer, pid)
        s.rollback()


def test_limit_and_digest(Session):
    with Session() as s:
        buyer = _repo(s, "citizen_04")
        ids = s.scalars(select(Project.id).order_by(Project.id).limit(MAX_WATCHES + 1)).all()
        for pid in ids[:MAX_WATCHES]:
            add_watch(buyer, pid, today=date(2025, 1, 1))
        with pytest.raises(ValueError):
            add_watch(buyer, ids[MAX_WATCHES], today=AS_OF)
        n = MockNotifier()
        assert digest(s, n, since=date(2026, 1, 1), today=AS_OF) >= 1
        user, lines = next(x for x in n.sent if x[0] == "citizen_04")
        assert 0 < len(lines) <= 10 and all(": " in line for line in lines)
        s.rollback()


def test_chat_and_api(Session):
    with Session() as s:
        buyer = _repo(s, "citizen_05")
        out = respond("Watch Test Watch Park", ChatState(), buyer).to_dict()
        assert out["intent"] == "watch" and out["cards"][0]["type"] == "watch"
        assert respond("Watch Test Watch Park", ChatState(), _repo(s, None)).intent == "watch"  # asks to log in
        feed = respond("what's new on my projects?", ChatState(), buyer).to_dict()
        assert feed["intent"] == "watch_feed"
        token = issue_token(s.scalar(select(User).where(User.username == "citizen_06")))
        dev = issue_token(s.scalar(select(User).where(User.username == "dev_001")))
        pid = _pid(s)
        s.rollback()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/gujrera/watch").status_code == 403
    assert client.post(f"/api/gujrera/watch/{pid}", headers={"Authorization": f"Bearer {dev}"}).status_code == 403
    assert client.post(f"/api/gujrera/watch/{pid}", headers=h).json()["created"] is True
    assert client.get("/api/gujrera/watch", headers=h).json()["watches"][0]["project_id"] == pid
    assert client.get("/api/gujrera/watch/unread").json() == {"unread": 0}
    assert client.post("/api/gujrera/watch/seen", headers=h).json()["marked"] == 1
    assert client.delete(f"/api/gujrera/watch/{pid}", headers=h).json()["removed"] is True
    assert client.post("/api/gujrera/watch/999999", headers=h).status_code == 400
