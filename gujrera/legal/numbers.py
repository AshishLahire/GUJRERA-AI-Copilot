"""Section and rule numbers said as words, as speech-to-text writes them: "धारा अठारह", "કલમ અઢાર",
"section eighteen" -> "धारा 18", "કલમ 18", "section 18". The RERA Act has 92 sections, so 1 to 99 is enough.

The Gujarati and Hindi words are the standard forms (with common spelling variants); a native speaker should
review them with the rest of the Gujarati and Hindi text."""

from __future__ import annotations

import re

_HI = """एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस
इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस
सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास
इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ
अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी
बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पंचानवे छियानवे
सत्तानवे अट्ठानवे निन्यानवे""".split()

_GU = """એક બે ત્રણ ચાર પાંચ છ સાત આઠ નવ દસ અગિયાર બાર તેર ચૌદ પંદર સોળ સત્તર અઢાર ઓગણીસ વીસ એકવીસ બાવીસ
તેવીસ ચોવીસ પચ્ચીસ છવ્વીસ સત્તાવીસ અઠ્ઠાવીસ ઓગણત્રીસ ત્રીસ એકત્રીસ બત્રીસ તેત્રીસ ચોત્રીસ પાંત્રીસ છત્રીસ
સાડત્રીસ આડત્રીસ ઓગણચાલીસ ચાલીસ એકતાળીસ બેતાળીસ તેતાળીસ ચુંમાળીસ પિસ્તાળીસ છેતાળીસ સુડતાળીસ અડતાળીસ
ઓગણપચાસ પચાસ એકાવન બાવન ત્રેપન ચોપન પંચાવન છપ્પન સત્તાવન અઠ્ઠાવન ઓગણસાઠ સાઠ એકસઠ બાસઠ ત્રેસઠ ચોસઠ પાંસઠ
છાસઠ સડસઠ અડસઠ ઓગણસિત્તેર સિત્તેર એકોતેર બોતેર તોતેર ચુમોતેર પંચોતેર છોતેર સિત્યોતેર ઇઠ્યોતેર ઓગણએંસી એંસી
એક્યાસી બ્યાસી ત્યાસી ચોર્યાસી પંચ્યાસી છ્યાસી સિત્યાસી ઇઠ્યાસી નેવ્યાસી નેવું એકાણું બાણું ત્રાણું ચોરાણું
પંચાણું છન્નું સત્તાણું અઠ્ઠાણું નવ્વાણું""".split()

# Spellings speech-to-text also writes
_HI_VARIANTS = {"पांच": 5, "छः": 6, "छे": 6, "नव": 9, "पन्द्रह": 15, "सतरह": 17, "अठ्ठारह": 18, "अठारा": 18,
                "उन्निस": 19, "अठाईस": 28, "अड़तिस": 38, "चालिस": 40, "पचपन": 55, "साठ": 60, "सत्तर": 70}
_GU_VARIANTS = {"અઢારમી": 18, "અગ્યાર": 11, "ચાલીસ": 40, "ચાળીસ": 40, "ઓગણીસમી": 19}

_EN_UNITS = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
            "seventeen eighteen nineteen".split()
_EN_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
            "ninety": 90}

WORDS: dict[str, int] = {}
WORDS.update({w: i + 1 for i, w in enumerate(_HI)})
WORDS.update({w: i + 1 for i, w in enumerate(_GU)})
WORDS.update(_HI_VARIANTS)
WORDS.update(_GU_VARIANTS)
WORDS.update({w: i + 1 for i, w in enumerate(_EN_UNITS)})
for _t, _v in _EN_TENS.items():
    WORDS[_t] = _v
    for _i, _u in enumerate(_EN_UNITS[:9]):
        WORDS[f"{_t}-{_u}"] = WORDS[f"{_t} {_u}"] = _v + _i + 1

_LEAD = r"(\bsection|\bsec\.?|\brule|કલમ|નિયમ|धारा|नियम)"
_NUM_WORDS = "|".join(sorted(map(re.escape, WORDS), key=len, reverse=True))
_SPOKEN = re.compile(rf"{_LEAD}\s*(?:no\.?\s*|number\s*|નંબર\s*|नंबर\s*)?({_NUM_WORDS})(?![\wऀ-ॿ઀-૿])",
                     re.IGNORECASE)


def spoken_numbers(text: str) -> str:
    """Replace a section or rule number said as a word with its digits; anything else is left as it is."""
    return _SPOKEN.sub(lambda m: f"{m.group(1)} {WORDS[m.group(2).lower()]}", text or "")
