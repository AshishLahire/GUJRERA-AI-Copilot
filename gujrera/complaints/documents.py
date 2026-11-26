"""A complaint's documents and hearing, as the buyer and the officer see them.

* **Documents.** The buyer adds evidence (the agreement, payment receipts, letters from the builder, photos)
  after filing; an officer can add papers such as a hearing notice. PDF, JPG and PNG only, checked by their
  first bytes, up to 10 MB each and 10 per complaint. Files are kept in the uploads folder beside the database.
* **Hearing.** The officer fixes the date and the place on the complaint desk; the buyer sees it on the
  "My complaint" page and in the chat ("Next hearing: 5 December 2026, in 9 days, at ...").

Who may see or add: an officer (within their district), the logged-in buyer who filed it, or anyone with the
reference number and the 6-digit tracking code given at filing. Wrong codes are limited per reference.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
import uuid
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from gujrera.complaints.adapter import _code_hash
from gujrera.complaints.strings import label, s
from gujrera.db.models import Complaint, ComplaintDocument, Project
from gujrera.db.repository import AccessDenied, Repository
from gujrera.i18n import fmt_date

MAX_BYTES = 10 * 1024 * 1024
MAX_DOCS = 10
TYPES = {".pdf": ("application/pdf", (b"%PDF-",)),
         ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
         ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
         ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",))}
OPEN = ("filed", "under_scrutiny", "hearing_scheduled", "order_reserved")
MAX_WRONG_CODES, WRONG_CODE_WINDOW = 5, 3600  # per reference number, per hour

_WRONG: dict[str, list[float]] = defaultdict(list)
_WRONG_LOCK = threading.Lock()


def _folder(repo: Repository, complaint_id: int) -> Path:
    from gujrera.onboarding import uploads_dir

    folder = uploads_dir(repo.s) / "complaints" / str(complaint_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _username(repo: Repository) -> str | None:
    from gujrera.db.models import User

    return repo.s.scalar(select(User.username).where(User.id == repo.p.user_id)) if repo.p.user_id else None


# ------------------------------------------------------------------ access
def _by_ref(repo: Repository, ref: str) -> Complaint:
    c = repo.s.scalar(select(Complaint).where(Complaint.ref_no == (ref or "").strip().upper()))
    if c is None:
        raise LookupError("No complaint has that reference number.")
    return c


def _check_code(ref: str, c: Complaint, code: str | None) -> bool:
    now = time.time()
    with _WRONG_LOCK:
        recent = [t for t in _WRONG[ref] if now - t < WRONG_CODE_WINDOW]
        _WRONG[ref] = recent
        if len(recent) >= MAX_WRONG_CODES:
            raise AccessDenied("Too many wrong tracking codes for this complaint. Try again in an hour.")
    if code and c.tracking_code_hash and hmac.compare_digest(c.tracking_code_hash, _code_hash(c.ref_no, code.strip())):
        return True
    if code:
        with _WRONG_LOCK:
            _WRONG[ref].append(now)
    return False


def complaint_for(repo: Repository, ref: str, code: str | None = None) -> Complaint:
    """The complaint, if this person may see it; otherwise AccessDenied (or LookupError)."""
    c = _by_ref(repo, ref)
    p = repo.p
    if p.role == "officer":
        if p.district_scope and c.district != p.district_scope:
            repo._audit("complaint_access_denied", {"ref_no": c.ref_no})
            raise AccessDenied("This complaint is outside your district.")
        return c
    if p.role == "citizen" and p.user_id is not None and c.complainant_user_id == p.user_id:
        return c
    if _check_code(c.ref_no, c, code):
        return c
    repo._audit("complaint_access_denied", {"ref_no": c.ref_no, "with_code": bool(code)})
    if code:
        raise AccessDenied("That tracking code does not match this complaint.")
    raise AccessDenied("Enter the 6-digit tracking code you were given when you filed.")


def officer_complaint(repo: Repository, complaint_id: int) -> Complaint:
    if repo.p.role != "officer":
        raise AccessDenied("This is for GUJRERA officers.")
    c = repo.s.get(Complaint, complaint_id)
    if c is None or (repo.p.district_scope and c.district != repo.p.district_scope):
        raise LookupError("Complaint not found.")
    return c


# ------------------------------------------------------------------ hearing
def hearing(c: Complaint, lang: str, today: date | None = None) -> dict[str, Any] | None:
    """The hearing as data and as one sentence; None when no date was fixed."""
    if not c.hearing_on:
        return None
    today = today or date.today()
    days = (c.hearing_on - today).days
    upcoming = days >= 0 and c.status == "hearing_scheduled"
    place = c.hearing_place or ""
    if upcoming:
        key = "hearing_today" if days == 0 else "hearing_next"
        text = s(key, lang, date=fmt_date(c.hearing_on, lang), days=days,
                 place=(s("hearing_at", lang, place=place) if place else ""))
    else:
        text = s("hearing_last", lang, date=fmt_date(c.hearing_on, lang))
    return {"on": c.hearing_on.isoformat(), "place": c.hearing_place, "days_to": days, "upcoming": upcoming,
            "text": text}


# ------------------------------------------------------------------ documents
def _doc_dict(d: ComplaintDocument) -> dict[str, Any]:
    return {"id": d.id, "filename": d.filename, "content_type": d.content_type, "size": d.size, "note": d.note,
            "added_by": d.added_by, "added_at": d.added_at.isoformat(timespec="minutes")}


def documents(repo: Repository, c: Complaint) -> list[dict[str, Any]]:
    rows = repo.s.scalars(select(ComplaintDocument).where(ComplaintDocument.complaint_id == c.id)
                          .order_by(ComplaintDocument.id)).all()
    return [_doc_dict(d) for d in rows]


def _safe_name(filename: str, ext: str) -> str:
    stem = Path(filename or "document").stem
    stem = "".join(ch if (ch.isalnum() or ch in " ._-()") else "_" for ch in stem).strip(" ._") or "document"
    return f"{stem[:100]}{ext}"


def _add(repo: Repository, c: Complaint, filename: str, data: bytes, note: str | None, by: str) -> dict[str, Any]:
    ext = Path(filename or "").suffix.lower()
    if ext not in TYPES:
        raise ValueError("Add a PDF, JPG or PNG file.")
    content_type, magic = TYPES[ext]
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ValueError("The file is larger than 10 MB. Add a smaller copy, or split it into parts.")
    if not any(data.startswith(m) for m in magic):
        raise ValueError(f"This does not look like a {ext.lstrip('.').upper()} file.")
    if c.status not in OPEN and by != "officer":
        raise ValueError("This complaint is closed; documents can no longer be added.")
    n = repo.s.scalar(select(func.count()).select_from(ComplaintDocument).where(ComplaintDocument.complaint_id == c.id))
    if n >= MAX_DOCS:
        raise ValueError(f"A complaint can have at most {MAX_DOCS} documents.")
    digest = hashlib.sha256(data).hexdigest()
    same = repo.s.scalar(select(ComplaintDocument).where(ComplaintDocument.complaint_id == c.id,
                                                         ComplaintDocument.sha256 == digest))
    if same is not None:
        raise ValueError(f"This file is already attached, as “{same.filename}”.")
    stored = f"{uuid.uuid4().hex}{ext}"
    (_folder(repo, c.id) / stored).write_bytes(data)
    doc = ComplaintDocument(complaint_id=c.id, filename=_safe_name(filename, ext), content_type=content_type,
                            size=len(data), sha256=digest, stored_as=stored,
                            note=(note or "").strip()[:200] or None, added_by=by, added_by_user=_username(repo),
                            added_at=datetime.now())
    repo.s.add(doc)
    repo.s.flush()
    repo._audit("complaint_document_added", {"ref_no": c.ref_no, "document": doc.id, "by": by, "size": len(data)})
    return _doc_dict(doc)


def add_document(repo: Repository, ref: str, code: str | None, filename: str, data: bytes,
                 note: str | None = None) -> dict[str, Any]:
    c = complaint_for(repo, ref, code)
    return _add(repo, c, filename, data, note, "officer" if repo.p.role == "officer" else "complainant")


def officer_add_document(repo: Repository, complaint_id: int, filename: str, data: bytes,
                         note: str | None = None) -> dict[str, Any]:
    return _add(repo, officer_complaint(repo, complaint_id), filename, data, note, "officer")


def document_file(repo: Repository, c: Complaint, doc_id: int) -> tuple[Path, str, str]:
    d = repo.s.get(ComplaintDocument, doc_id)
    if d is None or d.complaint_id != c.id:
        raise LookupError("No such document on this complaint.")
    path = _folder(repo, c.id) / d.stored_as
    if not path.exists():
        raise LookupError("The file is missing from the uploads folder.")
    repo._audit("complaint_document_opened", {"ref_no": c.ref_no, "document": d.id})
    return path, d.filename, d.content_type


# ------------------------------------------------------------------ the buyer's view
def view(repo: Repository, c: Complaint, lang: str, today: date | None = None) -> dict[str, Any]:
    project = repo.s.get(Project, c.project_id) if c.project_id else None
    docs = documents(repo, c)
    return {
        "ref_no": c.ref_no, "form": c.form, "category": c.category, "category_label": label(c.category, lang),
        "relief": c.relief, "filed_on": c.filed_on.isoformat(), "filed_text": fmt_date(c.filed_on, lang),
        "status": c.status, "status_label": label(c.status, lang),
        "project": {"name": project.name, "rera_no": project.rera_no} if project else None,
        "events": [{"at": e.at.isoformat(), "status": e.status, "status_label": label(e.status, lang), "note": e.note}
                   for e in sorted(c.events, key=lambda e: (e.at, e.id))],
        "hearing": hearing(c, lang, today),
        "documents": docs,
        "can_add_documents": c.status in OPEN and len(docs) < MAX_DOCS,
        "is_mock": bool(c.is_mock),
    }


def lookup(repo: Repository, ref: str, code: str | None, lang: str) -> dict[str, Any]:
    c = complaint_for(repo, ref, code)
    repo._audit("complaint_status", {"ref_no": c.ref_no})
    return view(repo, c, lang)


def mine(repo: Repository, lang: str) -> dict[str, Any]:
    if repo.p.role != "citizen" or repo.p.user_id is None:
        return {"complaints": []}
    rows = repo.s.scalars(select(Complaint).where(Complaint.complainant_user_id == repo.p.user_id)
                          .order_by(Complaint.filed_on.desc(), Complaint.id.desc()).limit(50)).all()
    return {"complaints": [view(repo, c, lang) for c in rows]}


def upcoming_hearings(repo: Repository, days: int = 14, today: date | None = None) -> list[dict[str, Any]]:
    """Hearings fixed in the next `days` days, in the officer's district."""
    from datetime import timedelta

    today = today or date.today()
    stmt = select(Complaint).where(Complaint.status == "hearing_scheduled", Complaint.hearing_on >= today,
                                   Complaint.hearing_on <= today + timedelta(days=days)).order_by(Complaint.hearing_on)
    if repo.p.district_scope:
        stmt = stmt.where(Complaint.district == repo.p.district_scope)
    rows = repo.s.scalars(stmt.limit(50)).all()
    names = {p.id: p.name for p in repo.s.scalars(select(Project).where(Project.id.in_({c.project_id for c in rows if c.project_id})))}
    return [{"id": c.id, "ref_no": c.ref_no, "on": c.hearing_on.isoformat(), "days_to": (c.hearing_on - today).days,
             "place": c.hearing_place, "category": c.category, "project": names.get(c.project_id),
             "district": c.district} for c in rows]
