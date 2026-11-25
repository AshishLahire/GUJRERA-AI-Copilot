"""Complaint triage and hearing preparation for GUJRERA officers.

The law sets the clock: the Authority shall dispose of a complaint within sixty days of receiving it,
or record its reasons (RERA Act Section 29(4)); the adjudicating officer has the same sixty days for
compensation (Section 71(2)). Triage ranks open complaints by named reasons, each with points:

  overdue        past the sixty-day period (more points the longer it is past)
  due_soon       thirty or fifteen days or fewer left
  not_scrutinised  still "filed" more than fifteen days after receipt
  group          other open complaints on the same project: they can be heard together
  risk           the project is on the risk watchlist (gujrera.analytics.risk)
  project_delay  a delay, refund or compensation complaint on a project long past its promised date

A hearing brief brings together the complaint, the project's registry facts (from the before-you-buy
report), the relevant sections, how similar complaints were decided, other open complaints on the same
project, and points to put to the promoter. Officers can move a complaint along (scrutiny, hearing date,
order reserved, disposed with an outcome); each step is a ComplaintEvent, so the buyer's own tracking
shows it. Officers only; district officers work their own district; every action is audited.

Complaint text is shown to officers, who handle complaints; complainant contact details are not part of
the complaint record here (they stay with the portal hand-off).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from gujrera.db.models import Complaint, ComplaintEvent, Project, Promoter
from gujrera.db.repository import AccessDenied, Repository
from gujrera.i18n import fmt_date

DISPOSAL_DAYS = 60  # Section 29(4); Section 71(2) for compensation
OPEN = ("filed", "under_scrutiny", "hearing_scheduled", "order_reserved")
STATUS_FLOW = {
    "filed": ("under_scrutiny", "hearing_scheduled", "withdrawn"),
    "under_scrutiny": ("hearing_scheduled", "order_reserved", "disposed", "withdrawn"),
    "hearing_scheduled": ("hearing_scheduled", "order_reserved", "disposed", "withdrawn"),
    "order_reserved": ("disposed",),
}
OUTCOMES = ("allowed", "partly_allowed", "dismissed", "settled")
URGENT_AT, HIGH_AT = 70, 55  # urgent: overdue and another reason (group, risk, long delay)

# Category -> (sections of the RERA Act 2016 that decide it, forum). Section titles from the Act.
SECTIONS: dict[str, tuple[list[tuple[str, str]], str]] = {
    "possession_delay": ([("18", "Return of amount and compensation"), ("19", "Rights and duties of allottees")], "authority"),
    "refund": ([("18", "Return of amount and compensation"), ("19", "Rights and duties of allottees")], "authority"),
    "compensation": ([("71", "Power to adjudicate"), ("72", "Factors for adjudging compensation"),
                      ("18", "Return of amount and compensation")], "adjudicating_officer"),
    "structural_defect": ([("14", "Adherence to sanctioned plans and project specifications (14(3): defects within 5 years)")], "authority"),
    "amenities_not_provided": ([("14", "Adherence to sanctioned plans and project specifications"),
                                ("11", "Functions and duties of promoter")], "authority"),
    "plan_deviation": ([("14", "Adherence to sanctioned plans and project specifications (14(2): changes need consent)")], "authority"),
    "agreement_violation": ([("13", "No deposit or advance without first entering into agreement for sale"),
                             ("11", "Functions and duties of promoter")], "authority"),
    "false_advertisement": ([("12", "Obligations of promoter regarding veracity of the advertisement or prospectus")], "authority"),
    "agent_misconduct": ([("10", "Functions of real estate agents")], "authority"),
}
FORUM_LAW = {"authority": "Section 31 (complaint to the Authority); disposal within 60 days, Section 29(4)",
             "adjudicating_officer": "Section 71 (adjudicating officer); disposal within 60 days, Section 71(2)"}

T: dict[str, dict[str, str]] = {
    "overdue": {"en": "Past the 60-day disposal period by {days} days (Section {sec}).",
                "gu": "60 દિવસની નિકાલ મુદત {days} દિવસથી વીતી ગઈ (કલમ {sec}).",
                "hi": "60 दिन की निपटान अवधि {days} दिन से बीत चुकी (धारा {sec})।"},
    "due_soon": {"en": "{days} days left of the 60-day disposal period (Section {sec}).",
                 "gu": "60 દિવસની નિકાલ મુદતમાં {days} દિવસ બાકી (કલમ {sec}).",
                 "hi": "60 दिन की निपटान अवधि में {days} दिन बाकी (धारा {sec})।"},
    "not_scrutinised": {"en": "Not yet taken up for scrutiny, {days} days after receipt.",
                        "gu": "મળ્યાના {days} દિવસ પછી પણ ચકાસણી શરૂ થઈ નથી.",
                        "hi": "प्राप्ति के {days} दिन बाद भी जाँच शुरू नहीं हुई।"},
    "group": {"en": "{n} other open complaints on the same project: they can be heard together.",
              "gu": "એ જ પ્રોજેક્ટ પર બીજી {n} ખુલ્લી ફરિયાદો: સાથે સુનાવણી થઈ શકે.",
              "hi": "उसी प्रोजेक्ट पर {n} अन्य खुली शिकायतें: साथ सुनवाई हो सकती है।"},
    "risk": {"en": "The project is on the risk watchlist ({band}, score {score}).",
             "gu": "પ્રોજેક્ટ જોખમ યાદીમાં છે ({band}, સ્કોર {score}).",
             "hi": "प्रोजेक्ट जोखिम सूची में है ({band}, स्कोर {score})।"},
    "project_delay": {"en": "The project is {days} days past its promised completion date.",
                      "gu": "પ્રોજેક્ટ વચન આપેલી પૂર્ણતા તારીખથી {days} દિવસ પાછળ છે.",
                      "hi": "प्रोजेक्ट वादा की गई पूर्णता तारीख से {days} दिन पीछे है।"},
}
POINTS_TO_PUT = {
    "possession_delay": ["The revised possession date, its reason, and any extension order (Section 6).",
                         "Interest for every month of delay from the date in the agreement (Section 18; rate under Rule 16).",
                         "Construction progress in the last quarterly report and any reports not filed (Section 11)."],
    "refund": ["Payments received from the buyer and their dates (interest runs from each, Rule 16(3)).",
               "The date the buyer withdrew and why the refund was not made within 45 days (Rule 17)."],
    "compensation": ["The loss claimed and how it is quantified (Section 72 factors).",
                     "Whether the matter belongs before the adjudicating officer (Section 71)."],
    "structural_defect": ["Date of possession: defects within 5 years must be fixed free within 30 days (Section 14(3)).",
                          "Inspection report and the promoter's repair plan with dates."],
    "amenities_not_provided": ["The amenities in the sanctioned plan and the agreement, and their status (Section 14).",
                               "A completion date for each promised amenity."],
    "plan_deviation": ["The sanctioned plan and the change made; written consent of the buyer, and of two-thirds of buyers for common areas (Section 14(2))."],
    "agreement_violation": ["The registered agreement for sale and the amounts taken before it (no more than 10% before registration, Section 13).",
                            "Demands not linked to the construction stage in the agreement."],
    "false_advertisement": ["The advertisement and how it differs from the registration (Section 12).",
                            "Whether the buyer relied on it and the loss caused."],
    "agent_misconduct": ["The agent's registration and the transaction handled (Section 10)."],
}


def _t(key: str, lang: str, **v: Any) -> str:
    return T[key].get(lang, T[key]["en"]).format(**v)


def _officer(repo: Repository) -> None:
    if repo.p.role != "officer":
        raise AccessDenied("Complaint triage is for GUJRERA officers.")


def _scope(repo: Repository, stmt):
    return stmt.where(Complaint.district == repo.p.district_scope) if repo.p.district_scope else stmt


def _sec(category: str) -> str:
    return "71(2)" if SECTIONS.get(category, ([], "authority"))[1] == "adjudicating_officer" else "29(4)"


def _risks(repo: Repository, lang: str, today: date) -> dict[int, Any]:
    from gujrera.analytics.risk import score_projects

    return {r.project_id: r for r in score_projects(repo, lang, as_of=today)}


def triage(repo: Repository, lang: str = "en", *, as_of: date | None = None, district: str | None = None,
           category: str | None = None) -> dict[str, Any]:
    _officer(repo)
    today = as_of or date.today()
    stmt = _scope(repo, select(Complaint).where(Complaint.status.in_(OPEN)))
    if district and not repo.p.district_scope:
        stmt = stmt.where(Complaint.district == district)
    rows = repo.s.scalars(stmt).all()
    projects = {p.id: p for p in repo.s.scalars(select(Project).where(Project.id.in_({c.project_id for c in rows if c.project_id})))}
    promoters = {p.id: p.name for p in repo.s.scalars(select(Promoter).where(Promoter.id.in_({c.promoter_id for c in rows if c.promoter_id})))}
    per_project: dict[int, list[Complaint]] = defaultdict(list)
    for c in rows:
        if c.project_id:
            per_project[c.project_id].append(c)
    risks = _risks(repo, lang, today) if rows else {}  # nothing to rank: skip scoring every project

    items = []
    for c in rows:
        age = (today - c.filed_on).days
        left = DISPOSAL_DAYS - age
        reasons: list[dict[str, Any]] = []

        def add(code: str, pts: int, text: str) -> None:
            reasons.append({"code": code, "points": pts, "text": text})

        if left < 0:
            add("overdue", 50 if -left >= 120 else 40, _t("overdue", lang, days=-left, sec=_sec(c.category)))
        elif left <= 15:
            add("due_soon", 25, _t("due_soon", lang, days=left, sec=_sec(c.category)))
        elif left <= 30:
            add("due_soon", 10, _t("due_soon", lang, days=left, sec=_sec(c.category)))
        if c.status == "filed" and age > 15:
            add("not_scrutinised", 10, _t("not_scrutinised", lang, days=age))
        others = len(per_project.get(c.project_id, [])) - 1 if c.project_id else 0
        if others >= 1:
            add("group", 15 if others >= 2 else 8, _t("group", lang, n=others))
        risk = risks.get(c.project_id)
        if risk and risk.band in ("high", "medium"):
            add("risk", 15 if risk.band == "high" else 5, _t("risk", lang, band=risk.band, score=risk.score))
        proj = projects.get(c.project_id)
        if proj and c.category in ("possession_delay", "refund", "compensation") and proj.status == "ongoing":
            late = (today - proj.proposed_completion).days
            if late > 365:
                add("project_delay", 10, _t("project_delay", lang, days=late))
        score = min(100, sum(r["points"] for r in reasons))
        sections, forum = SECTIONS.get(c.category, ([], "authority"))
        items.append({
            "id": c.id, "ref_no": c.ref_no, "filed_on": c.filed_on.isoformat(), "age_days": age, "days_left": left,
            "due_by": (c.filed_on + timedelta(days=DISPOSAL_DAYS)).isoformat(), "status": c.status, "form": c.form,
            "category": c.category, "relief": c.relief, "summary": c.summary, "district": c.district,
            "channel": c.channel, "project_id": c.project_id, "project": proj.name if proj else None,
            "rera_no": proj.rera_no if proj else None, "promoter": promoters.get(c.promoter_id),
            "forum": forum, "sections": [f"Section {n}" for n, _ in sections],
            "score": score, "band": "urgent" if score >= URGENT_AT else "high" if score >= HIGH_AT else "normal",
            "reasons": sorted(reasons, key=lambda r: -r["points"]), "group_size": others + 1 if c.project_id else 1,
            "is_mock": bool(c.is_mock),
        })
    if category:
        items = [i for i in items if i["category"] == category]
    items.sort(key=lambda i: (-i["score"], i["days_left"]))

    groups = []
    for pid, cs in per_project.items():
        if len(cs) >= 2 and pid in projects:
            groups.append({"project_id": pid, "project": projects[pid].name, "district": projects[pid].district,
                           "complaints": sorted(c.ref_no for c in cs), "categories": dict(Counter(c.category for c in cs)),
                           "oldest_days": max((today - c.filed_on).days for c in cs)})
    groups.sort(key=lambda g: (-len(g["complaints"]), -g["oldest_days"]))
    summary = {
        "open": len(rows), "overdue": sum(1 for c in rows if (today - c.filed_on).days > DISPOSAL_DAYS),
        "due_15": sum(1 for c in rows if 0 <= DISPOSAL_DAYS - (today - c.filed_on).days <= 15),
        "by_status": dict(Counter(c.status for c in rows)), "by_category": dict(Counter(c.category for c in rows).most_common()),
        "groups": len(groups), "urgent": sum(i["band"] == "urgent" for i in items),
    }
    repo._audit("complaint_triage", {"open": len(rows), "district": repo.p.district_scope or district})
    return {"summary": summary, "items": items, "groups": groups, "district_scope": repo.p.district_scope,
            "as_of": today.isoformat()}


def _get(repo: Repository, complaint_id: int) -> Complaint | None:
    return repo.s.scalar(_scope(repo, select(Complaint).where(Complaint.id == complaint_id)))


def brief(repo: Repository, complaint_id: int, lang: str = "en", *, as_of: date | None = None) -> dict[str, Any] | None:
    """Everything an officer needs before the hearing, on one page."""
    from gujrera.tools.project_report import build_report

    _officer(repo)
    today = as_of or date.today()
    c = _get(repo, complaint_id)
    if c is None:
        return None
    sections, forum = SECTIONS.get(c.category, ([], "authority"))
    events = [{"at": e.at.isoformat(), "status": e.status, "note": e.note}
              for e in sorted(c.events, key=lambda e: (e.at, e.id))]
    project = build_report(repo, c.project_id, lang, as_of=today) if c.project_id else None
    risk = _risks(repo, lang, today).get(c.project_id) if c.project_id else None

    # precedents: how the Authority decided this kind of complaint, and on this project / promoter
    decided = repo.s.scalars(select(Complaint).where(Complaint.category == c.category, Complaint.status == "disposed",
                                                     Complaint.outcome.is_not(None))).all()
    outcome_counts = dict(Counter(d.outcome for d in decided))
    related = repo.s.scalars(select(Complaint).where(Complaint.status == "disposed", Complaint.id != c.id,
                                                     (Complaint.project_id == c.project_id) | (Complaint.promoter_id == c.promoter_id))
                             .order_by(Complaint.closed_on.desc()).limit(6)).all()
    precedents = [{"ref_no": d.ref_no, "category": d.category, "outcome": d.outcome, "closed_on": d.closed_on.isoformat() if d.closed_on else None,
                   "same_project": d.project_id == c.project_id,
                   "order_no": next((o.order_no for o in d.orders), None) if hasattr(d, "orders") else None,
                   "summary": d.summary} for d in related]
    others = repo.s.scalars(_scope(repo, select(Complaint).where(Complaint.project_id == c.project_id, Complaint.id != c.id,
                                                                  Complaint.status.in_(OPEN)))).all() if c.project_id else []
    repo._audit("complaint_brief", {"ref_no": c.ref_no})
    age = (today - c.filed_on).days
    return {
        "complaint": {"id": c.id, "ref_no": c.ref_no, "form": c.form, "category": c.category, "relief": c.relief,
                      "summary": c.summary, "status": c.status, "filed_on": c.filed_on.isoformat(), "district": c.district,
                      "channel": c.channel, "age_days": age, "days_left": DISPOSAL_DAYS - age,
                      "due_by": (c.filed_on + timedelta(days=DISPOSAL_DAYS)).isoformat(),
                      "due_by_text": fmt_date(c.filed_on + timedelta(days=DISPOSAL_DAYS), lang)},
        "forum": forum, "forum_law": FORUM_LAW[forum],
        "sections": [{"section": n, "title": t, "citation": {"type": "legal_act", "id": f"RERA Act, 2016, Section {n}"}}
                     for n, t in sections],
        "timeline": events,
        "project": None if project is None else {"glance": project["glance"], "project": project["project"],
                                                 "progress_last": next((q for q in reversed(project["progress"]) if q["filed_on"]), None),
                                                 "orders": project["orders"]},
        "risk": None if risk is None else {"score": risk.score, "band": risk.band,
                                           "signals": [s.text for s in sorted(risk.signals, key=lambda s: -s.points)[:4]]},
        "precedents": {"category_outcomes": outcome_counts, "category_decided": len(decided), "related": precedents},
        "other_open": [{"id": o.id, "ref_no": o.ref_no, "category": o.category, "filed_on": o.filed_on.isoformat()} for o in others],
        "points_to_put": POINTS_TO_PUT.get(c.category, []),
        "is_mock": bool(c.is_mock),
    }


def update_status(repo: Repository, complaint_id: int, status: str, *, note: str | None = None,
                  hearing_on: date | None = None, outcome: str | None = None, today: date | None = None) -> dict[str, Any] | None:
    """Move a complaint along. Each step is a ComplaintEvent, which the buyer's tracking shows."""
    _officer(repo)
    today = today or date.today()
    c = _get(repo, complaint_id)
    if c is None:
        return None
    allowed = STATUS_FLOW.get(c.status, ())
    if status not in allowed:
        raise ValueError(f"A complaint that is '{c.status}' can move to: {', '.join(allowed) or 'nothing (closed)'}.")
    if status == "hearing_scheduled" and (hearing_on is None or hearing_on < today):
        raise ValueError("Give a hearing date today or later.")
    if status == "disposed" and outcome not in OUTCOMES:
        raise ValueError(f"Choose an outcome: {', '.join(OUTCOMES)}.")
    parts = []
    if hearing_on:
        parts.append(f"Hearing on {hearing_on.isoformat()}")
    if outcome:
        parts.append(f"Outcome: {outcome.replace('_', ' ')}")
    if note and note.strip():
        parts.append(note.strip()[:200])
    c.status = status
    if status in ("disposed", "withdrawn"):
        c.closed_on = today
        c.outcome = outcome if status == "disposed" else None
    c.events.append(ComplaintEvent(at=today, status=status, note="; ".join(parts)[:300] or None))
    repo.s.flush()
    repo._audit("complaint_status_changed", {"ref_no": c.ref_no, "status": status, "outcome": outcome})
    return {"id": c.id, "ref_no": c.ref_no, "status": c.status, "outcome": c.outcome,
            "timeline": [{"at": e.at.isoformat(), "status": e.status, "note": e.note}
                         for e in sorted(c.events, key=lambda e: (e.at, e.id))]}


