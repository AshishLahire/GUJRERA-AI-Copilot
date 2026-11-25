"""Data onboarding console: upload, column matching, check (saves nothing), load, history, rejected rows."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gujrera.api.routes import get_session, router
from gujrera.db.models import Project
from gujrera.db.session import init_db, make_engine, session_factory
from gujrera.enforcement import ensure_tables
from gujrera.ingest.mock_generator import MockConfig, generate

NEW_1 = "PR/GJ/AHMEDABAD/DASKROI/AUDA/RAA77001/010124"
NEW_2 = "PR/GJ/SURAT/SURAT CITY/SUDA/RAA77002/150224"
PROJECTS_CSV = (
    "Registration No,Project Name,Promoter Name,District,Project Type,Registration Date,Completion Date,Site Address,Phone\n"
    f"{NEW_1},Saathi Heights,Saathi Developers,Ahmedabad,Residential/Group Housing,01/01/2024,31/12/2027,"
    "\"Near Shela Road, Bopal, Ahmedabad\",9876543210\n"
    f"{NEW_2},Tapi Arcade,Tapi Infra,Surat,Commercial,15/02/2024,30/06/2027,\"Ring Road, Surat\",9876500000\n"
    "PR/GJ/SURAT/SURAT CITY/SUDA/RAA77003/150224,Bad Date Tower,X,Surat,Residential,31/31/2024,30/06/2027,,\n"
    "PR/GJ/SURAT/SURAT CITY/SUDA/MOCK00001/150224,Mock Tower,X,Surat,Residential,15/02/2024,30/06/2027,,\n"
)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    path: Path = tmp_path_factory.mktemp("onb") / "d.sqlite"
    engine = make_engine(f"sqlite:///{path.as_posix()}")
    init_db(engine)
    ensure_tables(engine)
    factory = session_factory(engine)
    with factory() as s:
        generate(s, MockConfig())
        s.commit()
    app = FastAPI()
    app.include_router(router)

    def _session():
        with factory() as session:
            yield session
            session.commit()

    app.dependency_overrides[get_session] = _session
    c = TestClient(app)
    c.factory = factory
    c.dir = path.parent
    yield c
    engine.dispose()


def _auth(c, user):
    tok = c.post("/api/gujrera/auth/login", json={"username": user, "password": "gujrera-demo"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _count(c):
    with c.factory() as s:
        return s.scalar(select(func.count()).select_from(Project))


def _upload(c, h, name, text):
    r = c.post("/api/gujrera/admin/imports", files={"file": (name, text.encode())}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_only_state_officers_can_load_data(client):
    files = {"file": ("p.csv", PROJECTS_CSV.encode())}
    assert client.post("/api/gujrera/admin/imports", files=files).status_code == 403
    for user in ("citizen_01", "officer_surat", "dev_002"):
        assert client.post("/api/gujrera/admin/imports", files=files, headers=_auth(client, user)).status_code == 403
        assert client.get("/api/gujrera/admin/imports", headers=_auth(client, user)).status_code == 403


def test_upload_check_load_and_answer(client):
    h = _auth(client, "officer_state")
    up = _upload(client, h, "department_projects.csv", PROJECTS_CSV)
    sheet = up["sheets"][0]
    assert sheet["name"] == "department_projects.csv" and sheet["rows"] == 4 and sheet["suggested_kind"] == "project"
    mapping = sheet["kinds"]["project"]["mapping"]
    assert mapping["rera_no"] == "Registration No" and mapping["address"] == "Site Address"
    assert "Phone" in sheet["kinds"]["project"]["unused"]  # personal data is never read
    body = {"sheet": sheet["name"], "kind": "project", "mapping": mapping}
    run = up["run"]["id"]

    before = _count(client)
    chk = client.post(f"/api/gujrera/admin/imports/{run}/check", json=body, headers=h).json()
    assert (chk["inserted"], chk["rejected"], chk["saved"]) == (2, 2, False)
    assert {e["row"] for e in chk["errors"]} == {4, 5}
    assert "MOCK" in next(e["error"] for e in chk["errors"] if e["row"] == 5)
    assert _count(client) == before  # a check saves nothing

    ld = client.post(f"/api/gujrera/admin/imports/{run}/load", json=body, headers=h).json()
    assert (ld["inserted"], ld["rejected"], ld["saved"]) == (2, 2, True)
    assert _count(client) == before + 2
    with client.factory() as s:
        p = s.scalar(select(Project).where(Project.rera_no == NEW_1))
        assert p.name == "Saathi Heights" and p.locality == "Bopal" and "Shela Road" in p.address

    # the assistants answer from the new record at once
    reply = client.post("/api/gujrera/chat", json={"message": "When will I get possession of Saathi Heights?"}).json()
    assert "Saathi Heights" in reply["text"] or "2027" in reply["text"]

    # loading the same file again changes nothing
    again = client.post(f"/api/gujrera/admin/imports/{run}/load", json=body, headers=h).json()
    assert (again["inserted"], again["updated"], again["unchanged"]) == (0, 0, 2)

    hist = client.get("/api/gujrera/admin/imports", headers=h).json()
    top = hist["runs"][0]
    assert top["status"] == "loaded" and top["loaded_by"] == "officer_state" and top["rejected"] == 2
    rej = client.get(f"/api/gujrera/admin/imports/{run}/rejected", headers=h)
    assert rej.status_code == 200 and "31/31/2024" in rej.text and rej.text.count("\n") == 3


def test_project_update_adds_addresses_to_existing_projects(client):
    h = _auth(client, "officer_state")
    csv_text = (f"RERA No,Site Address\n{NEW_2},\"Plot 4, Vesu, Surat\"\n"
                "PR/GJ/SURAT/SURAT CITY/SUDA/RAA77999/150224,Somewhere\n")
    up = _upload(client, h, "addresses.csv", csv_text)
    sheet = up["sheets"][0]
    assert sheet["suggested_kind"] == "project_update"
    body = {"sheet": sheet["name"], "kind": "project_update", "mapping": sheet["kinds"]["project_update"]["mapping"]}
    ld = client.post(f"/api/gujrera/admin/imports/{up['run']['id']}/load", json=body, headers=h).json()
    assert (ld["updated"], ld["rejected"]) == (1, 1) and "not in the registry" in ld["errors"][0]["error"]
    with client.factory() as s:
        assert s.scalar(select(Project.locality).where(Project.rera_no == NEW_2)) == "Vesu"


def test_bad_files_and_mappings_are_refused(client):
    h = _auth(client, "officer_state")
    assert client.post("/api/gujrera/admin/imports", files={"file": ("x.exe", b"MZ")}, headers=h).status_code == 400
    assert client.post("/api/gujrera/admin/imports", files={"file": ("x.csv", b"")}, headers=h).status_code == 400
    up = _upload(client, h, "p.csv", PROJECTS_CSV)
    run = up["run"]["id"]
    no_name = {"kind": "project", "mapping": {"rera_no": "Registration No"}}
    r = client.post(f"/api/gujrera/admin/imports/{run}/check", json=no_name, headers=h)
    assert r.status_code == 400 and "Project name" in r.json()["detail"]
    ghost = {"kind": "project", "mapping": {"rera_no": "No Such Column", "project_name": "Project Name"}}
    assert client.post(f"/api/gujrera/admin/imports/{run}/check", json=ghost, headers=h).status_code == 400
    assert client.get("/api/gujrera/admin/imports/" + "0" * 32, headers=h).status_code == 400
