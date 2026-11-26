"""Regressions found by checking every tab: complaint categories, samples on public records."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gujrera.api.routes import get_session, router
from gujrera.complaints.rules import classify
from gujrera.db.models import Project, Promoter
from gujrera.db.session import init_db, make_engine, session_factory


@pytest.mark.parametrize("story,expected", [
    ("The possession has been delayed beyond the promised date in the agreement.", "possession_delay"),
    ("પઝેશનમાં વિલંબ થયો છે, કરાર મુજબ તારીખ વીતી ગઈ", "possession_delay"),
    ("Builder is demanding extra charges not in the agreement", "agreement_violation"),
    ("બિલ્ડરે કરારનો ભંગ કર્યો", "agreement_violation"),
    ("अनुबंध का उल्लंघन किया", "agreement_violation"),
    ("No agreement was signed but they took 30%", "agreement_violation"),
])
def test_the_word_agreement_alone_is_not_a_breach(story, expected):
    assert classify(story)[0] == expected


@pytest.fixture()
def public_client(tmp_path: Path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'p.sqlite').as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        prom = Promoter(name="Promoter not in imported records", promoter_type="unknown", district="Surat",
                        source_url="https://gujrera.gujarat.gov.in/", is_mock=False)
        s.add(prom)
        s.flush()
        s.add(Project(rera_no="PR/GJ/SURAT/SURAT CITY/SUDA/RAA70001/010120", name="REAL TOWER", promoter_id=prom.id,
                      district="Surat", taluka="Surat City", project_type="residential", status="ongoing", units=10,
                      reg_date=date(2020, 1, 1), proposed_completion=date(2029, 4, 30), reg_valid_until=date(2029, 4, 30),
                      source_url="https://gujrera.gujarat.gov.in/", is_mock=False))
        s.commit()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    yield TestClient(app)
    engine.dispose()


def test_public_records_get_honest_samples(public_client):
    c = public_client
    items = c.get("/api/gujrera/trust/samples").json()["items"]
    assert {i["kind"] for i in items} == {"not_found", "no_number"}
    assert all("REAL TOWER" not in i["text"] for i in items)  # never built around a real project
    for it in items:
        assert c.post("/api/gujrera/trust/text", json={"text": it["text"]}).json()["verdict"] in it["expected"]
    agr = c.get("/api/gujrera/agreement/samples").json()
    assert agr["note"] and "made-up project" in agr["note"]
