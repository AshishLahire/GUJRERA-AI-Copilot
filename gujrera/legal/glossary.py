"""Gujarati/Hindi RERA vocabulary → English legal terms, for searching English legal text.

A small, reviewed glossary is more reliable for Gujarati than a 7B model's translation
(which mistranslated "પઝેશનમાં મોડું" as "modifies the plan" in testing). Matching terms
are appended to the query; the original words stay in it too. Words like "rule", "section"
or "law" are left out on purpose: they pull the search toward rule-making provisions.
"""

from __future__ import annotations

GLOSSARY: dict[str, str] = {
    # Gujarati
    "પઝેશન": "possession", "કબજો": "possession", "મોડું": "delay", "મોડા": "delay", "વિલંબ": "delay",
    "વ્યાજ": "interest", "રિફંડ": "refund", "પૈસા પાછા": "refund return of amount", "બિલ્ડર": "promoter",
    "ડેવલપર": "promoter", "પ્રમોટર": "promoter", "નોંધણી": "registration", "રજીસ્ટ્રેશન": "registration",
    "જાહેરાત": "advertisement", "ફરિયાદ": "complaint", "વળતર": "compensation", "કરાર": "agreement for sale",
    "બુકિંગ": "booking advance deposit", "એડવાન્સ": "advance deposit", "દંડ": "penalty", "એજન્ટ": "real estate agent",
    "દલાલ": "real estate agent", "ખામી": "structural defect", "તિરાડ": "structural defect",
    "પ્લાન": "sanctioned plan", "નકશો": "sanctioned plan", "મંજૂરી": "approval", "વેચાણ દસ્તાવેજ": "conveyance deed",
    "દસ્તાવેજ": "conveyance deed", "સુવિધા": "amenities common areas", "પાર્કિંગ": "parking",
    "અપીલ": "appeal appellate tribunal", "મુદત": "extension period", "રદ": "revocation cancellation",
    "ત્રિમાસિક": "quarterly", "ખરીદનાર": "allottee", "ગ્રાહક": "allottee", "ફ્લેટ": "apartment",
    "મકાન": "apartment building", "પ્રોજેક્ટ": "real estate project", "અધિકાર": "rights", "ફરજ": "duties", "માહિતી": "information",
    # Hindi
    "पज़ेशन": "possession", "पजेशन": "possession", "कब्जा": "possession", "कब्ज़ा": "possession",
    "देरी": "delay", "विलंब": "delay", "ब्याज": "interest", "रिफंड": "refund", "पैसे वापस": "refund return of amount",
    "बिल्डर": "promoter", "डेवलपर": "promoter", "प्रमोटर": "promoter", "पंजीकरण": "registration",
    "रजिस्ट्रेशन": "registration", "विज्ञापन": "advertisement", "शिकायत": "complaint", "मुआवजा": "compensation",
    "मुआवज़ा": "compensation", "अनुबंध": "agreement for sale", "बुकिंग": "booking advance deposit",
    "अग्रिम": "advance deposit", "जुर्माना": "penalty", "दंड": "penalty", "एजेंट": "real estate agent",
    "दलाल": "real estate agent", "खराबी": "structural defect", "दरार": "structural defect",
    "नक्शा": "sanctioned plan", "मंजूरी": "approval", "रजिस्ट्री": "conveyance deed", "सुविधा": "amenities common areas",
    "पार्किंग": "parking", "अपील": "appeal appellate tribunal", "खरीदार": "allottee", "फ्लैट": "apartment",
    "प्रोजेक्ट": "real estate project", "अधिकार": "rights",
    "बिना": "without", "कर्तव्य": "duties",
}

