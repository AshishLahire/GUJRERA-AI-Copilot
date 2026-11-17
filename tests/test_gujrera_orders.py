"""Order tracking: what an order directs, by when, whether it was done, and what the buyer can do."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gujrera.api.routes import get_session, router
from gujrera.auth import issue_token
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.complaints.flow import _status_out
from gujrera.db.models import Complaint, Order, OrderCompliance, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.mock_generator import MockConfig, generate
from gujrera.orders import explain, orders_for, seed_compliance, state, to_enforce, update

AS_OF = date(2026, 11, 1)


@pytest.fixture(scope="module")
def Session(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("orders") / "o.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
        seed_compliance(s, as_of=AS_OF)
    yield factory
    engine.dispose()


def _repo(s, username: str | None) -> Repository:
    if username is None:
        return Repository(s, Principal.anonymous())
    return Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == username))))


def _order_with(s, outcome: str) -> tuple[Order, Complaint]:
    return s.execute(select(Order, Complaint).join(Complaint, Complaint.id == Order.complaint_id)
                     .where(Complaint.outcome == outcome, Complaint.category == "refund")).first()


def test_seed_covers_orders_that_direct_something(Session):
    with Session() as s:
        allowed = s.scalar(select(func.count()).select_from(Order).join(Complaint, Complaint.id == Order.complaint_id)
                           .where(Complaint.outcome.in_(("allowed", "partly_allowed", "settled")),
                                  (Complaint.category != "agent_misconduct") | (Complaint.outcome == "settled")))
        assert s.scalar(select(func.count()).select_from(OrderCompliance)) == allowed
        assert seed_compliance(s, as_of=AS_OF) == 0  # idempotent
        dismissed = s.scalar(select(OrderCompliance.id).join(Order).join(Complaint, Complaint.id == Order.complaint_id)
                             .where(Complaint.outcome == "dismissed"))
        assert dismissed is None


def test_each_state_is_explained_with_the_law(Session):
    with Session() as s:
        order, c = _order_with(s, "allowed")
        rec = s.scalar(select(OrderCompliance).where(OrderCompliance.order_id == order.id))
        rec.direction, rec.due_on = "refund_interest", order.issued_on + timedelta(days=45)
        cases = {
            ("pending", rec.due_on - timedelta(days=10)): ("pending", "10 days left", set()),
            ("pending", rec.due_on + timedelta(days=20)): ("overdue", "20 days ago", {"Section 40", "Section 63"}),
            ("recovery", rec.due_on + timedelta(days=20)): ("recovery", "arrear of land revenue", {"Section 40"}),
        }
        for (status, today), (want_state, phrase, laws) in cases.items():
            rec.status, rec.complied_on = status, None
            assert state(rec, today) == want_state
            lines = explain(order, rec, c, "Test Builders", "en", today)
            assert "refund the amount paid with interest" in lines[0].text
            assert any(phrase in x.text for x in lines)
            cited = {cc["id"].replace("RERA Act, 2016, ", "") for x in lines for cc in x.citations if cc["type"] == "legal_act"}
            assert laws <= cited
        rec.status, rec.complied_on = "complied", rec.due_on - timedelta(days=3)
        assert "complied on" in explain(order, rec, c, "X", "en", AS_OF)[1].text
        gu = explain(order, rec, c, "X", "gu", AS_OF)
        assert "પાલન થયું" in gu[1].text
        dorder, dc = _order_with(s, "dismissed")
        d = explain(dorder, None, dc, "X", "hi", AS_OF)
        assert "धारा 44" in d[0].text and any(cc["id"].endswith("Section 44") for cc in d[0].citations)
        s.rollback()


def test_public_lookups_and_buyer_tracking(Session):
    with Session() as s:
        repo = _repo(s, None)
        order, c = _order_with(s, "allowed")
        by_no = orders_for(repo, order_no=order.order_no.lower(), as_of=AS_OF)
        by_ref = orders_for(repo, complaint_ref=c.ref_no, as_of=AS_OF)
        assert by_no[0]["order_no"] == order.order_no == by_ref[0]["order_no"]
        assert orders_for(repo, project_id=c.project_id, as_of=AS_OF)
        assert orders_for(repo, order_no="DEMO-ORD-1999-99999") == [] and orders_for(repo) == []
        out = _status_out(c.ref_no, c.category, c.form, c.filed_on, "disposed", None, [], True, "en", session=s)
        assert any(x.key == "order_line" for x in out.sentences)  # the buyer's tracking shows the order
        s.rollback()


def test_officer_enforcement(Session):
    with Session() as s:
        for u in (None, "citizen_01", "dev_001"):
            with pytest.raises(AccessDenied):
                to_enforce(_repo(s, u))
        state_ = to_enforce(_repo(s, "officer_state"), as_of=AS_OF)
        assert state_["items"] and sum(state_["counts"].values()) == len(state_["items"])
        assert all(i["state"] != "complied" for i in state_["items"])
        surat = to_enforce(_repo(s, "officer_surat"), as_of=AS_OF)
        assert {i["district"] for i in surat["items"]} <= {"Surat"}
        officer = _repo(s, "officer_state")
        item = state_["items"][0]
        with pytest.raises(ValueError):
            update(officer, item["order_id"], "complied", complied_on=date.today() + timedelta(days=5))
        with pytest.raises(ValueError):
            update(officer, item["order_id"], "partly_complied")
        out = update(officer, item["order_id"], "complied", note="Refund cheque received by the buyer")
        assert out["state"] == "complied"
        other = next((i for i in state_["items"] if i["district"] != "Surat"), None)
        if other:
            assert update(_repo(s, "officer_surat"), other["order_id"], "recovery") is None
        s.rollback()


def test_chat_and_api(Session):
    with Session() as s:
        order, c = _order_with(s, "allowed")
        anon = respond(f"Has the builder complied with the order in {c.ref_no}?", ChatState(), _repo(s, None)).to_dict()
        assert anon["intent"] == "order_status" and anon["cards"][0]["type"] == "orders"
        by_no = respond(f"What does order {order.order_no} say?", ChatState(), _repo(s, None)).to_dict()
        assert by_no["intent"] == "order_status"
        off = respond("Which orders are not complied with?", ChatState(), _repo(s, "officer_state")).to_dict()
        assert off["intent"] == "orders_to_enforce"
        assert respond("Which promoters in Surat have the most delayed projects?", ChatState(),
                       _repo(s, "officer_state")).intent != "orders_to_enforce"
        token = issue_token(s.scalar(select(User).where(User.username == "officer_state")))
        order_no = order.order_no
        s.rollback()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with Session() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    client = TestClient(app)
    assert client.get("/api/gujrera/orders/track").status_code == 400
    assert client.get("/api/gujrera/orders/track", params={"order_no": order_no}).json()["items"]
    assert client.get("/api/gujrera/orders/enforce").status_code == 403
    h = {"Authorization": f"Bearer {token}"}
    items = client.get("/api/gujrera/orders/enforce", headers=h).json()["items"]
    res = client.post(f"/api/gujrera/orders/{items[0]['order_id']}/compliance", json={"status": "recovery"}, headers=h)
    assert res.status_code == 200 and res.json()["state"] == "recovery"
