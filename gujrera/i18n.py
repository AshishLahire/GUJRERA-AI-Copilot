"""Answer templates in Gujarati, Hindi and English.

Every factual sentence the copilot says is one of these templates filled with
registry values, so answers can never contain facts that are not in the
records. The Gujarati and Hindi strings need a native-speaker review before
any public pilot.
"""

from __future__ import annotations

from datetime import date

LANGS = ("gu", "hi", "en")

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
    "gu": ["જાન્યુઆરી", "ફેબ્રુઆરી", "માર્ચ", "એપ્રિલ", "મે", "જૂન", "જુલાઈ", "ઓગસ્ટ", "સપ્ટેમ્બર",
           "ઓક્ટોબર", "નવેમ્બર", "ડિસેમ્બર"],
    "hi": ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
           "नवंबर", "दिसंबर"],
}

WORDS = {
    # project status
    "ongoing": {"en": "ongoing", "gu": "ચાલુ", "hi": "चालू"},
    "completed": {"en": "completed", "gu": "પૂર્ણ", "hi": "पूर्ण"},
    "lapsed": {"en": "lapsed", "gu": "મુદત પૂરી થયેલ", "hi": "व्यपगत"},
    "revoked": {"en": "revoked", "gu": "રદ", "hi": "रद्द"},
    # districts
    "Ahmedabad": {"en": "Ahmedabad", "gu": "અમદાવાદ", "hi": "अहमदाबाद"},
    "Surat": {"en": "Surat", "gu": "સુરત", "hi": "सूरत"},
    "Vadodara": {"en": "Vadodara", "gu": "વડોદરા", "hi": "वडोदरा"},
    "Rajkot": {"en": "Rajkot", "gu": "રાજકોટ", "hi": "राजकोट"},
    "Gandhinagar": {"en": "Gandhinagar", "gu": "ગાંધીનગર", "hi": "गांधीनगर"},
    "Bhavnagar": {"en": "Bhavnagar", "gu": "ભાવનગર", "hi": "भावनगर"},
    # project type
    "residential": {"en": "residential", "gu": "રહેણાંક", "hi": "आवासीय"},
    "commercial": {"en": "commercial", "gu": "વાણિજ્યિક", "hi": "वाणिज्यिक"},
    "mixed": {"en": "mixed-use", "gu": "મિશ્ર ઉપયોગ", "hi": "मिश्रित उपयोग"},
    "plotted": {"en": "plotted", "gu": "પ્લોટિંગ", "hi": "प्लॉटिंग"},
    # approvals
    "layout_plan": {"en": "layout plan", "gu": "લેઆઉટ પ્લાન", "hi": "लेआउट प्लान"},
    "building_permission": {"en": "building permission", "gu": "બાંધકામ પરવાનગી", "hi": "भवन अनुमति"},
    "non_agricultural": {"en": "NA permission", "gu": "બિનખેતી પરવાનગી", "hi": "गैर-कृषि अनुमति"},
    "fire_noc": {"en": "fire NOC", "gu": "ફાયર NOC", "hi": "फायर NOC"},
    "environment_clearance": {"en": "environment clearance", "gu": "પર્યાવરણ મંજૂરી", "hi": "पर्यावरण मंजूरी"},
}

