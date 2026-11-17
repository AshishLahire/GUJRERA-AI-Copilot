"""GUJRERA data foundation: schema, views, mock data, access control, CSV import."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from gujrera.db.models import AuditLog, Complaint, DueNotice, Project, Promoter, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import init_db, make_engine, make_readonly_engine, session_factory
from gujrera.ingest.csv_import import import_projects_csv
from gujrera.ingest.mock_generator import MockConfig, generate


def _build(path: Path, seed: int = 7):
    url = f"sqlite:///{path.as_posix()}"
    engine = make_engine(url)
    init_db(engine, drop=True)
    Session = session_factory(engine)
    with Session() as s:
        counts = generate(s, MockConfig(seed=seed))
    return url, engine, Session, counts


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    url, engine, Session, counts = _build(tmp_path_factory.mktemp("gujrera") / "g.sqlite")
    yield url, engine, Session, counts
    engine.dispose()


@pytest.fixture
def session(db):
    _, _, Session, _ = db
    with Session() as s:
        yield s
        s.rollback()


def _user(s, username):
    return Principal.from_user(s.scalar(select(User).where(User.username == username)))


# ------------------------------------------------------------------ mock data
def test_generation_is_reproducible(tmp_path, db):
    _, _, Session2, counts2 = _build(tmp_path / "again.sqlite")
    assert counts2 == db[3]
    with db[2]() as a, Session2() as b:
        q = select(Project.rera_no, Project.status, Project.proposed_completion).order_by(Project.id)
        assert a.execute(q).all() == b.execute(q).all()


def test_every_mock_row_is_labelled(session):
    assert session.scalar(select(func.count()).select_from(Project).where(Project.is_mock.is_(False))) == 0
    assert all("/MOCK" in r for r in session.scalars(select(Project.rera_no)))
    assert all(n.endswith("(Demo)") for n in session.scalars(select(Promoter.name)))


def test_volumes_are_demo_sized(db):
    counts = db[3]
    assert counts["promoters"] == 60
    assert 120 <= counts["projects"] <= 260
    assert counts["complaints"] > 100


# ---------------------------------------------------------------------- views
def test_views_are_consistent(session):
    total_projects = session.scalar(select(func.count()).select_from(Project))
    assert session.scalar(text("SELECT SUM(projects) FROM v_promoter_scorecard")) == total_projects
    assert session.scalar(text("SELECT MIN(delay_days) FROM v_project_delays")) >= 0
    delayed = session.scalar(text("SELECT COUNT(*) FROM v_project_delays WHERE is_delayed = 1"))
    assert 0 < delayed < total_projects
    open_ = session.scalar(text("SELECT SUM(is_open) FROM v_complaint_stats"))
    assert open_ == session.scalar(select(func.count()).select_from(Complaint).where(
        Complaint.status.in_(["filed", "under_scrutiny", "hearing_scheduled", "order_reserved"])))


def test_analytics_views_hide_complainant_identity(session):
    cols = session.execute(text("SELECT * FROM v_complaint_stats LIMIT 1")).keys()
    assert not {"complainant_user_id", "complainant_hash"} & set(cols)


def test_readonly_engine_cannot_write(db):
    ro = make_readonly_engine(db[0])
    try:
        with ro.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM v_project_delays")).scalar() > 0
            with pytest.raises(OperationalError):
                conn.execute(text("DELETE FROM projects"))
    finally:
        ro.dispose()


# --------------------------------------------------------- public lookups
def test_project_lookup_tolerates_noise(session):
    project = session.scalars(select(Project)).first()
    repo = Repository(session, Principal.anonymous())
    noisy = project.rera_no.lower().replace("/", " / ")
    found = repo.get_project(noisy)
    assert found["rera_no"] == project.rera_no
    assert found["source"] == {"type": "project", "id": project.rera_no, "is_mock": True}
    assert "delay_days" in found and "promoter_name" in found


def test_unknown_project_returns_none(session):
    repo = Repository(session, Principal.anonymous())
    assert repo.get_project("PR/GJ/SURAT/SURAT CITY/SUDA/RAA99999/010120") is None


def test_fuzzy_search_in_gujarati_and_english(session):
    promoter = session.scalars(select(Promoter)).first()
    repo = Repository(session, Principal.anonymous())
    assert repo.search_promoters(promoter.name.replace(" (Demo)", "").lower())[0]["id"] == promoter.id
    assert repo.search_promoters(promoter.name_gu)[0]["id"] == promoter.id
    assert repo.search_promoters("zzqx unrelated words") == []


# ------------------------------------------------------------- access control
def _promoter_with_dues(s, other_than=None):
    stmt = select(DueNotice.promoter_id).distinct()
    if other_than:
        stmt = stmt.where(DueNotice.promoter_id != other_than)
    return s.scalars(stmt).first()


def test_developer_sees_only_own_dues(session):
    pid = _promoter_with_dues(session)
    dev = _user(session, f"dev_{pid:03d}")
    repo = Repository(session, dev)
    rows = repo.dues_notices()
    assert rows and {r["promoter_id"] for r in rows} == {pid}
    other = _promoter_with_dues(session, other_than=pid)
    with pytest.raises(AccessDenied):
        repo.dues_notices(other)


@pytest.mark.parametrize("role_user", ["citizen_01", "agent"])
def test_citizens_and_agents_cannot_see_dues(session, role_user):
    if role_user == "agent":
        principal = Principal.from_user(session.scalar(select(User).where(User.role == "agent")))
    else:
        principal = _user(session, role_user)
    with pytest.raises(AccessDenied):
        Repository(session, principal).dues_notices()


def test_district_officer_scope(session):
    officer = _user(session, "officer_surat")
    complaints = Repository(session, officer).list_complaints(limit=1000)
    assert complaints and {c["district"] for c in complaints} == {"Surat"}
    dues = Repository(session, officer).dues_notices()
    districts = {session.get(Promoter, d["promoter_id"]).district for d in dues}
    assert districts <= {"Surat"}
    state = Repository(session, _user(session, "officer_state")).list_complaints(limit=10000)
    assert len(state) == session.scalar(select(func.count()).select_from(Complaint))


def test_developer_complaints_hide_complainant(session):
    pid = session.scalars(select(Complaint.promoter_id)).first()
    rows = Repository(session, _user(session, f"dev_{pid:03d}")).list_complaints()
    assert rows and {r["promoter_id"] for r in rows} == {pid}
    assert all("complainant_user_id" not in r and "complainant_hash" not in r for r in rows)


def test_citizen_tracks_only_own_complaint(session):
    mine = session.scalars(select(Complaint).where(Complaint.complainant_user_id.is_not(None))).first()
    owner = Principal.from_user(session.get(User, mine.complainant_user_id))
    status = Repository(session, owner).complaint_status(mine.ref_no.lower())
    assert status["ref_no"] == mine.ref_no and status["events"][0]["status"] == "filed"
    assert "complainant_hash" not in status

    other = session.scalars(select(Complaint).where(
        (Complaint.complainant_user_id != owner.user_id) | Complaint.complainant_user_id.is_(None))).first()
    with pytest.raises(AccessDenied):
        Repository(session, owner).complaint_status(other.ref_no)
    assert Repository(session, owner).complaint_status("DEMO-CMP-1999-99999") is None
    assert Repository(session, Principal.anonymous()).list_complaints() == []


def test_private_reads_are_audited(session):
    before = session.scalar(select(func.count()).select_from(AuditLog))
    pid = _promoter_with_dues(session)
    Repository(session, _user(session, f"dev_{pid:03d}")).dues_notices()
    assert session.scalar(select(func.count()).select_from(AuditLog)) == before + 1


# ----------------------------------------------------------------- CSV import
CSV_HEADER = ("rera_no,project_name,project_name_gu,promoter_name,promoter_name_gu,district,taluka,"
              "planning_authority,project_type,status,units,reg_date,proposed_completion,"
              "revised_completion,actual_completion,source_url\n")


def test_csv_import(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'csv.sqlite').as_posix()}")
    init_db(engine)
    csv_path = tmp_path / "public.csv"
    csv_path.write_text(
        CSV_HEADER
        + "pr/gj/surat/olpad/suda/RAA11111/010122,Test Homes,,Test Promoter,,Surat,Olpad,SUDA,"
          "residential,ongoing,120,2022-01-01,2025-12-31,2027-06-30,,https://example.invalid/p/1\n"
        + "PR/GJ/SURAT/OLPAD/SUDA/MOCK00001/010122,Bad,,X,,Surat,,,residential,ongoing,1,"
          "2022-01-01,2025-01-01,,,https://example.invalid/p/2\n"
        + "PR/GJ/SURAT/OLPAD/SUDA/RAA22222/010122,No Source,,X,,Surat,,,residential,ongoing,1,"
          "2022-01-01,2025-01-01,,,\n",
        encoding="utf-8",
    )
    with session_factory(engine)() as s:
        rep = import_projects_csv(s, csv_path)
        assert rep.inserted == 1 and len(rep.errors) == 2
        p = s.scalar(select(Project))
        assert p.rera_no == "PR/GJ/SURAT/OLPAD/SUDA/RAA11111/010122"
        assert p.is_mock is False and p.promoter.is_mock is False
        assert p.reg_valid_until.isoformat() == "2027-06-30"
        rep2 = import_projects_csv(s, csv_path)
        assert rep2.inserted == 0 and rep2.updated == 1
    engine.dispose()
