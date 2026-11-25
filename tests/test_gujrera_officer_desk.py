"""Officer work queue: district scope, sections built from the registry and citizen signals, reviews."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.db.models import Project, UnknownNumberLookup
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate

FAKE = "PR/GJ/SURAT/SURAT CITY/SUDA/RAA99999/010125"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("desk") / "d.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
        p = s.scalar(select(Project).where(Project.district == "Surat", Project.status == "ongoing").order_by(Project.id))
        p.reg_valid_until = date.today() + timedelta(days=20)  # one registration ending soon
        q = s.scalar(select(Project).where(Project.district == "Surat", Project.status == "ongoing",
                                           Project.id != p.id).order_by(Project.id))
        q.rera_no = q.rera_no.rsplit("/", 1)[0] + "/EX1/EX2/" + q.rera_no.rsplit("/", 1)[1]
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


def _auth(c, user):
    tok = c.post("/api/gujrera/auth/login", json={"username": user, "password": "gujrera-demo"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_citizen_checks_of_unknown_numbers_become_officer_signals(client):
    client.post("/api/gujrera/trust/text", json={"text": f"Shree Residency Surat, book now. RERA {FAKE}"})
    client.post("/api/gujrera/chat", json={"message": f"Is {FAKE} registered?"})
    with client.factory() as s:
        row = s.scalar(select(UnknownNumberLookup))
        assert row.number == FAKE and row.lookups == 2 and row.district == "Surat" and "ad_check" in row.channels
    d = client.get("/api/gujrera/officer/dashboard", headers=_auth(client, "officer_surat")).json()
    assert [i["number"] for i in d["sections"]["unknown_numbers"]["items"]] == [FAKE]
    other = client.get("/api/gujrera/officer/dashboard", headers=_auth(client, "officer_rajkot")).json()
    assert other["sections"]["unknown_numbers"]["items"] == []  # another district's signal is not shown


def test_sections_are_scoped_and_built_from_the_registry(client):
    d = client.get("/api/gujrera/officer/dashboard", headers=_auth(client, "officer_surat")).json()
    assert d["district"] == "Surat"
    for sec in d["sections"].values():
        assert all(it.get("district") in (None, "Surat") for it in sec["items"])
    assert d["sections"]["expiring"]["items"][0]["days_left"] == 20
    assert d["sections"]["extensions"]["items"][0]["extensions"] == 2
    assert d["sections"]["complaints"]["count"] > 0  # demo complaints in Surat
    state = client.get("/api/gujrera/officer/dashboard", headers=_auth(client, "officer_state")).json()
    assert state["district"] is None and state["total_projects"] > d["total_projects"]


def test_review_is_saved_and_moves_the_item_down(client):
    h = _auth(client, "officer_surat")
    first = client.get("/api/gujrera/officer/dashboard", headers=h).json()["sections"]["complaints"]["items"]
    key = first[0]["key"]
    r = client.post("/api/gujrera/officer/review", headers=h,
                    json={"item_type": "complaint", "item_key": key, "status": "reviewed", "note": "Hearing fixed"})
    assert r.status_code == 200 and r.json()["status"] == "reviewed"
    after = client.get("/api/gujrera/officer/dashboard", headers=h).json()["sections"]["complaints"]["items"]
    assert after[-1]["key"] == key and after[-1]["review"]["by"] == "officer_surat"
    assert client.post("/api/gujrera/officer/review", headers=h,
                       json={"item_type": "complaint", "item_key": key, "status": "deleted"}).status_code == 400


def test_only_officers(client):
    assert client.get("/api/gujrera/officer/dashboard").status_code == 403
    assert client.get("/api/gujrera/officer/dashboard", headers=_auth(client, "citizen_01")).status_code == 403
    assert client.post("/api/gujrera/officer/review", headers=_auth(client, "dev_002"),
                       json={"item_type": "complaint", "item_key": "x", "status": "reviewed"}).status_code == 403