# Word stems, so every inflected form matches (मुआवजा / मुआवजे, દાવો / દાવા, खाता / खाते / खातों), and
# the words that decide which provision a question is about (punishment, extension, revocation, account,
# withdraw, responsible). Matched as substrings of the question, like the glossary above.
STEMS: dict[str, str] = {
    # Gujarati
    "કબજ": "possession",
    "દાવ": "claims adjudging compensation", "નિર્ણય": "adjudicate decide", "સજા": "punishment penalty",
    "નોંધણી ન": "non-registration punishment", "નોંધણી વગર": "prior registration without registering",
    "ખાતા": "separate account", "ખાતું": "separate account", "ખાતુ": "separate account", "બેંક": "bank account",
    "ઉપાડ": "withdraw withdrawal", "જવાબદાર": "responsible liability", "બાંધકામ": "construction structural",
    "માળખા": "structural", "વધાર": "extension", "લંબાવ": "extension", "રદ્દ": "revocation cancellation",
    "વેચાણ ખત": "conveyance deed", "રજિસ્ટ્રેશન": "registration", "હક": "rights", "અધિકારો": "rights and duties of allottees",
    "વ્યાજ દર": "rate of interest", "ત્રિમાસિક અહેવાલ": "quarterly progress report",
    # Hindi (with and without nukta)
    "कब्ज": "possession", "क़ब्ज़": "possession", "कब्ज़": "possession",
    "मुआवज": "compensation", "मुआवज़": "compensation", "दाव": "claims adjudging compensation",
    "फैसल": "adjudicate decide", "फ़ैसल": "adjudicate decide", "निर्णय": "adjudicate decide",
    "सजा": "punishment penalty", "सज़ा": "punishment penalty", "पंजीकरण न": "non-registration punishment",
    "पंजीकरण के बिना": "prior registration without registering", "बिना पंजीकरण": "prior registration without registering",
    "बढ़ा": "extension", "बढा": "extension", "रद्द": "revocation cancellation", "निरस्त": "revocation",
    "कन्वेयंस": "conveyance deed", "डीड": "deed", "बैनामा": "conveyance deed",
    "ढांच": "structural", "ढाँच": "structural", "निर्माण": "construction", "जिम्मेदार": "responsible liability",
    "ज़िम्मेदार": "responsible liability", "समझौत": "agreement for sale", "करार": "agreement for sale",
    "हस्ताक्षर": "execute agreement", "खाता": "separate account", "खाते": "separate account", "खातों": "separate account",
    "बैंक": "bank account", "निकाल": "withdraw withdrawal", "ब्याज दर": "rate of interest",
    "खरीदार के अधिकार": "rights and duties of allottees", "आवंटी": "allottee", "विज्ञापन": "advertisement marketing",
    "तिमाही": "quarterly progress report",
}


# Everyday English → the Act's own vocabulary ("per cent", "allottee", "promoter").
ENGLISH_TERMS: dict[str, str] = {
    "percent": "per cent", "%": "per cent", "builder": "promoter", "developer": "promoter",
    "buyer": "allottee", "home buyer": "allottee", "flat": "apartment", "money back": "refund return of amount",
    "deposit": "advance payment", "token amount": "advance payment", "late": "delay",
    "handover": "possession", "hand over": "possession", "sale deed": "conveyance deed",
    "decides": "adjudicate", "decide": "adjudicate", "claim": "adjudging compensation",
}


# Two ideas together that name one provision: (any of these) and (any of these) -> the provision's own words.
PAIRS: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
    (("agent", "એજન્ટ", "દલાલ", "एजेंट", "दलाल"), ("regist", "નોંધણી", "રજિસ્ટ્રેશન", "पंजीकरण", "रजिस्ट्रेशन"),
     "registration of real estate agents"),
    (("allottee", "buyer", "ખરીદનાર", "ગ્રાહક", "खरीदार", "आवंटी"), ("right", "અધિકાર", "હક", "अधिकार", "हक"),
     "rights and duties of allottees"),
]


def english_terms(query: str) -> str:
    """Only the English legal terms the question's words map to ("" when none do)."""
    terms: list[str] = []
    lowered = query.lower()
    for word, english in ENGLISH_TERMS.items():
        if word in lowered and english not in terms:
            terms.append(english)
    for word, english in (*GLOSSARY.items(), *STEMS.items()):
        if word in query and english not in terms:
            terms.append(english)
    for first, second, english in PAIRS:
        if any(w in lowered for w in first) and any(w in lowered for w in second) and english not in terms:
            terms.append(english)
    return " ".join(terms)


def expand(query: str) -> str:
    """The query plus English legal terms for any Gujarati/Hindi words or everyday English it contains."""
    terms = english_terms(query)
    return f"{query} {terms}" if terms else query
