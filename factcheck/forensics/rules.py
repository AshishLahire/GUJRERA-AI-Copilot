"""Scoring weights, cue definitions, multilingual keyword lists, and issuer rules for Stage 2 forensics."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ISSUER_REGISTRY_PATH = REPO_ROOT / "data" / "dataset" / "03_issuer_registry" / "issuers.json"
OFFICIAL_CORPUS_PATH = REPO_ROOT / "data" / "dataset" / "02_official_source_corpus" / "documents.jsonl"
CUE_TAXONOMY_PATH = REPO_ROOT / "data" / "dataset" / "06_synthetic_forgeries" / "cue_taxonomy.json"

# Scoring weights (mutable dict so unit tests can verify dynamic weight changes)
SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 35,
    "warning": 15,
    "info": 0,
}

RISK_THRESHOLDS: dict[str, int] = {
    "high": 60,
    "medium": 25,
}

# Fictional issuers from 06_synthetic_forgeries so synthetic tests/samples work seamlessly
SYNTHETIC_ISSUERS: list[dict[str, Any]] = [
    {
        "issuer_id": "FIC-NFRA",
        "name_en": "National Financial Regulatory Authority (Fictional)",
        "name_hi": "",
        "type": "regulator",
        "official_domains": ["nfra-fictional.example"],
        "head_title": "Chief General Manager",
        "never_does": [
            "use signatory titles such as 'Chairman & CEO', 'Chief Commissioner (Finance)', or 'Customer Care Manager'",
        ],
        "reference_patterns": [
            {
                "name": "NFRA circular serial",
                "regex": r"^NFRA/\d{4}-\d{2}/\d+$",
                "status": "verified",
            }
        ],
    },
    {
        "issuer_id": "FIC-CEB",
        "name_en": "Central Examination Board (Fictional)",
        "name_hi": "",
        "type": "exam board",
        "official_domains": ["ceb-fictional.example"],
        "head_title": "Director (Academics)",
        "never_does": [
            "use signatory titles such as 'Customer Care Manager' or 'Chairman & CEO'",
        ],
        "reference_patterns": [
            {
                "name": "CEB academic circular",
                "regex": r"^CEB/Acad-\d+/\d{4}$",
                "status": "verified",
            }
        ],
    },
    {
        "issuer_id": "FIC-TCA",
        "name_en": "Telecom Compliance Authority (Fictional)",
        "name_hi": "",
        "type": "regulator",
        "official_domains": ["tca-fictional.example"],
        "head_title": "Secretary",
        "never_does": [
            "use signatory titles such as 'Customer Care Manager', 'Chairman & CEO', or 'Chief Commissioner (Finance)'",
        ],
        "reference_patterns": [
            {
                "name": "TCA QoS circular",
                "regex": r"^TCA/QoS/\d+/\d{4}$",
                "status": "verified",
            }
        ],
    },
    {
        "issuer_id": "FIC-RSM",
        "name_en": "Rural Skills Mission (Fictional)",
        "name_hi": "",
        "type": "mission",
        "official_domains": ["rsm-fictional.example"],
        "head_title": "Mission Director",
        "never_does": [
            "use signatory titles such as 'Customer Care Manager' or 'Chairman & CEO'",
        ],
        "reference_patterns": [
            {
                "name": "RSM HR reference",
                "regex": r"^RSM-\d{4}/HR/\d+$",
                "status": "verified",
            }
        ],
    },
]

# Issuer aliases for letterhead & body detection
# NOTE: Regional script aliases across gu, kn, ml, pa, or, ur, mr, bn, ta, te - needs native-speaker review
ISSUER_ALIASES: dict[str, list[str]] = {
    "RBI": [
        "Reserve Bank of India",
        "भारतीय रिज़र्व बैंक",
        "भारतीय रिजर्व बैंक",
        "रिज़र्व बैंक",
        "रिजर्व बैंक",
        "आरबीआई",
        "ரிசர்வ் வங்கி",
        "ஆர்பிஐ",
        "রিজার্ভ ব্যাংক",
        "আরবিআই",
        "రిజర్వ్ బ్యాంక్",
        "ఆర్బీఐ",
        "रिझर्व्ह बँक",
        "आरबीआय",
        "RBI",
        "રિઝર્વ બેંક ઓફ ઇન્ડિયા",
        "રિઝર્વ બેંક",
        "આરબીઆઈ",
        "આરબીઆઇ",
        "ಭಾರತೀಯ ರಿಸರ್ವ್ ಬ್ಯಾಂಕ್",
        "ರಿಸರ್ವ್ ಬ್ಯಾಂಕ್",
        "ಆರ್‌ಬಿಐ",
        "ഭാരതീയ റിസർവ് ബാങ്ക്",
        "റിസർവ് ബാങ്ക്",
        "ആർബിഐ",
        "ਭਾਰਤੀ ਰਿਜ਼ਰਵ ਬੈਂਕ",
        "ਰਿਜ਼ਰਵ ਬੈਂਕ",
        "ਆਰਬੀਆਈ",
        "ଭାରତୀୟ ରିଜର୍ଭ ବ୍ୟାଙ୍କ",
        "ରିଜର୍ଭ ବ୍ୟାଙ୍କ",
        "ଆରବିଆଇ",
        "ریزرو بینک آف انڈیا",
        "ریزرو بینک",
        "آر بی آئی",
    ],
    "SEBI": [
        "Securities and Exchange Board of India",
        "भारतीय प्रतिभूति और विनिमय बोर्ड",
        "सेबी",
        "SEBI",
        "भारतीय रोखे आणि विनिमय मंडळ",
        "ভারতীয় সিকিউরিটিজ অ্যান্ড এক্সচেঞ্জ বোর্ড",
        "இந்திய பங்கு மற்றும் பரிவர்த்தனை வாரியம்",
        "సెక్యూరిటీస్ అండ్ ఎక్స్ఛేంజ్ బోర్డ్ ఆఫ్ ఇండియా",
        "ભારતીય સિક્યોરિટીઝ એન્ડ એક્સચેન્જ બોર્ડ",
        "ಸೆಕ್ಯುರಿಟೀಸ್ ಅಂಡ್ ಎಕ್ಸ್ಚೇಂಜ್ ಬೋರ್ಡ್ ಆಫ್ ಇಂಡಿಯಾ",
        "സെക്യൂരിറ്റീസ് ആൻഡ് എക്സ്ചേഞ്ച് ബോർഡ് ഓഫ് ഇന്ത്യ",
        "ਭਾਰਤੀ ਪ੍ਰਤੀਭੂਤੀਆਂ ਅਤੇ ਵਟਾਂਦਰਾ ਬੋਰਡ",
        "ଭାରତୀୟ ପ୍ରତିଭୂତି ଏବଂ ବିନିମୟ ବୋର୍ଡ",
        "سیکیورٹیز اینڈ ایکسچینج بورڈ آف انڈیا",
    ],
    "PIB": [
        "Press Information Bureau",
        "पत्र सूचना कार्यालय",
        "पीआईबी",
        "पीआयबी",
        "প্রেস ইনফরমেশন ব্যুরো",
        "পিআইবি",
        "பத்திரிகை தகவல் பணியகம்",
        "பிஐபி",
        "ప్రెస్ ఇన్ఫర్మేషన్ బ్యూరో",
        "పీఐబీ",
        "પ્રેસ ઇન્ફોર્મેશન બ્યુરો",
        "પીઆઈબી",
        "ಪ್ರೆಸ್ ಮಾಹಿತಿ ಬ್ಯೂರೋ",
        "ಪಿಐಬಿ",
        "പ്രസ് ഇൻഫർമേഷൻ ബ്യൂറോ",
        "പിഐബി",
        "ਪ੍ਰੈਸ ਸੂਚਨਾ ਬਿਊਰੋ",
        "ਪੀਆਈਬੀ",
        "ପ୍ରେସ ସୂଚନା ବ୍ୟୁରୋ",
        "ପିଆଇବି",
        "پریس انفارمیشن بیورو",
        "پی آئی بی",
    ],
    "CBSE": [
        "Central Board of Secondary Education",
        "केंद्रीय माध्यमिक शिक्षा बोर्ड",
        "केन्द्रीय माध्यमिक शिक्षा बोर्ड",
        "के.मा.शि.बो.",
        "सीबीएसई",
        "CBSE",
        "केंद्रीय माध्यमिक शिक्षण मंडळ",
        "সেন্ট্রাল বোর্ড অফ সেকেন্ডারি এডুকেশন",
        "மத்திய இடைநிலைக் கல்வி வாரியம்",
        "సెంట్రల్ బోర్డ్ ఆఫ్ సెకండరీ ఎడ್ಯుకేషన్",
        "સેન્ટ્રલ બોર્ડ ઓફ સેકન્ડરી એજ્યુકેશન",
        "ಕೇಂದ್ರೀಯ ಪ್ರೌಢ ಶಿಕ್ಷಣ ಮಂಡಳಿ",
        "സെൻട്രൽ ബോർഡ് ഓഫ് സെക്കൻഡറി എജ്യുക്കേഷൻ",
        "ਕੇਂਦਰੀ ਸੈਕੰਡਰੀ ਸਿੱਖਿਆ ਬੋਰਡ",
        "କେନ୍ଦ୍ରୀୟ ମାଧ୍ୟମିକ ଶିକ୍ଷା ବୋର୍ଡ",
        "سنٹرل بورڈ آف سیکنڈری ایجوکیشن",
    ],
    "I4C": [
        "Indian Cyber Crime Coordination Centre",
        "भारतीय साइबर अपराध समन्वय केंद्र",
        "भारतीय सायबर गुन्हे समन्वय केंद्र",
        "ভারতীয় সাইবার অপরাধ সমন্বয় কেন্দ্র",
        "இந்திய சைபர் குற்ற ஒருங்கிணைப்பு மையம்",
        "భారత సైబర్ నేర సమన్వయ కేంద్రం",
        "Cyber Crime Centre",
        "I4C",
    ],
    "MUDRA": [
        "Micro Units Development & Refinance Agency",
        "PM Mudra Yojana",
        "Pradhan Mantri Mudra Yojana",
        "Pradhan Mantri Mudra Vojna",
        "Mudra Finance",
        "MUDRA LOAN",
        "प्रधानमंत्री मुद्रा योजना",
        "प्रधनमंत्री Mudra योजना",
        "मुद्रा योजना",
        "প্রধানমন্ত্রী মুদ্রা যোজনা",
        "பிரதமர் முத்ரா யோஜனா",
        "ప్రధానమంత్రి ముద్రా యోజన",
        "MUDRA",
    ],
    "TRAI": [
        "Telecom Regulatory Authority of India",
        "भारतीय दूरसंचार विनियामक प्राधिकरण",
        "ट्राई",
        "ट्राय",
        "ट्रायने",
        "ট্রাই",
        "டிராய்",
        "டிராயால்",
        "ట్రాయ్",
        "TRAI",
    ],
    "BSNL": [
        "Bharat Sanchar Nigam Limited",
        "भारत संचार निगम लिमिटेड",
        "बीएसएनएल",
        "BSNL",
    ],
    "MOE": [
        "Ministry of Education",
        "Department of School Education",
        "Department of Higher Education",
        "शिक्षा मंत्रालय",
        "PM Free Laptop Yojana",
        "पीएम फ्री लैपटॉप योजना",
        "पीएम मोफत लॅपटॉप योजना",
        "পিএম ফ্রি ল্যাপটপ যোজনা",
        "பிஎம் இலவச மடிக்கணினி திட்டம்",
        "పీఎం ఉచిత ల్యాప్‌టాప్ యోజన",
        "শিক্ষা মন্ত্রক",
        "கல்வி அமைச்சகம்",
        "విద్యా మంత్రిత్వ శాఖ",
        "શિક્ષણ મંત્રાલય",
        "પીએમ મફત લેપટોપ યોજના",
        "ಶಿಕ್ಷಣ ಸಚಿವಾಲಯ",
        "ಪಿಎಂ ಉಚಿತ ಲ್ಯಾಪ್ಟಾಪ್ ಯೋಜನೆ",
        "വിദ്യാഭ്യാസ മന്ത്രാലയം",
        "പിഎം സൗജന്യ ലാപ്‌ടോപ്പ് പദ്ധതി",
        "ਸਿੱਖਿਆ ਮੰਤਰਾਲਾ",
        "ਪੀਐਮ ਮੁਫ਼ਤ ਲੈਪਟਾਪ ਯੋਜਨਾ",
        "ଶିକ୍ଷା ମନ୍ତ୍ରଣାଳୟ",
        "ପ୍ରଧାନମନ୍ତ୍ରୀ ମାଗଣା ଲାପଟପ୍ ଯୋଜନା",
        "وزارت تعلیم",
        "پی ایم مفت لیپ ٹاپ اسکیم",
    ],
    "NBE": [
        "National Board of Examinations in Medical Sciences",
        "National Board of Examinations",
        "राष्ट्रीय चिकित्सा विज्ञान परीक्षा बोर्ड",
        "एनबीई",
        "एनबीईची",
        "এনবিই",
        "என்பிஇ",
        "ఎన్‌బీఈ",
        "NBEMS",
        "NBE",
    ],
    "NTA": [
        "National Testing Agency",
        "राष्ट्रीय परीक्षा एजेंसी",
        "NTA",
    ],
    "UGC": [
        "University Grants Commission",
        "विश्वविद्यालय अनुदान आयोग",
        "UGC",
    ],
    "RRB": [
        "Railway Recruitment Board",
        "Railway Recruitment Boards",
        "Ministry of Railways",
        "Railway Board",
        "रेलवे भर्ती बोर्ड",
        "रेल मंत्रालय",
        "RRB",
        "रेल्वे भरती मंडळ",
        "রেলওয়ে রিক্রুটমেন্ট বোর্ড",
        "রেল মন্ত্রক",
        "ரயில்வே भर्ती வாரியம்",
        "ரயில்வே அமைச்சகம்",
        "రైల్వే రిక్రూట్‌మెంట్ బోర్డు",
        "రైల్వే మంత్రిత్వ శాఖ",
        "રેલવે ભરતી બોર્ડ",
        "રેલવે મંત્રાલય",
        "ರೈಲ್ವೆ ನೇಮಕಾತಿ ಮಂಡಳಿ",
        "ರೈಲ್ವೆ ಸಚಿವಾಲಯ",
        "റെയിൽവേ റിക്രൂട്ട്‌മെന്റ് ബോർഡ്",
        "റെയിൽവേ മന്ത്രാലയം",
        "ਰੇਲਵੇ ਭਰਤੀ ਬੋਰਡ",
        "ਰੇਲਵੇ ਮੰਤਰਾਲਾ",
        "ରେଳବାଇ ନିଯୁକ୍ତି ବୋର୍ଡ",
        "ରେଳ ମନ୍ତ୍ରଣାଳୟ",
        "ریلوے بھرتی بورڈ",
        "وزارت ریلوے",
    ],
    "MOF": [
        "Ministry of Finance",
        "Department of Economic Affairs",
        "Department of Revenue",
        "Department of Financial Services",
        "वित्त मंत्रालय",
        "अर्थ मंत्रक",
        "অর্থ মন্ত্রকের",
        "நிதி அமைச்சகத்தின்",
        "ఆర్థిక మంత్రిత్వ శాఖ",
        "Finance Ministry",
    ],
    "MOP": [
        "Ministry of Power",
        "विद्युत मंत्रालय",
    ],
    "INC": [
        "Indian Nursing Council",
        "भारतीय उपचर्या परिषद",
    ],
    "MOL": [
        "Ministry of Labour & Employment",
        "Ministry of Labour and Employment",
        "श्रम और रोजगार मंत्रालय",
    ],
    "MSDE": [
        "Ministry of Skill Development & Entrepreneurship",
        "Ministry of Skill Development and Entrepreneurship",
        "कौशल विकास और उद्यमशीलता मंत्रालय",
        "Kaushal Bharat Yojana",
        "कौशल भारत योजना",
        "कौशल भारत योजनेअंतर्गत",
        "কৌশল ভারত যোজনায়",
        "கௌஷல் பாரத் யோஜனா",
        "కౌశల్ భారత్ యోజన",
        "Skill India",
    ],
    "IB": [
        "Intelligence Bureau",
        "आसूचना ब्यूरो",
        "खुफिया ब्यूरो",
    ],
    "OMC": [
        "Ministry of Petroleum and Natural Gas",
        "Ministry of Petroleum & Natural Gas",
        "Petroleum Ministry",
        "Indian Oil Corporation",
        "Bharat Petroleum Corporation",
        "Bharat Petroleum",
        "Hindustan Petroleum",
        "Ujjwala Gas Agency",
        "Ujjwala Yojana",
        "LPG Vitrak Chayan",
        "LPG Vitarak Chayan",
        "पेट्रोलियम और प्राकृतिक गैस मंत्रालय",
        "पेट्रोलियम मंत्रालय",
        "पेट्रोलियम कंपनी",
        "भारत पेट्रोलियम",
        "পেট্রোলিয়াম মন্ত্রকের",
        "পেট্রোলিয়াম কোম্পানি",
        "பெட்ரோலிய அமைச்சக",
        "பெட்ரோலிய நிறுவனம்",
        "పెట్రోలియం మంత్రిత్వ శాఖ",
        "పెట్రోలియం కంపెనీ",
        "IOCL",
        "BPCL",
        "HPCL",
    ],
    "ITD": [
        "Income Tax Department",
        "Department of Income Tax",
        "Central Board of Direct Taxes",
        "आयकर विभाग",
        "আয়কর বিভাগ",
        "வருமான வரித் துறை",
        "ఆదాయపు పన్ను శాఖ",
        "Income Tax Dept",
        "CBDT",
    ],
    "MOD": [
        "Ministry of Defence",
        "Indian Air Force",
        "Indian Army",
        "Indian Navy",
        "रक्षा मंत्रालय",
        "भारतीय वायुसेना",
        "वायुसेना प्रमुख",
        "हवाई दल",
        "বায়ুসেনা",
        "விமானப்படை",
        "వాయుసేన",
        "IAF",
    ],
    "MEA": [
        "Ministry of External Affairs",
        "विदेश मंत्रालय",
    ],
    "MHA": [
        "Ministry of Home Affairs",
        "गृह मंत्रालय",
        "MHA",
        "স্বরাষ্ট্র মন্ত্রক",
        "স্বরাষ্ট্র মন্ত্রণালয়",
        "உள்துறை அமைச்சகம்",
        "హోం వ్యవహారాల మంత్రిత్వ శాఖ",
        "హోం శాఖ",
        "ગૃહ મંત્રાલય",
        "ಗೃಹ ವ್ಯವಹಾರಗಳ ಸಚಿವಾಲಯ",
        "ಗೃಹ ಸಚಿವಾಲಯ",
        "ആഭ്യന്തര മന്ത്രാലയം",
        "ਗ੍ਰਹਿ ਮੰਤਰਾਲਾ",
        "ਗ੍ਰਹਿ ਮੰਤਰਾਲੇ",
        "ଗୃହ ମନ୍ତ୍ରଣାଳୟ",
        "وزارت داخلہ",
    ],
    "MOHFW": [
        "Ministry of Health and Family Welfare",
        "Ministry of Health & Family Welfare",
        "National Health Mission",
        "National Rural Health Mission",
        "स्वास्थ्य और परिवार कल्याण मंत्रालय",
        "राष्ट्रीय स्वास्थ्य मिशन",
        "राष्ट्रीय ग्रामीण स्वास्थ्य मिशन",
        "राष्ट्रीय स्वास्थ्य मंत्रालय",
        "NHM",
        "NRHM",
        "MoHFW",
        "आरोग्य आणि कुटुंब कल्याण मंत्रालय",
        "স্বাস্থ্য ও পরিবার কল্যাণ মন্ত্রক",
        "சுகாதாரம் மற்றும் குடும்ப நல அமைச்சகம்",
        "వైద్య మరియు కుటుంబ సంକ୍ଷೇమ మంత్రిత్వ శాఖ",
        "ఆరోగ్య శాఖ",
        "આરોગ્ય અને પરિવાર કલ્યાણ મંત્રાલય",
        "ಆರೋಗ್ಯ ಮತ್ತು ಕುಟುಂಬ ಕಲ್ಯಾಣ ಸಚಿವಾಲಯ",
        "ആരോഗ്യ കുടുംബക്ഷേമ മന്ത്രാലയം",
        "ਸਿਹਤ ਅਤੇ ਪਰਿਵਾਰ ਭਲਾਈ ਮੰਤਰਾਲਾ",
        "ସ୍ୱାସ୍ଥ୍ୟ ଏବଂ ପରିବାର କଲ୍ୟାଣ ମନ୍ତ୍ରଣାଳୟ",
        "وزارت صحت اور خاندانی بہبود",
        "وزارت صحت",
    ],
    "MSME": [
        "Ministry of Micro, Small and Medium Enterprises",
        "सूक्ष्म, लघु और मध्यम उद्यम मंत्रालय",
        "PMEGP",
        "MSME",
    ],
    "BOI": [
        "Bank of India",
        "बैंक ऑफ़ इंडिया",
        "बैंक ऑफ इंडिया",
    ],
    "MORTH": [
        "Ministry of Road Transport and Highways",
        "National Highways Authority of India",
        "सड़क परिवहन और राजमार्ग मंत्रालय",
        "भारतीय राष्ट्रीय राजमार्ग प्राधिकरण",
        "नितिन गडकरी",
        "Nitin Gadkari",
        " टोल प्लाजा",
        "टोल प्लाज़ा",
        "NHAI",
        "Parivahan",
    ],
    "MIB": [
        "Ministry of Information and Broadcasting",
        "सूचना और प्रसारण मंत्रालय",
    ],
    "DELHIPOLICE": [
        "Delhi Police",
        "दिल्ली पुलिस",
    ],
    "MOCI": [
        "Ministry of Commerce and Industry",
        "Ministry of Commerce",
        "Department of Commerce",
        "वाणिज्य और उद्योग मंत्रालय",
    ],
    "MNRE": [
        "Ministry of New and Renewable Energy",
        "नवीन और नवीकरणीय ऊर्जा मंत्रालय",
        "PM-KUSUM",
        "PM Kusum Yojna",
        "PM Kusum Yojana",
        "कुसुम योजना",
        "नवीन आणि नवीकरणीय ऊर्जा मंत्रालय",
        "নতুন এবং পুনর্নবীকরণযোগ্য শক্তি মন্ত্রক",
        "புதிய மற்றும் புதுப்பிக்கத்தக்க எரிசக்தி அமைச்சகம்",
        "குசும் திட்டம்",
        "కొత్త మరియు పునరుత్పాదక ఇంధన మంత్రిత్వ శాఖ",
        "નવીન અને નવીનીકરણીય ઉર્જા મંત્રાલય",
        "કુસુમ યોજના",
        "ಹೊಸ ಮತ್ತು ನವೀಕರಿಸಬಹುದಾದ ಇಂಧನ ಸಚಿವಾಲಯ",
        "ಕುಸುಮ್ ಯೋಜನೆ",
        "പുതിയതും പുനരുപയോഗിക്കാവുന്നതുമായ ഊർജ്ജ മന്ത്രാലയം",
        "കുസും പദ്ധതി",
        "ਨਵੀਂ ਅਤੇ ਨਵਿਆਉਣਯੋਗ ਊਰਜਾ ਮੰਤਰਾਲਾ",
        "ਕੁਸੁਮ ਯੋਜਨਾ",
        "ନୂତନ ଏବଂ ଅକ୍ଷୟ ଶକ୍ତି ମନ୍ତ୍ରଣାଳୟ",
        "କୁସୁਮ ଯୋଜନା",
        "نئی اور قابل تجدید توانائی کی وزارت",
        "کسم یوجنا",
    ],
    "MEITY": [
        "Ministry of Electronics and Information Technology",
        "Ministry of Electronics and IT",
        "इलेक्ट्रॉनिकी और सूचना प्रौद्योगिकी मंत्रालय",
        "MeitY",
    ],
    "MOEFCC": [
        "Ministry of Environment, Forest and Climate Change",
        "पर्यावरण, वन और जलवायु परिवर्तन मंत्रालय",
    ],
    "SCI": [
        "Supreme Court of India",
        "Supreme Court",
        "भारत का सर्वोच्च न्यायालय",
        "सर्वोच्च न्यायालय",
        "सुप्रीम कोर्ट",
        "সুপ্রিম কোর্ট",
        "உச்ச நீதிமன்றம்",
        "உச்ச நீதிமன்ற",
        "సుప్రీంకోర్టు",
    ],
    "FIC-NFRA": [
        "National Financial Regulatory Authority",
        "NFRA",
    ],
    "FIC-CEB": [
        "Central Examination Board",
        "CEB",
    ],
    "FIC-TCA": [
        "Telecom Compliance Authority",
        "TCA",
    ],
    "FIC-RSM": [
        "Rural Skills Mission",
        "RSM",
    ],
}

# Distinct law-enforcement / judicial / ministry agencies for check (b) Mixed Issuers
MIXED_AGENCY_GROUPS: list[tuple[str, str, re.Pattern[str]]] = [
    ("I4C", "Indian Cyber Crime Coordination Centre (I4C)", re.compile(r"\b(?:I4C|Indian\s+Cyber\s+Crime\s+Coordination\s+Centre)\b", re.IGNORECASE)),
    ("CBI", "Central Bureau of Investigation (CBI)", re.compile(r"\b(?:CBI|Central\s+Bureau\s+of\s+Investigation)\b", re.IGNORECASE)),
    ("INTERPOL", "INTERPOL", re.compile(r"\bINTERPOL\b", re.IGNORECASE)),
    ("DELHI_POLICE", "Delhi Police", re.compile(r"\bDelhi\s+Police\b", re.IGNORECASE)),
    ("IB", "Intelligence Bureau (IB)", re.compile(r"\bIntelligence\s+Bureau\b", re.IGNORECASE)),
    ("RAW", "Research and Analysis Wing (RAW)", re.compile(r"\b(?:R&AW|Research\s+and\s+Analysis\s+Wing)\b", re.IGNORECASE)),
    ("SCI", "Supreme Court", re.compile(r"\bSupreme\s+Court\b|सर्वोच्च\s+न्यायालय|सुप्रीम\s+कोर्ट|সুপ্রিম\s+কোর্ট|உச்ச\s+நீதிமன்ற|సుప్రీంకోర్టు", re.IGNORECASE)),
    ("MOF", "Ministry of Finance", re.compile(r"\b(?:Ministry\s+of\s+Finance|Finance\s+Ministry)\b|वित्त\s+मंत्रालय| वित्त\s+मंत्रालया|অর্থ\s+মন্ত্রক|நிதி\s+அமைச்சக|ఆర్థిక\s+మంత్రిత్వ", re.IGNORECASE)),
    ("MOCI", "Ministry of Commerce", re.compile(r"\bMinistry\s+of\s+Commerce\b", re.IGNORECASE)),
    ("MOCA", "Ministry of Civil Aviation", re.compile(r"\bMinistry\s+of\s+Civil\s+Aviation\b", re.IGNORECASE)),
]

# Free-mail providers flagged when used as contact on official notices
FREE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "yahoo.in",
        "yahoo.co.in",
        "outlook.com",
        "hotmail.com",
        "rediffmail.com",
        "protonmail.com",
        "proton.me",
        "ymail.com",
        "mail.com",
    }
)

# Official helplines that should NOT be flagged as personal mobile numbers
OFFICIAL_HELPLINE_NUMBERS: frozenset[str] = frozenset(
    {
        "8799711259",  # PIB Fact Check WhatsApp
        "1930",        # I4C Cyber Crime Helpline
    }
)

# Payment demand words across en, hi, hi-Latn, mr, bn, ta, te, gu, kn, ml, pa, or, ur
# NOTE: Lists for gu, kn, ml, pa, or, ur - needs native-speaker review
FEE_PAYMENT_PATTERNS: list[re.Pattern[str]] = [
    # English & Hinglish explicit fee / charge / deposit demands
    re.compile(
        r"\b(?:"
        r"(?:registration|processing|application|file|agreement|verification|security|allotment|form|noc|insurance|refundable|advance|counselling)\s+"
        r"(?:fee|fees|charge|charges|deposit|amount|payment)"
        r"|(?:pay|deposit|submit|remit|transfer)\s+(?:only\s+|a\s+|an\s+|the\s+|refundable\s+)?(?:Rs\.?|INR|₹|\d[\d,]*|\w+\s+)*(?:fee|fees|charge|charges|deposit|penalty)"
        r"|(?:fee|fees|charge|charges|deposit)\s+(?:of\s+)?(?:is\s+)?(?:refundable\s+)?(?:Rs\.?|INR|₹)\s*\d[\d,]*"
        r"|(?:Rs\.?|INR|₹)\s*\d[\d,]*\s+(?:[\w\-]+\s+){0,2}(?:fee|fees|charge|charges|deposit|registration)"
        r"|(?:bharo|bharein|jama\s+karo|jama\s+karein|dena\s+hai|pay\s+karo)"
        r")\b",
        re.IGNORECASE,
    ),
    # Hindi (Devanagari) & Marathi (Devanagari)
    re.compile(
        r"(?:"
        r"(?:पंजीकरण|प्रोसेसिंग|फाइल|फ़ाइल|आवेदन|फॉर्म|समझौता|सुरक्षा|वापसी\s+योग्य|नोंदणी|परतावायोग्य)\s*(?:शुल्क|फीस|चार्ज|जमा|रक्कम)"
        r"|(?:शुल्क|फीस|चार्ज|जुर्माना\s+राशि|दंडाची\s+रक्कम)\s*(?:जमा|भरा|भरावी|दें|देना)"
        r"|(?:₹|रु\.?|रुपये)\s*[\d,]+\s*(?:[\w\u0900-\u097F]+\s+){0,3}(?:शुल्क|फीस|चार्ज|जमा\s+करें|भरा)"
        r")"
    ),
    # Bengali
    re.compile(
        r"(?:"
        r"(?:রেজিস্ট্রেশন|প্রসেসিং|ফাইল|ফর্ম|ফেরতযোগ্য|জরিমানার)\s*(?:ফি|চার্জ|টাকা)"
        r"|(?:ফি|চার্জ|জরিমানার\s+টাকা)\s*(?:জমা\s+দিন|দিন|দিতে\s+হবে)"
        r"|₹\s*[\d,০-৯]+\s*(?:[^\s]+\s+){0,3}(?:ফি|চার্জ)"
        r")"
    ),
    # Tamil
    re.compile(
        r"(?:"
        r"(?:பதிவுக்|பதிவு|கோப்புக்|கோப்பு|படிவக்|படிவ|திருப்பித்\s+தரக்கூடிய|அபராதத்)\s*(?:கட்டணம்|தொகை|தொகையைச்)"
        r"|(?:கட்டணம்|அபராதத்\s+தொகையைச்)\s*(?:செலுத்துங்கள்|செலுத்த\s+வேண்டும்|செலுத்தவும்)"
        r"|₹\s*[\d,]+\s*(?:[^\s]+\s+){0,3}(?:கட்டணம்)"
        r")"
    ),
    # Telugu
    re.compile(
        r"(?:"
        r"(?:రిజిస్ట్రేషన్|ఫైల్|ఫారం|తిరిగి\s+చెల్లించదగిన|జరిమానా)\s*(?:ఫీజు|ఛార్జీ|రుసుము|మొత్తం)"
        r"|(?:ఫీజు|ఛార్జీ|రుసుము|జరిమానా\s+మొత్తం)\s*(?:చెల్లించండి|జమ\s+చేయండి|చెల్లించాలి)"
        r"|₹\s*[\d,]+\s*(?:[^\s]+\s+){0,3}(?:ఫీజు|ఛార్జీ|రుసుము)"
        r")"
    ),
    # Gujarati - needs native-speaker review
    re.compile(
        r"(?:"
        r"(?:નોંધણી|પ્રોસેસિંગ|અરજી|ફાઇલ|સિક્યોરિટી|રિફંડપાત્ર|દંડ)\s*(?:ફી|ચાર્જ|રકમ)"
        r"|(?:ફી|ચાર્જ|દંડની\s+રકમ)\s*(?:ભરો|ચૂકવો|જમા\s+કરો)"
        r"|₹\s*[\d,૦-૯]+\s*(?:[^\s]+\s+){0,3}(?:ફી|ચાર્જ)"
        r")"
    ),
    # Kannada - needs native-speaker review
    re.compile(
        r"(?:"
        r"(?:ನೋಂದಣಿ|ಪ್ರಕ್ರಿಯೆ|ಅರ್ಜಿ|ಫೈಲ್|ಭದ್ರತಾ|ಮರುಪಾವತಿಸಬಹುದಾದ|ದಂಡದ)\s*(?:ಶುಲ್ಕ|ಹಣ|ಮೊತ್ತ)"
        r"|(?:ಶುಲ್ಕ|ದಂಡದ\s+ಮೊತ್ತ)\s*(?:ಪಾವತಿಸಿ|ಭರಿಸಿ|ಜಮೆ\s+ಮಾಡಿ)"
        r"|₹\s*[\d,೦-೯]+\s*(?:[^\s]+\s+){0,3}(?:ಶುಲ್ಕ|ಹಣ|ಮೊತ್ತ)"
        r")"
    ),
    # Malayalam - needs native-speaker review
    re.compile(
        r"(?:"
        r"(?:രജിസ്ട്രേഷൻ|പ്രോസസ്സിംഗ്|അപേക്ഷ|ഫയൽ|സെക്യൂരിറ്റി|തിരിച്ചടക്കാവുന്ന|പിഴ)\s*(?:ഫീസ്|തുക)"
        r"|(?:ഫീസ്|പിഴത്തുക)\s*(?:അടയ്ക്കുക|നൽകുക|നിക്ഷേപിക്കുക)"
        r"|₹\s*[\d,൦-൯]+\s*(?:[^\s]+\s+){0,3}(?:ഫീസ്|തുക)"
        r")"
    ),
    # Punjabi - needs native-speaker review
    re.compile(
        r"(?:"
        r"(?:ਰਜਿਸਟ੍ਰੇਸ਼ਨ|ਪ੍ਰੋਸੈਸਿੰਗ|ਅਰਜ਼ੀ|ਫਾਈਲ|ਸੁਰੱਖਿਆ|ਵਾਪਸੀਯੋਗ|ਜੁਰਮਾਨਾ)\s*(?:ਫੀਸ|ਖਰਚਾ|ਰਕਮ)"
        r"|(?:ਫੀਸ|ਜੁਰਮਾਨੇ\s+ਦੀ\s+ਰਕਮ)\s*(?:ਭਰੋ|ਅਦਾ\s+ਕਰੋ|ਜਮ੍ਹਾਂ\s+ਕਰੋ)"
        r"|₹\s*[\d,੦-੯]+\s*(?:[^\s]+\s+){0,3}(?:ਫੀਸ|ਖਰਚਾ|ਰਕਮ)"
        r")"
    ),
    # Odia - needs native-speaker review
    re.compile(
        r"(?:"
        r"(?:ପଞ୍ଜୀକରଣ|ପ୍ରୋସେସିଂ|ଆବେଦନ|ଫାଇଲ|ସୁରକ୍ଷା|ଫେରସ୍ତଯୋଗ୍ୟ|ଜରିମାନା)\s*(?:ଫି|ଶୁଳ୍କ|ଚାର୍ଜ|ରାଶି)"
        r"|(?:ଫି|ଶୁଳ୍କ|ଜରିମାନା\s+ରାଶି)\s*(?:ପୈଠ\s+କରନ୍ତୁ|ଦିଅନ୍ତୁ|ଦାଖଲ\s+କରନ୍ତୁ)"
        r"|₹\s*[\d,୦-୯]+\s*(?:[^\s]+\s+){0,3}(?:ଫି|ଶୁଳ୍କ|ରାଶି)"
        r")"
    ),
    # Urdu - needs native-speaker review
    re.compile(
        r"(?:"
        r"(?:رجسٹریشن|پروسیسنگ|درخواست|فائل|سیکیورٹی|قابلِ\s*واپسی|جرمانہ)\s*(?:فیس|چارجز|رقم)"
        r"|(?:فیس|جرمانے\s*کی\s*رقم)\s*(?:ادا\s*کریں|جمع\s*کرائیں|دیں)"
        r"|₹\s*[\d,۰-۹]+\s*(?:[^\s]+\s+){0,3}(?:فیس|رقم)"
        r")"
    ),
]

# Negation patterns that suppress fee_demand only when directly modifying the fee word
# NOTE: Lists for gu, kn, ml, pa, or, ur - needs native-speaker review
FEE_NEGATION_RE = re.compile(
    r"(?i)(?:"
    r"\bno\s+(?:registration\s+|processing\s+|application\s+|entry\s+|participation\s+)?(?:fee|fees|charge|charges)\b"
    r"|\b(?:fee|fees|charge|charges)\s+(?:is|are)?\s*(?:free|nil|zero|exempted|waived|not\s+applicable)\b"
    r"|\bfee-free\b"
    r"|\bfree\s+of\s+(?:cost|charge)\b"
    r"|\bwithout\s+(?:any\s+)?(?:fee|fees|charge|charges)\b"
    r"|\bnot\s+required\s+to\s+pay\b"
    r"|\bneed\s+not\s+pay\b"
    r"|\b(?:fee|fees|charge)\s+nahi\b"
    r"|\bkoi\s+(?:bhi\s+)?(?:fee|fees|charge)\s+nahi\b"
    r"|कोई\s+(?:पंजीकरण\s+|आवेदन\s+)?(?:शुल्क|फीस|चार्ज)\s+नहीं"
    r"|(?:शुल्क|फीस|चार्ज)\s+(?:नहीं|माफ|शून्य|देय\s+नहीं)"
    r"|(?:पंजीकरण|आवेदन)\s+(?:मुफ्त|निःशुल्क|नि:शुल्क)"
    r"|निःशुल्क|नि:शुल्क"
    r"|कोणतेही\s+(?:नोंदणी\s+)?शुल्क\s+नाही"
    r"|शुल्क\s+(?:नाही|माफ|शून्य)"
    r"|(?:नोंदणी|अर्ज)\s+(?:मोफत|विनामूल्य)"
    r"|विनामूल्य"
    r"|কোনো\s+(?:রেজিস্ট্রেশন\s+)?(?:ফি|চার্জ)\s+নেই"
    r"|(?:ফি|চার্জ)\s+(?:নেই|মকুব|শূন্য)"
    r"|(?:রেজিস্ট্রেশন|আবেদন)\s+বিনামূল্যে"
    r"|বিনামূল্যে"
    r"|(?:பதிவுக்\s+|விண்ணப்பக்\s+)?கட்டணம்\s+இல்லை"
    r"|கட்டணமின்றி"
    r"|(?:பதிவு|விண்ணப்பம்)\s+இலவசம்"
    r"|ఎలాంటి\s+(?:రిజిస్ట్రేషన్\s+)?(?:రుసుము|ఫీజు)\s+లేదు"
    r"|(?:రుసుము|ఫీజు)\s+లేదు"
    r"|(?:రిజిస్ట్రేషన్|దరఖాస్తు)\s+ఉచితం"
    r"|કોઈ\s+(?:નોંધણી\s+)?ફી\s+નથી"
    r"|ફી\s+નથી"
    r"|(?:નોંધણી|અરજી)\s+મફત"
    r"|વિનામૂલ્યે"
    r"|ಯಾವುದೇ\s+(?:ನೋಂದಣಿ\s+)?ಶುಲ್ಕವಿಲ್ಲ"
    r"|ಶುಲ್ಕವಿಲ್ಲ"
    r"|(?:ನೋಂದಣಿ|ಅರ್ಜಿ)\s+ಉಚಿತ"
    r"|യാതൊരു\s+(?:രജിസ്ട്രേഷൻ\s+)?ഫീസും\s+ഇല്ല"
    r"|ഫീസില്ല"
    r"|(?:രജിസ്ട്രേഷൻ|അപേക്ഷ)\s+സൗജന്യമാണ്"
    r"|സൗജന്യ\s+രജിസ്ട്രേഷൻ"
    r"|ਕੋਈ\s+(?:ਰਜਿਸਟ੍ਰੇਸ਼ਨ\s+)?ਫੀਸ\s+ਨਹੀਂ"
    r"|ਫੀਸ\s+ਨਹੀਂ"
    r"|(?:ਰਜਿਸਟ੍ਰੇਸ਼ਨ|ਦਾਖਲਾ)\s+ਮੁਫ਼ਤ"
    r"|କୌଣସି\s+(?:ପଞ୍ଜୀକରଣ\s+)?ଫି\s+ନାହିଁ"
    r"|ଫି\s+ନାହିଁ"
    r"|(?:ପଞ୍ଜୀକରଣ|ଆବେଦନ)\s+ମାଗଣା"
    r"|ବିନାମୂଲ୍ୟରେ"
    r"|کوئی\s+(?:رجسٹریشن\s+)?فیس\s+نہیں"
    r"|فیس\s+نہیں"
    r"|(?:رجسٹریشن|داخلہ)\s+مفت"
    r"|بلا\s+معاوضہ"
    r")"
)

# Urgency / threat patterns across all SUPPORTED_LANGS
# NOTE: Lists for gu, kn, ml, pa, or, ur - needs native-speaker review
URGENCY_THREAT_PATTERNS: list[re.Pattern[str]] = [
    # English & Hinglish
    re.compile(
        r"\b(?:"
        r"within\s+(?:24|48|12|two|one)\s*(?:hours?|hrs?)"
        r"|within\s+one\s+hour"
        r"|(?:24|48)\s*(?:hours?|hrs?|ghante)\s+(?:me|mein)"
        r"|arrest\s+warrant"
        r"|digital\s+arrest"
        r"|avoid\s+arrest"
        r"|warna\s+arrest"
        r"|(?:SIM|account)\s+will\s+be\s+(?:blocked|suspended|disconnected|frozen)"
        r"|(?:SIM|account)\s+(?:aaj\s+)?block\s+ho\s+jayega"
        r"|disconnection\s+tonight"
        r"|from\s+12\s+midnight\s+tonight"
        r"|aaj\s+raat\s+12\s+baje\s+se"
        r"|share\s+before\s+it\s+is\s+deleted"
        r"|delete\s+hone\s+se\s+pehle\s+share"
        r"|click\s+the\s+link\s+below\s+to\s+download\s+[^\n.]{0,40}\s+immediately"
        r"|update\s+now\s+using\s+the\s+link\s+to\s+avoid\s+suspension"
        r"|failing\s+which\s+[^\n.]{0,50}(?:cancelled|suspended|blocked|forfeited|penal|legal\s+action)"
        r"|failure\s+to\s+respond\s+within\s+\d+\s+hours"
        r"|strict\s+(?:legal|penal|disciplinary)\s+action\s+within\s+24"
        r")\b",
        re.IGNORECASE,
    ),
    # Hindi (Devanagari)
    re.compile(
        r"(?:"
        r"24\s*घंटे\s*(?:के\s*भीतर|में)"
        r"|गिरफ्तारी\s*वारंट"
        r"|गिरफ्तारी\s*से\s*बचने"
        r"|(?:सिम|बैंक\s*खाता)\s*ब्लॉक\s*(?:हो\s*जाएगा|कर\s*दिया\s*जाएगा)"
        r"|आज\s*रात\s*12\s*बजे\s*से"
        r"|डिलीट\s*होने\s*से\s*पहले\s*शेयर"
        r"|निलंबन\s*से\s*बचने\s*के\s*लिए\s*लिंक\s*से\s*अभी"
        r"|तुरंत\s*डाउनलोड\s*करने\s*के\s*लिए\s*नीचे\s*दिए\s*लिंक"
        r")"
    ),
    # Marathi
    re.compile(
        r"(?:"
        r"24\s*तासांत"
        r"|अटक\s*वॉरंट"
        r"|अटक\s*टाळण्यासाठी"
        r"|(?:सिम|बँक\s*खाते)\s*ब्लॉक\s*(?:होईल|केले\s*जाईल)"
        r"|आज\s*रात्री\s*12\s*वाजल्यापासून"
        r"|डिलीट\s*होण्यापूर्वी\s*शेअर"
        r"|निलंबन\s*टाळण्यासाठी\s*लिंकवरून\s*आत्ताच"
        r"|त्वरित\s*डाउनलोड\s*करण्यासाठी\s*खालील\s*लिंकवर"
        r")"
    ),
    # Bengali
    re.compile(
        r"(?:"
        r"(?:২৪|24)\s*ঘণ্টার\s*মধ্যে"
        r"|গ্রেফতারি\s*পরোয়ানা"
        r"|গ্রেফতার\s*এড়াতে"
        r"|(?:সিম|ব্যাংক\s*অ্যাকাউন্ট)\s*ব্লক\s*(?:হয়ে\s*যাবে|করে\s*দেওয়া\s*হবে)"
        r"|আজ\s*রাত\s*১২টা\s*থেকে"
        r"|মুছে\s*ফেলার\s*আগে\s*শেয়ার"
        r"|স্থগিতাদেশ\s*এড়াতে\s*লিংক\s*থেকে\s*এখনই"
        r"|এখনই\s*[^\n।]{0,40}\s*ডাউনলোড\s*করতে\s*নিচের\s*লিংকে"
        r")"
    ),
    # Tamil
    re.compile(
        r"(?:"
        r"24\s*மணி\s*நேரத்தி(?:ல்|ற்குள்)"
        r"|கைது\s*வாரண்ட்"
        r"|கைதைத்\s*தவிர்க்க"
        r"|(?:சிம்|வங்கிக்\s*கணக்கு)\s*முடக்கப்படும்"
        r"|இன்று\s*நள்ளிரவு\s*12\s*மணி\s*முதல்"
        r"|நீக்கப்படும்\s*முன்\s*பகிருங்கள்"
        r"|இடைநீக்கத்தைத்\s*தவிர்க்க\s*இணைப்பில்\s*இப்போதே"
        r"|உடனே\s*பதிவிறக்க\s*கீழே\s*உள்ள\s*இணைப்பைக்"
        r")"
    ),
    # Telugu
    re.compile(
        r"(?:"
        r"24\s*గంట(?:ల్లో|ల్లోగా)"
        r"|అరెస్ట్\s*వారెంట్"
        r"|అరెస్ట్\s*నివారించడానికి"
        r"|(?:సిమ్|బ్యాంక్\s*ఖాతా)\s*బ్లాక్\s*(?:అవుతుంది|చేయబడుతుంది)"
        r"|ఈ\s*రాత్రి\s*12\s*గంటల\s*నుంచి"
        r"|తొలగించే\s*ముందే\s*షేర్"
        r"|నిలిపివేతను\s*నివారించడానికి\s*లింక్\s*ద్వారా\s*ఇప్పుడే"
        r"|వెంటనే\s*డೌన్‌లోడ్\s*చేయడానికి\s*కింది\s*లింక్"
        r")"
    ),
    # Gujarati - needs native-speaker review
    re.compile(
        r"(?:"
        r"24\s*કલાક(?:માં|ની\s*અંદર)"
        r"|ધરપકડ\s*વોરંટ"
        r"|ધરપકડથી\s*બચવા"
        r"|(?:સિમ|બેંક\s*ખાતું)\s*બ્લોક"
        r"|આજે\s*રાત્રે\s*12\s*વાગ્યાથી"
        r"|કાઢી\s*નાખવામાં\s*આવે\s*તે\s*પહેલાં\s*શેર"
        r")"
    ),
    # Kannada - needs native-speaker review
    re.compile(
        r"(?:"
        r"24\s*ಗಂಟೆ(?:ಗಳಲ್ಲಿ|ಯೊಳಗೆ)"
        r"|ಬಂಧನ\s*ವಾರಂಟ್"
        r"|ಬಂಧನದಿಂದ\s*ತಪ್ಪಿಸಿಕೊಳ್ಳಲು"
        r"|(?:ಸಿಮ್|ಬ್ಯಾಂಕ್\s*ಖಾತೆ)\s*ಬ್ಲಾಕ್"
        r"|ಇಂದು\s*ರಾತ್ರಿ\s*12\s*ಗಂಟೆಯಿಂದ"
        r"|ಅಳಿಸುವ\s*ಮೊದಲು\s*ಹಂಚಿಕೊಳ್ಳಿ"
        r")"
    ),
    # Malayalam - needs native-speaker review
    re.compile(
        r"(?:"
        r"24\s*മണിക്കൂറിനകം"
        r"|അറസ്റ്റ്\s*വാറണ്ട്"
        r"|അറസ്റ്റ്\s*ഒഴിവാക്കാൻ"
        r"|(?:സിം|ബാങ്ക്\s*അക്കൗണ്ട്)\s*ബ്ലോക്ക്"
        r"|ഇന്ന്\s*രാത്രി\s*12\s*മണി\s*മുതൽ"
        r"|ഡിലീറ്റ്\s*ചെയ്യുന്നതിന്\s*മുമ്പ്\s*പങ്കിടുക"
        r")"
    ),
    # Punjabi - needs native-speaker review
    re.compile(
        r"(?:"
        r"24\s*ਘੰਟਿਆਂ\s*(?:ਦੇ\s*ਅੰਦਰ|ਵਿੱਚ)"
        r"|ਗ੍ਰਿਫ਼ਤਾਰੀ\s*ਵਾਰੰਟ"
        r"|ਗ੍ਰਿਫ਼ਤਾਰੀ\s*ਤੋਂ\s*ਬਚਣ"
        r"|(?:ਸਿਮ|ਬੈਂਕ\s*ਖਾਤਾ)\s*ਬਲਾਕ"
        r"|ਅੱਜ\s*ਰਾਤ\s*12\s*ਵਜੇ\s*ਤੋਂ"
        r"|ਮਿਟਾਉਣ\s*ਤੋਂ\s*ਪਹਿਲਾਂ\s*ਸ਼ੇਅਰ"
        r")"
    ),
    # Odia - needs native-speaker review
    re.compile(
        r"(?:"
        r"24\s*ଘଣ୍ଟା\s*(?:ମଧ୍ୟରେ|ଭିତରେ)"
        r"|ଗିରଫ\s*ୱାରେଣ୍ଟ"
        r"|ଗିରଫରୁ\s*ବର୍ତ୍ତିବା"
        r"|(?:ସିମ୍|ବ୍ୟାଙ୍କ\s*ଖାତା)\s*ବ୍ଲକ"
        r"|ଆଜି\s*ରାତି\s*12\s*ଟାରୁ"
        r"|ଡିଲିଟ୍\s*ହେବା\s*ପୂର୍ବରୁ\s*ଶେୟାର"
        r")"
    ),
    # Urdu - needs native-speaker review
    re.compile(
        r"(?:"
        r"24\s*گھنٹوں\s*(?:کے\s*اندر|میں)"
        r"|وارنٹ\s*گرفتاری"
        r"|گرفتاری\s*سے\s*بچنے"
        r"|(?:سم|بینک\s*اکاؤنٹ)\s*بلاک"
        r"|آج\s*رات\s*12\s*بجے\s*سے"
        r"|ڈیلیٹ\s*ہونے\s*سے\s*پہلے\s*شیئر"
        r")"
    ),
]

# Too-good-to-be-true offer patterns across all SUPPORTED_LANGS
# NOTE: Lists for gu, kn, ml, pa, or, ur - needs native-speaker review
TOO_GOOD_OFFER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"\b(?:"
        r"(?:(?:offering|giving|distributing)\s+)?free\s+laptops?(?:\s+for\s+all\s+students)?"
        r"|PM\s+Free\s+Laptop\s+Yojana"
        r"|free\s+(?:gas\s+cylinder|lpg\s+cylinder|cylinder)"
        r"|free\s+(?:mobile\s+)?recharge"
        r"|(?:free\s+)?5G\s+(?:mobile\s+)?tower"
        r"|muft\s+(?:laptop|recharge|cylinder|gas\s+cylinder)"
        r"|(?:old\s+coins\s+selected|give\s+Rs\.?\s*\d+\s*lakh\s+for\s+old\s+coins|purane\s+sikke\s+ke\s+badle)"
        r"|(?:5G\s+(?:mobile\s+)?tower\s+on\s+your\s+land|5G\s+tower\s+lagane\s+ki\s+permission)"
        r"|(?:monthly\s+rent\s+Rs\.?\s*[\d,]+\s*\+\s*advance\s+Rs\.?\s*\d+\s*lakh)"
        r"|(?:selected\s+beneficiaries\s+will\s+receive\s+(?:Rs\.?|INR|₹)\s*[\d,]+)"
        r"|(?:loan\s+of\s+(?:Rs\.?|₹)\s*[\d,]+\s+is\s+APPROVED)"
        r"|(?:LPG\s+Gas\s+Agency\s+Distributorship\s+is\s+APPROVED)"
        r"|(?:lottery|bumper\s+prize|cash\s+reward\s+of\s+(?:Rs\.?|₹)|unclaimed\s+(?:compensation|grant|subsidy|fund))"
        r"|(?:100%\s+subsidy|50%\s+subsidy\s+on\s+loan|direct\s+recruitment\s+without\s+exam)"
        r")\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:"
        r"(?:(?:मुफ्त|फ्री)\s+लैपटॉप)"
        r"|(?:(?:मोफत|फ्री)\s+लॅपटॉप)"
        r"|(?:(?:বিনামূল্যে|ফ্রি)\s+ল্যাপটপ)"
        r"|(?:இலவச\s+மடிக்கணினி)"
        r"|(?:ఉచిత\s+ల్యాప్‌టాప్)"
        r"|(?:મફત\s+લેપટોપ)"
        r"|(?:ಉಚಿತ\s+ಲ್ಯಾಪ್ಟಾಪ್)"
        r"|(?:സൗജന്യ\s+ലാപ്‌ടോപ്പ്)"
        r"|(?:ਮੁਫ਼ਤ\s+ਲੈਪਟਾਪ)"
        r"|(?:ମାଗଣା\s+ଲାପଟପ୍)"
        r"|(?:مفت\s+لیپ\s*ٹاپ)"
        r"|(?:(?:मुफ्त|फ्री)\s+(?:गैस\s+सिलेंडर|सिलेंडर|एलपीजी\s+सिलेंडर))"
        r"|(?:(?:मोफत|फ्री)\s+(?:गॅस\s+सिलिंडर|सिलिंडर))"
        r"|(?:(?:বিনামূল্যে|ফ্রি)\s+(?:গ্যাস\s+সিলিন্ডার|সিলিন্ডার))"
        r"|(?:இலவச\s+(?:எரிவாயு\s+சிலிண்டர்|சிலிண்டர்))"
        r"|(?:ఉచిత\s+(?:గ్యాస్\s+సిలిండర్|సిలిండర్))"
        r"|(?:મફત\s+(?:ગેસ\s+સિલિન્ડર|સિલિન્ડર))"
        r"|(?:ಉಚಿತ\s+(?:ಗ್ಯಾಸ್\s+ಸಿಲಿಂಡರ್|ಸಿಲಿಂಡರ್))"
        r"|(?:സൗജന്യ\s+(?:ഗ്യാസ്\s+സിലിണ്ടർ|സിലിണ്ടർ))"
        r"|(?:ਮੁਫ਼ਤ\s+(?:ਗੈਸ\s+ਸਿਲੰਡਰ|ਸਿਲੰਡਰ))"
        r"|(?:ମାଗଣା\s+(?:ଗ୍ୟାସ\s+ସିଲିଣ୍ଡର|ସିଲିଣ୍ଡର))"
        r"|(?:مفت\s+(?:گیس\s+سلنڈر|سلنڈر))"
        r"|(?:(?:मुफ्त|फ्री)\s+(?:मोबाइल\s+)?रिचार्ज)"
        r"|(?:(?:मोफत|फ्री)\s+(?:मोबाइल\s+)?रिचार्ज)"
        r"|(?:(?:বিনামূল্যে|ফ্রি)\s+(?:মোবাইল\s+)?রিচার্জ)"
        r"|(?:இலவச\s+(?:மொபைல்\s+)?ரீசார்ஜ்)"
        r"|(?:ఉచిత\s+(?:మొబైల్\s+)?రీఛార్జ్)"
        r"|(?:મફત\s+(?:મોબાઇલ\s+)?રિચાર્જ)"
        r"|(?:ಉಚಿತ\s+(?:ಮೊಬೈಲ್\s+)?ರೀಚಾರ್ಜ್)"
        r"|(?:സൗജന്യ\s+(?:മൊബൈൽ\s+)?റീചാർജ്)"
        r"|(?:ਮੁਫ਼ਤ\s+(?:ਮੋਬਾਈਲ\s+)?ਰੀਚਾਰਜ)"
        r"|(?:ମାଗଣା\s+(?:ମୋବାଇଲ୍\s+)?ରିଚାର୍ଜ)"
        r"|(?:مفت\s+(?:موبائل\s+)?ریچارج)"
        r"|(?:पुराने\s+सिक्कों\s+के\s+बदले|जुन्या\s+नाण्यांच्या\s+बदल्यात|পুরনো\s+কয়েনের\s+বদলে|பழைய\s+நாணயங்களுக்கு|పాత\s+నాణేలకు\s+బదులుగా|જૂના\s+સિક્કા|ಹಳೆಯ\s+ನಾಣ್ಯ|പഴയ\s+നാണയങ്ങൾ|ਪੁਰਾਣੇ\s+ਸਿੱਕੇ|ପୁରୁଣା\s+ମୁଦ୍ରା|پرانے\s+سکے)"
        r"|(?:(?:मुफ्त\s+)?(?:5G|5जी)\s+(?:मोबाइल\s+)?टावर|5G\s+मोबाईल\s+टॉवर|5G\s+মোবাইল\s+টাওয়ার|5G\s+மொபைல்\s+டவர்|5G\s+మొబైల్\s+టవర్|5G\s+મોબાઇલ\s+ટાવર|5G\s+ಮೊಬೈಲ್\s+ಟವರ್|5G\s+മൊബൈൽ\s+ടവർ|5G\s+ਮੋਬਾਈਲ\s+ਟਾਵਰ|5G\s+ମୋବାଇଲ୍\s+ଟାୱାର|5G\s+موبائل\s+ٹاور)"
        r")"
    ),
]

# Glossary of official English terms for check (i) spelling_errors
OFFICIAL_TERM_GLOSSARY: tuple[str, ...] = (
    "government",
    "ministry",
    "department",
    "authority",
    "regulatory",
    "examination",
    "notification",
    "corrigendum",
    "secretariat",
    "commissioner",
    "directorate",
    "compliance",
    "recruitment",
    "certificate",
    "clarification",
    "supplementary",
    "provisional",
    "circular",
    "attention",
    "subject",
)

# Valid English words that happen to be edit distance 1 from a glossary word (never flag these!)
SPELLING_ALLOWLIST: frozenset[str] = frozenset(
    {
        "governments",
        "ministries",
        "departments",
        "authorities",
        "examinations",
        "notifications",
        "commissioners",
        "directorates",
        "recruitments",
        "certificates",
        "certificate",
        "clarifications",
        "provisionally",
        "governmental",
        "departmental",
        "ministerial",
        "authorise",
        "authorised",
        "authorize",
        "authorized",
        "regulation",
        "regulations",
        "regulator",
        "regulators",
        "director",
        "directors",
        "secretary",
        "secretaries",
        "commission",
        "commissions",
        "circulars",
        "subjects",
        "subjected",
        "training",
        "clarify",
        "chief",
        "truly",
        "account",
        "accounts",
    }
)

# Known explicit misspellings seen in fake notices & synthetic forgeries
KNOWN_MISSPELLINGS: dict[str, str] = {
    "goverment": "Government",
    "govrnment": "Government",
    "govenment": "Government",
    "ministy": "Ministry",
    "minstry": "Ministry",
    "departmant": "Department",
    "deparment": "Department",
    "authorty": "Authority",
    "authoriy": "Authority",
    "examiantion": "Examination",
    "examintion": "Examination",
    "notificaton": "Notification",
    "corrigendem": "Corrigendum",
    "circuler": "Circular",
    "subjet": "Subject",
    "attension": "Attention",
    "adviced": "advised",
    "calrify": "clarify",
    "instgram": "Instagram",
    "cheif": "Chief",
    "traning": "Training",
    "acount": "account",
    "truely": "truly",
    "regulatery": "Regulatory",
    "complaince": "Compliance",
    "secratary": "Secretary",
    "secretery": "Secretary",
    "commisioner": "Commissioner",
    "recrutment": "Recruitment",
    "suplementary": "Supplementary",
}


# PIB Fact-Check overlay & caption leakage line patterns (centralized in rules.py for Stage 2 pre-filtering)
PIB_OVERLAY_LINE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?i)(?:"
        r"#\s*PIBFactCheck"
        r"|\bPIB\s*Fact\s*Check\b"
        r"|@\s*PIBFactCheck"
        r"|[/\]\s*P[_ ]?IBFactCheck"
        r"|t\.me/PIB_FactCheck"
        r"|socialmedia@pib\.gov\.in"
        r"|factcheck@pib\.gov\.in"
        r"|87997\s*11259"
        r"|\bThis\s+letter\s+is\s+#?fake\b"
        r"|\bThe\s+letter\s+is\s+FAKE\b"
        r"|\bThis\s+letter\s+has\s+NOT\s+been\s+issued\s+by\b"
        r"|\bhas\s+not\s+been\s+issued\b"
        r"|\bpurported\b"
        r"|\bhas\s+clarified\b"
        r"|\bis\s+circulating\b"
        r"|\bis\s+being\s+circulated\b"
        r"|\bfake\s*/\s*fabricated\b"
        r"|#\s*FAKE\b"
        r"|\bFAKE\s+DOCUMENT\s+ALERT\b"
        r"|\bFAKE\s+NOTICE\s+ALERT\b"
        r"|\bFake\s+(?:letter|notice|claims)\b"
        r"|\bFollow\s+us\s+on\s+social\s+media\b"
        r"|\bqueries\s+here\b"
        r"|\bReport\s+suspicious\s+content\b"
        r"|\bDo\s+not\s+share\s+or\s+rely\s+on\s+unverified\b"
        r"|(?:फ़र्ज़ी|फर्जी|फ़र्ज़ी)\s+है"
        r"|यह\s+दावा\s+\S{0,8}[जज़]़?ी\s+है"  # OCR variants of फरजी in PIB caption
        r"|भ्रामक"
        r"|दावा\s+किया\s+जा\s+रहा"
        r"|द्वारा\s+(?:ऐसा\s+कोई\s+[^\n]*\s+)?जारी\s+नहीं\s+किया\s+गया"
        r"|ऐसा\s+कोई\s+(?:पत्र|नियुक्ति\s+पत्र)\s+(?:नहीं\s+भेजा|जारी\s+नहीं)"
        r"|संदिग्ध\s+जानकारी\s+यहाँ\s+साझा\s+करें?"
        r"|सोशल\s+मीडिया\s+पर\s+हम(?:ें)?\s+फ[ोॉौ]लो\s+करें?"
        r")"
    ),
    # Isolated stamp or banner tokens on their own line
    re.compile(
        r"^(?:[\W_]*)(?:"
        r"FAKE|FAKER|FAK|fake|FPIB|pib|FACT\s*CHECK|DOCUMENT\s*ALERT|BEWARE"
        r"|फ़र्ज़ी|फर्जी|फ़र्ज़ी"
        r")(?:[\W_]*)$",
        re.IGNORECASE,
    ),
]

# Approximate narrative keyword rules for assigning narrative_id to raw Telegram debunk posts
NARRATIVE_KEYWORD_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "NAR-MUDRA-LOAN",
        re.compile(r"(?i)(?:\bmudra\b|मुद्रा\s*योजना|प्रधानमंत्री\s*मुद्रा|mudra\s*loan|mudra\s*yojana)"),
    ),
    (
        "NAR-I4C-LETTER",
        re.compile(
            r"(?i)(?:\bI4C\b|Indian\s+Cyber\s+Crime\s+Coordination\s+Centre|भारतीय\s+साइबर\s+अपराध\s+समन्वय"
            r"|cyber\s+crime[^\n]{0,60}(?:arrest|child\s+pornography|illegal\s+content)|digital\s+arrest)"
        ),
    ),
    (
        "NAR-TRAI-TOWER",
        re.compile(
            r"(?i)(?:(?:mobile|5G|4G|telecom|BSNL|TRAI)\s+tower|टावर\s+लगाने|मोबाइल\s+टावर|tower\s+installation|tower\s+on\s+your\s+land)"
        ),
    ),
    (
        "NAR-BSNL-KYC",
        re.compile(
            r"(?i)(?:SIM\s+(?:card\s+)?(?:KYC|block|suspended|deactivat)|सिम\s+(?:कार्ड\s+)?(?:केवाईसी|ब्लॉक|बंद)|BSNL[^\n]{0,50}KYC|TRAI[^\n]{0,50}SIM)"
        ),
    ),
    (
        "NAR-FREE-LAPTOP",
        re.compile(
            r"(?i)(?:free\s+laptop|फ्री\s+लैपटॉप|मुफ्त\s+लैपटॉप|मोफत\s+लॅपटॉप|laptop\s+scheme|लैपटॉप\s+योजना)"
        ),
    ),
    (
        "NAR-RBI-PRIZE-EXCHANGE",
        re.compile(
            r"(?i)(?:old\s+coins?|पुराने\s+सिक्क|old\s+notes?|demonetis|lottery|lucky\s+draw|KBC|foreign\s+exchange\s+conversion\s+fee"
            r"|RBI[^\n]{0,60}(?:prize|lottery|award|exchange\s+facility|old\s+coin))"
        ),
    ),
    (
        "NAR-OMC-DEALERSHIP",
        re.compile(
            r"(?i)(?:LPG\s+(?:gas\s+)?(?:agency|dealership|distributorship)|एलपीजी|गैस\s+एजेंसी|डीलरशिप|डिस्ट्रीब्यूटरशिप"
            r"|petrol\s+pump\s+dealership|Ujjwala\s+gas\s+agency|Indane\s+gas\s+dealership)"
        ),
    ),
    (
        "NAR-SOLAR-SCHEME",
        re.compile(r"(?i)(?:\bKUSUM\b|PM-KUSUM|कुसुम\s+योजना|solar\s+pump|सोलर\s+पंप|rooftop\s+solar)"),
    ),
    (
        "NAR-EPAN-PHISHING",
        re.compile(r"(?i)(?:e-?PAN\s+card|ई-?पैन\s+कार्ड|download\s+your\s+e-?PAN)"),
    ),
    (
        "NAR-TAX-REFUND",
        re.compile(r"(?i)(?:income\s+tax\s+refund|आयकर\s+रिफंड|tax\s+refund\s+of\s+Rs)"),
    ),
    (
        "NAR-BANK-KYC-BLOCK",
        re.compile(
            r"(?i)(?:bank\s+account\s+will\s+be\s+(?:blocked|suspended|frozen)|बैंक\s+खाता\s+(?:ब्लॉक|बंद)"
            r"|(?:SBI|PAN|Aadhaar|YONO)[^\n]{0,50}(?:account|खाता)[^\n]{0,50}(?:blocked|suspended|update|ब्लॉक|बंद))"
        ),
    ),
    (
        "NAR-UTILITY-DISCONNECT",
        re.compile(r"(?i)(?:electricity\s+(?:bill|will\s+be\s+disconnected|power\s+cut)|बिजली\s+(?:का\s+बिल|काट\s+दी\s+जाएगी|कनेक्शन))"),
    ),
    (
        "NAR-COURT-NOTICE",
        re.compile(
            r"(?i)(?:Supreme\s+Court[^\n]{0,80}(?:Ministry\s+of\s+Finance|penalty|arrest|Financial\s+Transaction\s+Committee)"
            r"|सुप्रीम\s+कोर्ट[^\n]{0,80}(?:वित्त\s+मंत्रालय|जुर्माना|गिरफ्तारी)|सर्वोच्च\s+न्यायालय[^\n]{0,80}वित्त\s+मंत्रालय)"
        ),
    ),
    (
        "NAR-DEFENCE-FORGED-LETTER",
        re.compile(
            r"(?i)(?:Rafale|राफेल|IAF\s+Chief|वायुसेना\s+प्रमुख|(?:Army|Air\s+Force|Navy|Defence|Ministry\s+of\s+Commerce)[^\n]{0,80}(?:resign|leaked|suspension\s+of\s+trade))"
        ),
    ),
    (
        "NAR-EXAM-NOTICE",
        re.compile(
            r"(?i)(?:NEET-?PG|नीट-?पीजी|(?:NBE|NBEMS|NTA|CBSE|UGC|board\s+exam)[^\n]{0,60}(?:postponed|cancelled|rescheduled|स्थगित|रद्द))"
        ),
    ),
    (
        "NAR-JOB-FEE",
        re.compile(
            r"(?i)(?:appointment\s+letter|नियुक्ति\s+पत्र|recruitment[^\n]{0,60}(?:fee|charge)|भर्ती[^\n]{0,60}शुल्क"
            r"|Kaushal\s+Bharat|कौशल\s+भारत|Rojgar\s+Yojana|रोजगार\s+योजना|customer\s+service\s+representative)"
        ),
    ),
    (
        "NAR-POLICY-ORDER",
        re.compile(
            r"(?i)(?:petrol\s+(?:and|&)\s+diesel\s+price|पेट्रोल\s+और\s+डीजल|Productivity\s+Linked\s+Bonus|PLB|RBE\s+No"
            r"|टोल\s+प्लाजा|toll\s+plaza|Nursing\s+Officer|Gazette\s+of\s+India|amalgamat|licence\s+of\s+[^\n]{0,40}Bank)"
        ),
    ),
]


def infer_narrative_from_text(text: str) -> str | None:
    """Infer an approximate narrative_id from text using NARRATIVE_KEYWORD_RULES in rules.py."""
    if not text:
        return None
    for nar_id, pattern in NARRATIVE_KEYWORD_RULES:
        if pattern.search(text):
            return nar_id
    return None

# Rule 2(a): payment_to_account (critical) — payment/transfer instruction within 2 lines of an account/IFSC/A/c No.
# NOTE: Lists for gu, kn, ml, pa, or, ur - needs native-speaker review
PAYMENT_INSTRUCTION_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:pay|send|transfer|deposit|remit|credit)\b"
    r"|\b(?:must|is\s+required\s+to|are\s+required\s+to|directed\s+to|advised\s+to|need\s+to|allowed\s+to|kindly)\s+"
    r"(?:pay|send|transfer|deposit|submit|remit)\b"
    r"|\b(?:NEFT|RTGS|IMPS|UPI)\b"
    r"|(?:(?:pay|send|transfer)\s+kare[n]?)"
    r"|(?:जमा\s+करें|जमा\s+करना\s+होगा|भुगतान\s+करें|ट्रांसफर\s+करें|अंतरित\s+करें|भेजें|भेजना\s+होगा|पे\s+करें)"
    r"|(?:जमा\s+करा|भरा|भरावी|पाठवा|पे\s+करा)"
    r"|(?:জমা\s+দিন|জমা\s+দিতে\s+হবে|পাঠান)"
    r"|(?:செலுத்துங்கள்|செலுத்த\s+வேண்டும்|அனுப்பவும்)"
    r"|(?:చెల్లించండి|జమ\s+చేయండి|చెల్లించాలి|పంపండి)"
    r"|(?:જમા\s+કરો|ચૂકવો|ટ્રાન્સફર\s+કરો|મોકલો)"
    r"|(?:ಪಾವತಿಸಿ|ಜಮೆ\s+ಮಾಡಿ|ವರ್ಗಾಯಿಸಿ|ಕಳುಹಿಸಿ)"
    r"|(?:അടയ്ക്കുക|നിക്ഷേപിക്കുക|കൈമാറുക|അയക്കുക)"
    r"|(?:ਜਮ੍ਹਾਂ\s+ਕਰੋ|ਅਦਾ\s+ਕਰੋ|ਭੇਜੋ)"
    r"|(?:ଦାଖଲ\s+କରନ୍ତୁ|ପୈଠ\s+କରନ୍ତୁ|ଜମା\s+କରନ୍ତୁ|ପଠାନ୍ତୁ)"
    r"|(?:جمع\s*کرائیں|منتقل\s*کریں|ادا\s*کریں|بھیجیں)"
    r")"
)

ACCOUNT_DETAIL_RE = re.compile(
    r"(?:"
    r"\b[A-Z]{4}0[A-Z0-9]{6}\b"
    r"|(?i:\b(?:A/c\s*(?:No\.?|Number|:|-)|Ac\.?\s*no\.?|Account\s*(?:No\.?|Number)|खाता\s*(?:संख्या|क्रमांक)|ખાતા\s*નંબર|ಖಾತೆ\s*ಸಂಖ್ಯೆ|അക്കൗണ്ട്\s*നമ്പർ|ਖਾਤਾ\s*ਨੰਬਰ|ଖାତା\s*ନମ୍ବର|اکاؤنٹ\s*نمبر)\s*[:\-]?\s*\d{9,18}\b)"
    r"|(?i:\b(?:savings?\s+account|type\s*:\s*saving|saving\s+account|बचत\s+खाता|બચત\s+ખાતું|ಉಳಿತಾಯ\s+ಖಾತೆ|സേവിംഗ്സ്\s+അക്കൗണ്ട്|ਬੱਚਤ\s+ਖਾਤਾ|ସଞ୍ଚୟ\s+ଖାତା|سیونگز\s+اکاؤنٹ)\b)"
    r"|(?i:\b(?:IFSC|IFC)\s*(?:Code)?\s*[:\-]?\s*[A-Z]{4}0[A-Z0-9]{6}\b)"
    r"|(?i:\b[a-zA-Z0-9.\-_]{2,64}@[a-zA-Z]{2,24}\b(?!\.[a-zA-Z]))"
    r")"
)

# Rule 2(b): Loan sanction offer addressed to an individual (not a circular to banks/institutions)
LOAN_SANCTION_OFFER_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:loan|mudra\s+loan|credit\s+facility)\b[^\n]{0,80}\b(?:approved|sanctioned|disbursed|verified)\b"
    r"|\b(?:approved|sanctioned|disbursed)\b[^\n]{0,80}\b(?:loan|mudra\s+loan)\b"
    r"|\bLoan\s+Approval\s+(?:Letter|No)\b"
    r"|\bEMI\s+and\s+Loan\s+Amount\s+Approved\b"
    r"|(?:लोन|ऋण|कर्ज)\s+[^\n]{0,50}(?:स्वीकृत|मंजूर)"
    r"|(?:ঋণ\s+মঞ্জুর|கடன்\s+அனுமதிக்கப்பட்டுள்ளது|రుణం\s+మంజూరైంది)"
    r")"
)

INDIVIDUAL_ADDRESSEE_RE = re.compile(
    r"(?i)(?:"
    r"\bDear\s+(?:Sir|Madam|Applicant|Beneficiar(?:y|ies)|Customer|Candidate|Mr\.?|Mrs\.?|Ms\.?|Shri|Smt\.?)\b"
    r"|\bDear\s*,\s*\n\s*[A-Z]"
    r"|\b(?:Applicant\s+Name|Beneficiary\s+Name|Customer\s+Name|Name\s*:\s*Mr/?Mrs)\b"
    r"|\b(?:your\s+application\s+for\s+(?:MUDRA\s+)?LOAN|your\s+(?:PM\s+Mudra\s+Yojana\s+)?loan\s+of)\b"
    r"|(?:प्रिय\s+(?:ग्राहक|आवेदक|लाभार्थी|महोदय)|आपका\s+[^\n]{0,30}(?:लोन|ऋण)|तुमचे\s+[^\n]{0,30}कर्ज|আপনার\s+[^\n]{0,30}ঋণ|உங்களுக்கு\s+[^\n]{0,30}கடன்|మీకు\s+[^\n]{0,30}రుణం)"
    r")"
)

INSTITUTIONAL_ADDRESSEE_RE = re.compile(
    r"(?i)(?:"
    r"\bAll\s+(?:Scheduled\s+Commercial\s+Banks|Commercial\s+Banks|Authorised\s+Dealer|Regional\s+Rural\s+Banks|Co-operative\s+Banks|NBFCs|Regulated\s+Entities|Banks\s+and\s+Financial\s+Institutions)\b"
    r"|\bMadam\s*/\s*Sir\b[^\n]*\n[^\n]*(?:Directions|Circular|Master\s+Direction|Prudential\s+Norms|Basel)"
    r")"
)


@lru_cache(maxsize=1)
def load_issuer_registry() -> dict[str, dict[str, Any]]:
    """Return mapping of issuer_id -> issuer entry (including synthetic issuers)."""
    registry: dict[str, dict[str, Any]] = {}
    if ISSUER_REGISTRY_PATH.exists():
        data = json.loads(ISSUER_REGISTRY_PATH.read_text(encoding="utf-8"))
        for entry in data.get("issuers", []):
            iid = entry.get("issuer_id")
            if iid:
                registry[iid] = entry
    for syn in SYNTHETIC_ISSUERS:
        registry[syn["issuer_id"]] = syn
    return registry


@lru_cache(maxsize=1)
def load_official_corpus_references() -> dict[str, dict[str, Any]]:
    """Return mapping of normalized reference number -> official document metadata from 02_official_source_corpus."""
    refs: dict[str, dict[str, Any]] = {}
    if not OFFICIAL_CORPUS_PATH.exists():
        return refs
    for line in OFFICIAL_CORPUS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        for key in ("reference_no", "department_ref"):
            val = doc.get(key)
            if val and isinstance(val, str):
                norm = re.sub(r"\s+", " ", val.strip()).upper()
                refs[norm] = doc
    return refs
