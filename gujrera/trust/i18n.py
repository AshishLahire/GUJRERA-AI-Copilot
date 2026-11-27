"""Gujarati and Hindi for the trust check's fixed text: each check's title and the next steps for a verdict.

The detail lines carry the record's own values (dates, names, numbers) and stay in English for now.
Native-speaker review pending.
"""

from __future__ import annotations

TITLES: dict[str, dict[str, str]] = {
    "Advertised possession is after the registered date": {"gu": "જાહેરાતમાં પઝેશન નોંધાયેલી તારીખ પછીનું છે", "hi": "विज्ञापन में कब्ज़ा पंजीकृत तारीख के बाद का है"},
    "Advertised possession is earlier than the registered date": {"gu": "જાહેરાતમાં પઝેશન નોંધાયેલી તારીખ પહેલાંનું છે", "hi": "विज्ञापन में कब्ज़ा पंजीकृत तारीख से पहले का है"},
    "Agent registered": {"gu": "એજન્ટ નોંધાયેલ છે", "hi": "एजेंट पंजीकृत है"},
    "Agent registration not found": {"gu": "એજન્ટની નોંધણી મળી નથી", "hi": "एजेंट का पंजीकरण नहीं मिला"},
    "Agent registration not valid": {"gu": "એજન્ટની નોંધણી માન્ય નથી", "hi": "एजेंट का पंजीकरण मान्य नहीं"},
    "Approvals pending": {"gu": "મંજૂરીઓ બાકી છે", "hi": "मंज़ूरियाँ बाकी हैं"},
    "Booking amount above 10%": {"gu": "બુકિંગ રકમ 10% થી વધુ", "hi": "बुकिंग राशि 10% से अधिक"},
    "Completion not recorded": {"gu": "પૂર્ણતા નોંધાઈ નથી", "hi": "पूर्णता दर्ज नहीं"},
    "Demo record": {"gu": "ડેમો રેકોર્ડ", "hi": "डेमो रिकॉर्ड"},
    "Location differs": {"gu": "સ્થળ અલગ છે", "hi": "स्थान अलग है"},
    "No RERA registration number": {"gu": "RERA નોંધણી નંબર નથી", "hi": "RERA पंजीकरण संख्या नहीं"},
    "Not enough text": {"gu": "પૂરતું લખાણ નથી", "hi": "पर्याप्त पाठ नहीं"},
    "Possession date consistent": {"gu": "પઝેશનની તારીખ મેળ ખાય છે", "hi": "कब्ज़े की तारीख मेल खाती है"},
    "Project is delayed": {"gu": "પ્રોજેક્ટ વિલંબિત છે", "hi": "प्रोजेक्ट में देरी है"},
    "Project name matches": {"gu": "પ્રોજેક્ટનું નામ મેળ ખાય છે", "hi": "प्रोजेक्ट का नाम मेल खाता है"},
    "Project name not found": {"gu": "પ્રોજેક્ટનું નામ મળ્યું નથી", "hi": "प्रोजेक्ट का नाम नहीं मिला"},
    "Promoter has open complaints or adverse orders": {"gu": "પ્રમોટર સામે ખુલ્લી ફરિયાદો કે પ્રતિકૂળ આદેશો છે", "hi": "प्रमोटर पर खुली शिकायतें या प्रतिकूल आदेश हैं"},
    "Promoter matches": {"gu": "પ્રમોટર મેળ ખાય છે", "hi": "प्रमोटर मेल खाता है"},
    "Promoter name mismatch": {"gu": "પ્રમોટરનું નામ મેળ ખાતું નથી", "hi": "प्रमोटर का नाम मेल नहीं खाता"},
    "Promoter not in imported records": {"gu": "પ્રમોટર લીધેલા રેકોર્ડમાં નથી", "hi": "प्रमोटर लिए गए रिकॉर्ड में नहीं"},
    "Promoter not named": {"gu": "પ્રમોટરનું નામ આપ્યું નથી", "hi": "प्रमोटर का नाम नहीं दिया"},
    "Registration found": {"gu": "નોંધણી મળી", "hi": "पंजीकरण मिला"},
    "Registration lapsed": {"gu": "નોંધણીની મુદત પૂરી થઈ", "hi": "पंजीकरण की अवधि समाप्त"},
    "Registration number not found": {"gu": "નોંધણી નંબર મળ્યો નથી", "hi": "पंजीकरण संख्या नहीं मिली"},
    "Registration number partly differs": {"gu": "નોંધણી નંબર થોડો અલગ છે", "hi": "पंजीकरण संख्या कुछ अलग है"},
    "Registration revoked": {"gu": "નોંધણી રદ થઈ", "hi": "पंजीकरण रद्द"},
    "Registration valid": {"gu": "નોંધણી માન્ય છે", "hi": "पंजीकरण मान्य है"},
    "Payment asked to an account in the ad": {"gu": "જાહેરાતમાં આપેલા ખાતામાં ચુકવણી માગી છે", "hi": "विज्ञापन में दिए खाते में भुगतान माँगा गया है"},
}

