"""RERA trust check: extraction, registry checks, verdicts and API."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.db.models import Agent, Project, Promoter
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import DEFAULT_AS_OF, MockConfig, generate
from gujrera.trust.checks import check_text
from gujrera.trust.extract import extract_claim
from gujrera.trust.samples import build_cases

AS_OF = DEFAULT_AS_OF


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("trust") / "t.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig(seed=3))
    yield factory
    engine.dispose()


@pytest.fixture
def repo(Session):
    with Session() as s:
        yield Repository(s, Principal.anonymous())
        s.rollback()


# ----------------------------------------------------------------- extraction
def test_extracts_english_ad():
    c = extract_claim(
        "Sabarmati Heights. GujRERA No: PR/GJ/AHMEDABAD/DASKROI/AUDA/RAA07226/200620. "
        "Possession Dec 2028. Book with just 20%! Price 45 Lakh onwards."
    )
    assert [n.normalised for n in c.project_numbers] == ["PR/GJ/AHMEDABAD/DASKROI/AUDA/RAA07226/200620"]
    assert c.possession.value == date(2028, 12, 1)
    assert c.booking_percent.value == 20.0
    assert c.price.value == 4_500_000
    assert c.mentions_rera and c.looks_like_property_offer


def test_extracts_gujarati_ad_with_gujarati_digits():
    c = extract_claim("2 BHK ફ્લેટ. પઝેશન ડિસેમ્બર ૨૦૨૮. બુકિંગ માત્ર રૂ. ૫૧,૦૦૦. કિંમત ૪૫ લાખ. રેરા નંબર આપેલ છે")
    assert c.possession.value == date(2028, 12, 1)
    assert c.booking_amount.value == 51_000
    assert c.price.value == 4_500_000
    assert c.mentions_rera


def test_extracts_hindi_possession():
    assert extract_claim("फ्लैट बुकिंग शुरू, पज़ेशन जून 2027").possession.value == date(2027, 6, 1)


def test_booking_amount_must_follow_keyword():
    c = extract_claim("Price Rs 45 lakh. Booking open now")
    assert c.booking_amount is None


# --------------------------------------------------------------- verdicts
@pytest.mark.parametrize("kind", ["genuine", "not_found", "lapsed_or_revoked", "promoter_mismatch",
                                  "possession_late", "no_number", "booking_over_limit"])
def test_case_kinds_get_expected_verdict(Session, kind):
    with Session() as s:
        cases = [c for c in build_cases(s, as_of=AS_OF, per_kind=4) if c.kind == kind]
        assert cases, f"no {kind} cases in mock data"
        repo = Repository(s, Principal.anonymous())
        for case in cases:
            report = check_text(case.text, repo, as_of=AS_OF)
            assert report.verdict in case.expected, (case.id, report.verdict, [c.id for c in report.checks])


def test_report_cites_registry_and_labels_mock(repo):
    p = repo.s.scalars(select(Project).where(Project.status == "ongoing")).first()
    report = check_text(f"{p.name} flats. RERA: {p.rera_no}", repo, as_of=AS_OF)
    lookup = next(c for c in report.checks if c.id == "registry_lookup")
    assert lookup.status == "pass" and lookup.source["id"] == p.rera_no
    assert report.is_mock and any(c.id == "mock_record" for c in report.checks)
    assert set(report.headline) == {"en", "gu", "hi"}


def test_short_text_is_unreadable(repo):
    assert check_text("RERA", repo, as_of=AS_OF).verdict == "unreadable"


def test_payment_to_account_raises_warning(repo):
    p = repo.s.scalars(select(Project).where(Project.status == "ongoing",
                                              Project.reg_valid_until > AS_OF)).first()
    pr = repo.s.get(Promoter, p.promoter_id)
    text = (f"{p.name} by {pr.name.replace(' (Demo)', '')}. RERA {p.rera_no}.\n"
            "Pay booking to A/c No 123456789012 IFSC SBIN0001234")
    report = check_text(text, repo, as_of=AS_OF)
    assert report.verdict == "registered_with_warnings"
    assert any(c.id == "forensic_payment_to_account" and c.status == "warn" for c in report.checks)


def test_unregistered_agent_is_mismatch(repo):
    p = repo.s.scalars(select(Project).where(Project.status == "ongoing",
                                              Project.reg_valid_until > AS_OF)).first()
    text = f"{p.name}. RERA {p.rera_no}. Agent: AG/GJ/SURAT/SURAT CITY/SUDA/AAA12345/010120"
    assert check_text(text, repo, as_of=AS_OF).verdict == "mismatch"


def test_registered_agent_passes(repo):
    agent = repo.s.scalars(select(Agent).where(Agent.status == "active", Agent.valid_until > AS_OF)).first()
    report = check_text(f"Flats for sale through agent {agent.reg_no}", repo, as_of=AS_OF)
    assert any(c.id == "agent_registration" and c.status == "pass" for c in report.checks)


def test_ocr_mangled_number_still_found_with_warning(repo):
    p = repo.s.scalars(select(Project).where(Project.status == "ongoing")).first()
    parts = p.rera_no.split("/")
    parts[3] = "WRONGTALUKA"
    report = check_text(f"{p.name} 2BHK. RERA: {'/'.join(parts)}", repo, as_of=AS_OF)
    assert any(c.id == "number_segments" and c.status == "warn" for c in report.checks)


# ----------------------------------------------------------------------- API
@pytest.fixture
def client(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


def test_api_samples_and_text(client):
    samples = client.get("/api/gujrera/trust/samples").json()
    assert samples["count"] >= 6 and samples["is_mock"]
    for item in samples["items"]:
        res = client.post("/api/gujrera/trust/text", json={"text": item["text"]})
        assert res.status_code == 200
        assert res.json()["verdict"] in item["expected"]


@pytest.mark.parametrize("payload", [{"text": ""}, {"text": "x" * 5001}])
def test_api_rejects_bad_text(client, payload):
    assert client.post("/api/gujrera/trust/text", json=payload).status_code == 400


def test_api_rejects_bad_upload(client):
    assert client.post("/api/gujrera/trust/upload", files={"file": ("a.txt", b"x")}).status_code == 400
    assert client.post("/api/gujrera/trust/upload", files={"file": ("a.png", b"")}).status_code == 400


def test_api_reports_empty_database(tmp_path, monkeypatch):
    import gujrera.api.routes as routes

    empty = make_engine(f"sqlite:///{(tmp_path / 'empty.sqlite').as_posix()}")
    monkeypatch.setattr(routes, "_engine", lambda: empty)
    app = FastAPI()
    app.include_router(router)
    res = TestClient(app).get("/api/gujrera/health")
    assert res.status_code == 503 and "seed_gujrera" in res.json()["detail"]
    empty.dispose()
