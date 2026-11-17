"""HTTP endpoints for the GUJRERA copilot, mounted on the Pramaan FastAPI app.

Login and self-service (send "Authorization: Bearer <token>"):
    POST /api/gujrera/auth/login           {"username": "...", "password": "..."}
    GET  /api/gujrera/auth/me
    GET  /api/gujrera/self-service/summary?lang=gu   promoter or agent compliance summary
    POST /api/gujrera/analytics/query      {"question": "...", "lang"?: "gu|hi|en"}   officers only

Chat and profiles:
    POST /api/gujrera/chat                 {"message": "...", "session_id"?: "...", "lang"?: "gu|hi|en"}
    GET  /api/gujrera/profile/project/{id}?lang=gu
    GET  /api/gujrera/profile/promoter/{id}?lang=gu

Trust check:
    GET  /api/gujrera/health
    GET  /api/gujrera/trust/samples        demo ads built from the registry
    POST /api/gujrera/trust/text           {"text": "..."}
    POST /api/gujrera/trust/upload         multipart: file (PNG/JPG/PDF)

Public endpoints (trust check, profiles) run as an anonymous citizen. Chat and
self-service run as the logged-in user when a valid token is sent; every data
rule is enforced in Repository. Uploaded files are deleted after reading. Chat state lives in memory
for the prototype (one process); a shared store (Redis/Postgres) replaces it
for multi-instance deployment.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.orm import Session

from gujrera.auth import LoginError, authenticate, issue_token, principal_for, read_token
from gujrera.chat.orchestrator import ChatState, respond
from gujrera.config import get_gujrera_settings
from gujrera.db.models import Agent, Project, Promoter, User
from gujrera.db.repository import AccessDenied, Principal, Repository
from gujrera.db.session import make_engine, session_factory
from gujrera.i18n import LANGS
from gujrera.profile.summarise import Profile, project_profile, promoter_profile
from gujrera.selfservice.summary import agent_summary, promoter_summary
from gujrera.trust.checks import check_text
from gujrera.trust.samples import demo_samples

REPO_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_DIR = REPO_ROOT / "data" / "raw" / "gujrera_uploads"
MAX_TEXT_CHARS = 5000
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}


class TrustTextRequest(BaseModel):
    text: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AnalyticsRequest(BaseModel):
    question: str
    lang: str = "en"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    lang: str | None = None


class _Sessions:
    """Small in-memory LRU of chat states with a time-to-live."""

    def __init__(self, max_items: int = 2000, ttl_seconds: int = 3600):
        self._items: OrderedDict[str, tuple[float, ChatState, int | None]] = OrderedDict()
        self._lock = threading.Lock()
        self.max_items, self.ttl = max_items, ttl_seconds

    def get(self, session_id: str | None, owner: int | None = None) -> tuple[str, ChatState]:
        """A chat state belongs to one user (or to anonymous); a different user gets a fresh one."""
        now = time.time()
        with self._lock:
            for key in [k for k, (ts, _, _) in self._items.items() if now - ts > self.ttl]:
                del self._items[key]
            item = self._items.pop(session_id, None) if session_id else None
            if item and item[2] == owner:
                state = item[1]
            else:
                session_id, state = uuid.uuid4().hex, ChatState()
            self._items[session_id] = (now, state, owner)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)
            return session_id, state


SESSIONS = _Sessions()


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


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(session: Session = Depends(get_session),
                 authorization: str | None = Header(default=None)) -> User | None:
    """The logged-in user, None when no token is sent; 401 for a bad or expired token."""
    token = _bearer(authorization)
    if token is None:
        return None
    user = read_token(token, session)
    if user is None:
        raise HTTPException(401, "Your session has expired. Please log in again.")
    return user


def user_repo(session: Session = Depends(get_session), user: User | None = Depends(current_user)) -> Repository:
    return Repository(session, principal_for(user))


def _user_dict(session: Session, user: User) -> dict[str, Any]:
    org = None
    if user.promoter_id:
        org = session.get(Promoter, user.promoter_id).name
    elif user.agent_id:
        org = session.get(Agent, user.agent_id).reg_no
    return {"username": user.username, "role": user.role, "display_name": user.display_name,
            "organisation": org, "district_scope": user.district_scope, "preferred_lang": user.preferred_lang,
            "is_demo": user.is_mock}


router = APIRouter(prefix="/api/gujrera", tags=["gujrera"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(Project))
    mock = session.scalar(select(func.count()).select_from(Project).where(Project.is_mock.is_(True)))
    return {"status": "ok", "projects": total, "mock_projects": mock}


def _profile_dict(prof: Profile | None) -> dict[str, Any]:
    if prof is None:
        raise HTTPException(404, "Not found in the GUJRERA records available to this copilot.")
    return {
        "kind": prof.kind, "id": prof.entity_id, "title": prof.title, "card": prof.card,
        "sentences": [{"text": s.text, "citations": s.citations} for s in prof.sentences],
        "is_mock": prof.is_mock,
    }


def _lang(lang: str) -> str:
    if lang not in LANGS:
        raise HTTPException(400, f"lang must be one of {', '.join(LANGS)}")
    return lang


@router.post("/auth/login")
def login(body: LoginRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        user = authenticate(session, body.username, body.password)
    except LoginError as exc:
        raise HTTPException(429 if exc.locked else 401, str(exc)) from None
    Repository(session, principal_for(user))._audit("login", {"username": user.username})
    return {"token": issue_token(user), "user": _user_dict(session, user)}


@router.get("/auth/me")
def me(session: Session = Depends(get_session), user: User | None = Depends(current_user)) -> dict[str, Any]:
    if user is None:
        raise HTTPException(401, "Not logged in.")
    return {"user": _user_dict(session, user)}


@router.get("/self-service/summary")
def self_service_summary(lang: str = Query("gu"), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    lang = _lang(lang)
    try:
        if repo.p.role == "developer":
            summary = promoter_summary(repo, lang)
        elif repo.p.role == "agent":
            summary = agent_summary(repo, lang)
        else:
            raise AccessDenied("Self-service is for logged-in promoters and agents.")
    except AccessDenied as exc:
        raise HTTPException(403, str(exc)) from None
    return {
        "sentences": [{"text": x.text, "citations": x.citations} for x in summary.sentences],
        "card": summary.card, "is_mock": summary.is_mock,
    }


@router.post("/analytics/query")
def analytics_query(body: AnalyticsRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    if repo.p.role != "officer":
        raise HTTPException(403, "Analytics is available to GUJRERA officers only.")
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(400, "Please type a question.")
    if len(question) > 500:
        raise HTTPException(400, "Question exceeds 500 characters.")
    from gujrera.analytics.engine import answer as analytics_answer

    a = analytics_answer(question, repo, _lang(body.lang))
    return {"intent": a.intent, "sentences": [{"text": x.text} for x in a.sentences], "card": a.card,
            "suggestions": a.suggestions}


@router.post("/chat")
def chat(body: ChatRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    message = (body.message or "").strip()
    if not message:
        raise HTTPException(400, "Please type a question.")
    if len(message) > MAX_TEXT_CHARS:
        raise HTTPException(400, f"Message exceeds the {MAX_TEXT_CHARS:,}-character limit.")
    lang = _lang(body.lang) if body.lang else None
    session_id, state = SESSIONS.get(body.session_id, owner=repo.p.user_id)
    rephrase = None
    if get_gujrera_settings().GUJRERA_LLM_PHRASING:
        from gujrera.chat.llm import make_rephraser

        rephrase = make_rephraser()
    try:
        reply = respond(message, state, repo, lang=lang, rephrase=rephrase)
    except AccessDenied as exc:  # last line of defence; skills normally answer politely first
        raise HTTPException(403, str(exc)) from None
    return {"session_id": session_id, **reply.to_dict()}


@router.get("/chat/starters")
def chat_starters(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Example questions built from registry names, so demo prompts always resolve."""
    projects = session.scalars(select(Project).where(Project.status == "ongoing").order_by(Project.id).limit(2)).all()
    items: list[dict[str, str]] = []
    if projects:
        a = projects[0]
        items.append({"lang": "gu", "text": f"{a.name_gu or a.name} નું પઝેશન ક્યારે મળશે?"})
        items.append({"lang": "en", "text": f"Tell me about the builder of {a.name}"})
    if len(projects) > 1:
        b = projects[1]
        items.append({"lang": "hi", "text": f"{b.name} का पज़ेशन कब मिलेगा?"})
    items.append({"lang": "en", "text": "Is PR/GJ/SURAT/OLPAD/SUDA/RAA99999/010122 registered?"})
    items.append({"lang": "gu", "text": "મારે ફરિયાદ નોંધાવવી છે"})
    return {"items": items, "is_mock": True}


@router.get("/profile/project/{project_id}")
def project_profile_endpoint(project_id: int, lang: str = Query("gu"),
                             repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    return _profile_dict(project_profile(repo, project_id, _lang(lang)))


@router.get("/profile/promoter/{promoter_id}")
def promoter_profile_endpoint(promoter_id: int, lang: str = Query("gu"),
                              repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    return _profile_dict(promoter_profile(repo, promoter_id, _lang(lang)))


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
