"""The officer's work queue: what in their district needs action now.

Built from the registry the app holds (public records or GUJRERA's own data) and from what citizens do
in the app, never from guesses:

* Registrations ending in the next 90 days: remind the promoter to apply for an extension
  (RERA Act Section 6) or file completion.
* Past the registered completion date with no completion on record: ask for the completion /
  occupancy certificate or an extension application; otherwise the registration lapses (Section 7).
* Repeated extensions (EX2 or more in the registration number): chronic delay, worth a closer look.
* Citizen signals: RERA numbers citizens checked that do not exist (a fake project or ad), ads citizens
  reported, and complaints filed through the app.

Every list respects the officer's district. An officer marks an item reviewed, actioned or not an issue,
with a note; the mark and who made it are kept, and reviewed items drop to the bottom.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gujrera.db.models import (
    OPEN_COMPLAINT_STATUSES,
    Complaint,
    EnforcementCase,
    OfficerReview,
    Project,
    UnknownNumberLookup,
)
from gujrera.db.repository import AccessDenied, Repository
from gujrera.trust.rera_number import parse_rera_number

REVIEW_STATUSES = ("reviewed", "actioned", "dismissed")
ITEM_TYPES = ("expiring", "overdue", "extensions", "unknown_number", "ad_case", "complaint")
_EX = re.compile(r"/EX(\d{1,2})(?=/|$)")
LIMIT = 25


def _require_officer(repo: Repository) -> str | None:
    if repo.p.role != "officer":
        raise AccessDenied("The work queue is for GUJRERA officers.")
    return repo.p.district_scope


def _project_item(p: Project, kind: str, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "key": p.rera_no, "project_id": p.id, "name": p.name, "rera_no": p.rera_no,
            "district": p.district, "taluka": p.taluka, "completion": p.reg_valid_until.isoformat(),
            "is_mock": bool(p.is_mock), **extra}


def _taluka_key(name: str | None) -> str:
    """Spelling-insensitive key: lower case, letters only, no 'y', doubled letters collapsed."""
    k = re.sub(r"[^a-z]", "", (name or "").lower()).replace("y", "")
    return re.sub(r"(.)\1+", r"\1", k)


def _extensions(rera_no: str) -> int:
    nums = [int(n) for n in _EX.findall(rera_no or "")]
    return max(nums) if nums else 0


def record_unknown_number(session: Session, number: str, channel: str) -> None:
    """Remember a checked registration number that is not in the registry (no personal data)."""
    parsed = parse_rera_number(number)
    if parsed is None or parsed.is_mock:
        return
    today = date.today()
    try:
        with session.begin_nested():
            row = session.scalar(select(UnknownNumberLookup).where(UnknownNumberLookup.number == parsed.normalised))
            if row is None:
                session.add(UnknownNumberLookup(number=parsed.normalised,
                                                district=(parsed.district or "").title() or None,
                                                first_seen=today, last_seen=today, lookups=1, channels=channel))
            else:
                row.lookups += 1
                row.last_seen = today
                if channel not in row.channels.split(","):
                    row.channels = ",".join(c for c in (row.channels, channel) if c)
    except Exception:  # noqa: BLE001 - an older database without the table: never break the check itself
        return


def _reviews(session: Session) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r.item_type, r.item_key): {"status": r.status, "note": r.note, "by": r.username,
                                        "at": r.at.isoformat(timespec="minutes")}
            for r in session.scalars(select(OfficerReview))}


def dashboard(repo: Repository, today: date | None = None) -> dict[str, Any]:
    district = _require_officer(repo)
    today = today or date.today()
    s = repo.s

    def scoped(stmt):
        return stmt.where(Project.district == district) if district else stmt

    reviews = _reviews(s)

    def mark(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for it in items:
            it["review"] = reviews.get((it["type"], it["key"]))
        return sorted(items, key=lambda it: it["review"] is not None)  # open items first, order kept

    # 1. Registrations ending soon
    soon = today + timedelta(days=90)
    exp_q = scoped(select(Project).where(Project.status == "ongoing", Project.reg_valid_until >= today,
                                         Project.reg_valid_until <= soon))
    exp_n = s.scalar(select(func.count()).select_from(exp_q.subquery()))
    expiring = [_project_item(p, "expiring", days_left=(p.reg_valid_until - today).days)
                for p in s.scalars(exp_q.order_by(Project.reg_valid_until).limit(LIMIT))]

    # 2. Past completion, no completion recorded (unverified, or ongoing past its date)
    over_cond = ((Project.status == "unverified")
                 | ((Project.status == "ongoing") & (Project.reg_valid_until < today)))
    over_q = scoped(select(Project).where(over_cond))
    over_n = s.scalar(select(func.count()).select_from(over_q.subquery()))
    buckets = {"under_6_months": 0, "6_to_24_months": 0, "over_2_years": 0}
    for (end,) in s.execute(scoped(select(Project.reg_valid_until).where(over_cond))):
        age = (today - end).days
        buckets["under_6_months" if age < 183 else "6_to_24_months" if age < 730 else "over_2_years"] += 1
    # most recent first: a project that has just run past its date is the one still worth chasing
    overdue = [_project_item(p, "overdue", days_over=(today - p.reg_valid_until).days)
               for p in s.scalars(over_q.order_by(Project.reg_valid_until.desc()).limit(LIMIT))]

    # 3. Repeated extensions
    ext_rows = [p for p in s.scalars(scoped(select(Project).where(Project.rera_no.like("%/EX%"),
                                                                  Project.status.in_(("ongoing", "unverified")))))
                if _extensions(p.rera_no) >= 2]
    ext_rows.sort(key=lambda p: (-_extensions(p.rera_no), p.reg_valid_until))
    extensions = [_project_item(p, "extensions", extensions=_extensions(p.rera_no)) for p in ext_rows[:LIMIT]]

    # 4. Citizen signals
    since = today - timedelta(days=90)
    unk_q = select(UnknownNumberLookup).where(UnknownNumberLookup.last_seen >= since)
    if district:
        unk_q = unk_q.where(UnknownNumberLookup.district == district)
    unknown = [{"type": "unknown_number", "key": u.number, "number": u.number, "district": u.district,
                "lookups": u.lookups, "first_seen": u.first_seen.isoformat(), "last_seen": u.last_seen.isoformat(),
                "channels": u.channels}
               for u in s.scalars(unk_q.order_by(UnknownNumberLookup.lookups.desc(),
                                                 UnknownNumberLookup.last_seen.desc()).limit(LIMIT))]
    case_q = select(EnforcementCase).where(EnforcementCase.status.in_(("new", "reviewing")))
    if district:
        case_q = case_q.where(EnforcementCase.district == district)
    ad_cases = [{"type": "ad_case", "key": c.ref_no, "ref_no": c.ref_no, "title": c.title, "kind": c.kind,
                 "district": c.district, "claimed_rera": c.claimed_rera, "status": c.status,
                 "opened_on": c.opened_on.isoformat()}
                for c in s.scalars(case_q.order_by(EnforcementCase.opened_on.desc()).limit(LIMIT))]
    comp_q = select(Complaint).where(Complaint.status.in_(OPEN_COMPLAINT_STATUSES))
    if district:
        comp_q = comp_q.where(Complaint.district == district)
    comp_n = s.scalar(select(func.count()).select_from(comp_q.subquery()))
    complaints = [{"type": "complaint", "key": c.ref_no, "ref_no": c.ref_no, "category": c.category,
                   "district": c.district, "status": c.status, "filed_on": c.filed_on.isoformat(),
                   "age_days": (today - c.filed_on).days, "channel": c.channel}
                  for c in s.scalars(comp_q.order_by(Complaint.filed_on).limit(LIMIT))]

    # 5. New registrations (workload)
    reg = scoped(select(func.count()).select_from(Project))
    new_30 = s.scalar(reg.where(Project.reg_date >= today - timedelta(days=30)))
    new_90 = s.scalar(reg.where(Project.reg_date >= today - timedelta(days=90)))
    total = s.scalar(reg)

    # 6. Charts: registrations ending month by month (next 6 months), overdue projects by taluka
    months: list[dict[str, Any]] = []
    y, m = today.year, today.month
    for _ in range(6):
        first = date(y, m, 1)
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        n = s.scalar(scoped(select(func.count()).select_from(Project).where(
            Project.status == "ongoing", Project.reg_valid_until >= max(first, today), Project.reg_valid_until < nxt)))
        months.append({"month": first.isoformat()[:7], "count": n})
        y, m = nxt.year, nxt.month
    raw = s.execute(scoped(select(Project.taluka, func.count()).where(over_cond)).group_by(Project.taluka)).all()
    merged: dict[str, list] = {}  # the registry spells some talukas two ways ("Chorasi", "Choryasi")
    for t, n in raw:
        key = _taluka_key(t)
        entry = merged.setdefault(key, [t or "Not stated", 0, 0])
        if n > entry[2]:
            entry[0], entry[2] = t or "Not stated", n  # show the most used spelling
        entry[1] += n
    tal = sorted(((name, n) for name, n, _top in merged.values()), key=lambda x: -x[1])
    by_taluka = [{"taluka": t, "count": n} for t, n in tal[:8]]
    if len(tal) > 8:
        by_taluka.append({"taluka": "Other", "count": sum(n for _t, n in tal[8:])})

    repo._audit("officer_dashboard", {"district": district})
    return {
        "district": district, "as_of": today.isoformat(), "total_projects": total,
        "new_registrations": {"last_30_days": new_30, "last_90_days": new_90},
        "charts": {"ending_by_month": months, "overdue_by_taluka": by_taluka},
        "sections": {
            "expiring": {"count": exp_n, "items": mark(expiring)},
            "overdue": {"count": over_n, "age": buckets, "items": mark(overdue)},
            "extensions": {"count": len(ext_rows), "items": mark(extensions)},
            "unknown_numbers": {"count": len(unknown), "items": mark(unknown)},
            "ad_cases": {"count": len(ad_cases), "items": mark(ad_cases)},
            "complaints": {"count": comp_n, "items": mark(complaints)},
        },
        "hearings": _hearings(repo, today),
    }


def _hearings(repo: Repository, today: date) -> list[dict[str, Any]]:
    from gujrera.complaints.documents import upcoming_hearings

    return upcoming_hearings(repo, 14, today)


def review(repo: Repository, item_type: str, item_key: str, status: str, note: str | None) -> dict[str, Any]:
    _require_officer(repo)
    if item_type not in ITEM_TYPES:
        raise ValueError(f"item_type must be one of {', '.join(ITEM_TYPES)}")
    if status not in REVIEW_STATUSES:
        raise ValueError(f"status must be one of {', '.join(REVIEW_STATUSES)}")
    note = (note or "").strip()[:500] or None
    row = repo.s.scalar(select(OfficerReview).where(OfficerReview.item_type == item_type,
                                                    OfficerReview.item_key == item_key))
    if row is None:
        row = OfficerReview(item_type=item_type, item_key=item_key)
        repo.s.add(row)
    from gujrera.db.models import User

    user = repo.s.get(User, repo.p.user_id) if repo.p.user_id else None
    row.status, row.note, row.user_id, row.username, row.at = (status, note, repo.p.user_id,
                                                               user.username if user else None, datetime.now())
    repo.s.flush()
    repo._audit("officer_review", {"item_type": item_type, "item_key": item_key, "status": status})
    return {"item_type": item_type, "item_key": item_key, "status": status, "note": note,
            "at": row.at.isoformat(timespec="minutes")}
