"""What the provisions buyers ask about cover, in plain words, in English, Gujarati and Hindi.

Used only to rank search results, never shown as the law: a buyer asks "the builder missed the handover
date, what can I do?", not "if the promoter fails to complete or is unable to give possession". Matching
the question against these descriptions as well as the legal text finds the right provision across
phrasings and languages. Each description says what the provision itself provides (RERA Act, 2016 and
the Gujarat RERA (General) Rules, 2017); none is written from a test question.
"""

from __future__ import annotations

PLAIN: dict[tuple[str, str], list[str]] = {
    ("act", "3"): [
        "A builder must register the project with RERA before advertising, booking or selling flats, plots or buildings.",
        "Selling or advertising a project without a RERA registration is not allowed.",
        "બિલ્ડરે ફ્લેટ, પ્લોટ કે મકાનની જાહેરાત, બુકિંગ કે વેચાણ પહેલાં પ્રોજેક્ટની RERA માં નોંધણી કરાવવી જ પડે.",
        "बिल्डर को फ्लैट, प्लॉट या मकान का विज्ञापन, बुकिंग या बिक्री से पहले प्रोजेक्ट का RERA में पंजीकरण कराना ज़रूरी है।",
    ],
    ("act", "6"): [
        "The project's registration can be extended by up to one year when completion is delayed by force majeure.",
        "પ્રોજેક્ટની નોંધણીની મુદત કુદરતી આફત જેવા કારણે એક વર્ષ સુધી વધારી શકાય.",
        "प्रोजेक्ट का पंजीकरण अप्रत्याशित कारणों से एक साल तक बढ़ाया जा सकता है।",
    ],
    ("act", "7"): [
        "RERA can cancel (revoke) a project's registration for default, unfair practice, fraud or false information.",
        "RERA છેતરપિંડી, ગેરરીતિ કે નિયમભંગ માટે પ્રોજેક્ટની નોંધણી રદ કરી શકે.",
        "RERA धोखाधड़ी, अनुचित व्यवहार या नियम तोड़ने पर प्रोजेक्ट का पंजीकरण रद्द कर सकता है।",
    ],
    ("act", "9"): [
        "A real estate agent or broker must register with RERA before helping sell or buy flats, plots or buildings.",
        "રિયલ એસ્ટેટ એજન્ટ કે દલાલે ફ્લેટ કે પ્લોટ વેચાવતા પહેલાં RERA માં નોંધણી કરાવવી પડે.",
        "रियल एस्टेट एजेंट या दलाल को फ्लैट या प्लॉट बिकवाने से पहले RERA में पंजीकरण कराना होता है।",
    ],
    ("act", "10"): [
        "Duties of a real estate agent: deal only in registered projects, keep records, no false statements or unfair practices.",
        "એજન્ટની ફરજો: ફક્ત નોંધાયેલા પ્રોજેક્ટ વેચવા, રેકોર્ડ રાખવો, ખોટી માહિતી ન આપવી.",
        "एजेंट के कर्तव्य: केवल पंजीकृत प्रोजेक्ट बेचना, रिकॉर्ड रखना, झूठी जानकारी न देना।",
    ],
    ("act", "11"): [
        "Duties of the builder: update the project's progress every quarter on the RERA website, publish bookings and approvals, "
        "form the buyers' association (society) and maintain the project until it is handed over.",
        "બિલ્ડરની ફરજો: દર ત્રણ મહિને RERA વેબસાઇટ પર પ્રોજેક્ટની પ્રગતિ જણાવવી, બુકિંગ અને મંજૂરીઓની માહિતી આપવી, ખરીદનારોની સોસાયટી બનાવવી.",
        "बिल्डर के कर्तव्य: हर तिमाही RERA वेबसाइट पर प्रोजेक्ट की प्रगति बताना, बुकिंग और मंज़ूरियों की जानकारी देना, खरीदारों की सोसायटी बनवाना।",
    ],
    ("act", "12"): [
        "If a buyer pays on the basis of a false advertisement or brochure, the builder must compensate or refund with interest.",
        "ખોટી જાહેરાત કે બ્રોશરના આધારે પૈસા ભર્યા હોય તો બિલ્ડરે વળતર કે વ્યાજ સાથે રિફંડ આપવું પડે.",
        "झूठे विज्ञापन या ब्रोशर के आधार पर पैसे दिए हों तो बिल्डर को मुआवज़ा या ब्याज सहित रिफंड देना होगा।",
    ],
    ("act", "13"): [
        "A builder cannot take more than 10 per cent of the price as booking amount or advance before a registered agreement for sale.",
        "નોંધાયેલા વેચાણ કરાર પહેલાં બિલ્ડર કિંમતના 10 ટકાથી વધુ બુકિંગ કે એડવાન્સ લઈ શકે નહીં.",
        "पंजीकृत बिक्री अनुबंध से पहले बिल्डर कीमत के 10 प्रतिशत से ज़्यादा बुकिंग राशि या अग्रिम नहीं ले सकता।",
    ],
    ("act", "14"): [
        "The builder must build as per the sanctioned plans; changing the plan or layout needs the buyers' consent (two-thirds for major changes).",
        "If structural defects or poor workmanship appear within five years of possession, the builder must repair them free within 30 days.",
        "બિલ્ડરે મંજૂર નકશા મુજબ જ બાંધકામ કરવું પડે; નકશો બદલવા ખરીદનારોની સંમતિ જોઈએ.",
        "પઝેશનના પાંચ વર્ષમાં બાંધકામમાં ખામી કે તિરાડ આવે તો બિલ્ડરે 30 દિવસમાં મફત રિપેર કરવું પડે.",
        "बिल्डर को मंज़ूर नक्शे के अनुसार ही निर्माण करना होगा; नक्शा बदलने के लिए खरीदारों की सहमति चाहिए।",
        "कब्जे के पांच साल के भीतर ढांचे में खराबी या दरार आए तो बिल्डर को 30 दिन में मुफ्त ठीक करना होगा।",
    ],
    ("act", "15"): [
        "A builder cannot hand the project over to another builder without the consent of two-thirds of the buyers and RERA's approval.",
        "બિલ્ડર ખરીદનારોની બે તૃતીયાંશ સંમતિ અને RERA ની મંજૂરી વગર પ્રોજેક્ટ બીજાને સોંપી શકે નહીં.",
        "बिल्डर दो-तिहाई खरीदारों की सहमति और RERA की मंज़ूरी के बिना प्रोजेक्ट किसी दूसरे को नहीं सौंप सकता।",
    ],
    ("act", "17"): [
        "The builder must execute the registered sale deed (conveyance deed) in the buyer's name and hand over common areas to the society, "
        "within three months of the occupancy certificate.",
        "બિલ્ડરે ઓક્યુપન્સી સર્ટિફિકેટ પછી ત્રણ મહિનામાં ખરીદનારના નામે વેચાણ દસ્તાવેજ કરી આપવો પડે.",
        "बिल्डर को कब्ज़ा प्रमाणपत्र के तीन महीने के भीतर खरीदार के नाम रजिस्ट्री (कन्वेयंस डीड) करनी होगी।",
    ],
    ("act", "18"): [
        "If the builder does not give possession by the promised date, the buyer can take a full refund with interest and compensation, "
        "or stay in the project and get interest for every month of delay until possession.",
        "બિલ્ડર વચન આપેલી તારીખે પઝેશન ન આપે તો ખરીદનાર વ્યાજ અને વળતર સાથે પૂરું રિફંડ લઈ શકે, અથવા દર મહિનાના વિલંબનું વ્યાજ મેળવી શકે.",
        "बिल्डर वादे की तारीख पर कब्ज़ा न दे तो खरीदार ब्याज और मुआवज़े सहित पूरा पैसा वापस ले सकता है, या हर महीने की देरी का ब्याज पा सकता है।",
    ],
    ("act", "19"): [
        "Rights of a home buyer: information on plans and the construction schedule, possession, documents, refund; "
        "duties: pay instalments on time and take possession.",
        "ફ્લેટ ખરીદનારના અધિકારો: નકશા અને બાંધકામની માહિતી, પઝેશન, દસ્તાવેજો, રિફંડ; ફરજો: સમયસર હપ્તા ભરવા.",
        "फ्लैट खरीदार के अधिकार: नक्शे और निर्माण की जानकारी, कब्ज़ा, दस्तावेज़, रिफंड; कर्तव्य: समय पर किस्तें भरना।",
    ],
    ("act", "31"): [
        "Any buyer or affected person can file a complaint with RERA or the adjudicating officer against a builder or agent.",
        "કોઈ પણ ખરીદનાર બિલ્ડર કે એજન્ટ સામે RERA માં ફરિયાદ નોંધાવી શકે.",
        "कोई भी खरीदार बिल्डर या एजेंट के खिलाफ RERA में शिकायत दर्ज कर सकता है।",
    ],
    ("act", "43"): [
        "An appeal against an order of RERA or the adjudicating officer goes to the Real Estate Appellate Tribunal, within 60 days.",
        "RERA ના આદેશ સામે 60 દિવસમાં રિયલ એસ્ટેટ અપીલેટ ટ્રિબ્યુનલમાં અપીલ કરી શકાય.",
        "RERA के आदेश के खिलाफ 60 दिन के भीतर रियल एस्टेट अपीलीय न्यायाधिकरण में अपील की जा सकती है।",
    ],
    ("act", "58"): [
        "An appeal against the Appellate Tribunal's order goes to the High Court within 60 days.",
        "અપીલેટ ટ્રિબ્યુનલના આદેશ સામે 60 દિવસમાં હાઈકોર્ટમાં અપીલ થાય.",
        "अपीलीय न्यायाधिकरण के आदेश के खिलाफ 60 दिन में हाईकोर्ट में अपील होती है।",
    ],
    ("act", "59"): [
        "A builder who does not register the project is fined up to 10 per cent of the project cost, and can be jailed up to three years if it continues.",
        "પ્રોજેક્ટની નોંધણી ન કરાવનાર બિલ્ડરને પ્રોજેક્ટ ખર્ચના 10 ટકા સુધી દંડ અને ત્રણ વર્ષ સુધીની જેલ થઈ શકે.",
        "प्रोजेक्ट का पंजीकरण न कराने वाले बिल्डर पर प्रोजेक्ट लागत का 10 प्रतिशत तक जुर्माना और तीन साल तक की जेल हो सकती है।",
    ],
    ("act", "63"): [
        "A builder who does not obey RERA's order pays a penalty for every day of default, up to 5 per cent of the project cost.",
        "RERA ના આદેશનું પાલન ન કરનાર બિલ્ડરને દરરોજનો દંડ થાય.",
        "RERA के आदेश का पालन न करने वाले बिल्डर पर हर दिन का जुर्माना लगता है।",
    ],
    ("act", "71"): [
        "The adjudicating officer decides claims for compensation from the builder.",
        "બિલ્ડર પાસેથી વળતરના દાવાનો નિર્ણય એડજ્યુડિકેટિંગ ઓફિસર કરે છે.",
        "बिल्डर से मुआवज़े के दावों का फैसला न्यायनिर्णायक अधिकारी करता है।",
    ],
    ("rules", "5"): [
        "The builder keeps 70 per cent of buyers' money in a separate bank account and can withdraw it only in proportion to "
        "construction, with an engineer's, architect's and chartered accountant's certificates.",
        "બિલ્ડરે ખરીદનારોના 70 ટકા પૈસા અલગ બેંક ખાતામાં રાખવા પડે અને બાંધકામના પ્રમાણમાં જ ઉપાડી શકે.",
        "बिल्डर को खरीदारों का 70 प्रतिशत पैसा अलग बैंक खाते में रखना होता है और निर्माण के अनुपात में ही निकाल सकता है।",
    ],
    ("rules", "7"): [
        "How a builder applies to extend the project's registration (Form E), giving the reasons for delay.",
        "બિલ્ડર પ્રોજેક્ટની નોંધણીની મુદત વધારવા ફોર્મ E માં અરજી કરે.",
        "बिल्डर प्रोजेक्ट का पंजीकरण बढ़ाने के लिए फॉर्म E में आवेदन करता है।",
    ],
    ("rules", "11"): [
        "RERA gives a registered real estate agent a registration certificate and number, valid for five years.",
        "નોંધાયેલા એજન્ટને RERA પાંચ વર્ષ માટે નોંધણી પ્રમાણપત્ર આપે.",
        "पंजीकृत एजेंट को RERA पांच साल के लिए पंजीकरण प्रमाणपत्र देता है।",
    ],
    ("rules", "16"): [
        "In Gujarat the interest for delay or refund is SBI's highest marginal cost of lending rate plus 2 per cent.",
        "ગુજરાતમાં વિલંબ કે રિફંડ પર વ્યાજનો દર SBI ના MCLR વત્તા 2 ટકા છે.",
        "गुजरात में देरी या रिफंड पर ब्याज दर SBI के MCLR से 2 प्रतिशत अधिक है।",
    ],
    ("rules", "17"): [
        "The builder must pay any refund, with interest and compensation, within 45 days.",
        "બિલ્ડરે રિફંડ વ્યાજ અને વળતર સાથે 45 દિવસમાં ચૂકવવું પડે.",
        "बिल्डर को रिफंड ब्याज और मुआवज़े सहित 45 दिन में देना होगा।",
    ],
}
