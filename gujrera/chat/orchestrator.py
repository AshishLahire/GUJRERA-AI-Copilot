"""Chat orchestrator: one message in, one cited answer out.

Flow: understand the message (language, intents, entities) → pick a skill
(trust check, project/promoter/agent profile, possession answer) → build the
answer from registry templates → number the citations → optionally let a
local LLM rephrase it, keeping the answer only if the citation guard passes.

Facts never come from a model. If no record supports an answer, the reply says
so ("not found") instead of guessing.
"""

from __future__ import annotations

import copy
import re
from contextvars import ContextVar
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
from gujrera.tools.interest import chat_estimate, wants_calculation
from gujrera.analytics.risk import chat_reply as risk_reply, wants_risk
from gujrera.enforcement import chat_reply as enforcement_reply, wants_enforcement
from gujrera.enforcement import citizen_reply as enforcement_citizen_reply
from gujrera.complaints.triage import chat_reply as triage_reply, wants_triage

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
ORDER_RE = re.compile(r"\b[A-Z]{2,8}-ORD-\d{4}-\d{5}\b", re.IGNORECASE)
ORDER_WORDS = ("order", "complied", "comply", "compliance", "આદેશ", "પાલન", "आदेश", "पालन")
REPORT_WORDS = ("report", "pdf", "before you buy", "before buying", "due diligence", "રિપોર્ટ", "અહેવાલ આપો",
                "ખરીદતા પહેલાં", "रिपोर्ट", "खरीदने से पहले")
router_generate = None

# English companion answers (see respond_with_english). _RECORD collects what the first pass
# decided with the LLM; _EN_PASS marks the second, English pass, which reuses that and calls no model.
_RECORD: ContextVar[dict | None] = ContextVar("gujrera_chat_record", default=None)
_EN_PASS: ContextVar[dict | None] = ContextVar("gujrera_chat_en_pass", default=None)


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


def respond_with_english(message: str, state: ChatState, repo: Repository, *, lang: str | None = None,
                         rephrase: Callable[[Reply], Reply] | None = None) -> tuple[Reply, str | None]:
    """``respond``, plus the same answer in English when the reply is in Gujarati or Hindi, so English
    readers can follow. The English text is built from the same records and templates (not machine
    translated); None when the reply is English or the turn is not safe or cheap to repeat."""
    before = copy.deepcopy(state)
    record: dict = {}
    token = _RECORD.set(record)
    try:
        reply = respond(message, state, repo, lang=lang, rephrase=rephrase)
    finally:
        _RECORD.reset(token)
    return reply, english_companion(message, before, repo, reply, record.get("routed"))


