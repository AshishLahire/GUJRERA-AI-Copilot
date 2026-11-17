"""Self-service answers for logged-in promoters and agents.

Everything is read through the role-scoped ``Repository``: a promoter's dues
and notices come from ``dues_notices()``, which refuses other promoters' data.
Each sentence names the record it came from and, where an action is due, the
rule behind it. Section references should be checked against the Act and the
Gujarat Rules before the pilot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from gujrera.db.models import Agent, Promoter
from gujrera.db.repository import Repository
from gujrera.i18n import fmt_date, word
from gujrera.profile.summarise import Sentence

EXPIRY_WARNING_DAYS = 180
QPR_GRACE_DAYS = 15  # report due this many days after the quarter ends

S: dict[str, dict[str, str]] = {
    "hello": {
        "en": "Welcome, {name}. Here is your compliance summary.",
        "gu": "સ્વાગત છે, {name}. આ રહ્યો તમારો અનુપાલન સારાંશ.",
        "hi": "स्वागत है, {name}। यह रहा आपका अनुपालन सारांश।",
    },
    "dues": {
        "en": "Pending dues: {n}, totalling ₹{amount}; earliest due date {date}.",
        "gu": "બાકી ચુકવણીઓ: {n}, કુલ ₹{amount}; સૌથી વહેલી નિયત તારીખ {date}.",
        "hi": "बकाया भुगतान: {n}, कुल ₹{amount}; सबसे पहली नियत तारीख {date}।",
    },
    "overdue": {
        "en": "Overdue: {n}.",
        "gu": "મુદત વીતી ગયેલી: {n}.",
        "hi": "नियत तारीख निकल चुकी: {n}।",
    },
    "no_dues": {
        "en": "No dues are pending.",
        "gu": "કોઈ ચુકવણી બાકી નથી.",
        "hi": "कोई भुगतान बकाया नहीं है।",
    },
    "notices": {
        "en": "Notices awaiting your response: {n}. Latest ({date}): {desc}",
        "gu": "જવાબ બાકી હોય તેવી નોટિસ: {n}. છેલ્લી ({date}): {desc}",
        "hi": "जवाब के लिए लंबित नोटिस: {n}। नवीनतम ({date}): {desc}",
    },
    "no_notices": {
        "en": "No notices are awaiting a response.",
        "gu": "કોઈ નોટિસ જવાબ માટે બાકી નથી.",
        "hi": "कोई नोटिस जवाब के लिए लंबित नहीं है।",
    },
    "qpr_missing": {
        "en": "Quarterly progress reports not filed for {project}: {quarters} (RERA Act, Section 11).",
        "gu": "{project} માટે ત્રિમાસિક પ્રગતિ અહેવાલ ફાઈલ થયા નથી: {quarters} (RERA કાયદો, કલમ 11).",
        "hi": "{project} के लिए तिमाही प्रगति रिपोर्ट दाखिल नहीं हुईं: {quarters} (RERA अधिनियम, धारा 11)।",
    },
    "qpr_ok": {
        "en": "All quarterly progress reports due so far have been filed.",
        "gu": "અત્યાર સુધીના બધા ત્રિમાસિક પ્રગતિ અહેવાલ ફાઈલ થઈ ગયા છે.",
        "hi": "अब तक की सभी तिमाही प्रगति रिपोर्ट दाखिल हो चुकी हैं।",
    },
    "qpr_next": {
        "en": "The next quarterly progress report for your {n} ongoing projects is due on {date}.",
        "gu": "તમારા {n} ચાલુ પ્રોજેક્ટ માટે આગામી ત્રિમાસિક પ્રગતિ અહેવાલ {date} સુધીમાં ભરવાનો છે.",
        "hi": "आपके {n} चालू प्रोजेक्ट्स की अगली तिमाही प्रगति रिपोर्ट {date} तक देय है।",
    },
    "expiring": {
        "en": "Registration of {project} is valid until {date}. If it will not be completed by then, "
              "apply for an extension (RERA Act, Section 6).",
        "gu": "{project} ની નોંધણી {date} સુધી માન્ય છે. ત્યાં સુધીમાં પૂર્ણ ન થાય તો મુદત વધારા માટે અરજી કરો "
              "(RERA કાયદો, કલમ 6).",
        "hi": "{project} का पंजीकरण {date} तक मान्य है। यदि तब तक पूरा नहीं होगा, तो विस्तार के लिए आवेदन करें "
              "(RERA अधिनियम, धारा 6)।",
    },
    "lapsed": {
        "en": "Registration of {project} ended on {date} while the project is not complete.",
        "gu": "પ્રોજેક્ટ પૂર્ણ થયા વિના {project} ની નોંધણી {date} ના રોજ પૂરી થઈ ગઈ.",
        "hi": "प्रोजेक्ट पूरा हुए बिना {project} का पंजीकरण {date} को समाप्त हो गया।",
    },
    "no_expiry": {
        "en": "No registration expires in the next six months.",
        "gu": "આગામી છ મહિનામાં કોઈ નોંધણીની મુદત પૂરી થતી નથી.",
        "hi": "अगले छह महीनों में किसी पंजीकरण की अवधि समाप्त नहीं हो रही।",
    },
    "approvals": {
        "en": "Pending approvals for {project}: {items}.",
        "gu": "{project} માટે બાકી મંજૂરીઓ: {items}.",
        "hi": "{project} के लिए लंबित अनुमोदन: {items}।",
    },
    "complaints": {
        "en": "Open complaints against your projects: {open} (of {total} filed).",
        "gu": "તમારા પ્રોજેક્ટ સામે ખુલ્લી ફરિયાદો: {open} (કુલ {total} માંથી).",
        "hi": "आपके प्रोजेक्ट्स के खिलाफ लंबित शिकायतें: {open} (कुल {total} में से)।",
    },
    "agent": {
        "en": "Your agent registration {reg} is {status}, valid until {date}.",
        "gu": "તમારી એજન્ટ નોંધણી {reg} {status} છે, {date} સુધી માન્ય.",
        "hi": "आपका एजेंट पंजीकरण {reg} {status} है, {date} तक मान्य।",
    },
    "agent_renew": {
        "en": "Apply for renewal before {date} to keep dealing in registered projects (RERA Act, Section 9).",
        "gu": "નોંધાયેલ પ્રોજેક્ટમાં કામ ચાલુ રાખવા {date} પહેલાં નવીનીકરણ માટે અરજી કરો (RERA કાયદો, કલમ 9).",
        "hi": "पंजीकृत प्रोजेक्ट्स में काम जारी रखने के लिए {date} से पहले नवीनीकरण के लिए आवेदन करें "
              "(RERA अधिनियम, धारा 9)।",
    },
    "agent_complaints": {
        "en": "Complaints naming you as the agent: {n}.",
        "gu": "તમારું નામ એજન્ટ તરીકે હોય તેવી ફરિયાદો: {n}.",
        "hi": "जिन शिकायतों में आपका नाम एजेंट के रूप में है: {n}।",
    },
    "login_required": {
        "en": "Dues, notices and filings are private. Please log in as the promoter or agent to see them.",
        "gu": "બાકી ચુકવણી, નોટિસ અને ફાઈલિંગ ખાનગી છે. તે જોવા માટે પ્રમોટર અથવા એજન્ટ તરીકે લોગિન કરો.",
        "hi": "बकाया, नोटिस और फाइलिंग निजी हैं। इन्हें देखने के लिए प्रमोटर या एजेंट के रूप में लॉगिन करें।",
    },
    "only_own": {
        "en": "You can only see your own dues, notices and filings.",
        "gu": "તમે ફક્ત તમારી પોતાની બાકી ચુકવણી, નોટિસ અને ફાઈલિંગ જોઈ શકો છો.",
        "hi": "आप केवल अपने बकाया, नोटिस और फाइलिंग देख सकते हैं।",
    },
}

# Which summary sections a question asks for.
FOCUS_WORDS: dict[str, tuple[str, ...]] = {
    "dues": ("due", "dues", "fee", "fees", "penalty", "pay", "payment", "outstanding", "owe",
             "બાકી", "ફી", "દંડ", "ચુકવણી", "बकाया", "शुल्क", "जुर्माना", "भुगतान"),
    "notices": ("notice", "notices", "show cause", "show-cause", "નોટિસ", "नोटिस"),
    "qpr": ("qpr", "quarterly", "progress report", "filing", "filings", "ત્રિમાસિક", "અહેવાલ", "तिमाही", "रिपोर्ट"),
    "registration": ("registration", "expire", "expiry", "extension", "renew", "validity",
                     "નોંધણી", "મુદત", "નવીનીકરણ", "पंजीकरण", "विस्तार", "नवीनीकरण"),
    "approvals": ("approval", "approvals", "noc", "permission", "મંજૂરી", "अनुमोदन", "मंजूरी"),
    "complaints": ("complaint", "complaints", "ફરિયાદ", "शिकायत"),
}
SELF_WORDS = ("my ", "mine", "our ", "pending", "summary", "compliance", "dashboard", "what do i",
              "મારા", "મારી", "મારું", "મારો", "અમારા", "સારાંશ", "अनुपालन", "मेरे", "मेरी", "मेरा", "हमारे", "सारांश", "અનુપાલન")


def s(key: str, lang: str, **values: Any) -> str:
    entry = S[key]
    return entry.get(lang, entry["en"]).format(**values)


def fmt_inr(amount: float) -> str:
    """Indian digit grouping: 1234567 → 12,34,567."""
    n = int(round(amount))
    text = str(n)
    if len(text) <= 3:
        return text
    head, tail = text[:-3], text[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def focus_of(text_lc: str) -> set[str]:
    return {f for f, words in FOCUS_WORDS.items() if any(w in text_lc for w in words)}


PRIVATE_WORDS = ("dues", "outstanding", "what do i owe", "બાકી ચુકવણી", "बकाया")


SUMMARY_WORDS = ("compliance", "summary", "dashboard", "what is pending", "what's pending",
                 "અનુપાલન", "સારાંશ", "अनुपालन", "सारांश")


def is_self_service(text_lc: str) -> bool:
    """A question about the asker's own compliance ("my dues", "pending notices", "my compliance summary")."""
    own = any(w in text_lc for w in (*SELF_WORDS, *PRIVATE_WORDS))
    return own and (bool(focus_of(text_lc)) or any(w in text_lc for w in SUMMARY_WORDS))


