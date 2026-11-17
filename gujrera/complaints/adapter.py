"""Hand-off to GUJRERA's complaint workflow.

The copilot never runs its own complaint process: it fills the form and passes
it to GUJRERA's existing workflow through ``ComplaintAdapter``. Until GUJRERA
provides an API, ``MockComplaintAdapter`` stands in for it and every record it
creates is marked as mock. A real adapter only needs ``submit`` and ``status``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gujrera.complaints.rules import form_for
from gujrera.config import get_gujrera_settings
from gujrera.db.models import Complaint, ComplaintEvent, MockPortalSubmission, Project


@dataclass
class ComplaintDraft:
    project_id: int | None = None
    description: str | None = None
    category: str | None = None
    relief: str | None = None
    name: str | None = None
    mobile: str | None = None
    email: str | None = None
    unit: str | None = None
    consent: bool = False
    skipped: set[str] = field(default_factory=set)  # optional fields the user chose to skip
    user_id: int | None = None  # logged-in citizen filing the complaint, if any

    @property
    def form(self) -> str:
        return form_for(self.relief)


@dataclass
class SubmissionResult:
    ref_no: str
    tracking_code: str
    form: str
    is_mock: bool


@dataclass
class ComplaintStatus:
    ref_no: str
    category: str
    form: str
    filed_on: date
    status: str
    project_name: str | None
    events: list[dict[str, Any]]
    is_mock: bool


class ComplaintAdapter(Protocol):
    def submit(self, draft: ComplaintDraft) -> SubmissionResult: ...

    def status(self, ref_no: str, tracking_code: str) -> ComplaintStatus | None: ...

    def has_tracking_code(self, ref_no: str) -> bool | None: ...


def _hmac(message: str) -> str:
    key = get_gujrera_settings().GUJRERA_HASH_SECRET.get_secret_value().encode()
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()


def _code_hash(ref_no: str, code: str) -> str:
    return _hmac(f"tracking:{ref_no}:{code}")


def complainant_hash(mobile: str) -> str:
    return _hmac(f"complainant:{mobile}")


class MockComplaintAdapter:
    """Writes to local tables that imitate GUJRERA's workflow. Prototype only."""

    is_mock = True

    def __init__(self, session: Session):
        self.s = session

    def submit(self, draft: ComplaintDraft) -> SubmissionResult:
        if not (draft.project_id and draft.description and draft.category and draft.relief
                and draft.name and draft.mobile and draft.consent):
            raise ValueError("Draft is incomplete or consent is missing")
        project = self.s.get(Project, draft.project_id)
        today = date.today()
        seq = (self.s.scalar(select(func.count()).select_from(MockPortalSubmission)) or 0) + 1
        ref_no = f"MOCK-CMP-{today.year}-{seq:05d}"
        code = f"{secrets.randbelow(10**6):06d}"

        complaint = Complaint(
            ref_no=ref_no, project_id=project.id, promoter_id=project.promoter_id,
            complainant_user_id=draft.user_id,
            complainant_hash=complainant_hash(draft.mobile), form=draft.form, category=draft.category,
            relief=draft.relief, summary=draft.description[:2000], district=project.district, filed_on=today,
            status="filed", channel="copilot", tracking_code_hash=_code_hash(ref_no, code), is_mock=True,
        )
        self.s.add(complaint)
        self.s.flush()
        self.s.add(ComplaintEvent(complaint_id=complaint.id, at=today, status="filed",
                                  note="Filed through GujRERA Saathi"))
        # What the real portal would receive, including contact details.
        self.s.add(MockPortalSubmission(
            ref_no=ref_no, submitted_at=datetime.now(timezone.utc).replace(tzinfo=None),
            payload_json=json.dumps({
                "form": draft.form, "project_rera_no": project.rera_no, "category": draft.category,
                "relief": draft.relief, "description": draft.description, "unit": draft.unit,
                "complainant": {"name": draft.name, "mobile": draft.mobile, "email": draft.email},
                "consent": True,
            }, ensure_ascii=False),
        ))
        self.s.commit()
        return SubmissionResult(ref_no, code, draft.form, True)

    def has_tracking_code(self, ref_no: str) -> bool | None:
        c = self.s.scalar(select(Complaint).where(Complaint.ref_no == ref_no))
        return None if c is None else bool(c.tracking_code_hash)

    def status(self, ref_no: str, tracking_code: str) -> ComplaintStatus | None:
        c = self.s.scalar(select(Complaint).where(Complaint.ref_no == ref_no))
        if c is None or not c.tracking_code_hash:
            return None
        if not hmac.compare_digest(c.tracking_code_hash, _code_hash(ref_no, tracking_code.strip())):
            return None
        project = self.s.get(Project, c.project_id) if c.project_id else None
        return ComplaintStatus(
            ref_no=c.ref_no, category=c.category, form=c.form, filed_on=c.filed_on, status=c.status,
            project_name=project.name if project else None,
            events=[{"at": e.at, "status": e.status, "note": e.note} for e in c.events], is_mock=c.is_mock,
        )
