"""Administration: accounts and roles, sessions ended on disable or reset, the audit log viewer."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from gujrera.api.routes import get_session, router
from gujrera.auth import LIMITER
from gujrera.db.models import AuditLog, User
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.enforcement import ensure_tables
from gujrera.ingest.mock_generator import MockConfig, generate


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("adm") / "d.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    ensure_tables(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    c = TestClient(app)
    c.factory = factory
    yield c
    engine.dispose()


def _login(c, user, password="gujrera-demo"):
    return c.post("/api/gujrera/auth/login", json={"username": user, "password": password})


def _auth(c, user, password="gujrera-demo"):
    return {"Authorization": f"Bearer {_login(c, user, password).json()['token']}"}


def test_only_state_officers_administer(client):
    for user in ("officer_surat", "citizen_01", "dev_002"):
        h = _auth(client, user)
        assert client.get("/api/gujrera/admin/users", headers=h).status_code == 403
        assert client.get("/api/gujrera/admin/audit", headers=h).status_code == 403
    assert client.get("/api/gujrera/admin/users").status_code == 403


def test_create_officer_login_and_scope(client):
    h = _auth(client, "officer_state")
    listing = client.get("/api/gujrera/admin/users", headers=h).json()
    assert "Surat" in listing["districts"] and listing["creatable_roles"] == ["officer", "citizen"]
    r = client.post("/api/gujrera/admin/users", headers=h,
                    json={"username": "officer_test_surat", "display_name": "Test officer", "role": "officer",
                          "district_scope": "Surat"})
    assert r.status_code == 200, r.text
    pw = r.json()["temporary_password"]
    assert len(pw) >= 10 and r.json()["user"]["district_scope"] == "Surat"
    with client.factory() as s:  # the password is stored hashed, never in clear, and not in the audit log
        u = s.scalar(select(User).where(User.username == "officer_test_surat"))
        assert pw not in (u.password_hash or "") and u.password_hash.startswith("pbkdf2_sha256$")
        assert all(pw not in (a.detail or "") for a in s.scalars(select(AuditLog)))
    me = _login(client, "officer_test_surat", pw).json()["user"]
    assert me["role"] == "officer" and me["district_scope"] == "Surat"
    # duplicates, bad names, unknown districts and promoter accounts are refused
    for body in ({"username": "officer_test_surat", "role": "officer"}, {"username": "A b", "role": "citizen"},
                 {"username": "x_officer", "role": "officer", "district_scope": "Atlantis"},
                 {"username": "promoter_x", "role": "developer"}):
        assert client.post("/api/gujrera/admin/users", headers=h, json=body).status_code == 400


def test_disable_and_reset_end_sessions(client):
    h = _auth(client, "officer_state")
    created = client.post("/api/gujrera/admin/users", headers=h,
                          json={"username": "buyer_test", "display_name": "Test buyer", "role": "citizen"}).json()
    uid, pw = created["user"]["id"], created["temporary_password"]
    hb = _auth(client, "buyer_test", pw)
    assert client.get("/api/gujrera/auth/me", headers=hb).status_code == 200
    assert client.patch(f"/api/gujrera/admin/users/{uid}", headers=h, json={"is_active": False}).json()["user"]["is_active"] is False
    assert client.get("/api/gujrera/auth/me", headers=hb).status_code == 401  # session ended at once
    r = _login(client, "buyer_test", pw)
    assert r.status_code == 401 and "disabled" in r.json()["detail"]
    client.patch(f"/api/gujrera/admin/users/{uid}", headers=h, json={"is_active": True})
    hb = _auth(client, "buyer_test", pw)
    new_pw = client.post(f"/api/gujrera/admin/users/{uid}/reset-password", headers=h).json()["temporary_password"]
    assert new_pw != pw
    assert client.get("/api/gujrera/auth/me", headers=hb).status_code == 401  # old session ended
    LIMITER.success("buyer_test")
    assert _login(client, "buyer_test", pw).status_code == 401 and _login(client, "buyer_test", new_pw).status_code == 200


def test_changing_an_officers_district_takes_effect(client):
    h = _auth(client, "officer_state")
    users = client.get("/api/gujrera/admin/users", headers=h, params={"q": "officer_rajkot"}).json()["users"]
    uid = users[0]["id"]
    hr = _auth(client, "officer_rajkot")
    r = client.patch(f"/api/gujrera/admin/users/{uid}", headers=h, json={"set_scope": True, "district_scope": "Surat"})
    assert r.json()["user"]["district_scope"] == "Surat"
    assert client.get("/api/gujrera/auth/me", headers=hr).status_code == 401  # must log in again
    assert _login(client, "officer_rajkot").json()["user"]["district_scope"] == "Surat"
    client.patch(f"/api/gujrera/admin/users/{uid}", headers=h, json={"set_scope": True, "district_scope": "Rajkot"})


def test_admins_cannot_lock_themselves_out(client):
    h = _auth(client, "officer_state")
    me = client.get("/api/gujrera/admin/users", headers=h, params={"q": "officer_state"}).json()["users"][0]
    r = client.patch(f"/api/gujrera/admin/users/{me['id']}", headers=h, json={"is_active": False})
    assert r.status_code == 400 and "own account" in r.json()["detail"]
    r = client.patch(f"/api/gujrera/admin/users/{me['id']}", headers=h, json={"set_scope": True, "district_scope": "Surat"})
    assert r.status_code == 400


def test_audit_log_records_refusals_and_filters(client):
    LIMITER.success("officer_surat")
    _login(client, "officer_surat", "wrong-password")
    hs = _auth(client, "officer_surat")
    client.post("/api/gujrera/analytics/query", headers=hs, json={"question": "Projects under scrutiny in Ahmedabad"})
    client.post("/api/gujrera/analytics/query", headers=hs, json={"question": "delete all notices"})
    client.get("/api/gujrera/admin/users", headers=hs)  # a district officer opening administration

    h = _auth(client, "officer_state")
    log = client.get("/api/gujrera/admin/audit", headers=h).json()
    s = log["summary"]
    assert s["failed_logins"] >= 1 and s["out_of_scope"] >= 1 and s["write_attempts"] >= 1 and s["access_denied"] >= 1
    refusals = client.get("/api/gujrera/admin/audit", headers=h, params={"category": "refusal"}).json()["entries"]
    assert refusals and all(e["category"] == "refusal" for e in refusals)
    failed = next(e for e in refusals if e["action"] == "login_failed")
    assert failed["user"] == "officer_surat" and "password" not in failed["detail"]
    mine = client.get("/api/gujrera/admin/audit", headers=h, params={"username": "officer_surat"}).json()["entries"]
    assert {e["action"] for e in mine} >= {"login", "login_failed", "analytics_out_of_scope"}
    created = client.get("/api/gujrera/admin/audit", headers=h, params={"action": "user_created"}).json()["entries"]
    assert created and created[0]["user"] == "officer_state"
    csv_text = client.get("/api/gujrera/admin/audit.csv", headers=h, params={"category": "refusal"}).text
    assert csv_text.lstrip("﻿").startswith("time,user,role,category,action") and "login_failed" in csv_text


def test_older_databases_get_the_new_columns(tmp_path):
    path = tmp_path / "old.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80), role VARCHAR(20))"))
        conn.execute(text("INSERT INTO users (username, role) VALUES ('old_user', 'citizen')"))
    init_db(engine)
    ensure_tables(engine)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT is_active, token_version FROM users WHERE username = 'old_user'")).one()
    assert tuple(row) == (1, 0)
    engine.dispose()
