"""Accuracy console: a test set, runs that score it, and feedback from users that grows it.

* **Feedback.** Anyone can mark an answer 👍 or 👎 with a reason. Down-votes go to a review queue where a
  state-level officer (the POC admin) turns one into a test case in a click, with what the right answer
  must contain, or dismisses it.
* **Test set.** Cases come from three places: generated from the loaded registry (the same templates as the
  300 gold questions, so the right answer is known exactly), imported from the department's test set (CSV
  or JSON), or added from feedback. A case can check the intent, text the answer must and must not contain,
  a cited source and the answer's language. A case with no check (only the department's model answer, say)
  is run and shown for review by hand, never counted as passed.
* **Runs.** A run answers every active case as a citizen or a statewide officer would be answered, in the
  background, and keeps every result: accuracy overall and by language, category and role, response times,
  and each failure with its reasons. Runs are kept, so accuracy can be reported week by week in the POC.
"""

from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from gujrera.db.models import AnswerFeedback, AppSetting, AuditLog, TestCase, TestResult, TestRun, User
from gujrera.db.repository import AccessDenied, Principal, Repository

REASONS = ("wrong_answer", "wrong_project", "should_have_found", "not_relevant", "unclear", "wrong_language",
           "other")
ROLES = ("citizen", "officer")
_GU_DIGITS = str.maketrans("૦૧૨૩૪૫૬૭૮૯०१२३४५६७८९", "01234567890123456789")
_RUNNING: dict[str, int] = {}  # database url -> running run id
_LOCK = threading.Lock()


def require_admin(repo: Repository) -> None:
    if repo.p.role != "officer" or repo.p.district_scope:
        raise AccessDenied("The accuracy console is for state-level GUJRERA officers.")


def _username(repo: Repository) -> str | None:
    u = repo.s.get(User, repo.p.user_id) if repo.p.user_id else None
    return u.username if u else None


def _list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip() for p in str(value).split(";") if p.strip()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(_GU_DIGITS)).strip().lower()


# ------------------------------------------------------------------ feedback
def give_feedback(repo: Repository, *, question: str, answer: str, rating: str, reason: str | None = None,
                  comment: str | None = None, intent: str | None = None, lang: str | None = None,
                  sources: list[str] | None = None, surface: str = "chat") -> dict[str, Any]:
    if rating not in ("up", "down"):
        raise ValueError("rating must be up or down")
    if reason and reason not in REASONS:
        raise ValueError(f"reason must be one of {', '.join(REASONS)}")
    if not (question or "").strip():
        raise ValueError("The question is missing.")
    fb = AnswerFeedback(at=datetime.now(), user_id=repo.p.user_id, role=repo.p.role,
                        surface=surface if surface in ("chat", "report") else "chat", lang=(lang or None),
                        question=question.strip()[:1000], answer=(answer or "")[:4000], intent=(intent or None),
                        sources=json.dumps([str(x)[:200] for x in (sources or [])][:10], ensure_ascii=False),
                        rating=rating, reason=reason, comment=(comment or "").strip()[:1000] or None,
                        status="new" if rating == "down" else "noted")
    repo.s.add(fb)
    repo.s.flush()
    return {"id": fb.id, "status": fb.status}


def _fb_dict(f: AnswerFeedback) -> dict[str, Any]:
    return {"id": f.id, "at": f.at.isoformat(timespec="minutes"), "role": f.role, "surface": f.surface,
            "lang": f.lang, "question": f.question, "answer": f.answer, "intent": f.intent,
            "sources": json.loads(f.sources or "[]"), "rating": f.rating, "reason": f.reason, "comment": f.comment,
            "status": f.status, "reviewed_by": f.reviewed_by}


def list_feedback(repo: Repository, status: str | None = "new", limit: int = 100) -> dict[str, Any]:
    require_admin(repo)
    stmt = select(AnswerFeedback)
    if status:
        stmt = stmt.where(AnswerFeedback.status == status)
    rows = repo.s.scalars(stmt.order_by(AnswerFeedback.at.desc()).limit(limit)).all()
    counts = dict(repo.s.execute(select(AnswerFeedback.status, func.count()).group_by(AnswerFeedback.status)).all())
    ratings = dict(repo.s.execute(select(AnswerFeedback.rating, func.count()).group_by(AnswerFeedback.rating)).all())
    reasons = dict(repo.s.execute(select(AnswerFeedback.reason, func.count()).where(AnswerFeedback.rating == "down")
                                  .group_by(AnswerFeedback.reason)).all())
    return {"feedback": [_fb_dict(f) for f in rows], "counts": counts, "ratings": ratings,
            "reasons": {k or "none": v for k, v in reasons.items()}}


