"""HTTP endpoints for GujRERA Saathi, mounted on the Pramaan FastAPI app.

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
from contextlib import asynccontextmanager
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi import Path as Path_
from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import Engine, event, func, inspect, select
from sqlalchemy.orm import Session

from gujrera.auth import LoginError, authenticate, issue_token, principal_for, read_token
from gujrera.tools.interest import Payment, calculate, default_rate, explain, possession_end, promised_date
from gujrera.chat.orchestrator import ChatState, respond_with_english
from gujrera.config import get_gujrera_settings
from gujrera.db.models import Agent, Complaint, Project, Promoter, User
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
    previous: str | None = Field(default=None, max_length=500)  # the last report's question, for follow-ups


class NewUserRequest(BaseModel):
    username: str = Field(max_length=40)
    display_name: str = Field(default="", max_length=200)
    role: str = Field(max_length=20)
    district_scope: str | None = Field(default=None, max_length=60)


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    district_scope: str | None = Field(default=None, max_length=60)
    set_scope: bool = False  # true: apply district_scope (None = statewide)
    is_active: bool | None = None


class CircularUpdate(BaseModel):
    number: str | None = Field(default=None, max_length=120)
    subject: str | None = Field(default=None, max_length=400)
    issued_on: date | None = None
    clear_date: bool = False
    status: str | None = Field(default=None, max_length=20)


class FeedbackRequest(BaseModel):
    question: str = Field(max_length=1000)
    answer: str = Field(default="", max_length=8000)
    rating: str = Field(max_length=10)
    reason: str | None = Field(default=None, max_length=40)
    comment: str | None = Field(default=None, max_length=1000)
    intent: str | None = Field(default=None, max_length=60)
    lang: str | None = Field(default=None, max_length=5)
    sources: list[str] = Field(default_factory=list, max_length=20)
    surface: str = Field(default="chat", max_length=20)


class CaseRequest(BaseModel):
    question: str = Field(max_length=1000)
    lang: str | None = Field(default=None, max_length=5)
    role: str = Field(default="citizen", max_length=20)
    expect_intent: str | None = Field(default=None, max_length=300)
    must_contain: list[str] | str | None = None
    must_not_contain: list[str] | str | None = None
    expected_source: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=2000)


class SaveReportRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    question: str = Field(max_length=500)
    lang: str = "en"


class PaymentIn(BaseModel):
    amount: float
    paid_on: date | None = None


class AdReportRequest(BaseModel):
    text: str
    channel: str = "text"  # text | upload | chat


class CaseUpdate(BaseModel):
    status: str | None = None
    outcome: str | None = None
    note: str | None = None


class ComplaintStatusUpdate(BaseModel):
    status: str
    note: str | None = None
    hearing_on: date | None = None
    hearing_place: str | None = Field(default=None, max_length=200)
    outcome: str | None = None


class ComplaintLookup(BaseModel):
    ref: str = Field(max_length=40)
    code: str | None = Field(default=None, max_length=12)
    lang: str = "en"


class ComplianceUpdate(BaseModel):
    status: str
    complied_on: date | None = None
    note: str | None = None


class QprData(BaseModel):
    percent_complete: float | None = None
    units_booked: int | None = None
    garages_booked: int | None = None
    collected_total: float | None = None
    deposited_total: float | None = None
    withdrawn_total: float | None = None
    project_cost: float | None = None
    approvals_pending: list[str] = []
    status_note: str | None = None


class AgreementText(BaseModel):
    text: str
    lang: str = "en"


class InterestRequest(BaseModel):
    project_id: int
    mode: str = "stay"  # stay | withdraw
    payments: list[PaymentIn]
    possession_on: date | None = None  # stay: the day possession was given (default: actual completion or today)
    promised_on: date | None = None  # the possession date in the buyer's agreement, if it differs
    rate: float | None = None  # agreement rate; default is SBI MCLR + 2% (Rule 16)
    lang: str = "en"


class ImportRequest(BaseModel):
    sheet: str | None = Field(default=None, max_length=120)
    kind: str = Field(max_length=30)
    mapping: dict[str, str] = Field(default_factory=dict)
    source_url: str | None = Field(default=None, max_length=500)


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

# Sync endpoints run in a thread pool (40 threads by default). A question that waits on the LLM holds
# its thread while it queues for the GPU, so with the default a few slow questions starve fast ones.
API_THREADS = 200


@asynccontextmanager
async def lifespan(_app):  # noqa: ANN001
    """Pass to FastAPI(lifespan=...) in any app that mounts this router."""
    import anyio.to_thread

    anyio.to_thread.current_default_thread_limiter().total_tokens = API_THREADS
    from gujrera.warmup import start as start_warmup

    start_warmup(_engine)  # load the models and answer the suggested questions in the background
    yield


@lru_cache
def _engine() -> Engine:
    engine = make_engine()
    if inspect(engine).has_table("projects"):
        from gujrera.enforcement import ensure_tables

        ensure_tables(engine)  # databases seeded before the enforcement tables existed
    return engine


def get_session() -> Iterator[Session]:
    engine = _engine()
    if not inspect(engine).has_table("projects"):
        raise HTTPException(503, "GUJRERA database is empty. Run: python scripts/seed_gujrera.py")
    with session_factory(engine)() as session:
        yield session
        session.commit()  # keeps the audit log


@event.listens_for(Session, "after_flush")
def _mark_writes(session: Session, _ctx) -> None:  # noqa: ANN001
    session.info["has_writes"] = True


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _clear_writes(session: Session) -> None:
    session.info.pop("has_writes", None)


def _commit_now(session: Session):
    """Audit sink. A request that has not written anything commits the audit row at once in its own short
    transaction, so waiting on the LLM never holds the database write lock. A request that has already
    written (a complaint, a report) holds that lock itself, so the row joins its transaction instead and is
    committed with it; a separate writer would wait for this same request and deadlock."""
    engine = session.get_bind()

    def sink(row) -> None:  # noqa: ANN001
        if session.info.get("has_writes"):
            session.add(row)
            return
        with Session(engine) as s:
            s.add(row)
            s.commit()

    return sink


def citizen_repo(session: Session = Depends(get_session)) -> Repository:
    return Repository(session, Principal.anonymous(), audit_sink=_commit_now(session))


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
    return Repository(session, principal_for(user), audit_sink=_commit_now(session))


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
    from gujrera.warmup import STATUS as warmup

    return {"status": "ok", "projects": total, "mock_projects": mock, "warmup": warmup["state"]}


def _profile_dict(prof: Profile | None) -> dict[str, Any]:
    if prof is None:
        raise HTTPException(404, "Not found in the GUJRERA records available to GujRERA Saathi.")
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
        action = "login_locked" if exc.locked else "login_disabled" if exc.disabled else "login_failed"
        Repository(session, Principal.anonymous(), audit_sink=_commit_now(session))._audit(
            action, {"username": (body.username or "").strip().lower()[:80]})  # never the password
        raise HTTPException(429 if exc.locked else 401, str(exc)) from None
    from datetime import datetime as _dt

    user.last_login_at = _dt.now()
    session.flush()
    Repository(session, principal_for(user), audit_sink=_commit_now(session))._audit("login", {"username": user.username})
    return {"token": issue_token(user), "user": _user_dict(session, user)}


# Demo logins offered as quick picks, in this order, when they exist in the loaded database.
_DEMO_PICKS = ("dev_002", "agent_001", "citizen_01", "citizen_03", "officer_state", "officer_surat",
               "officer_ahmedabad", "officer_gandhinagar")


@router.get("/auth/demo-accounts")
def demo_accounts(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Quick-pick demo logins for this database (demo accounts only; real accounts are never listed)."""
    users = {u.username: u for u in session.scalars(select(User).where(User.is_mock.is_(True),
                                                                      User.username.in_(_DEMO_PICKS)))}
    label = {"developer": "Promoter", "agent": "Agent", "citizen": "Home buyer"}
    out = []
    for name in _DEMO_PICKS:
        u = users.get(name)
        if u is None:
            continue
        text = (f"Officer ({u.district_scope or 'statewide'})" if u.role == "officer"
                else label.get(u.role, u.role) + (f" {name.split('_')[-1]}" if name.startswith("citizen") else ""))
        out.append({"username": u.username, "label": text})
    return {"accounts": out}


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


