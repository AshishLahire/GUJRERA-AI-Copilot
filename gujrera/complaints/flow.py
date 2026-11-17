"""Conversational complaint filing and tracking.

Filing asks only for what is still missing, in this order:
    project → description → category → relief → name → mobile → email (optional)
    → unit (optional) → consent → review → submit
Category is guessed from the description and confirmed at review; the form
(A or B) follows from the relief. Nothing is submitted without explicit
consent and a final "Submit".

Tracking needs the reference number and the 6-digit tracking code given at
filing. Three wrong codes for a reference lock it for the session.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from gujrera.chat.understand import understand
from gujrera.complaints.adapter import ComplaintAdapter, ComplaintDraft, MockComplaintAdapter
from gujrera.complaints.rules import (
    DEFAULT_RELIEF,
    PRIORITY,
    classify,
    clean_email,
    clean_mobile,
    clean_name,
    is_cancel,
    is_skip,
    match_relief,
)
from gujrera.complaints.strings import label, s
from gujrera.db.models import RELIEFS, Project
from gujrera.db.repository import AccessDenied, Repository
from gujrera.i18n import fmt_date, word
from gujrera.profile.summarise import Sentence

REF_RE = re.compile(r"\b((?:MOCK|DEMO)-CMP-\d{4}-\d{5})\b", re.IGNORECASE)
CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
YES = {"yes", "y", "ok", "agree", "i agree", "haan", "ha", "હા", "હા, હું સંમત છું", "हाँ", "हां", "हाँ, मैं सहमत हूँ"}
NO = {"no", "n", "nahi", "ના", "नहीं"}
SUBMIT = {"submit", "submit complaint", "send", "મોકલો", "ફરિયાદ મોકલો", "जमा करें", "शिकायत जमा करें"}
EDIT = {"edit", "change", "change something", "બદલો", "કંઈક બદલો", "बदलें", "कुछ बदलें"}
FIELDS = ("project", "description", "category", "relief", "name", "mobile", "email", "unit")
OPTIONAL = ("email", "unit")
MAX_CODE_ATTEMPTS = 3


@dataclass
class FlowOut:
    intent: str
    sentences: list[Sentence]
    cards: list[dict[str, Any]] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FilingState:
    draft: ComplaintDraft = field(default_factory=ComplaintDraft)
    awaiting: str | None = None
    options: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TrackingState:
    ref: str | None = None
    awaiting: str = "ref"
    failures: dict[str, int] = field(default_factory=dict)


def _say(key: str, lang: str, **values: Any) -> Sentence:
    return Sentence(s(key, lang, **values), [], f"complaint_{key}")


def _opts(pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"n": i, "kind": "choice", "id": value, "label": text} for i, (value, text) in enumerate(pairs, 1)]


def _choice(message: str, options: list[dict[str, Any]]) -> str | None:
    msg = (message or "").strip()
    m = re.fullmatch(r"(\d)\s*[.)]?", msg)
    if m:
        hit = next((o for o in options if o["n"] == int(m.group(1))), None)
        return hit["id"] if hit else None
    lowered = msg.lower()
    hit = next((o for o in options if o["label"].lower() == lowered or str(o["id"]) == lowered), None)
    return hit["id"] if hit else None


def adapter_for(session: Session) -> ComplaintAdapter:
    return MockComplaintAdapter(session)


# ------------------------------------------------------------------ filing
def start_filing(message: str, state: Any, repo: Repository, lang: str) -> FlowOut:
    flow = FilingState()
    state.complaint = flow
    d = flow.draft
    if repo.p.role == "citizen" and repo.p.user_id is not None:
        d.user_id = repo.p.user_id
    if state.entity and state.entity.get("kind") == "project":
        d.project_id = state.entity["id"]
    u = understand(repo.s, message)
    projects = [c for c in u.candidates if c.kind == "project"]
    if u.project_numbers:
        found = repo.get_project(u.project_numbers[0].normalised)
        if found:
            d.project_id = found["id"]
    elif len(projects) == 1:
        d.project_id = projects[0].id
    # A long first message is the complainant's story.
    story = re.sub(r"(?i)\b(i want to|i would like to|please)?\s*(file|register|lodge)\s+a\s+complaint\b", "",
                   message).strip(" .,:;-")
    if len(story) >= 40:
        d.description = story
        cats = classify(story)
        d.category = cats[0] if cats else None
    out = _ask_next(flow, repo, lang)
    understood: list[Sentence] = [_say("start", lang)]
    if d.project_id and flow.awaiting != "description":  # the description prompt already names the project
        understood.append(_project_line(d, repo, lang))
    if d.category:
        understood.append(_say("category_guess", lang, category=label(d.category, lang)))
    out.sentences[:0] = understood
    return out


def continue_filing(message: str, state: Any, repo: Repository, lang: str) -> FlowOut:
    flow: FilingState = state.complaint
    d = flow.draft
    if is_cancel(message) or (flow.awaiting == "review" and _choice(message, flow.options) == "cancel"):
        state.complaint = None
        return FlowOut("complaint_cancelled", [_say("cancelled", lang)])

    field_ = flow.awaiting
    error: str | None = None
    if field_ == "project":
        error = _take_project(message, flow, repo, lang)
        if error == "_options":
            return FlowOut("complaint_filing", [_say("pick_project", lang)], options=flow.options)
    elif field_ == "description":
        text = (message or "").strip()
        if len(text) < 15 or len(text.split()) < 3:
            error = "short_description"
        else:
            d.description = text
            if not d.category:
                cats = classify(text)
                d.category = cats[0] if cats else None
    elif field_ == "category":
        value = _choice(message, flow.options) or (classify(message) or [None])[0]
        if value:
            d.category = value
        else:
            error = "ask_category"
    elif field_ == "relief":
        value = _choice(message, flow.options) or match_relief(message)
        if value:
            d.relief = value
        else:
            error = "ask_relief"
    elif field_ == "name":
        d.name = clean_name(message)
        error = None if d.name else "bad_name"
    elif field_ == "mobile":
        d.mobile = clean_mobile(message)
        error = None if d.mobile else "bad_mobile"
    elif field_ in OPTIONAL:
        if is_skip(message) or _choice(message, flow.options) == "skip":
            d.skipped.add(field_)
        elif field_ == "email":
            d.email = clean_email(message)
            error = None if d.email else "bad_email"
        else:
            d.unit = (message or "").strip()[:30] or None
    elif field_ == "consent":
        answer = _choice(message, flow.options) or (message or "").strip().lower()
        if answer in ("yes", *YES):
            d.consent = True
        elif answer in ("no", *NO):
            state.complaint = None
            return FlowOut("complaint_cancelled", [_say("no_consent", lang)])
        else:
            error = "ask_consent"
    elif field_ == "review":
        answer = _choice(message, flow.options) or (message or "").strip().lower()
        if answer in ("submit", *SUBMIT):
            return _submit(state, repo, lang)
        if answer in ("edit", *EDIT):
            flow.awaiting = "edit"
            flow.options = _opts([(f, label(f"f_{f}", lang)) for f in FIELDS])
            return FlowOut("complaint_filing", [_say("ask_edit", lang)], options=flow.options)
        return _review(flow, repo, lang)
    elif field_ == "edit":
        target = _choice(message, flow.options)
        if target is None:
            return FlowOut("complaint_filing", [_say("ask_edit", lang)], options=flow.options)
        d.skipped.discard(target)
        setattr(d, "project_id" if target == "project" else target, None)

    if error:
        out = _ask_next(flow, repo, lang)
        if error not in ("ask_category", "ask_relief", "ask_consent"):
            out.sentences.insert(0, _say(error, lang))
        return out
    return _ask_next(flow, repo, lang)


def _take_project(message: str, flow: FilingState, repo: Repository, lang: str) -> str | None:
    chosen = _choice(message, flow.options) if flow.options else None
    if chosen:
        flow.draft.project_id = int(chosen)
        flow.options = []
        return None
    u = understand(repo.s, message)
    if u.project_numbers:
        found = repo.get_project(u.project_numbers[0].normalised)
        if found:
            flow.draft.project_id = found["id"]
            return None
        return "project_not_found"
    projects = [c for c in u.candidates if c.kind == "project"]
    for c in u.candidates:
        if c.kind == "promoter":
            projects += [type(c)("project", p["id"], p["name"], 100, p["district"])
                         for p in repo.promoter_projects(c.id)]
    if len(projects) == 1:
        flow.draft.project_id = projects[0].id
        return None
    if projects:
        flow.options = _opts([(str(p.id), f"{p.label} · {word(p.district, lang)}") for p in projects[:6]])
        return "_options"
    return "project_not_found"


def _next_missing(d: ComplaintDraft) -> str:
    if not d.project_id:
        return "project"
    if not d.description:
        return "description"
    if not d.category:
        return "category"
    if not d.relief:
        return "relief"
    if not d.name:
        return "name"
    if not d.mobile:
        return "mobile"
    for f in OPTIONAL:
        if getattr(d, f) is None and f not in d.skipped:
            return f
    if not d.consent:
        return "consent"
    return "review"


def _ask_next(flow: FilingState, repo: Repository, lang: str) -> FlowOut:
    d = flow.draft
    step = _next_missing(d)
    flow.awaiting, flow.options = step, []
    if step == "review":
        return _review(flow, repo, lang)
    sentences: list[Sentence] = []
    if step == "project":
        sentences.append(_say("ask_project", lang))
    elif step == "description":
        sentences.append(_project_line(d, repo, lang))
        sentences.append(_say("ask_description", lang))
    elif step == "category":
        flow.options = _opts([(c, label(c, lang)) for c in PRIORITY])
        sentences.append(_say("ask_category", lang))
    elif step == "relief":
        default = DEFAULT_RELIEF.get(d.category or "")
        ordered = ([default] if default else []) + [r for r in RELIEFS if r != default]
        flow.options = _opts([(r, label(r, lang)) for r in ordered])
        sentences.append(_say("ask_relief", lang))
    elif step in ("name", "mobile"):
        sentences.append(_say(f"ask_{step}", lang))
    elif step in OPTIONAL:
        flow.options = _opts([("skip", label("skip", lang))])
        sentences.append(_say(f"ask_{step}", lang))
    elif step == "consent":
        flow.options = _opts([("yes", label("yes", lang)), ("no", label("no", lang))])
        sentences.append(_say("ask_consent", lang))
    return FlowOut("complaint_filing", sentences, options=flow.options)


def _project_line(d: ComplaintDraft, repo: Repository, lang: str) -> Sentence:
    p = repo.s.get(Project, d.project_id)
    name = (p.name_gu if lang == "gu" and p.name_gu else p.name)
    return Sentence(s("project_ok", lang, name=name, rera=p.rera_no),
                    [{"type": "project", "id": p.rera_no, "is_mock": p.is_mock}], "complaint_project_ok")


def _review(flow: FilingState, repo: Repository, lang: str) -> FlowOut:
    d = flow.draft
    flow.awaiting = "review"
    flow.options = _opts([("submit", label("submit", lang)), ("edit", label("edit", lang)),
                          ("cancel", label("cancel", lang))])
    p = repo.s.get(Project, d.project_id)
    card = {
        "type": "complaint_draft", "form": d.form,
        "fields": [
            {"key": "project", "label": label("f_project", lang), "value": f"{p.name} ({p.rera_no})"},
            {"key": "category", "label": label("f_category", lang), "value": label(d.category, lang)},
            {"key": "relief", "label": label("f_relief", lang), "value": label(d.relief, lang)},
            {"key": "description", "label": label("f_description", lang), "value": d.description},
            {"key": "name", "label": label("f_name", lang), "value": d.name},
            {"key": "mobile", "label": label("f_mobile", lang), "value": d.mobile},
            {"key": "email", "label": label("f_email", lang), "value": d.email or "—"},
            {"key": "unit", "label": label("f_unit", lang), "value": d.unit or "—"},
        ],
        "is_mock": True,
    }
    note = "form_b_note" if d.form == "B" else "form_a_note"
    return FlowOut("complaint_review", [_say("review", lang, form=d.form), _say(note, lang)],
                   cards=[card], options=flow.options)


def _submit(state: Any, repo: Repository, lang: str) -> FlowOut:
    flow: FilingState = state.complaint
    result = adapter_for(repo.s).submit(flow.draft)
    state.complaint = None
    card = {"type": "complaint_submitted", "ref_no": result.ref_no, "tracking_code": result.tracking_code,
            "form": result.form, "is_mock": result.is_mock}
    sentences = [_say("submitted", lang, ref=result.ref_no, code=result.tracking_code)]
    if result.is_mock:
        sentences.append(_say("mock_note", lang))
    return FlowOut("complaint_submitted", sentences, cards=[card])


# ---------------------------------------------------------------- tracking
def wants_tracking(message: str) -> bool:
    lc = (message or "").lower()
    return bool(REF_RE.search(message or "")) or any(
        w in lc for w in ("status", "track", "my complaint", "સ્થિતિ", "મારી ફરિયાદ", "स्थिति", "मेरी शिकायत",
                          "ट्रैक", "ટ્રેક"))


def start_tracking(message: str, state: Any, repo: Repository, lang: str) -> FlowOut:
    state.tracking = state.tracking or TrackingState()
    state.tracking.ref, state.tracking.awaiting = None, "ref"
    return continue_tracking(message, state, repo, lang)


def continue_tracking(message: str, state: Any, repo: Repository, lang: str) -> FlowOut:
    t: TrackingState = state.tracking
    adapter = adapter_for(repo.s)
    m = REF_RE.search(message or "")
    if m:
        t.ref, t.awaiting = m.group(1).upper(), "code"
    if t.ref is None:
        return FlowOut("complaint_tracking", [_say("ask_ref", lang)])
    if t.failures.get(t.ref, 0) >= MAX_CODE_ATTEMPTS:
        return FlowOut("complaint_tracking", [_say("locked", lang)])
    own = _own_complaint(repo, t.ref)
    if own is not None:  # logged-in complainant: no code needed
        state.tracking = None
        return _status_out(own["ref_no"], own["category"], own["form"], own["filed_on"], own["status"],
                           None, own["events"], own["source"]["is_mock"], lang)
    has_code = adapter.has_tracking_code(t.ref)
    if has_code is None:
        ref, t.ref = t.ref, None
        return FlowOut("complaint_tracking", [_say("unknown_ref", lang, ref=ref)])
    if not has_code:
        ref, t.ref = t.ref, None
        return FlowOut("complaint_tracking", [_say("no_code_on_record", lang, ref=ref)])
    code = CODE_RE.search(REF_RE.sub(" ", message or ""))
    if not code:
        return FlowOut("complaint_tracking", [_say("ask_code", lang, ref=t.ref)])
    status = adapter.status(t.ref, code.group(1))
    if status is None:
        t.failures[t.ref] = t.failures.get(t.ref, 0) + 1
        left = MAX_CODE_ATTEMPTS - t.failures[t.ref]
        if left <= 0:
            return FlowOut("complaint_tracking", [_say("locked", lang)])
        return FlowOut("complaint_tracking", [_say("bad_code", lang, left=left)])
    state.tracking = None
    return _status_out(status.ref_no, status.category, status.form, status.filed_on, status.status,
                       status.project_name, status.events, status.is_mock, lang)


def _own_complaint(repo: Repository, ref: str) -> dict[str, Any] | None:
    if repo.p.role != "citizen" or repo.p.user_id is None:
        return None
    try:
        return repo.complaint_status(ref)
    except AccessDenied:
        return None


def _status_out(ref: str, category: str, form: str, filed_on, status: str, project_name: str | None,
                events: list[dict[str, Any]], is_mock: bool, lang: str) -> FlowOut:
    sentence = Sentence(
        s("status", lang, ref=ref, category=label(category, lang), form=form,
          filed=fmt_date(filed_on, lang), status=label(status, lang)),
        [{"type": "complaint", "id": ref, "is_mock": is_mock}], "complaint_status")
    card = {"type": "complaint_status", "ref_no": ref, "project_name": project_name,
            "status": status, "status_label": label(status, lang),
            "events": [{"at": e["at"], "status": label(e["status"], lang), "note": e["note"]} for e in events],
            "is_mock": is_mock}
    sentences = [sentence] + ([_say("mock_note", lang)] if is_mock else [])
    return FlowOut("complaint_status", sentences, cards=[card])


def my_complaints(repo: Repository, lang: str) -> FlowOut:
    """All complaints filed by the logged-in citizen (repository-scoped)."""
    rows = repo.list_complaints(limit=20)
    if not rows:
        return FlowOut("complaint_list", [_say("none_mine", lang)])
    sentences = [Sentence(
        s("status", lang, ref=c["ref_no"], category=label(c["category"], lang), form=c["form"],
          filed=fmt_date(c["filed_on"], lang), status=label(c["status"], lang)),
        [c["source"]], "complaint_status") for c in rows]
    if any(c["source"]["is_mock"] for c in rows):
        sentences.append(_say("mock_note", lang))
    return FlowOut("complaint_list", sentences)
