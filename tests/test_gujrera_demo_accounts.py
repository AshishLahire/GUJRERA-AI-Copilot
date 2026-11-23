"""Login quick picks list only the demo accounts present in the loaded database."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.db.models import User
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate


def _client(factory):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


def _db(tmp_path, name, users=None):
    engine = make_engine(f"sqlite:///{(tmp_path / name).as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        if users is None:
            generate(s, MockConfig())
        else:
            s.add_all(users)
        s.commit()
    return factory


def test_demo_database_lists_its_accounts(tmp_path):
    body = _client(_db(tmp_path, "demo.sqlite")).get("/api/gujrera/auth/demo-accounts").json()
    names = [a["username"] for a in body["accounts"]]
    assert names[:3] == ["dev_002", "agent_001", "citizen_01"] and "officer_surat" in names
    assert {"username", "label"} == set(body["accounts"][0]) and "Officer (Surat)" in [a["label"] for a in body["accounts"]]


def test_public_database_lists_only_what_exists(tmp_path):
    factory = _db(tmp_path, "public.sqlite", [
        User(username="officer_state", role="officer", is_mock=True),
        User(username="officer_gandhinagar", role="officer", district_scope="Gandhinagar", is_mock=True),
        User(username="citizen_01", role="citizen", is_mock=True),
        User(username="officer_surat", role="officer", district_scope="Surat", is_mock=False),  # a real account
    ])
    body = _client(factory).get("/api/gujrera/auth/demo-accounts").json()
    assert body["accounts"] == [
        {"username": "citizen_01", "label": "Home buyer 01"},
        {"username": "officer_state", "label": "Officer (statewide)"},
        {"username": "officer_gandhinagar", "label": "Officer (Gandhinagar)"},
    ]
    with factory() as s:
        assert s.scalar(select(User).where(User.username == "officer_surat")).is_mock is False
