"""Import public GUJRERA records (projects and agents) from a downloaded file.

Reads CSV, Excel (.xlsx) or JSON exactly as downloaded or exported, without hand-editing:

* Column names are matched loosely ("Project Name", "projectName", "PROJECT_NAME" all work).
  See ``PROJECT_COLUMNS`` / ``AGENT_COLUMNS`` for the accepted names.
* Dates may be ``dd/mm/yyyy`` (as shown on the GUJRERA portal), ``yyyy-mm-dd``, Excel dates, or
  millisecond timestamps (as in JSON feeds).
* Portal project types ("Residential/Group Housing", "Plotted Development", ...) are mapped to
  residential / commercial / mixed / plotted.
* JSON may be a list of records or an object holding one (``data``, ``content``, ``items``, ...).

Every imported row is marked ``is_mock=False`` and keeps a ``source_url`` (the row's own link if the
file has one, else the page it was downloaded from) so answers can cite it. MOCK registration
numbers are refused. Rows with problems are reported, not guessed.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from gujrera.db.models import Agent, Promoter
from gujrera.ingest.csv_import import ImportReport, import_project_row
from gujrera.trust.rera_number import parse_rera_number

DEFAULT_SOURCE = "https://gujrera.gujarat.gov.in/#/"

# canonical field -> accepted column names (compared after lower-casing and dropping non-letters/digits)
PROJECT_COLUMNS: dict[str, tuple[str, ...]] = {
    "rera_no": ("rera_no", "rera no", "rera number", "registration no", "registration number", "reg no",
                "project registration no", "project reg no", "projectregno", "rera reg no", "rera registration no",
                "gujrera no", "regno", "projectregistrationno"),
    "project_name": ("project_name", "project name", "projectname", "name of project", "project", "name",
                     "entityname"),
    "project_name_gu": ("project_name_gu", "project name gujarati", "project name (gujarati)"),
    "promoter_name": ("promoter_name", "promoter name", "promotername", "promoter", "developer",
                      "developer name", "builder", "builder name", "name of promoter"),
    "promoter_name_gu": ("promoter_name_gu", "promoter name gujarati", "promoter name (gujarati)"),
    "district": ("district", "district name", "districtname", "dist", "distname"),
    "taluka": ("taluka", "taluka name", "tehsil"),
    "planning_authority": ("planning_authority", "planning authority", "authority", "development authority"),
    "project_type": ("project_type", "project type", "projecttype", "type", "type of project", "ptype"),
    "status": ("status", "project status", "projectstatus"),
    "units": ("units", "total units", "no of units", "number of units", "totalunits", "unit count"),
    "reg_date": ("reg_date", "registration date", "date of registration", "approval date", "approved on",
                 "reg date", "registrationdate", "approvedate"),
    "start_date": ("start_date", "project start date", "start date", "projectstartdate"),
    "proposed_completion": ("proposed_completion", "project end date", "end date", "completion date",
                            "proposed completion", "proposed completion date", "projectenddate",
                            "original completion date", "proposed date of completion"),
    "revised_completion": ("revised_completion", "revised completion", "revised completion date",
                           "extended completion date", "extension date", "extended end date", "revised end date"),
    "actual_completion": ("actual_completion", "actual completion", "actual completion date",
                          "completion certificate date", "occupancy date"),
    "source_url": ("source_url", "source url", "url", "link", "project url", "source"),
    # "02/08/2024 - 30/04/2029" as in the portal's search results
    "date_range": ("pdate", "project dates", "projectdates", "project duration", "project period", "duration"),
    "entity_type": ("entitytype", "entity type", "record type"),
}
AGENT_COLUMNS: dict[str, tuple[str, ...]] = {
    "reg_no": ("reg_no", "agent registration no", "agent reg no", "registration no", "registration number",
               "rera no", "agent rera no", "agentregno", "reg no", "regno"),
    "name": ("name", "agent name", "agentname", "name of agent"),
    "name_gu": ("name_gu", "agent name gujarati"),
    "district": ("district", "district name", "dist"),
    "reg_date": ("reg_date", "registration date", "date of registration", "approval date", "reg date"),
    "valid_until": ("valid_until", "valid upto", "valid up to", "valid till", "validity", "expiry date",
                    "valid until", "validupto", "expirydate"),
    "status": ("status", "agent status"),
    "source_url": ("source_url", "source url", "url", "link", "source"),
}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y",
                "%d %B %Y", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S")


@dataclass
class FileReport:
    kind: str = ""
    sheet: str = ""
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # imported, but worth a look
    no_promoter: int = 0  # projects imported without a promoter name
    unmatched_columns: list[str] = field(default_factory=list)


def _key(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _column_map(headers: Iterable[str], spec: dict[str, tuple[str, ...]]) -> tuple[dict[str, str], list[str]]:
    """Map file headers to canonical fields; returns (canonical -> header, unused headers)."""
    lookup = {_key(alias): canon for canon, aliases in spec.items() for alias in aliases}
    mapping: dict[str, str] = {}
    unused = []
    for h in headers:
        canon = lookup.get(_key(h))
        if canon and canon not in mapping:
            mapping[canon] = h
        else:
            unused.append(str(h))
    return mapping, unused


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:  # epoch milliseconds (JSON feeds)
            return datetime.fromtimestamp(value / 1000, tz=UTC).date()
        if 20_000 < value < 80_000:  # Excel serial day number
            return date(1899, 12, 30) + timedelta(days=int(value))
        raise ValueError(f"unrecognised date {value!r}")
    text = str(value).strip()
    if text.isdigit():
        return parse_date(int(text))
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {text!r} (use dd/mm/yyyy or yyyy-mm-dd)")


def project_type(value: Any) -> str:
    t = str(value or "").lower()
    if "plot" in t:
        return "plotted"
    if "mix" in t:
        return "mixed"
    if "commerc" in t or "shop" in t or "office" in t:
        return "commercial"
    return "residential"  # "Residential/Group Housing", blanks


UNKNOWN_PROMOTER = "Promoter not in imported records"


def project_status(value: Any, actual_completion: date | None, end: date | None = None,
                   today: date | None = None) -> str:
    """Status from the file; without one, 'unverified' once the registered end date has passed (the source does
    not say whether the project was completed, so no delay or lapse is claimed), else 'ongoing'."""
    s = str(value or "").lower()
    if "revok" in s or "cancel" in s:
        return "revoked"
    if "laps" in s or "expir" in s:
        return "lapsed"
    if "complet" in s or actual_completion:
        return "completed"
    if s:
        return "ongoing"
    if end and end < (today or date.today()):
        return "unverified"
    return "ongoing"


def split_range(value: Any) -> tuple[date | None, date | None]:
    """'02/08/2024 - 30/04/2029' -> (start, end)."""
    parts = [p for p in re.split(r"\s+(?:-|to)\s+", _s(value)) if p]
    if len(parts) != 2:
        return None, None
    return parse_date(parts[0]), parse_date(parts[1])


def agent_status(value: Any, valid_until: date | None, today: date) -> str:
    s = str(value or "").lower()
    if "revok" in s or "cancel" in s:
        return "revoked"
    if "laps" in s or "expir" in s:
        return "expired"
    if s:
        return "active"
    return "expired" if valid_until and valid_until < today else "active"


# ------------------------------------------------------------------ reading files
def read_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        text = path.read_text(encoding="utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        return [dict(r) for r in csv.DictReader(text.splitlines(), dialect=dialect)]
    if suffix in (".xlsx", ".xlsm"):

        return [rec for _, recs in read_sheets(path) for rec in recs]
    if suffix == ".json":
        return _json_records(json.loads(path.read_text(encoding="utf-8-sig")))
    raise ValueError(f"{path.name}: use a .csv, .xlsx or .json file")


def read_sheets(path: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    """Every sheet (Excel) or the whole file (CSV/JSON) as (name, records). Empty sheets are dropped."""
    if path.suffix.lower() not in (".xlsx", ".xlsm"):
        return [(path.name, read_records(path))]
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    out = []
    try:
        for ws in wb.worksheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            rows = [r for r in rows if any(c not in (None, "") for c in r)]
            if len(rows) < 2:
                continue
            header = [str(c).strip() if c is not None else "" for c in rows[0]]
            out.append((ws.title, [{h: v for h, v in zip(header, r) if h} for r in rows[1:]]))
    finally:
        wb.close()
    return out


def _json_records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("data", "content", "items", "result", "results", "records", "projects", "agents", "list"):
            if key in data:
                return _json_records(data[key])
        lists = [v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
        if lists:
            return lists[0]
    raise ValueError("JSON must be a list of records, or an object containing one")


def detect_kind(records: list[dict[str, Any]]) -> str:
    """'agent' if the registration numbers are agent numbers (AG/...), else 'project'."""
    if not records:
        return "project"
    pmap, _ = _column_map(records[0].keys(), PROJECT_COLUMNS)
    amap, _ = _column_map(records[0].keys(), AGENT_COLUMNS)
    col = pmap.get("rera_no") or amap.get("reg_no")
    for r in records[:20]:
        parsed = parse_rera_number(str(r.get(col) or "")) if col else None
        if parsed:
            return parsed.kind
    return "agent" if "name" in amap and "project_name" not in pmap else "project"


# ------------------------------------------------------------------ importing
def import_file(session: Session, path: Path, *, kind: str | None = None, source_url: str | None = None,
                today: date | None = None) -> list[FileReport]:
    """Import every sheet of the file (one report per sheet; a CSV or JSON file is one sheet).
    Sheets with no registration-number column (e.g. an instructions sheet) are skipped."""
    reports = []
    for name, records in read_sheets(path):
        if records and kind is None and not _has_number_column(records):
            continue
        rep = import_records(session, records, kind=kind, source_url=source_url, today=today)
        rep.sheet = name
        reports.append(rep)
    if not reports:
        reports.append(FileReport(errors=["no rows with a registration number column found"]))
    return reports


def _has_number_column(records: list[dict[str, Any]]) -> bool:
    keys = records[0].keys()
    return "rera_no" in _column_map(keys, PROJECT_COLUMNS)[0] or "reg_no" in _column_map(keys, AGENT_COLUMNS)[0]


def import_records(session: Session, records: list[dict[str, Any]], *, kind: str | None = None,
                   source_url: str | None = None, today: date | None = None) -> FileReport:
    kind = kind or detect_kind(records)
    # Mixed search results (projects, promoters, agents, professionals): keep only this kind. Other rows can hold
    # personal contact details and are never read.
    etype = next((k for k in records[0] if _key(k) in ("entitytype", "recordtype")), None) if records else None
    if etype:
        keep = {"project": "PROJECT", "agent": "AGENT"}[kind]
        records = [r for r in records if _s(r.get(etype)).upper() == keep]
    report = FileReport(kind=kind, rows=len(records))
    if not records:
        report.errors.append("no rows found")
        return report
    spec = PROJECT_COLUMNS if kind == "project" else AGENT_COLUMNS
    mapping, report.unmatched_columns = _column_map(records[0].keys(), spec)
    today = today or date.today()
    for n, rec in enumerate(records, start=2):  # row 1 is the header
        row = {canon: rec.get(col) for canon, col in mapping.items()}
        number = _s(row.get("rera_no" if kind == "project" else "reg_no"))
        parsed = parse_rera_number(number)
        if parsed and parsed.code is None:
            report.warnings.append(f"row {n}: {number!r} has an unexpected code segment; chat and ad checks may "
                                   "not recognise it (tell us the format so the parser can be updated)")
        try:
            with session.begin_nested():
                if kind == "project":
                    _project(session, row, source_url, report, today)
                else:
                    _agent(session, row, source_url, today, report)
        except (ValueError, KeyError) as exc:
            report.errors.append(f"row {n}: {exc}")
    session.commit()
    return report


def _s(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _project(session: Session, row: dict[str, Any], source_url: str | None, report: FileReport,
             today: date | None = None) -> None:
    parsed = parse_rera_number(_s(row.get("rera_no")))
    actual = parse_date(row.get("actual_completion"))
    start, end = split_range(row.get("date_range"))
    reg = parse_date(row.get("reg_date")) or parse_date(row.get("start_date")) or start
    proposed = parse_date(row.get("proposed_completion")) or end
    revised = parse_date(row.get("revised_completion"))
    promoter = _s(row.get("promoter_name"))
    canonical = {
        "rera_no": _s(row.get("rera_no")),
        "project_name": _s(row.get("project_name")),
        "project_name_gu": _s(row.get("project_name_gu")),
        "promoter_name": promoter or UNKNOWN_PROMOTER,
        "promoter_name_gu": _s(row.get("promoter_name_gu")),
        "district": _s(row.get("district")).title() or ((parsed.district or "").title() if parsed else ""),
        "taluka": _s(row.get("taluka")),
        "planning_authority": _s(row.get("planning_authority")),
        "project_type": project_type(row.get("project_type")),
        "status": project_status(row.get("status"), actual, revised or proposed, today),
        "units": _s(row.get("units")).split(".")[0],
        "reg_date": reg.isoformat() if reg else "",
        "proposed_completion": proposed.isoformat() if proposed else "",
        "revised_completion": revised.isoformat() if revised else "",
        "actual_completion": actual.isoformat() if actual else "",
        "source_url": _s(row.get("source_url")) or (source_url or ""),
    }
    inner = ImportReport()
    import_project_row(session, canonical, inner)
    if not promoter:
        placeholder = session.scalar(select(Promoter).where(Promoter.name == UNKNOWN_PROMOTER))
        placeholder.promoter_type = "unknown"
        report.no_promoter += 1
    report.inserted += inner.inserted
    report.updated += inner.updated


def _iso(value: Any) -> str:
    d = parse_date(value)
    return d.isoformat() if d else ""


def _agent(session: Session, row: dict[str, Any], source_url: str | None, today: date, report: FileReport) -> None:
    raw = _s(row.get("reg_no"))
    parsed = parse_rera_number(raw)
    if parsed is None or parsed.kind != "agent":
        raise ValueError(f"unrecognised agent registration number {raw!r}")
    if parsed.is_mock:
        raise ValueError("MOCK registration numbers cannot be imported as public data")
    name = _s(row.get("name"))
    if not name:
        raise ValueError("missing name")
    valid_until = parse_date(row.get("valid_until"))
    reg = parse_date(row.get("reg_date"))
    if not valid_until or not reg:
        raise ValueError("missing " + ", ".join(k for k, v in (("reg_date", reg), ("valid_until", valid_until)) if not v))
    src = _s(row.get("source_url")) or source_url
    if not src:
        raise ValueError("missing source_url (add a column or pass a default source URL)")
    values = dict(name=name, name_gu=_s(row.get("name_gu")) or None,
                  district=_s(row.get("district")).title() or (parsed.district or "").title() or "Gujarat",
                  reg_date=reg, valid_until=valid_until, status=agent_status(row.get("status"), valid_until, today),
                  source_url=src, is_mock=False)
    agent = session.scalar(select(Agent).where(Agent.reg_no == parsed.normalised))
    if agent is None:
        session.add(Agent(reg_no=parsed.normalised, **values))
        report.inserted += 1
    else:
        for k, v in values.items():
            setattr(agent, k, v)
        report.updated += 1
    session.flush()
