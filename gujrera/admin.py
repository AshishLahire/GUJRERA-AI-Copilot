"""Administration for the POC: user accounts and roles, and the audit log viewer.

State-level officers are the administrators of the POC (the department will name its own admins). They:

* create test accounts for officers (with a district, or statewide) and citizens; a one-time password is
  shown once to the admin, who hands it over; it is never stored or logged in clear;
* change an officer's district, disable or enable an account, and reset a password. Disabling an account
  or resetting its password ends every session it has open;
* read the audit log: who did what and when, every refusal (outside the district, attempts to change data,
  unsafe queries, failed logins, pages a role may not open), data loads and exports, with filters and a
  CSV download.

Guards: an admin cannot disable or narrow their own account, and the last active statewide officer cannot be
disabled or given a district, so the system can always be administered. Promoter and agent accounts are
linked to registry records and are not created here.
"""

from __future__ import annotations

import csv
import io
import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select

from gujrera.auth import hash_password
from gujrera.db.models import Agent, AuditLog, Project, Promoter, User
from gujrera.db.repository import AccessDenied, Repository

CREATABLE_ROLES = ("officer", "citizen")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,39}$")
ROLE_LABELS = {"officer": "GUJRERA officer", "citizen": "Home buyer", "developer": "Promoter", "agent": "Agent"}

# What each audit action means, and its category, for the viewer.
ACTIONS: dict[str, tuple[str, str]] = {
    "login": ("login", "Logged in"),
    "login_failed": ("refusal", "Wrong username or password"),
    "login_locked": ("refusal", "Login locked after repeated failures"),
    "login_disabled": ("refusal", "Login to a disabled account"),
    "access_denied": ("refusal", "Opened something this role may not use"),
    "analytics_out_of_scope": ("refusal", "Asked about another district"),
    "analytics_write_refused": ("refusal", "Asked to change data (reports are read-only)"),
    "analytics_refused": ("refusal", "Unsafe query blocked"),
    "analytics_failed": ("report", "Report query failed"),
    "complaint_status_denied": ("refusal", "Complaint status change refused"),
    "dues_denied": ("refusal", "Dues of another promoter refused"),
    "qpr_denied": ("refusal", "Quarterly report of another promoter refused"),
    "analytics_query": ("report", "Ran a report"),
    "analytics_export": ("report", "Exported a report"),
    "report_saved": ("report", "Saved a report"),
    "data_upload": ("data", "Uploaded a data file"),
    "data_check": ("data", "Checked a data file"),
    "data_load": ("data", "Loaded a data file"),
    "user_created": ("admin", "Created an account"),
    "user_updated": ("admin", "Changed an account"),
    "password_reset": ("admin", "Reset a password"),
    "officer_dashboard": ("work", "Opened the work queue"),
    "officer_review": ("work", "Marked a work-queue item"),
    "complaint_triage": ("work", "Opened the complaint desk"),
    "complaint_brief": ("work", "Opened a hearing brief"),
    "complaint_status_changed": ("work", "Changed a complaint's status"),
    "enforcement_list": ("work", "Opened ad enforcement"),
    "enforcement_case_viewed": ("work", "Opened an ad case"),
    "enforcement_case_updated": ("work", "Updated an ad case"),
    "order_compliance_updated": ("work", "Updated an order's compliance"),
    "risk_watchlist": ("work", "Opened the risk watch"),
}
CATEGORIES = {
    "refusal": "Refusals", "report": "Reports", "data": "Data loads", "admin": "Account changes",
    "login": "Logins", "work": "Officer work", "public": "Citizen and public use",
}


def _category(action: str) -> str:
    return ACTIONS.get(action, ("public", ""))[0]


def _label(action: str) -> str:
    return ACTIONS.get(action, ("", action.replace("_", " ").capitalize()))[1] or action.replace("_", " ").capitalize()


def require_admin(repo: Repository) -> None:
    if repo.p.role != "officer" or repo.p.district_scope:
        raise AccessDenied("Administration is for state-level GUJRERA officers.")


def _me(repo: Repository) -> User | None:
    return repo.s.get(User, repo.p.user_id) if repo.p.user_id else None


def _districts(repo: Repository) -> list[str]:
    from gujrera.analytics.reports import DISTRICT_WORDS

    known = set(DISTRICT_WORDS.values()) | {d for (d,) in repo.s.execute(select(Project.district).distinct()) if d}
    return sorted(known)


