"""Small, common questions the chat should answer well: what RERA is, thanks, projects in a district,
and matching project names typed in Hindi (Devanagari) script."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select

from gujrera.chat.understand import gu_to_deva  # noqa: F401 - re-exported for callers
from gujrera.db.models import Project
from gujrera.db.repository import Repository
from gujrera.profile.summarise import Sentence


def _act(sec: str) -> dict[str, Any]:
    return {"type": "legal_act", "id": f"RERA Act, 2016, Section {sec}", "is_mock": False}


ABOUT = [
    ({"en": "RERA is the Real Estate (Regulation and Development) Act, 2016.",
      "gu": "RERA એટલે રિયલ એસ્ટેટ (નિયમન અને વિકાસ) અધિનિયમ, 2016.",
      "hi": "RERA यानी रियल एस्टेट (विनियमन और विकास) अधिनियम, 2016।"}, "1"),
    ({"en": "A project must be registered with the Real Estate Regulatory Authority before it is advertised or sold.",
      "gu": "પ્રોજેક્ટની જાહેરાત કે વેચાણ પહેલાં તેની રિયલ એસ્ટેટ નિયમનકારી સત્તામંડળમાં નોંધણી જરૂરી છે.",
      "hi": "किसी प्रोजेक्ट का विज्ञापन या बिक्री से पहले रियल एस्टेट नियामक प्राधिकरण में पंजीकरण ज़रूरी है।"}, "3"),
    ({"en": "Buyers have rights to the project's information and to possession on time, with interest or a refund if it is late.",
      "gu": "ખરીદનારને પ્રોજેક્ટની માહિતી અને સમયસર પઝેશનનો હક છે; મોડું થાય તો વ્યાજ કે રિફંડ મળે.",
      "hi": "खरीदारों को प्रोजेक्ट की जानकारी और समय पर पज़ेशन का हक है; देर हो तो ब्याज या रिफंड मिलता है।"}, "18"),
    ({"en": "GUJRERA is Gujarat's Real Estate Regulatory Authority, set up under the Act; anyone aggrieved can complain to it.",
      "gu": "GUJRERA એ કાયદા હેઠળ સ્થપાયેલું ગુજરાતનું રિયલ એસ્ટેટ નિયમનકારી સત્તામંડળ છે; કોઈ પણ પીડિત વ્યક્તિ તેમાં ફરિયાદ કરી શકે.",
      "hi": "GUJRERA अधिनियम के तहत बना गुजरात का रियल एस्टेट नियामक प्राधिकरण है; कोई भी पीड़ित व्यक्ति इसमें शिकायत कर सकता है।"}, "20"),
]
_ABOUT_RX = re.compile(r"(what\s+is\s+(the\s+)?(guj)?rera|(guj)?rera\s+(kya|shu|shun)\s+(hai|che|chhe)|"
                       r"(ગુજ)?રેરા\s*શું|RERA\s*શું|(गुज)?रेरा\s*क्या|RERA\s*क्या)", re.IGNORECASE)
_THANKS_RX = re.compile(r"\b(thank(s| you)|dhanyavaad|dhanyavad|shukriya|aabhar|abhar)\b|આભાર|धन्यवाद|शुक्रिया", re.IGNORECASE)
THANKS = {"en": "You're welcome. Ask me anything else about a project, a builder or your rights.",
          "gu": "આપનો આભાર. કોઈ પ્રોજેક્ટ, બિલ્ડર કે તમારા અધિકારો વિશે બીજું કંઈ પણ પૂછો.",
          "hi": "आपका स्वागत है। किसी प्रोजेक्ट, बिल्डर या अपने अधिकारों के बारे में और कुछ भी पूछें।"}


def asks_about_rera(text: str) -> bool:
    return bool(_ABOUT_RX.search(text or ""))


def says_thanks(text: str) -> bool:
    return bool(_THANKS_RX.search(text or "")) and len((text or "").split()) <= 6


def about_rera(lang: str) -> list[Sentence]:
    return [Sentence(t.get(lang, t["en"]), [_act(sec)] + ([_act("19")] if sec == "18" else [_act("31")] if sec == "20" else []),
                     f"about_rera_{sec}") for t, sec in ABOUT]


def thanks(lang: str) -> list[Sentence]:
    return [Sentence(THANKS.get(lang, THANKS["en"]), [], "thanks")]


_PROJECT_WORDS = ("project", "projects", "પ્રોજેક્ટ", "प्रोजेक्ट", "scheme", "society", "flats in", "flat in")
LIST = {
    "head": {"en": "{district}: {total} registered {projects} ({ongoing} ongoing, {completed} completed{other}).",
             "gu": "{district}: {total} નોંધાયેલા પ્રોજેક્ટ ({ongoing} ચાલુ, {completed} પૂર્ણ{other}).",
             "hi": "{district}: {total} पंजीकृत प्रोजेक्ट ({ongoing} चालू, {completed} पूरे{other})।"},
    "other": {"en": ", {n} lapsed or revoked", "gu": ", {n} રદ કે મુદત પૂરી", "hi": ", {n} समाप्त या रद्द"},
    "unverified": {"en": ", {n} past their completion date with completion not recorded in our data",
                   "gu": ", {n} પૂર્ણ થવાની તારીખ વીતી ગઈ પણ પૂર્ણતા અમારા ડેટામાં નોંધાયેલ નથી",
                   "hi": ", {n} समापन तिथि बीत चुकी पर पूरा होना हमारे डेटा में दर्ज नहीं"},
    "delayed": {"en": "Ongoing projects past their originally promised date: {n}, including {names}.",
                "gu": "મૂળ વચન આપેલી તારીખ વીતી ગઈ હોય તેવા ચાલુ પ્રોજેક્ટ: {n}, જેમાં {names}.",
                "hi": "मूल वादा की गई तारीख पार कर चुके चालू प्रोजेक्ट: {n}, जिनमें {names}।"},
    "some": {"en": "Ongoing projects include: {names}.", "gu": "ચાલુ પ્રોજેક્ટમાં સામેલ છે: {names}.",
             "hi": "चालू प्रोजेक्ट में शामिल हैं: {names}।"},
    "tip": {"en": "Ask about any of them by name, or open its before-you-buy report.",
            "gu": "કોઈ પણ વિશે નામથી પૂછો, અથવા તેનો ખરીદી પહેલાંનો રિપોર્ટ ખોલો.",
            "hi": "किसी के बारे में नाम से पूछें, या उसकी खरीद से पहले रिपोर्ट खोलें।"},
}


# Rankings across promoters ("which builders have the most…") are officer reports, not a district listing.
_RANKING_WORDS = ("promoter", "builder", "developer", "most ", "top ", "highest", "worst", "rank",
                  "પ્રમોટર", "બિલ્ડર", "સૌથી", "प्रमोटर", "बिल्डर", "सबसे")


def wants_district_list(text_lc: str) -> bool:
    return any(w in text_lc for w in _PROJECT_WORDS) and not any(w in text_lc for w in _RANKING_WORDS)


DELAY_WORDS = ("delay", "late", "behind", "વિલંબ", "મોડા", "મોડું", "देरी", "देर से", "विलंब")


def district_list(repo: Repository, district: str, lang: str, limit: int = 8, *, delayed: bool = False
                  ) -> tuple[list[Sentence], dict[str, Any]]:
    from datetime import date

    s = repo.s
    counts = dict(s.execute(select(Project.status, func.count()).where(Project.district == district)
                            .group_by(Project.status)).all())
    stmt = select(Project).where(Project.district == district, Project.status == "ongoing")
    if delayed:  # promised date passed, or completion moved later
        stmt = stmt.where((Project.proposed_completion < date.today()) | (Project.revised_completion > Project.proposed_completion))
    n_delayed = s.scalar(select(func.count()).select_from(stmt.subquery())) if delayed else 0
    ongoing = s.scalars(stmt.order_by(Project.name).limit(limit)).all()

    def t(key: str, **v: Any) -> str:
        return LIST[key].get(lang, LIST[key]["en"]).format(**v)

    other = sum(n for st, n in counts.items() if st not in ("ongoing", "completed", "unverified"))
    unverified = counts.get("unverified", 0)
    names = ", ".join((p.name_gu if lang == "gu" and p.name_gu else p.name).replace(" (Demo)", "") for p in ongoing)
    stat = {"type": "district_stats", "id": district, "is_mock": True}
    total = sum(counts.values())
    out = [Sentence(t("head", district=district, total=total, projects="project" if total == 1 else "projects",
                      ongoing=counts.get("ongoing", 0),
                      completed=counts.get("completed", 0),
                      other=(t("other", n=other) if other else "") + (t("unverified", n=unverified) if unverified else "")),
                    [stat], "district_head")]
    if ongoing:
        out.append(Sentence(t("delayed", n=n_delayed, names=names) if delayed else t("some", names=names), [{"type": "project", "id": p_.rera_no, "is_mock": bool(p_.is_mock)}
                                                    for p_ in ongoing[:3]], "district_some"))
        out.append(Sentence(t("tip"), [], "district_tip"))
    repo._audit("district_list", {"district": district})
    return out, {"type": "district", "district": district,
                 "projects": [{"id": p.id, "name": p.name, "rera_no": p.rera_no} for p in ongoing]}


# ------------------------------------------------------------------ localities, agents, follow-ups on a list
LOCAL = {
    "head": {"en": "{place}: {n} RERA-registered {projects}.",
             "gu": "{place}: {n} RERA નોંધાયેલા પ્રોજેક્ટ.",
             "hi": "{place}: {n} RERA पंजीकृत प्रोजेक्ट।"},
    "item": {"en": "{name}, {rera}, by {promoter} ({status}).",
             "gu": "{name}, {rera}, {promoter} દ્વારા ({status}).",
             "hi": "{name}, {rera}, {promoter} द्वारा ({status})।"},
    "item_np": {"en": "{name}, {rera} ({status}).", "gu": "{name}, {rera} ({status}).", "hi": "{name}, {rera} ({status})।"},
    "more": {"en": "Showing {shown} of {n}; ask for a narrower list, e.g. only ongoing ones.",
             "gu": "{n} માંથી {shown} બતાવ્યા; ટૂંકી યાદી માટે પૂછો, દા.ત. ફક્ત ચાલુ પ્રોજેક્ટ.",
             "hi": "{n} में से {shown} दिखाए; छोटी सूची के लिए पूछें, जैसे केवल चालू प्रोजेक्ट।"},
    "none": {"en": "No RERA-registered projects found in {place} in the records available to me.",
             "gu": "મારી પાસેના રેકોર્ડમાં {place} માં કોઈ RERA નોંધાયેલ પ્રોજેક્ટ મળ્યો નથી.",
             "hi": "मेरे पास के रिकॉर्ड में {place} में कोई RERA पंजीकृत प्रोजेक्ट नहीं मिला।"},
    "agents_head": {"en": "{district}: {n} registered real estate agents ({active} with active registration).",
                    "gu": "{district}: {n} નોંધાયેલા રિયલ એસ્ટેટ એજન્ટ ({active} ની નોંધણી સક્રિય).",
                    "hi": "{district}: {n} पंजीकृत रियल एस्टेट एजेंट ({active} का पंजीकरण सक्रिय)।"},
    "agent_item": {"en": "{name}, {reg}, valid until {valid} ({status}).",
                   "gu": "{name}, {reg}, {valid} સુધી માન્ય ({status}).",
                   "hi": "{name}, {reg}, {valid} तक मान्य ({status})।"},
    "filtered": {"en": "Of the previous list, {n} match.", "gu": "આગળની યાદીમાંથી {n} મેળ ખાય છે.",
                 "hi": "पिछली सूची में से {n} मेल खाते हैं।"},
    "need_list": {"en": "There is no list to narrow down yet. Ask for one first, for example: "
                         "\"Which RERA-approved projects are in Gandhinagar?\" Then ask \"which of these are ongoing?\"",
                  "gu": "હજી કોઈ યાદી નથી જેમાંથી પસંદ કરી શકાય. પહેલાં યાદી માંગો, દા.ત. \"ગાંધીનગરમાં કયા "
                        "પ્રોજેક્ટ છે?\" પછી પૂછો \"આમાંથી કયા ચાલુ છે?\"",
                  "hi": "अभी कोई सूची नहीं है जिसमें से छाँटा जा सके। पहले सूची माँगें, जैसे \"गांधीनगर में कौन से "
                        "प्रोजेक्ट हैं?\" फिर पूछें \"इनमें से कौन से चालू हैं?\""},
    "filtered_none": {"en": "None of the previous list match that.", "gu": "આગળની યાદીમાંથી કોઈ મેળ ખાતું નથી.",
                      "hi": "पिछली सूची में से कोई मेल नहीं खाता।"},
}
AGENT_WORDS = ("agent", "agents", "broker", "brokers", "એજન્ટ", "દલાલ", "एजेंट", "दलाल")
_FOLLOWUP = re.compile(r"\b(of these|of them|these|those|among them)\b|આમાંથી|આમાં|એમાંથી|તેમાંથી|इनमें|इनमे|उनमें",
                       re.IGNORECASE)
_LIST_WORDS = _PROJECT_WORDS + ("developer", "developers", "builder", "builders", "ડેવલપર", "બિલ્ડર", "डेवलपर",
                                "बिल्डर", "rera approved", "rera-approved", "માન્ય", "मान्य")


def wants_locality_list(text_lc: str) -> bool:
    return any(w in text_lc for w in _LIST_WORDS)


def wants_agent_list(text_lc: str) -> bool:
    return any(w in text_lc for w in AGENT_WORDS)


_DEMO_TAG = re.compile(r"\s*\((?:demo|ડેમો|डेमो)\)", re.IGNORECASE)


def _clean(name: str | None) -> str:
    return _DEMO_TAG.sub("", name or "").strip()


def _place(locality: str, lang: str) -> str:
    """The locality in the answer's language (from the fixed list), else as stored."""
    from gujrera.authority_seed import LOCALITIES

    for names in LOCALITIES.values():
        for en, gu, hi in names:
            if en == locality:
                return {"gu": gu, "hi": hi}.get(lang, en)
    return locality