NEXT_STEPS: dict[str, dict[str, str]] = {
    "verified": {
        "gu": "સહી કરતાં પહેલાં રજિસ્ટ્રી રેકોર્ડ ખોલીને પ્રોજેક્ટનું પાનું જાતે તપાસો. ચુકવણી ફક્ત કરારમાં લખેલા પ્રોજેક્ટના નિયત બેંક ખાતામાં જ કરો.",
        "hi": "हस्ताक्षर से पहले रजिस्ट्री रिकॉर्ड खोलकर प्रोजेक्ट का पेज खुद जाँचें। भुगतान केवल अनुबंध में लिखे प्रोजेक्ट के निर्धारित बैंक खाते में करें।",
    },
    "registered_with_warnings": {
        "gu": "દરેક ચેતવણી વાંચો. પ્રમોટર પાસે તેનો લેખિત ખુલાસો માગો, અને ચુકવણી પહેલાં પ્રોજેક્ટની ફરિયાદો અને પ્રગતિ અહેવાલ તપાસો.",
        "hi": "हर चेतावनी पढ़ें। प्रमोटर से इनकी लिखित सफ़ाई माँगें, और भुगतान से पहले प्रोजेक्ट की शिकायतें और प्रगति रिपोर्ट जाँचें।",
    },
    "mismatch": {
        "gu": "હમણાં ચુકવણી ન કરો. પ્રમોટર પાસે નોંધણી પ્રમાણપત્ર માગો અને અહીં બતાવેલા રજિસ્ટ્રી રેકોર્ડ સાથે સરખાવો.",
        "hi": "अभी भुगतान न करें। प्रमोटर से पंजीकरण प्रमाणपत्र माँगें और यहाँ दिखाए रजिस्ट्री रिकॉर्ड से मिलाएँ।",
    },
    "not_found": {
        "gu": "ચુકવણી ન કરો. નોંધણી પ્રમાણપત્ર માગો અને GUJRERA પોર્ટલ પર નંબર શોધો. નોંધણી વગર વેચાણ કે જાહેરાતની જાણ GUJRERA ને કરી શકાય.",
        "hi": "भुगतान न करें। पंजीकरण प्रमाणपत्र माँगें और GUJRERA पोर्टल पर नंबर खोजें। बिना पंजीकरण बिक्री या विज्ञापन की सूचना GUJRERA को दी जा सकती है।",
    },
    "lapsed_or_revoked": {
        "gu": "ચુકવણી ન કરો. મુદત પૂરી થયેલી કે રદ થયેલી નોંધણી હેઠળ પ્રોજેક્ટ વેચી શકાય નહીં. મુદત વધારાના આદેશ માટે રજિસ્ટ્રી રેકોર્ડ તપાસો.",
        "hi": "भुगतान न करें। समाप्त या रद्द पंजीकरण के तहत प्रोजेक्ट बेचा नहीं जा सकता। अवधि विस्तार के आदेश के लिए रजिस्ट्री रिकॉर्ड जाँचें।",
    },
    "no_rera_number": {
        "gu": "GUJRERA નોંધણી નંબર માગો. નોંધાયેલા પ્રોજેક્ટની જાહેરાતમાં તે બતાવવો ફરજિયાત છે.",
        "hi": "GUJRERA पंजीकरण संख्या माँगें। पंजीकृत प्रोजेक्ट के विज्ञापन में इसे दिखाना ज़रूरी है।",
    },
    "unreadable": {
        "gu": "વધુ સ્પષ્ટ ફોટો અપલોડ કરો અથવા જાહેરાતનું લખાણ પેસ્ટ કરો.",
        "hi": "ज़्यादा साफ़ फ़ोटो अपलोड करें या विज्ञापन का पाठ पेस्ट करें।",
    },
}


