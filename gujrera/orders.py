"""Order tracking: what an order directs the promoter to do, by when, and whether it was done,
explained in plain Gujarati, Hindi or English, with what the buyer can do next.

Law used (checked against the indexed RERA Act 2016):
- Section 40(1): interest, penalty or compensation not paid is recoverable as an arrear of land revenue.
- Section 63: a promoter who does not comply with the Authority's orders pays a penalty for every day of
  default, up to 5% of the estimated project cost.
- Section 44: an appeal to the Real Estate Appellate Tribunal within sixty days of receiving the order.
- Rule 17 (Gujarat RERA Rules): a refund with interest is payable within 45 days of becoming due;
  Section 14(3): defects reported within five years are rectified within 30 days.

Deadlines here are the days the direction allows from the order date (in the PoC they are read from
the order itself). Orders are public, so the order and its compliance status are shown to anyone;
amounts and the buyer's identity are not part of these records.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from gujrera.db.models import Complaint, Order, OrderCompliance, Project, Promoter
from gujrera.db.repository import AccessDenied, Repository
from gujrera.i18n import fmt_date
from gujrera.profile.summarise import Sentence

# complaint category -> (direction, days allowed, section the direction rests on)
DIRECTIONS: dict[str, tuple[str, int, str]] = {
    "refund": ("refund_interest", 45, "Rule 17"),
    "possession_delay": ("delay_interest", 45, "Section 18"),
    "compensation": ("pay_compensation", 45, "Section 71"),
    "structural_defect": ("rectify_defects", 30, "Section 14(3)"),
    "amenities_not_provided": ("provide_amenities", 90, "Section 14"),
    "plan_deviation": ("restore_plan", 90, "Section 14(2)"),
    "agreement_violation": ("comply_agreement", 45, "Section 13"),
    "false_advertisement": ("correct_advertisement", 30, "Section 12"),
}
SETTLED = ("carry_out_settlement", 30, "settlement recorded in the order")
MONEY = ("refund_interest", "delay_interest", "pay_compensation")
STATUSES = ("pending", "complied", "partly_complied", "not_complied", "recovery")

WHAT: dict[str, dict[str, str]] = {
    "refund_interest": {"en": "refund the amount paid with interest", "gu": "ચૂકવેલી રકમ વ્યાજ સાથે પરત કરવી",
                        "hi": "चुकाई गई राशि ब्याज सहित लौटाना"},
    "delay_interest": {"en": "pay interest for the delay in possession", "gu": "પઝેશનમાં વિલંબ માટે વ્યાજ ચૂકવવું",
                       "hi": "पज़ेशन में देरी के लिए ब्याज देना"},
    "pay_compensation": {"en": "pay the compensation ordered", "gu": "આદેશ મુજબ વળતર ચૂકવવું", "hi": "आदेश के अनुसार मुआवज़ा देना"},
    "rectify_defects": {"en": "repair the defects free of charge", "gu": "ખામીઓ મફત સુધારવી", "hi": "खामियाँ मुफ़्त ठीक करना"},
    "provide_amenities": {"en": "provide the promised amenities", "gu": "વચન આપેલી સુવિધાઓ આપવી", "hi": "वादा की गई सुविधाएँ देना"},
    "restore_plan": {"en": "undo the change made without consent to the sanctioned plan", "gu": "સંમતિ વગર મંજૂર પ્લાનમાં કરેલો ફેરફાર દૂર કરવો",
                     "hi": "बिना सहमति स्वीकृत नक्शे में किया बदलाव हटाना"},
    "comply_agreement": {"en": "act as the agreement for sale requires and return amounts taken against it",
                         "gu": "વેચાણ કરાર મુજબ વર્તવું અને તેની વિરુદ્ધ લીધેલી રકમ પરત કરવી",
                         "hi": "बिक्री अनुबंध के अनुसार चलना और उसके विरुद्ध ली गई राशि लौटाना"},
    "correct_advertisement": {"en": "withdraw or correct the misleading advertisement", "gu": "ગેરમાર્ગે દોરતી જાહેરાત પાછી ખેંચવી કે સુધારવી",
                              "hi": "भ्रामक विज्ञापन वापस लेना या सुधारना"},
    "carry_out_settlement": {"en": "carry out the settlement recorded in the order", "gu": "આદેશમાં નોંધાયેલું સમાધાન અમલમાં મૂકવું",
                             "hi": "आदेश में दर्ज समझौते को लागू करना"},
}
T: dict[str, dict[str, str]] = {
    "ordered": {"en": "Order {no} of {date} directs {promoter} to {what} by {due}.",
                "gu": "{date} ના આદેશ {no} મુજબ {promoter} એ {due} સુધીમાં {what}.",
                "hi": "{date} के आदेश {no} के अनुसार {promoter} को {due} तक {what} है।"},
    "complied": {"en": "Done: the promoter complied on {date}.", "gu": "પાલન થયું: પ્રમોટરે {date} એ પાલન કર્યું.",
                 "hi": "पालन हुआ: प्रमोटर ने {date} को पालन किया।"},
    "partly_complied": {"en": "Partly done: {note}", "gu": "આંશિક પાલન: {note}", "hi": "आंशिक पालन: {note}"},
    "pending": {"en": "Not due yet: {days} days left.", "gu": "હજી મુદત બાકી: {days} દિવસ.", "hi": "अभी समय बाकी: {days} दिन।"},
    "overdue": {"en": "Not done: the deadline passed {days} days ago.", "gu": "પાલન થયું નથી: મુદત {days} દિવસ પહેલાં વીતી ગઈ.",
                "hi": "पालन नहीं हुआ: समय-सीमा {days} दिन पहले निकल गई।"},
    "not_complied": {"en": "Not done: GUJRERA has recorded that the promoter did not comply.",
                     "gu": "પાલન થયું નથી: પ્રમોટરે પાલન નથી કર્યું એવી GUJRERA માં નોંધ છે.",
                     "hi": "पालन नहीं हुआ: GUJRERA में दर्ज है कि प्रमोटर ने पालन नहीं किया।"},
    "recovery": {"en": "Not done, so GUJRERA has started recovering the amount as an arrear of land revenue (Section 40).",
                 "gu": "પાલન ન થતાં GUJRERA એ રકમ જમીન મહેસૂલની બાકી તરીકે વસૂલવાનું શરૂ કર્યું છે (કલમ 40).",
                 "hi": "पालन न होने पर GUJRERA ने राशि भू-राजस्व के बकाया के रूप में वसूलना शुरू किया है (धारा 40)।"},
    "next_money": {"en": "What you can do: tell GUJRERA the order is not complied with. The amount can be recovered as an arrear of land revenue (Section 40), and the promoter faces a penalty for every day of default, up to 5% of the project cost (Section 63).",
                   "gu": "તમે શું કરી શકો: આદેશનું પાલન થયું નથી એમ GUJRERA ને જણાવો. રકમ જમીન મહેસૂલની બાકી તરીકે વસૂલી શકાય (કલમ 40), અને પ્રમોટરને દરેક દિવસના ડિફોલ્ટ માટે પ્રોજેક્ટ ખર્ચના 5% સુધી દંડ થઈ શકે (કલમ 63).",
                   "hi": "आप क्या कर सकते हैं: GUJRERA को बताएँ कि आदेश का पालन नहीं हुआ। राशि भू-राजस्व के बकाया के रूप में वसूली जा सकती है (धारा 40), और प्रमोटर पर हर दिन की चूक के लिए परियोजना लागत के 5% तक जुर्माना लग सकता है (धारा 63)।"},
    "next_works": {"en": "What you can do: tell GUJRERA the order is not complied with; the promoter faces a penalty for every day of default, up to 5% of the project cost (Section 63).",
                   "gu": "તમે શું કરી શકો: આદેશનું પાલન થયું નથી એમ GUJRERA ને જણાવો; પ્રમોટરને દરેક દિવસના ડિફોલ્ટ માટે પ્રોજેક્ટ ખર્ચના 5% સુધી દંડ થઈ શકે (કલમ 63).",
                   "hi": "आप क्या कर सकते हैं: GUJRERA को बताएँ कि आदेश का पालन नहीं हुआ; प्रमोटर पर हर दिन की चूक के लिए परियोजना लागत के 5% तक जुर्माना लग सकता है (धारा 63)।"},
    "dismissed": {"en": "Order {no} of {date} dismissed complaint {ref}. If you disagree, you can appeal to the Real Estate Appellate Tribunal within 60 days of receiving the order (Section 44).",
                  "gu": "{date} ના આદેશ {no} થી ફરિયાદ {ref} નામંજૂર થઈ. તમે અસંમત હો તો આદેશ મળ્યાના 60 દિવસમાં રિયલ એસ્ટેટ એપેલેટ ટ્રિબ્યુનલમાં અપીલ કરી શકો (કલમ 44).",
                  "hi": "{date} के आदेश {no} से शिकायत {ref} खारिज हुई। असहमत हों तो आदेश मिलने के 60 दिनों में रियल एस्टेट अपीलीय न्यायाधिकरण में अपील कर सकते हैं (धारा 44)।"},
}


def _t(key: str, lang: str, **v: Any) -> str:
    return T[key].get(lang, T[key]["en"]).format(**v)


def _act(sec: str) -> dict[str, Any]:
    return {"type": "legal_act", "id": f"RERA Act, 2016, Section {sec}", "is_mock": False}


def state(rec: OrderCompliance, today: date) -> str:
    if rec.status == "pending" and rec.due_on < today:
        return "overdue"
    return rec.status


def explain(order: Order, rec: OrderCompliance | None, complaint: Complaint | None, promoter: str, lang: str,
            today: date) -> list[Sentence]:
    cite = {"type": "order", "id": order.order_no, "is_mock": bool(order.is_mock)}
    if complaint is not None and complaint.outcome == "dismissed":
        return [Sentence(_t("dismissed", lang, no=order.order_no, date=fmt_date(order.issued_on, lang), ref=complaint.ref_no),
                         [cite, _act("44")], "order_dismissed")]
    if rec is None:
        return []
    what = WHAT[rec.direction].get(lang, WHAT[rec.direction]["en"])
    out = [Sentence(_t("ordered", lang, no=order.order_no, date=fmt_date(order.issued_on, lang), promoter=promoter,
                       what=what, due=fmt_date(rec.due_on, lang)), [cite], "order_ordered")]
    st = state(rec, today)
    if st == "complied":
        out.append(Sentence(_t("complied", lang, date=fmt_date(rec.complied_on, lang)), [cite], "order_complied"))
    elif st == "partly_complied":
        out.append(Sentence(_t("partly_complied", lang, note=rec.note or ""), [cite], "order_partly"))
    elif st == "pending":
        out.append(Sentence(_t("pending", lang, days=(rec.due_on - today).days), [cite], "order_pending"))
    else:
        if st == "overdue":
            out.append(Sentence(_t("overdue", lang, days=(today - rec.due_on).days), [cite], "order_overdue"))
        elif st == "not_complied":
            out.append(Sentence(_t("not_complied", lang), [cite], "order_not_complied"))
        else:
            out.append(Sentence(_t("recovery", lang), [cite, _act("40")], "order_recovery"))
        if st != "recovery":
            key = "next_money" if rec.direction in MONEY else "next_works"
            out.append(Sentence(_t(key, lang), [_act("40"), _act("63")] if key == "next_money" else [_act("63")], "order_next"))
    return out


def _clean(name: str | None) -> str:
    return (name or "").replace(" (Demo)", "").replace(" (ડેમો)", "")


def _bundle(s, orders: list[Order], lang: str, today: date) -> list[dict[str, Any]]:
    if not orders:
        return []
    ids = [o.id for o in orders]
    recs = {r.order_id: r for r in s.scalars(select(OrderCompliance).where(OrderCompliance.order_id.in_(ids)))}
    complaints = {c.id: c for c in s.scalars(select(Complaint).where(Complaint.id.in_({o.complaint_id for o in orders if o.complaint_id})))}
    promoters = {p.id: p.name for p in s.scalars(select(Promoter).where(Promoter.id.in_({o.promoter_id for o in orders if o.promoter_id})))}
    projects = {p.id: p for p in s.scalars(select(Project).where(Project.id.in_({o.project_id for o in orders if o.project_id})))}
    out = []
    for o in orders:
        rec, c = recs.get(o.id), complaints.get(o.complaint_id)
        sentences = explain(o, rec, c, _clean(promoters.get(o.promoter_id)), lang, today)
        if not sentences:
            continue
        proj = projects.get(o.project_id)
        out.append({
            "order_id": o.id, "order_no": o.order_no, "issued_on": o.issued_on.isoformat(), "order_type": o.order_type,
            "complaint_ref": c.ref_no if c else None, "outcome": c.outcome if c else None,
            "project": proj.name if proj else None, "project_id": o.project_id, "district": proj.district if proj else None,
            "promoter": _clean(promoters.get(o.promoter_id)),
            "direction": rec.direction if rec else None, "due_on": rec.due_on.isoformat() if rec else None,
            "state": state(rec, today) if rec else ("dismissed" if c and c.outcome == "dismissed" else None),
            "complied_on": rec.complied_on.isoformat() if rec and rec.complied_on else None,
            "sentences": [{"text": x.text, "citations": x.citations} for x in sentences],
            "is_mock": bool(o.is_mock),
        })
    return out


# ------------------------------------------------------------------ public lookups
def orders_for(repo: Repository, *, order_no: str | None = None, complaint_ref: str | None = None,
               project_id: int | None = None, lang: str = "en", as_of: date | None = None) -> list[dict[str, Any]]:
    """Complaint orders and their compliance. Orders are public records."""
    today = as_of or date.today()
    stmt = select(Order).where(Order.order_type == "complaint_order").order_by(Order.issued_on.desc())
    if order_no:
        stmt = stmt.where(Order.order_no == order_no.strip().upper())
    elif complaint_ref:
        stmt = stmt.join(Complaint, Complaint.id == Order.complaint_id).where(Complaint.ref_no == complaint_ref.strip().upper())
    elif project_id is not None:
        stmt = stmt.where(Order.project_id == project_id)
    else:
        return []
    rows = _bundle(repo.s, list(repo.s.scalars(stmt.limit(50))), lang, today)
    repo._audit("order_lookup", {"order_no": order_no, "complaint_ref": complaint_ref, "project_id": project_id, "n": len(rows)})
    return rows


def sentences_for_complaint(session, complaint_id: int, lang: str, today: date | None = None) -> list[Sentence]:
    """Order lines for the buyer's own complaint tracking."""
    today = today or date.today()
    orders = list(session.scalars(select(Order).where(Order.complaint_id == complaint_id, Order.order_type == "complaint_order")))
    out: list[Sentence] = []
    for b in _bundle(session, orders, lang, today):
        out += [Sentence(x["text"], x["citations"], "order_line") for x in b["sentences"]]
    return out


