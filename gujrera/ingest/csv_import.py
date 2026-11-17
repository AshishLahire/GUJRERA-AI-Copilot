"""Import public GUJRERA project records from a CSV file.

Use this for records collected by hand (or exported) from the public GUJRERA
project search while scraping permission is unconfirmed. Imported rows get
``is_mock=False`` and must carry ``source_url`` so every answer can cite the
public page it came from.

Columns (see ``public_projects_template.csv``; dates as YYYY-MM-DD):
rera_no, project_name, project_name_gu, promoter_name, promoter_name_gu,
district, taluka, planning_authority, project_type, status, units, reg_date,
proposed_completion, revised_completion, actual_completion, source_url
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gujrera.db.models import PROJECT_STATUSES, PROJECT_TYPES, Project, Promoter
from gujrera.trust.rera_number import parse_rera_number

REQUIRED = ("rera_no", "project_name", "promoter_name", "district", "reg_date",
            "proposed_completion", "source_url")


@dataclass
class ImportReport:
    inserted: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def _date(value: str | None) -> date | None:
    value = (value or "").strip()
    return date.fromisoformat(value) if value else None


def import_projects_csv(session: Session, path: Path) -> ImportReport:
    report = ImportReport()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            try:
                _import_row(session, row, report)
            except (ValueError, KeyError) as exc:
                report.errors.append(f"line {line_no}: {exc}")
    session.commit()
    return report


def _import_row(session: Session, row: dict[str, str], report: ImportReport) -> None:
    row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
    missing = [c for c in REQUIRED if not row.get(c)]
    if missing:
        raise ValueError(f"missing {', '.join(missing)}")
    parsed = parse_rera_number(row["rera_no"])
    if parsed is None or parsed.kind != "project":
        raise ValueError(f"unrecognised project registration number {row['rera_no']!r}")
    if parsed.is_mock:
        raise ValueError("MOCK registration numbers cannot be imported as public data")

    ptype = (row.get("project_type") or "residential").lower()
    status = (row.get("status") or "ongoing").lower()
    if ptype not in PROJECT_TYPES:
        raise ValueError(f"project_type must be one of {PROJECT_TYPES}")
    if status not in PROJECT_STATUSES:
        raise ValueError(f"status must be one of {PROJECT_STATUSES}")

    promoter = session.scalar(select(Promoter).where(func.lower(Promoter.name) == row["promoter_name"].lower()))
    if promoter is None:
        promoter = Promoter(name=row["promoter_name"], name_gu=row.get("promoter_name_gu") or None,
                            district=row["district"], source_url=row["source_url"], is_mock=False)
        session.add(promoter)
        session.flush()

    proposed = _date(row["proposed_completion"])
    revised = _date(row.get("revised_completion"))
    values = dict(
        promoter_id=promoter.id, name=row["project_name"], name_gu=row.get("project_name_gu") or None,
        district=row["district"], taluka=row.get("taluka") or parsed.taluka,
        planning_authority=row.get("planning_authority") or parsed.authority,
        project_type=ptype, status=status, units=int(row.get("units") or 0),
        reg_date=_date(row["reg_date"]), proposed_completion=proposed, revised_completion=revised,
        actual_completion=_date(row.get("actual_completion")), reg_valid_until=revised or proposed,
        source_url=row["source_url"], is_mock=False,
    )
    project = session.scalar(select(Project).where(Project.rera_no == parsed.normalised))
    if project is None:
        session.add(Project(rera_no=parsed.normalised, **values))
        report.inserted += 1
    else:
        for key, value in values.items():
            setattr(project, key, value)
        report.updated += 1
    session.flush()