# Detail lines: templates filled with the record's values. English is the text the check always had.
DETAILS: dict[str, dict[str, str]] = {
    "readable": {"en": "Only {n} characters could be read.",
                 "gu": "ફક્ત {n} અક્ષરો વાંચી શકાયા.", "hi": "केवल {n} अक्षर पढ़े जा सके।"},
    "no_number_offer": {
        "en": "This looks like a property offer but shows no GUJRERA project registration number. Advertisements for real estate projects must show it (RERA Act, Section 11(2)).",
        "gu": "આ મિલકતની ઓફર લાગે છે, પણ તેમાં GUJRERA પ્રોજેક્ટ નોંધણી નંબર નથી. રિયલ એસ્ટેટ પ્રોજેક્ટની જાહેરાતમાં તે બતાવવો ફરજિયાત છે (RERA કાયદો, કલમ 11(2)).",
        "hi": "यह संपत्ति का ऑफ़र लगता है, पर इसमें GUJRERA प्रोजेक्ट पंजीकरण संख्या नहीं है। रियल एस्टेट प्रोजेक्ट के विज्ञापन में इसे दिखाना ज़रूरी है (RERA अधिनियम, धारा 11(2))।"},
    "no_number": {"en": "No GUJRERA project registration number was found in the text.",
                  "gu": "લખાણમાં GUJRERA પ્રોજેક્ટ નોંધણી નંબર મળ્યો નથી.", "hi": "पाठ में GUJRERA प्रोजेक्ट पंजीकरण संख्या नहीं मिली।"},
    "payment": {
        "en": "The ad asks for payment to an account number. Under RERA, buyer payments should go to the project's designated bank account named in the registration and agreement. Confirm the account with the promoter in writing before paying.",
        "gu": "જાહેરાત એક ખાતા નંબરમાં ચુકવણી માગે છે. RERA હેઠળ ખરીદનારની ચુકવણી નોંધણી અને કરારમાં લખેલા પ્રોજેક્ટના નિયત બેંક ખાતામાં જ જવી જોઈએ. ચુકવણી પહેલાં પ્રમોટર પાસેથી ખાતાની લેખિત ખાતરી લો.",
        "hi": "विज्ञापन एक खाता नंबर में भुगतान माँगता है। RERA के तहत खरीदार का भुगतान पंजीकरण और अनुबंध में लिखे प्रोजेक्ट के निर्धारित बैंक खाते में ही जाना चाहिए। भुगतान से पहले प्रमोटर से खाते की लिखित पुष्टि लें।"},
    "not_found": {"en": "{number} is not in the GUJRERA registry data available to GujRERA Saathi.",
                  "gu": "{number} ગુજરેરા સાથી પાસેના GUJRERA રજિસ્ટ્રી ડેટામાં નથી.", "hi": "{number} गुजरेरा साथी के पास उपलब्ध GUJRERA रजिस्ट्री डेटा में नहीं है।"},
    "found": {"en": "{name} by {promoter}, {district}.",
              "gu": "{name}, પ્રમોટર {promoter}, {district}.", "hi": "{name}, प्रमोटर {promoter}, {district}।"},
    "found_differs": {"en": " The number in the document ({doc}) differs from the registry ({reg}) in some segments.",
                      "gu": " દસ્તાવેજમાંનો નંબર ({doc}) રજિસ્ટ્રીના નંબર ({reg}) થી અમુક ભાગમાં અલગ છે.",
                      "hi": " दस्तावेज़ का नंबर ({doc}) रजिस्ट्री के नंबर ({reg}) से कुछ हिस्सों में अलग है।"},
    "segments": {"en": "Registry: {reg}; document: {doc}.",
                 "gu": "રજિસ્ટ્રી: {reg}; દસ્તાવેજ: {doc}.", "hi": "रजिस्ट्री: {reg}; दस्तावेज़: {doc}।"},
    "mock": {"en": "This registry record is mock data for the prototype, not a real GUJRERA project.",
             "gu": "આ રજિસ્ટ્રી રેકોર્ડ પ્રોટોટાઇપ માટેનો ડેમો ડેટા છે, ખરો GUJRERA પ્રોજેક્ટ નથી.",
             "hi": "यह रजिस्ट्री रिकॉर्ड प्रोटोटाइप का डेमो डेटा है, असली GUJRERA प्रोजेक्ट नहीं।"},
    "unverified": {
        "en": "The registered completion date ({date}) has passed, and the public records imported here do not show whether the project was completed. Check the project's page on the GUJRERA portal before paying.",
        "gu": "નોંધાયેલી પૂર્ણતા તારીખ ({date}) વીતી ગઈ છે, અને અહીં લીધેલા જાહેર રેકોર્ડમાં પ્રોજેક્ટ પૂર્ણ થયો કે નહીં તે દેખાતું નથી. ચુકવણી પહેલાં GUJRERA પોર્ટલ પર પ્રોજેક્ટનું પાનું તપાસો.",
        "hi": "पंजीकृत पूर्णता तिथि ({date}) बीत चुकी है, और यहाँ लिए गए सार्वजनिक रिकॉर्ड में यह नहीं दिखता कि प्रोजेक्ट पूरा हुआ या नहीं। भुगतान से पहले GUJRERA पोर्टल पर प्रोजेक्ट का पेज जाँचें।"},
    "revoked": {"en": "The registry shows this registration as revoked.",
                "gu": "રજિસ્ટ્રી મુજબ આ નોંધણી રદ થયેલી છે.", "hi": "रजिस्ट्री के अनुसार यह पंजीकरण रद्द है।"},
    "lapsed": {"en": "Registration was valid until {date} and no extension is recorded.",
               "gu": "નોંધણી {date} સુધી માન્ય હતી અને કોઈ મુદત વધારો નોંધાયેલો નથી.", "hi": "पंजीकरण {date} तक मान्य था और कोई अवधि विस्तार दर्ज नहीं है।"},
    "valid": {"en": "Status {status}; valid until {date}.",
              "gu": "સ્થિતિ: {status}; {date} સુધી માન્ય.", "hi": "स्थिति: {status}; {date} तक मान्य।"},
    "promoter_unknown": {
        "en": "The public records imported here do not name this project's promoter; compare the name in the document with the project's page on the GUJRERA portal.",
        "gu": "અહીં લીધેલા જાહેર રેકોર્ડમાં આ પ્રોજેક્ટના પ્રમોટરનું નામ નથી; દસ્તાવેજમાંનું નામ GUJRERA પોર્ટલ પરના પ્રોજેક્ટના પાના સાથે સરખાવો.",
        "hi": "यहाँ लिए गए सार्वजनिक रिकॉर्ड में इस प्रोजेक्ट के प्रमोटर का नाम नहीं है; दस्तावेज़ का नाम GUJRERA पोर्टल पर प्रोजेक्ट के पेज से मिलाएँ।"},
    "promoter_match": {"en": "The document names the registered promoter, {name}.",
                       "gu": "દસ્તાવેજમાં નોંધાયેલા પ્રમોટર {name} નું નામ છે.", "hi": "दस्तावेज़ में पंजीकृत प्रमोटर {name} का नाम है।"},
    "promoter_mismatch": {"en": "The document names {other}, but this registration belongs to {name}.",
                          "gu": "દસ્તાવેજમાં {other} નું નામ છે, પણ આ નોંધણી {name} ની છે.", "hi": "दस्तावेज़ में {other} का नाम है, पर यह पंजीकरण {name} का है।"},
    "promoter_not_named": {"en": "The document does not name the registered promoter ({name}).",
                           "gu": "દસ્તાવેજમાં નોંધાયેલા પ્રમોટર ({name}) નું નામ નથી.", "hi": "दस्तावेज़ में पंजीकृत प्रमोटर ({name}) का नाम नहीं है।"},
    "name_match": {"en": "The document names {name}.", "gu": "દસ્તાવેજમાં {name} નું નામ છે.", "hi": "दस्तावेज़ में {name} का नाम है।"},
    "name_missing": {"en": "The registered name {name} does not appear in the document.",
                     "gu": "નોંધાયેલું નામ {name} દસ્તાવેજમાં નથી.", "hi": "पंजीकृत नाम {name} दस्तावेज़ में नहीं है।"},
    "district": {"en": "The document mentions {named}; the registered project is in {district}.",
                 "gu": "દસ્તાવેજમાં {named} લખ્યું છે; નોંધાયેલો પ્રોજેક્ટ {district} માં છે.", "hi": "दस्तावेज़ में {named} लिखा है; पंजीकृत प्रोजेक्ट {district} में है।"},
    "poss_after_unverified": {
        "en": "The document promises possession around {when}, later than the completion date in the imported records ({date}). Check the GUJRERA portal for an extension before paying.",
        "gu": "દસ્તાવેજ {when} આસપાસ પઝેશનનું વચન આપે છે, જે લીધેલા રેકોર્ડની પૂર્ણતા તારીખ ({date}) પછીનું છે. ચુકવણી પહેલાં GUJRERA પોર્ટલ પર મુદત વધારો તપાસો.",
        "hi": "दस्तावेज़ {when} के आसपास कब्ज़े का वादा करता है, जो लिए गए रिकॉर्ड की पूर्णता तिथि ({date}) के बाद है। भुगतान से पहले GUJRERA पोर्टल पर अवधि विस्तार जाँचें।"},
    "poss_after": {
        "en": "The document promises possession around {when}, later than the registered completion date {date}.",
        "gu": "દસ્તાવેજ {when} આસપાસ પઝેશનનું વચન આપે છે, જે નોંધાયેલી પૂર્ણતા તારીખ {date} પછીનું છે.",
        "hi": "दस्तावेज़ {when} के आसपास कब्ज़े का वादा करता है, जो पंजीकृत पूर्णता तिथि {date} के बाद है।"},
    "poss_earlier": {
        "en": "The document promises possession around {when}, but the project is registered to complete by {date}. Ask the promoter to put the earlier date in the agreement for sale.",
        "gu": "દસ્તાવેજ {when} આસપાસ પઝેશનનું વચન આપે છે, પણ પ્રોજેક્ટ {date} સુધીમાં પૂર્ણ થવા નોંધાયેલો છે. પ્રમોટરને વહેલી તારીખ વેચાણ કરારમાં લખવા કહો.",
        "hi": "दस्तावेज़ {when} के आसपास कब्ज़े का वादा करता है, पर प्रोजेक्ट {date} तक पूरा होने के लिए पंजीकृत है। प्रमोटर से पहले की तारीख बिक्री अनुबंध में लिखने को कहें।"},
    "poss_ok": {"en": "Registered completion: {date}.", "gu": "નોંધાયેલી પૂર્ણતા: {date}.", "hi": "पंजीकृत पूर्णता: {date}।"},
    "delay": {"en": "{days} days past its original completion date ({date}).",
              "gu": "મૂળ પૂર્ણતા તારીખ ({date}) થી {days} દિવસ વધુ.", "hi": "मूल पूर्णता तिथि ({date}) से {days} दिन अधिक।"},
    "approvals": {"en": "Pending: {items}.", "gu": "બાકી: {items}.", "hi": "लंबित: {items}।"},
    "promoter_record": {
        "en": "{open} open complaints, {orders} show-cause, penalty or revocation orders across {projects} projects.",
        "gu": "{projects} પ્રોજેક્ટમાં {open} ખુલ્લી ફરિયાદો, {orders} કારણદર્શક, દંડ કે રદ કરવાના આદેશો.",
        "hi": "{projects} प्रोजेक्ट में {open} खुली शिकायतें, {orders} कारण बताओ, दंड या रद्द करने के आदेश।"},
    "agent_not_found": {"en": "{number} is not in the GUJRERA agent registry data.",
                        "gu": "{number} GUJRERA એજન્ટ રજિસ્ટ્રી ડેટામાં નથી.", "hi": "{number} GUJRERA एजेंट रजिस्ट्री डेटा में नहीं है।"},
    "agent_invalid": {"en": "{name}: status {status}, valid until {date}.",
                      "gu": "{name}: સ્થિતિ {status}, {date} સુધી માન્ય.", "hi": "{name}: स्थिति {status}, {date} तक मान्य।"},
    "agent_ok": {"en": "{name}, valid until {date}.", "gu": "{name}, {date} સુધી માન્ય.", "hi": "{name}, {date} तक मान्य।"},
    "booking": {
        "en": "The document asks for about {pct}% at booking. A promoter cannot take more than 10% of the cost before a registered agreement for sale (RERA Act, Section 13).",
        "gu": "દસ્તાવેજ બુકિંગ વખતે લગભગ {pct}% માગે છે. નોંધાયેલા વેચાણ કરાર પહેલાં પ્રમોટર કિંમતના 10% થી વધુ લઈ શકે નહીં (RERA કાયદો, કલમ 13).",
        "hi": "दस्तावेज़ बुकिंग पर लगभग {pct}% माँगता है। पंजीकृत बिक्री अनुबंध से पहले प्रमोटर कीमत के 10% से अधिक नहीं ले सकता (RERA अधिनियम, धारा 13)।"},
}

