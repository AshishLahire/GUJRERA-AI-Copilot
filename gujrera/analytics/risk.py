"""Project risk early warning for GUJRERA officers.

Every ongoing project gets a 0-100 score made of named signals, each with points, a one-line reason in
the officer's language and the registry records it comes from. No black box: an officer can see exactly
why a project is on the list, and the weights below are the whole model. They are a starting point to
calibrate with GUJRERA's history in the PoC (which past projects stalled or drew many complaints).

Signals (ongoing projects only):
  pace          progress is behind the share of time used up to the completion target
  projection    at the pace of the last four quarterly reports, finishes after the target (or has stalled)
  past_due      the originally promised completion date has passed
  extended      the completion date was extended
  qpr           quarterly progress reports overdue (Section 11) or filed late
  registration  registration expired or ending soon with the project far from done (Section 6)
  approvals     approvals still pending or rejected
  complaints    open complaints on the project, or a recent rise in complaints
  promoter_*    the promoter's other projects delayed, adverse orders, unpaid penalties

Officers only; district officers see their own district (same rule as officer analytics). Each listing
is written to the audit log. Money signals (withdrawals from the project account vs. progress) need the
escrow data GUJRERA holds and are a PoC addition.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select

from gujrera.db.models import Approval, Complaint, DueNotice, Order, Project, ProjectProgress, Promoter
from gujrera.db.repository import AccessDenied, Repository
from gujrera.i18n import fmt_date

HIGH, MEDIUM, LOW = "high", "medium", "low"
HIGH_AT, MEDIUM_AT = 60, 30  # about one ongoing project in ten is 'high': a list officers can act on
CLOSED = ("disposed", "withdrawn")
ADVERSE_ORDERS = ("penalty_order", "revocation_order", "show_cause")

T: dict[str, dict[str, str]] = {
    "pace": {
        "en": "Behind schedule: {done}% built at the last report ({quarter}), but {expected}% of the time to the target date has passed.",
        "gu": "સમયપત્રકથી પાછળ: છેલ્લા અહેવાલ ({quarter}) મુજબ {done}% બાંધકામ, પણ લક્ષ્ય તારીખ સુધીનો {expected}% સમય વીતી ગયો છે.",
        "hi": "समय से पीछे: पिछली रिपोर्ट ({quarter}) के अनुसार {done}% निर्माण, पर लक्ष्य तारीख तक का {expected}% समय बीत चुका है।",
    },
    "stalled": {
        "en": "Progress has stalled: only {gain} percentage points in the last {quarters} quarterly reports.",
        "gu": "પ્રગતિ અટકી છે: છેલ્લા {quarters} ત્રિમાસિક અહેવાલમાં ફક્ત {gain} ટકા પોઇન્ટ.",
        "hi": "प्रगति रुकी है: पिछली {quarters} तिमाही रिपोर्टों में केवल {gain} प्रतिशत अंक।",
    },
    "projection": {
        "en": "At the recent pace ({pace} points a quarter) it would finish around {finish}, {months} months after the target date.",
        "gu": "હાલની ગતિએ (ત્રિમાસિક {pace} પોઇન્ટ) તે આશરે {finish} સુધીમાં પૂરું થાય, લક્ષ્ય તારીખથી {months} મહિના પછી.",
        "hi": "हाल की गति से (प्रति तिमाही {pace} अंक) यह लगभग {finish} तक पूरा होगा, लक्ष्य तारीख से {months} महीने बाद।",
    },
    "past_due": {
        "en": "The promised completion date ({date}) passed {days} days ago.",
        "gu": "વચન આપેલી પૂર્ણતા તારીખ ({date}) {days} દિવસ પહેલાં વીતી ગઈ.",
        "hi": "वादा की गई पूर्णता तारीख ({date}) {days} दिन पहले निकल चुकी है।",
    },
    "extended": {
        "en": "Completion was extended from {old} to {new}{orders}.",
        "gu": "પૂર્ણતા તારીખ {old} થી {new} સુધી લંબાવાઈ{orders}.",
        "hi": "पूर्णता तारीख {old} से {new} तक बढ़ाई गई{orders}।",
    },
    "qpr_missing": {
        "en": "{n} quarterly progress report(s) overdue, the oldest due {date} (Section 11).",
        "gu": "{n} ત્રિમાસિક પ્રગતિ અહેવાલ બાકી, સૌથી જૂનો {date} એ આપવાનો હતો (કલમ 11).",
        "hi": "{n} तिमाही प्रगति रिपोर्ट बाकी, सबसे पुरानी {date} को देय थी (धारा 11)।",
    },
    "qpr_late": {
        "en": "{n} of the last 4 quarterly reports were filed late.",
        "gu": "છેલ્લા 4 માંથી {n} ત્રિમાસિક અહેવાલ મોડા ફાઈલ થયા.",
        "hi": "पिछली 4 में से {n} तिमाही रिपोर्ट देर से दाखिल हुईं।",
    },
    "reg_expired": {
        "en": "Registration expired on {date} while the project is still under construction (Section 6).",
        "gu": "પ્રોજેક્ટ હજી બાંધકામ હેઠળ છે ત્યારે નોંધણી {date} એ પૂરી થઈ ગઈ (કલમ 6).",
        "hi": "प्रोजेक्ट अभी निर्माणाधीन है और पंजीकरण {date} को समाप्त हो गया (धारा 6)।",
    },
    "reg_ending": {
        "en": "Registration ends on {date} ({days} days) with the project {done}% built (Section 6).",
        "gu": "નોંધણી {date} એ પૂરી થાય છે ({days} દિવસ) અને પ્રોજેક્ટ {done}% જ બન્યો છે (કલમ 6).",
        "hi": "पंजीकरण {date} को समाप्त होता है ({days} दिन) और प्रोजेक्ट {done}% ही बना है (धारा 6)।",
    },
    "approvals": {
        "en": "Approvals not in place: {items}.",
        "gu": "મંજૂરીઓ બાકી: {items}.",
        "hi": "अनुमोदन लंबित: {items}।",
    },
    "complaints_open": {
        "en": "{n} open complaints on this project.",
        "gu": "આ પ્રોજેક્ટ સામે {n} ખુલ્લી ફરિયાદો.",
        "hi": "इस प्रोजेक्ट पर {n} खुली शिकायतें।",
    },
    "complaints_spike": {
        "en": "Complaints are rising: {recent} in the last 6 months against {before} in the 6 months before.",
        "gu": "ફરિયાદો વધી રહી છે: છેલ્લા 6 મહિનામાં {recent}, તેના પહેલાંના 6 મહિનામાં {before}.",
        "hi": "शिकायतें बढ़ रही हैं: पिछले 6 महीनों में {recent}, उससे पहले के 6 महीनों में {before}।",
    },
    "promoter_delays": {
        "en": "The promoter's other projects: {delayed} of {total} are behind their original date.",
        "gu": "પ્રમોટરના અન્ય પ્રોજેક્ટ: {total} માંથી {delayed} મૂળ તારીખથી પાછળ છે.",
        "hi": "प्रमोटर के अन्य प्रोजेक्ट: {total} में से {delayed} मूल तारीख से पीछे हैं।",
    },
    "promoter_orders": {
        "en": "Adverse orders against the promoter: {items}.",
        "gu": "પ્રમોટર સામે પ્રતિકૂળ આદેશો: {items}.",
        "hi": "प्रमोटर के विरुद्ध प्रतिकूल आदेश: {items}।",
    },
    "promoter_dues": {
        "en": "The promoter has {n} unpaid penalty or fee notice(s), ₹{amount} in all.",
        "gu": "પ્રમોટરની {n} દંડ કે ફી નોટિસ બાકી છે, કુલ ₹{amount}.",
        "hi": "प्रमोटर के {n} जुर्माना या शुल्क नोटिस बकाया हैं, कुल ₹{amount}।",
    },
}


def _t(key: str, lang: str, **v: Any) -> str:
    return T[key].get(lang, T[key]["en"]).format(**v)


def _inr(n: float) -> str:
    s = str(int(round(n)))
    if len(s) <= 3:
        return s
    head, tail, groups = s[:-3], s[-3:], []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return ",".join([head, *groups, tail] if head else [*groups, tail])


@dataclass
class Signal:
    code: str
    points: int
    text: str
    citations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProjectRisk:
    project_id: int
    name: str
    name_gu: str | None
    rera_no: str
    district: str
    promoter: str
    promoter_id: int
    target: date
    percent_complete: float | None
    expected_percent: float | None
    projected_finish: date | None
    is_mock: bool = False
    signals: list[Signal] = field(default_factory=list)

    @property
    def score(self) -> int:
        return min(100, sum(s.points for s in self.signals))

    @property
    def band(self) -> str:
        return HIGH if self.score >= HIGH_AT else MEDIUM if self.score >= MEDIUM_AT else LOW

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "name": self.name, "name_gu": self.name_gu, "rera_no": self.rera_no,
            "district": self.district, "promoter": self.promoter, "promoter_id": self.promoter_id,
            "target": self.target.isoformat(), "percent_complete": self.percent_complete,
            "expected_percent": self.expected_percent,
            "projected_finish": self.projected_finish.isoformat() if self.projected_finish else None,
            "score": self.score, "band": self.band, "is_mock": self.is_mock,
            "signals": [{"code": s.code, "points": s.points, "text": s.text, "citations": s.citations}
                        for s in sorted(self.signals, key=lambda s: -s.points)],
        }


def _months(a: date, b: date) -> int:
    return round((b - a).days / 30.44)


def _quarter_end(q: str) -> date:
    year, n = int(q[:4]), int(q[-1])
    return date(year, 3 * n, 30 if n in (2, 3) else 31)


def score_projects(repo: Repository, lang: str = "en", *, district: str | None = None,
                   as_of: date | None = None) -> list[ProjectRisk]:
    """Risk for every ongoing project the officer may see, highest first."""
    p = repo.p
    if p.role != "officer":
        raise AccessDenied("The risk watchlist is for GUJRERA officers.")
    if p.district_scope:  # district officers: their district only, whatever they ask for
        district = p.district_scope
    today = as_of or date.today()
    s = repo.s

    stmt = select(Project).where(Project.status == "ongoing")
    if district:
        stmt = stmt.where(Project.district == district)
    projects = s.scalars(stmt).all()
    ids = [x.id for x in projects]
    promoter_ids = {x.promoter_id for x in projects}

    progress: dict[int, list[ProjectProgress]] = defaultdict(list)
    for r in s.scalars(select(ProjectProgress).where(ProjectProgress.project_id.in_(ids))
                       .order_by(ProjectProgress.quarter)):
        progress[r.project_id].append(r)
    approvals: dict[int, list[Approval]] = defaultdict(list)
    for a in s.scalars(select(Approval).where(Approval.project_id.in_(ids), Approval.status != "granted")):
        approvals[a.project_id].append(a)
    complaints: dict[int, list[Complaint]] = defaultdict(list)
    for c in s.scalars(select(Complaint).where(Complaint.project_id.in_(ids))):
        complaints[c.project_id].append(c)
    ext_orders: dict[int, int] = defaultdict(int)
    adverse: dict[int, list[Order]] = defaultdict(list)
    for o in s.scalars(select(Order).where((Order.project_id.in_(ids)) | (Order.promoter_id.in_(promoter_ids)))):
        if o.order_type == "extension_order" and o.project_id:
            ext_orders[o.project_id] += 1
        if o.order_type in ADVERSE_ORDERS and o.promoter_id:
            adverse[o.promoter_id].append(o)
    dues: dict[int, list[DueNotice]] = defaultdict(list)
    for d in s.scalars(select(DueNotice).where(DueNotice.promoter_id.in_(promoter_ids), DueNotice.status == "pending",
                                               DueNotice.amount.is_not(None))):
        if d.due_date is None or d.due_date < today:
            dues[d.promoter_id].append(d)
    siblings: dict[int, list[Project]] = defaultdict(list)
    for x in s.scalars(select(Project).where(Project.promoter_id.in_(promoter_ids))):
        siblings[x.promoter_id].append(x)
    promoters = {x.id: x for x in s.scalars(select(Promoter).where(Promoter.id.in_(promoter_ids)))}

    out: list[ProjectRisk] = []
    for pr in projects:
        rec = {"type": "project", "id": pr.rera_no, "is_mock": pr.is_mock}
        target = pr.revised_completion or pr.proposed_completion
        reports = progress.get(pr.id, [])
        filed = [r for r in reports if r.filed_on is not None]
        latest = filed[-1] if filed else None
        done = round(latest.percent_complete, 1) if latest else None
        risk = ProjectRisk(pr.id, pr.name, pr.name_gu, pr.rera_no, pr.district, promoters[pr.promoter_id].name,
                           pr.promoter_id, target, done, None, None, bool(pr.is_mock))
        sig = risk.signals.append

        # pace: progress vs share of time used
        span = (target - pr.reg_date).days
        if latest and span > 0:
            used = min(1.0, max(0.0, (min(today, target) - pr.reg_date).days / span))
            expected = round(100 * used, 1)
            risk.expected_percent = expected
            gap = expected - latest.percent_complete
            pts = 25 if gap >= 30 else 15 if gap >= 15 else 5 if gap >= 5 else 0
            if pts:
                sig(Signal("pace", pts, _t("pace", lang, done=done, expected=round(expected), quarter=latest.quarter),
                           [{"type": "progress_report", "id": f"{pr.id}:{latest.quarter}", "is_mock": pr.is_mock}, rec]))

        # projection from the last four filed reports
        window = filed[-5:]
        if len(window) >= 3 and latest and latest.percent_complete < 99:
            quarters = len(window) - 1
            gain = latest.percent_complete - window[0].percent_complete
            velocity = gain / quarters
            cite = [{"type": "progress_report", "id": f"{pr.id}:{r.quarter}", "is_mock": pr.is_mock} for r in window]
            if velocity < 1.0:
                sig(Signal("projection", 20, _t("stalled", lang, gain=round(gain, 1), quarters=quarters), cite))
            else:
                finish = _quarter_end(latest.quarter) + timedelta(days=round((100 - latest.percent_complete) / velocity * 91.3))
                risk.projected_finish = finish
                over = _months(target, finish)
                pts = 20 if over >= 12 else 12 if over >= 6 else 5 if over >= 2 else 0
                if pts:
                    sig(Signal("projection", pts, _t("projection", lang, pace=round(velocity, 1),
                                                     finish=fmt_date(finish, lang), months=over), cite))

        # dates
        late = (today - pr.proposed_completion).days
        if late > 0:
            pts = 15 if late > 365 else 10 if late > 180 else 5
            sig(Signal("past_due", pts, _t("past_due", lang, date=fmt_date(pr.proposed_completion, lang), days=late), [rec]))
        if pr.revised_completion and pr.revised_completion > pr.proposed_completion:
            n = ext_orders.get(pr.id, 0)
            orders = {"en": f", with {n} extension orders", "gu": f", {n} મુદત વધારાના આદેશ સાથે",
                      "hi": f", {n} विस्तार आदेशों के साथ"}.get(lang, "") if n >= 2 else ""
            sig(Signal("extended", 10 if n >= 2 else 5,
                       _t("extended", lang, old=fmt_date(pr.proposed_completion, lang),
                          new=fmt_date(pr.revised_completion, lang), orders=orders), [rec]))

        # quarterly reports (Section 11)
        missing = [r for r in reports if r.filed_on is None and r.due_on < today]
        if missing:
            sig(Signal("qpr", 20 if len(missing) >= 2 else 10,
                       _t("qpr_missing", lang, n=len(missing), date=fmt_date(missing[0].due_on, lang)),
                       [{"type": "progress_report", "id": f"{pr.id}:{r.quarter}", "is_mock": pr.is_mock} for r in missing]))
        else:
            late_filed = [r for r in filed[-4:] if r.filed_on > r.due_on]
            if len(late_filed) >= 2:
                sig(Signal("qpr", 5, _t("qpr_late", lang, n=len(late_filed)),
                           [{"type": "progress_report", "id": f"{pr.id}:{r.quarter}", "is_mock": pr.is_mock}
                            for r in late_filed]))

        # registration (Section 6)
        left = (pr.reg_valid_until - today).days
        if left < 0:
            sig(Signal("registration", 20, _t("reg_expired", lang, date=fmt_date(pr.reg_valid_until, lang)), [rec]))
        elif left <= 180 and (done is None or done < 90):
            sig(Signal("registration", 10, _t("reg_ending", lang, date=fmt_date(pr.reg_valid_until, lang), days=left,
                                              done=done if done is not None else 0), [rec]))

        # approvals
        pend = approvals.get(pr.id, [])
        if pend:
            pts = 10 if any(a.status == "rejected" for a in pend) or len(pend) >= 2 else 5
            items = ", ".join(f"{a.kind.replace('_', ' ')} ({a.status})" for a in pend)
            sig(Signal("approvals", pts, _t("approvals", lang, items=items),
                       [{"type": "approval", "id": str(a.id), "is_mock": pr.is_mock} for a in pend]))

        # complaints
        cs = complaints.get(pr.id, [])
        open_cs = [c for c in cs if c.status not in CLOSED]
        if len(open_cs) >= 3:
            sig(Signal("complaints", 10, _t("complaints_open", lang, n=len(open_cs)),
                       [{"type": "complaint", "id": c.ref_no, "is_mock": c.is_mock} for c in open_cs[:5]]))
        recent = sum(1 for c in cs if c.filed_on > today - timedelta(days=182))
        before = sum(1 for c in cs if today - timedelta(days=365) < c.filed_on <= today - timedelta(days=182))
        if recent >= 3 and recent >= 2 * max(1, before):
            sig(Signal("complaints_spike", 10, _t("complaints_spike", lang, recent=recent, before=before),
                       [{"type": "complaint_stats", "id": f"project:{pr.id}", "is_mock": pr.is_mock}]))

        # promoter's record
        others = [x for x in siblings.get(pr.promoter_id, []) if x.id != pr.id]
        delayed = [x for x in others if (x.actual_completion or today) > x.proposed_completion
                   and (x.actual_completion or x.revised_completion or x.proposed_completion) > x.proposed_completion]
        if len(others) >= 2 and len(delayed) / len(others) >= 0.5:
            sig(Signal("promoter_delays", 10, _t("promoter_delays", lang, delayed=len(delayed), total=len(others)),
                       [{"type": "promoter", "id": str(pr.promoter_id), "is_mock": pr.is_mock}]))
        bad = adverse.get(pr.promoter_id, [])
        if bad:
            items = ", ".join(f"{o.order_type.replace('_', ' ')} {o.order_no}" for o in bad[:3])
            sig(Signal("promoter_orders", 10, _t("promoter_orders", lang, items=items),
                       [{"type": "order", "id": o.order_no, "is_mock": pr.is_mock} for o in bad[:3]]))
        unpaid = dues.get(pr.promoter_id, [])
        if unpaid:
            sig(Signal("promoter_dues", 5, _t("promoter_dues", lang, n=len(unpaid),
                                              amount=_inr(sum(d.amount or 0 for d in unpaid))),
                       [{"type": "due_notice", "id": str(d.id), "is_mock": pr.is_mock} for d in unpaid[:3]]))
        out.append(risk)

    out.sort(key=lambda r: (-r.score, r.name))
    repo._audit("risk_watchlist", {"district": district, "projects": len(out),
                                   "high": sum(r.band == HIGH for r in out)})
    return out


def summary(risks: list[ProjectRisk]) -> dict[str, Any]:
    by_band = {b: sum(r.band == b for r in risks) for b in (HIGH, MEDIUM, LOW)}
    by_signal: dict[str, int] = defaultdict(int)
    for r in risks:
        for s_ in {s.code for s in r.signals}:
            by_signal[s_] += 1
    by_district: dict[str, dict[str, int]] = defaultdict(lambda: {HIGH: 0, MEDIUM: 0, LOW: 0})
    for r in risks:
        by_district[r.district][r.band] += 1
    return {"projects": len(risks), "by_band": by_band, "by_signal": dict(sorted(by_signal.items(), key=lambda kv: -kv[1])),
            "by_district": [{"district": d, **v} for d, v in sorted(by_district.items(), key=lambda kv: -kv[1][HIGH])]}


# ------------------------------------------------------------------------ chat
RISK_WORDS = ("risk", "risky", "at-risk", "early warning", "red flag", "watchlist", "watch list",
              "જોખમ", "જોખમી", "जोखिम", "जोखिमी")

CHAT = {
    "overview": {
        "en": "Of {n} ongoing projects{where}, {high} are high risk and {medium} medium risk.",
        "gu": "{where}{n} ચાલુ પ્રોજેક્ટમાંથી {high} ઊંચા જોખમમાં અને {medium} મધ્યમ જોખમમાં છે.",
        "hi": "{where}{n} चालू प्रोजेक्ट में से {high} उच्च जोखिम में और {medium} मध्यम जोखिम में हैं।",
    },
    "top": {
        "en": "Highest: {items}.",
        "gu": "સૌથી વધુ: {items}.",
        "hi": "सबसे अधिक: {items}।",
    },
    "one": {
        "en": "{name} has a risk score of {score}/100 ({band}).",
        "gu": "{name} નો જોખમ સ્કોર {score}/100 ({band}) છે.",
        "hi": "{name} का जोखिम स्कोर {score}/100 ({band}) है।",
    },
    "none": {
        "en": "No warning signals for {name} right now.",
        "gu": "હાલ {name} માટે કોઈ ચેતવણી સંકેત નથી.",
        "hi": "अभी {name} के लिए कोई चेतावनी संकेत नहीं है।",
    },
    "not_ongoing": {
        "en": "{name} is not an ongoing project, so it is not on the risk watchlist.",
        "gu": "{name} ચાલુ પ્રોજેક્ટ નથી, તેથી જોખમ યાદીમાં નથી.",
        "hi": "{name} चालू प्रोजेक्ट नहीं है, इसलिए जोखिम सूची में नहीं है।",
    },
}
BAND_WORD = {"high": {"en": "high", "gu": "ઊંચું", "hi": "उच्च"}, "medium": {"en": "medium", "gu": "મધ્યમ", "hi": "मध्यम"},
             "low": {"en": "low", "gu": "ઓછું", "hi": "कम"}}


def wants_risk(text_lc: str) -> bool:
    return any(w in text_lc for w in RISK_WORDS)


def chat_reply(repo: Repository, lang: str, *, project_id: int | None = None, district: str | None = None):
    """Sentences and a card for an officer's risk question (whole list, or one project)."""
    from gujrera.profile.summarise import Sentence

    def c(key: str, **v: Any) -> str:
        return CHAT[key].get(lang, CHAT[key]["en"]).format(**v)

    risks = score_projects(repo, lang, district=district)
    if project_id is not None:
        r = next((x for x in risks if x.project_id == project_id), None)
        if r is None:
            proj = repo.s.get(Project, project_id)
            name = (proj.name_gu if lang == "gu" and proj.name_gu else proj.name) if proj else str(project_id)
            return [Sentence(c("not_ongoing", name=name), [], "risk_not_ongoing")], None
        name = r.name_gu if lang == "gu" and r.name_gu else r.name
        rec = {"type": "project", "id": r.rera_no, "is_mock": r.is_mock}
        out = [Sentence(c("one", name=name, score=r.score, band=BAND_WORD[r.band][lang]), [rec], "risk_one")]
        out += [Sentence(sg.text, sg.citations, f"risk_{sg.code}") for sg in sorted(r.signals, key=lambda x: -x.points)]
        if not r.signals:
            out.append(Sentence(c("none", name=name), [rec], "risk_none"))
        return out, {"type": "risk", "items": [r.to_dict()], "summary": None}
    sm = summary(risks)
    shown = repo.p.district_scope or district  # a district officer always sees their own district
    where = {"en": f" in {shown}" if shown else "", "gu": f"{shown} માં " if shown else "",
             "hi": f"{shown} में " if shown else ""}[lang]
    out = [Sentence(c("overview", n=sm["projects"], where=where, high=sm["by_band"]["high"],
                      medium=sm["by_band"]["medium"]), [], "risk_overview")]
    top = risks[:3]
    if top:
        items = "; ".join(f"{(r.name_gu if lang == 'gu' and r.name_gu else r.name)} ({r.score})" for r in top)
        out.append(Sentence(c("top", items=items), [{"type": "project", "id": r.rera_no, "is_mock": r.is_mock} for r in top],
                            "risk_top"))
    return out, {"type": "risk", "items": [r.to_dict() for r in risks[:5]], "summary": sm}