def review_feedback(repo: Repository, fid: int, status: str) -> dict[str, Any]:
    require_admin(repo)
    f = repo.s.get(AnswerFeedback, fid)
    if f is None:
        raise ValueError("No such feedback.")
    if status not in ("dismissed", "new"):
        raise ValueError("status must be dismissed or new")
    f.status, f.reviewed_by, f.reviewed_at = status, _username(repo), datetime.now()
    repo.s.flush()
    return _fb_dict(f)


def feedback_to_case(repo: Repository, fid: int, *, must_contain: list[str] | str | None = None,
                     must_not_contain: list[str] | str | None = None, expect_intent: str | None = None,
                     expected_source: str | None = None, category: str | None = None,
                     note: str | None = None) -> dict[str, Any]:
    require_admin(repo)
    f = repo.s.get(AnswerFeedback, fid)
    if f is None:
        raise ValueError("No such feedback.")
    case = _new_case(repo, question=f.question, lang=f.lang, role="officer" if f.role == "officer" else "citizen",
                     expect_intent=expect_intent, must_contain=must_contain, must_not_contain=must_not_contain,
                     expected_source=expected_source, category=category or "from feedback", origin="feedback",
                     note=note or (f"User said: {f.reason or ''} {f.comment or ''}".strip()))
    f.status, f.reviewed_by, f.reviewed_at = "added", _username(repo), datetime.now()
    repo.s.flush()
    repo._audit("test_case_from_feedback", {"feedback": fid, "case": case["id"]})
    return case


# ------------------------------------------------------------------ test cases
def _case_dict(c: TestCase) -> dict[str, Any]:
    return {"id": c.id, "question": c.question, "lang": c.lang, "role": c.role,
            "expect_intent": c.expect_intent.split("|") if c.expect_intent else [],
            "must_contain": json.loads(c.must_contain or "[]"), "must_not_contain": json.loads(c.must_not_contain or "[]"),
            "expected_source": c.expected_source, "category": c.category, "origin": c.origin, "note": c.note,
            "active": c.active is not False, "judged": _judged(c)}


def _judged(c: TestCase) -> bool:
    return bool(c.expect_intent or json.loads(c.must_contain or "[]") or json.loads(c.must_not_contain or "[]")
                or c.expected_source)


def _new_case(repo: Repository, *, question: str, lang: str | None, role: str, expect_intent: Any,
              must_contain: Any, must_not_contain: Any, expected_source: str | None, category: str | None,
              origin: str, note: str | None) -> dict[str, Any]:
    question = (question or "").strip()
    if not question:
        raise ValueError("A test case needs a question.")
    role = (role or "citizen").strip().lower()
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    lang = (lang or "").strip().lower() or None
    if lang and lang not in ("gu", "hi", "en"):
        raise ValueError("lang must be gu, hi or en")
    intents = _list(expect_intent.replace("|", ";") if isinstance(expect_intent, str) else expect_intent)
    c = TestCase(question=question[:1000], lang=lang, role=role, expect_intent="|".join(intents) or None,
                 must_contain=json.dumps(_list(must_contain), ensure_ascii=False),
                 must_not_contain=json.dumps(_list(must_not_contain), ensure_ascii=False),
                 expected_source=(expected_source or "").strip()[:300] or None,
                 category=(category or "general").strip()[:60] or "general", origin=origin,
                 note=(note or "").strip()[:2000] or None, active=True, created_by=_username(repo),
                 created_at=datetime.now())
    repo.s.add(c)
    repo.s.flush()
    return _case_dict(c)


