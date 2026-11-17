"""Chat orchestrator: one message in, one cited answer out.

Flow: understand the message (language, intents, entities) → pick a skill
(trust check, project/promoter/agent profile, possession answer) → build the
answer from registry templates → number the citations → optionally let a
local LLM rephrase it, keeping the answer only if the citation guard passes.

Facts never come from a model. If no record supports an answer, the reply says
so ("not found") instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from gujrera.db.models import Project
from gujrera.db.repository import Repository
from gujrera.i18n import t, word
from gujrera.profile.summarise import Profile, Sentence, agent_profile, project_profile, promoter_profile
from gujrera.analytics.engine import answer as analytics_answer
from gujrera.analytics.engine import s as analytics_text
from gujrera.analytics.reports import looks_like_analytics, match_report
from gujrera.analytics.reports import ANALYTICS_CUES
from gujrera.chat.llm_router import Routed
from gujrera.chat.llm_router import route as llm_route
from gujrera.chat.understand import Candidate, Understanding, find_candidates, suggest_names, understand
from gujrera.legal.answer import answer as legal_answer
from gujrera.complaints.flow import (
    CODE_RE,
    REF_RE,
    FlowOut,
    continue_filing,
    continue_tracking,
    my_complaints,
    start_filing,
    start_tracking,
    wants_tracking,
)
from gujrera.selfservice.summary import agent_summary, focus_of, is_self_service, promoter_summary
from gujrera.selfservice.summary import s as ss
from gujrera.trust.checks import check_text

SUGGESTIONS = {
    "project": {
        "en": ["When will I get possession?", "Who is the builder?", "Any complaints?", "File a complaint"],
        "gu": ["પઝેશન ક્યારે મળશે?", "બિલ્ડર કોણ છે?", "કોઈ ફરિયાદ છે?", "ફરિયાદ નોંધાવો"],
        "hi": ["पज़ेशन कब मिलेगा?", "बिल्डर कौन है?", "कोई शिकायत है?", "शिकायत दर्ज करें"],
    },
    "promoter": {
        "en": ["Show the delayed projects", "Any penalty orders?"],
        "gu": ["વિલંબિત પ્રોજેક્ટ બતાવો", "કોઈ દંડના આદેશ છે?"],
        "hi": ["देरी वाले प्रोजेक्ट दिखाएँ", "कोई दंड आदेश है?"],
    },
    "start": {
        "en": ["File a complaint", "Track my complaint"],
        "gu": ["ફરિયાદ નોંધાવો", "મારી ફરિયાદની સ્થિતિ"],
        "hi": ["शिकायत दर्ज करें", "मेरी शिकायत की स्थिति"],
    },
}


# Tests replace these with fakes; None means "use the configured self-hosted LLM".
analytics_generate = None
router_generate = None


@dataclass
class ChatState:
    lang: str = "gu"
    entity: dict[str, Any] | None = None  # {"kind": "project"|"promoter"|"agent", "id": ...}
    options: list[dict[str, Any]] = field(default_factory=list)  # pending disambiguation
    pending_focus: str | None = None
    turns: int = 0
    complaint: Any = None  # gujrera.complaints.flow.FilingState while a complaint is being filed
    tracking: Any = None  # gujrera.complaints.flow.TrackingState while a complaint is being tracked


@dataclass
class Reply:
    lang: str
    intent: str
    sentences: list[Sentence]
    cards: list[dict[str, Any]] = field(default_factory=list)
    options: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    is_mock: bool = False
    phrased_by: str = "template"
    understood_by: str = "rules"  # "llm" when the self-hosted model classified the question
    text_override: str | None = None

    def to_dict(self) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        index: dict[tuple[str, str], int] = {}
        out_sentences = []
        for s in self.sentences:
            refs = []
            for c in s.citations:
                key = (c["type"], str(c["id"]))
                if key not in index:
                    index[key] = len(sources) + 1
                    sources.append({"n": index[key], **c})
                if index[key] not in refs:
                    refs.append(index[key])
            out_sentences.append({"text": s.text, "refs": refs})
        text = self.text_override or " ".join(
            s["text"] + ("".join(f" [{r}]" for r in s["refs"][:3]) if s["refs"] else "") for s in out_sentences)
        return {
            "lang": self.lang, "intent": self.intent, "text": text, "sentences": out_sentences,
            "sources": sources, "cards": self.cards, "options": self.options,
            "suggestions": self.suggestions, "is_mock": self.is_mock, "phrased_by": self.phrased_by,
            "understood_by": self.understood_by,
        }


def _say(key: str, lang: str, **values: Any) -> Sentence:
    return Sentence(t(key, lang, **values), [], key)


def _from_profile(prof: Profile, lang: str, intent: str, suggestion_key: str) -> Reply:
    return Reply(lang, intent, list(prof.sentences), cards=[prof.card],
                 suggestions=SUGGESTIONS[suggestion_key][lang], is_mock=prof.is_mock)


def _options(repo: Repository, cands: list[Candidate], lang: str) -> list[dict[str, Any]]:
    out = []
    for i, c in enumerate(cands[:6], start=1):
        if c.kind == "project":
            p = repo.s.get(Project, c.id)
            label = f"{p.name} · {p.promoter.name} · {word(p.district, lang)}"
        else:
            label = f"{c.label} · {word(c.district, lang)}"
        out.append({"n": i, "kind": c.kind, "id": c.id, "label": label})
    return out


def _pick_option(message: str, options: list[dict[str, Any]], u: Understanding) -> dict[str, Any] | None:
    m = re.fullmatch(r"\s*(\d)\s*[.)]?\s*", message)
    if m:
        n = int(m.group(1))
        return next((o for o in options if o["n"] == n), None)
    if u.districts:
        hits = [o for o in options if any(word(d, "en") in o["label"] or d in o["label"] for d in u.districts)]
        if len(hits) == 1:
            return hits[0]
    lowered = message.lower()
    hits = [o for o in options if o["label"].split(" · ")[1].lower().replace(" (demo)", "") in lowered]
    return hits[0] if len(hits) == 1 else None


def respond(message: str, state: ChatState, repo: Repository, *, lang: str | None = None,
            rephrase: Callable[[Reply], Reply] | None = None) -> Reply:
    state.turns += 1
    u = understand(repo.s, message)
    is_choice = bool(state.options) and re.fullmatch(r"\s*\d\s*[.)]?\s*", message or "")
    in_form = state.complaint is not None or state.tracking is not None
    # Inside a form, Latin-script answers ("skip", "B-402", an email) keep the conversation's language.
    keep = is_choice or (u.lang == "en" and state.turns > 1 and
                         (in_form or not re.search(r"[a-z]{3,}", (message or "").lower())))
    lang = lang or (state.lang if keep else u.lang)
    state.lang = lang
    reply = _complaint_turn(message, u, state, repo, lang) or _route(message, u, state, repo, lang)
    if reply.is_mock and reply.sentences:
        reply.sentences.append(_say("demo_note", lang))
    if rephrase and reply.intent in ("project_profile", "promoter_profile", "possession"):
        reply = rephrase(reply)
    return reply


def _route(message: str, u: Understanding, state: ChatState, repo: Repository, lang: str) -> Reply:
    # 1. Answer to a "which one did you mean?" question
    if state.options:
        choice = _pick_option(message, state.options, u)
        options, focus = state.options, state.pending_focus
        state.options, state.pending_focus = [], None
        if choice:
            state.entity = {"kind": choice["kind"], "id": choice["id"]}
            return _answer_entity(state, repo, lang, focus)
        # A short reply we could not match: ask again. Anything else is a new question.
        if (len((message or "").split()) <= 3 and not u.intents
                and not (u.candidates or u.project_numbers or u.agent_numbers)):
            state.options, state.pending_focus = options, focus
            return Reply(lang, "disambiguate", [_say("disambiguate", lang)], options=options)

    # 2. Pasted ad, or an explicit "is this genuine?" with a registration number → trust check
    if u.project_numbers and ("trust" in u.intents or u.looks_like_ad):
        return _trust(message, repo, lang)
    if u.looks_like_ad and "trust" in u.intents:
        return _trust(message, repo, lang)

    # 3. Explicit registration numbers
    if u.agent_numbers and not u.project_numbers:
        prof = agent_profile(repo, u.agent_numbers[0].normalised, lang)
        if prof is None:
            return Reply(lang, "not_found", [_say("not_found", lang, q=u.agent_numbers[0].normalised)])
        state.entity = {"kind": "agent", "id": prof.entity_id}
        return Reply(lang, "agent_profile", list(prof.sentences), cards=[prof.card], is_mock=prof.is_mock)
    if u.project_numbers:
        project = repo.get_project(u.project_numbers[0].normalised)
        if project is None:
            return Reply(lang, "not_found", [_say("not_found", lang, q=u.project_numbers[0].normalised)],
                         suggestions=SUGGESTIONS["start"][lang])
        state.entity = {"kind": "project", "id": project["id"]}
        return _answer_entity(state, repo, lang, _focus(u))

    # 4. Officer analytics: standard reports, or LLM-written SQL behind the guard
    text_lc = (message or "").lower()
    if repo.p.role == "officer" and (match_report(text_lc) or (looks_like_analytics(text_lc) and not u.candidates)):
        a = analytics_answer(message, repo, lang, generate=analytics_generate)
        return Reply(lang, a.intent, a.sentences, cards=[a.card] if a.card else [], suggestions=a.suggestions)
    if repo.p.role != "officer" and match_report(text_lc) and looks_like_report_request(text_lc)             and not u.candidates:
        return Reply(lang, "officer_only", [Sentence(analytics_text("officer_only", lang), [], "an_officer_only")])

    # 5. Promoter / agent self-service (role-scoped), or a login prompt for private data
    if is_self_service(text_lc) and not (repo.p.role == "citizen" and "complaint_file" in u.intents):
        reply = _self_service(text_lc, u, repo, lang)
        if reply:
            return reply

    # 6. Questions about the law: RAG over the RERA Act, Gujarat Rules and orders
    if "legal" in u.intents and not u.candidates and not u.project_numbers and "complaint_file" not in u.intents:
        la = legal_answer(message, lang)
        return Reply(lang, la.intent, la.sentences, cards=[la.card] if la.card else [],
                     suggestions=SUGGESTIONS["start"][lang])

    # 6b. Complaint filing / tracking
    if "complaint_file" in u.intents or REF_RE.search(message or ""):
        if (repo.p.role == "citizen" and repo.p.user_id is not None and not REF_RE.search(message or "")
                and wants_tracking(message)):
            return _from_flow(my_complaints(repo, lang), lang)
        out = (start_tracking if wants_tracking(message) else start_filing)(message, state, repo, lang)
        return _from_flow(out, lang)

    # 7. Names
    cands = u.candidates
    if u.districts and len(cands) > 1:
        narrowed = [c for c in cands if c.district in u.districts]
        cands = narrowed or cands
    if "promoter" in u.intents and any(c.kind == "promoter" for c in cands):
        cands = [c for c in cands if c.kind == "promoter"]
    focus = _focus(u)
    if len(cands) == 1:
        state.entity = {"kind": cands[0].kind, "id": cands[0].id}
        if "promoter" in u.intents and cands[0].kind == "project":
            p = repo.s.get(Project, cands[0].id)
            state.entity = {"kind": "promoter", "id": p.promoter_id}
        return _answer_entity(state, repo, lang, focus)
    if len(cands) > 1:
        state.options = _options(repo, cands, lang)
        state.pending_focus = focus
        return Reply(lang, "disambiguate", [_say("disambiguate", lang)], options=state.options)

    # 8. Follow-up about the entity already in the conversation
    topical = u.intents & {"possession", "promoter", "complaints"}
    if state.entity and topical and len(u.leftover.split()) <= 2:
        if "promoter" in topical and state.entity["kind"] == "project":
            p = repo.s.get(Project, state.entity["id"])
            state.entity = {"kind": "promoter", "id": p.promoter_id}
        return _answer_entity(state, repo, lang, focus)

    # 9. Rules did not understand: let the self-hosted LLM classify it and copy out the name
    if not (u.intents & {"greeting"}) and len((message or "").strip()) >= 6:
        routed = llm_route(message, generate=router_generate)
        if routed:
            reply = _from_llm_route(routed, message, state, repo, lang)
            if reply:
                reply.understood_by = "llm"
                return reply

    # 10. Nothing matched
    if "greeting" in u.intents and not u.leftover:
        return Reply(lang, "greeting", [_say("greeting", lang)], suggestions=SUGGESTIONS["start"][lang])
    if u.leftover and not u.leftover.isdigit() and (u.names_something or u.intents - {"greeting"}):
        return _not_found(u.leftover, state, repo, lang, _focus(u))
    if u.intents - {"greeting"} or u.leftover.isdigit():
        return Reply(lang, "need_entity", [_say("need_entity", lang)], suggestions=SUGGESTIONS["start"][lang])
    return Reply(lang, "out_of_scope", [_say("out_of_scope", lang)], suggestions=SUGGESTIONS["start"][lang])


def _not_found(q: str, state: ChatState, repo: Repository, lang: str, focus: str | None) -> Reply:
    """Not found; but if a registry name is close (a typo or a voice-recognition slip), offer it."""
    close = suggest_names(repo.s, q)
    if close:
        state.options, state.pending_focus = _options(repo, close, lang), focus
        return Reply(lang, "did_you_mean", [_say("did_you_mean", lang, q=q)], options=state.options)
    return Reply(lang, "not_found", [_say("not_found", lang, q=q), _say("need_entity", lang)],
                 suggestions=SUGGESTIONS["start"][lang])


def looks_like_report_request(text_lc: str) -> bool:
    """A report-style question ("which…", "how many…", "list…"), not a buyer describing their problem."""
    return any(c in text_lc for c in ANALYTICS_CUES)


def _from_llm_route(routed: Routed, message: str, state: ChatState, repo: Repository, lang: str) -> Reply | None:
    """Turn the model's classification into a normal, record-based answer (or None to fall back)."""
    intent = routed.intent
    if intent == "legal":
        # Search with the model's English rewrite as well (helps romanised Gujarati/Hindi).
        query = routed.english or message
        la = legal_answer(message, lang, search_query=query)
        return Reply(lang, la.intent, la.sentences, cards=[la.card] if la.card else [],
                     suggestions=SUGGESTIONS["start"][lang])
    if intent == "file_complaint":
        return _from_flow(start_filing(message, state, repo, lang), lang)
    if intent == "track_complaint":
        return _from_flow(start_tracking(message, state, repo, lang), lang)
    if intent == "check_ad":
        return _trust(message, repo, lang)
    if intent in ("project", "possession", "promoter", "complaints"):
        if not routed.name:
            return Reply(lang, "need_entity", [_say("need_entity", lang)], suggestions=SUGGESTIONS["start"][lang])
        cands = find_candidates(repo.s, routed.name.lower(), threshold=90)
        if intent == "promoter" and any(c.kind == "promoter" for c in cands):
            cands = [c for c in cands if c.kind == "promoter"]
        focus = {"possession": "possession", "complaints": "complaints"}.get(intent)
        if len(cands) == 1:
            state.entity = {"kind": cands[0].kind, "id": cands[0].id}
            if intent == "promoter" and cands[0].kind == "project":
                state.entity = {"kind": "promoter", "id": repo.s.get(Project, cands[0].id).promoter_id}
            return _answer_entity(state, repo, lang, focus)
        if len(cands) > 1:
            state.options, state.pending_focus = _options(repo, cands, lang), focus
            return Reply(lang, "disambiguate", [_say("disambiguate", lang)], options=state.options)
        return _not_found(routed.name, state, repo, lang, focus)
    if intent == "other":
        return Reply(lang, "out_of_scope", [_say("out_of_scope", lang)], suggestions=SUGGESTIONS["start"][lang])
    return None


