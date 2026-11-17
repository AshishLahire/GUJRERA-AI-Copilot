"""Quarterly progress report assistant for promoters.

Law used (checked against the indexed RERA Act 2016):
- Section 11(1)(b)-(e): quarterly up-to-date details on the Authority's website: apartments or plots booked
  (number and type), garages booked, approvals taken and pending, and the status of the project.
- Section 4(2)(l)(D): seventy per cent of the amounts realised from allottees go into a separate account in
  a scheduled bank; withdrawals must be in proportion to the percentage of completion of the project and
  certified by an engineer, an architect and a chartered accountant in practice.
- Section 6: extension of registration, to apply for before it ends when the project will run late.

The assistant shows each ongoing project's report status, drafts the next report from the last one, checks
it before filing (errors stop filing; warnings are shown), and files it: a QprSubmission (handed to the
GUJRERA portal in the PoC) and the registry's progress row for that quarter marked filed. Promoters only,
and only for their own projects.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from gujrera.db.models import Approval, DueNotice, Project, ProjectProgress, QprSubmission
from gujrera.db.repository import AccessDenied, Repository
from gujrera.i18n import fmt_date, word
from gujrera.tools.interest import fmt_inr

BIG_JUMP = 25.0  # points in one quarter: possible, but keep the engineer's certificate ready
DEPOSIT_SHARE = 0.70  # Section 4(2)(l)(D)


def _act(sec: str) -> dict[str, Any]:
    return {"type": "legal_act", "id": f"RERA Act, 2016, Section {sec}", "is_mock": False}


def quarter_of(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def quarter_end(q: str) -> date:
    y, n = int(q[:4]), int(q[-1])
    return date(y, 3 * n, 30 if n in (2, 3) else 31)


def next_quarter(q: str) -> str:
    y, n = int(q[:4]), int(q[-1])
    return f"{y + 1}-Q1" if n == 4 else f"{y}-Q{n + 1}"


def due_date(q: str) -> date:
    """Due on the 15th day after the quarter ends, as in the registry's own records."""
    return quarter_end(q) + timedelta(days=15)


def _promoter(repo: Repository) -> int:
    if repo.p.role != "developer" or repo.p.promoter_id is None:
        raise AccessDenied("The quarterly report assistant is for promoters, for their own projects.")
    return repo.p.promoter_id


def _own_project(repo: Repository, project_id: int) -> Project:
    pid = _promoter(repo)
    p = repo.s.get(Project, project_id)
    if p is None or p.promoter_id != pid:
        repo._audit("qpr_denied", {"project_id": project_id})
        raise AccessDenied("You can only report on your own projects.")
    return p


def overview(repo: Repository, *, as_of: date | None = None) -> dict[str, Any]:
    pid = _promoter(repo)
    today = as_of or date.today()
    projects = repo.s.scalars(select(Project).where(Project.promoter_id == pid, Project.status == "ongoing")
                              .order_by(Project.name)).all()
    out = []
    for p in projects:
        rows = repo.s.scalars(select(ProjectProgress).where(ProjectProgress.project_id == p.id)
                              .order_by(ProjectProgress.quarter)).all()
        filed = [r for r in rows if r.filed_on]
        missing = [r for r in rows if not r.filed_on and r.due_on < today]
        last_q = rows[-1].quarter if rows else quarter_of(p.reg_date)
        upcoming = next_quarter(last_q)
        while quarter_end(upcoming) < today - timedelta(days=95):  # registry has no row for an ended quarter
            missing_q = upcoming
            upcoming = next_quarter(upcoming)
            missing.append(ProjectProgress(project_id=p.id, quarter=missing_q, percent_complete=0,
                                           due_on=due_date(missing_q), filed_on=None))
        to_file = [r.quarter for r in missing]
        current = quarter_of(today - timedelta(days=92)) if quarter_end(quarter_of(today - timedelta(days=92))) < today else None
        if current and current not in {r.quarter for r in rows} and current not in to_file:
            to_file.append(current)
        penalties = repo.s.scalars(select(DueNotice).where(DueNotice.project_id == p.id, DueNotice.kind == "late_qpr_penalty",
                                                           DueNotice.status == "pending")).all()
        late = sum(1 for r in filed[-8:] if r.filed_on > r.due_on)
        out.append({
            "project_id": p.id, "name": p.name, "name_gu": p.name_gu, "rera_no": p.rera_no, "district": p.district,
            "last_filed": None if not filed else {"quarter": filed[-1].quarter, "percent": filed[-1].percent_complete,
                                                   "filed_on": filed[-1].filed_on.isoformat()},
            "overdue": [{"quarter": r.quarter, "due_on": r.due_on.isoformat(), "days_late": (today - r.due_on).days}
                        for r in missing],
            "to_file": to_file,
            # the quarter now running: file it once it ends
            "next_due": {"quarter": quarter_of(today), "due_on": due_date(quarter_of(today)).isoformat()},
            "late_last_8": late,
            "penalties_pending": [{"description": d.description, "amount": d.amount} for d in penalties],
            "completion_target": (p.revised_completion or p.proposed_completion).isoformat(),
            "reg_valid_until": p.reg_valid_until.isoformat(),
        })
    repo._audit("qpr_overview", {"projects": len(out)})
    return {"projects": out, "as_of": today.isoformat()}


