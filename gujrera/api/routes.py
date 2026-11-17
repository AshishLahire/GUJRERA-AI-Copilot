"""HTTP endpoints for the GUJRERA copilot, mounted on the Pramaan FastAPI app.

Trust check:
    GET  /api/gujrera/health
    GET  /api/gujrera/trust/samples        demo ads built from the registry
    POST /api/gujrera/trust/text           {"text": "..."}
    POST /api/gujrera/trust/upload         multipart: file (PNG/JPG/PDF)

The trust check only reads public registry data, so it runs as an anonymous
citizen. Uploaded files are deleted after reading.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import Session

from gujrera.db.models import Project
from gujrera.db.repository import Principal, Repository
from gujrera.db.session import make_engine, session_factory
from gujrera.trust.checks import check_text
from gujrera.trust.samples import demo_samples

REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = REPO_ROOT / "data" / "raw" / "gujrera_uploads"
MAX_TEXT_CHARS = 5000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}


class TrustTextRequest(BaseModel):
    text: str


@lru_cache
def _engine() -> Engine:
    return make_engine()


def get_session() -> Iterator[Session]:
    engine = _engine()
    if not inspect(engine).has_table("projects"):
        raise HTTPException(503, "GUJRERA database is empty. Run: python scripts/seed_gujrera.py")
    with session_factory(engine)() as session:
        yield session
        session.commit()  # keeps the audit log


def citizen_repo(session: Session = Depends(get_session)) -> Repository:
    return Repository(session, Principal.anonymous())


router = APIRouter(prefix="/api/gujrera", tags=["gujrera"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(Project))
    mock = session.scalar(select(func.count()).select_from(Project).where(Project.is_mock.is_(True)))
    return {"status": "ok", "projects": total, "mock_projects": mock}


@router.get("/trust/samples")
def trust_samples(session: Session = Depends(get_session)) -> dict[str, Any]:
    items = [
        {"id": c.id, "kind": c.kind, "lang": c.lang, "label": c.note, "text": c.text, "expected": list(c.expected)}
        for c in demo_samples(session)
    ]
    return {"count": len(items), "items": items, "is_mock": True}


@router.post("/trust/text")
def trust_text(body: TrustTextRequest, repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "Please paste the text of the ad or message.")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(400, f"Text exceeds the {MAX_TEXT_CHARS:,}-character limit.")
    return check_text(text, repo).to_dict()


@router.post("/trust/upload")
async def trust_upload(
    file: UploadFile = File(...),
    allow_fallback: bool = Form(default=False),
    repo: Repository = Depends(citizen_repo),
) -> dict[str, Any]:
    from gujrera.trust.service import check_document

    ext = Path(file.filename or "upload").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Unsupported file type. Allowed: PNG, JPG, WEBP, PDF.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File exceeds the 10 MB size limit.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    try:
        return check_document(path, repo, allow_cloud=allow_fallback)
    finally:
        for leftover in UPLOAD_DIR.glob(f"{path.stem}*"):
            leftover.unlink(missing_ok=True)