VOICE_DIR = REPO_ROOT / "data" / "raw" / "gujrera_voice"
VOICE_EXTENSIONS = {".webm", ".ogg", ".opus", ".wav", ".m4a", ".mp3", ".mp4"}
MAX_VOICE_BYTES = 10 * 1024 * 1024
MAX_VOICE_SECONDS = 60
WEAK_VOICE_LANGS = {"gu", "kn", "te", "ml", "bn"}  # Whisper small is unreliable here (deck: ~64% WER on Gujarati)


@router.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...), lang: str | None = Form(default=None)) -> dict[str, Any]:
    """Speech to text for the chat box (Whisper small, self-hosted). The audio is deleted after reading.
    The text is returned for the user to check and send; it is not sent to the chat automatically."""
    from factcheck.ingest.audio import transcribe_audio  # loads faster-whisper lazily

    ext = Path(file.filename or "voice.webm").suffix.lower() or ".webm"
    if ext not in VOICE_EXTENSIONS:
        raise HTTPException(400, "Unsupported audio type.")
    if lang is not None and lang not in LANGS:
        raise HTTPException(400, f"lang must be one of {', '.join(LANGS)}")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The recording is empty.")
    if len(data) > MAX_VOICE_BYTES:
        raise HTTPException(400, "Recording exceeds 10 MB.")
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    path = VOICE_DIR / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    try:
        result = transcribe_audio(path, language=lang, engine="whisper", use_cache=False)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except Exception as exc:  # noqa: BLE001 - undecodable audio
        raise HTTPException(400, f"Could not read the recording: {str(exc).splitlines()[0][:150]}") from None
    finally:
        path.unlink(missing_ok=True)
    if result.get("duration_sec", 0) > MAX_VOICE_SECONDS:
        raise HTTPException(400, f"Please keep voice questions under {MAX_VOICE_SECONDS} seconds.")
    detected = result.get("language")
    return {
        "text": (result.get("text") or "").strip(),
        "language": detected,
        "duration_sec": result.get("duration_sec"),
        "engine": result.get("engine"),
        "low_quality": detected in WEAK_VOICE_LANGS,
        "notes": result.get("notes", []),
    }


@router.post("/trust/report")
def trust_report(body: AdReportRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """A citizen reports an ad that failed the RERA check. The check is re-run here on the ad text;
    the reporter's name and number are not stored."""
    from gujrera.enforcement import file_report

    text = (body.text or "").strip()
    if len(text) < 20:
        raise HTTPException(400, "The ad text is too short to report.")
    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(400, f"Text exceeds the {MAX_TEXT_CHARS:,}-character limit.")
    channel = body.channel if body.channel in ("text", "upload", "chat") else "text"
    report = check_text(text, repo)
    try:
        row, case, new = file_report(repo, text, report, channel=channel)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"received": True, "receipt": f"RPT-{row.reported_on.year}-{row.id:05d}", "duplicate": not new,
            "kind": case.kind,
            "message": "Thank you. GUJRERA's enforcement team will see this ad with what the check found. "
                       "Your name and number were not included."}


