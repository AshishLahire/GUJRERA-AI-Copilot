"""Officer reports as Excel files and saved reports.

An export re-runs the question on the server (so the file is current, district-scoped and audited) and
writes an .xlsx with the report on the first sheet, headed by what was asked, the scope, the period, when
and by whom it was run, and the read-only SQL on a second sheet. Saved reports keep an officer's question
so it can be run again with one click; each officer sees only their own.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from sqlalchemy import select

from gujrera.db.models import SavedReport, User
from gujrera.db.repository import AccessDenied, Repository

MAX_SAVED = 30


def _officer(repo: Repository) -> None:
    if repo.p.role != "officer":
        raise AccessDenied("Reports are available to GUJRERA officers only.")


def _username(repo: Repository) -> str:
    user = repo.s.get(User, repo.p.user_id) if repo.p.user_id else None
    return user.username if user else "officer"


def _heading(column: str) -> str:
    return column.replace("_", " ").strip().capitalize()


def to_xlsx(repo: Repository, question: str, card: dict[str, Any], sentences: list[str]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    bold = Font(bold=True)
    ws.append([card.get("title") or "Report"])
    ws["A1"].font = Font(bold=True, size=14)
    meta = [
        ("Question", question),
        ("District scope", card.get("scoped_to") or "All districts"),
        ("Run at", datetime.now().strftime("%d %b %Y %H:%M")),
        ("Run by", _username(repo)),
        ("Rows", len(card.get("rows") or [])),
        ("Source", "GujRERA Saathi: read-only query on the reporting views, logged"),
    ]
    for k, v in meta:
        ws.append([k, v])
        ws.cell(ws.max_row, 1).font = bold
    for line in sentences:
        ws.append(["Note", line])
        ws.cell(ws.max_row, 1).font = bold
    ws.append([])
    header_row = ws.max_row + 1
    columns = card.get("columns") or []
    ws.append([_heading(c) for c in columns])
    fill = PatternFill("solid", fgColor="FFF1BF")
    for i in range(1, len(columns) + 1):
        cell = ws.cell(header_row, i)
        cell.font = bold
        cell.fill = fill
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for row in card.get("rows") or []:
        ws.append(list(row))
    ws.freeze_panes = ws.cell(header_row + 1, 1)
    for i, c in enumerate(columns, 1):
        values = [len(str(r[i - 1])) for r in (card.get("rows") or [])[:200] if r[i - 1] is not None]
        ws.column_dimensions[get_column_letter(i)].width = min(60, max(12, len(_heading(c)) + 2, *(v + 2 for v in values)))
    if columns:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(columns))}{ws.max_row}"

    q = wb.create_sheet("Query")
    q.append(["The read-only SQL that produced this report (district scope added on the server)"])
    q["A1"].font = bold
    q.append([card.get("sql") or ""])
    q["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    q.column_dimensions["A"].width = 120
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _saved_dict(r: SavedReport) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "question": r.question, "lang": r.lang,
            "created_at": r.created_at.isoformat(timespec="minutes"),
            "last_run_at": r.last_run_at.isoformat(timespec="minutes") if r.last_run_at else None}


def list_saved(repo: Repository) -> dict[str, Any]:
    _officer(repo)
    rows = repo.s.scalars(select(SavedReport).where(SavedReport.user_id == repo.p.user_id)
                          .order_by(SavedReport.created_at.desc())).all()
    return {"saved": [_saved_dict(r) for r in rows]}


def save(repo: Repository, name: str, question: str, lang: str) -> dict[str, Any]:
    _officer(repo)
    name, question = (name or "").strip()[:120], (question or "").strip()[:500]
    if not question:
        raise ValueError("Nothing to save: run a report first.")
    mine = repo.s.scalars(select(SavedReport).where(SavedReport.user_id == repo.p.user_id)).all()
    same = next((r for r in mine if r.question.lower() == question.lower()), None)
    if same:
        same.name = name or same.name
        repo.s.flush()
        return _saved_dict(same)
    if len(mine) >= MAX_SAVED:
        raise ValueError(f"You can keep up to {MAX_SAVED} saved reports; delete one first.")
    row = SavedReport(user_id=repo.p.user_id, name=name or question[:120], question=question, lang=lang,
                      created_at=datetime.now())
    repo.s.add(row)
    repo.s.flush()
    repo._audit("report_saved", {"question": question})
    return _saved_dict(row)


def delete(repo: Repository, saved_id: int) -> dict[str, Any]:
    _officer(repo)
    row = repo.s.get(SavedReport, saved_id)
    if row is None or row.user_id != repo.p.user_id:
        raise ValueError("No such saved report.")
    repo.s.delete(row)
    repo.s.flush()
    return {"deleted": saved_id}


def touch(repo: Repository, question: str) -> None:
    """Note when a saved report was last run."""
    for r in repo.s.scalars(select(SavedReport).where(SavedReport.user_id == repo.p.user_id)):
        if r.question.lower() == (question or "").strip().lower():
            r.last_run_at = datetime.now()