def _user_dict(repo: Repository, u: User) -> dict[str, Any]:
    org = None
    if u.promoter_id:
        p = repo.s.get(Promoter, u.promoter_id)
        org = p.name if p else None
    elif u.agent_id:
        a = repo.s.get(Agent, u.agent_id)
        org = a.reg_no if a else None
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role,
            "role_label": ROLE_LABELS.get(u.role, u.role), "district_scope": u.district_scope, "organisation": org,
            "is_active": u.is_active is not False, "is_demo": bool(u.is_mock),
            "created_at": u.created_at.isoformat(timespec="minutes") if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat(timespec="minutes") if u.last_login_at else None}


# ------------------------------------------------------------------ users
def list_users(repo: Repository, role: str | None = None, q: str | None = None) -> dict[str, Any]:
    require_admin(repo)
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.username).like(like), func.lower(User.display_name).like(like)))
    users = repo.s.scalars(stmt.order_by(User.role, User.district_scope, User.username)).all()
    counts = dict(repo.s.execute(select(User.role, func.count()).group_by(User.role)).all())
    return {"users": [_user_dict(repo, u) for u in users], "counts": counts, "districts": _districts(repo),
            "creatable_roles": list(CREATABLE_ROLES)}


def _temp_password() -> str:
    return secrets.token_urlsafe(9)  # 12 characters, shown once