def english_companion(message: str, state_before: ChatState, repo: Repository, reply: Reply,
                      routed: Routed | None = None) -> str | None:
    if reply.lang == "en" or not reply.sentences or reply.text_override:
        return None
    # Complaint filing/tracking changes data and asks step by step; officer analytics may call the model.
    if (reply.intent.startswith("complaint_") or state_before.complaint is not None
            or state_before.tracking is not None or any(c.get("type") == "analytics" for c in reply.cards)):
        return None
    quiet = Repository(repo.s, repo.p, audit_sink=lambda _row: None)  # same reads, already audited
    token = _EN_PASS.set({"routed": routed})
    try:
        en = respond(message, copy.deepcopy(state_before), quiet, lang="en")
    except Exception:  # noqa: BLE001 - the English line is a convenience, never a failure
        return None
    finally:
        _EN_PASS.reset(token)
    if en.intent != reply.intent or not en.sentences:
        return None
    return en.to_dict()["text"]


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
    if (repo.p.role == "officer" and any(w in text_lc for w in ORDER_WORDS) and not ORDER_RE.search(message or "")
            and not REF_RE.search(message or "") and not u.candidates):  # orders to enforce (officers only)
        return _orders_to_enforce(repo, lang)
    if repo.p.role == "officer" and wants_triage(text_lc) and not u.candidates:  # complaint queue (officers only)
        district = next(iter(u.districts)) if len(u.districts) == 1 else None
        sentences, card = triage_reply(repo, lang, district=district)
        return Reply(lang, "complaint_triage", sentences, cards=[card])
    if repo.p.role == "officer" and wants_enforcement(text_lc):  # citizen ad reports (officers only)
        district = next(iter(u.districts)) if len(u.districts) == 1 else None
        sentences, card = enforcement_reply(repo, lang, district=district)
        return Reply(lang, "enforcement", sentences, cards=[card] if card else [])
    if repo.p.role != "officer" and wants_enforcement(text_lc) and not u.candidates and not u.project_numbers             and not u.looks_like_ad:
        return Reply(lang, "enforcement_info", enforcement_citizen_reply(lang), suggestions=SUGGESTIONS["start"][lang])
    if repo.p.role == "officer" and wants_risk(text_lc):  # project risk early warning (officers only)
        projects = [c for c in u.candidates if c.kind == "project"]
        district = next(iter(u.districts)) if len(u.districts) == 1 else None
        sentences, card = risk_reply(repo, lang, project_id=projects[0].id if len(projects) == 1 else None,
                                     district=district)
        return Reply(lang, "risk", sentences, cards=[card] if card else [])
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
        la = legal_answer(message, lang, use_llm=False if _EN_PASS.get() is not None else None)
        return Reply(lang, la.intent, la.sentences, cards=[la.card] if la.card else [],
                     suggestions=SUGGESTIONS["start"][lang])

    # 6a'. Orders: what an order directs and whether it was complied with (orders are public)
    order_no = ORDER_RE.search(message or "")
    if order_no or (any(w in text_lc for w in ORDER_WORDS) and (REF_RE.search(message or "") or u.candidates)
                    and "complaint_file" not in u.intents):
        if repo.p.role == "officer" and not order_no and not REF_RE.search(message or "") and not u.candidates:
            return _orders_to_enforce(repo, lang)
        else:
            from gujrera.orders import orders_for

            ref = REF_RE.search(message or "")
            projects = [c for c in u.candidates if c.kind == "project"]
            rows = (orders_for(repo, order_no=order_no.group(0), lang=lang) if order_no else
                    orders_for(repo, complaint_ref=ref.group(1), lang=lang) if ref else
                    orders_for(repo, project_id=projects[0].id, lang=lang) if len(projects) == 1 else [])
            if rows:
                sentences = [Sentence(x["text"], x["citations"], "order_line") for r in rows[:4] for x in r["sentences"]]
                return Reply(lang, "order_status", sentences, cards=[{"type": "orders", "items": rows[:6]}],
                             is_mock=any(r["is_mock"] for r in rows))
            if order_no or ref:
                return Reply(lang, "not_found", [_say("not_found", lang, q=(order_no.group(0) if order_no else ref.group(1)))])

    # 6b. Complaint filing / tracking
    if "complaint_file" in u.intents or REF_RE.search(message or ""):
        if (repo.p.role == "citizen" and repo.p.user_id is not None and not REF_RE.search(message or "")
                and wants_tracking(message)):
            return _from_flow(my_complaints(repo, lang), lang)
        out = (start_tracking if wants_tracking(message) else start_filing)(message, state, repo, lang)
        return _from_flow(out, lang)

    # 6b'. Before-you-buy report for one named project (or the project being discussed)
    if (any(w in text_lc for w in REPORT_WORDS) and "complaint_file" not in u.intents
            and not any(w in text_lc for w in ("progress report", "quarterly", "qpr", "ત્રિમાસિક", "तिमाही",
                                               "complaint", "ફરિયાદ", "शिकायत", " ad", "advert", "જાહેરાત",
                                               "विज्ञापन"))):
        projects = [c for c in u.candidates if c.kind == "project"]
        pid = projects[0].id if len(projects) == 1 else (
            state.entity["id"] if not u.candidates and state.entity and state.entity.get("kind") == "project" else None)
        if pid is not None:
            from gujrera.tools.project_report import build_report

            rep = build_report(repo, pid, lang)
            if rep:
                state.entity = {"kind": "project", "id": pid}
                sentences = [Sentence(g["text"], g["citations"], f"report_{g['key']}") for g in rep["glance"]]
                card = {"type": "report", "project_id": pid, "project": rep["project"]["name"],
                        "overall": rep["overall"], "questions": len(rep["questions"]), "is_mock": rep["is_mock"]}
                return Reply(lang, "project_report", sentences, cards=[card], is_mock=rep["is_mock"],
                             suggestions=SUGGESTIONS["start"][lang])

    # 6c. Delay interest / refund estimate for one named project (or the project being discussed)
    if wants_calculation(text_lc) and "complaint_file" not in u.intents:
        projects = [c for c in u.candidates if c.kind == "project"]
        pid = None
        if len(projects) == 1:
            pid = projects[0].id
        elif not u.candidates and state.entity and state.entity.get("kind") == "project":
            pid = state.entity["id"]
        project = repo.get_project_by_id(pid) if pid is not None else None
        if project:
            state.entity = {"kind": "project", "id": project["id"]}
            sentences, card = chat_estimate(message, project, lang)
            return Reply(lang, "interest_estimate", sentences, cards=[card], is_mock=card["is_mock"],
                         suggestions=SUGGESTIONS["start"][lang])

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
        en_pass = _EN_PASS.get()
        if en_pass is not None:
            routed = en_pass.get("routed")  # reuse the first pass's reading: no second model call
        else:
            routed = llm_route(message, generate=router_generate)
            record = _RECORD.get()
            if record is not None:
                record["routed"] = routed
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


def _orders_to_enforce(repo: Repository, lang: str) -> Reply:
    """Officers: orders not yet complied with (Section 63 penalty, Section 40 recovery)."""
    from gujrera.orders import to_enforce

    data = to_enforce(repo, lang)
    k = data["counts"]
    text = {"en": f"Orders not yet complied with: {k['overdue']} past their deadline, {k['not_complied']} recorded as not complied, "
                  f"{k['partly_complied']} partly done, {k['recovery']} in recovery (Section 40); {k['pending']} not due yet.",
            "gu": f"પાલન બાકી આદેશો: {k['overdue']} મુદત વીતી ગઈ, {k['not_complied']} પાલન ન થયાની નોંધ, {k['partly_complied']} આંશિક, "
                  f"{k['recovery']} વસૂલાતમાં (કલમ 40); {k['pending']} ની મુદત બાકી.",
            "hi": f"पालन बाकी आदेश: {k['overdue']} समय-सीमा पार, {k['not_complied']} पालन न होने की प्रविष्टि, {k['partly_complied']} आंशिक, "
                  f"{k['recovery']} वसूली में (धारा 40); {k['pending']} का समय बाकी।"}[lang]
    return Reply(lang, "orders_to_enforce", [Sentence(text, [{"type": "legal_act", "id": "RERA Act, 2016, Section 63",
                                                                "is_mock": False}], "orders_enforce")],
                 cards=[{"type": "orders", "items": data["items"][:6], "officer": True}])


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
        la = legal_answer(message, lang, search_query=query,
                          use_llm=False if _EN_PASS.get() is not None else None)
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