def list_cases(repo: Repository, origin: str | None = None, q: str | None = None, limit: int = 200) -> dict[str, Any]:
    require_admin(repo)
    stmt = select(TestCase)
    if origin:
        stmt = stmt.where(TestCase.origin == origin)
    if q:
        stmt = stmt.where(TestCase.question.like(f"%{q.strip()[:100]}%"))
    rows = repo.s.scalars(stmt.order_by(TestCase.id.desc()).limit(limit)).all()
    agg = repo.s.execute(select(TestCase.origin, TestCase.lang, TestCase.role, func.count())
                         .where(TestCase.active.is_not(False)).group_by(TestCase.origin, TestCase.lang, TestCase.role)).all()
    by_origin: dict[str, int] = defaultdict(int)
    by_lang: dict[str, int] = defaultdict(int)
    by_role: dict[str, int] = defaultdict(int)
    for o, l, r, n in agg:
        by_origin[o] += n
        by_lang[l or "any"] += n
        by_role[r] += n
    return {"cases": [_case_dict(c) for c in rows], "active": sum(by_origin.values()),
            "by_origin": dict(by_origin), "by_lang": dict(by_lang), "by_role": dict(by_role)}


def add_case(repo: Repository, **fields: Any) -> dict[str, Any]:
    require_admin(repo)
    case = _new_case(repo, origin="manual", **fields)
    repo._audit("test_case_added", {"case": case["id"]})
    return case


def set_case_active(repo: Repository, cid: int, active: bool) -> dict[str, Any]:
    require_admin(repo)
    c = repo.s.get(TestCase, cid)
    if c is None:
        raise ValueError("No such test case.")
    c.active = active
    repo.s.flush()
    return _case_dict(c)


def generate_cases(repo: Repository, per_language: int = 100) -> dict[str, Any]:
    """Questions built from the loaded registry (the gold-question templates); replaces earlier generated ones."""
    require_admin(repo)
    from gujrera.chat.gold import build_gold

    gold = build_gold(repo.s)
    keep: list = []
    seen: dict[str, int] = defaultdict(int)
    for g in gold:
        if seen[g.lang] < per_language:
            keep.append(g)
            seen[g.lang] += 1
    repo.s.query(TestCase).filter(TestCase.origin == "generated").delete()
    for g in keep:
        _new_case(repo, question=g.question, lang=g.lang, role="citizen", expect_intent=list(g.expect_intent),
                  must_contain=list(g.must_contain), must_not_contain=None, expected_source=None,
                  category=g.kind, origin="generated", note=None)
    repo._audit("test_cases_generated", {"n": len(keep)})
    return {"generated": len(keep), "by_lang": dict(seen)}


IMPORT_COLUMNS = {
    "question": ("question", "query", "prashna", "prashn", "q"),
    "lang": ("lang", "language", "bhasha"),
    "role": ("role", "user", "user_type", "assistant"),
    "expect_intent": ("expect_intent", "intent", "expected_intent"),
    "must_contain": ("must_contain", "expected_contains", "expected_facts", "key_facts", "contains"),
    "must_not_contain": ("must_not_contain", "not_contain", "should_not_contain"),
    "expected_source": ("expected_source", "source", "citation"),
    "category": ("category", "type", "topic"),
    "note": ("note", "expected_answer", "answer", "model_answer", "remarks"),
}


def import_cases(repo: Repository, filename: str, data: bytes) -> dict[str, Any]:
    """The department's test set as CSV or JSON. Columns: question (required), lang, role, expect_intent,
    must_contain and must_not_contain (separate several with ';'), expected_source, category, note (or
    expected_answer: kept for review by hand)."""
    require_admin(repo)
    name = (filename or "").lower()
    text = data.decode("utf-8-sig", errors="replace")
    if name.endswith(".json"):
        raw = json.loads(text)
        rows = raw if isinstance(raw, list) else raw.get("cases") or raw.get("questions") or []
    elif name.endswith(".csv"):
        rows = list(csv.DictReader(io.StringIO(text)))
    else:
        raise ValueError("Use a .csv or .json file.")
    if not rows:
        raise ValueError("The file has no rows.")

    def key(h: str) -> str:
        return re.sub(r"[^a-z_]", "", str(h).lower().replace(" ", "_"))

    headers = {key(h): h for h in rows[0].keys()}
    mapping = {field: next((headers[a] for a in aliases if a in headers), None) for field, aliases in IMPORT_COLUMNS.items()}
    if not mapping["question"]:
        raise ValueError("The file needs a 'question' column.")
    added, errors = 0, []
    for n, row in enumerate(rows, start=2):
        values = {f: (row.get(col) if col else None) for f, col in mapping.items()}
        role = (str(values["role"] or "citizen")).strip().lower()
        role = "officer" if role.startswith(("off", "auth", "adhik")) else "citizen"
        try:
            with repo.s.begin_nested():
                _new_case(repo, question=str(values["question"] or ""), lang=values["lang"], role=role,
                          expect_intent=values["expect_intent"] or None, must_contain=values["must_contain"],
                          must_not_contain=values["must_not_contain"], expected_source=values["expected_source"],
                          category=values["category"], origin="imported", note=values["note"])
            added += 1
        except (ValueError, TypeError) as exc:
            errors.append({"row": n, "error": str(exc)})
    repo._audit("test_cases_imported", {"file": filename, "added": added, "rejected": len(errors)})
    return {"added": added, "rejected": len(errors), "errors": errors[:50]}


