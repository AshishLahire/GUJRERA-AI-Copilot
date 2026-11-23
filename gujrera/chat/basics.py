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
