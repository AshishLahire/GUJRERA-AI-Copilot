"""Law questions with the provision that must be retrieved (top 3), for eval_gujrera_legal.py.

Expected answers: ("act", "18") = RERA Act section 18; ("rules", "16") = Gujarat RERA General Rules rule 16.
Where the Gujarat Rules have their own provision on the same point (e.g. Rule 7, extension of registration,
alongside Act section 6), either is accepted. None = off-topic, must return nothing.

LEGAL_HELD_OUT was written after the glossary was extended, in buyers' own words ("cracks appeared", "missed
the handover date"), to check that search works beyond the questions it was tuned on. Keep it that way: when
a held-out question fails, fix the cause in general, and add new held-out questions rather than tuning to these.
"""

from __future__ import annotations

LEGAL_GOLD: list[tuple[str, str, tuple[str, str] | list[tuple[str, str]] | None]] = [
    ("en", "Can a builder advertise a project before registering it with RERA?", ("act", "3")),
    ("en", "How much advance can the promoter take before signing the agreement for sale?", ("act", "13")),
    ("en", "If possession is delayed, can I get my money back with interest?", ("act", "18")),
    ("en", "Who is responsible for structural defects after I take possession?", ("act", "14")),
    ("en", "How do I file a complaint with RERA?", ("act", "31")),
    ("en", "Who decides claims for compensation?", ("act", "71")),
    ("en", "What is the punishment if a promoter does not register the project?", ("act", "59")),
    ("en", "Can the registration of a project be revoked?", [("act", "7"), ("rules", "8")]),
    ("en", "Can the registration of a project be extended?", [("act", "6"), ("rules", "7")]),
    ("en", "When must the promoter execute the conveyance deed?", ("act", "17")),
    ("en", "What are the rights of an allottee?", ("act", "19")),
    ("en", "Does a real estate agent need to register with RERA?", [("act", "9"), ("rules", "11")]),
    ("en", "What is the rate of interest payable by the promoter in Gujarat?", ("rules", "16")),
    ("en", "Within how many days must a refund be paid?", ("rules", "17")),
    ("en", "When can the promoter withdraw money from the separate project account?", ("rules", "5")),
    ("gu", "શું બિલ્ડર RERA નોંધણી વગર પ્રોજેક્ટની જાહેરાત કરી શકે?", ("act", "3")),
    ("gu", "કરાર પહેલાં બિલ્ડર કેટલું એડવાન્સ લઈ શકે?", ("act", "13")),
    ("gu", "પઝેશનમાં વિલંબ થાય તો શું મને વ્યાજ સાથે પૈસા પાછા મળે?", ("act", "18")),
    ("gu", "RERA માં ફરિયાદ કેવી રીતે કરવી?", ("act", "31")),
    ("gu", "ગુજરાતમાં પ્રમોટરે કેટલા વ્યાજ દરે ચૂકવવું પડે?", ("rules", "16")),
    ("hi", "क्या बिल्डर बिना पंजीकरण के विज्ञापन दे सकता है?", ("act", "3")),
    ("hi", "कब्जे में देरी होने पर क्या मुझे ब्याज सहित पैसे वापस मिलेंगे?", ("act", "18")),
    ("hi", "RERA में शिकायत कैसे दर्ज करें?", ("act", "31")),
    ("hi", "प्रोजेक्ट का पंजीकरण कब बढ़ाया जा सकता है?", [("act", "6"), ("rules", "7")]),
    ("hi", "रिफंड कितने दिनों में मिलना चाहिए?", ("rules", "17")),
    # Gujarati and Hindi versions of the English questions above
    ('gu', 'પ્રમોટર કરાર કર્યા વગર કેટલી રકમ એડવાન્સ લઈ શકે?', ('act', '13')),
    ('gu', 'પઝેશન લીધા પછી બાંધકામમાં ખામી માટે કોણ જવાબદાર છે?', ('act', '14')),
    ('gu', 'વળતરના દાવાનો નિર્ણય કોણ કરે છે?', ('act', '71')),
    ('gu', 'પ્રોજેક્ટની નોંધણી ન કરાવે તો પ્રમોટરને શી સજા થાય?', ('act', '59')),
    ('gu', 'શું પ્રોજેક્ટની નોંધણી રદ થઈ શકે?', [('act', '7'), ('rules', '8')]),
    ('gu', 'પ્રોજેક્ટની નોંધણીની મુદત વધારી શકાય?', [('act', '6'), ('rules', '7')]),
    ('gu', 'પ્રમોટરે વેચાણ દસ્તાવેજ ક્યારે કરી આપવો પડે?', ('act', '17')),
    ('gu', 'ફ્લેટ ખરીદનારના અધિકારો શું છે?', ('act', '19')),
    ('gu', 'શું રિયલ એસ્ટેટ એજન્ટે RERA માં નોંધણી કરાવવી પડે?', [('act', '9'), ('rules', '11')]),
    ('gu', 'રિફંડ કેટલા દિવસમાં ચૂકવવું પડે?', ('rules', '17')),
    ('gu', 'પ્રમોટર પ્રોજેક્ટના અલગ બેંક ખાતામાંથી પૈસા ક્યારે ઉપાડી શકે?', ('rules', '5')),
    ('hi', 'समझौते पर हस्ताक्षर से पहले प्रमोटर कितना अग्रिम ले सकता है?', ('act', '13')),
    ('hi', 'कब्जा लेने के बाद ढांचे में खराबी के लिए कौन जिम्मेदार है?', ('act', '14')),
    ('hi', 'मुआवजे के दावों का फैसला कौन करता है?', ('act', '71')),
    ('hi', 'प्रोजेक्ट का पंजीकरण न कराने पर प्रमोटर को क्या सजा है?', ('act', '59')),
    ('hi', 'क्या प्रोजेक्ट का पंजीकरण रद्द किया जा सकता है?', [('act', '7'), ('rules', '8')]),
    ('hi', 'प्रमोटर को कन्वेयंस डीड कब करनी होती है?', ('act', '17')),
    ('hi', 'फ्लैट खरीदार के क्या अधिकार हैं?', ('act', '19')),
    ('hi', 'क्या रियल एस्टेट एजेंट को RERA में पंजीकरण कराना होता है?', [('act', '9'), ('rules', '11')]),
    ('hi', 'गुजरात में प्रमोटर को किस ब्याज दर से भुगतान करना होता है?', ('rules', '16')),
    ('hi', 'प्रमोटर प्रोजेक्ट के अलग खाते से पैसे कब निकाल सकता है?', ('rules', '5')),
    ("en", "best biryani in Surat", None),
    ("en", "who won the cricket world cup", None),
    ("en", "what is the weather today", None),
    ("gu", "આજે હવામાન કેવું છે?", None),
    ("gu", "ક્રિકેટ મેચ કોણ જીત્યું?", None),
    ("hi", "आज मौसम कैसा है?", None),
    ("hi", "दाल कैसे बनाते हैं?", None),
]