def _lt(key: str, lang: str, **v: Any) -> str:
    return LOCAL[key].get(lang, LOCAL[key]["en"]).format(**v)


def _project_lines(repo: Repository, projects: list[Project], lang: str, limit: int) -> list[Sentence]:
    from gujrera.db.models import Promoter
    from gujrera.i18n import word

    out = []
    for p in projects[:limit]:
        promoter = repo.s.get(Promoter, p.promoter_id)
        src = {"type": "project", "id": p.rera_no, "is_mock": bool(p.is_mock)}
        name = _clean(p.name_gu if lang == "gu" and p.name_gu else p.name)
        status = word(p.status, lang)
        if promoter.promoter_type == "unknown":
            out.append(Sentence(_lt("item_np", lang, name=name, rera=p.rera_no, status=status), [src], "locality_item"))
        else:
            pname = _clean(promoter.name_gu if lang == "gu" and promoter.name_gu else promoter.name)
            out.append(Sentence(_lt("item", lang, name=name, rera=p.rera_no, promoter=pname, status=status),
                                [src], "locality_item"))
    return out


def locality_list(repo: Repository, locality: str, lang: str, limit: int = 10
                  ) -> tuple[list[Sentence], dict[str, Any], list[int]]:
    """Registered projects in a locality, as on the public registry (citizen-safe columns only)."""
    projects = repo.s.scalars(select(Project).where(Project.locality == locality)
                              .order_by(Project.status != "ongoing", Project.name)).all()
    repo._audit("locality_list", {"locality": locality, "n": len(projects)})
    card: dict[str, Any] = {"type": "locality", "locality": locality,
                            "projects": [{"id": p.id, "name": p.name, "rera_no": p.rera_no, "status": p.status}
                                         for p in projects]}
    if not projects:
        return [Sentence(_lt("none", lang, place=_place(locality, lang)), [], "locality_none")], card, []
    stat = {"type": "locality", "id": locality, "is_mock": any(p.is_mock for p in projects)}
    out = [Sentence(_lt("head", lang, place=_place(locality, lang), n=len(projects),
                        projects="project" if len(projects) == 1 else "projects"), [stat], "locality_head")]
    out += _project_lines(repo, list(projects), lang, limit)
    if len(projects) > limit:
        out.append(Sentence(_lt("more", lang, shown=limit, n=len(projects)), [], "locality_more"))
    return out, card, [p.id for p in projects]


