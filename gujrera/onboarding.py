"""Data onboarding console: load the department's data files into the registry the assistants answer from.

The department shares its data as CSV dumps, Excel exports or API JSON, split by its own database headers.
A state-level officer (the data admin in the POC) loads them in four steps:

1. **Upload** a .csv, .xlsx or .json file. It is kept in the uploads folder next to the database; nothing
   reaches the registry yet.
2. **Match columns.** Each sheet's headers are matched to the registry's fields ("Project Name",
   "projectName", "PROJECT_NAME" all match); the officer can change any match.
3. **Check.** Every row is applied inside a transaction that is then rolled back: the result shows how many
   rows are new, changed, unchanged or rejected, and why each rejected row failed. Nothing is saved.
4. **Load.** The same run, committed. The chat's name index is refreshed so the assistants answer from the
   new records straight away, and the rejected rows can be downloaded to fix and load again.

Eight kinds of file. Public registry records:

* ``project``: full project records (new projects are added, existing ones updated);
* ``agent``: real estate agent records;
* ``project_update``: extra fields for projects already in the registry, matched by RERA number, such as
  the site address (which also sets the locality, so "projects in Bopal" is answered exactly), a revised
  or actual completion date, the status or the promoter.

And the department's internal records, which the authority assistant answers from (see
``gujrera/onboarding_internal.py``): ``complaint``, ``order`` (with penalty amounts), ``notice``, ``scrutiny``
and ``default``, each matched to its project by RERA number.

Only mapped columns are read; any other column in the file (phone numbers, e-mails) is ignored. Every
check and load is written to the audit log with the officer's name.
"""

from __future__ import annotations

import csv
import io
import json
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gujrera.db.models import Agent, ImportRun, Project, Promoter, User
from gujrera.db.repository import AccessDenied, Repository
from gujrera.ingest.public_import import (
    AGENT_COLUMNS,
    DEFAULT_SOURCE,
    PROJECT_COLUMNS,
    FileReport,
    _agent,
    _column_map,
    _project,
    _s,
    detect_kind,
    district_name,
    parse_date,
    project_type,
    read_sheets,
)
from gujrera.trust.rera_number import parse_rera_number

ALLOWED = (".csv", ".xlsx", ".xlsm", ".json")
MAX_BYTES = 25 * 1024 * 1024
MAX_ERRORS = 500

ADDRESS = ("address", "site address", "project address", "siteaddress", "projectaddress", "location",
           "project location", "address of project", "site location")
LOCALITY = ("locality", "area", "village", "town", "city area", "mouje", "moje", "village name")

SPECS: dict[str, dict[str, tuple[str, ...]]] = {
    "project": {**PROJECT_COLUMNS, "address": ADDRESS, "locality": LOCALITY},
    "agent": AGENT_COLUMNS,
    "project_update": {
        "rera_no": PROJECT_COLUMNS["rera_no"], "address": ADDRESS, "locality": LOCALITY,
        "taluka": PROJECT_COLUMNS["taluka"], "promoter_name": PROJECT_COLUMNS["promoter_name"],
        "project_type": PROJECT_COLUMNS["project_type"], "status": PROJECT_COLUMNS["status"],
        "units": PROJECT_COLUMNS["units"], "revised_completion": PROJECT_COLUMNS["revised_completion"],
        "actual_completion": PROJECT_COLUMNS["actual_completion"],
    },
}
REQUIRED: dict[str, tuple[str, ...]] = {
    "project": ("rera_no", "project_name"),
    "agent": ("reg_no", "name", "reg_date", "valid_until"),
    "project_update": ("rera_no",),
}
KIND_LABELS = {
    "project": "Projects: new or updated records",
    "agent": "Real estate agents",
    "project_update": "Extra details for projects already loaded (address, dates, status)",
}
LABELS = {
    "rera_no": "RERA registration number", "project_name": "Project name",
    "project_name_gu": "Project name (Gujarati)", "promoter_name": "Promoter name",
    "promoter_name_gu": "Promoter name (Gujarati)", "district": "District", "taluka": "Taluka",
    "planning_authority": "Planning authority", "project_type": "Project type", "status": "Status",
    "units": "Number of units", "reg_date": "Registration date", "start_date": "Project start date",
    "proposed_completion": "Proposed completion date", "revised_completion": "Revised completion date",
    "actual_completion": "Actual completion date", "source_url": "Source link",
    "date_range": "Project dates (start - end)", "entity_type": "Record type", "address": "Site address",
    "locality": "Locality / area", "reg_no": "Agent registration number", "name": "Agent name",
    "name_gu": "Agent name (Gujarati)", "valid_until": "Registration valid until",
}
HINTS = {
    "proposed_completion": "or 'Project dates'",
    "reg_date": "or 'Project start date' / 'Project dates'",
    "address": "also sets the locality when it names a known area",
    "source_url": "else the source link below is used",
}