# ---------------------------------------------------------------------- officers
def _officer(repo: Repository) -> None:
    if repo.p.role != "officer":
        raise AccessDenied("Order enforcement is for GUJRERA officers.")


def to_enforce(repo: Repository, lang: str = "en", *, as_of: date | None = None) -> dict[str, Any]:
    """Orders not yet complied with, oldest deadline first (district officers: their district)."""
    _officer(repo)
    today = as_of or date.today()
    stmt = (select(Order).join(OrderCompliance, OrderCompliance.order_id == Order.id)
            .where(OrderCompliance.status.in_(("pending", "not_complied", "partly_complied", "recovery"))))
    if repo.p.district_scope:
        stmt = stmt.join(Project, Project.id == Order.project_id).where(Project.district == repo.p.district_scope)
    rows = _bundle(repo.s, list(repo.s.scalars(stmt)), lang, today)
    counts = {k: sum(r["state"] == k for r in rows) for k in ("overdue", "pending", "not_complied", "partly_complied", "recovery")}
    order = {"overdue": 0, "not_complied": 1, "partly_complied": 2, "recovery": 3, "pending": 4}
    rows.sort(key=lambda r: (order.get(r["state"], 9), r["due_on"] or ""))
    repo._audit("orders_to_enforce", {"n": len(rows)})
    return {"counts": counts, "items": rows}


