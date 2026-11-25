"""Officer reports: follow-up refinements, Excel export and saved reports."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gujrera.analytics.followup import refine
from gujrera.analytics.reports import match_report
from gujrera.api.routes import get_session, router
from gujrera.authority_seed import seed_authority
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.enforcement import ensure_tables
from gujrera.ingest.mock_generator import MockConfig, generate

SCRUTINY = "Projects under scrutiny in Ahmedabad"


# ------------------------------------------------------------------ merging (no database)
@pytest.mark.parametrize("followup,district,locality,period,top", [
    ("only Bopal", "Ahmedabad", "Bopal", False, None),
    ("ફક્ત બોપલ", "Ahmedabad", "Bopal", False, None),
    ("last 3 months", "Ahmedabad", None, True, None),
    ("છેલ્લા 3 મહિના", "Ahmedabad", None, True, None),
    ("in Vadodara instead", "Vadodara", None, False, None),
    ("केवल सूरत", "Surat", None, False, None),
])
def test_followups_narrow_the_previous_report(followup, district, locality, period, top):
    r = refine(SCRUTINY, followup)
    rep = match_report(r.question.lower())
    assert rep.key == "projects_under_scrutiny" and rep.district == district and rep.locality == locality
    assert bool(rep.period) is period


def test_chained_followups_replace_rather_than_pile_up():
    q = refine(SCRUTINY, "only Bopal").question
    q = refine(q, "last six months").question
    q = refine(q, "in Surat").question  # a new district drops the old district's locality
    rep = match_report(q)
    assert rep.district == "Surat" and rep.locality is None and rep.period is not None
    assert "top 5" in refine("Developers issued notices", "top 5").question


@pytest.mark.parametrize("message", ["Which promoters have the most delayed projects?", "thanks", "show me more",
                                     "Bopal na project ni yaadi ane tena promoter na naam ane phone number aapo"])
def test_new_questions_and_chatter_are_not_followups(message):
    assert refine(SCRUTINY, message) is None
    assert refine(None, "only Bopal") is None


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("rep") / "d.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    ensure_tables(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
        seed_authority(s)
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


def _auth(c, user):
    tok = c.post("/api/gujrera/auth/login", json={"username": user, "password": "gujrera-demo"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_api_followup_returns_the_merged_question(client):
    h = _auth(client, "officer_state")
    first = client.post("/api/gujrera/analytics/query", json={"question": SCRUTINY}, headers=h).json()
    assert first["intent"] == "analytics" and first["refined"] is None
    narrowed = client.post("/api/gujrera/analytics/query",
                           json={"question": "only Bopal", "previous": first["question"]}, headers=h).json()
    assert narrowed["refined"] == [{"kind": "locality", "value": "Bopal"}]
    assert "bopal" in narrowed["question"] and "ahmedabad" in narrowed["question"]
    assert "locality = 'Bopal'" in narrowed["card"]["sql"]
    assert len(narrowed["card"]["rows"]) <= len(first["card"]["rows"])


def test_a_followup_cannot_leave_the_officers_district(client):
    h = _auth(client, "officer_ahmedabad")
    r = client.post("/api/gujrera/analytics/query",
                    json={"question": "in Surat instead", "previous": SCRUTINY}, headers=h).json()
    assert r["intent"] == "analytics_out_of_scope" and r["card"] is None


def test_chat_remembers_the_last_report(client):
    h = _auth(client, "officer_state")
    a = client.post("/api/gujrera/chat", json={"message": SCRUTINY}, headers=h).json()
    b = client.post("/api/gujrera/chat", json={"message": "last 3 months", "session_id": a["session_id"]}, headers=h).json()
    assert b["intent"] == "analytics" and b["text"].startswith("Narrowed the last report")
    card = next(c for c in b["cards"] if c.get("type") == "analytics")
    assert "opened_on >=" in card["sql"] and "ahmedabad" in card["question"]


def test_excel_export(client):
    from openpyxl import load_workbook

    h = _auth(client, "officer_ahmedabad")
    r = client.post("/api/gujrera/analytics/export", json={"question": "Developers issued notices"}, headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["Report"]
    cells = {(row[0].value, row[1].value) for row in ws.iter_rows(min_row=2, max_row=8) if row[0].value}
    assert ("District scope", "Ahmedabad") in cells and ("Run by", "officer_ahmedabad") in cells
    assert "Query" in wb.sheetnames and "SELECT" in wb["Query"]["A2"].value.upper()
    assert client.post("/api/gujrera/analytics/export", json={"question": "x"},
                       headers=_auth(client, "citizen_01")).status_code == 403
    assert client.post("/api/gujrera/analytics/export", json={"question": "make me tea"}, headers=h).status_code == 400


def test_saved_reports_are_private_to_each_officer(client):
    h1, h2 = _auth(client, "officer_state"), _auth(client, "officer_surat")
    s = client.post("/api/gujrera/analytics/saved", json={"name": "Scrutiny, Bopal", "question": SCRUTINY + " in bopal"},
                    headers=h1).json()
    again = client.post("/api/gujrera/analytics/saved", json={"name": "Renamed", "question": SCRUTINY + " in Bopal"},
                        headers=h1).json()
    assert again["id"] == s["id"] and again["name"] == "Renamed"  # same question: updated, not duplicated
    assert [x["id"] for x in client.get("/api/gujrera/analytics/saved", headers=h1).json()["saved"]] == [s["id"]]
    assert client.get("/api/gujrera/analytics/saved", headers=h2).json()["saved"] == []
    assert client.delete(f"/api/gujrera/analytics/saved/{s['id']}", headers=h2).status_code == 400
    client.post("/api/gujrera/analytics/query", json={"question": SCRUTINY + " in bopal"}, headers=h1)
    assert client.get("/api/gujrera/analytics/saved", headers=h1).json()["saved"][0]["last_run_at"]
    assert client.delete(f"/api/gujrera/analytics/saved/{s['id']}", headers=h1).status_code == 200
    assert client.get("/api/gujrera/analytics/saved", headers=_auth(client, "citizen_01")).status_code == 403