T: dict[str, dict[str, str]] = {
    # ---- project
    "project_intro": {
        "en": "{name} is a {ptype} project by {promoter} in {district}, registered as {rera}.",
        "gu": "{name} એ {district}માં {promoter} નો {ptype} પ્રોજેક્ટ છે, નોંધણી નંબર {rera}.",
        "hi": "{name} {district} में {promoter} का {ptype} प्रोजेक्ट है, पंजीकरण संख्या {rera}।",
    },
    "project_status": {
        "en": "Registration status: {status}, valid until {valid}.",
        "gu": "નોંધણીની સ્થિતિ: {status}, {valid} સુધી માન્ય.",
        "hi": "पंजीकरण की स्थिति: {status}, {valid} तक मान्य।",
    },
    "completion_date": {
        "en": "As per the RERA registration, the completion date is {date}.",
        "gu": "RERA નોંધણી મુજબ પૂર્ણ થવાની તારીખ {date} છે.",
        "hi": "RERA पंजीकरण के अनुसार पूरा होने की तारीख {date} है।",
    },
    "completion_extended": {
        "en": "The original completion date was {orig}; it was extended to {revised}.",
        "gu": "મૂળ પૂર્ણ થવાની તારીખ {orig} હતી; તે {revised} સુધી લંબાવવામાં આવી.",
        "hi": "मूल समापन तिथि {orig} थी; इसे {revised} तक बढ़ाया गया।",
    },
    "completed_on": {
        "en": "The project was completed on {date}.",
        "gu": "પ્રોજેક્ટ {date} ના રોજ પૂર્ણ થયો.",
        "hi": "प्रोजेक्ट {date} को पूरा हुआ।",
    },
    "delay": {
        "en": "It is {days} days behind its original completion date.",
        "gu": "તે મૂળ પૂર્ણ થવાની તારીખથી {days} દિવસ પાછળ છે.",
        "hi": "यह मूल समापन तिथि से {days} दिन पीछे है।",
    },
    "progress": {
        "en": "Latest quarterly progress report ({quarter}): {pct}% complete.",
        "gu": "છેલ્લો ત્રિમાસિક પ્રગતિ અહેવાલ ({quarter}): {pct}% પૂર્ણ.",
        "hi": "नवीनतम तिमाही प्रगति रिपोर्ट ({quarter}): {pct}% पूर्ण।",
    },
    "qpr_missed": {
        "en": "{n} quarterly progress reports were not filed.",
        "gu": "{n} ત્રિમાસિક પ્રગતિ અહેવાલ ફાઈલ થયા નથી.",
        "hi": "{n} तिमाही प्रगति रिपोर्ट दाखिल नहीं की गईं।",
    },
    "approvals_pending": {
        "en": "Pending approvals: {items}.",
        "gu": "બાકી મંજૂરીઓ: {items}.",
        "hi": "लंबित अनुमोदन: {items}।",
    },
    "complaints": {
        "en": "{total} complaints have been filed, {open} of them still open.",
        "gu": "{total} ફરિયાદો નોંધાઈ છે, જેમાંથી {open} હજુ ખુલ્લી છે.",
        "hi": "{total} शिकायतें दर्ज हुई हैं, जिनमें से {open} अभी लंबित हैं।",
    },
    "no_complaints": {
        "en": "No complaints are on record.",
        "gu": "કોઈ ફરિયાદ રેકોર્ડ પર નથી.",
        "hi": "कोई शिकायत रिकॉर्ड पर नहीं है।",
    },
    # ---- promoter
    "promoter_intro": {
        "en": "{name} has {n} projects registered with GUJRERA ({ongoing} ongoing, {completed} completed).",
        "gu": "{name} ના GUJRERA માં {n} પ્રોજેક્ટ નોંધાયેલા છે ({ongoing} ચાલુ, {completed} પૂર્ણ).",
        "hi": "{name} के GUJRERA में {n} प्रोजेक्ट पंजीकृत हैं ({ongoing} चालू, {completed} पूर्ण)।",
    },
    "promoter_delayed": {
        "en": "{d} of them are behind their original completion date; the longest delay is {max} days.",
        "gu": "તેમાંથી {d} મૂળ તારીખથી પાછળ છે; સૌથી લાંબો વિલંબ {max} દિવસ છે.",
        "hi": "इनमें से {d} मूल तिथि से पीछे हैं; सबसे लंबी देरी {max} दिन है।",
    },
    "promoter_no_delay": {
        "en": "None of them are behind their original completion date.",
        "gu": "તેમાંથી કોઈ પણ મૂળ પૂર્ણ થવાની તારીખથી પાછળ નથી.",
        "hi": "इनमें से कोई भी मूल समापन तिथि से पीछे नहीं है।",
    },
    "promoter_complaints": {
        "en": "{total} complaints have been filed against its projects, {open} of them still open.",
        "gu": "તેના પ્રોજેક્ટ સામે {total} ફરિયાદો નોંધાઈ છે, જેમાંથી {open} હજુ ખુલ્લી છે.",
        "hi": "इसके प्रोजेक्ट्स के खिलाफ {total} शिकायतें दर्ज हुई हैं, जिनमें से {open} अभी लंबित हैं।",
    },
    "promoter_orders": {
        "en": "{n} show-cause, penalty or revocation orders are on record.",
        "gu": "{n} કારણદર્શક, દંડ અથવા રદ કરવાના આદેશ રેકોર્ડ પર છે.",
        "hi": "{n} कारण बताओ, दंड या रद्द करने के आदेश रिकॉर्ड पर हैं।",
    },
    "promoter_no_orders": {
        "en": "No show-cause, penalty or revocation orders are on record.",
        "gu": "કોઈ કારણદર્શક, દંડ અથવા રદ કરવાનો આદેશ રેકોર્ડ પર નથી.",
        "hi": "कोई कारण बताओ, दंड या रद्द करने का आदेश रिकॉर्ड पर नहीं है।",
    },
    "latest_order": {
        "en": "Latest order ({date}): {summary}",
        "gu": "છેલ્લો આદેશ ({date}): {summary}",
        "hi": "नवीनतम आदेश ({date}): {summary}",
    },
    # ---- agent
    "agent_status": {
        "en": "{name} is a GUJRERA-registered agent in {district}; registration {status}, valid until {valid}.",
        "gu": "{name} {district}માં GUJRERA નોંધાયેલ એજન્ટ છે; નોંધણી {status}, {valid} સુધી માન્ય.",
        "hi": "{name} {district} में GUJRERA पंजीकृत एजेंट हैं; पंजीकरण {status}, {valid} तक मान्य।",
    },
    # ---- conversation
    "not_found": {
        "en": "I could not find \"{q}\" in the GUJRERA records available to me.",
        "gu": "મને ઉપલબ્ધ GUJRERA રેકોર્ડમાં \"{q}\" મળ્યું નથી.",
        "hi": "मुझे उपलब्ध GUJRERA रिकॉर्ड में \"{q}\" नहीं मिला।",
    },
    "did_you_mean": {
        "en": "I couldn't find \"{q}\". Did you mean one of these?",
        "gu": "\"{q}\" મળ્યું નથી. શું તમે આમાંથી કોઈ વિશે પૂછો છો?",
        "hi": "\"{q}\" नहीं मिला। क्या आपका मतलब इनमें से कोई है?",
    },
    "need_entity": {
        "en": "Please tell me the project name, promoter name or RERA registration number.",
        "gu": "કૃપા કરીને પ્રોજેક્ટનું નામ, પ્રમોટરનું નામ અથવા RERA નોંધણી નંબર જણાવો.",
        "hi": "कृपया प्रोजेक्ट का नाम, प्रमोटर का नाम या RERA पंजीकरण संख्या बताइए।",
    },
    "disambiguate": {
        "en": "I found more than one match. Which one do you mean?",
        "gu": "એકથી વધુ પરિણામ મળ્યાં. તમે કયા વિશે પૂછો છો?",
        "hi": "एक से अधिक परिणाम मिले। आप किसके बारे में पूछ रहे हैं?",
    },
    "out_of_scope": {
        "en": "I can answer questions about GUJRERA projects, promoters and agents, and check property ads. "
              "I can't help with that question.",
        "gu": "હું GUJRERA પ્રોજેક્ટ, પ્રમોટર અને એજન્ટ વિશેના પ્રશ્નોના જવાબ આપી શકું છું અને મિલકતની જાહેરાતો "
              "તપાસી શકું છું. આ પ્રશ્નમાં હું મદદ કરી શકતો નથી.",
        "hi": "मैं GUJRERA प्रोजेक्ट, प्रमोटर और एजेंट से जुड़े सवालों के जवाब दे सकता हूँ और संपत्ति के विज्ञापन "
              "जाँच सकता हूँ। इस सवाल में मैं मदद नहीं कर सकता।",
    },
    "greeting": {
        "en": "Namaste! Ask me about a project or builder, or paste a property ad to check its RERA number.",
        "gu": "નમસ્તે! કોઈ પ્રોજેક્ટ કે બિલ્ડર વિશે પૂછો, અથવા RERA નંબર તપાસવા માટે મિલકતની જાહેરાત મૂકો.",
        "hi": "नमस्ते! किसी प्रोजेक्ट या बिल्डर के बारे में पूछें, या RERA नंबर जाँचने के लिए संपत्ति का विज्ञापन डालें।",
    },
    "complaints_coming": {
        "en": "Filing and tracking complaints by chat is not available in this prototype yet. "
              "For now, please use the GUJRERA portal.",
        "gu": "ચેટ દ્વારા ફરિયાદ નોંધવાની અને તેની સ્થિતિ જાણવાની સુવિધા આ પ્રોટોટાઇપમાં હજુ ઉપલબ્ધ નથી. "
              "હાલ માટે GUJRERA પોર્ટલનો ઉપયોગ કરો.",
        "hi": "चैट से शिकायत दर्ज करने और उसकी स्थिति जानने की सुविधा इस प्रोटोटाइप में अभी उपलब्ध नहीं है। "
              "अभी के लिए GUJRERA पोर्टल का उपयोग करें।",
    },
    "trust_result": {
        "en": "RERA check: {headline}.",
        "gu": "RERA તપાસ: {headline}.",
        "hi": "RERA जाँच: {headline}।",
    },
    "demo_note": {
        "en": "(Demo data, not real GUJRERA records.)",
        "gu": "(ડેમો ડેટા, સાચા GUJRERA રેકોર્ડ નથી.)",
        "hi": "(डेमो डेटा, असली GUJRERA रिकॉर्ड नहीं।)",
    },
}


def t(key: str, lang: str, **values) -> str:
    templates = T[key]
    return templates.get(lang, templates["en"]).format(**values)


def word(key: str, lang: str) -> str:
    entry = WORDS.get(key)
    if entry:
        return entry.get(lang, entry["en"])
    return key if key[:1].isupper() else key.replace("_", " ")


def fmt_date(d: date | None, lang: str) -> str:
    if d is None:
        return "—"
    return f"{d.day} {MONTHS.get(lang, MONTHS['en'])[d.month - 1]} {d.year}"