# ------------------------------------------------------------------ POC measures
# How a reply ended, for "share of questions answered without a person". A clarifying question is
# answered by the user, not by a person at GUJRERA; "could not answer" would go to the helpdesk.
UNANSWERED = frozenset({"not_found", "out_of_scope", "legal_not_found", "legal_unavailable", "unknown", "error",
                        "analytics_unmatched", "analytics_refused", "login_required", "access_denied"})
CLARIFYING = frozenset({"need_entity", "disambiguate", "did_you_mean", "list_needed"})
SOCIAL = frozenset({"greeting", "thanks", "help"})  # not questions: left out of the share
CONSISTENCY_SAMPLE = 50


def outcome(intent: str | None) -> str | None:
    if not intent or intent in SOCIAL:
        return None
    if intent in UNANSWERED:
        return "unanswered"
    return "clarified" if intent in CLARIFYING else "answered"


def _outcomes(intents: list[str | None]) -> dict[str, Any]:
    counts = {"answered": 0, "clarified": 0, "unanswered": 0}
    for i in intents:
        o = outcome(i)
        if o:
            counts[o] += 1
    total = sum(counts.values())
    return {**counts, "total": total, "answered_pct": round(100 * counts["answered"] / total, 1) if total else None,
            "self_served_pct": round(100 * (counts["answered"] + counts["clarified"]) / total, 1) if total else None}