LEGAL_HELD_OUT: list[tuple[str, str, tuple[str, str] | list[tuple[str, str]]]] = [
    ('hi', 'बिल्डर ने तय तारीख पर फ्लैट नहीं दिया, मैं क्या कर सकता हूँ?', ('act', '18')),
    ('hi', 'क्या बिल्डर बुकिंग के समय 20 प्रतिशत ले सकता है?', ('act', '13')),
    ('hi', 'घर मिलने के पांच साल के अंदर दरारें आएं तो कौन ठीक करेगा?', ('act', '14')),
    ('hi', 'RERA के आदेश के खिलाफ अपील कहाँ करें?', [('act', '43'), ('act', '44')]),
    ('hi', 'बिना RERA नंबर के प्रोजेक्ट बेचना क्या अपराध है?', [('act', '3'), ('act', '59')]),
    ('hi', 'एजेंट का पंजीकरण कितने साल के लिए होता है?', [('act', '9'), ('rules', '11'), ('rules', '12')]),
    ('hi', 'प्रमोटर को कितनी बार प्रोजेक्ट की प्रगति की जानकारी देनी होती है?', ('act', '11')),
    ('hi', 'नक्शा बदलने के लिए क्या खरीदारों की सहमति चाहिए?', ('act', '14')),
    ('hi', 'गुजरात में देरी पर ब्याज की दर क्या है?', ('rules', '16')),
    ('gu', 'બિલ્ડરે વચન આપેલી તારીખે ફ્લેટ ન આપ્યો તો હું શું કરી શકું?', ('act', '18')),
    ('gu', 'બુકિંગ વખતે બિલ્ડર 20 ટકા માગે છે, શું તે કાયદેસર છે?', ('act', '13')),
    ('gu', 'ઘર મળ્યાના પાંચ વર્ષમાં તિરાડ પડે તો કોણ રિપેર કરે?', ('act', '14')),
    ('gu', 'RERA ના આદેશ સામે અપીલ ક્યાં કરવી?', [('act', '43'), ('act', '44')]),
    ('gu', 'એજન્ટની નોંધણી કેટલા વર્ષ માટે હોય છે?', [('act', '9'), ('rules', '11'), ('rules', '12')]),
    ('gu', 'પ્રમોટરે કેટલા સમયે પ્રોજેક્ટની પ્રગતિની માહિતી આપવી પડે?', ('act', '11')),
    ('gu', 'નકશો બદલવા માટે ખરીદનારની મંજૂરી જોઈએ?', ('act', '14')),
    ('gu', 'ગુજરાતમાં વિલંબ માટે વ્યાજનો દર શું છે?', ('rules', '16')),
    ('en', 'The builder missed the promised handover date, what can I do?', ('act', '18')),
    ('en', 'Is it legal for the developer to ask 20% at booking?', ('act', '13')),
    ('en', 'Cracks appeared three years after possession, who must repair them?', ('act', '14')),
    ('en', 'Where do I appeal against a RERA order?', [('act', '43'), ('act', '44')]),
    ('en', "How long is an agent's registration valid?", [('act', '9'), ('rules', '11'), ('rules', '12')]),
    ('en', "Can the promoter change the plan without the buyers' consent?", ('act', '14')),
]