# ------------------------------------------------------------------------ chat
TRIAGE_WORDS = ("triage", "complaint queue", "pending complaints", "overdue complaints", "complaints overdue",
                "complaints to hear", "hearing", "60 days", "બાકી ફરિયાદ", "સુનાવણી", "लंबित शिकायत", "सुनवाई")
_CHAT = {
    "overview": {
        "en": "{open} open complaints{where}: {overdue} past the 60-day disposal period (Section 29(4)), {due} due within 15 days, {groups} projects with several complaints that can be heard together.",
        "gu": "{where}{open} ખુલ્લી ફરિયાદો: {overdue} 60 દિવસની નિકાલ મુદત વીતી ગઈ (કલમ 29(4)), {due} 15 દિવસમાં બાકી, {groups} પ્રોજેક્ટ પર ઘણી ફરિયાદો જેની સાથે સુનાવણી થઈ શકે.",
        "hi": "{where}{open} खुली शिकायतें: {overdue} 60 दिन की निपटान अवधि पार (धारा 29(4)), {due} 15 दिनों में देय, {groups} प्रोजेक्ट पर कई शिकायतें जिनकी साथ सुनवाई हो सकती है।",
    },
    "top": {"en": "Take up first: {items}.", "gu": "પહેલા લો: {items}.", "hi": "पहले लें: {items}।"},
}