def create_user(repo: Repository, username: str, display_name: str, role: str,
                district_scope: str | None) -> dict[str, Any]:
    require_admin(repo)
    username = (username or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ValueError("Username: 3–40 characters, lower-case letters, digits, '.', '_' or '-'.")
    if role not in CREATABLE_ROLES:
        raise ValueError("Create officer or citizen accounts here; promoter and agent accounts are linked to "
                         "registry records.")
    if repo.s.scalar(select(User).where(User.username == username)):
        raise ValueError(f"The username {username} is taken.")
    scope = (district_scope or "").strip() or None
    if role != "officer":
        scope = None
    elif scope and scope not in _districts(repo):
        raise ValueError(f"Unknown district {scope!r}.")
    password = _temp_password()
    user = User(username=username, display_name=(display_name or "").strip()[:200] or username, role=role,
                district_scope=scope, password_hash=hash_password(password), is_mock=False, is_active=True,
                token_version=0, created_at=datetime.now(), preferred_lang="gu")
    repo.s.add(user)
    repo.s.flush()
    repo._audit("user_created", {"username": username, "role": role, "district_scope": scope or "statewide"})
    return {"user": _user_dict(repo, user), "temporary_password": password}


def _statewide_admins(repo: Repository) -> int:
    return repo.s.scalar(select(func.count()).select_from(User).where(
        User.role == "officer", User.district_scope.is_(None), User.is_active.is_not(False))) or 0


def update_user(repo: Repository, user_id: int, *, display_name: str | None = None,
                district_scope: str | None = None, set_scope: bool = False,
                is_active: bool | None = None) -> dict[str, Any]:
    require_admin(repo)
    user = repo.s.get(User, user_id)
    if user is None:
        raise ValueError("No such account.")
    me = _me(repo)
    changes: dict[str, Any] = {}
    if display_name is not None and display_name.strip() and display_name.strip() != user.display_name:
        user.display_name = display_name.strip()[:200]
        changes["display_name"] = user.display_name
    if set_scope:
        if user.role != "officer":
            raise ValueError("Only officer accounts have a district.")
        scope = (district_scope or "").strip() or None
        if scope and scope not in _districts(repo):
            raise ValueError(f"Unknown district {scope!r}.")
        if scope and user.district_scope is None:
            if me and me.id == user.id:
                raise ValueError("You cannot give your own account a district: ask another state admin.")
            if _statewide_admins(repo) <= 1:
                raise ValueError("This is the last statewide officer; it cannot be given a district.")
        if scope != user.district_scope:
            user.district_scope = scope
            user.token_version = (user.token_version or 0) + 1  # the new scope applies from the next login
            changes["district_scope"] = scope or "statewide"
    if is_active is not None and is_active != (user.is_active is not False):
        if not is_active:
            if me and me.id == user.id:
                raise ValueError("You cannot disable your own account.")
            if user.role == "officer" and user.district_scope is None and _statewide_admins(repo) <= 1:
                raise ValueError("This is the last active statewide officer; it cannot be disabled.")
            user.token_version = (user.token_version or 0) + 1  # end its sessions now
        user.is_active = is_active
        changes["is_active"] = is_active
    repo.s.flush()
    if changes:
        repo._audit("user_updated", {"username": user.username, **changes})
    return {"user": _user_dict(repo, user)}


def reset_password(repo: Repository, user_id: int) -> dict[str, Any]:
    require_admin(repo)
    user = repo.s.get(User, user_id)
    if user is None:
        raise ValueError("No such account.")
    password = _temp_password()
    user.password_hash = hash_password(password)
    user.token_version = (user.token_version or 0) + 1
    repo.s.flush()
    repo._audit("password_reset", {"username": user.username})
    return {"user": _user_dict(repo, user), "temporary_password": password}


# ------------------------------------------------------------------ audit log
def _utc_start(d: date) -> datetime:
    """Local midnight of a day, as the naive UTC time the audit log stores."""
    local = datetime.combine(d, datetime.min.time()).astimezone()
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _local(at: datetime) -> str:
    return at.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def _filtered(repo: Repository, *, username: str | None, role: str | None, category: str | None,
              action: str | None, since: date | None, until: date | None, q: str | None):
    stmt = select(AuditLog, User.username).outerjoin(User, User.id == AuditLog.user_id)
    if username:
        stmt = stmt.where(or_(User.username == username.strip().lower(),
                              AuditLog.detail.like(f'%"username": "{username.strip().lower()}"%')))
    if role:
        stmt = stmt.where(AuditLog.role == role)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if category:
        names = [a for a, (c, _l) in ACTIONS.items() if c == category]
        stmt = stmt.where(AuditLog.action.in_(names)) if category != "public" else stmt.where(
            AuditLog.action.not_in(list(ACTIONS)))
    if since:
        stmt = stmt.where(AuditLog.at >= _utc_start(since))
    if until:
        stmt = stmt.where(AuditLog.at < _utc_start(until + timedelta(days=1)))
    if q:
        stmt = stmt.where(AuditLog.detail.like(f"%{q.strip()[:100]}%"))
    return stmt


def _entry(row: AuditLog, username: str | None) -> dict[str, Any]:
    try:
        detail = json.loads(row.detail) if row.detail else {}
    except json.JSONDecodeError:
        detail = {"text": row.detail}
    who = username or (detail.get("username") if row.action.startswith("login") else None)
    signed_in = row.user_id is not None
    return {"id": row.id, "at": _local(row.at), "user": who or (None if signed_in else "visitor"),
            "role": row.role if signed_in else "not logged in", "action": row.action, "label": _label(row.action),
            "category": _category(row.action), "detail": detail}


def audit_log(repo: Repository, *, username: str | None = None, role: str | None = None, category: str | None = None,
              action: str | None = None, since: date | None = None, until: date | None = None, q: str | None = None,
              limit: int = 100, offset: int = 0) -> dict[str, Any]:
    require_admin(repo)
    since = since or (date.today() - timedelta(days=7))
    stmt = _filtered(repo, username=username, role=role, category=category, action=action, since=since,
                     until=until, q=q)
    total = repo.s.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = repo.s.execute(stmt.order_by(AuditLog.at.desc(), AuditLog.id.desc())
                          .limit(max(1, min(limit, 500))).offset(max(0, offset))).all()
    # summary of the same window, all categories
    window = _filtered(repo, username=username, role=role, category=None, action=None, since=since, until=until, q=q)
    sub = window.subquery()
    by_action = dict(repo.s.execute(select(sub.c.action, func.count()).group_by(sub.c.action)).all())
    by_category: dict[str, int] = {}
    for a, n in by_action.items():
        by_category[_category(a)] = by_category.get(_category(a), 0) + n
    users = repo.s.scalar(select(func.count(func.distinct(sub.c.user_id))))
    return {
        "since": since.isoformat(), "until": until.isoformat() if until else None, "total": total,
        "entries": [_entry(r, u) for r, u in rows],
        "summary": {"by_category": by_category, "distinct_users": users,
                    "failed_logins": by_action.get("login_failed", 0) + by_action.get("login_locked", 0)
                    + by_action.get("login_disabled", 0),
                    "out_of_scope": by_action.get("analytics_out_of_scope", 0),
                    "write_attempts": by_action.get("analytics_write_refused", 0),
                    "blocked_queries": by_action.get("analytics_refused", 0),
                    "access_denied": by_action.get("access_denied", 0)},
        "categories": CATEGORIES,
        "actions": sorted({*by_action, *ACTIONS}),
    }


def audit_csv(repo: Repository, **filters: Any) -> str:
    require_admin(repo)
    data = audit_log(repo, **filters, limit=500)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["time", "user", "role", "category", "action", "what happened", "detail"])
    for e in data["entries"]:
        w.writerow([e["at"], e["user"] or "", e["role"], e["category"], e["action"], e["label"],
                    json.dumps(e["detail"], ensure_ascii=False)])
    repo._audit("audit_exported", {"rows": len(data["entries"])})
    return out.getvalue()