def _focus(u: Understanding) -> str | None:
    if "possession" in u.intents:
        return "possession"
    if "complaints" in u.intents and "promoter" not in u.intents:
        return "complaints"
    return None


COMPLAINT_KEYS = {"complaints", "no_complaints", "promoter_complaints", "promoter_orders", "promoter_no_orders",
                  "latest_order"}


def _self_service(text_lc: str, u: Understanding, repo: Repository, lang: str) -> Reply | None:
    role = repo.p.role
    focus = focus_of(text_lc)
    if role == "developer":
        other = [c for c in u.candidates if (c.kind == "promoter" and c.id != repo.p.promoter_id) or
                 (c.kind == "project" and repo.s.get(Project, c.id).promoter_id != repo.p.promoter_id)]
        if other:
            return Reply(lang, "access_denied", [Sentence(ss("only_own", lang), [], "ss_only_own")])
        summary = promoter_summary(repo, lang, focus=focus or None)
    elif role == "agent":
        summary = agent_summary(repo, lang)
    elif role == "officer":
        return None  # officer analytics is a separate skill
    else:
        if focus & {"dues", "notices", "qpr"} and not u.candidates:
            return Reply(lang, "login_required", [Sentence(ss("login_required", lang), [], "ss_login_required")])
        return None
    sentences = summary.sentences
    if focus and len(sentences) > 1:
        sentences = sentences[1:]  # skip the greeting for a specific question
    return Reply(lang, "self_service", sentences, cards=[summary.card], is_mock=summary.is_mock)