# Registry status words shown inside detail lines
STATUS: dict[str, dict[str, str]] = {
    "ongoing": {"en": "ongoing", "gu": "ચાલુ", "hi": "चालू"},
    "completed": {"en": "completed", "gu": "પૂર્ણ", "hi": "पूर्ण"},
    "lapsed": {"en": "lapsed", "gu": "મુદત પૂરી", "hi": "समाप्त"},
    "revoked": {"en": "revoked", "gu": "રદ", "hi": "रद्द"},
    "unverified": {"en": "completion not recorded", "gu": "પૂર્ણતા નોંધાઈ નથી", "hi": "पूर्णता दर्ज नहीं"},
    "active": {"en": "active", "gu": "સક્રિય", "hi": "सक्रिय"},
    "expired": {"en": "expired", "gu": "મુદત પૂરી", "hi": "समाप्त"},
}


def detail(key: str, **values) -> dict[str, str]:
    """A detail line in English, Gujarati and Hindi. A value given as {"en":..,"gu":..,"hi":..} is used per language."""
    out = {}
    for lang, template in DETAILS[key].items():
        out[lang] = template.format(**{k: (v.get(lang, v.get("en")) if isinstance(v, dict) else v) for k, v in values.items()})
    return out


def status_word(status: str) -> dict[str, str]:
    return STATUS.get(status, {"en": status, "gu": status, "hi": status})


# Approval kinds named in "Approvals pending"
APPROVALS: dict[str, dict[str, str]] = {
    "building_permission": {"en": "building permission", "gu": "બાંધકામ પરવાનગી", "hi": "भवन निर्माण अनुमति"},
    "environment_clearance": {"en": "environment clearance", "gu": "પર્યાવરણ મંજૂરી", "hi": "पर्यावरण मंज़ूरी"},
    "fire_noc": {"en": "fire noc", "gu": "ફાયર NOC", "hi": "फ़ायर NOC"},
    "layout_plan": {"en": "layout plan", "gu": "લેઆઉટ પ્લાન", "hi": "लेआउट प्लान"},
    "non_agricultural": {"en": "non agricultural", "gu": "બિનખેતી (NA)", "hi": "गैर-कृषि (NA)"},
}


def approvals_list(kinds: list[str]) -> dict[str, str]:
    """The pending approvals, comma-separated, in each language (English exactly as before)."""
    out = {}
    for lang in ("en", "gu", "hi"):
        out[lang] = ", ".join(APPROVALS.get(k, {}).get(lang) or k.replace("_", " ") for k in kinds)
    return out