@dataclass
class Summary:
    sentences: list[Sentence] = field(default_factory=list)
    card: dict[str, Any] = field(default_factory=dict)
    is_mock: bool = False

    def add(self, key: str, lang: str, citations: list[dict[str, Any]], **values: Any) -> None:
        self.sentences.append(Sentence(s(key, lang, **values), citations, f"ss_{key}"))


def _next_qpr_due(today: date) -> date:
    q_end_month = ((today.month - 1) // 3 + 1) * 3
    q_end = date(today.year + (q_end_month == 12), q_end_month % 12 + 1, 1) - timedelta(days=1)
    due = q_end + timedelta(days=QPR_GRACE_DAYS)
    if due < today:  # this quarter's report window closed; the next one applies
        nxt = q_end + timedelta(days=1)
        q2_end_month = ((nxt.month - 1) // 3 + 1) * 3
        q2_end = date(nxt.year + (q2_end_month == 12), q2_end_month % 12 + 1, 1) - timedelta(days=1)
        due = q2_end + timedelta(days=QPR_GRACE_DAYS)
    return due


def promoter_summary(repo: Repository, lang: str, focus: set[str] | None = None,
                     today: date | None = None) -> Summary:
    """Compliance summary for the logged-in promoter (raises AccessDenied for anyone else)."""
    today = today or date.today()
    want = focus or set(FOCUS_WORDS)
    dues_all = repo.dues_notices()  # role-scoped: only the caller's promoter
    promoter = repo.s.get(Promoter, repo.p.promoter_id)
    out = Summary(is_mock=promoter.is_mock)
    out.add("hello", lang, [{"type": "promoter", "id": str(promoter.id), "is_mock": promoter.is_mock}],
            name=(promoter.name_gu if lang == "gu" and promoter.name_gu else promoter.name))
    projects = repo.promoter_projects(promoter.id)
    ongoing = [p for p in projects if p["status"] == "ongoing"]
    card: dict[str, Any] = {"type": "self_service", "role": "developer", "name": promoter.name,
                            "is_mock": promoter.is_mock, "dues": [], "notices": [], "qpr_missing": [],
                            "registrations": []}

    if "dues" in want:
        pending = [d for d in dues_all if d["kind"] != "notice" and d["status"] == "pending"]
        if pending:
            total = sum(d["amount"] or 0 for d in pending)
            earliest = min(d["due_date"] for d in pending if d["due_date"])
            overdue = [d for d in pending if d["due_date"] and d["due_date"] < today]
            out.add("dues", lang, [d["source"] for d in pending], n=len(pending), amount=fmt_inr(total),
                    date=fmt_date(earliest, lang))
            if overdue:
                out.add("overdue", lang, [d["source"] for d in overdue], n=len(overdue))
        else:
            out.add("no_dues", lang, [])
        card["dues"] = [{"description": d["description"], "amount": d["amount"], "due_date": d["due_date"],
                         "status": d["status"], "overdue": bool(d["due_date"] and d["due_date"] < today)}
                        for d in pending]
    if "notices" in want:
        notices = [d for d in dues_all if d["kind"] == "notice" and d["status"] == "pending"]
        if notices:
            latest = max(notices, key=lambda d: d["issued_on"])
            # Notice text is stored in English; shown as issued.
            out.add("notices", lang, [d["source"] for d in notices], n=len(notices),
                    date=fmt_date(latest["issued_on"], lang), desc=latest["description"])
        else:
            out.add("no_notices", lang, [])
        card["notices"] = [{"description": d["description"], "issued_on": d["issued_on"],
                            "due_date": d["due_date"]} for d in notices]
    if "qpr" in want:
        any_missing = False
        for p in ongoing:  # reports that can still be filed
            missing = [r for r in repo.project_progress(p["id"]) if not r["filed_on"]]
            if missing:
                any_missing = True
                quarters = ", ".join(r["quarter"] for r in missing[-4:])
                out.add("qpr_missing", lang, [r["source"] for r in missing[-4:]],
                        project=p["name"], quarters=quarters)
                card["qpr_missing"].append({"project": p["name"], "quarters": [r["quarter"] for r in missing]})
        if not any_missing:
            out.add("qpr_ok", lang, [p["source"] for p in ongoing])
        if ongoing:
            out.add("qpr_next", lang, [p["source"] for p in ongoing], n=len(ongoing),
                    date=fmt_date(_next_qpr_due(today), lang))
    if "registration" in want:
        flagged = False
        for p in ongoing:
            until = p["reg_valid_until"]
            if until < today:
                out.add("lapsed", lang, [p["source"]], project=p["name"], date=fmt_date(until, lang))
                flagged = True
            elif (until - today).days <= EXPIRY_WARNING_DAYS:
                out.add("expiring", lang, [p["source"]], project=p["name"], date=fmt_date(until, lang))
                flagged = True
            card["registrations"].append({"project": p["name"], "rera_no": p["rera_no"], "valid_until": until,
                                          "days_left": (until - today).days})
        if not flagged:
            out.add("no_expiry", lang, [p["source"] for p in ongoing])
    if "approvals" in want:
        for p in projects:
            pending = [a for a in repo.project_approvals(p["id"]) if a["status"] == "pending"]
            if pending:
                out.add("approvals", lang, [a["source"] for a in pending], project=p["name"],
                        items=", ".join(word(a["kind"], lang) for a in pending))
    if "complaints" in want:
        counts = repo.complaint_counts(promoter_id=promoter.id)
        if counts["total"]:
            out.add("complaints", lang, [counts["source"]], open=counts["open"], total=counts["total"])
    out.card = card
    return out


def agent_summary(repo: Repository, lang: str, today: date | None = None) -> Summary:
    today = today or date.today()
    agent = repo.s.get(Agent, repo.p.agent_id)
    src = {"type": "agent", "id": agent.reg_no, "is_mock": agent.is_mock}
    out = Summary(is_mock=agent.is_mock)
    out.add("hello", lang, [src], name=(agent.name_gu if lang == "gu" and agent.name_gu else agent.name))
    status = {"active": {"en": "active", "gu": "સક્રિય", "hi": "सक्रिय"},
              "expired": {"en": "expired", "gu": "મુદત પૂરી", "hi": "समाप्त"},
              "revoked": {"en": "revoked", "gu": "રદ", "hi": "रद्द"}}[agent.status]
    out.add("agent", lang, [src], reg=agent.reg_no, status=status.get(lang, status["en"]),
            date=fmt_date(agent.valid_until, lang))
    if agent.status == "active" and (agent.valid_until - today).days <= EXPIRY_WARNING_DAYS:
        out.add("agent_renew", lang, [src], date=fmt_date(agent.valid_until, lang))
    mine = repo.list_complaints()  # role-scoped: complaints naming this agent
    if mine:
        out.add("agent_complaints", lang, [c["source"] for c in mine[:5]], n=len(mine))
    out.card = {"type": "self_service", "role": "agent", "name": agent.name, "reg_no": agent.reg_no,
                "status": agent.status, "valid_until": agent.valid_until, "complaints": len(mine),
                "is_mock": agent.is_mock}
    return out
