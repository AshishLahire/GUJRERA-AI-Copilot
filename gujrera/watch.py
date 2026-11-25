"""Project watch: a logged-in buyer follows a project and gets alerts when something happens to it.

Alerts are built from the registry's own dated records, so no background job is needed to detect them:

  qpr_filed      a quarterly progress report was filed (with the new percentage built)
  qpr_missed     a quarterly report's due date passed without a filing (Section 11)
  extension      GUJRERA extended the registration / completion date (extension order)
  order          another order on the project (penalty, show-cause, revocation, complaint order)
  order_overdue  an order's deadline passed without compliance (gujrera.orders)
  reg_ending     the registration ends within 90 days and the project is not complete (Section 6)
  reg_expired    the registration ended while the project is still under construction
  reg_passed     public records: the registered end date passed and no completion is on record
  complaints     new complaints filed on the project in a month (counts only)

Unread = dated after the buyer last opened their alerts. Delivery by SMS or WhatsApp is a hand-off
(Notifier): the prototype stores no phone numbers; `digest()` returns what would be sent and
scripts/send_watch_alerts.py prints it. Buyers (citizen accounts) only; each sees only their own watches.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Protocol

from sqlalchemy import func, select

from gujrera.db.models import Complaint, Order, OrderCompliance, Project, ProjectProgress, ProjectWatch, User
from gujrera.db.repository import AccessDenied, Repository
from gujrera.i18n import fmt_date

MAX_WATCHES = 20
LOOKBACK_DAYS = 365
GOOD, WARN, BAD, INFO = "good", "warn", "bad", "info"

T: dict[str, dict[str, str]] = {
    "qpr_filed": {"en": "Quarterly report for {q} filed: {pct}% built{change}.",
                  "gu": "{q} નો ત્રિમાસિક અહેવાલ ફાઈલ થયો: {pct}% બાંધકામ{change}.",
                  "hi": "{q} की तिमाही रिपोर्ट दाखिल हुई: {pct}% निर्माण{change}।"},
    "change_up": {"en": " (up from {prev}%)", "gu": " ({prev}% થી વધીને)", "hi": " ({prev}% से बढ़कर)"},
    "change_down": {"en": " (down from {prev}%: ask the promoter why)", "gu": " ({prev}% થી ઘટીને: પ્રમોટરને કારણ પૂછો)",
                    "hi": " ({prev}% से घटकर: प्रमोटर से कारण पूछें)"},
    "change_none": {"en": " (no progress since {prev}%)", "gu": " ({prev}% પછી કોઈ પ્રગતિ નહીં)", "hi": " ({prev}% के बाद कोई प्रगति नहीं)"},
    "qpr_missed": {"en": "Quarterly report for {q} was due on {date} and has not been filed (Section 11).",
                   "gu": "{q} નો ત્રિમાસિક અહેવાલ {date} એ ફાઈલ કરવાનો હતો, હજી થયો નથી (કલમ 11).",
                   "hi": "{q} की तिमाही रिपोर्ट {date} को देय थी, अभी दाखिल नहीं हुई (धारा 11)।"},
    "extension": {"en": "GUJRERA extended the registration (order {no}); the completion date is now {date}.",
                  "gu": "GUJRERA એ નોંધણી લંબાવી (આદેશ {no}); પૂર્ણતા તારીખ હવે {date} છે.",
                  "hi": "GUJRERA ने पंजीकरण बढ़ाया (आदेश {no}); पूर्णता तारीख अब {date} है।"},
    "order": {"en": "New {kind} on this project: {no}.", "gu": "આ પ્રોજેક્ટ પર નવો {kind}: {no}.",
              "hi": "इस प्रोजेक्ट पर नया {kind}: {no}।"},
    "order_overdue": {"en": "Order {no} was to be complied with by {date}; it has not been done yet.",
                      "gu": "આદેશ {no} નું {date} સુધીમાં પાલન કરવાનું હતું; હજી થયું નથી.",
                      "hi": "आदेश {no} का {date} तक पालन करना था; अभी नहीं हुआ।"},
    "reg_ending": {"en": "The registration ends on {date}; ask the promoter whether an extension has been applied for (Section 6).",
                   "gu": "નોંધણી {date} એ પૂરી થાય છે; મુદત વધારા માટે અરજી થઈ છે કે નહીં તે પ્રમોટરને પૂછો (કલમ 6).",
                   "hi": "पंजीकरण {date} को समाप्त होता है; प्रमोटर से पूछें कि विस्तार का आवेदन हुआ है या नहीं (धारा 6)।"},
    "reg_expired": {"en": "The registration ended on {date} while the project is still under construction.",
                    "gu": "પ્રોજેક્ટ હજી બાંધકામ હેઠળ છે ત્યારે નોંધણી {date} એ પૂરી થઈ ગઈ.",
                    "hi": "प्रोजेक्ट अभी निर्माणाधीन है और पंजीकरण {date} को समाप्त हो गया।"},
    "reg_passed": {"en": "The registered completion date {date} has passed and no completion is on record{ext}. Ask the promoter for the completion certificate or the extension order. If your possession is late, you can claim interest for the delay (Section 18).",
                   "gu": "નોંધાયેલી પૂર્ણતા તારીખ {date} વીતી ગઈ છે અને પૂર્ણતા નોંધાયેલ નથી{ext}. પ્રમોટર પાસે પૂર્ણતા પ્રમાણપત્ર અથવા મુદત વધારાનો આદેશ માંગો. પઝેશન મોડું હોય તો તમે વિલંબનું વ્યાજ માંગી શકો (કલમ 18).",
                   "hi": "पंजीकृत पूर्णता तिथि {date} बीत चुकी है और पूर्णता दर्ज नहीं है{ext}। प्रमोटर से पूर्णता प्रमाणपत्र या विस्तार आदेश माँगें। कब्ज़ा देर से मिले तो आप देरी का ब्याज माँग सकते हैं (धारा 18)।"},
    "ext_note": {"en": "; the registration number shows {n} extension(s)", "gu": "; નોંધણી નંબરમાં {n} મુદત વધારા દેખાય છે",
                 "hi": "; पंजीकरण संख्या में {n} विस्तार दिखते हैं"},
    "complaints": {"en": "{n} new complaint(s) filed on this project in {month}.",
                   "gu": "{month} માં આ પ્રોજેક્ટ પર {n} નવી ફરિયાદ નોંધાઈ.",
                   "hi": "{month} में इस प्रोजेक्ट पर {n} नई शिकायतें दर्ज हुईं।"},
}
ORDER_KIND = {
    "penalty_order": {"en": "penalty order", "gu": "દંડ આદેશ", "hi": "जुर्माना आदेश"},
    "show_cause": {"en": "show-cause notice", "gu": "કારણદર્શક નોટિસ", "hi": "कारण बताओ नोटिस"},
    "revocation_order": {"en": "revocation order", "gu": "નોંધણી રદ કરવાનો આદેશ", "hi": "पंजीकरण रद्द करने का आदेश"},
    "complaint_order": {"en": "complaint order", "gu": "ફરિયાદ આદેશ", "hi": "शिकायत आदेश"},
}
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]


def _t(key: str, lang: str, **v: Any) -> str:
    return T[key].get(lang, T[key]["en"]).format(**v)


def _act(sec: str) -> dict[str, Any]:
    return {"type": "legal_act", "id": f"RERA Act, 2016, Section {sec}", "is_mock": False}


def _buyer(repo: Repository) -> int:
    if repo.p.role != "citizen" or repo.p.user_id is None:
        raise AccessDenied("Log in with a buyer account to watch projects.")
    return repo.p.user_id


def project_events(session, project: Project, lang: str, *, since: date, today: date) -> list[dict[str, Any]]:
    """Dated events for one project between `since` and `today`, newest first."""
    rec = {"type": "project", "id": project.rera_no, "is_mock": bool(project.is_mock)}
    events: list[dict[str, Any]] = []

    def add(d: date, kind: str, tone: str, text: str, cites: list[dict[str, Any]]) -> None:
        if since <= d <= today:
            events.append({"date": d.isoformat(), "kind": kind, "tone": tone, "text": text, "citations": cites})

    rows = session.scalars(select(ProjectProgress).where(ProjectProgress.project_id == project.id)
                           .order_by(ProjectProgress.quarter)).all()
    prev_pct = None
    for r in rows:
        cite = [{"type": "progress_report", "id": f"{project.id}:{r.quarter}", "is_mock": bool(project.is_mock)}]
        if r.filed_on:
            change = ("" if prev_pct is None else _t("change_up", lang, prev=round(prev_pct, 1)) if r.percent_complete > prev_pct
                      else _t("change_down", lang, prev=round(prev_pct, 1)) if r.percent_complete < prev_pct
                      else _t("change_none", lang, prev=round(prev_pct, 1)))
            tone = GOOD if prev_pct is None or r.percent_complete > prev_pct else BAD if r.percent_complete < prev_pct else WARN
            add(r.filed_on, "qpr_filed", tone,
                _t("qpr_filed", lang, q=r.quarter, pct=round(r.percent_complete, 1), change=change), cite)
            prev_pct = r.percent_complete
        elif r.due_on < today and project.status == "ongoing":
            add(r.due_on, "qpr_missed", BAD, _t("qpr_missed", lang, q=r.quarter, date=fmt_date(r.due_on, lang)), cite + [_act("11")])

    for o in session.scalars(select(Order).where(Order.project_id == project.id)):
        cite = [{"type": "order", "id": o.order_no, "is_mock": bool(o.is_mock)}]
        if o.order_type == "extension_order":
            add(o.issued_on, "extension", WARN,
                _t("extension", lang, no=o.order_no, date=fmt_date(project.revised_completion or project.proposed_completion, lang)), cite)
        else:
            kind = ORDER_KIND.get(o.order_type, {}).get(lang, o.order_type.replace("_", " "))
            add(o.issued_on, "order", BAD if o.order_type != "complaint_order" else INFO,
                _t("order", lang, kind=kind, no=o.order_no), cite)
    for o, rec_c in session.execute(select(Order, OrderCompliance).join(OrderCompliance, OrderCompliance.order_id == Order.id)
                                    .where(Order.project_id == project.id, OrderCompliance.status == "pending",
                                           OrderCompliance.due_on < today)).all():
        add(rec_c.due_on + timedelta(days=1), "order_overdue", BAD,
            _t("order_overdue", lang, no=o.order_no, date=fmt_date(rec_c.due_on, lang)),
            [{"type": "order", "id": o.order_no, "is_mock": bool(o.is_mock)}, _act("63")])

    if project.status == "unverified":
        from gujrera.officer_desk import _extensions

        n_ext = _extensions(project.rera_no)
        ext = _t("ext_note", lang, n=n_ext) if n_ext else ""
        # A standing condition, not a one-off event: keep it visible however long ago the date passed.
        add(max(since, min(project.reg_valid_until, today)), "reg_passed", BAD,
            _t("reg_passed", lang, date=fmt_date(project.reg_valid_until, lang), ext=ext), [rec, _act("18")])
    if project.status == "ongoing":
        if project.reg_valid_until < today:
            add(project.reg_valid_until, "reg_expired", BAD, _t("reg_expired", lang, date=fmt_date(project.reg_valid_until, lang)), [rec])
        else:
            add(project.reg_valid_until - timedelta(days=90), "reg_ending", WARN,
                _t("reg_ending", lang, date=fmt_date(project.reg_valid_until, lang)), [rec, _act("6")])

    months = Counter((c.filed_on.year, c.filed_on.month) for c in session.scalars(
        select(Complaint).where(Complaint.project_id == project.id, Complaint.filed_on >= since)))
    for (y, m), n in months.items():
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        month = fmt_date(date(y, m, 1), lang).split(" ", 1)[1] if lang != "en" else f"{MONTHS_EN[m - 1]} {y}"
        add(min(last, today), "complaints", WARN if n >= 2 else INFO, _t("complaints", lang, n=n, month=month),
            [{"type": "complaint_stats", "id": f"project:{project.id}", "is_mock": bool(project.is_mock)}])
    events.sort(key=lambda e: e["date"], reverse=True)
    return events


# ------------------------------------------------------------------------ buyers
def add_watch(repo: Repository, project_id: int, *, today: date | None = None) -> dict[str, Any]:
    uid = _buyer(repo)
    today = today or date.today()
    if repo.s.get(Project, project_id) is None:
        raise ValueError("Project not found.")
    existing = repo.s.scalar(select(ProjectWatch).where(ProjectWatch.user_id == uid, ProjectWatch.project_id == project_id))
    if existing:
        return {"watching": True, "created": False, "project_id": project_id}
    if (repo.s.scalar(select(func.count()).select_from(ProjectWatch).where(ProjectWatch.user_id == uid)) or 0) >= MAX_WATCHES:
        raise ValueError(f"You can watch up to {MAX_WATCHES} projects. Stop watching one first.")
    repo.s.add(ProjectWatch(user_id=uid, project_id=project_id, created_on=today, last_seen_on=today))
    repo.s.flush()
    repo._audit("watch_added", {"project_id": project_id})
    return {"watching": True, "created": True, "project_id": project_id}


def remove_watch(repo: Repository, project_id: int) -> bool:
    uid = _buyer(repo)
    w = repo.s.scalar(select(ProjectWatch).where(ProjectWatch.user_id == uid, ProjectWatch.project_id == project_id))
    if w is None:
        return False
    repo.s.delete(w)
    repo.s.flush()
    repo._audit("watch_removed", {"project_id": project_id})
    return True


def my_watches(repo: Repository, lang: str = "en", *, as_of: date | None = None, limit: int = 15) -> dict[str, Any]:
    uid = _buyer(repo)
    today = as_of or date.today()
    out = []
    for w in repo.s.scalars(select(ProjectWatch).where(ProjectWatch.user_id == uid).order_by(ProjectWatch.created_on.desc())):
        p = repo.s.get(Project, w.project_id)
        events = project_events(repo.s, p, lang, since=today - timedelta(days=LOOKBACK_DAYS), today=today)
        for e in events:
            e["unread"] = e["date"] > w.last_seen_on.isoformat()
        out.append({"project_id": p.id, "name": p.name, "name_gu": p.name_gu, "rera_no": p.rera_no, "district": p.district,
                    "status": p.status, "watching_since": w.created_on.isoformat(), "last_seen_on": w.last_seen_on.isoformat(),
                    "unread": sum(e["unread"] for e in events), "events": events[:limit]})
    return {"watches": out, "unread": sum(w["unread"] for w in out), "as_of": today.isoformat()}


def unread_count(repo: Repository, *, as_of: date | None = None) -> int:
    if repo.p.role != "citizen" or repo.p.user_id is None:
        return 0
    return my_watches(repo, "en", as_of=as_of, limit=0)["unread"]


def mark_seen(repo: Repository, project_id: int | None = None, *, today: date | None = None) -> int:
    uid = _buyer(repo)
    today = today or date.today()
    stmt = select(ProjectWatch).where(ProjectWatch.user_id == uid)
    if project_id is not None:
        stmt = stmt.where(ProjectWatch.project_id == project_id)
    n = 0
    for w in repo.s.scalars(stmt):
        w.last_seen_on = today
        n += 1
    repo.s.flush()
    return n


# ------------------------------------------------------------------ delivery hand-off
class Notifier(Protocol):
    def send(self, user: User, lines: list[str]) -> None: ...


class MockNotifier:
    """Collects what would be sent. GUJRERA's SMS/WhatsApp gateway replaces this in the PoC."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[str]]] = []

    def send(self, user: User, lines: list[str]) -> None:
        self.sent.append((user.username, lines))


