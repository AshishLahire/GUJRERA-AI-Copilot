"""Template-generated gold questions for the chat (100 per language by default).

The Stage 1 deck promises 300 gold questions, 100 per language. These are
generated from registry records so the correct answer is known exactly. They
test routing, entity matching, facts and citations; they are NOT a substitute
for questions written by real buyers, promoters and officers, which should be
collected during the pilot and added to this set.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from gujrera.db.models import Project, Promoter
from gujrera.db.repository import Principal, Repository
from gujrera.i18n import fmt_date, t

FAKE_NAMES = {
    "en": ["Xyzzy Towers", "Quasar Heights", "Blue Lagoon Residency", "Zenith Plaza", "Moonlit Greens"],
    "gu": ["ઝાયલો ટાવર્સ", "ક્વાસર હાઇટ્સ", "બ્લૂ લગૂન રેસિડેન્સી", "ઝેનિથ ટાવર્સ", "મૂનલિટ રેસિડેન્સી"],
    "hi": ["ज़ायलो टावर्स", "क्वासर टावर्स", "ब्लू लैगून रेजिडेंसी", "ज़ेनिथ टावर्स", "मूनलिट रेजिडेंसी"],
}
OUT_OF_SCOPE = {
    "en": ["what is the weather today", "who won the cricket match yesterday", "tell me a joke",
           "how do i cook dal", "what is the price of gold"],
    "gu": ["આજે હવામાન કેવું છે?", "ગઈકાલે ક્રિકેટ મેચ કોણ જીત્યું?", "મને એક જોક કહો",
           "દાળ કેવી રીતે બનાવવી?", "સોનાનો ભાવ શું છે?"],
    "hi": ["आज मौसम कैसा है?", "कल क्रिकेट मैच कौन जीता?", "मुझे एक चुटकुला सुनाओ",
           "दाल कैसे बनाते हैं?", "सोने का भाव क्या है?"],
}
Q = {
    "possession": {
        "en": ["When will I get possession of {p}?", "{p} possession date?", "When is {p} getting completed?"],
        "gu": ["{p} નું પઝેશન ક્યારે મળશે?", "{p} ક્યારે પૂર્ણ થશે?", "{p} પઝેશન તારીખ શું છે?"],
        "hi": ["{p} का पज़ेशन कब मिलेगा?", "{p} कब पूरा होगा?", "{p} की पज़ेशन तारीख क्या है?"],
    },
    "promoter": {
        "en": ["Tell me about the builder {b}", "What is the track record of {b}?"],
        "gu": ["બિલ્ડર {b} વિશે જણાવો", "{b} બિલ્ડર કેવા છે?"],
        "hi": ["बिल्डर {b} के बारे में बताइए", "{b} बिल्डर का रिकॉर्ड कैसा है?"],
    },
    "project": {
        "en": ["Tell me about {p}", "Details of {p}"],
        "gu": ["{p} વિશે જણાવો", "{p} ની માહિતી આપો"],
        "hi": ["{p} के बारे में बताइए", "{p} की जानकारी दीजिए"],
    },
    "complaints": {
        "en": ["How many complaints against {p}?", "Any complaints on {p}?"],
        "gu": ["{p} સામે કેટલી ફરિયાદો છે?", "{p} ની ફરિયાદો?"],
        "hi": ["{p} के खिलाफ कितनी शिकायतें हैं?", "{p} की शिकायतें?"],
    },
}
COUNTS = {"possession": 30, "promoter": 20, "project": 20, "complaints": 15, "not_found": 10, "out_of_scope": 5}


@dataclass
class GoldQuestion:
    id: str
    lang: str
    kind: str
    question: str
    expect_intent: tuple[str, ...]
    must_contain: list[str] = field(default_factory=list)


def _pname(p: Project | Promoter, lang: str) -> str:
    name = (p.name_gu if lang == "gu" and p.name_gu else p.name)
    return name.replace(" (Demo)", "").replace(" (ડેમો)", "")


def build_gold(session: Session, seed: int = 300) -> list[GoldQuestion]:
    rng = random.Random(seed)
    repo = Repository(session, Principal.anonymous())
    projects = session.scalars(select(Project).order_by(Project.id)).all()
    promoters = session.scalars(select(Promoter).order_by(Promoter.id)).all()
    out: list[GoldQuestion] = []
    for lang in ("gu", "hi", "en"):
        n = 0

        def add(kind: str, question: str, intents: tuple[str, ...], must: list[str]) -> None:
            nonlocal n
            n += 1
            out.append(GoldQuestion(f"{lang}-{kind}-{n:03d}", lang, kind, question, intents, must))

        for p in rng.sample(projects, COUNTS["possession"]):
            date_ = p.actual_completion or p.reg_valid_until
            add("possession", rng.choice(Q["possession"][lang]).format(p=_pname(p, lang)), ("possession",),
                [fmt_date(date_, lang)])
        for b in rng.sample(promoters, COUNTS["promoter"]):
            n_projects = sum(1 for p in projects if p.promoter_id == b.id)
            add("promoter", rng.choice(Q["promoter"][lang]).format(b=_pname(b, lang)), ("promoter_profile",),
                [str(n_projects)])
        for p in rng.sample(projects, COUNTS["project"]):
            add("project", rng.choice(Q["project"][lang]).format(p=_pname(p, lang)), ("project_profile",),
                [p.rera_no])
        for p in rng.sample(projects, COUNTS["complaints"]):
            total = repo.complaint_counts(project_id=p.id)["total"]
            add("complaints", rng.choice(Q["complaints"][lang]).format(p=_pname(p, lang)), ("complaints",),
                [str(total)] if total else [t("no_complaints", lang)])
        for i in range(COUNTS["not_found"]):
            fake = FAKE_NAMES[lang][i % len(FAKE_NAMES[lang])]
            template = rng.choice(Q["possession"][lang] + Q["project"][lang])
            # A suggestion ("did you mean …?") is also correct: it is offered, never answered automatically.
            add("not_found", template.format(p=fake), ("not_found", "did_you_mean"), [])
        for q in OUT_OF_SCOPE[lang][: COUNTS["out_of_scope"]]:
            add("out_of_scope", q, ("out_of_scope",), [])
    return out
