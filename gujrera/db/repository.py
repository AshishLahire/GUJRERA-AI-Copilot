"""Role-scoped data access. ALL reads by copilot tools go through here.

Access rules are enforced in this module, never by prompts:

| Data                                   | citizen        | developer          | agent            | officer           |
|----------------------------------------|----------------|--------------------|------------------|-------------------|
| projects, promoters, agents, approvals, | yes            | yes                | yes              | yes               |
| progress reports, orders, scorecards   |                |                    |                  |                   |
| complaints                             | own only       | against own        | against self     | own district      |
|                                        |                | projects           |                  | (or statewide)    |
| dues and notices                       | no             | own only           | no               | own district      |

Asking for a specific record outside your scope raises ``AccessDenied``;
list queries are silently narrowed to your scope. Complainant identity
(user id, hash) is only ever returned to that complainant.

Every record returned carries ``source`` (record type, id, is_mock) so answers
can cite it and the UI can label mock data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from rapidfuzz import fuzz, process
from sqlalchemy import Select, select, text
from sqlalchemy.orm import Session

from gujrera.db.models import (
    Agent,
    Approval,
    AuditLog,
    Complaint,
    DueNotice,
    OPEN_COMPLAINT_STATUSES,
    Order,
    Project,
    ProjectProgress,
    Promoter,
    User,
)
from gujrera.trust.rera_number import parse_rera_number


class AccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    role: str
    promoter_id: int | None = None
    agent_id: int | None = None
    district_scope: str | None = None  # officers only; None = statewide

    @classmethod
    def from_user(cls, user: User) -> Principal:
        return cls(user.id, user.role, user.promoter_id, user.agent_id, user.district_scope)

    @classmethod
    def anonymous(cls) -> Principal:
        return cls(None, "citizen")


def _row(obj: Any, source_type: str, source_id: str, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    data = {
        c.key: getattr(obj, c.key)
        for c in obj.__table__.columns
        if c.key not in exclude
    }
    data["source"] = {"type": source_type, "id": source_id, "is_mock": bool(getattr(obj, "is_mock", True))}
    return data


class Repository:
    def __init__(self, session: Session, principal: Principal,
                 audit_sink: Callable[[AuditLog], None] | None = None):
        """``audit_sink`` writes each audit row somewhere other than this session. The API uses it to
        commit audit rows at once, so a request that then waits on the LLM does not hold the
        database write lock. Without it, rows are added to this session (committed with it)."""
        self.s = session
        self.p = principal
        self._audit_sink = audit_sink

    # ------------------------------------------------------------------ audit
    def _audit(self, action: str, detail: dict[str, Any]) -> None:
        row = AuditLog(at=datetime.now(timezone.utc).replace(tzinfo=None), user_id=self.p.user_id,
                       role=self.p.role, action=action, detail=json.dumps(detail, default=str))
        if self._audit_sink is not None:
            self._audit_sink(row)
            return
        self.s.add(row)
        self.s.flush()

    # ---------------------------------------------------------- public data
    def get_project(self, rera_no: str) -> dict[str, Any] | None:
        """Exact lookup by registration number (normalised; OCR noise tolerated)."""
        parsed = parse_rera_number(rera_no)
        key = parsed.normalised if parsed else rera_no.strip().upper()
        project = self.s.scalar(select(Project).where(Project.rera_no == key))
        if project is None and parsed and parsed.code:
            # Same unique code but other segments differ (e.g. OCR mangled the taluka).
            project = self.s.scalar(select(Project).where(Project.rera_no.like(f"%/{parsed.code}/%")))
        return self._project_dict(project) if project else None

    def get_project_by_id(self, project_id: int) -> dict[str, Any] | None:
        project = self.s.get(Project, project_id)
        return self._project_dict(project) if project else None

    def _project_dict(self, project: Project) -> dict[str, Any]:
        d = _row(project, "project", project.rera_no)
        d["promoter_name"] = project.promoter.name
        delay = self.s.execute(
            text("SELECT delay_days, is_delayed FROM v_project_delays WHERE project_id = :id"),
            {"id": project.id},
        ).one()
        d["delay_days"], d["is_delayed"] = int(delay.delay_days), bool(delay.is_delayed)
        return d

    def search_projects(self, query: str, district: str | None = None, limit: int = 5,
                        min_score: float = 70) -> list[dict[str, Any]]:
        """Fuzzy search on English and Gujarati project names."""
        stmt: Select = select(Project)
        if district:
            stmt = stmt.where(Project.district == district)
        candidates = self.s.scalars(stmt).all()
        return [self._project_dict(p) | {"match_score": score}
                for p, score in self._fuzzy(query, candidates, lambda p: (p.name, p.name_gu), limit, min_score)]

    def get_promoter(self, promoter_id: int) -> dict[str, Any] | None:
        promoter = self.s.get(Promoter, promoter_id)
        return _row(promoter, "promoter", str(promoter.id)) if promoter else None

    def search_promoters(self, query: str, limit: int = 5, min_score: float = 70) -> list[dict[str, Any]]:
        candidates = self.s.scalars(select(Promoter)).all()
        return [_row(p, "promoter", str(p.id)) | {"match_score": score}
                for p, score in self._fuzzy(query, candidates, lambda p: (p.name, p.name_gu), limit, min_score)]

    def promoter_scorecard(self, promoter_id: int) -> dict[str, Any] | None:
        row = self.s.execute(text("SELECT * FROM v_promoter_scorecard WHERE promoter_id = :id"),
                             {"id": promoter_id}).mappings().first()
        if row is None:
            return None
        d = dict(row)
        d["source"] = {"type": "promoter_scorecard", "id": str(promoter_id), "is_mock": bool(d["is_mock"])}
        return d

    def promoter_projects(self, promoter_id: int) -> list[dict[str, Any]]:
        projects = self.s.scalars(select(Project).where(Project.promoter_id == promoter_id)
                                  .order_by(Project.reg_date)).all()
        return [self._project_dict(p) for p in projects]

    def project_approvals(self, project_id: int) -> list[dict[str, Any]]:
        rows = self.s.scalars(select(Approval).where(Approval.project_id == project_id)).all()
        return [_row(a, "approval", str(a.id)) for a in rows]

    def project_progress(self, project_id: int) -> list[dict[str, Any]]:
        rows = self.s.scalars(select(ProjectProgress).where(ProjectProgress.project_id == project_id)
                              .order_by(ProjectProgress.due_on)).all()
        return [_row(r, "progress_report", f"{project_id}:{r.quarter}") for r in rows]

    def list_orders(self, *, promoter_id: int | None = None, project_id: int | None = None,
                    limit: int = 50) -> list[dict[str, Any]]:
        stmt = select(Order).order_by(Order.issued_on.desc()).limit(limit)
        if promoter_id is not None:
            stmt = stmt.where(Order.promoter_id == promoter_id)
        if project_id is not None:
            stmt = stmt.where(Order.project_id == project_id)
        return [_row(o, "order", o.order_no) for o in self.s.scalars(stmt).all()]

    def get_agent(self, reg_no: str) -> dict[str, Any] | None:
        parsed = parse_rera_number(reg_no)
        key = parsed.normalised if parsed else reg_no.strip().upper()
        agent = self.s.scalar(select(Agent).where(Agent.reg_no == key))
        if agent is None and parsed and parsed.code:
            agent = self.s.scalar(select(Agent).where(Agent.reg_no.like(f"%/{parsed.code}/%")))
        return _row(agent, "agent", agent.reg_no) if agent else None

    def search_agents(self, query: str, limit: int = 5, min_score: float = 70) -> list[dict[str, Any]]:
        candidates = self.s.scalars(select(Agent)).all()
        return [_row(a, "agent", a.reg_no) | {"match_score": score}
                for a, score in self._fuzzy(query, candidates, lambda a: (a.name, a.name_gu), limit, min_score)]

    def complaint_counts(self, *, promoter_id: int | None = None,
                         project_id: int | None = None) -> dict[str, Any]:
        """Public aggregate counts (no complaint records or complainant data)."""
        stmt = select(Complaint.status, Complaint.category, Complaint.is_mock)
        if promoter_id is not None:
            stmt = stmt.where(Complaint.promoter_id == promoter_id)
        if project_id is not None:
            stmt = stmt.where(Complaint.project_id == project_id)
        rows = self.s.execute(stmt).all()
        by_category: dict[str, int] = {}
        for _, cat, _mock in rows:
            by_category[cat] = by_category.get(cat, 0) + 1
        return {
            "total": len(rows),
            "open": sum(1 for st, _, _m in rows if st in OPEN_COMPLAINT_STATUSES),
            "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
            "source": {"type": "complaint_stats",
                       "id": f"project:{project_id}" if project_id is not None else f"promoter:{promoter_id}",
                       "is_mock": any(m for _, _, m in rows)},
        }

    # -------------------------------------------------------- scoped: complaints
    def _complaint_scope(self, stmt: Select) -> Select:
        p = self.p
        if p.role == "officer":
            return stmt.where(Complaint.district == p.district_scope) if p.district_scope else stmt
        if p.role == "developer":
            return stmt.where(Complaint.promoter_id == p.promoter_id)
        if p.role == "agent":
            return stmt.where(Complaint.agent_id == p.agent_id)
        if p.role == "citizen" and p.user_id is not None:
            return stmt.where(Complaint.complainant_user_id == p.user_id)
        return stmt.where(False)  # anonymous citizen: nothing

    def _complaint_dict(self, c: Complaint) -> dict[str, Any]:
        own = self.p.role == "citizen" and c.complainant_user_id == self.p.user_id and self.p.user_id is not None
        exclude = ("complainant_hash",) if own else ("complainant_hash", "complainant_user_id")
        d = _row(c, "complaint", c.ref_no, exclude)
        d["events"] = [{"at": e.at, "status": e.status, "note": e.note} for e in c.events]
        return d

    def complaint_status(self, ref_no: str) -> dict[str, Any] | None:
        """Track one complaint. Raises AccessDenied if it exists but is outside scope."""
        c = self.s.scalar(select(Complaint).where(Complaint.ref_no == ref_no.strip().upper()))
        if c is None:
            return None
        if self.s.scalar(self._complaint_scope(select(Complaint.id).where(Complaint.id == c.id))) is None:
            self._audit("complaint_status_denied", {"ref_no": ref_no})
            raise AccessDenied("This complaint is not visible to you.")
        self._audit("complaint_status", {"ref_no": ref_no})
        return self._complaint_dict(c)

    def list_complaints(self, *, promoter_id: int | None = None, project_id: int | None = None,
                        open_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        stmt = self._complaint_scope(select(Complaint)).order_by(Complaint.filed_on.desc()).limit(limit)
        if promoter_id is not None:
            stmt = stmt.where(Complaint.promoter_id == promoter_id)
        if project_id is not None:
            stmt = stmt.where(Complaint.project_id == project_id)
        if open_only:
            stmt = stmt.where(Complaint.status.in_(OPEN_COMPLAINT_STATUSES))
        rows = self.s.scalars(stmt).all()
        self._audit("list_complaints", {"promoter_id": promoter_id, "project_id": project_id, "n": len(rows)})
        return [self._complaint_dict(c) for c in rows]

    # ----------------------------------------------------------- scoped: dues
    def dues_notices(self, promoter_id: int | None = None, *, pending_only: bool = False) -> list[dict[str, Any]]:
        p = self.p
        if p.role == "developer":
            if promoter_id is not None and promoter_id != p.promoter_id:
                self._audit("dues_denied", {"promoter_id": promoter_id})
                raise AccessDenied("You can only view your own dues and notices.")
            promoter_id = p.promoter_id
        elif p.role != "officer":
            raise AccessDenied("Dues and notices are visible only to the promoter and GUJRERA officers.")

        stmt = select(DueNotice).order_by(DueNotice.issued_on.desc())
        if promoter_id is not None:
            stmt = stmt.where(DueNotice.promoter_id == promoter_id)
        if p.role == "officer" and p.district_scope:
            stmt = stmt.join(Promoter, Promoter.id == DueNotice.promoter_id).where(
                Promoter.district == p.district_scope)
        if pending_only:
            stmt = stmt.where(DueNotice.status == "pending")
        rows = self.s.scalars(stmt).all()
        self._audit("dues_notices", {"promoter_id": promoter_id, "n": len(rows)})
        return [_row(r, "due_notice", str(r.id)) for r in rows]

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _fuzzy(query: str, candidates: list[Any], names, limit: int, min_score: float):
        choices: dict[int, str] = {}
        owners: dict[int, Any] = {}
        for obj in candidates:
            for name in names(obj):
                if name:
                    key = len(choices)
                    choices[key] = name
                    owners[key] = obj
        best: dict[int, tuple[Any, float]] = {}
        for _, score, key in process.extract(query, choices, scorer=fuzz.WRatio, limit=limit * 3):
            obj = owners[key]
            if score >= min_score and (obj.id not in best or best[obj.id][1] < score):
                best[obj.id] = (obj, round(float(score), 1))
        return sorted(best.values(), key=lambda t: -t[1])[:limit]