def digest(session, notifier: Notifier, *, since: date, today: date | None = None) -> int:
    """Send each buyer the alerts dated after `since` for the projects they watch. Returns users notified."""
    today = today or date.today()
    by_user: dict[int, list[str]] = {}
    for w in session.scalars(select(ProjectWatch)):
        user = session.get(User, w.user_id)
        p = session.get(Project, w.project_id)
        lang = user.preferred_lang if user.preferred_lang in ("gu", "hi", "en") else "gu"
        for e in project_events(session, p, lang, since=max(since, w.created_on), today=today):
            by_user.setdefault(w.user_id, []).append(f"{p.name}: {e['text']}")
    for uid, lines in by_user.items():
        notifier.send(session.get(User, uid), lines[:10])
    return len(by_user)


def seed_watches(session, *, as_of: date | None = None) -> int:
    """The demo buyer citizen_01 watches three ongoing projects with recent activity."""
    today = as_of or date.today()
    user = session.scalar(select(User).where(User.username == "citizen_01"))
    if user is None or session.scalar(select(ProjectWatch.id).where(ProjectWatch.user_id == user.id)):
        return 0
    picks = session.scalars(select(Project).where(Project.status == "ongoing").order_by(Project.id)).all()
    chosen = [p for p in picks if project_events(session, p, "en", since=today - timedelta(days=120), today=today)][:3]
    for p in chosen:
        session.add(ProjectWatch(user_id=user.id, project_id=p.id, created_on=today - timedelta(days=200),
                                 last_seen_on=today - timedelta(days=60)))
    session.commit()
    return len(chosen)