def update(repo: Repository, order_id: int, status: str, *, complied_on: date | None = None, note: str | None = None,
           today: date | None = None) -> dict[str, Any] | None:
    _officer(repo)
    today = today or date.today()
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    rec = repo.s.scalar(select(OrderCompliance).where(OrderCompliance.order_id == order_id))
    order = repo.s.get(Order, order_id)
    if rec is None or order is None:
        return None
    if repo.p.district_scope:
        proj = repo.s.get(Project, order.project_id) if order.project_id else None
        if proj is None or proj.district != repo.p.district_scope:
            return None
    if status == "complied":
        complied_on = complied_on or today
        if complied_on > today or complied_on < order.issued_on:
            raise ValueError("The compliance date must be between the order date and today.")
    if status == "partly_complied" and not (note and note.strip()):
        raise ValueError("Say what has been done and what is left.")
    rec.status, rec.updated_on = status, today
    rec.complied_on = complied_on if status == "complied" else None
    if note and note.strip():
        rec.note = note.strip()[:300]
    repo.s.flush()
    repo._audit("order_compliance_updated", {"order_no": order.order_no, "status": status})
    return _bundle(repo.s, [order], "en", today)[0]


# ------------------------------------------------------------------ starting set
def seed_compliance(session, *, as_of: date | None = None, seed: int = 2016) -> int:
    """One compliance record for every complaint order that allowed (or settled) the complaint, with
    a deadline from DIRECTIONS and a status drawn so that most are complied, some are overdue."""
    rng = random.Random(seed)
    today = as_of or date.today()
    n = 0
    rows = session.execute(select(Order, Complaint).join(Complaint, Complaint.id == Order.complaint_id)
                           .where(Order.order_type == "complaint_order",
                                  Complaint.outcome.in_(("allowed", "partly_allowed", "settled")))).all()
    for order, c in rows:
        if session.scalar(select(OrderCompliance.id).where(OrderCompliance.order_id == order.id)):
            continue
        direction, days, _ = SETTLED if c.outcome == "settled" else DIRECTIONS.get(c.category, (None, 0, ""))
        if direction is None:
            continue
        due = order.issued_on + timedelta(days=days)
        status, complied_on, note = "pending", None, None
        roll = rng.random()
        if due >= today:
            if roll < 0.3:
                status, complied_on = "complied", order.issued_on + timedelta(days=rng.randint(5, max(6, (today - order.issued_on).days)))
        elif roll < 0.55:
            status, complied_on = "complied", order.issued_on + timedelta(days=rng.randint(10, days + 20))
        elif roll < 0.65:
            status, note = "partly_complied", "Interest paid; principal refund pending." if direction in MONEY else "Work started; not finished."
        elif roll < 0.75 and direction in MONEY:
            status, note = "recovery", "Recovery certificate sent to the Collector."
        if complied_on and complied_on > today:
            complied_on = today
        session.add(OrderCompliance(order_id=order.id, direction=direction, due_on=due, status=status,
                                    complied_on=complied_on, updated_on=complied_on or min(today, due), note=note,
                                    is_mock=bool(order.is_mock)))
        n += 1
    session.commit()
    return n