def _from_flow(out: FlowOut, lang: str) -> Reply:
    return Reply(lang, out.intent, out.sentences, cards=out.cards, options=out.options)


def _complaint_turn(message: str, u: Understanding, state: ChatState, repo: Repository, lang: str) -> Reply | None:
    """Keep the user inside an open filing or tracking conversation."""
    if state.complaint is not None:
        return _from_flow(continue_filing(message, state, repo, lang), lang)
    if state.tracking is not None:
        if REF_RE.search(message or "") or CODE_RE.search(message or "") or not (u.intents or u.candidates):
            return _from_flow(continue_tracking(message, state, repo, lang), lang)
        state.tracking = None  # the user moved on to another question
    return None


def _answer_entity(state: ChatState, repo: Repository, lang: str, focus: str | None) -> Reply:
    reply = _answer_entity_full(state, repo, lang, focus)
    if focus == "complaints" and reply.intent in ("project_profile", "promoter_profile"):
        kept = [s for s in reply.sentences if s.key in COMPLAINT_KEYS]
        if kept:
            reply.sentences, reply.intent = kept, "complaints"
    return reply


def _answer_entity_full(state: ChatState, repo: Repository, lang: str, focus: str | None) -> Reply:
    entity = state.entity
    if entity["kind"] == "project":
        prof = project_profile(repo, entity["id"], lang, focus="possession" if focus == "possession" else None)
        return _from_profile(prof, lang, "possession" if focus == "possession" else "project_profile", "project")
    if entity["kind"] == "promoter":
        if focus == "possession":
            projects = [p for p in repo.promoter_projects(entity["id"]) if p["status"] == "ongoing"]
            if len(projects) == 1:
                state.entity = {"kind": "project", "id": projects[0]["id"]}
                return _answer_entity(state, repo, lang, focus)
            if projects:
                cands = [Candidate("project", p["id"], p["name"], 100, p["district"]) for p in projects]
                state.options, state.pending_focus = _options(repo, cands, lang), focus
                return Reply(lang, "disambiguate", [_say("disambiguate", lang)], options=state.options)
        prof = promoter_profile(repo, entity["id"], lang)
        return _from_profile(prof, lang, "promoter_profile", "promoter")
    prof = agent_profile(repo, entity["id"], lang)
    return Reply(lang, "agent_profile", list(prof.sentences), cards=[prof.card], is_mock=prof.is_mock)


def _trust(message: str, repo: Repository, lang: str) -> Reply:
    report = check_text(message, repo)
    problems = [c for c in report.checks if c.status in ("fail", "warn")]
    sources = [c.source for c in report.checks if c.source and c.status == "pass" and c.id == "registry_lookup"]
    sentence = Sentence(t("trust_result", lang, headline=report.headline[lang].rstrip(".।")), sources, "trust_result")
    return Reply(lang, "trust_check", [sentence], cards=[{"type": "trust", **report.to_dict(),
                                                          "problems": [c.title for c in problems]}],
                 is_mock=report.is_mock)
