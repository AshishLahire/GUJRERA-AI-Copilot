"""Complaint-flow wording in Gujarati, Hindi and English (native-speaker review pending)."""

from __future__ import annotations

S: dict[str, dict[str, str]] = {
    "start": {
        "en": "I'll help you file a complaint with GUJRERA. Type 'cancel' at any time to stop.",
        "gu": "હું GUJRERA માં ફરિયાદ નોંધાવવામાં મદદ કરીશ. ગમે ત્યારે રોકવા માટે 'cancel' લખો.",
        "hi": "मैं GUJRERA में शिकायत दर्ज करने में मदद करूँगा। कभी भी रोकने के लिए 'cancel' लिखें।",
    },
    "ask_project": {
        "en": "Which project is it about? Tell me the project name or its RERA number.",
        "gu": "કયા પ્રોજેક્ટ વિશે છે? પ્રોજેક્ટનું નામ અથવા RERA નંબર જણાવો.",
        "hi": "यह किस प्रोजेक्ट के बारे में है? प्रोजेक्ट का नाम या RERA नंबर बताइए।",
    },
    "project_not_found": {
        "en": "I couldn't find that project in the registry. Please check the name or RERA number.",
        "gu": "આ પ્રોજેક્ટ રેકોર્ડમાં મળ્યો નથી. કૃપા કરીને નામ અથવા RERA નંબર તપાસો.",
        "hi": "यह प्रोजेक्ट रिकॉर्ड में नहीं मिला। कृपया नाम या RERA नंबर जाँचें।",
    },
    "pick_project": {
        "en": "More than one project matches. Which one?",
        "gu": "એકથી વધુ પ્રોજેક્ટ મળ્યા. કયો?",
        "hi": "एक से अधिक प्रोजेक्ट मिले। कौन सा?",
    },
    "project_ok": {
        "en": "Project: {name} ({rera}).",
        "gu": "પ્રોજેક્ટ: {name} ({rera}).",
        "hi": "प्रोजेक्ट: {name} ({rera})।",
    },
    "category_guess": {
        "en": "I've noted this as: {category}. You can change it before submitting.",
        "gu": "મેં આને \"{category}\" તરીકે નોંધ્યું છે. મોકલતા પહેલાં બદલી શકો છો.",
        "hi": "मैंने इसे \"{category}\" के रूप में दर्ज किया है। जमा करने से पहले बदल सकते हैं।",
    },
    "ask_description": {
        "en": "Please describe the problem in a few sentences.",
        "gu": "કૃપા કરીને સમસ્યા થોડા વાક્યોમાં જણાવો.",
        "hi": "कृपया समस्या कुछ वाक्यों में बताइए।",
    },
    "short_description": {
        "en": "Please add a little more detail (at least one full sentence).",
        "gu": "કૃપા કરીને થોડી વધુ વિગત આપો (ઓછામાં ઓછું એક પૂરું વાક્ય).",
        "hi": "कृपया थोड़ा और विवरण दें (कम से कम एक पूरा वाक्य)।",
    },
    "ask_category": {
        "en": "Which of these best describes your complaint?",
        "gu": "તમારી ફરિયાદ માટે આમાંથી કયું સૌથી યોગ્ય છે?",
        "hi": "आपकी शिकायत के लिए इनमें से कौन सा सबसे सही है?",
    },
    "ask_relief": {
        "en": "What would you like GUJRERA to order?",
        "gu": "તમે GUJRERA પાસેથી કયો આદેશ ઇચ્છો છો?",
        "hi": "आप GUJRERA से कौन सा आदेश चाहते हैं?",
    },
    "ask_name": {
        "en": "Your full name, as in the agreement for sale?",
        "gu": "વેચાણ કરાર મુજબ તમારું પૂરું નામ?",
        "hi": "बिक्री अनुबंध के अनुसार आपका पूरा नाम?",
    },
    "bad_name": {
        "en": "Please enter your full name.",
        "gu": "કૃપા કરીને તમારું પૂરું નામ લખો.",
        "hi": "कृपया अपना पूरा नाम लिखें।",
    },
    "ask_mobile": {
        "en": "Your 10-digit mobile number, for updates on the complaint?",
        "gu": "ફરિયાદની જાણકારી માટે તમારો 10 અંકનો મોબાઇલ નંબર?",
        "hi": "शिकायत की जानकारी के लिए आपका 10 अंकों का मोबाइल नंबर?",
    },
    "bad_mobile": {
        "en": "That doesn't look like a valid 10-digit Indian mobile number. Please try again.",
        "gu": "આ માન્ય 10 અંકનો મોબાઇલ નંબર લાગતો નથી. ફરી પ્રયાસ કરો.",
        "hi": "यह मान्य 10 अंकों का मोबाइल नंबर नहीं लगता। कृपया फिर से लिखें।",
    },
    "ask_email": {
        "en": "Email address (optional, or type 'skip')?",
        "gu": "ઇમેઇલ સરનામું (વૈકલ્પિક, અથવા 'skip' લખો)?",
        "hi": "ईमेल पता (वैकल्पिक, या 'skip' लिखें)?",
    },
    "bad_email": {
        "en": "That email doesn't look right. Please try again or type 'skip'.",
        "gu": "આ ઇમેઇલ બરાબર લાગતો નથી. ફરી લખો અથવા 'skip' લખો.",
        "hi": "यह ईमेल सही नहीं लगता। फिर से लिखें या 'skip' लिखें।",
    },
    "ask_unit": {
        "en": "Your flat or unit number (optional, or 'skip')?",
        "gu": "તમારો ફ્લેટ અથવા યુનિટ નંબર (વૈકલ્પિક, અથવા 'skip')?",
        "hi": "आपका फ्लैट या यूनिट नंबर (वैकल्पिक, या 'skip')?",
    },
    "ask_consent": {
        "en": "Do you agree to share these details with GUJRERA to process your complaint? "
              "They will be used only for this complaint.",
        "gu": "ફરિયાદની કાર્યવાહી માટે આ વિગતો GUJRERA સાથે શેર કરવા તમે સંમત છો? "
              "તેનો ઉપયોગ ફક્ત આ ફરિયાદ માટે થશે.",
        "hi": "क्या आप शिकायत की कार्रवाई के लिए ये विवरण GUJRERA के साथ साझा करने के लिए सहमत हैं? "
              "इनका उपयोग केवल इसी शिकायत के लिए होगा।",
    },
    "no_consent": {
        "en": "Without your consent I can't submit the complaint. Your details have been discarded.",
        "gu": "તમારી સંમતિ વિના હું ફરિયાદ મોકલી શકતો નથી. તમારી વિગતો કાઢી નાખવામાં આવી છે.",
        "hi": "आपकी सहमति के बिना मैं शिकायत जमा नहीं कर सकता। आपके विवरण हटा दिए गए हैं।",
    },
    "review": {
        "en": "Please check your complaint before submitting. It will be filed as Form {form}.",
        "gu": "મોકલતા પહેલાં તમારી ફરિયાદ તપાસો. તે ફોર્મ {form} તરીકે નોંધાશે.",
        "hi": "जमा करने से पहले अपनी शिकायत जाँच लें। यह फॉर्म {form} के रूप में दर्ज होगी।",
    },
    "form_a_note": {
        "en": "Form A is a complaint to the Authority (RERA Act, Section 31).",
        "gu": "ફોર્મ A એ ઓથોરિટી સમક્ષ ફરિયાદ છે (RERA કાયદો, કલમ 31).",
        "hi": "फॉर्म A प्राधिकरण के समक्ष शिकायत है (RERA अधिनियम, धारा 31)।",
    },
    "form_b_note": {
        "en": "Form B is a claim for compensation, decided by the adjudicating officer (RERA Act, Section 71).",
        "gu": "ફોર્મ B વળતર માટેનો દાવો છે, જેનો નિર્ણય ન્યાયનિર્ણાયક અધિકારી કરે છે (RERA કાયદો, કલમ 71).",
        "hi": "फॉर्म B मुआवजे का दावा है, जिसका निर्णय न्यायनिर्णायक अधिकारी करते हैं (RERA अधिनियम, धारा 71)।",
    },
    "ask_edit": {
        "en": "Which detail do you want to change?",
        "gu": "કઈ વિગત બદલવી છે?",
        "hi": "कौन सा विवरण बदलना है?",
    },
    "submitted": {
        "en": "Your complaint has been filed. Reference number: {ref}. Tracking code: {code}. "
              "Keep both safe; you need them to check the status.",
        "gu": "તમારી ફરિયાદ નોંધાઈ ગઈ છે. સંદર્ભ નંબર: {ref}. ટ્રેકિંગ કોડ: {code}. "
              "બંને સાચવી રાખો; સ્થિતિ જાણવા માટે તેની જરૂર પડશે.",
        "hi": "आपकी शिकायत दर्ज हो गई है। संदर्भ संख्या: {ref}। ट्रैकिंग कोड: {code}। "
              "दोनों संभालकर रखें; स्थिति जानने के लिए इनकी ज़रूरत होगी।",
    },
    "mock_note": {
        "en": "(Prototype: filed in a mock GUJRERA workflow, not the real portal.)",
        "gu": "(પ્રોટોટાઇપ: ડેમો GUJRERA વર્કફ્લોમાં નોંધાઈ, સાચા પોર્ટલમાં નહીં.)",
        "hi": "(प्रोटोटाइप: डेमो GUJRERA वर्कफ़्लो में दर्ज, असली पोर्टल में नहीं।)",
    },
    "cancelled": {
        "en": "Complaint cancelled. Nothing was submitted.",
        "gu": "ફરિયાદ રદ કરી. કશું મોકલવામાં આવ્યું નથી.",
        "hi": "शिकायत रद्द की गई। कुछ भी जमा नहीं किया गया।",
    },
    "ask_ref": {
        "en": "Please tell me your complaint reference number.",
        "gu": "કૃપા કરીને ફરિયાદનો સંદર્ભ નંબર જણાવો.",
        "hi": "कृपया शिकायत की संदर्भ संख्या बताइए।",
    },
    "ask_code": {
        "en": "Please enter the 6-digit tracking code for {ref}.",
        "gu": "{ref} માટે 6 અંકનો ટ્રેકિંગ કોડ લખો.",
        "hi": "{ref} के लिए 6 अंकों का ट्रैकिंग कोड लिखें।",
    },
    "bad_code": {
        "en": "That tracking code doesn't match. {left} attempts left.",
        "gu": "ટ્રેકિંગ કોડ મેળ ખાતો નથી. {left} પ્રયાસ બાકી.",
        "hi": "ट्रैकिंग कोड मेल नहीं खाता। {left} प्रयास बाकी।",
    },
    "locked": {
        "en": "Too many wrong codes. Please try again later.",
        "gu": "ઘણા ખોટા કોડ. થોડા સમય પછી ફરી પ્રયાસ કરો.",
        "hi": "बहुत सारे गलत कोड। कृपया बाद में फिर कोशिश करें।",
    },
    "unknown_ref": {
        "en": "I couldn't find a complaint with reference {ref}.",
        "gu": "{ref} સંદર્ભ નંબરવાળી ફરિયાદ મળી નથી.",
        "hi": "{ref} संदर्भ संख्या वाली शिकायत नहीं मिली।",
    },
    "no_code_on_record": {
        "en": "Complaint {ref} was not filed through this copilot, so it has no tracking code. "
              "Please check its status on the GUJRERA portal.",
        "gu": "ફરિયાદ {ref} આ કોપાયલટ દ્વારા નોંધાઈ ન હતી, તેથી તેનો ટ્રેકિંગ કોડ નથી. "
              "તેની સ્થિતિ GUJRERA પોર્ટલ પર જુઓ.",
        "hi": "शिकायत {ref} इस कोपायलट से दर्ज नहीं हुई थी, इसलिए इसका ट्रैकिंग कोड नहीं है। "
              "इसकी स्थिति GUJRERA पोर्टल पर देखें।",
    },
    "status": {
        "en": "Complaint {ref} ({category}, Form {form}) was filed on {filed}. Current status: {status}.",
        "gu": "ફરિયાદ {ref} ({category}, ફોર્મ {form}) {filed} ના રોજ નોંધાઈ હતી. હાલની સ્થિતિ: {status}.",
        "hi": "शिकायत {ref} ({category}, फॉर्म {form}) {filed} को दर्ज हुई थी। वर्तमान स्थिति: {status}।",
    },
}