# ------------------------------------------------------------------------ chat
WATCH_WORDS = ("watch ", "follow ", "notify me", "alert me", "keep me updated", "updates on", "નજર રાખો", "અપડેટ આપ",
               "જાણ કરજો", "सूचना दें", "अपडेट दें", "नज़र रखें", "नजर रखें")
FEED_WORDS = ("my alerts", "what's new", "whats new", "my watched", "watched projects", "my watchlist",
              "મારા એલર્ટ", "નવું શું", "मेरे अलर्ट", "नया क्या")
_C = {
    "added": {"en": "You are now watching {name}. Alerts will appear under Watched projects when reports, orders or registration dates change.",
              "gu": "તમે હવે {name} પર નજર રાખી રહ્યા છો. અહેવાલ, આદેશ કે નોંધણીની તારીખમાં ફેરફાર થાય ત્યારે 'નજર હેઠળના પ્રોજેક્ટ' માં એલર્ટ દેખાશે.",
              "hi": "आप अब {name} पर नज़र रख रहे हैं। रिपोर्ट, आदेश या पंजीकरण तारीख बदलने पर 'निगरानी वाले प्रोजेक्ट' में अलर्ट दिखेंगे।"},
    "already": {"en": "You are already watching {name}.", "gu": "તમે {name} પર પહેલેથી નજર રાખો છો.",
                "hi": "आप पहले से {name} पर नज़र रख रहे हैं।"},
    "login": {"en": "Log in with a buyer account to watch projects and get alerts.",
              "gu": "પ્રોજેક્ટ પર નજર રાખવા અને એલર્ટ મેળવવા ખરીદનાર ખાતાથી લોગિન કરો.",
              "hi": "प्रोजेक्ट पर नज़र रखने और अलर्ट पाने के लिए खरीदार खाते से लॉगिन करें।"},
    "feed": {"en": "{n} new alert(s) on the projects you watch.", "gu": "તમારા નજર હેઠળના પ્રોજેક્ટ પર {n} નવા એલર્ટ.",
             "hi": "आपके निगरानी वाले प्रोजेक्ट पर {n} नए अलर्ट।"},
    "none": {"en": "You are not watching any project yet. Say 'watch' and the project name.",
             "gu": "તમે હજી કોઈ પ્રોજેક્ટ પર નજર રાખતા નથી. પ્રોજેક્ટનું નામ લખીને 'નજર રાખો' કહો.",
             "hi": "आप अभी किसी प्रोजेक्ट पर नज़र नहीं रख रहे। प्रोजेक्ट का नाम लिखकर 'नज़र रखें' कहें।"},
}