def draft(repo: Repository, project_id: int, quarter: str, *, as_of: date | None = None) -> dict[str, Any]:
    """Pre-filled form for one quarter: last figures, approvals on record, units in the registration."""
    p = _own_project(repo, project_id)
    today = as_of or date.today()
    if quarter_end(quarter) >= today:
        raise ValueError(f"{quarter} has not ended yet; it can be filed after {fmt_date(quarter_end(quarter), 'en')}.")
    rows = repo.s.scalars(select(ProjectProgress).where(ProjectProgress.project_id == p.id).order_by(ProjectProgress.quarter)).all()
    prev = next((r for r in reversed(rows) if r.filed_on and r.quarter < quarter), None)
    last_sub = repo.s.scalar(select(QprSubmission).where(QprSubmission.project_id == p.id).order_by(QprSubmission.id.desc()))
    last_payload = json.loads(last_sub.payload_json) if last_sub else {}
    approvals = repo.s.scalars(select(Approval).where(Approval.project_id == p.id)).all()
    return {
        "project": {"id": p.id, "name": p.name, "rera_no": p.rera_no, "units": p.units,
                    "completion_target": (p.revised_completion or p.proposed_completion).isoformat(),
                    "reg_valid_until": p.reg_valid_until.isoformat()},
        "quarter": quarter, "due_on": due_date(quarter).isoformat(), "late": today > due_date(quarter),
        "previous": None if prev is None else {"quarter": prev.quarter, "percent": prev.percent_complete},
        "prefill": {
            "percent_complete": prev.percent_complete if prev else None,
            "units_booked": last_payload.get("units_booked"), "garages_booked": last_payload.get("garages_booked"),
            "collected_total": last_payload.get("collected_total"), "deposited_total": last_payload.get("deposited_total"),
            "withdrawn_total": last_payload.get("withdrawn_total"), "project_cost": last_payload.get("project_cost"),
            "approvals": [{"id": a.id, "kind": word(a.kind, "en"), "authority": a.authority, "status": a.status} for a in approvals],
        },
        "law": {"details": "Section 11(1)(b)-(e)", "account": "Section 4(2)(l)(D)"},
    }