LABELS: dict[str, dict[str, str]] = {
    # categories
    "possession_delay": {"en": "Delay in possession", "gu": "પઝેશનમાં વિલંબ", "hi": "कब्जे में देरी"},
    "refund": {"en": "Refund", "gu": "રિફંડ", "hi": "रिफंड"},
    "structural_defect": {"en": "Structural defect", "gu": "બાંધકામમાં ખામી", "hi": "निर्माण में खराबी"},
    "plan_deviation": {"en": "Change from approved plan", "gu": "મંજૂર પ્લાનમાં ફેરફાર", "hi": "स्वीकृत नक्शे में बदलाव"},
    "false_advertisement": {"en": "False advertisement", "gu": "ખોટી જાહેરાત", "hi": "झूठा विज्ञापन"},
    "amenities_not_provided": {"en": "Amenities not provided", "gu": "સુવિધાઓ આપી નથી", "hi": "सुविधाएँ नहीं दी गईं"},
    "agreement_violation": {"en": "Breach of agreement or extra charges", "gu": "કરારનો ભંગ અથવા વધારાના ચાર્જ",
                            "hi": "अनुबंध का उल्लंघन या अतिरिक्त शुल्क"},
    "agent_misconduct": {"en": "Agent misconduct", "gu": "એજન્ટનું ગેરવર્તન", "hi": "एजेंट का दुर्व्यवहार"},
    "compensation": {"en": "Compensation", "gu": "વળતર", "hi": "मुआवजा"},
    # reliefs
    "possession_with_interest": {"en": "Possession, with interest for the delay", "gu": "વિલંબ માટે વ્યાજ સાથે પઝેશન",
                                 "hi": "देरी के ब्याज के साथ कब्जा"},
    "refund_with_interest": {"en": "Refund with interest", "gu": "વ્યાજ સાથે રિફંડ", "hi": "ब्याज सहित रिफंड"},
    "rectification": {"en": "Repair or correction of defects", "gu": "ખામીઓનું સમારકામ", "hi": "खराबियों की मरम्मत"},
    "other": {"en": "Other", "gu": "અન્ય", "hi": "अन्य"},
    # complaint statuses
    "filed": {"en": "filed", "gu": "નોંધાયેલ", "hi": "दर्ज"},
    "under_scrutiny": {"en": "under scrutiny", "gu": "ચકાસણી હેઠળ", "hi": "जाँच में"},
    "hearing_scheduled": {"en": "hearing scheduled", "gu": "સુનાવણી નક્કી", "hi": "सुनवाई तय"},
    "order_reserved": {"en": "order reserved", "gu": "આદેશ અનામત", "hi": "आदेश सुरक्षित"},
    "disposed": {"en": "disposed", "gu": "નિકાલ", "hi": "निपटारा"},
    "withdrawn": {"en": "withdrawn", "gu": "પાછી ખેંચી", "hi": "वापस ली गई"},
    # buttons
    "submit": {"en": "Submit complaint", "gu": "ફરિયાદ મોકલો", "hi": "शिकायत जमा करें"},
    "edit": {"en": "Change something", "gu": "કંઈક બદલો", "hi": "कुछ बदलें"},
    "cancel": {"en": "Cancel", "gu": "રદ કરો", "hi": "रद्द करें"},
    "yes": {"en": "Yes, I agree", "gu": "હા, હું સંમત છું", "hi": "हाँ, मैं सहमत हूँ"},
    "no": {"en": "No", "gu": "ના", "hi": "नहीं"},
    "skip": {"en": "Skip", "gu": "છોડો", "hi": "छोड़ें"},
    # field names
    "f_project": {"en": "Project", "gu": "પ્રોજેક્ટ", "hi": "प्रोजेक्ट"},
    "f_description": {"en": "Problem", "gu": "સમસ્યા", "hi": "समस्या"},
    "f_category": {"en": "Category", "gu": "પ્રકાર", "hi": "प्रकार"},
    "f_relief": {"en": "Relief sought", "gu": "માગણી", "hi": "माँग"},
    "f_name": {"en": "Name", "gu": "નામ", "hi": "नाम"},
    "f_mobile": {"en": "Mobile", "gu": "મોબાઇલ", "hi": "मोबाइल"},
    "f_email": {"en": "Email", "gu": "ઇમેઇલ", "hi": "ईमेल"},
    "f_unit": {"en": "Unit", "gu": "યુનિટ", "hi": "यूनिट"},
    "f_form": {"en": "Form", "gu": "ફોર્મ", "hi": "फॉर्म"},
}


def s(key: str, lang: str, **values) -> str:
    entry = S[key]
    return entry.get(lang, entry["en"]).format(**values)


def label(key: str, lang: str) -> str:
    entry = LABELS.get(key)
    return entry.get(lang, entry["en"]) if entry else key