def agent_list(repo: Repository, district: str, lang: str, limit: int = 10) -> tuple[list[Sentence], dict[str, Any]]:
    """Registered agents in a district: name, registration number, validity (public fields only)."""
    from datetime import date

    from gujrera.db.models import Agent
    from gujrera.i18n import fmt_date

    agents = repo.s.scalars(select(Agent).where(Agent.district == district)
                            .order_by(Agent.status != "active", Agent.name)).all()
    repo._audit("agent_list", {"district": district, "n": len(agents)})
    today = date.today()
    active = sum(a.status == "active" and a.valid_until >= today for a in agents)
    label = {"active": {"en": "active", "gu": "સક્રિય", "hi": "सक्रिय"},
             "expired": {"en": "expired", "gu": "મુદત પૂરી", "hi": "समाप्त"},
             "revoked": {"en": "revoked", "gu": "રદ", "hi": "रद्द"}}
    stat = {"type": "agent_registry", "id": district, "is_mock": any(a.is_mock for a in agents)}
    from gujrera.i18n import word

    out = [Sentence(_lt("agents_head", lang, district=word(district, lang), n=len(agents), active=active), [stat],
                    "agents_head")]
    for a in agents[:limit]:
        st = a.status if a.valid_until >= today or a.status != "active" else "expired"
        name = _clean(a.name_gu if lang == "gu" and a.name_gu else a.name)
        out.append(Sentence(_lt("agent_item", lang, name=name, reg=a.reg_no, valid=fmt_date(a.valid_until, lang),
                                status=label[st].get(lang, label[st]["en"])),
                            [{"type": "agent", "id": a.reg_no, "is_mock": bool(a.is_mock)}], "agent_item"))
    if len(agents) > limit:
        out.append(Sentence(_lt("more", lang, shown=limit, n=len(agents)), [], "agents_more"))
    return out, {"type": "agents", "district": district,
                 "agents": [{"name": a.name, "reg_no": a.reg_no, "status": a.status} for a in agents]}


