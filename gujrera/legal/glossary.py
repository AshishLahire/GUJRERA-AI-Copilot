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


def expand(query: str) -> str:
    """The query plus English legal terms for any Gujarati/Hindi words it contains."""
    terms = []
    for word, english in GLOSSARY.items():
        if word in query and english not in terms:
            terms.append(english)
    return f"{query} {' '.join(terms)}" if terms else query