# ------------------------------------------------------------------ access and storage
def require_admin(repo: Repository) -> None:
    if repo.p.role != "officer" or repo.p.district_scope:
        raise AccessDenied("Loading data is for state-level GUJRERA officers (the data admins).")


def _username(repo: Repository) -> str | None:
    user = repo.s.get(User, repo.p.user_id) if repo.p.user_id else None
    return user.username if user else None


def uploads_dir(session: Session) -> Path:
    db = session.get_bind().url.database
    base = Path(db).parent if db and db != ":memory:" else Path("data/gujrera")
    folder = base / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _stored(session: Session, run: ImportRun) -> Path:
    return uploads_dir(session) / run.stored_as


def _get_run(repo: Repository, run_id: str) -> ImportRun:
    run = repo.s.get(ImportRun, run_id)
    if run is None:
        raise ValueError("No such upload.")
    return run


def _sheets(path: Path, display: str | None = None) -> list[tuple[str, list[dict[str, Any]]]]:
    """Sheets of the stored file; a CSV or JSON file is one sheet named after the uploaded file."""
    try:
        sheets = read_sheets(path)
        if display and len(sheets) == 1 and sheets[0][0] == path.name:
            sheets = [(display, sheets[0][1])]
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Could not read the file: {exc}") from None
    sheets = [(n, r) for n, r in sheets if r]
    if not sheets:
        raise ValueError("The file has no rows.")
    return sheets


# ------------------------------------------------------------------ step 1: upload and describe
def suggest_kind(records: list[dict[str, Any]]) -> str:
    # The department's internal records are recognised by a column only they have.
    keys = {str(h).strip().lower().replace("_", " ") for h in (records[0].keys() if records else [])}
    for kind, marks in (("order", ("order no", "order number", "order type")),
                        ("notice", ("notice no", "notice number", "notice type")),
                        ("complaint", ("complaint no", "complaint number", "complaint type", "complaint id")),
                        ("default", ("default type", "non compliance", "non-compliance")),
                        ("scrutiny", ("application type", "scrutiny status", "current stage"))):
        if keys & set(marks):
            return kind
    kind = detect_kind(records)
    if kind == "project":
        mapping, _ = _column_map(records[0].keys(), SPECS["project"])
        if "project_name" not in mapping:
            return "project_update"
    return kind