def _officer_or_403(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AccessDenied as exc:
        if args and isinstance(args[0], Repository):
            args[0]._audit("access_denied", {"what": getattr(fn, "__name__", "?")})
        raise HTTPException(403, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/enforcement/cases")
def enforcement_cases(status: str | None = Query(None), kind: str | None = Query(None),
                      district: str | None = Query(None, max_length=60),
                      repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.enforcement import list_cases

    return _officer_or_403(list_cases, repo, status=status, kind=kind, district=district)


@router.get("/enforcement/cases/{case_id}")
def enforcement_case(case_id: int, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.enforcement import get_case

    case = _officer_or_403(get_case, repo, case_id)
    if case is None:
        raise HTTPException(404, "Case not found.")
    return case


@router.post("/enforcement/cases/{case_id}")
def enforcement_case_update(case_id: int, body: CaseUpdate, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.enforcement import update_case

    case = _officer_or_403(update_case, repo, case_id, status=body.status, outcome=body.outcome, note=body.note)
    if case is None:
        raise HTTPException(404, "Case not found.")
    return case


QUARTER_RE = r"^\d{4}-Q[1-4]$"


@router.get("/qpr/overview")
def qpr_overview(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.selfservice.qpr import overview

    return _officer_or_403(overview, repo)


@router.get("/qpr/{project_id}/{quarter}/draft")
def qpr_draft(project_id: int, quarter: str = Path_(..., pattern=QUARTER_RE), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.selfservice.qpr import draft

    return _officer_or_403(draft, repo, project_id, quarter)


@router.post("/qpr/{project_id}/{quarter}/check")
def qpr_check(project_id: int, body: QprData, quarter: str = Path_(..., pattern=QUARTER_RE),
              repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.selfservice.qpr import check

    return {"issues": _officer_or_403(check, repo, project_id, quarter, body.model_dump())}


@router.post("/qpr/{project_id}/{quarter}/submit")
def qpr_submit(project_id: int, body: QprData, quarter: str = Path_(..., pattern=QUARTER_RE),
               repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.selfservice.qpr import submit

    return _officer_or_403(submit, repo, project_id, quarter, body.model_dump())


@router.get("/watch")
def watch_list(lang: str = Query("en"), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.watch import my_watches

    return _officer_or_403(my_watches, repo, _lang(lang))


@router.get("/watch/unread")
def watch_unread(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.watch import unread_count

    return {"unread": unread_count(repo)}


@router.post("/watch/seen")
def watch_seen(project_id: int | None = Query(None), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.watch import mark_seen

    return {"marked": _officer_or_403(mark_seen, repo, project_id)}


@router.post("/watch/{project_id}")
def watch_add(project_id: int, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.watch import add_watch

    return _officer_or_403(add_watch, repo, project_id)


@router.delete("/watch/{project_id}")
def watch_remove(project_id: int, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.watch import remove_watch

    return {"removed": _officer_or_403(remove_watch, repo, project_id)}


MAX_AGREEMENT_CHARS = 200_000


@router.get("/agreement/samples")
def agreement_samples(session: Session = Depends(get_session)) -> dict[str, Any]:
    from gujrera.tools.agreement_samples import FAIR, ONE_SIDED

    demo = bool(session.scalar(select(Project.id).where(Project.is_mock.is_(True)).limit(1)))
    # The samples name a made-up project; they are never rewritten around a real project or builder.
    note = None if demo else ("The samples use a made-up project, so the registration check says it is not in "
                              "the registry. Paste your own agreement to check its project.")
    return {"one_sided": ONE_SIDED, "fair": FAIR, "note": note}


@router.post("/agreement/check")
def agreement_check(body: AgreementText, repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    """Compare a draft agreement for sale with the model in the Gujarat RERA Rules (Annexure A)."""
    from gujrera.tools.agreement import report

    text = (body.text or "").strip()
    if len(text) < 200:
        raise HTTPException(400, "Paste the full agreement (at least a few clauses).")
    if len(text) > MAX_AGREEMENT_CHARS:
        raise HTTPException(400, "The agreement is too long; paste the main clauses.")
    return report(text, repo, _lang(body.lang))


@router.post("/agreement/upload")
async def agreement_upload(file: UploadFile = File(...), lang: str = Form(default="en"),
                           repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    from gujrera.tools.agreement import extract_text, report

    ext = Path(file.filename or "agreement").suffix.lower()
    if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt"):
        raise HTTPException(400, "Upload a PDF, a photo (PNG/JPG) or a text file.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty.")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "File exceeds the 20 MB size limit.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    try:
        text, how = extract_text(path)
    except Exception as exc:  # noqa: BLE001 - unreadable file
        raise HTTPException(400, f"Could not read the file: {str(exc).splitlines()[0][:150]}") from None
    finally:
        path.unlink(missing_ok=True)
    if len(text.strip()) < 200:
        raise HTTPException(400, "Too little text could be read from the file; paste the text instead.")
    out = report(text[:MAX_AGREEMENT_CHARS], repo, _lang(lang))
    out["read_as"] = how
    return out


@router.get("/orders/track")
def orders_track(order_no: str | None = Query(None, max_length=40), complaint_ref: str | None = Query(None, max_length=40),
                 project_id: int | None = Query(None), lang: str = Query("en"),
                 repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    """Public: what complaint orders direct and whether they were complied with."""
    from gujrera.orders import orders_for

    if not (order_no or complaint_ref or project_id is not None):
        raise HTTPException(400, "Give an order number, a complaint reference or a project.")
    return {"items": orders_for(repo, order_no=order_no, complaint_ref=complaint_ref, project_id=project_id, lang=_lang(lang))}


@router.get("/orders/enforce")
def orders_enforce(lang: str = Query("en"), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.orders import to_enforce

    return _officer_or_403(to_enforce, repo, _lang(lang))


@router.post("/orders/{order_id}/compliance")
def orders_compliance(order_id: int, body: ComplianceUpdate, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.orders import update

    out = _officer_or_403(update, repo, order_id, body.status, complied_on=body.complied_on, note=body.note)
    if out is None:
        raise HTTPException(404, "Order not found.")
    return out


@router.get("/complaints/triage")
def complaints_triage(lang: str = Query("en"), district: str | None = Query(None, max_length=60),
                      category: str | None = Query(None, max_length=40),
                      repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.complaints.triage import triage

    return _officer_or_403(triage, repo, _lang(lang), district=district, category=category)


def _complaint_call(fn, *args, **kwargs):
    """Errors from the complaint pages as HTTP: 403 not allowed, 404 not found, 400 bad input."""
    try:
        return fn(*args, **kwargs)
    except AccessDenied as exc:
        raise HTTPException(403, str(exc)) from None
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


def _file_response(path: Path, filename: str, content_type: str):
    from fastapi.responses import FileResponse

    return FileResponse(path, media_type=content_type, filename=filename,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})


@router.get("/complaints/mine")
def complaints_mine(lang: str = Query("en"), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """The logged-in buyer's complaints, with hearing and documents."""
    from gujrera.complaints.documents import mine

    return mine(repo, _lang(lang))


@router.post("/complaints/lookup")
def complaints_lookup(body: ComplaintLookup, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """One complaint by reference number: the buyer who filed it (logged in), an officer, or anyone with the
    tracking code. The code goes in the body, never in the URL."""
    from gujrera.complaints.documents import lookup

    return _complaint_call(lookup, repo, body.ref, body.code, _lang(body.lang))


@router.post("/complaints/documents")
async def complaints_add_document(file: UploadFile = File(...), ref: str = Form(..., max_length=40),
                                  code: str | None = Form(default=None, max_length=12),
                                  note: str | None = Form(default=None, max_length=200),
                                  repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.complaints.documents import MAX_BYTES, add_document

    data = await file.read(MAX_BYTES + 1)
    return _complaint_call(add_document, repo, ref, code, file.filename or "", data, note)


@router.post("/complaints/documents/{doc_id}/file")
def complaints_document_file(doc_id: int, body: ComplaintLookup, repo: Repository = Depends(user_repo)):
    from gujrera.complaints.documents import complaint_for, document_file

    c = _complaint_call(complaint_for, repo, body.ref, body.code)
    return _file_response(*_complaint_call(document_file, repo, c, doc_id))


@router.get("/complaints/hearings")
def complaints_hearings(days: int = Query(14, ge=1, le=90), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """Hearings fixed in the next days, in the officer's district."""
    from gujrera.complaints.documents import upcoming_hearings

    if repo.p.role != "officer":
        raise HTTPException(403, "This is for GUJRERA officers.")
    return {"items": upcoming_hearings(repo, days)}


@router.post("/complaints/{complaint_id}/documents")
async def complaints_officer_add_document(complaint_id: int, file: UploadFile = File(...),
                                          note: str | None = Form(default=None, max_length=200),
                                          repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.complaints.documents import MAX_BYTES, officer_add_document

    data = await file.read(MAX_BYTES + 1)
    return _complaint_call(officer_add_document, repo, complaint_id, file.filename or "", data, note)


@router.get("/complaints/{complaint_id}/documents/{doc_id}")
def complaints_officer_document(complaint_id: int, doc_id: int, repo: Repository = Depends(user_repo)):
    from gujrera.complaints.documents import document_file, officer_complaint

    c = _complaint_call(officer_complaint, repo, complaint_id)
    return _file_response(*_complaint_call(document_file, repo, c, doc_id))


@router.get("/complaints/{complaint_id}/brief")
def complaint_brief(complaint_id: int, lang: str = Query("en"), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.complaints.triage import brief

    out = _officer_or_403(brief, repo, complaint_id, _lang(lang))
    if out is None:
        raise HTTPException(404, "Complaint not found.")
    return out


@router.post("/complaints/{complaint_id}/status")
def complaint_status_update(complaint_id: int, body: ComplaintStatusUpdate,
                            repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.complaints.triage import update_status

    out = _officer_or_403(update_status, repo, complaint_id, body.status, note=body.note,
                          hearing_on=body.hearing_on, outcome=body.outcome, hearing_place=body.hearing_place)
    if out is None:
        raise HTTPException(404, "Complaint not found.")
    return out


@router.get("/risk/projects")
def risk_projects(lang: str = Query("en"), district: str | None = Query(None, max_length=60),
                  repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """Project risk watchlist (officers; district officers see their district only)."""
    from gujrera.analytics.risk import score_projects, summary

    try:
        risks = score_projects(repo, _lang(lang), district=district or None)
    except AccessDenied as exc:
        raise HTTPException(403, str(exc)) from None
    return {"summary": summary(risks), "items": [r.to_dict() for r in risks],
            "district_scope": repo.p.district_scope, "is_mock": any(r.is_mock for r in risks)}


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
    from gujrera.analytics.export import touch
    from gujrera.analytics.followup import refine

    refined = refine(body.previous, question)  # "only Bopal", "last 3 months" after a report
    asked = refined.question if refined else question
    a = analytics_answer(asked, repo, _lang(body.lang))
    if a.intent == "analytics":
        touch(repo, asked)
    return {"intent": a.intent, "sentences": [{"text": x.text} for x in a.sentences], "card": a.card,
            "suggestions": a.suggestions, "question": asked,
            "refined": refined.changes if refined else None}


@router.post("/analytics/export")
def analytics_export(body: AnalyticsRequest, repo: Repository = Depends(user_repo)):
    """The report as an Excel file, re-run on the server so it is current, district-scoped and logged."""
    from fastapi.responses import Response

    from gujrera.analytics.engine import answer as analytics_answer
    from gujrera.analytics.export import to_xlsx

    if repo.p.role != "officer":
        raise HTTPException(403, "Analytics is available to GUJRERA officers only.")
    question = (body.question or "").strip()
    if not question or len(question) > 500:
        raise HTTPException(400, "Please give the report question.")
    a = analytics_answer(question, repo, _lang(body.lang))
    if a.intent != "analytics" or not a.card:
        raise HTTPException(400, a.sentences[0].text if a.sentences else "This question did not produce a report.")
    repo._audit("analytics_export", {"question": question, "rows": len(a.card.get("rows") or [])})
    data = to_xlsx(repo, question, a.card, [x.text for x in a.sentences])
    stem = "".join(ch if ch.isalnum() else "_" for ch in (a.card.get("title") or "report"))[:60].strip("_") or "report"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'})


@router.get("/analytics/saved")
def analytics_saved(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.analytics.export import list_saved

    return _officer_or_403(list_saved, repo)


@router.post("/analytics/saved")
def analytics_save(body: SaveReportRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.analytics.export import save

    return _officer_or_403(save, repo, body.name, body.question, _lang(body.lang))


@router.delete("/analytics/saved/{saved_id}")
def analytics_unsave(saved_id: int, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.analytics.export import delete

    return _officer_or_403(delete, repo, saved_id)


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
    started = time.perf_counter()
    try:
        reply, english = respond_with_english(message, state, repo, lang=lang, rephrase=rephrase)
    except AccessDenied as exc:  # last line of defence; skills normally answer politely first
        raise HTTPException(403, str(exc)) from None
    # Outcome and time only, never the question: feeds "answered without a person" and response time.
    repo._audit("chat_reply", {"intent": reply.intent, "lang": reply.lang, "by": reply.understood_by,
                               "ms": int((time.perf_counter() - started) * 1000)})
    return {"session_id": session_id, **reply.to_dict(), "english": english}


CLOSED_COMPLAINT_STATUSES = ("disposed", "withdrawn")


class ReviewRequest(BaseModel):
    item_type: str = Field(max_length=30)
    item_key: str = Field(max_length=160)
    status: str = Field(max_length=20)
    note: str | None = Field(default=None, max_length=500)


@router.get("/officer/dashboard")
def officer_dashboard(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """The officer's work queue for their district (officers only)."""
    from gujrera.officer_desk import dashboard

    return _officer_or_403(dashboard, repo)


@router.post("/officer/review")
def officer_review(body: ReviewRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.officer_desk import review

    return _officer_or_403(review, repo, body.item_type, body.item_key, body.status, body.note)


def _overview_charts(session: Session, today: date, by_status: dict[str, int], ending: int) -> dict[str, Any]:
    """Counts for the home charts: where projects stand, start years, how long past their date, types."""
    past_q = (Project.status == "unverified") | ((Project.status == "ongoing") & (Project.reg_valid_until < today))
    ongoing_past = session.scalar(select(func.count()).select_from(Project).where(
        Project.status == "ongoing", Project.reg_valid_until < today)) or 0
    standing = {
        "on_schedule": max(0, by_status.get("ongoing", 0) - ongoing_past - ending),
        "ending_90_days": ending,
        "past_date": by_status.get("unverified", 0) + ongoing_past,
        "completed": by_status.get("completed", 0),
        "lapsed_or_revoked": by_status.get("lapsed", 0) + by_status.get("revoked", 0),
    }
    years: dict[str, int] = {}
    for (y, n) in session.execute(select(func.strftime("%Y", Project.reg_date), func.count())
                                  .group_by(func.strftime("%Y", Project.reg_date))):
        if y is None:
            continue
        key = y if int(y) > 2012 else "2012"  # earlier years are a handful each: fold them in
        years[key] = years.get(key, 0) + n
    start_years = [{"year": ("up to 2012" if y == "2012" else y), "count": n} for y, n in sorted(years.items())]
    ages = {"under_6_months": 0, "6_to_12_months": 0, "1_to_2_years": 0, "2_to_4_years": 0, "over_4_years": 0}
    for (end,) in session.execute(select(Project.reg_valid_until).where(past_q)):
        d = (today - end).days
        ages["under_6_months" if d < 183 else "6_to_12_months" if d < 365 else "1_to_2_years" if d < 730
             else "2_to_4_years" if d < 1461 else "over_4_years"] += 1
    types = [{"type": t, "count": n} for t, n in session.execute(
        select(Project.project_type, func.count()).group_by(Project.project_type).order_by(func.count().desc()))]
    return {"standing": standing, "start_years": start_years, "past_age": ages, "types": types}


@router.get("/overview")
def overview(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Registry totals for the dashboard home: counts only, no names or personal data."""
    by_status = dict(session.execute(select(Project.status, func.count()).group_by(Project.status)).all())
    # Delayed: still ongoing and either past the date first promised, or given a later completion date.
    # The same definition as the chat's district answers, so the two never disagree.
    delayed = session.scalar(select(func.count()).select_from(Project).where(
        Project.status == "ongoing",
        (Project.proposed_completion < date.today())
        | (func.coalesce(Project.revised_completion, Project.proposed_completion) > Project.proposed_completion))) or 0
    complaints = dict(session.execute(select(Complaint.status, func.count()).group_by(Complaint.status)).all())
    districts = session.execute(select(Project.district, func.count()).group_by(Project.district)
                                .order_by(func.count().desc())).all()
    # Public records: the registered end date has passed and no completion is on record.
    from datetime import timedelta

    today = date.today()
    past = (Project.status == "unverified") | ((Project.status == "ongoing") & (Project.reg_valid_until < today))
    past_by_district = session.execute(select(Project.district, func.count()).where(past).group_by(Project.district)
                                       .order_by(func.count().desc())).all()
    ending = session.scalar(select(func.count()).select_from(Project).where(
        Project.status == "ongoing", Project.reg_valid_until >= today,
        Project.reg_valid_until <= today + timedelta(days=90))) or 0
    return {
        "projects": sum(by_status.values()),
        "projects_by_status": by_status,
        "ongoing_delayed": delayed,
        "promoters": session.scalar(select(func.count()).select_from(Promoter)) or 0,
        "agents_active": session.scalar(select(func.count()).select_from(Agent).where(Agent.status == "active")) or 0,
        "complaints": sum(complaints.values()),
        "complaints_open": sum(n for st, n in complaints.items() if st not in CLOSED_COMPLAINT_STATUSES),
        "complaints_by_status": complaints,
        "projects_by_district": [{"district": d, "count": n} for d, n in districts],
        "past_completion": sum(n for _, n in past_by_district),
        "past_completion_by_district": [{"district": d, "count": n} for d, n in past_by_district],
        "ending_90_days": ending,
        "charts": _overview_charts(session, today, by_status, ending),
        "is_mock": bool(session.scalar(select(func.count()).select_from(Project).where(Project.is_mock))),
    }


@router.get("/report/project/{project_id}")
def project_report(project_id: int, lang: str = Query("en"), repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    """Before-you-buy report: public registry facts with sources, questions to ask, buyer rights."""
    from gujrera.tools.project_report import build_report

    report = build_report(repo, project_id, _lang(lang))
    if report is None:
        raise HTTPException(404, "Project not found.")
    return report


@router.get("/calc/projects")
def calc_projects(q: str = Query("", max_length=120), repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    """Projects for the calculator's picker: by RERA number or by (English or Gujarati) name."""
    q = q.strip()
    if len(q) < 2:
        return {"items": []}
    exact = repo.get_project(q)
    rows = [exact] if exact else repo.search_projects(q, limit=12, min_score=60)

    def prefix_hit(r: dict[str, Any]) -> bool:  # every typed word starts a word of the name ("mangal sq")
        typed = q.lower().split()
        return any(all(any(w.startswith(t) for w in (name or "").lower().split()) for t in typed)
                   for name in (r["name"], r.get("name_gu")))

    rows = sorted(rows, key=lambda r: (not prefix_hit(r), -r.get("match_score", 100)))[:8]
    return {"items": [{"id": r["id"], "name": r["name"], "name_gu": r.get("name_gu"), "rera_no": r["rera_no"],
                       "district": r["district"], "status": r["status"],
                       "promised": str(r["proposed_completion"])} for r in rows]}


@router.get("/calc/rate")
def calc_rate() -> dict[str, Any]:
    return default_rate()


@router.post("/calc/interest")
def calc_interest(body: InterestRequest, repo: Repository = Depends(citizen_repo)) -> dict[str, Any]:
    """Delay interest (stay) or refund with interest (withdraw): RERA Act s.18, Gujarat Rules r.16-17."""
    lang = _lang(body.lang)
    project = repo.get_project_by_id(body.project_id)
    if project is None:
        raise HTTPException(404, "Project not found.")
    if len(body.payments) > 50:
        raise HTTPException(400, "Enter at most 50 payments.")
    promised = body.promised_on or promised_date(project)
    until = body.possession_on or possession_end(project)
    try:
        calc = calculate([Payment(p.amount, p.paid_on) for p in body.payments], promised,
                         mode=body.mode, until=until, rate_pct=body.rate)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    sentences = explain(calc, project, lang)
    if body.promised_on:  # the buyer's own date, not the registry's
        sentences = sentences[1:]
    return {
        "project": {"id": project["id"], "name": project["name"], "name_gu": project.get("name_gu"),
                    "rera_no": project["rera_no"], "status": project["status"],
                    "registered_promised": str(project["proposed_completion"])},
        "result": calc.to_dict(),
        "sentences": [{"text": x.text, "citations": x.citations} for x in sentences],
        "is_mock": bool(project.get("is_mock")),
    }


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
    # Name used in the overview page's examples, so they always point at a project in this database.
    first = projects[0] if projects else None
    return {"items": items, "is_mock": bool(first.is_mock) if first else True,
            "project": first.name.replace(" (Demo)", "") if first else None,
            "project_gu": (first.name_gu or first.name.replace(" (Demo)", "")) if first else None}


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
    if not items:
        # Public records: no sample ad is built around a real project or builder. These two name made-up
        # projects; the number uses a MOCK code so trying it adds nothing to the officers' unknown-numbers list.
        items = [
            {"id": "public-not-registered", "kind": "not_found", "lang": "en",
             "label": "Sample: a registration number that is not in the registry",
             "text": "Shree Sample Residency, Olpad, Surat. 2 & 3 BHK flats, possession 2027. Book now! "
                     "GujRERA No. PR/GJ/SURAT/OLPAD/SUDA/MOCK99999/010125",
             "expected": ["not_found"]},
            {"id": "public-no-number", "kind": "no_number", "lang": "gu",
             "label": "નમૂનો: RERA નંબર વગરની જાહેરાત",
             "text": "વેસુ, સુરતમાં લક્ઝરી ફ્લેટ (નમૂનો). 2BHK માત્ર ₹45 લાખથી. આજે જ ₹51,000 આપી બુક કરો!",
             "expected": ["no_rera_number"]},
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
            try:
                leftover.unlink(missing_ok=True)
            except OSError:  # still locked by a reader on Windows: the check is done, never fail the request
                pass


# ------------------------------------------------------------ data onboarding (state-level officers)
@router.post("/admin/imports")
async def admin_import_upload(file: UploadFile = File(...), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """Upload a department data file (CSV, Excel or JSON); returns its sheets with suggested column matches."""
    from gujrera.onboarding import MAX_BYTES, upload

    data = await file.read(MAX_BYTES + 1)
    return _officer_or_403(upload, repo, file.filename or "upload", data)


@router.get("/admin/imports")
def admin_import_history(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.onboarding import history

    return _officer_or_403(history, repo)


@router.get("/admin/imports/{run_id}")
def admin_import_describe(run_id: str = Path_(..., pattern=r"^[0-9a-f]{32}$"),
                          repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.onboarding import describe

    return _officer_or_403(describe, repo, run_id)


@router.post("/admin/imports/{run_id}/check")
def admin_import_check(body: ImportRequest, run_id: str = Path_(..., pattern=r"^[0-9a-f]{32}$"),
                       repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """Apply every row and roll back: counts of new, changed, unchanged and rejected rows. Saves nothing."""
    from gujrera.onboarding import run_import

    return _officer_or_403(run_import, repo, run_id, sheet=body.sheet, kind=body.kind, mapping=body.mapping,
                           source_url=body.source_url, commit=False)


@router.post("/admin/imports/{run_id}/load")
def admin_import_load(body: ImportRequest, run_id: str = Path_(..., pattern=r"^[0-9a-f]{32}$"),
                      repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.onboarding import run_import

    return _officer_or_403(run_import, repo, run_id, sheet=body.sheet, kind=body.kind, mapping=body.mapping,
                           source_url=body.source_url, commit=True)


@router.get("/admin/imports/{run_id}/rejected")
def admin_import_rejected(run_id: str = Path_(..., pattern=r"^[0-9a-f]{32}$"),
                          repo: Repository = Depends(user_repo)):
    from fastapi.responses import Response

    from gujrera.onboarding import rejected_csv

    name, text = _officer_or_403(rejected_csv, repo, run_id)
    return Response("\ufeff" + text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ------------------------------------------------------------ administration (state-level officers)
@router.get("/admin/users")
def admin_users(role: str | None = Query(None, max_length=20), q: str | None = Query(None, max_length=80),
                repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.admin import list_users

    return _officer_or_403(list_users, repo, role, q)


@router.post("/admin/users")
def admin_create_user(body: NewUserRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """Create an officer or citizen account; the one-time password is in the response only."""
    from gujrera.admin import create_user

    return _officer_or_403(create_user, repo, body.username, body.display_name, body.role, body.district_scope)


@router.patch("/admin/users/{user_id}")
def admin_update_user(user_id: int, body: UpdateUserRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.admin import update_user

    return _officer_or_403(update_user, repo, user_id, display_name=body.display_name,
                           district_scope=body.district_scope, set_scope=body.set_scope, is_active=body.is_active)


@router.post("/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.admin import reset_password

    return _officer_or_403(reset_password, repo, user_id)


def _audit_filters(username, role, category, action, since, until, q) -> dict[str, Any]:
    return {"username": username or None, "role": role or None, "category": category or None,
            "action": action or None, "since": since, "until": until, "q": q or None}


@router.get("/admin/audit")
def admin_audit(username: str | None = Query(None, max_length=80), role: str | None = Query(None, max_length=20),
                category: str | None = Query(None, max_length=20), action: str | None = Query(None, max_length=60),
                since: date | None = Query(None), until: date | None = Query(None),
                q: str | None = Query(None, max_length=100), limit: int = Query(100, ge=1, le=500),
                offset: int = Query(0, ge=0), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.admin import audit_log

    return _officer_or_403(audit_log, repo, **_audit_filters(username, role, category, action, since, until, q),
                           limit=limit, offset=offset)


@router.get("/admin/audit.csv")
def admin_audit_csv(username: str | None = Query(None, max_length=80), role: str | None = Query(None, max_length=20),
                    category: str | None = Query(None, max_length=20), action: str | None = Query(None, max_length=60),
                    since: date | None = Query(None), until: date | None = Query(None),
                    q: str | None = Query(None, max_length=100), repo: Repository = Depends(user_repo)):
    from fastapi.responses import Response

    from gujrera.admin import audit_csv

    text = _officer_or_403(audit_csv, repo, **_audit_filters(username, role, category, action, since, until, q))
    return Response("\ufeff" + text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="gujrera_audit_log.csv"'})


# ------------------------------------------------------------ circulars
@router.post("/admin/circulars")
async def admin_circular_upload(file: UploadFile = File(...), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """Upload a circular PDF: text read (OCR for scanned pages), details guessed, saved as a draft."""
    from starlette.concurrency import run_in_threadpool

    from gujrera.circulars import MAX_BYTES, upload

    data = await file.read(MAX_BYTES + 1)
    return await run_in_threadpool(_officer_or_403, upload, repo, file.filename or "circular.pdf", data)


@router.get("/admin/circulars")
def admin_circulars(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.circulars import list_all

    return _officer_or_403(list_all, repo)


@router.patch("/admin/circulars/{cid}")
def admin_circular_update(cid: int, body: CircularUpdate, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.circulars import update

    return _officer_or_403(update, repo, cid, number=body.number, subject=body.subject, issued_on=body.issued_on,
                           clear_date=body.clear_date, status=body.status)


@router.delete("/admin/circulars/{cid}")
def admin_circular_delete(cid: int, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.circulars import delete

    return _officer_or_403(delete, repo, cid)


@router.get("/circulars")
def circulars_public(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Published circulars (public)."""
    from gujrera.circulars import list_published

    return {"circulars": list_published(session)}


@router.get("/circulars/{cid}/pdf")
def circular_pdf(cid: int, token: str | None = Query(None, max_length=600), repo: Repository = Depends(user_repo)):
    """The circular's PDF. Published circulars are public; drafts only for state-level officers."""
    from fastapi.responses import FileResponse

    from gujrera.auth import principal_for, read_token
    from gujrera.circulars import pdf_path
    from gujrera.db.models import Circular

    c = repo.s.get(Circular, cid)
    if c is None:
        raise HTTPException(404, "No such circular.")
    if c.status != "published":
        p = repo.p
        if token and p.role != "officer":  # a link opened in a new tab carries the token in the query
            user = read_token(token, repo.s)
            p = principal_for(user) if user else p
        if p.role != "officer" or p.district_scope:
            raise HTTPException(404, "No such circular.")
    path = pdf_path(repo.s, c)
    if not path.exists():
        raise HTTPException(404, "The PDF file is missing.")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{c.filename}"'})


# ------------------------------------------------------------ accuracy: feedback, test set, runs
@router.post("/feedback")
def feedback(body: FeedbackRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """A thumbs up or down on an answer (anyone). Down-votes go to the admin's review queue."""
    from gujrera.accuracy import give_feedback

    return _officer_or_403(give_feedback, repo, question=body.question, answer=body.answer, rating=body.rating,
                           reason=body.reason, comment=body.comment, intent=body.intent, lang=body.lang,
                           sources=body.sources, surface=body.surface)


@router.get("/admin/feedback")
def admin_feedback(status: str | None = Query("new", max_length=20), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import list_feedback

    return _officer_or_403(list_feedback, repo, status or None)


@router.post("/admin/feedback/{fid}/dismiss")
def admin_feedback_dismiss(fid: int, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import review_feedback

    return _officer_or_403(review_feedback, repo, fid, "dismissed")


@router.post("/admin/feedback/{fid}/to-test")
def admin_feedback_to_test(fid: int, body: CaseRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import feedback_to_case

    return _officer_or_403(feedback_to_case, repo, fid, must_contain=body.must_contain,
                           must_not_contain=body.must_not_contain, expect_intent=body.expect_intent,
                           expected_source=body.expected_source, category=body.category, note=body.note)


@router.get("/admin/tests")
def admin_tests(origin: str | None = Query(None, max_length=20), q: str | None = Query(None, max_length=100),
                repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import list_cases

    return _officer_or_403(list_cases, repo, origin, q)


@router.post("/admin/tests")
def admin_test_add(body: CaseRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import add_case

    return _officer_or_403(add_case, repo, **body.model_dump())


@router.post("/admin/tests/generate")
def admin_tests_generate(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import generate_cases

    return _officer_or_403(generate_cases, repo)


@router.post("/admin/tests/import")
async def admin_tests_import(file: UploadFile = File(...), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import import_cases

    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "The test set file is larger than 5 MB.")
    return _officer_or_403(import_cases, repo, file.filename or "tests.csv", data)


@router.post("/admin/tests/{cid}/active")
def admin_test_active(cid: int, active: bool = Query(...), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import set_case_active

    return _officer_or_403(set_case_active, repo, cid, active)


@router.post("/admin/tests/run")
def admin_tests_run(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """Start a run in the background; poll /admin/tests/runs/{id} for progress."""
    from gujrera.accuracy import start_run

    return _officer_or_403(start_run, repo)


@router.get("/admin/tests/runs")
def admin_tests_runs(repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import list_runs

    return _officer_or_403(list_runs, repo)


@router.get("/admin/tests/runs/{run_id}")
def admin_tests_run_detail(run_id: int, show: str = Query("failed", pattern="^(failed|unjudged|all)$"),
                           repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import run_detail

    return _officer_or_403(run_detail, repo, run_id, show=show)


@router.get("/admin/poc-metrics")
def admin_poc_metrics(days: int = Query(30, ge=1, le=365), repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    """The POC scope's measures: answered without a person, report time against manual, consistency."""
    from gujrera.accuracy import poc_metrics

    return _officer_or_403(poc_metrics, repo, days)


class ManualTimeRequest(BaseModel):
    minutes: float | None = Field(default=None)


@router.post("/admin/poc-metrics/manual-time")
def admin_poc_manual_time(body: ManualTimeRequest, repo: Repository = Depends(user_repo)) -> dict[str, Any]:
    from gujrera.accuracy import set_manual_report_minutes

    return _officer_or_403(set_manual_report_minutes, repo, body.minutes)


@router.get("/admin/tests/runs/{run_id}/csv")
def admin_tests_run_csv(run_id: int, repo: Repository = Depends(user_repo)):
    from fastapi.responses import Response

    from gujrera.accuracy import run_csv

    text = _officer_or_403(run_csv, repo, run_id)
    return Response("\ufeff" + text, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="gujrera_test_run_{run_id}.csv"'})

