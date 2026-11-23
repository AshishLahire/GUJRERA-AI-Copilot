"""Test records for the authority (officer) assistant: localities, applications under scrutiny, defaults,
notices issued and penalty amounts. Shaped like the internal tables the department will share, until the
real CSV/API data arrives. Deterministic (own random seed) and additive: existing records are not changed,
apart from filling in each project's locality.

    python scripts/seed_gujrera.py --add-authority-data
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gujrera.db.models import (
    AuthorityNotice,
    ComplianceEvent,
    Order,
    OrderPenalty,
    Project,
    ProjectScrutiny,
)
from gujrera.ingest.mock_generator import DEFAULT_AS_OF

# Localities by (district, taluka), with Gujarati and Hindi names for matching questions.
LOCALITIES: dict[tuple[str, str], list[tuple[str, str, str]]] = {
    ("Ahmedabad", "Ahmedabad City"): [("Satellite", "સેટેલાઇટ", "सैटेलाइट"), ("Thaltej", "થલતેજ", "थलतेज"),
                                      ("Prahlad Nagar", "પ્રહલાદ નગર", "प्रह्लाद नगर")],
    ("Ahmedabad", "Daskroi"): [("Bopal", "બોપલ", "बोपल"), ("Ghuma", "ઘુમા", "घुमा")],
    ("Ahmedabad", "Sanand"): [("Shela", "શેલા", "शेला"), ("South Bopal", "સાઉથ બોપલ", "साउथ बोपल")],
    ("Bhavnagar", "Bhavnagar"): [("Waghawadi Road", "વાઘાવાડી રોડ", "वाघावाडी रोड"),
                                 ("Kaliyabid", "કાળિયાબીડ", "कालियाबीड")],
    ("Gandhinagar", "Gandhinagar"): [("Kudasan", "કુડાસણ", "कुडासन"), ("Sargasan", "સરગાસણ", "सरगासन"),
                                     ("Raysan", "રાયસણ", "रायसन")],
    ("Rajkot", "Rajkot"): [("Kalawad Road", "કાલાવડ રોડ", "कालावड रोड"), ("Mavdi", "મવડી", "मवडी"),
                           ("Raiya", "રૈયા", "रैया")],
    ("Surat", "Choryasi"): [("Pal", "પાલ", "पाल"), ("Bhatar", "ભટાર", "भटार")],
    ("Surat", "Olpad"): [("Olpad", "ઓલપાડ", "ओलपाड"), ("Sayan", "સાયણ", "सायण")],
    ("Surat", "Surat City"): [("Adajan", "અડાજણ", "अडाजण"), ("Vesu", "વેસુ", "वेसु"), ("Piplod", "પીપલોદ", "पीपलोद")],
    ("Vadodara", "Vadodara"): [("Alkapuri", "અલકાપુરી", "अलकापुरी"), ("Gotri", "ગોત્રી", "गोत्री"),
                               ("Vasna Bhayli", "વાસણા ભાયલી", "वासणा भायली")],
}


def locality_names() -> dict[str, str]:
    """Every spelling (English lower-case, Gujarati, Hindi) -> locality name in the registry."""
    out: dict[str, str] = {}
    for names in LOCALITIES.values():
        for en, gu, hi in names:
            out[en.lower()] = en
            out[gu] = en
            out[hi] = en
    return out


def seed_authority(session: Session, as_of: date = DEFAULT_AS_OF, seed: int = 2027) -> dict[str, int]:
    """Add authority test records. Does nothing if they are already there."""
    if session.scalar(select(func.count()).select_from(ProjectScrutiny)):
        return {}
    rng = random.Random(seed)
    projects = session.scalars(select(Project).order_by(Project.id)).all()
    counts = {"localities": 0, "project_scrutiny": 0, "compliance_events": 0, "authority_notices": 0,
              "penalty_orders": 0}

    def day(back_from: int, back_to: int) -> date:
        return as_of - timedelta(days=rng.randint(back_from, back_to))

    for p in projects:
        if p.locality is None and (p.district, p.taluka) in LOCALITIES:
            p.locality = rng.choice(LOCALITIES[(p.district, p.taluka)])[0]
            counts["localities"] += 1

    # Applications under scrutiny: new registrations, extensions of delayed projects, alterations.
    for p in projects:
        r = rng.random()
        if p.status != "ongoing" or r > 0.22:
            continue
        subject = "extension" if p.revised_completion else rng.choice(("registration", "alteration"))
        stage = rng.choices(("under_scrutiny", "query_raised", "cleared", "rejected"), (5, 2, 3, 1))[0]
        opened = day(10, 300)
        closed = opened + timedelta(days=rng.randint(15, 90)) if stage in ("cleared", "rejected") else None
        session.add(ProjectScrutiny(project_id=p.id, subject=subject, stage=stage, opened_on=opened,
                                    closed_on=min(closed, as_of) if closed else None, is_mock=True))
        counts["project_scrutiny"] += 1

    # Defaults: missed quarterly progress reports, quarter-end returns, Form 5 annual reports, unpaid fees.
    for p in projects:
        if p.status not in ("ongoing", "lapsed") or rng.random() > 0.35:
            continue
        for _ in range(rng.randint(1, 3)):
            kind = rng.choices(("qpr_not_filed", "quarter_end_return_not_filed", "form5_annual_report_not_filed",
                                "fee_not_paid"), (5, 2, 2, 1))[0]
            when = day(5, 720)
            fy = when.year if when.month >= 4 else when.year - 1
            period = (f"FY{fy}-{str(fy + 1)[2:]}" if kind == "form5_annual_report_not_filed"
                      else f"{when.year}-Q{(when.month - 1) // 3 + 1}")
            resolved = when + timedelta(days=rng.randint(10, 120)) if rng.random() < 0.45 else None
            session.add(ComplianceEvent(project_id=p.id, promoter_id=p.promoter_id, event_type=kind, period=period,
                                        event_date=when, resolved_on=resolved if resolved and resolved <= as_of
                                        else None, is_mock=True))
            counts["compliance_events"] += 1
    session.flush()

    # Notices issued: mostly to projects with defaults, some show-cause notices on delayed projects.
    defaults = session.scalars(select(ComplianceEvent).order_by(ComplianceEvent.id)).all()
    seq = 0
    for e in defaults:
        if rng.random() > 0.55:
            continue
        seq += 1
        issued = min(as_of, e.event_date + timedelta(days=rng.randint(7, 60)))
        session.add(AuthorityNotice(ref_no=f"DEMO-NTC-{issued.year}-{seq:05d}", promoter_id=e.promoter_id,
                                    project_id=e.project_id,
                                    notice_type=rng.choices(("non_compliance", "show_cause", "hearing"), (6, 3, 1))[0],
                                    issued_on=issued, status=rng.choice(("issued", "replied", "closed")),
                                    is_mock=True))
    for p in projects:
        if p.status == "ongoing" and p.proposed_completion < as_of and rng.random() < 0.3:
            seq += 1
            issued = day(5, 400)
            session.add(AuthorityNotice(ref_no=f"DEMO-NTC-{issued.year}-{seq:05d}", promoter_id=p.promoter_id,
                                        project_id=p.id, notice_type="show_cause", issued_on=issued,
                                        status=rng.choice(("issued", "replied")), is_mock=True))
    counts["authority_notices"] = seq

    # Penalty orders with amounts: existing penalty orders get an amount; add some across districts.
    for o in session.scalars(select(Order).where(Order.order_type == "penalty_order")):
        session.add(OrderPenalty(order_id=o.id, amount=float(rng.choice((25_000, 50_000, 100_000, 200_000))),
                                 paid=rng.random() < 0.5, is_mock=True))
    seq = 0
    for p in projects:
        if rng.random() > 0.08:
            continue
        seq += 1
        issued = day(5, 540)
        o = Order(order_no=f"DEMO-PEN-{issued.year}-{seq:05d}", order_type="penalty_order", project_id=p.id,
                  promoter_id=p.promoter_id, issued_on=issued,
                  summary="Penalty under Section 63 for not complying with the Act (test record).", is_mock=True)
        session.add(o)
        session.flush()
        session.add(OrderPenalty(order_id=o.id, amount=float(rng.choice((25_000, 50_000, 100_000, 250_000, 500_000))),
                                 paid=rng.random() < 0.4, is_mock=True))
    counts["penalty_orders"] = seq
    session.commit()
    return counts
