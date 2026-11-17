"""Delay interest and refund calculator (RERA Act s.18; Gujarat RERA Rules r.16, r.17)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gujrera.api.routes import get_session, router
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.db.models import Project
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.tools.interest import STAY, WITHDRAW, Payment, calculate, default_rate, fmt_inr, parse_amount


# ------------------------------------------------------------------ arithmetic
def test_delay_interest_matches_hand_calculation():
    calc = calculate([Payment(4_000_000)], date(2026, 6, 26), until=date(2026, 11, 17), rate_pct=10.95)
    assert calc.delay_days == 144
    assert round(calc.interest) == 172_800  # 40,00,000 x 10.95% x 144 / 365
    assert calc.total == calc.interest and calc.refund_due_by is None


def test_delay_interest_starts_at_later_payment_and_is_zero_before_the_date():
    calc = calculate([Payment(1_000_000, date(2026, 9, 1))], date(2026, 6, 26), until=date(2026, 11, 17), rate_pct=10)
    assert calc.rows[0].start == date(2026, 9, 1) and calc.rows[0].days == 77
    early = calculate([Payment(1_000_000)], date(2027, 1, 1), until=date(2026, 11, 17), rate_pct=10)
    assert early.interest == 0 and early.delay_days == 0


def test_refund_runs_from_each_payment_and_is_due_in_45_days():
    calc = calculate([Payment(1_000_000, date(2024, 1, 1)), Payment(3_000_000, date(2025, 1, 1))],
                     date(2026, 6, 26), mode=WITHDRAW, until=date(2026, 11, 17), rate_pct=10.95)
    assert [r.days for r in calc.rows] == [1051, 685]
    assert round(calc.total) == 4_931_800
    assert calc.refund_due_by == date(2027, 1, 1)  # Rule 17


def test_refund_needs_payment_dates_and_sane_rate():
    with pytest.raises(ValueError, match="Rule 16"):
        calculate([Payment(100_000)], date(2026, 1, 1), mode=WITHDRAW)
    with pytest.raises(ValueError):
        calculate([Payment(100_000)], date(2026, 1, 1), rate_pct=55)
    with pytest.raises(ValueError):
        calculate([], date(2026, 1, 1))


def test_default_rate_is_sbi_mclr_plus_two():
    r = default_rate()
    assert r["rate"] == round(r["mclr"] + 2, 2) and r["mclr_as_of"]
    assert calculate([Payment(100_000)], date(2026, 1, 1), until=date(2026, 2, 1)).rate_pct == r["rate"]


@pytest.mark.parametrize("text,amount", [
    ("I paid 40 lakh", 4_000_000), ("₹40,00,000 paid in 2023", 4_000_000), ("મેં ૩૫ લાખ ચૂકવ્યા", 3_500_000),
    ("1.2 करोड़", 12_000_000), ("paid 40L", 4_000_000), ("rs 250000", 250_000), ("flat 302 in 2025", None),
])
def test_parse_amount(text, amount):
    assert parse_amount(text) == amount


def test_fmt_inr():
    assert fmt_inr(12_345_678) == "1,23,45,678" and fmt_inr(999) == "999" and fmt_inr(100_000) == "1,00,000"


# ------------------------------------------------------------------ chat + API
@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("interest") / "i.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
    yield factory
    engine.dispose()


def _delayed(s) -> Project:
    return next(p for p in s.scalars(select(Project).where(Project.status == "ongoing").order_by(Project.id))
                if p.proposed_completion < date.today())


def test_chat_calculates_for_a_named_project(Session):
    with Session() as s:
        p = _delayed(s)
        repo = Repository(s, Principal.anonymous())
        out = respond(f"How much interest will I get for the delay in {p.name}? I paid 40 lakh", ChatState(), repo).to_dict()
        assert out["intent"] == "interest_estimate"
        card = out["cards"][0]
        assert card["type"] == "interest" and card["amount"] == 4_000_000 and card["interest"] > 0
        ids = [x["id"] for x in out["sources"]]
        assert p.rera_no in ids and "RERA Act, 2016, Section 18" in ids and "Gujarat RERA General Rules, 2017, Rule 16" in ids
        gu = respond(f"{p.name_gu} માં મેં ૩૫ લાખ ચૂકવ્યા છે, વિલંબ માટે કેટલું વ્યાજ મળે?", ChatState(), repo).to_dict()
        assert gu["intent"] == "interest_estimate" and gu["lang"] == "gu" and gu["cards"][0]["amount"] == 3_500_000
        refund = respond(f"I want a refund from {p.name}, how much?", ChatState(), repo).to_dict()
        assert refund["cards"][0]["mode"] == "withdraw" and refund["cards"][0]["interest"] is None  # needs dates


def test_interest_question_without_project_is_a_law_question(Session):
    with Session() as s:
        repo = Repository(s, Principal.anonymous())
        for q in ("પઝેશનમાં વિલંબ થાય તો શું મને વ્યાજ મળે?", "कब्जे में देरी होने पर क्या मुझे ब्याज मिलेगा?"):
            out = respond(q, ChatState(), repo).to_dict()
            assert out["intent"] == "legal" and any("Section 18" in x["id"] for x in out["sources"])


@pytest.fixture
def client(Session):
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    return TestClient(app)


def test_api_search_and_calculate(client, Session):
    with Session() as s:
        p = _delayed(s)
        name, pid = p.name, p.id
    items = client.get("/api/gujrera/calc/projects", params={"q": name}).json()["items"]
    assert items[0]["id"] == pid
    body = client.post("/api/gujrera/calc/interest", json={
        "project_id": pid, "mode": "withdraw", "lang": "hi",
        "payments": [{"amount": 1_000_000, "paid_on": "2024-01-01"}], "possession_on": "2026-11-17", "rate": 10,
    }).json()
    assert body["result"]["rate_source"] == "agreement" and body["result"]["refund_due_by"] == "2027-01-01"
    assert body["result"]["total"] == 1_000_000 + round(1_000_000 * 0.10 * 1051 / 365)
    assert any("धारा 18" in x["text"] for x in body["sentences"])
    bad = client.post("/api/gujrera/calc/interest", json={"project_id": pid, "mode": "withdraw",
                                                          "payments": [{"amount": 100}]})
    assert bad.status_code == 400 and "Rule 16" in bad.json()["detail"]
    assert client.post("/api/gujrera/calc/interest", json={"project_id": 999999, "payments": [{"amount": 1}]}).status_code == 404