def _headers(records: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for rec in records[:50]:
        for h in rec:
            seen.setdefault(str(h), None)
    return list(seen)


# Gujarati and Hindi for what the check screen shows (English above). Native-speaker review pending.
KIND_I18N = {
    "project": ("પ્રોજેક્ટ: નવા કે બદલાયેલા રેકોર્ડ", "प्रोजेक्ट: नए या बदले हुए रिकॉर्ड"),
    "agent": ("રિયલ એસ્ટેટ એજન્ટ", "रियल एस्टेट एजेंट"),
    "project_update": ("લોડ થયેલા પ્રોજેક્ટની વધારાની વિગતો (સરનામું, તારીખો, સ્થિતિ)",
                       "लोड हो चुके प्रोजेक्ट का अतिरिक्त विवरण (पता, तारीखें, स्थिति)"),
}
LABEL_I18N = {
    "rera_no": ("RERA નોંધણી નંબર", "RERA पंजीकरण संख्या"),
    "project_name": ("પ્રોજેક્ટનું નામ", "प्रोजेक्ट का नाम"),
    "project_name_gu": ("પ્રોજેક્ટનું નામ (ગુજરાતી)", "प्रोजेक्ट का नाम (गुजराती)"),
    "promoter_name": ("પ્રમોટરનું નામ", "प्रमोटर का नाम"),
    "promoter_name_gu": ("પ્રમોટરનું નામ (ગુજરાતી)", "प्रमोटर का नाम (गुजराती)"),
    "district": ("જિલ્લો", "जिला"),
    "taluka": ("તાલુકો", "तालुका"),
    "planning_authority": ("આયોજન સત્તામંડળ", "योजना प्राधिकरण"),
    "project_type": ("પ્રોજેક્ટનો પ્રકાર", "प्रोजेक्ट का प्रकार"),
    "status": ("સ્થિતિ", "स्थिति"),
    "units": ("એકમોની સંખ્યા", "इकाइयों की संख्या"),
    "reg_date": ("નોંધણી તારીખ", "पंजीकरण तिथि"),
    "start_date": ("પ્રોજેક્ટ શરૂ થવાની તારીખ", "प्रोजेक्ट शुरू होने की तिथि"),
    "proposed_completion": ("પ્રસ્તાવિત પૂર્ણતા તારીખ", "प्रस्तावित पूर्णता तिथि"),
    "revised_completion": ("સુધારેલી પૂર્ણતા તારીખ", "संशोधित पूर्णता तिथि"),
    "actual_completion": ("ખરેખર પૂર્ણતા તારીખ", "वास्तविक पूर्णता तिथि"),
    "source_url": ("સ્રોત લિંક", "स्रोत लिंक"),
    "date_range": ("પ્રોજેક્ટની તારીખો (શરૂ - અંત)", "प्रोजेक्ट की तारीखें (शुरू - अंत)"),
    "entity_type": ("રેકોર્ડનો પ્રકાર", "रिकॉर्ड का प्रकार"),
    "address": ("સ્થળનું સરનામું", "स्थल का पता"),
    "locality": ("વિસ્તાર", "इलाका"),
    "reg_no": ("એજન્ટ નોંધણી નંબર", "एजेंट पंजीकरण संख्या"),
    "name": ("એજન્ટનું નામ", "एजेंट का नाम"),
    "name_gu": ("એજન્ટનું નામ (ગુજરાતી)", "एजेंट का नाम (गुजराती)"),
    "valid_until": ("નોંધણી ક્યાં સુધી માન્ય", "पंजीकरण कब तक मान्य"),
}
HINT_I18N = {
    "proposed_completion": ("અથવા 'Project dates'", "या 'Project dates'"),
    "reg_date": ("અથવા 'Project start date' / 'Project dates'", "या 'Project start date' / 'Project dates'"),
    "address": ("જાણીતા વિસ્તારનું નામ હોય તો વિસ્તાર પણ નક્કી કરે છે", "किसी जाने-पहचाने इलाके का नाम हो तो इलाका भी तय करता है"),
    "source_url": ("નહીં તો નીચેની સ્રોત લિંક વપરાય છે", "नहीं तो नीचे दी गई स्रोत लिंक इस्तेमाल होती है"),
}


# The department's internal records (gujrera/onboarding_internal.py): same console, five more kinds.
from gujrera import onboarding_internal as _internal  # noqa: E402

SPECS.update(_internal.SPECS)
REQUIRED.update(_internal.REQUIRED)
KIND_LABELS.update(_internal.KIND_LABELS)
KIND_I18N.update(_internal.KIND_I18N)
for _k, _v in _internal.LABELS.items():
    LABELS.setdefault(_k, _v)
for _k, _v in _internal.LABEL_I18N.items():
    LABEL_I18N.setdefault(_k, _v)


def _tri(en: str | None, pair: tuple[str, str] | None) -> dict[str, str] | None:
    if en is None:
        return None
    return {"en": en, "gu": pair[0], "hi": pair[1]} if pair else {"en": en, "gu": en, "hi": en}


def describe_sheet(name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    headers = _headers(records)
    kinds = {}
    for kind, spec in SPECS.items():
        mapping, unused = _column_map(headers, spec)
        kinds[kind] = {
            "label": KIND_LABELS[kind],
            "label_i18n": _tri(KIND_LABELS[kind], KIND_I18N.get(kind)),
            "fields": [{"key": k, "label": LABELS.get(k, k), "required": k in REQUIRED[kind], "hint": HINTS.get(k),
                        "label_i18n": _tri(LABELS.get(k, k), LABEL_I18N.get(k)),
                        "hint_i18n": _tri(HINTS.get(k), HINT_I18N.get(k))}
                       for k in spec if k != "entity_type"],
            "mapping": mapping, "unused": unused,
        }
    sample = [{h: _s(rec.get(h))[:120] for h in headers} for rec in records[:5]]
    return {"name": name, "rows": len(records), "headers": headers, "suggested_kind": suggest_kind(records),
            "kinds": kinds, "sample": sample}


def upload(repo: Repository, filename: str, data: bytes) -> dict[str, Any]:
    require_admin(repo)
    name = Path(filename or "upload").name[:200]
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise ValueError("Use a .csv, .xlsx or .json file.")
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise ValueError("The file is larger than 25 MB; split it into smaller files.")
    run_id = uuid.uuid4().hex
    path = uploads_dir(repo.s) / f"{run_id}{ext}"
    path.write_bytes(data)
    try:
        sheets = _sheets(path, name)
    except ValueError:
        path.unlink(missing_ok=True)
        raise
    run = ImportRun(id=run_id, filename=name, stored_as=path.name, size_bytes=len(data),
                    uploaded_by=_username(repo), uploaded_at=datetime.now(), status="uploaded",
                    rows=sum(len(r) for _, r in sheets))
    repo.s.add(run)
    repo.s.commit()
    repo._audit("data_upload", {"run": run_id, "file": name, "rows": run.rows})
    return {"run": _run_dict(run), "sheets": [describe_sheet(n, r) for n, r in sheets]}


def describe(repo: Repository, run_id: str) -> dict[str, Any]:
    require_admin(repo)
    run = _get_run(repo, run_id)
    return {"run": _run_dict(run), "sheets": [describe_sheet(n, r) for n, r in _sheets(_stored(repo.s, run), run.filename)]}


# ------------------------------------------------------------------ steps 3 and 4: check and load
@dataclass
class _Tally:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: int = 0
    no_promoter: int = 0


def _snap(obj: Any) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _locality(given: str, address: str) -> str | None:
    from gujrera.analytics.reports import find_locality

    if given:
        return find_locality(given.lower()) or given.strip().title()[:80]
    return find_locality(address.lower()) if address else None


def _extras(project: Project, row: dict[str, Any]) -> None:
    address, given = _s(row.get("address")), _s(row.get("locality"))
    if address:
        project.address = address[:400]
    loc = _locality(given, address)
    if loc:
        project.locality = loc


def _apply_project(s: Session, row: dict[str, Any], source_url: str, today: date, tally: _Tally) -> str:
    parsed = parse_rera_number(_s(row.get("rera_no")))
    existing = s.scalar(select(Project).where(Project.rera_no == parsed.normalised)) if parsed else None
    before = _snap(existing) if existing else None
    rep = FileReport()
    _project(s, row, source_url, rep, today)
    tally.no_promoter += rep.no_promoter
    project = existing or s.scalar(select(Project).where(Project.rera_no == parsed.normalised))
    _extras(project, row)
    s.flush()
    if before is None:
        return "inserted"
    return "unchanged" if _snap(project) == before else "updated"


def _apply_agent(s: Session, row: dict[str, Any], source_url: str, today: date) -> str:
    parsed = parse_rera_number(_s(row.get("reg_no")))
    existing = s.scalar(select(Agent).where(Agent.reg_no == parsed.normalised)) if parsed else None
    before = _snap(existing) if existing else None
    _agent(s, row, source_url, today, FileReport())
    if before is None:
        return "inserted"
    return "unchanged" if _snap(existing) == before else "updated"


def _apply_update(s: Session, row: dict[str, Any], today: date) -> str:
    raw = _s(row.get("rera_no"))
    parsed = parse_rera_number(raw)
    if parsed is None or parsed.kind != "project":
        raise ValueError(f"unrecognised project registration number {raw!r}")
    project = s.scalar(select(Project).where(Project.rera_no == parsed.normalised))
    if project is None:
        raise ValueError(f"{parsed.normalised} is not in the registry: load the project record first")
    before = _snap(project)
    _extras(project, row)
    if _s(row.get("taluka")):
        project.taluka = _s(row.get("taluka"))[:80]
    if _s(row.get("project_type")):
        project.project_type = project_type(row.get("project_type"))
    if _s(row.get("units")):
        project.units = int(float(_s(row.get("units"))))
    revised = parse_date(row.get("revised_completion"))
    if revised:
        project.revised_completion = revised
        project.reg_valid_until = revised
    actual = parse_date(row.get("actual_completion"))
    if actual:
        project.actual_completion = actual
        project.status = "completed"
    status = _s(row.get("status")).lower()
    if status and not actual:
        project.status = ("revoked" if "revok" in status or "cancel" in status else "lapsed" if "laps" in status
                          else "completed" if "complet" in status else "ongoing")
    elif project.status == "unverified" and revised and revised >= today:
        project.status = "ongoing"  # an extension moved the date into the future
    name = _s(row.get("promoter_name"))
    if name:
        promoter = s.scalar(select(Promoter).where(func.lower(Promoter.name) == name.lower()))
        if promoter is None:
            promoter = Promoter(name=name[:200], district=project.district, source_url=project.source_url,
                                is_mock=False)
            s.add(promoter)
            s.flush()
        project.promoter_id = promoter.id
    s.flush()
    return "unchanged" if _snap(project) == before else "updated"


def _validate(kind: str, mapping: dict[str, str], headers: list[str]) -> dict[str, str]:
    if kind not in SPECS:
        raise ValueError(f"kind must be one of {', '.join(SPECS)}")
    spec = SPECS[kind]
    clean = {k: v for k, v in (mapping or {}).items() if v}
    bad = [k for k in clean if k not in spec]
    if bad:
        raise ValueError(f"unknown field(s): {', '.join(bad)}")
    missing_cols = [v for v in clean.values() if v not in headers]
    if missing_cols:
        raise ValueError(f"column(s) not in the file: {', '.join(missing_cols)}")
    missing = [LABELS.get(k, k) for k in REQUIRED[kind] if k not in clean]
    if kind == "project":
        if "proposed_completion" not in clean and "date_range" not in clean:
            missing.append("Proposed completion date (or Project dates)")
        if not {"reg_date", "start_date", "date_range"} & clean.keys():
            missing.append("Registration date (or Project start date / Project dates)")
    if missing:
        raise ValueError(f"match a column for: {', '.join(missing)}")
    return clean


def _apply_rows(s: Session, records: list[dict[str, Any]], clean: dict[str, str], kind: str, src: str,
                today: date, batch: int | None) -> tuple[_Tally, list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply each row in its own savepoint; with ``batch``, commit every ``batch`` rows so a long load never
    holds the database's write lock for long."""
    tally = _Tally()
    errors: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for i, rec in enumerate(records):
        n = i + 2  # row 1 is the header
        row = {canon: rec.get(col) for canon, col in clean.items()}
        try:
            with s.begin_nested():
                if kind == "project":
                    outcome = _apply_project(s, row, src, today, tally)
                elif kind == "agent":
                    outcome = _apply_agent(s, row, src, today)
                elif kind == "project_update":
                    outcome = _apply_update(s, row, today)
                else:
                    outcome = _internal.APPLY[kind](s, row)
            setattr(tally, outcome, getattr(tally, outcome) + 1)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            tally.rejected += 1
            msg = str(exc) or exc.__class__.__name__
            if len(errors) < MAX_ERRORS:
                errors.append({"row": n, "error": msg})
            rejected_rows.append({"row": n, "error": msg, **{str(h): _s(v) for h, v in rec.items()}})
        if batch and (i + 1) % batch == 0:
            s.commit()
        if i % 200 == 199:
            time.sleep(0.005)  # let other users' requests run during a long check or load
    return tally, errors, rejected_rows


def _check_on_copy(s: Session, fn):
    """Run ``fn(session)`` on a throw-away copy of a SQLite database, so a long check never blocks other
    users; on other databases run it in a transaction that is rolled back."""
    bind = s.get_bind()
    db = bind.url.database
    if bind.dialect.name != "sqlite" or not db or db == ":memory:":
        s.commit()
        try:
            return fn(s)
        finally:
            s.rollback()
    import sqlite3

    from gujrera.db.session import make_engine, session_factory

    copy = uploads_dir(s) / f"check-{uuid.uuid4().hex}.sqlite"
    src = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(copy)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    engine = make_engine(f"sqlite:///{copy.as_posix()}")
    try:
        with session_factory(engine)() as cs:
            return fn(cs)
    finally:
        engine.dispose()
        for f in copy.parent.glob(copy.name + "*"):
            f.unlink(missing_ok=True)


def run_import(repo: Repository, run_id: str, *, sheet: str | None, kind: str, mapping: dict[str, str],
               source_url: str | None = None, commit: bool, today: date | None = None) -> dict[str, Any]:
    """Check (on a copy, nothing saved) or load (committed in batches) every row of one sheet.
    Returns counts and the reason each rejected row failed."""
    require_admin(repo)
    run = _get_run(repo, run_id)
    sheets = _sheets(_stored(repo.s, run), run.filename)
    name, records = next(((n, r) for n, r in sheets if n == sheet), sheets[0])
    clean = _validate(kind, mapping, _headers(records))
    today = today or date.today()
    src = (source_url or "").strip() or DEFAULT_SOURCE
    s = repo.s
    if commit:
        s.commit()
        tally, errors, rejected_rows = _apply_rows(s, records, clean, kind, src, today, batch=500)
        s.commit()
        from gujrera.chat import understand

        understand._INDEX.clear()  # answer from the new names at once
        (uploads_dir(s) / f"{run.id}.rejected.json").write_text(json.dumps(rejected_rows, ensure_ascii=False),
                                                                 encoding="utf-8")
    else:
        tally, errors, rejected_rows = _check_on_copy(
            s, lambda cs: _apply_rows(cs, records, clean, kind, src, today, batch=None))
    run = _get_run(repo, run_id)
    run.kind, run.sheet, run.rows = kind, name, len(records)
    run.inserted, run.updated, run.unchanged, run.rejected = tally.inserted, tally.updated, tally.unchanged, tally.rejected
    run.mapping_json = json.dumps(clean, ensure_ascii=False)
    if commit:
        run.status, run.loaded_by, run.loaded_at = "loaded", _username(repo), datetime.now()
    elif run.status != "loaded":
        run.status = "checked"
    s.commit()
    repo._audit("data_load" if commit else "data_check",
                {"run": run.id, "file": run.filename, "kind": kind, "rows": len(records), "inserted": tally.inserted,
                 "updated": tally.updated, "rejected": tally.rejected})
    sample_new = []
    if commit and kind == "project" and tally.inserted:
        sample_new = [p.name for p in s.scalars(select(Project).where(Project.source_url == src)
                                                .order_by(Project.id.desc()).limit(3))]
    return {"run": _run_dict(run), "saved": commit, "rows": len(records), "inserted": tally.inserted,
            "updated": tally.updated, "unchanged": tally.unchanged, "rejected": tally.rejected,
            "no_promoter": tally.no_promoter, "errors": errors, "errors_truncated": tally.rejected > len(errors),
            "sample_new": sample_new}


# ------------------------------------------------------------------ history and rejected rows
def _run_dict(run: ImportRun) -> dict[str, Any]:
    return {"id": run.id, "filename": run.filename, "size_bytes": run.size_bytes, "status": run.status,
            "kind": run.kind, "kind_label": KIND_LABELS.get(run.kind or "", None), "sheet": run.sheet,
            "rows": run.rows, "inserted": run.inserted, "updated": run.updated, "unchanged": run.unchanged,
            "rejected": run.rejected, "uploaded_by": run.uploaded_by,
            "uploaded_at": run.uploaded_at.isoformat(timespec="minutes"), "loaded_by": run.loaded_by,
            "loaded_at": run.loaded_at.isoformat(timespec="minutes") if run.loaded_at else None}


def history(repo: Repository, limit: int = 50) -> dict[str, Any]:
    require_admin(repo)
    runs = repo.s.scalars(select(ImportRun).order_by(ImportRun.uploaded_at.desc()).limit(limit)).all()
    totals = {"projects": repo.s.scalar(select(func.count()).select_from(Project)),
              "agents": repo.s.scalar(select(func.count()).select_from(Agent)),
              "with_address": repo.s.scalar(select(func.count()).select_from(Project).where(Project.address.is_not(None))),
              "with_locality": repo.s.scalar(select(func.count()).select_from(Project).where(Project.locality.is_not(None)))}
    return {"runs": [_run_dict(r) for r in runs], "registry": totals}


def rejected_csv(repo: Repository, run_id: str) -> tuple[str, str]:
    require_admin(repo)
    run = _get_run(repo, run_id)
    path = uploads_dir(repo.s) / f"{run.id}.rejected.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    out = io.StringIO()
    if rows:
        cols = list(dict.fromkeys(k for r in rows for k in r))
        w = csv.DictWriter(out, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    else:
        out.write("row,error\n")
    stem = Path(run.filename).stem
    return f"{stem}_rejected.csv", out.getvalue()


__all__ = ["upload", "describe", "run_import", "history", "rejected_csv", "require_admin", "SPECS", "district_name"]
