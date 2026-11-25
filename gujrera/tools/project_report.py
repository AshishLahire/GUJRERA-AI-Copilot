"""Before-you-buy project report: one page a buyer can save as PDF and share with their bank or family.

Built only from public registry data through the role-checked Repository (registration, approvals,
quarterly progress reports, orders, complaint counts, the promoter's record). Every finding carries
the records it comes from. The report ends with questions to ask the promoter, generated from what
was found, and the buyer's main rights under the RERA Act with section numbers.

Complaints appear as counts only, never complaint records or complainants.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from gujrera.db.repository import Repository
from gujrera.i18n import fmt_date, word

GOOD, WARN, BAD = "good", "warn", "bad"
CLOSED = ("disposed", "withdrawn")

T: dict[str, dict[str, str]] = {
    # at a glance
    "reg_valid": {"en": "Registered with GUJRERA, valid until {date}.",
                  "gu": "GUJRERA માં નોંધાયેલ, {date} સુધી માન્ય.",
                  "hi": "GUJRERA में पंजीकृत, {date} तक मान्य।"},
    "reg_ending": {"en": "Registration ends on {date}, in {days} days.",
                   "gu": "નોંધણી {date} એ, {days} દિવસમાં પૂરી થાય છે.",
                   "hi": "पंजीकरण {date} को, {days} दिनों में समाप्त होता है।"},
    "reg_expired": {"en": "Registration expired on {date}.",
                    "gu": "નોંધણી {date} એ પૂરી થઈ ગઈ.",
                    "hi": "पंजीकरण {date} को समाप्त हो गया।"},
    "reg_revoked": {"en": "Registration has been revoked.",
                    "gu": "નોંધણી રદ કરવામાં આવી છે.",
                    "hi": "पंजीकरण रद्द कर दिया गया है।"},
    "completed": {"en": "Completed on {date}, on or before the promised date.", "gu": "{date} એ, વચન આપેલી તારીખ સુધીમાં પૂર્ણ થયો.",
                  "hi": "{date} को, वादा की गई तारीख तक पूरा हुआ।"},
    "completed_late": {"en": "Completed on {date}, {days} days after the promised date.",
                       "gu": "{date} એ પૂર્ણ થયો, વચન આપેલી તારીખથી {days} દિવસ મોડો.",
                       "hi": "{date} को पूरा हुआ, वादा की गई तारीख से {days} दिन बाद।"},
    "on_time": {"en": "On schedule: completion date {date}.",
                "gu": "સમયસર: પૂર્ણતા તારીખ {date}.",
                "hi": "समय पर: पूर्णता तारीख {date}।"},
    "extended": {"en": "Completion moved from {orig} to {date}, {days} days later than first promised.",
                 "gu": "પૂર્ણતા તારીખ {orig} થી {date} કરાઈ, પહેલા વચન કરતાં {days} દિવસ મોડી.",
                 "hi": "पूर्णता तारीख {orig} से {date} की गई, पहले वादे से {days} दिन बाद।"},
    "overdue": {"en": "The originally promised date ({orig}) passed {days} days ago and the project is not complete.",
                "gu": "મૂળ વચન આપેલી તારીખ ({orig}) {days} દિવસ પહેલાં વીતી ગઈ અને પ્રોજેક્ટ પૂરો થયો નથી.",
                "hi": "मूल वादा की गई तारीख ({orig}) {days} दिन पहले निकल चुकी है और प्रोजेक्ट पूरा नहीं हुआ।"},
    "progress": {"en": "{pct}% built at the last quarterly report ({quarter}).",
                 "gu": "છેલ્લા ત્રિમાસિક અહેવાલ ({quarter}) મુજબ {pct}% બાંધકામ.",
                 "hi": "पिछली तिमाही रिपोर्ट ({quarter}) के अनुसार {pct}% निर्माण।"},
    "qpr_ok": {"en": "Quarterly progress reports filed on time.",
               "gu": "ત્રિમાસિક પ્રગતિ અહેવાલ સમયસર ફાઈલ થયા.",
               "hi": "तिमाही प्रगति रिपोर्ट समय पर दाखिल हुईं।"},
    "qpr_missing": {"en": "Quarterly progress reports not filed: {n}.",
                    "gu": "{n} ત્રિમાસિક પ્રગતિ અહેવાલ ફાઈલ થયા નથી.",
                    "hi": "{n} तिमाही प्रगति रिपोर्ट दाखिल नहीं हुईं।"},
    "approvals_ok": {"en": "All {n} listed approvals granted.",
                     "gu": "યાદીમાંની તમામ {n} મંજૂરીઓ મળેલી છે.",
                     "hi": "सूची के सभी {n} अनुमोदन मिल चुके हैं।"},
    "approvals_pending": {"en": "Approvals not yet granted: {items}.",
                          "gu": "હજી ન મળેલી મંજૂરીઓ: {items}.",
                          "hi": "अभी न मिले अनुमोदन: {items}।"},
    "complaints_none": {"en": "No complaints on record for this project.",
                        "gu": "આ પ્રોજેક્ટ સામે કોઈ ફરિયાદ નોંધાયેલી નથી.",
                        "hi": "इस प्रोजेक्ट पर कोई शिकायत दर्ज नहीं है।"},
    "complaints": {"en": "Complaints on record: {total}; still open: {open}.",
                   "gu": "નોંધાયેલી ફરિયાદો: {total}; હજી ખુલ્લી: {open}.",
                   "hi": "दर्ज शिकायतें: {total}; अभी खुली: {open}।"},
    "promoter_record": {"en": "{promoter}: projects {projects}; behind their original date {delayed}; adverse orders {adverse}.",
                        "gu": "{promoter}: {projects} પ્રોજેક્ટ, {delayed} મૂળ તારીખથી પાછળ, {adverse} પ્રતિકૂળ આદેશ.",
                        "hi": "{promoter}: {projects} प्रोजेक्ट, {delayed} मूल तारीख से पीछे, {adverse} प्रतिकूल आदेश।"},
    # questions to ask
    "q_approval": {"en": "Ask for the {item} from {authority}: it is not yet granted in the registration.",
                   "gu": "{authority} ની {item} માંગો: નોંધણીમાં તે હજી મળેલી નથી.",
                   "hi": "{authority} से {item} माँगें: पंजीकरण में यह अभी नहीं मिला है।"},
    "q_qpr": {"en": "Ask why {n} quarterly progress report(s) were not filed (Section 11).",
              "gu": "{n} ત્રિમાસિક પ્રગતિ અહેવાલ કેમ ફાઈલ થયા નથી તે પૂછો (કલમ 11).",
              "hi": "{n} तिमाही प्रगति रिपोर्ट क्यों दाखिल नहीं हुईं, यह पूछें (धारा 11)।"},
    "q_delay": {"en": "Ask for the new possession date in writing in your agreement; for delay you are entitled to interest (Section 18).",
                "gu": "નવી પઝેશન તારીખ કરારમાં લેખિતમાં માંગો; વિલંબ માટે તમને વ્યાજનો હક છે (કલમ 18).",
                "hi": "नई पज़ेशन तारीख अनुबंध में लिखित में माँगें; देरी के लिए आपको ब्याज का हक है (धारा 18)।"},
    "q_reg": {"en": "Registration ends on {date}: ask whether an extension has been applied for (Section 6).",
              "gu": "નોંધણી {date} એ પૂરી થાય છે: મુદત વધારા માટે અરજી થઈ છે કે નહીં તે પૂછો (કલમ 6).",
              "hi": "पंजीकरण {date} को समाप्त होता है: पूछें कि विस्तार के लिए आवेदन हुआ है या नहीं (धारा 6)।"},
    "q_complaints": {"en": "{open} complaints are open on this project: ask the promoter what they are about.",
                     "gu": "આ પ્રોજેક્ટ સામે {open} ફરિયાદો ખુલ્લી છે: તે શેના વિશે છે તે પ્રમોટરને પૂછો.",
                     "hi": "इस प्रोजेक्ट पर {open} शिकायतें खुली हैं: प्रमोटर से पूछें कि वे किस बारे में हैं।"},
    "q_order": {"en": "Ask about {kind} {no} ({date}).",
                "gu": "{kind} {no} ({date}) વિશે પૂછો.",
                "hi": "{kind} {no} ({date}) के बारे में पूछें।"},
    "q_account": {"en": "Pay only into the project's designated bank account named in the agreement, never to a personal account.",
                  "gu": "ફક્ત કરારમાં લખેલા પ્રોજેક્ટના નિયત બેંક ખાતામાં જ ચૂકવો, ક્યારેય વ્યક્તિગત ખાતામાં નહીં.",
                  "hi": "केवल अनुबंध में लिखे प्रोजेक्ट के निर्धारित बैंक खाते में भुगतान करें, कभी निजी खाते में नहीं।"},
    "q_carpet": {"en": "Check that the agreement states the carpet area of your flat, not only super built-up area.",
                 "gu": "કરારમાં તમારા ફ્લેટનો કાર્પેટ એરિયા લખેલો છે તે તપાસો, ફક્ત સુપર બિલ્ટ-અપ નહીં.",
                 "hi": "जाँचें कि अनुबंध में आपके फ्लैट का कारपेट एरिया लिखा है, केवल सुपर बिल्ट-अप नहीं।"},
    # rights
    "r13": {"en": "No more than 10% of the price may be taken before a written agreement for sale is registered (Section 13).",
            "gu": "નોંધાયેલા લેખિત વેચાણ કરાર પહેલાં કિંમતના 10% થી વધુ લઈ શકાય નહીં (કલમ 13).",
            "hi": "पंजीकृत लिखित बिक्री अनुबंध से पहले कीमत का 10% से अधिक नहीं लिया जा सकता (धारा 13)।"},
    "r19": {"en": "You are entitled to see the sanctioned plans, layout and specifications approved by the authority (Section 19).",
            "gu": "સત્તાવાળાએ મંજૂર કરેલા પ્લાન, લેઆઉટ અને સ્પેસિફિકેશન જોવાનો તમને હક છે (કલમ 19).",
            "hi": "प्राधिकरण द्वारा स्वीकृत नक्शे, लेआउट और विनिर्देश देखने का आपको हक है (धारा 19)।"},
    "r14": {"en": "The sanctioned plans cannot be changed without your consent, and for common areas two-thirds of buyers must agree (Section 14).",
            "gu": "તમારી સંમતિ વગર મંજૂર પ્લાન બદલી શકાય નહીં, અને સામાન્ય વિસ્તાર માટે બે-તૃતીયાંશ ખરીદનારની સંમતિ જરૂરી છે (કલમ 14).",
            "hi": "आपकी सहमति के बिना स्वीकृत नक्शे नहीं बदले जा सकते, और साझा क्षेत्रों के लिए दो-तिहाई खरीदारों की सहमति ज़रूरी है (धारा 14)।"},
    "r14_3": {"en": "Structural defects reported within 5 years of possession must be fixed by the promoter free of charge within 30 days (Section 14(3)).",
              "gu": "પઝેશનના 5 વર્ષમાં જણાવેલી માળખાકીય ખામીઓ પ્રમોટરે 30 દિવસમાં મફત સુધારવી પડે (કલમ 14(3)).",
              "hi": "पज़ेशन के 5 साल में बताई गई संरचनात्मक खामियाँ प्रमोटर को 30 दिनों में मुफ़्त ठीक करनी होंगी (धारा 14(3))।"},
    "r18": {"en": "If possession is late you may stay and get interest for every month of delay, or withdraw and get a refund with interest (Section 18; rate under Rule 16).",
            "gu": "પઝેશન મોડું થાય તો ચાલુ રહીને દર મહિનાના વિલંબનું વ્યાજ મેળવી શકો, અથવા નીકળીને વ્યાજ સાથે રિફંડ (કલમ 18; દર નિયમ 16 મુજબ).",
            "hi": "पज़ेशन देर से हो तो बने रहकर हर महीने की देरी का ब्याज ले सकते हैं, या छोड़कर ब्याज सहित रिफंड (धारा 18; दर नियम 16 के अनुसार)।"},
}
ORDER_WORD = {
    "complaint_order": {"en": "complaint order", "gu": "ફરિયાદ આદેશ", "hi": "शिकायत आदेश"},
    "extension_order": {"en": "extension order", "gu": "મુદત વધારાનો આદેશ", "hi": "विस्तार आदेश"},
    "penalty_order": {"en": "penalty order", "gu": "દંડ આદેશ", "hi": "जुर्माना आदेश"},
    "revocation_order": {"en": "revocation order", "gu": "નોંધણી રદ કરવાનો આદેશ", "hi": "पंजीकरण रद्द करने का आदेश"},
    "show_cause": {"en": "show-cause notice", "gu": "કારણદર્શક નોટિસ", "hi": "कारण बताओ नोटिस"},
}
ADVERSE = ("penalty_order", "revocation_order", "show_cause")


def _t(key: str, lang: str, **v: Any) -> str:
    return T[key].get(lang, T[key]["en"]).format(**v)


def _d(v: Any) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _act(section: str) -> dict[str, Any]:
    return {"type": "legal_act", "id": f"RERA Act, 2016, Section {section}", "is_mock": False}


def build_report(repo: Repository, project_id: int, lang: str = "en", *, as_of: date | None = None) -> dict[str, Any] | None:
    today = as_of or date.today()
    p = repo.get_project_by_id(project_id)
    if p is None:
        return None
    rec = p["source"]
    mock = bool(p.get("is_mock"))
    approvals = repo.project_approvals(project_id)
    progress = repo.project_progress(project_id)
    orders = repo.list_orders(project_id=project_id)
    complaints = repo.complaint_counts(project_id=project_id)
    # Public records do not name every promoter; the placeholder groups thousands of unrelated
    # projects, so it has no track record to report.
    known = p.get("promoter_name") != "Promoter not in imported records"
    card = (repo.promoter_scorecard(p["promoter_id"]) or {}) if known else {}
    siblings = [x for x in repo.promoter_projects(p["promoter_id"]) if x["id"] != project_id] if known else []
    promoter_orders = ([o for o in repo.list_orders(promoter_id=p["promoter_id"]) if o["order_type"] in ADVERSE]
                       if known else [])

    valid_until, proposed = _d(p["reg_valid_until"]), _d(p["proposed_completion"])
    revised, actual = _d(p.get("revised_completion")), _d(p.get("actual_completion"))
    target = revised or proposed
    glance: list[dict[str, Any]] = []

    def add(key: str, tone: str, cites: list[dict[str, Any]], **v: Any) -> None:
        glance.append({"key": key, "tone": tone, "text": _t(key, lang, **v), "citations": cites})

    # registration
    if p["status"] == "revoked":
        add("reg_revoked", BAD, [rec, *[o["source"] for o in orders if o["order_type"] == "revocation_order"]])
    elif valid_until < today and p["status"] != "completed":
        add("reg_expired", BAD, [rec], date=fmt_date(valid_until, lang))
    elif p["status"] != "completed" and valid_until <= today + timedelta(days=180):
        add("reg_ending", WARN, [rec], date=fmt_date(valid_until, lang), days=(valid_until - today).days)
    elif p["status"] != "completed":
        add("reg_valid", GOOD, [rec], date=fmt_date(valid_until, lang))

    # schedule
    if p["status"] == "completed" and actual:
        late = (actual - proposed).days
        if late > 0:
            add("completed_late", WARN, [rec], date=fmt_date(actual, lang), days=late)
        else:
            add("completed", GOOD, [rec], date=fmt_date(actual, lang))
    elif p["status"] == "ongoing":
        moved = (target - proposed).days
        overdue = (today - proposed).days
        if moved > 0:
            add("extended", BAD if moved > 365 else WARN,
                [rec, *[o["source"] for o in orders if o["order_type"] == "extension_order"][:2]],
                orig=fmt_date(proposed, lang), date=fmt_date(target, lang), days=moved)
        if overdue > 0:
            add("overdue", BAD if overdue > 180 else WARN, [rec], orig=fmt_date(proposed, lang), days=overdue)
        if moved <= 0 and overdue <= 0:
            add("on_time", GOOD, [rec], date=fmt_date(target, lang))

    # progress reports
    filed = [r for r in progress if r.get("filed_on")]
    missing = [r for r in progress if not r.get("filed_on") and _d(r["due_on"]) < today]
    if filed and p["status"] == "ongoing":
        last = filed[-1]
        add("progress", GOOD, [last["source"]], pct=round(last["percent_complete"], 1), quarter=last["quarter"])
    if progress and p["status"] == "ongoing":
        if missing:
            add("qpr_missing", BAD if len(missing) >= 2 else WARN, [r["source"] for r in missing[:4]], n=len(missing))
        else:
            add("qpr_ok", GOOD, [filed[-1]["source"]] if filed else [rec])

    # approvals
    pending = [a for a in approvals if a["status"] != "granted"]
    if pending:
        items = ", ".join(f"{word(a['kind'], lang)} ({a['authority']})" for a in pending)
        add("approvals_pending", WARN, [a["source"] for a in pending], items=items)
    elif approvals:
        add("approvals_ok", GOOD, [a["source"] for a in approvals], n=len(approvals))

    # complaints (counts only)
    if complaints["total"] == 0:
        add("complaints_none", GOOD, [complaints["source"]])
    else:
        add("complaints", BAD if complaints["open"] >= 3 else WARN if complaints["open"] else GOOD,
            [complaints["source"]], total=complaints["total"], open=complaints["open"])

    # promoter
    if card:
        name = p["promoter_name"].replace(" (Demo)", "").replace(" (ડેમો)", "")
        add("promoter_record", BAD if card.get("adverse_orders") else WARN if card.get("delayed_projects") else GOOD,
            [card["source"]], promoter=name, projects=card.get("projects", 0), delayed=card.get("delayed_projects", 0),
            adverse=card.get("adverse_orders", 0))

    # questions to ask the promoter
    questions: list[dict[str, Any]] = []

    def ask(key: str, cites: list[dict[str, Any]], **v: Any) -> None:
        questions.append({"key": key, "text": _t(key, lang, **v), "citations": cites})

    for a in pending:
        ask("q_approval", [a["source"]], item=word(a["kind"], lang), authority=a["authority"])
    if missing and p["status"] == "ongoing":
        ask("q_qpr", [r["source"] for r in missing[:4]] + [_act("11")], n=len(missing))
    if p["status"] == "ongoing" and (target > proposed or today > proposed):
        ask("q_delay", [rec, _act("18")])
    if p["status"] == "ongoing" and valid_until <= today + timedelta(days=180):
        ask("q_reg", [rec, _act("6")], date=fmt_date(valid_until, lang))
    if complaints["open"]:
        ask("q_complaints", [complaints["source"]], open=complaints["open"])
    for o in [o for o in orders if o["order_type"] in ADVERSE][:2] + promoter_orders[:2]:
        ask("q_order", [o["source"]], kind=ORDER_WORD.get(o["order_type"], {}).get(lang, o["order_type"]),
            no=o["order_no"], date=fmt_date(_d(o["issued_on"]), lang))
    ask("q_account", [_act("4")])
    ask("q_carpet", [_act("13")])

    rights = [{"key": k, "text": _t(k, lang), "citations": [_act(s)]}
              for k, s in (("r13", "13"), ("r19", "19"), ("r14", "14"), ("r14_3", "14"), ("r18", "18"))]

    from gujrera.orders import orders_for

    compliance = {x["order_no"]: {"state": x["state"], "due_on": x["due_on"], "text": " ".join(t["text"] for t in x["sentences"][1:2])}
                  for x in orders_for(repo, project_id=project_id, lang=lang, as_of=today) if x["state"]}
    worst = BAD if any(g["tone"] == BAD for g in glance) else WARN if any(g["tone"] == WARN for g in glance) else GOOD
    repo._audit("project_report", {"project_id": project_id})
    return {
        "generated_on": today.isoformat(),
        "lang": lang,
        "overall": worst,
        "project": {
            "id": p["id"], "name": p["name"], "name_gu": p.get("name_gu"), "rera_no": p["rera_no"],
            "district": p["district"], "taluka": p.get("taluka"), "type": word(p["project_type"], lang),
            "units": p.get("units"), "status": p["status"], "status_text": word(p["status"], lang),
            "promoter": p["promoter_name"], "reg_date": str(p["reg_date"]), "reg_valid_until": str(valid_until),
            "proposed_completion": str(proposed), "revised_completion": str(revised) if revised else None,
            "actual_completion": str(actual) if actual else None, "delay_days": p.get("delay_days", 0),
            "source_url": p.get("source_url"),
        },
        "glance": glance,
        "progress": [{"quarter": r["quarter"], "percent": r["percent_complete"], "due_on": str(r["due_on"]),
                      "filed_on": str(r["filed_on"]) if r.get("filed_on") else None,
                      "state": "missing" if (not r.get("filed_on") and _d(r["due_on"]) < today)
                      else "due" if not r.get("filed_on") else "late" if _d(r["filed_on"]) > _d(r["due_on"]) else "on_time"}
                     for r in progress],
        "approvals": [{"kind": word(a["kind"], lang), "authority": a["authority"], "status": a["status"],
                       "ref": a.get("ref"), "decided_on": str(a["decided_on"]) if a.get("decided_on") else None}
                      for a in approvals],
        "complaints": {"total": complaints["total"], "open": complaints["open"], "by_category": complaints["by_category"]},
        "orders": [{"order_no": o["order_no"], "type": ORDER_WORD.get(o["order_type"], {}).get(lang, o["order_type"]),
                    "issued_on": str(o["issued_on"]), "summary": o["summary"],
                    "compliance": compliance.get(o["order_no"])} for o in orders],
        "promoter": {"name": p["promoter_name"], "projects": card.get("projects"), "delayed": card.get("delayed_projects"),
                     "complaints_total": card.get("complaints_total"), "complaints_open": card.get("complaints_open"),
                     "adverse_orders": card.get("adverse_orders"),
                     "other_projects": [{"id": x["id"], "name": x["name"], "district": x["district"], "status": x["status"],
                                         "delay_days": x.get("delay_days", 0)} for x in siblings[:12]]},
        "questions": questions,
        "rights": rights,
        "is_mock": mock,
    }
