"""Importing public GUJRERA records from downloaded CSV, Excel and JSON files.

The registration numbers below are made-up test values in the real format (not MOCK numbers,
which the importer refuses); they exist only in these temporary test databases.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from gujrera.db.models import Agent, Project, Promoter
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.ingest.public_import import (
    import_file,
    parse_date,
    project_status,
    project_type,
)

ROOT = Path(__file__).resolve().parents[1]
P1 = "PR/GJ/GANDHINAGAR/GANDHINAGAR/GUDA/RAA90001/010123"
P2 = "PR/GJ/SURAT/OLPAD/SUDA/RAA90002/150622"
A1 = "AG/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/AAA90003/010124"


@pytest.fixture
def Session(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'pub.sqlite').as_posix()}")
    init_db(engine)
    yield session_factory(engine)
    engine.dispose()


def _xlsx(path: Path, sheets: dict[str, list[list]]) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    wb.save(path)
    return path


def test_parsing_helpers():
    assert parse_date("31/12/2027") == date(2027, 12, 31)
    assert parse_date("2027-12-31") == date(2027, 12, 31)
    assert parse_date(datetime(2027, 12, 31, 10, 0)) == date(2027, 12, 31)
    assert parse_date(int(datetime(2027, 12, 31, tzinfo=UTC).timestamp() * 1000)) == date(2027, 12, 31)
    assert parse_date(46387) == date(2026, 12, 31)  # Excel serial day
    assert parse_date("") is None
    with pytest.raises(ValueError, match="dd/mm/yyyy"):
        parse_date("sometime next year")
    assert [project_type(t) for t in ("Residential/Group Housing", "Plotted Development", "Mixed Development",
                                      "Commercial", "")] == ["residential", "plotted", "mixed", "commercial", "residential"]
    assert project_status("", date(2024, 1, 1)) == "completed" and project_status("", None) == "ongoing"
    assert project_status("Registration Lapsed", None) == "lapsed"


def test_excel_with_portal_columns_projects_and_agents(Session, tmp_path):
    path = _xlsx(tmp_path / "download.xlsx", {
        "Projects": [
            ["Project Registration No", "Project Name", "Promoter Name", "District", "Project Type",
             "Project Start Date", "Project End Date", "Total Units", "Extra column"],
            [P1, "Shanti Residency", "Shanti Developers", "", "Residential/Group Housing", "01/01/2023",
             "31/12/2027", 120, "x"],
            [P2, "Olpad Plots", "Olpad Infra", "Surat", "Plotted Development", "15/06/2022", "30/06/2025", "", ""],
            ["PR/GJ/SURAT/OLPAD/SUDA/MOCK00001/010122", "Fake", "X", "Surat", "", "01/01/2022", "01/01/2025", "", ""],
            ["PR/GJ/SURAT/OLPAD/SUDA/RAA90004/010122", "No promoter", "", "Surat", "", "01/01/2022", "01/01/2025", "", ""],
        ],
        "Agents": [
            ["Agent Registration No", "Agent Name", "Registration Date", "Valid Upto"],
            [A1, "Ravi Patel", "01/01/2024", "31/12/2028"],
        ],
        "How to fill": [["Some instructions"], ["more text"]],
    })
    with Session() as s:
        reports = import_file(s, path, source_url="https://gujrera.gujarat.gov.in/#/")
        assert [(r.sheet, r.kind, r.inserted) for r in reports] == [("Projects", "project", 2), ("Agents", "agent", 1)]
        proj = reports[0]
        assert len(proj.errors) == 2 and "row 4" in proj.errors[0] and "MOCK" in proj.errors[0]
        assert "row 5" in proj.errors[1] and "promoter_name" in proj.errors[1]
        assert proj.unmatched_columns == ["Extra column"]

        p = s.scalar(select(Project).where(Project.rera_no == P1))
        assert p.name == "Shanti Residency" and p.district == "Gandhinagar"  # district read from the number
        assert p.reg_date == date(2023, 1, 1) and p.proposed_completion == date(2027, 12, 31)
        assert p.project_type == "residential" and p.status == "ongoing" and p.units == 120
        assert p.is_mock is False and p.promoter.is_mock is False and p.source_url.startswith("https://gujrera")
        assert s.scalar(select(Project).where(Project.rera_no == P2)).project_type == "plotted"
        assert not proj.warnings
        a = s.scalar(select(Agent))
        assert a.reg_no == A1 and a.status == "active" and a.district == "Ahmedabad" and a.is_mock is False


def test_json_feed_with_millisecond_dates_and_reimport_updates(Session, tmp_path):
    ms = lambda d: int(datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp() * 1000)
    rows = [{"projectRegNo": P1, "projectName": "Shanti Residency", "promoterName": "Shanti Developers",
             "projectType": "Mixed Development", "projectStartDate": ms(date(2023, 1, 1)),
             "projectEndDate": ms(date(2027, 12, 31)), "url": "https://gujrera.gujarat.gov.in/#/p/1"}]
    path = tmp_path / "feed.json"
    path.write_text(json.dumps({"status": "ok", "data": rows}), encoding="utf-8")
    with Session() as s:
        (rep,) = import_file(s, path)
        assert rep.inserted == 1 and not rep.errors
        rows[0]["projectName"] = "Shanti Residency Phase 1"
        path.write_text(json.dumps({"data": rows}), encoding="utf-8")
        (rep,) = import_file(s, path)
        assert rep.updated == 1 and rep.inserted == 0
        p = s.scalar(select(Project))
        assert p.name == "Shanti Residency Phase 1" and p.project_type == "mixed"
        assert p.source_url == "https://gujrera.gujarat.gov.in/#/p/1"
        assert s.scalar(select(Promoter)).name == "Shanti Developers"


def test_semicolon_csv_needs_a_source(Session, tmp_path):
    path = tmp_path / "list.csv"
    path.write_text("RERA No;Name of Project;Developer;End Date;Registration Date\n"
                    f"{P2};Olpad Plots;Olpad Infra;30-06-2025;15-06-2022\n", encoding="utf-8")
    with Session() as s:
        (rep,) = import_file(s, path)  # no URL column and no default source
        assert rep.inserted == 0 and "source_url" in rep.errors[0]
        (rep,) = import_file(s, path, source_url="https://gujrera.gujarat.gov.in/#/")
        assert rep.inserted == 1 and s.scalar(select(Project)).district == "Surat"


def test_script_builds_separate_database_with_logins(tmp_path):
    src = _xlsx(tmp_path / "p.xlsx", {"Projects": [
        ["Project Registration No", "Project Name", "Promoter Name", "Project Start Date", "Project End Date"],
        [P1, "Shanti Residency", "Shanti Developers", "01/01/2023", "31/12/2027"]]})
    db = tmp_path / "public.sqlite"
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_gujrera_public.py"), str(src), "--db", str(db)],
                         capture_output=True, text=True, cwd=ROOT, encoding="utf-8", check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "1 added" in out.stdout and "officer_state" in out.stdout and "officer_gandhinagar" in out.stdout
    demo = subprocess.run([sys.executable, str(ROOT / "scripts" / "import_gujrera_public.py"), str(src), "--db",
                           str(ROOT / "data" / "gujrera" / "gujrera.sqlite")], capture_output=True, text=True, cwd=ROOT, check=False)
    assert demo.returncode == 2 and "Refusing" in demo.stdout


def test_template_columns_are_all_understood(Session):
    wb = load_workbook(ROOT / "gujrera" / "ingest" / "public_records_template.xlsx", read_only=True)
    from gujrera.ingest.public_import import AGENT_COLUMNS, PROJECT_COLUMNS, _column_map
    proj = [c for c in next(wb["Projects"].iter_rows(values_only=True))]
    agent = [c for c in next(wb["Agents"].iter_rows(values_only=True))]
    wb.close()
    assert _column_map(proj, PROJECT_COLUMNS)[1] == [] and _column_map(agent, AGENT_COLUMNS)[1] == []


def test_unexpected_number_format_is_imported_with_a_note(Session, tmp_path):
    path = _xlsx(tmp_path / "a.xlsx", {"Agents": [
        ["Agent Registration No", "Agent Name", "Registration Date", "Valid Upto"],
        ["AG/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/AA90003/010124", "Ravi Patel", "01/01/2024", "31/12/2028"]]})
    with Session() as s:
        (rep,) = import_file(s, path, source_url="https://gujrera.gujarat.gov.in/#/")
        assert rep.inserted == 1 and len(rep.warnings) == 1 and "unexpected code" in rep.warnings[0]