def need_list(lang: str) -> list[Sentence]:
    return [Sentence(_lt("need_list", lang), [], "need_list")]


def is_followup(text: str) -> bool:
    return bool(_FOLLOWUP.search(text or ""))


def filter_list(repo: Repository, ids: list[int], text: str, lang: str, limit: int = 10
                ) -> tuple[list[Sentence], list[int]] | None:
    """Narrow the previous project list: registered after/before/in a year, ongoing or completed, a locality.
    None if the follow-up asks for nothing this can filter on."""
    from datetime import date

    from gujrera.analytics.reports import find_locality

    t = (text or "").lower()
    conds = []
    m = re.search(r"(?:after|since)\s+(20\d{2})|(20\d{2})\s*(?:પછી|થી|के बाद|से)", t)
    if m:
        y = int(m.group(1) or m.group(2))
        after = any(w in m.group(0) for w in ("after", "પછી", "के बाद"))
        conds.append(Project.reg_date >= date(y + 1 if after else y, 1, 1))
    m = re.search(r"before\s+(20\d{2})|(20\d{2})\s*(?:પહેલાં|પહેલા|से पहले)", t)
    if m:
        conds.append(Project.reg_date < date(int(m.group(1) or m.group(2)), 1, 1))
    if any(w in t for w in ("ongoing", "ચાલુ", "चालू", "under construction")):
        conds.append(Project.status == "ongoing")
    if any(w in t for w in ("completed", "પૂર્ણ થયેલ", "પૂર્ણ થયા", "पूरे हो")):
        conds.append(Project.status == "completed")
    loc = find_locality(t)
    if loc:
        conds.append(Project.locality == loc)
    if not conds:
        return None
    projects = repo.s.scalars(select(Project).where(Project.id.in_(ids), *conds).order_by(Project.name)).all()
    if not projects:
        return [Sentence(_lt("filtered_none", lang), [], "filter_none")], []
    head = Sentence(_lt("filtered", lang, n=len(projects)), [], "filter_head")
    return [head, *_project_lines(repo, list(projects), lang, limit)], [p.id for p in projects]