def _times(values: list[int]) -> dict[str, int]:
    v = sorted(values)
    return {"n": len(v), "p50": v[len(v) // 2] if v else 0, "p95": _p95(v), "max": v[-1] if v else 0}


def _signature(reply: dict[str, Any]) -> tuple[str, str]:
    """What must be the same when the same question is asked again: the intent and the words."""
    return reply.get("intent") or "", _norm(re.sub(r"\[\d+\]", "", reply.get("text") or ""))


def get_setting(s: Session, key: str) -> str | None:
    row = s.get(AppSetting, key)
    return row.value if row else None


def set_manual_report_minutes(repo: Repository, minutes: float | None) -> dict[str, Any]:
    """The department's own figure: minutes an officer takes to prepare a report by hand."""
    require_admin(repo)
    if minutes is not None and not (0 < minutes <= 60 * 24 * 30):
        raise ValueError("Give the manual time in minutes, between 1 minute and 30 days.")
    row = repo.s.get(AppSetting, "manual_report_minutes")
    if minutes is None:
        if row:
            repo.s.delete(row)
    else:
        if row is None:
            row = AppSetting(key="manual_report_minutes", value="")
            repo.s.add(row)
        row.value, row.updated_at, row.updated_by = str(minutes), datetime.now(), _username(repo)
    repo.s.flush()
    repo._audit("poc_setting_changed", {"manual_report_minutes": minutes})
    return poc_metrics(repo)


def poc_metrics(repo: Repository, days: int = 30) -> dict[str, Any]:
    """The POC scope's measures: from real use in the last `days` days and from the latest test run."""
    require_admin(repo)
    since = datetime.now() - timedelta(days=days)
    rows = repo.s.execute(select(AuditLog.role, AuditLog.action, AuditLog.detail)
                          .where(AuditLog.action.in_(("chat_reply", "analytics_query")), AuditLog.at >= since)).all()
    intents: dict[str, list[str | None]] = defaultdict(list)
    chat_ms: dict[str, list[int]] = defaultdict(list)
    report_ms: list[int] = []
    ai_understood = 0
    for role, action, detail in rows:
        d = json.loads(detail or "{}")
        if action == "analytics_query":
            if "ms" in d:
                report_ms.append(int(d["ms"]))
            continue
        who = "officer" if role == "officer" else "citizen"
        intents[who].append(d.get("intent"))
        intents["all"].append(d.get("intent"))
        if "ms" in d:
            chat_ms[who].append(int(d["ms"]))
            chat_ms["all"].append(int(d["ms"]))
        ai_understood += d.get("by") == "llm"
    latest = repo.s.scalar(select(TestRun).where(TestRun.status == "done").order_by(TestRun.id.desc()).limit(1))
    summary = json.loads(latest.summary) if latest and latest.summary else {}
    manual = get_setting(repo.s, "manual_report_minutes")
    manual_min = float(manual) if manual else None
    live_reports = _times(report_ms)
    speedup = None
    if manual_min and live_reports["n"] and live_reports["p50"]:
        speedup = round(manual_min * 60000 / max(live_reports["p50"], 1))
    return {
        "days": days,
        "live": {"questions": len(intents["all"]), "outcomes": {k: _outcomes(v) for k, v in intents.items()},
                 "response_ms": {k: _times(v) for k, v in chat_ms.items()},
                 "understood_by_ai": ai_understood, "reports": live_reports},
        "test_run": {"id": latest.id if latest else None,
                     "finished_at": latest.finished_at.isoformat(timespec="minutes") if latest and latest.finished_at else None,
                     "outcomes": summary.get("outcomes"), "latency_by_role": summary.get("latency_by_role"),
                     "consistency": summary.get("consistency")},
        "manual_report_minutes": manual_min,
        "report_speedup": speedup,  # times faster than by hand, at the median
        "targets": {"citizen_p95_ms": 3000, "consistency_pct": 98},
    }


# ------------------------------------------------------------------ judging and runs
def judge(case: TestCase, reply: dict[str, Any]) -> tuple[bool | None, list[str]]:
    if not _judged(case):
        return None, []
    problems = []
    text = _norm(reply.get("text") or "")
    intents = case.expect_intent.split("|") if case.expect_intent else []
    if intents and reply.get("intent") not in intents:
        problems.append(f"intent was {reply.get('intent')}, expected {' or '.join(intents)}")
    if case.lang and reply.get("lang") and reply["lang"] != case.lang:
        problems.append(f"answered in {reply['lang']}, expected {case.lang}")
    for fact in json.loads(case.must_contain or "[]"):
        if _norm(fact) not in text:
            problems.append(f"missing “{fact}”")
    for bad in json.loads(case.must_not_contain or "[]"):
        if _norm(bad) in text:
            problems.append(f"should not say “{bad}”")
    if case.expected_source:
        ids = " ".join(str(s.get("id", "")) for s in reply.get("sources") or [])
        if _norm(case.expected_source) not in _norm(ids):
            problems.append(f"did not cite {case.expected_source}")
    return not problems, problems


def _answer(s: Session, case: TestCase) -> dict[str, Any]:
    from gujrera.chat.orchestrator import ChatState, respond

    principal = Principal(user_id=None, role="officer") if case.role == "officer" else Principal.anonymous()
    repo = Repository(s, principal, audit_sink=lambda _row: None)  # test runs do not fill the audit log
    return respond(case.question, ChatState(), repo).to_dict()  # the language is detected, as for real users


def _p95(values: list[int]) -> int:
    v = sorted(values)
    return v[int(0.95 * (len(v) - 1))] if v else 0


def _write(factory: Any, fn: Callable[[Session], None], attempts: int = 30) -> None:
    """Write in a short transaction of its own, retrying while the app is writing too.

    SQLite in WAL mode refuses a write at once ("database is locked") when the writing transaction began
    reading before another connection committed, whatever the busy timeout. Starting fresh avoids that;
    retrying covers the rest.
    """
    for attempt in range(attempts):
        with factory() as w:
            try:
                fn(w)
                w.commit()
                return
            except OperationalError as exc:
                w.rollback()
                if "locked" not in str(exc).lower() or attempt == attempts - 1:
                    raise
        time.sleep(min(0.2 * (attempt + 1), 2.0))


def _ask(s: Session, case: TestCase) -> dict[str, Any]:
    """Answer one case and keep nothing it wrote (a complaint draft, say); end the read transaction too,
    so the run never holds an old snapshot while the app writes."""
    try:
        with s.begin_nested():
            reply = _answer(s, case)
            raise _Rollback(reply)
    except _Rollback as rb:
        reply = rb.reply
    except Exception as exc:  # noqa: BLE001 - a crash is a failed case, not a failed run
        reply = {"intent": "error", "text": f"Error: {exc.__class__.__name__}: {exc}"[:500], "sources": []}
    finally:
        s.rollback()
    return reply


def _execute(url: str, run_id: int) -> None:
    from gujrera.db.session import make_engine, session_factory

    engine = make_engine(url)
    factory = session_factory(engine)
    try:
        with factory() as s:
            cases = s.scalars(select(TestCase).where(TestCase.active.is_not(False)).order_by(TestCase.id)).all()
            s.expunge_all()  # plain records from here on: a rollback must not expire them
            s.rollback()

            def _set_total(w: Session) -> None:
                w.get(TestRun, run_id).total = len(cases)

            _write(factory, _set_total)
            buckets: dict[str, dict[str, list]] = {"lang": defaultdict(list), "category": defaultdict(list),
                                                    "role": defaultdict(list), "origin": defaultdict(list)}
            times: list[int] = []
            role_times: dict[str, list[int]] = defaultdict(list)
            role_intents: dict[str, list[str | None]] = defaultdict(list)
            first: dict[int, tuple[str, str]] = {}
            pending: list[dict[str, Any]] = []
            passed = unjudged = 0
            for i, case in enumerate(cases, 1):
                t0 = time.perf_counter()
                reply = _ask(s, case)
                ms = int((time.perf_counter() - t0) * 1000)
                ok, problems = judge(case, reply) if reply.get("intent") != "error" else (False, [reply["text"]])
                times.append(ms)
                role_times[case.role].append(ms)
                role_intents[case.role].append(reply.get("intent"))
                role_intents["all"].append(reply.get("intent"))
                first[case.id] = _signature(reply)
                if ok is None:
                    unjudged += 1
                elif ok:
                    passed += 1
                for dim, value in (("lang", case.lang or "any"), ("category", case.category), ("role", case.role),
                                   ("origin", case.origin)):
                    buckets[dim][value].append(ok)
                pending.append(dict(run_id=run_id, case_id=case.id, passed=ok, intent=reply.get("intent"),
                                    lang=reply.get("lang"), answer=(reply.get("text") or "")[:3000],
                                    sources=json.dumps([x.get("id") for x in reply.get("sources") or []][:6],
                                                       ensure_ascii=False),
                                    problems=json.dumps(problems, ensure_ascii=False), ms=ms))
                if i % 10 == 0 or i == len(cases):
                    batch, progress = list(pending), (i, passed, unjudged)

                    def _save(w: Session, batch=batch, progress=progress) -> None:
                        w.add_all(TestResult(**r) for r in batch)
                        run = w.get(TestRun, run_id)
                        run.done, run.passed, run.unjudged = progress

                    _write(factory, _save)
                    pending.clear()
            summary = {dim: {k: {"total": len(v), "judged": sum(x is not None for x in v),
                                 "passed": sum(x is True for x in v)} for k, v in b.items()}
                       for dim, b in buckets.items()}
            summary["latency_ms"] = {"p50": sorted(times)[len(times) // 2] if times else 0,
                                     "p95": _p95(times), "max": max(times) if times else 0}
            summary["latency_by_role"] = {k: _times(v) for k, v in role_times.items()}
            summary["outcomes"] = {k: _outcomes(v) for k, v in role_intents.items()}
            # Consistency: ask a spread sample again and compare intent and wording.
            sample = cases[:: max(1, len(cases) // CONSISTENCY_SAMPLE)][:CONSISTENCY_SAMPLE]
            same, differing = 0, []
            for case in sample:
                if _signature(_ask(s, case)) == first.get(case.id):
                    same += 1
                else:
                    differing.append(case.id)
            summary["consistency"] = {"checked": len(sample), "same": same, "differing": differing[:20],
                                      "pct": round(100 * same / len(sample), 1) if sample else None}

            def _finish(w: Session) -> None:
                run = w.get(TestRun, run_id)
                run.done, run.passed, run.unjudged = len(cases), passed, unjudged
                run.summary = json.dumps(summary)
                run.status, run.finished_at = "done", datetime.now()

            _write(factory, _finish)
    except Exception as exc:  # noqa: BLE001
        reason = f"{exc.__class__.__name__}: {exc}"[:500]

        def _failed(w: Session) -> None:
            run = w.get(TestRun, run_id)
            if run:  # keep the reason, so a failed run can be explained
                run.status, run.finished_at = "failed", datetime.now()
                run.summary = json.dumps({"error": reason})

        try:
            _write(factory, _failed)
        except Exception:  # noqa: BLE001 - nothing more can be done; the run stays "running" in the list
            pass
    finally:
        with _LOCK:
            _RUNNING.pop(url, None)
        engine.dispose()


class _Rollback(Exception):
    def __init__(self, reply: dict[str, Any]):
        super().__init__("rollback")
        self.reply = reply


def start_run(repo: Repository, *, wait: bool = False) -> dict[str, Any]:
    require_admin(repo)
    url = repo.s.get_bind().url.render_as_string(hide_password=False)
    with _LOCK:
        if url in _RUNNING:
            raise ValueError("A run is already in progress.")
        n = repo.s.scalar(select(func.count()).select_from(TestCase).where(TestCase.active.is_not(False)))
        if not n:
            raise ValueError("There are no active test cases: generate, import or add some first.")
        run = TestRun(started_at=datetime.now(), started_by=_username(repo), status="running", total=n)
        repo.s.add(run)
        repo.s.commit()
        _RUNNING[url] = run.id
    repo._audit("test_run_started", {"run": run.id, "cases": n})
    t = threading.Thread(target=_execute, args=(url, run.id), daemon=True)
    t.start()
    if wait:
        t.join()
        repo.s.expire_all()
    return run_detail(repo, run.id)


def _run_dict(r: TestRun) -> dict[str, Any]:
    judged = r.done - r.unjudged
    return {"id": r.id, "status": r.status, "started_at": r.started_at.isoformat(timespec="minutes"),
            "finished_at": r.finished_at.isoformat(timespec="minutes") if r.finished_at else None,
            "started_by": r.started_by, "total": r.total, "done": r.done, "passed": r.passed, "unjudged": r.unjudged,
            "judged": judged, "accuracy": round(100 * r.passed / judged, 1) if judged else None,
            "summary": json.loads(r.summary) if r.summary else None}


def list_runs(repo: Repository, limit: int = 20) -> dict[str, Any]:
    require_admin(repo)
    rows = repo.s.scalars(select(TestRun).order_by(TestRun.id.desc()).limit(limit)).all()
    return {"runs": [_run_dict(r) for r in rows]}


def run_detail(repo: Repository, run_id: int, *, show: str = "failed", limit: int = 200) -> dict[str, Any]:
    require_admin(repo)
    r = repo.s.get(TestRun, run_id)
    if r is None:
        raise ValueError("No such run.")
    stmt = select(TestResult, TestCase).join(TestCase, TestCase.id == TestResult.case_id).where(TestResult.run_id == run_id)
    if show == "failed":
        stmt = stmt.where(TestResult.passed.is_(False))
    elif show == "unjudged":
        stmt = stmt.where(TestResult.passed.is_(None))
    rows = repo.s.execute(stmt.order_by(TestResult.id).limit(limit)).all()
    return {"run": _run_dict(r), "results": [
        {"case_id": c.id, "question": c.question, "lang": c.lang, "role": c.role, "category": c.category,
         "origin": c.origin, "passed": res.passed, "intent": res.intent, "answer": res.answer,
         "sources": json.loads(res.sources or "[]"), "problems": json.loads(res.problems or "[]"), "ms": res.ms,
         "expected": {"intent": c.expect_intent, "must_contain": json.loads(c.must_contain or "[]"),
                      "expected_source": c.expected_source, "note": c.note}}
        for res, c in rows]}


def run_csv(repo: Repository, run_id: int) -> str:
    data = run_detail(repo, run_id, show="all", limit=100000)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["case", "question", "lang", "role", "category", "origin", "result", "problems", "intent", "ms", "answer"])
    for x in data["results"]:
        result = "pass" if x["passed"] else "review" if x["passed"] is None else "fail"
        w.writerow([x["case_id"], x["question"], x["lang"] or "", x["role"], x["category"], x["origin"], result,
                    "; ".join(x["problems"]), x["intent"] or "", x["ms"], x["answer"]])
    return out.getvalue()