_COMPLAINT = ("complaint", "ફરિયાદ", "शिकायत")
_QUEUE = ("overdue", "pending", "queue", "to hear", "hear first", "take up", "backlog", "prioriti",
          "બાકી", "મુદત", "પહેલા લ", "લંબિત", "लंबित", "बकाया", "प्राथमिक", "बैकलॉग", "पहले ल")


def wants_triage(text_lc: str) -> bool:
    return any(w in text_lc for w in TRIAGE_WORDS) or (
        any(w in text_lc for w in _COMPLAINT) and any(w in text_lc for w in _QUEUE))


def chat_reply(repo: Repository, lang: str, *, district: str | None = None):
    from gujrera.profile.summarise import Sentence

    data = triage(repo, lang, district=district)
    s_ = data["summary"]
    shown = repo.p.district_scope or district
    where = {"en": f" in {shown}" if shown else "", "gu": f"{shown} માં " if shown else "", "hi": f"{shown} में " if shown else ""}[lang]
    out = [Sentence(_CHAT["overview"].get(lang, _CHAT["overview"]["en"]).format(
        open=s_["open"], where=where, overdue=s_["overdue"], due=s_["due_15"], groups=s_["groups"]),
        [{"type": "legal_act", "id": "RERA Act, 2016, Section 29", "is_mock": False}], "triage_overview")]
    top = data["items"][:3]
    if top:
        items = "; ".join(f"{i['ref_no']} ({i['category'].replace('_', ' ')}, {i['age_days']} days)" for i in top)
        out.append(Sentence(_CHAT["top"].get(lang, _CHAT["top"]["en"]).format(items=items),
                            [{"type": "complaint", "id": i["ref_no"], "is_mock": i["is_mock"]} for i in top], "triage_top"))
    return out, {"type": "triage", "summary": s_, "items": [{k: i[k] for k in ("id", "ref_no", "category", "age_days", "band", "project")}
                                                            for i in data["items"][:5]]}
