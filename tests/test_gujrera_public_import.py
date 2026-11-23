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
        assert [(r.sheet, r.kind, r.inserted) for r in reports] == [("Projects", "project", 3), ("Agents", "agent", 1)]
        proj = reports[0]
        assert len(proj.errors) == 1 and "row 4" in proj.errors[0] and "MOCK" in proj.errors[0]
        assert proj.no_promoter == 1  # row 5 is kept, under the "not in imported records" placeholder
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
        ["AG/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/X90003/010124", "Ravi Patel", "01/01/2024", "31/12/2028"]]})
    with Session() as s:
        (rep,) = import_file(s, path, source_url="https://gujrera.gujarat.gov.in/#/")
        assert rep.inserted == 1 and len(rep.warnings) == 1 and "unexpected code" in rep.warnings[0]


def test_portal_search_results_are_imported_safely(Session, tmp_path):
    """Shape of the portal's public search response: mixed entity types, 'pdate' ranges, no promoter or status."""
    from gujrera.db.repository import Principal, Repository
    from gujrera.ingest.public_import import UNKNOWN_PROMOTER
    from gujrera.profile.summarise import project_profile
    from gujrera.trust.checks import check_text

    new = "PR/GJ/GANDHINAGAR/GANDHINAGAR/Gandhinagar Municipal Corporation/MAA90010/301124/311228"
    old = "PR/GJ/GANDHINAGAR/KALOL/AUDA/PAA90011/280917"
    rows = [
        {"entityType": "PROJECT", "regNo": new, "entityName": " SKYVIEW TEST", "distName": "Gandhinagar",
         "taluka": "Gandhinagar", "ptype": "Mixed Development", "pdate": "02/08/2024 - 30/04/2029"},
        {"entityType": "PROJECT", "regNo": old, "entityName": "OLD TEST HOMES", "distName": "Gandhinagar",
         "taluka": "Kalol", "ptype": "Residential/Group Housing", "pdate": "28/09/2017 - 31/03/2021"},
        {"entityType": "PROMOTER", "regNo": "", "entityName": "Someone", "mobileNo": "9999999999",
         "emailId": "x@example.invalid", "pdate": ""},
    ]
    path = tmp_path / "search.json"
    path.write_text(json.dumps({"status": 200, "data": rows}), encoding="utf-8")
    with Session() as s:
        (rep,) = import_file(s, path, source_url="https://gujrera.gujarat.gov.in/#/", today=date(2026, 11, 23))
        assert rep.kind == "project" and rep.rows == 2 and rep.inserted == 2 and not rep.errors
        assert rep.no_promoter == 2
        assert s.scalar(select(Promoter)).name == UNKNOWN_PROMOTER  # the promoter row's details are never stored
        p_new = s.scalar(select(Project).where(Project.rera_no.like("%MAA90010%")))
        p_old = s.scalar(select(Project).where(Project.rera_no.like("%PAA90011%")))
        assert (p_new.status, p_new.reg_date, p_new.proposed_completion) == ("ongoing", date(2024, 8, 2), date(2029, 4, 30))
        assert p_old.status == "unverified" and p_new.name == "SKYVIEW TEST"

        repo = Repository(s, Principal.anonymous())
        assert repo.get_project_by_id(p_old.id)["delay_days"] == 0  # no delay claimed without a completion record
        text = " ".join(x.text for x in project_profile(repo, p_old.id, "en").sentences)
        assert "do not show whether the project was completed" in text and "behind" not in text
        report = check_text(f"OLD TEST HOMES by Some Builder, Kalol. RERA {old}", repo, as_of=date(2026, 11, 23))
        checks = {c.id: c for c in report.checks}
        assert checks["registration_valid"].status == "info" and checks["promoter_match"].status == "info"
        assert "delay" not in checks and report.verdict != "lapsed_or_revoked"

        # Gujarati question about an English-only registry name; no "by <placeholder>" in the summary
        from gujrera.chat.orchestrator import ChatState, respond
        out = respond("સ્કાયવ્યુ ટેસ્ટ નું પઝેશન ક્યારે મળશે?", ChatState(), repo).to_dict()
        assert out["intent"] == "possession" and out["sources"][0]["id"].endswith("/MAA90010/301124/311228")
        intro = respond(f"Tell me about {old}", ChatState(), repo).to_dict()["text"]
        assert "OLD TEST HOMES" in intro and UNKNOWN_PROMOTER not in intro
        listing = respond("Show me projects in Gandhinagar", ChatState(), repo).to_dict()["text"]
        assert "completion not recorded" in listing and "lapsed" not in listing


def test_sample_ads_are_not_made_from_real_records(Session, tmp_path):
    """The ad page's sample picker must load on imported public data (no fake ads about real builders)."""
    from gujrera.trust.samples import demo_samples

    path = tmp_path / "one.json"
    path.write_text(json.dumps({"data": [{"entityType": "PROJECT", "regNo": P1, "entityName": "X Test",
                                           "pdate": "01/01/2023 - 31/12/2029"}]}), encoding="utf-8")
    with Session() as s:
        import_file(s, path, source_url="https://gujrera.gujarat.gov.in/#/")
        assert demo_samples(s) == []
