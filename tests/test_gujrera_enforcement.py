"""Unregistered-project watch: citizen ad reports grouped into enforcement cases for officers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gujrera.api.routes import get_session, router
from gujrera.auth import issue_token
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.db.models import AdReport, AuditLog, EnforcementCase, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.enforcement import (LAPSED, MISLEADING, UNREGISTERED, extract_ad_details, file_report, get_case,
                                 kind_of, list_cases, seed_reports, update_case)
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.trust.checks import check_text
from gujrera.trust.samples import build_cases


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("enf") / "e.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
    yield factory
    engine.dispose()


def _repo(s, username: str | None = None) -> Repository:
    if username is None:
        return Repository(s, Principal.anonymous())
    return Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == username))))


def _ad(s, kind: str, i: int = 0) -> str:
    return [c for c in build_cases(s) if c.kind == kind][i].text


def test_extract_who_and_where():
    d = extract_ad_details("NEW LAUNCH! Utsav Enclave by Sabarmati Builders\nFlats in Gandhinagar.\n"
                           "Call 98250 12345 / +91-9825099999 or visit www.utsavenclave.in")
    assert d["project"] == "Utsav Enclave" and d["promoter"] == "Sabarmati Builders"
    assert d["district"] == "Gandhinagar" and d["phones"] == ["9825012345", "9825099999"]
    assert d["websites"] == ["www.utsavenclave.in"]
    gu = extract_ad_details("ધમાકા ઓફર! મંગલ સ્ક્વેર\nસુરત")
    assert gu["project"] == "મંગલ સ્ક્વેર" and gu["district"] == "Surat"


def test_kind_follows_the_check(Session):
    with Session() as s:
        repo = _repo(s)
        assert kind_of(check_text(_ad(s, "not_found"), repo)) == UNREGISTERED
        assert kind_of(check_text(_ad(s, "no_number"), repo)) == UNREGISTERED
        assert kind_of(check_text(_ad(s, "lapsed_or_revoked"), repo)) == LAPSED
        assert kind_of(check_text(_ad(s, "promoter_mismatch"), repo)) == MISLEADING
        assert kind_of(check_text(_ad(s, "booking_over_limit"), repo)) == MISLEADING
        assert kind_of(check_text(_ad(s, "genuine"), repo)) is None


def test_reports_group_into_cases_and_duplicates_are_not_counted(Session):
    with Session() as s:
        repo = _repo(s)
        base = _ad(s, "not_found", 0)
        r1, c1, new1 = file_report(repo, base, check_text(base, repo), channel="text", today=date(2026, 10, 1))
        again = "  " + base.upper() + "  "  # same ad, different spacing and case
        r2, c2, new2 = file_report(repo, again, check_text(again, repo), channel="upload")
        assert new1 and not new2 and r2.id == r1.id
        variant = base + "\nLimited units! Call 9825012345"  # same project and number, new wording
        r3, c3, new3 = file_report(repo, variant, check_text(variant, repo), channel="chat")
        assert new3 and c3.id == c1.id and r3.contact_phones == "9825012345"
        no_number = _ad(s, "no_number", 0)
        r4, c4, _ = file_report(repo, no_number, check_text(no_number, repo), channel="text")
        assert c4.id != c1.id and c4.kind == UNREGISTERED and r4.asks_payment_to_account
        # grouped by name + district when no number is shown
        similar = no_number.replace("Book now", "Hurry, book now")
        _, c5, new5 = file_report(repo, similar, check_text(similar, repo), channel="text")
        assert new5 and c5.id == c4.id
        with pytest.raises(ValueError):
            genuine = _ad(s, "genuine")
            file_report(repo, genuine, check_text(genuine, repo), channel="text")
        s.rollback()


def test_reporter_identity_is_not_stored(Session):
    with Session() as s:
        buyer = _repo(s, "citizen_02")
        ad = _ad(s, "lapsed_or_revoked", 0)
        row, _, _ = file_report(buyer, ad, check_text(ad, buyer), channel="text")
        cols = {c.name for c in AdReport.__table__.columns}
        assert row.reporter_user_id == buyer.p.user_id
        assert not cols & {"reporter_name", "reporter_phone", "mobile", "email", "ip"}
        s.rollback()


def test_officers_only_scope_and_workflow(Session):
    with Session() as s:
        seed_reports(s, as_of=date(2026, 11, 1))
        for username in (None, "citizen_01", "dev_001", "agent_001"):
            with pytest.raises(AccessDenied):
                list_cases(_repo(s, username))
        state = list_cases(_repo(s, "officer_state"), status="")
        assert state["counts"]["reports"] == s.scalar(select(func.count()).select_from(AdReport))
        counts = [i["reports"] for i in state["items"] if i["status"] != "closed"]
        assert counts == sorted(counts, reverse=True)  # most reported first
        surat = list_cases(_repo(s, "officer_surat"), status="", district="Ahmedabad")
        assert surat["items"] and {i["district"] for i in surat["items"]} == {"Surat"}
        other = s.scalar(select(EnforcementCase).where(EnforcementCase.district != "Surat"))
        assert get_case(_repo(s, "officer_surat"), other.id) is None  # cannot open another district's case
        case = s.scalar(select(EnforcementCase).where(EnforcementCase.status == "new"))
        officer = _repo(s, "officer_state")
        detail = get_case(officer, case.id)
        assert detail["evidence"] and detail["law"].startswith("RERA Act")
        with pytest.raises(ValueError):
            update_case(officer, case.id, status="closed")  # an outcome is needed to close
        out = update_case(officer, case.id, status="notice_issued", note="Notice 12/2026 under Section 3")
        assert out["status"] == "notice_issued" and "Notice 12/2026" in out["notes"]
        assert s.scalar(select(AuditLog.action).order_by(AuditLog.id.desc())) == "enforcement_case_updated"
        s.rollback()


def test_chat_for_officers_and_citizens(Session):
    with Session() as s:
        seed_reports(s, as_of=date(2026, 11, 1))
        out = respond("Show unregistered projects reported by citizens", ChatState(), _repo(s, "officer_state")).to_dict()
        assert out["intent"] == "enforcement" and out["cards"][0]["type"] == "enforcement"
        buyer = respond("unregistered projects in Surat", ChatState(), _repo(s)).to_dict()
        assert buyer["intent"] == "enforcement_info" and not buyer["cards"]
        s.rollback()


def test_api_report_rechecks_and_officer_endpoints(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    with Session() as s:
        bad, good = _ad(s, "possession_late", 1), _ad(s, "genuine", 1)
        officer = issue_token(s.scalar(select(User).where(User.username == "officer_state")))
        dev = issue_token(s.scalar(select(User).where(User.username == "dev_001")))
    res = client.post("/api/gujrera/trust/report", json={"text": bad, "channel": "upload"})
    assert res.status_code == 200 and res.json()["receipt"].startswith("RPT-") and res.json()["kind"] == MISLEADING
    assert client.post("/api/gujrera/trust/report", json={"text": bad}).json()["duplicate"] is True
    # the browser cannot force a report: a genuine ad is re-checked on the server and refused
    assert client.post("/api/gujrera/trust/report", json={"text": good}).status_code == 400
    assert client.get("/api/gujrera/enforcement/cases").status_code == 403
    assert client.get("/api/gujrera/enforcement/cases", headers={"Authorization": f"Bearer {dev}"}).status_code == 403
    listing = client.get("/api/gujrera/enforcement/cases", headers={"Authorization": f"Bearer {officer}"}).json()
    case_id = listing["items"][0]["id"]
    assert client.get(f"/api/gujrera/enforcement/cases/{case_id}", headers={"Authorization": f"Bearer {officer}"}).json()["evidence"]
    upd = client.post(f"/api/gujrera/enforcement/cases/{case_id}", json={"status": "bogus"},
                      headers={"Authorization": f"Bearer {officer}"})
    assert upd.status_code == 400
