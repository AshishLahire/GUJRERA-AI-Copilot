"""Law questions with the provision that must be retrieved (top 3), for eval_gujrera_legal.py.

Expected answers: ("act", "18") = RERA Act section 18; ("rules", "16") = Gujarat RERA General Rules rule 16.
Where the Gujarat Rules have their own provision on the same point (e.g. Rule 7, extension of registration,
alongside Act section 6), either is accepted. None = off-topic, must return nothing.
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
    ("en", "best biryani in Surat", None),
    ("en", "who won the cricket world cup", None),
    ("en", "what is the weather today", None),
    ("gu", "આજે હવામાન કેવું છે?", None),
    ("gu", "ક્રિકેટ મેચ કોણ જીત્યું?", None),
    ("hi", "आज मौसम कैसा है?", None),
    ("hi", "दाल कैसे बनाते हैं?", None),
]
