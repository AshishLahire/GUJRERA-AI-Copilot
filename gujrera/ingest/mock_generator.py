"""Reproducible mock GUJRERA data for the prototype.

Everything produced here has ``is_mock=True``, promoter and agent names end in
"(Demo)", and registration numbers use the ``MOCK`` code prefix, so no row can
be mistaken for (or defame) a real promoter, agent or project.

The generator is seeded and dated against a fixed ``as_of`` date so the same
seed always yields the same database, which keeps evaluation answers stable.
Distributions are tuned to make the demo questions interesting: about one in
five promoters is "troubled" (frequent delays, late quarterly reports, more
complaints and adverse orders).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gujrera.db.models import (
    Agent,
    Approval,
    Complaint,
    ComplaintEvent,
    DueNotice,
    Order,
    Project,
    ProjectProgress,
    Promoter,
    User,
)

DEFAULT_AS_OF = date(2026, 11, 1)

# (district, Gujarati, [(taluka, planning authority)], weight)
DISTRICTS: list[tuple[str, str, list[tuple[str, str]], int]] = [
    ("Ahmedabad", "અમદાવાદ", [("Ahmedabad City", "AUDA"), ("Daskroi", "AUDA"), ("Sanand", "AUDA")], 3),
    ("Surat", "સુરત", [("Surat City", "SUDA"), ("Choryasi", "SUDA"), ("Olpad", "SUDA")], 3),
    ("Vadodara", "વડોદરા", [("Vadodara", "VUDA")], 2),
    ("Rajkot", "રાજકોટ", [("Rajkot", "RUDA")], 2),
    ("Gandhinagar", "ગાંધીનગર", [("Gandhinagar", "GUDA")], 1),
    ("Bhavnagar", "ભાવનગર", [("Bhavnagar", "BADA")], 1),
]

STEMS = [
    ("Sabarmati", "સાબરમતી"), ("Narmada", "નર્મદા"), ("Tapi", "તાપી"), ("Girnar", "ગિરનાર"),
    ("Akshar", "અક્ષર"), ("Shanti", "શાંતિ"), ("Prakash", "પ્રકાશ"), ("Suvarna", "સુવર્ણ"),
    ("Navrang", "નવરંગ"), ("Vasant", "વસંત"), ("Utsav", "ઉત્સવ"), ("Kesar", "કેસર"),
    ("Mangal", "મંગલ"), ("Sarjan", "સર્જન"), ("Aangan", "આંગણ"), ("Pratham", "પ્રથમ"),
]
PROMOTER_SUFFIXES = [
    ("Developers", "ડેવલપર્સ"), ("Infra", "ઇન્ફ્રા"), ("Builders", "બિલ્ડર્સ"),
    ("Realty", "રિયલ્ટી"), ("Constructions", "કન્સ્ટ્રક્શન્સ"),
]
PROJECT_SUFFIXES = [
    ("Residency", "રેસિડેન્સી"), ("Heights", "હાઇટ્સ"), ("Greens", "ગ્રીન્સ"),
    ("Arcade", "આર્કેડ"), ("Avenue", "એવન્યુ"), ("Park", "પાર્ક"), ("Enclave", "એન્ક્લેવ"),
]
FIRST_NAMES = [
    ("Rakesh", "રાકેશ"), ("Nilesh", "નિલેશ"), ("Hetal", "હેતલ"), ("Jignesh", "જિજ્ઞેશ"),
    ("Priya", "પ્રિયા"), ("Kiran", "કિરણ"), ("Mehul", "મેહુલ"), ("Darshana", "દર્શના"),
]
SURNAMES = [
    ("Patel", "પટેલ"), ("Shah", "શાહ"), ("Desai", "દેસાઈ"), ("Mehta", "મહેતા"),
    ("Joshi", "જોશી"), ("Parmar", "પરમાર"), ("Trivedi", "ત્રિવેદી"), ("Chauhan", "ચૌહાણ"),
]
DEMO_EN, DEMO_GU = "(Demo)", "(ડેમો)"

COMPLAINT_TEMPLATES = {
    "possession_delay": "Possession not handed over; agreement promised possession by {date}.",
    "refund": "Buyer seeks refund of booking amount with interest after withdrawing from the project.",
    "structural_defect": "Seepage and cracks reported in the unit within five years of possession.",
    "plan_deviation": "Construction deviates from the sanctioned plan without buyer consent.",
    "false_advertisement": "Brochure advertised amenities and approvals that do not exist.",
    "amenities_not_provided": "Club house and parking promised in the agreement not provided.",
    "agreement_violation": "Promoter demanded payments not linked to construction stage.",
    "agent_misconduct": "Agent collected token money without issuing a receipt.",
    "compensation": "Buyer seeks compensation for loss caused by delayed possession.",
}

STATUS_FLOW = ["filed", "under_scrutiny", "hearing_scheduled", "order_reserved", "disposed"]


@dataclass
class MockConfig:
    seed: int = 2016
    as_of: date = DEFAULT_AS_OF
    n_promoters: int = 60
    n_agents: int = 80
    n_citizens: int = 10
    troubled_share: float = 0.2


@dataclass
class _Ctx:
    rng: random.Random
    cfg: MockConfig
    project_seq: int = 0
    order_seq: int = 0
    complaint_seq: int = 0
    citizen_ids: list[int] = field(default_factory=list)


def _days(rng: random.Random, lo: int, hi: int) -> timedelta:
    return timedelta(days=rng.randint(lo, hi))


def _ddmmyy(d: date) -> str:
    return d.strftime("%d%m%y")


def _quarter_label(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def _quarter_end(d: date) -> date:
    q_last_month = ((d.month - 1) // 3 + 1) * 3
    nxt = date(d.year + (q_last_month == 12), q_last_month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def _pick_district(rng: random.Random) -> tuple[str, str, list[tuple[str, str]]]:
    d = rng.choices(DISTRICTS, weights=[w for *_, w in DISTRICTS])[0]
    return d[0], d[1], d[2]


def generate(session: Session, cfg: MockConfig | None = None) -> dict[str, int]:
    """Populate an empty database. Returns row counts per table."""
    cfg = cfg or MockConfig()
    ctx = _Ctx(rng=random.Random(cfg.seed), cfg=cfg)
    rng = ctx.rng

    names = rng.sample([(s, p) for s in STEMS for p in PROMOTER_SUFFIXES], cfg.n_promoters)
    promoters: list[tuple[Promoter, bool]] = []
    for (stem, suf) in names:
        district, _, _ = _pick_district(rng)
        p = Promoter(
            name=f"{stem[0]} {suf[0]} {DEMO_EN}",
            name_gu=f"{stem[1]} {suf[1]} {DEMO_GU}",
            promoter_type=rng.choice(["company", "company", "llp", "partnership", "individual"]),
            district=district,
            address=f"Demo address, {district}",
            is_mock=True,
        )
        session.add(p)
        promoters.append((p, rng.random() < cfg.troubled_share))
    session.flush()

    _make_users(session, ctx, [p for p, _ in promoters])
    agents = _make_agents(session, ctx)

    for promoter, troubled in promoters:
        for _ in range(rng.choices([1, 2, 3, 4, 5, 6], weights=[3, 4, 3, 2, 1, 1])[0]):
            _make_project(session, ctx, promoter, troubled, agents)
    _make_promoter_dues(session, ctx, promoters)
    session.commit()

    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in (Promoter, Project, ProjectProgress, Approval, Agent, User, Complaint,
                      ComplaintEvent, Order, DueNotice)
    }


def _make_users(session: Session, ctx: _Ctx, promoters: list[Promoter]) -> None:
    session.add(User(username="officer_state", role="officer", district_scope=None, preferred_lang="en"))
    for district, *_ in DISTRICTS:
        session.add(User(username=f"officer_{district.lower()}", role="officer",
                         district_scope=district, preferred_lang="gu"))
    for p in promoters:
        session.add(User(username=f"dev_{p.id:03d}", role="developer", promoter_id=p.id, preferred_lang="gu"))
    for i in range(1, ctx.cfg.n_citizens + 1):
        u = User(username=f"citizen_{i:02d}", role="citizen",
                 preferred_lang=["gu", "hi", "en"][i % 3])
        session.add(u)
        session.flush()
        ctx.citizen_ids.append(u.id)


def _make_agents(session: Session, ctx: _Ctx) -> list[Agent]:
    rng, as_of = ctx.rng, ctx.cfg.as_of
    agents = []
    for i in range(1, ctx.cfg.n_agents + 1):
        district, _, talukas = _pick_district(rng)
        taluka, auth = rng.choice(talukas)
        fn, sn = rng.choice(FIRST_NAMES), rng.choice(SURNAMES)
        reg = date(2018, 1, 1) + _days(rng, 0, (as_of - date(2018, 1, 1)).days - 30)
        valid = reg + timedelta(days=5 * 365)
        roll = rng.random()
        status = "revoked" if roll < 0.03 else ("expired" if valid < as_of else "active")
        a = Agent(
            reg_no=f"AG/GJ/{district.upper()}/{taluka.upper()}/{auth}/MOCK{50000 + i:05d}/{_ddmmyy(reg)}",
            name=f"{fn[0]} {sn[0]} {DEMO_EN}",
            name_gu=f"{fn[1]} {sn[1]} {DEMO_GU}",
            district=district, reg_date=reg, valid_until=valid, status=status, is_mock=True,
        )
        session.add(a)
        agents.append(a)
    session.flush()
    for a in agents[:10]:
        session.add(User(username=f"agent_{a.id:03d}", role="agent", agent_id=a.id, preferred_lang="gu"))
    return agents


def _make_project(session: Session, ctx: _Ctx, promoter: Promoter, troubled: bool,
                  agents: list[Agent]) -> None:
    rng, as_of = ctx.rng, ctx.cfg.as_of
    ctx.project_seq += 1
    # Most projects sit in the promoter's home district.
    if rng.random() < 0.8:
        district = promoter.district
        talukas = next(d[2] for d in DISTRICTS if d[0] == district)
        district_gu = next(d[1] for d in DISTRICTS if d[0] == district)
    else:
        district, district_gu, talukas = _pick_district(rng)
    taluka, auth = rng.choice(talukas)
    stem, suf = rng.choice(STEMS), rng.choice(PROJECT_SUFFIXES)
    ptype = rng.choices(["residential", "commercial", "mixed", "plotted"], weights=[6, 2, 1, 1])[0]
    units = rng.randint(20, 600)

    reg = date(2018, 1, 1) + _days(rng, 0, (as_of - date(2018, 1, 1)).days - 90)
    proposed = reg + _days(rng, 2 * 365, 5 * 365)
    revised = actual = None
    status = "ongoing"
    delay_p = 0.7 if troubled else 0.25
    delayed = rng.random() < delay_p

    if delayed:
        delay = _days(rng, 30, 900)
        finish = proposed + delay
        if finish <= as_of:
            actual = finish
            status = "completed"
        if finish > proposed:
            revised = proposed + delay + _days(rng, 0, 120)
        if status == "ongoing" and proposed < as_of and rng.random() < 0.1:
            revised, status = None, "lapsed"  # no extension sought
    elif proposed <= as_of:
        actual, status = proposed - _days(rng, 0, 120), "completed"
    if troubled and status == "ongoing" and rng.random() < 0.08:
        status = "revoked"
    valid_until = revised or proposed

    name = f"{stem[0]} {suf[0]}"
    project = Project(
        rera_no=f"PR/GJ/{district.upper()}/{taluka.upper()}/{auth}/MOCK{ctx.project_seq:05d}/{_ddmmyy(reg)}",
        promoter_id=promoter.id, name=name, name_gu=f"{stem[1]} {suf[1]}",
        district=district, taluka=taluka, planning_authority=auth, project_type=ptype,
        status=status, units=units, reg_date=reg, proposed_completion=proposed,
        revised_completion=revised, actual_completion=actual, reg_valid_until=valid_until, is_mock=True,
    )
    session.add(project)
    session.flush()

    _make_progress(session, ctx, project, troubled)
    _make_approvals(session, ctx, project, auth)
    if revised:
        _add_order(session, ctx, "extension_order", project, promoter.id, reg + (revised - reg) // 2,
                   f"Registration of {name} extended to {revised.isoformat()} under Section 6.")
    if status == "revoked":
        _add_order(session, ctx, "revocation_order", project, promoter.id, as_of - _days(rng, 10, 300),
                   f"Registration of {name} revoked under Section 7 for persistent non-compliance.")
    _make_complaints(session, ctx, project, promoter, troubled, delayed, agents)


def _make_progress(session: Session, ctx: _Ctx, project: Project, troubled: bool) -> None:
    rng, as_of = ctx.rng, ctx.cfg.as_of
    end = min(project.actual_completion or as_of, as_of)
    total_days = max((project.actual_completion or project.revised_completion
                      or project.proposed_completion) - project.reg_date, timedelta(days=1)).days
    q_end = _quarter_end(project.reg_date)
    while q_end < end:
        due = q_end + timedelta(days=15)
        if due > as_of:
            break
        frac = min(1.0, (q_end - project.reg_date).days / total_days)
        pct = round(min(100.0, 100 * frac * rng.uniform(0.85, 1.05)), 1)
        miss = rng.random() < (0.25 if troubled else 0.04)
        late = not miss and rng.random() < (0.3 if troubled else 0.08)
        filed = None if miss else due + (_days(rng, 1, 90) if late else -_days(rng, 0, 14))
        session.add(ProjectProgress(project_id=project.id, quarter=_quarter_label(q_end),
                                    percent_complete=pct, due_on=due, filed_on=filed, is_mock=True))
        q_end = _quarter_end(q_end + timedelta(days=1))


def _make_approvals(session: Session, ctx: _Ctx, project: Project, auth: str) -> None:
    rng = ctx.rng
    kinds = ["layout_plan", "building_permission", "non_agricultural", "fire_noc"]
    if project.units > 300:
        kinds.append("environment_clearance")
    for kind in kinds:
        authority = {"fire_noc": "Fire Department", "environment_clearance": "SEIAA Gujarat",
                     "non_agricultural": "Collector"}.get(kind, auth)
        pending = kind in ("fire_noc", "environment_clearance") and rng.random() < 0.2
        decided = None if pending else project.reg_date - _days(rng, 10, 400)
        session.add(Approval(
            project_id=project.id, kind=kind, authority=authority,
            status="pending" if pending else "granted",
            ref=None if pending else f"DEMO/{kind[:3].upper()}/{project.id:04d}",
            decided_on=decided, is_mock=True,
        ))


def _make_complaints(session: Session, ctx: _Ctx, project: Project, promoter: Promoter,
                     troubled: bool, delayed: bool, agents: list[Agent]) -> None:
    rng, as_of = ctx.rng, ctx.cfg.as_of
    base = (3 if troubled else 0.6) + (2 if delayed else 0)
    count = sum(1 for _ in range(int(base * 3)) if rng.random() < 1 / 3)
    first_possible = project.reg_date + timedelta(days=180)
    if first_possible >= as_of:
        return
    cats = list(COMPLAINT_TEMPLATES)
    weights = [6 if delayed else 1, 2, 2, 1, 1, 2, 2, 1, 2 if delayed else 1]
    for _ in range(count):
        ctx.complaint_seq += 1
        category = rng.choices(cats, weights=weights)[0]
        filed = first_possible + _days(rng, 0, (as_of - first_possible).days)
        agent = rng.choice(agents) if category == "agent_misconduct" else None
        citizen = rng.choice(ctx.citizen_ids) if rng.random() < 0.15 else None
        c = Complaint(
            ref_no=f"DEMO-CMP-{filed.year}-{ctx.complaint_seq:05d}",
            project_id=project.id, promoter_id=promoter.id, agent_id=agent.id if agent else None,
            complainant_user_id=citizen,
            complainant_hash=hashlib.sha256(f"demo-complainant-{ctx.complaint_seq}".encode()).hexdigest(),
            form="B" if category == "compensation" else "A",
            category=category,
            summary=COMPLAINT_TEMPLATES[category].format(date=project.proposed_completion.isoformat()),
            district=project.district, filed_on=filed, status="filed", is_mock=True,
        )
        session.add(c)
        session.flush()

        # Walk the status flow; older complaints get further along.
        at = filed
        session.add(ComplaintEvent(complaint_id=c.id, at=at, status="filed", note="Complaint registered"))
        for status in STATUS_FLOW[1:]:
            step = _days(rng, 20, 150 if not troubled else 200)
            if at + step > as_of:
                break
            at += step
            c.status = status
            session.add(ComplaintEvent(complaint_id=c.id, at=at, status=status, note=None))
        if c.status == "disposed":
            c.closed_on = at
            c.outcome = rng.choices(["allowed", "partly_allowed", "dismissed", "settled"],
                                    weights=[4, 3, 2, 1] if troubled else [2, 2, 3, 2])[0]
            _add_order(session, ctx, "complaint_order", project, promoter.id, at,
                       f"Complaint {c.ref_no} ({category.replace('_', ' ')}) disposed: {c.outcome.replace('_', ' ')}.",
                       complaint_id=c.id)
        elif rng.random() < 0.03:
            c.status, c.closed_on = "withdrawn", at + timedelta(days=1)
            session.add(ComplaintEvent(complaint_id=c.id, at=c.closed_on, status="withdrawn",
                                       note="Withdrawn by complainant"))


def _add_order(session: Session, ctx: _Ctx, order_type: str, project: Project | None,
               promoter_id: int, issued: date, summary: str, complaint_id: int | None = None) -> None:
    ctx.order_seq += 1
    session.add(Order(
        order_no=f"DEMO-ORD-{issued.year}-{ctx.order_seq:05d}", order_type=order_type,
        complaint_id=complaint_id, project_id=project.id if project else None,
        promoter_id=promoter_id, issued_on=min(issued, ctx.cfg.as_of), summary=summary, is_mock=True,
    ))


def _make_promoter_dues(session: Session, ctx: _Ctx, promoters: list[tuple[Promoter, bool]]) -> None:
    rng, as_of = ctx.rng, ctx.cfg.as_of
    for promoter, troubled in promoters:
        projects = session.scalars(select(Project).where(Project.promoter_id == promoter.id)).all()
        for project in projects:
            missed = session.scalars(select(ProjectProgress).where(
                ProjectProgress.project_id == project.id, ProjectProgress.filed_on.is_(None))).all()
            for qpr in missed[-2:]:  # penalties for the most recent missed reports
                issued = qpr.due_on + timedelta(days=30)
                if issued > as_of:
                    continue
                session.add(DueNotice(
                    promoter_id=promoter.id, project_id=project.id, kind="late_qpr_penalty",
                    description=f"Penalty for quarterly progress report {qpr.quarter} not filed ({project.name}).",
                    amount=float(rng.choice([10000, 25000, 50000])), issued_on=issued,
                    due_date=issued + timedelta(days=30),
                    status=rng.choices(["pending", "paid"], weights=[3, 1] if troubled else [1, 3])[0],
                ))
        if troubled and rng.random() < 0.7:
            issued = as_of - _days(rng, 5, 120)
            session.add(DueNotice(
                promoter_id=promoter.id, kind="notice",
                description="Show-cause notice: repeated failure to file quarterly progress reports.",
                amount=None, issued_on=issued, due_date=issued + timedelta(days=21),
                status=rng.choice(["pending", "responded"]),
            ))
            _add_order(session, ctx, "show_cause", None, promoter.id, issued,
                       f"Show-cause notice to {promoter.name} for non-filing of quarterly progress reports.")
            if rng.random() < 0.5:
                pen_date = issued + _days(rng, 25, 60)
                if pen_date <= as_of:
                    amount = float(rng.choice([100000, 250000, 500000]))
                    session.add(DueNotice(
                        promoter_id=promoter.id, kind="penalty",
                        description="Penalty under Section 63 for non-compliance with Authority directions.",
                        amount=amount, issued_on=pen_date, due_date=pen_date + timedelta(days=30),
                        status=rng.choice(["pending", "paid"]),
                    ))
                    _add_order(session, ctx, "penalty_order", None, promoter.id, pen_date,
                               f"Penalty of Rs {amount:,.0f} imposed on {promoter.name} under Section 63.")
        if rng.random() < 0.6:
            issued = date(as_of.year, 4, 1) if as_of.month >= 4 else date(as_of.year - 1, 4, 1)
            session.add(DueNotice(
                promoter_id=promoter.id, kind="annual_fee",
                description=f"Annual compliance fee for FY {issued.year}-{str(issued.year + 1)[-2:]}.",
                amount=float(rng.choice([5000, 10000, 20000])), issued_on=issued,
                due_date=issued + timedelta(days=60), status=rng.choices(["paid", "pending"], weights=[4, 1])[0],
            ))