def check(repo: Repository, project_id: int, quarter: str, data: dict[str, Any], *, as_of: date | None = None) -> list[dict[str, Any]]:
    """Errors stop filing; warnings are shown and recorded with the filing."""
    p = _own_project(repo, project_id)
    today = as_of or date.today()
    issues: list[dict[str, Any]] = []

    def add(level: str, code: str, text: str, *cites: dict[str, Any]) -> None:
        issues.append({"level": level, "code": code, "text": text, "citations": list(cites)})

    pct = data.get("percent_complete")
    if pct is None or not 0 <= float(pct) <= 100:
        add("error", "percent", "Enter the percentage of completion (0 to 100).", _act("11"))
        return issues
    pct = float(pct)
    rows = repo.s.scalars(select(ProjectProgress).where(ProjectProgress.project_id == p.id).order_by(ProjectProgress.quarter)).all()
    prev = next((r for r in reversed(rows) if r.filed_on and r.quarter < quarter), None)
    later = next((r for r in rows if r.filed_on and r.quarter > quarter), None)
    if later and pct > later.percent_complete:  # a missed report filed late must fit between its neighbours
        add("error", "percent_above_later", f"Completion cannot be above the {later.percent_complete}% already reported for "
            f"{later.quarter}, a later quarter.", _act("11"))
    if prev and pct < prev.percent_complete:
        add("error", "percent_down", f"Completion cannot go down: {prev.percent_complete}% was reported for {prev.quarter}.", _act("11"))
    elif prev and pct - prev.percent_complete > BIG_JUMP:
        add("warning", "percent_jump", f"{pct - prev.percent_complete:.1f} points in one quarter is unusually large; keep the engineer's certificate ready.")

    units, garages = data.get("units_booked"), data.get("garages_booked")
    if units is None:
        add("error", "units_missing", "Enter the number of apartments or plots booked (Section 11(1)(b)).", _act("11"))
    elif int(units) < 0 or (p.units and int(units) > p.units):
        add("error", "units", f"Units booked must be between 0 and the {p.units} units in the registration.", _act("11"))
    if garages is not None and int(garages) < 0:
        add("error", "garages", "Garages booked cannot be negative.", _act("11"))

    collected, deposited = data.get("collected_total"), data.get("deposited_total")
    withdrawn, cost = data.get("withdrawn_total"), data.get("project_cost")
    if None in (collected, deposited, withdrawn, cost):
        add("error", "account_missing", "Enter the project-account figures: amount collected from buyers, deposited in the "
            "separate account, withdrawn from it, and the estimated project cost (Section 4(2)(l)(D)).", _act("4"))
    else:
        collected, deposited, withdrawn, cost = (float(x) for x in (collected, deposited, withdrawn, cost))
        if min(collected, deposited, withdrawn) < 0 or cost <= 0:
            add("error", "account_values", "Amounts cannot be negative and the project cost must be above zero.")
        else:
            if deposited + 0.5 < DEPOSIT_SHARE * collected:
                add("error", "deposit_short", f"Only {100 * deposited / collected:.0f}% of the amount collected is in the separate account; "
                    "at least 70% must be deposited (Section 4(2)(l)(D)).", _act("4"))
            if withdrawn > deposited + 0.5:
                add("error", "withdraw_over", "More has been withdrawn than was deposited in the separate account.", _act("4"))
            allowed = cost * pct / 100
            if withdrawn > allowed + 0.5:
                add("error", "withdraw_ahead", f"Withdrawals (₹{fmt_inr(withdrawn)}) are ahead of construction: at {pct:.1f}% complete, "
                    f"up to ₹{fmt_inr(allowed)} of the ₹{fmt_inr(cost)} project cost may be withdrawn. Withdrawals must be in proportion to "
                    "completion and certified by an engineer, an architect and a chartered accountant (Section 4(2)(l)(D)).", _act("4"))

    target = p.revised_completion or p.proposed_completion
    if later is not None:
        pass  # back-filling a missed quarter: later reports already show the current pace
    elif prev and pct > prev.percent_complete:
        quarters_between = max(1, (int(quarter[:4]) - int(prev.quarter[:4])) * 4 + int(quarter[-1]) - int(prev.quarter[-1]))
        pace = (pct - prev.percent_complete) / quarters_between
        finish = quarter_end(quarter) + timedelta(days=round((100 - pct) / pace * 91.3)) if pct < 100 else quarter_end(quarter)
        if finish > target:
            add("warning", "pace", f"At this pace ({pace:.1f} points a quarter) the project would finish around {fmt_date(finish, 'en')}, "
                f"after the registered completion date {fmt_date(target, 'en')}. Apply for an extension of registration "
                f"before {fmt_date(p.reg_valid_until, 'en')} if needed (Section 6).", _act("6"))
    elif prev and later is None and pct == prev.percent_complete and pct < 100:
        add("warning", "no_progress", "No progress since the last report: explain the reason in the project status.")
    pending = data.get("approvals_pending")
    if pending:
        add("warning", "approvals", f"{len(pending)} approval(s) still pending will be shown as pending (Section 11(1)(d)).", _act("11"))
    if today > due_date(quarter):
        add("warning", "late", f"This report was due on {fmt_date(due_date(quarter), 'en')}; filing late can attract a penalty.")
    return issues


def submit(repo: Repository, project_id: int, quarter: str, data: dict[str, Any], *, as_of: date | None = None) -> dict[str, Any]:
    p = _own_project(repo, project_id)
    today = as_of or date.today()
    if quarter_end(quarter) >= today:
        raise ValueError(f"{quarter} has not ended yet.")
    issues = check(repo, project_id, quarter, data, as_of=today)
    if any(i["level"] == "error" for i in issues):
        return {"filed": False, "issues": issues}
    row = repo.s.scalar(select(ProjectProgress).where(ProjectProgress.project_id == p.id, ProjectProgress.quarter == quarter))
    if row is not None and row.filed_on is not None:
        raise ValueError(f"The report for {quarter} was already filed on {row.filed_on.isoformat()}.")
    if row is None:
        row = ProjectProgress(project_id=p.id, quarter=quarter, percent_complete=float(data["percent_complete"]),
                              due_on=due_date(quarter), filed_on=today, is_mock=p.is_mock)
        repo.s.add(row)
    else:
        row.percent_complete, row.filed_on = float(data["percent_complete"]), today
    keep = {k: data.get(k) for k in ("percent_complete", "units_booked", "garages_booked", "collected_total",
                                     "deposited_total", "withdrawn_total", "project_cost", "approvals_pending", "status_note")}
    sub = QprSubmission(project_id=p.id, quarter=quarter, filed_on=today, filed_by_user_id=repo.p.user_id,
                        payload_json=json.dumps(keep, default=str),
                        warnings="\n".join(i["text"] for i in issues) or None, is_mock=p.is_mock)
    repo.s.add(sub)
    repo.s.flush()
    repo._audit("qpr_filed", {"project_id": p.id, "quarter": quarter, "warnings": len(issues)})
    return {"filed": True, "receipt": f"QPR-{p.id:04d}-{quarter}-{sub.id:05d}", "filed_on": today.isoformat(),
            "late": today > due_date(quarter), "issues": issues}