def _c(key: str, lang: str, **v: Any) -> str:
    return _C[key].get(lang, _C[key]["en"]).format(**v)


def wants_watch(text_lc: str) -> bool:
    return any(w in text_lc + " " for w in WATCH_WORDS)


def wants_feed(text_lc: str) -> bool:
    return any(w in text_lc for w in FEED_WORDS)


def chat_watch(repo: Repository, project_id: int, lang: str):
    from gujrera.profile.summarise import Sentence

    p = repo.s.get(Project, project_id)
    name = (p.name_gu if lang == "gu" and p.name_gu else p.name).replace(" (Demo)", "").replace(" (ડેમો)", "")
    if repo.p.role != "citizen" or repo.p.user_id is None:
        return [Sentence(_c("login", lang), [], "watch_login")], None
    res = add_watch(repo, project_id)
    rec = {"type": "project", "id": p.rera_no, "is_mock": bool(p.is_mock)}
    return [Sentence(_c("added" if res["created"] else "already", lang, name=name), [rec], "watch_added")], \
        {"type": "watch", "project_id": p.id}


def chat_feed(repo: Repository, lang: str):
    from gujrera.profile.summarise import Sentence

    if repo.p.role != "citizen" or repo.p.user_id is None:
        return [Sentence(_c("login", lang), [], "watch_login")], None
    data = my_watches(repo, lang, limit=5)
    if not data["watches"]:
        return [Sentence(_c("none", lang), [], "watch_none")], None
    out = [Sentence(_c("feed", lang, n=data["unread"]), [], "watch_feed")]
    for w in data["watches"]:
        for e in [e for e in w["events"] if e["unread"]][:2]:
            out.append(Sentence(f"{w['name'].replace(' (Demo)', '')}: {e['text']}", e["citations"], "watch_event"))
    return out, {"type": "watch_feed", "unread": data["unread"]}
