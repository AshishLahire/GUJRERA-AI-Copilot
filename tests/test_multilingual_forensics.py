"""Tests for multilingual forensics across all 12 SUPPORTED_LANGS.

Covers:
1. Fee-demand detection across all new languages (gu, kn, ml, pa, or, ur).
2. Urgency/threat detection across all new languages (gu, kn, ml, pa, or, ur).
3. Fee negation suppression across all new languages.
4. Scoped fee negation: "Free laptop scheme. Registration fee Rs 199." produces fee_demand AND too_good_offer across all 12 + hi-Latn.
5. Genuine circular paragraph scoring low risk (< 25) for every new language.
6. Transliterated transcript handling: te-tagged Devanagari transcript sets transcript_transliterated = True.
7. Multilingual reference extraction and digit normalization across regional scripts.
8. Regional issuer alias detection for central authorities.
9. Pasted English free-laptop message scores HIGH.
"""

from __future__ import annotations

import pytest

from factcheck.extract.ocr.fields import extract_fields, normalize_reference_number
from factcheck.forensics.checks import (
    check_fee_demand,
    check_too_good_offer,
    check_urgency_threat,
    detect_issuer,
)
from factcheck.forensics.runner import run_forensics
from factcheck.schemas import ExtractedFields, OCRResult


NEW_LANG_SAMPLES = {
    "gu": {
        "fee_demand": "કૃપા કરીને રજીસ્ટ્રેશન માટે ₹5,000 પ્રોસેસિંગ ફી જમા કરો.",
        "urgency": "ધ્યાન આપો: 24 કલાકમાં વેરિફિકેશન પૂર્ણ કરો નહીંતર બેંક ખાતું બ્લોક થશે.",
        "negated_fee": "આ યોજના સંપૂર્ણપણે વિનામૂલ્યે છે અને કોઈ નોંધણી ફી નથી.",
        "genuine": (
            "ભારતીય રિઝર્વ બેંક\nપરિપત્ર ક્રમાંક: ૧૨૩/૨૦૨૬\nતારીખ: ૧૫ માર્ચ ૨૦૨૬\n\n"
            "તમામ અનુસૂચિત વાણિજ્યિક બેંકો માટે ગ્રાહક સેવા માર્ગદર્શિકા.\n"
            "આ પરિપત્ર ગ્રાહક હિતોના રક્ષણ માટે જાહેર કરવામાં આવ્યો છે."
        ),
    },
    "kn": {
        "fee_demand": "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅರ್ಜಿಯ ನೋಂದಣಿ ಶುಲ್ಕ ₹4,500 ಪಾವತಿಸಿ.",
        "urgency": "ಎಚ್ಚರಿಕೆ: ಬಂಧನದಿಂದ ತಪ್ಪಿಸಿಕೊಳ್ಳಲು 24 ಗಂಟೆಗಳಲ್ಲಿ ಪ್ರತಿಕ್ರಿಯಿಸಿ.",
        "negated_fee": "ಈ ಸರ್ಕಾರಿ ಕಾರ್ಯಕ್ರಮಕ್ಕೆ ಯಾವುದೇ ಶುಲ್ಕವಿಲ್ಲ, ಸಂಪೂರ್ಣ ಉಚಿತವಾಗಿದೆ.",
        "genuine": (
            "ಭಾರತೀಯ ರಿಸರ್ವ್ ಬ್ಯಾಂಕ್\nಸುತ್ತೋಲೆ ಸಂಖ್ಯೆ: ೪೫೬/೨೦૨೬\nದಿನಾಂಕ: ೧೦ ಏಪ್ರಿಲ್ ೨೦૨೬\n\n"
            "ಎಲ್ಲಾ ವಾಣಿಜ್ಯ ಬ್ಯಾಂಕುಗಳಿಗೆ ನಿರ್ದೇಶನಗಳು.\n"
            "ಸಾರ್ವಜನಿಕ ಹಿತದೃಷ್ಟಿಯಿಂದ ಈ ಸುತ್ತೋಲೆಯನ್ನು ಹೊರಡಿಸಲಾಗಿದೆ."
        ),
    },
    "ml": {
        "fee_demand": "രജിസ്ട്രേഷൻ ഫീസ് ഇനത്തിൽ ₹6,000 ഉടൻ അടയ്ക്കുക.",
        "urgency": "മുന്നറിയിപ്പ്: 24 മണിക്കൂറിനകം രേഖകൾ സമർപ്പിക്കുക, അറസ്റ്റ് വാറണ്ട് ഒഴിവാക്കുക.",
        "negated_fee": "ഈ സേവനത്തിന് യാതൊരു ഫീസും ഇല്ല, തികച്ചും സൗജന്യമാണ്.",
        "genuine": (
            "ഭാരതീയ റിസർവ് ബാങ്ക്\nസർക്കുലർ നമ്പർ: 789/2026\nതീയതി: 05 മേയ് 2026\n\n"
            "എല്ലാ വാണിജ്യ ബാങ്കുകൾക്കുമുള്ള വിജ്ഞാപനം.\n"
            "ധനകാര്യ സുരക്ഷ ഉറപ്പാക്കുന്നതിനാണ് ഈ നിർദ്ദേശം."
        ),
    },
    "pa": {
        "fee_demand": "ਆਪਣੀ ਫਾਈਲ ਦੀ ਪ੍ਰੋਸੈਸਿੰਗ ਲਈ ₹7,500 ਰਜਿਸਟ੍ਰੇਸ਼ਨ ਫੀਸ ਭਰੋ.",
        "urgency": "ਚੇਤਾਵਨੀ: 24 ਘੰਟਿਆਂ ਦੇ ਅੰਦਰ ਪੁਸ਼ਟੀ ਕਰੋ ਨਹੀਂ ਤਾਂ ਬੈਂਕ ਖਾਤਾ ਬਲਾਕ ਹੋਵੇਗਾ.",
        "negated_fee": "ਸਰਕਾਰ ਵਲੋਂ ਇਹ ਕੋਰਸ ਬਿਲਕੁਲ ਮੁਫ਼ਤ ਹੈ ਅਤੇ ਕੋਈ ਫੀਸ ਨਹੀਂ ਲਈ ਜਾਂਦੀ.",
        "genuine": (
            "ਭਾਰਤੀ ਰਿਜ਼ਰਵ ਬੈਂਕ\nਸਰਕੂਲਰ ਨੰਬਰ: ੩੨੧/੨੦੨੬\nਮਿਤੀ: ੨੦ ਮਈ ੨੦੨੬\n\n"
            "ਸਮੂਹ ਵਪਾਰਕ ਬੈਂਕਾਂ ਲਈ ਵਿਸ਼ੇਸ਼ ਦਿਸ਼ਾ-ਨਿਰਦੇਸ਼.\n"
            "ਇਹ ਪੱਤਰ ਜਨਤਕ ਜਾਣਕਾਰੀ ਲਈ ਜਾਰੀ ਕੀਤਾ ਗਿਆ ਹੈ."
        ),
    },
    "or": {
        "fee_demand": "ଆପଣଙ୍କର ଆବେଦନ ପାଇଁ ପଞ୍ଜୀକରଣ ଫି ₹3,000 ପୈଠ କରନ୍ତୁ.",
        "urgency": "ଚେତାବନୀ: 24 ଘଣ୍ଟା ମଧ୍ୟରେ ତଥ୍ୟ ଯାଞ୍ଚ କରନ୍ତୁ ନଚେତ୍ ସିମ୍ ବ୍ଲକ ହେବ.",
        "negated_fee": "ଏହି ଯୋଜନାରେ କୌଣସି ଫି ନାହିଁ ଏବଂ ଆବେଦନ ସମ୍ପୂର୍ଣ୍ଣ ମାଗଣା.",
        "genuine": (
            "ଭାରତୀୟ ରିଜର୍ଭ ବ୍ୟାଙ୍କ\nପରିପତ୍ର ସଂଖ୍ୟା: ୫୫୫/୨୦୨୬\nତାରିଖ: ୧୨ ଜୁନ ୨୦୨୬\n\n"
            "ସମସ୍ତ ବ୍ୟାଙ୍କିଙ୍ଗ ପ୍ରତିଷ୍ଠାନ ପାଇଁ ମାର୍ଗଦର୍ଶିକା.\n"
            "ଏହି ନିର୍ଦ୍ଦେଶନାମା ନିୟମିତ ପ୍ରଶାସନିକ କାର୍ଯ୍ୟ ପାଇଁ ପ୍ରଦାନ କରାଗଲା."
        ),
    },
    "ur": {
        "fee_demand": "براہ کرم رجسٹریشن فیس کی مد میں ₹8,000 جمع کرائیں۔",
        "urgency": "وارنٹ گرفتاری سے بچنے کے لیے 24 گھنٹوں کے اندر جواب دیں۔",
        "negated_fee": "یہ سرکاری اسکیم بلا معاوضہ ہے اور کوئی فیس نہیں ہے۔",
        "genuine": (
            "ریزرو بینک آف انڈیا\nسرکلر نمبر: 101/2026\nتاریخ: 15 جون 2026\n\n"
            "تمام تجارتی بینکوں کے لیے باضابطہ ہدایات نامہ جاری کیا جاتا ہے۔\n"
            "یہ دستاویز عوامی آگاہی اور بینکنگ ضوابط کے تحت ہے۔"
        ),
    },
}

FREE_LAPTOP_FEE_SAMPLES = {
    "en": "Free laptop scheme. Registration fee Rs 199.",
    "hi": "मुफ्त लैपटॉप योजना। पंजीकरण शुल्क ₹199 जमा करें।",
    "hi-Latn": "PM Free Laptop Yojana. Registration fee Rs 199 pay karo.",
    "mr": "मोफत लॅपटॉप योजना. नोंदणी शुल्क ₹199 भरा.",
    "bn": "ফ্রি ল্যাপটপ যোজনা। রেজিস্ট্রেশন ফি ₹১৯৯ জমা দিন।",
    "ta": "இலவச மடிக்கணினி திட்டம். பதிவுக் கட்டணம் ₹199 செலுத்துங்கள்.",
    "te": "ఉచిత ల్యాప్‌టాప్ యోజన. రిజిస్ట్రేషన్ ఫీజు ₹199 చెల్లించండి.",
    "gu": "મફત લેપટોપ યોજના. નોંધણી ફી ₹199 ભરો.",
    "kn": "ಉಚಿತ ಲ್ಯಾಪ್ಟಾಪ್ ಯೋಜನೆ. ನೋಂದಣಿ ಶುಲ್ಕ ₹199 ಪಾವತಿಸಿ.",
    "ml": "സൗജന്യ ലാപ്‌ടോപ്പ് പദ്ധതി. രജിസ്ട്രേഷൻ ഫീസ് ₹199 അടയ്ക്കുക.",
    "pa": "ਮੁਫ਼ਤ ਲੈਪਟਾਪ ਯੋਜਨਾ. ਰਜਿਸਟ੍ਰੇਸ਼ਨ ਫੀਸ ₹199 ਭਰੋ.",
    "or": "ମାଗଣା ଲାପଟପ୍ ଯୋଜନା. ପଞ୍ଜୀକରଣ ଫି ₹199 ପୈଠ କରନ୍ତୁ.",
    "ur": "مفت لیپ ٹاپ اسکیم۔ رجسٹریشن فیس ₹199 جمع کرائیں۔",
}


@pytest.mark.parametrize("lang_code", list(NEW_LANG_SAMPLES.keys()))
def test_fee_demand_detection_new_languages(lang_code: str):
    text = NEW_LANG_SAMPLES[lang_code]["fee_demand"]
    fields = ExtractedFields()
    findings = check_fee_demand(text, fields)
    assert len(findings) > 0, f"Expected fee demand finding for {lang_code}: '{text}'"
    assert findings[0].cue_id == "fee_demand"
    assert findings[0].severity == "critical"


@pytest.mark.parametrize("lang_code", list(NEW_LANG_SAMPLES.keys()))
def test_urgency_detection_new_languages(lang_code: str):
    text = NEW_LANG_SAMPLES[lang_code]["urgency"]
    findings = check_urgency_threat(text)
    assert len(findings) > 0, f"Expected urgency finding for {lang_code}: '{text}'"
    assert findings[0].cue_id == "urgency_threat"


@pytest.mark.parametrize("lang_code", list(NEW_LANG_SAMPLES.keys()))
def test_fee_negation_suppresses_demand(lang_code: str):
    text = NEW_LANG_SAMPLES[lang_code]["negated_fee"]
    fields = ExtractedFields()
    findings = check_fee_demand(text, fields)
    assert len(findings) == 0, f"Negated fee should NOT trigger fee_demand for {lang_code}: '{text}'"


@pytest.mark.parametrize("lang_code", list(FREE_LAPTOP_FEE_SAMPLES.keys()))
def test_free_laptop_with_fee_produces_both_cues(lang_code: str):
    """'Free laptop scheme. Registration fee Rs 199.' must produce fee_demand AND too_good_offer in every language."""
    text = FREE_LAPTOP_FEE_SAMPLES[lang_code]
    fields = ExtractedFields()

    fee_findings = check_fee_demand(text, fields)
    assert len(fee_findings) > 0, f"Expected fee_demand for {lang_code}: '{text}'"
    assert fee_findings[0].cue_id == "fee_demand"

    tg_findings = check_too_good_offer(text, fields)
    assert len(tg_findings) > 0, f"Expected too_good_offer for {lang_code}: '{text}'"
    assert tg_findings[0].cue_id == "too_good_offer"

    ocr = OCRResult(image_hash=f"fl_{lang_code}", final_text=text, engine_used="text_intake", valid=True)
    res = run_forensics(ocr)
    cue_ids = {f.cue_id for f in res.findings}
    assert "fee_demand" in cue_ids, f"run_forensics missed fee_demand for {lang_code}: '{text}'"
    assert "too_good_offer" in cue_ids, f"run_forensics missed too_good_offer for {lang_code}: '{text}'"


@pytest.mark.parametrize("lang_code", list(NEW_LANG_SAMPLES.keys()))
def test_genuine_paragraph_scores_low(lang_code: str):
    text = NEW_LANG_SAMPLES[lang_code]["genuine"]
    ocr = OCRResult(image_hash=f"gen_{lang_code}", final_text=text, engine_used="surya_ocr", valid=True)
    res = run_forensics(ocr)
    assert res.risk_level == "low", f"Genuine sample for {lang_code} scored {res.risk_score} ({res.risk_level})"
    assert res.risk_score < 25


def test_te_tagged_devanagari_transliterated_transcript():
    """A Telugu-tagged audio file with Whisper Devanagari output must set transcript_transliterated."""
    from factcheck.lang.detect import detect_language, get_language_info

    # 1. Linguistic detection verification
    devanagari_audio_text = "यह एक फर्जी संदेश है तुरंत फीस जमा करें और सिम ब्लॉक होने से बचें"
    det = detect_language(devanagari_audio_text)
    assert det.script == "Deva"

    # Spoken language is te (expected Telu)
    te_info = get_language_info("te")
    assert te_info.script_code == "Telu"
    assert te_info.script_code != det.script  # Mismatch triggers transliteration

    # 2. Forensics runner with transcript_transliterated=True runs Hindi/English lists only
    ocr = OCRResult(
        image_hash="test_audio_te_deva",
        final_text=devanagari_audio_text,
        engine_used="whisper_small",
        valid=True,
        language="te",
        script="Deva",
        transcript_transliterated=True,
    )
    res = run_forensics(ocr, is_audio=True, transcript_transliterated=True)
    assert res.transcript_transliterated is True
    assert res.transliteration_note is not None
    assert "different script" in res.transliteration_note
    cues = {f.cue_id for f in res.findings}
    assert "fee_demand" in cues or "urgency_threat" in cues


def test_multilingual_reference_extraction():
    """Test circular reference extraction across regional scripts and digit normalization."""
    # Gujarati with Gujarati numerals: ૧૨૩ -> 123
    gu_text = "પરિપત્ર ક્રમાંક: ૧૨૩/૨૦૨૬"
    f_gu = extract_fields(gu_text)
    assert len(f_gu.reference_numbers) > 0
    assert "123/2026" in f_gu.normalized_reference_numbers[0]

    # Bengali with Bengali numerals: ৪৫৬ -> 456
    bn_text = "স্মারক নম্বর: ৪৫৬/২০২৬"
    f_bn = extract_fields(bn_text)
    assert len(f_bn.reference_numbers) > 0
    assert "456/2026" in f_bn.normalized_reference_numbers[0]

    # Tamil with Tamil numerals / ASCII:
    ta_text = "சுற்றறிக்கை எண்: 789/2026"
    f_ta = extract_fields(ta_text)
    assert len(f_ta.reference_numbers) > 0
    assert "789/2026" in f_ta.normalized_reference_numbers[0]

    # Telugu:
    te_text = "సర్క్యులర్ నంబర్: 321/2026"
    f_te = extract_fields(te_text)
    assert len(f_te.reference_numbers) > 0
    assert "321/2026" in f_te.normalized_reference_numbers[0]

    # Urdu:
    ur_text = "سرکلر نمبر: 654/2026"
    f_ur = extract_fields(ur_text)
    assert len(f_ur.reference_numbers) > 0
    assert "654/2026" in f_ur.normalized_reference_numbers[0]


def test_regional_issuer_detection():
    """Test regional script names detect official central issuers."""
    # RBI in Gujarati
    assert detect_issuer("રિઝર્વ બેંક ઓફ ઇન્ડિયા નો પરિપત્ર").issuer_id == "RBI"
    # RBI in Kannada
    assert detect_issuer("ಭಾರತೀಯ ರಿಸರ್ವ್ ಬ್ಯಾಂಕ್ ಸುತ್ತೋಲೆ").issuer_id == "RBI"
    # CBSE in Gujarati
    assert detect_issuer("સેન્ટ્રલ બોર્ડ ઓફ સેકન્ડરી એજ્યુકેશન").issuer_id == "CBSE"
    # MHA in Urdu
    assert detect_issuer("وزارت داخلہ کا اعلامیہ").issuer_id == "MHA"
    # MoE in Malayalam
    assert detect_issuer("വിദ്യാഭ്യാസ മന്ത്രാലയം ഔദ്യോഗിക അറിയിപ്പ്").issuer_id == "MOE"
    # Railways / RRB in Punjabi
    assert detect_issuer("ਰੇਲਵੇ ਭਰਤੀ ਬੋਰਡ ਨੋਟੀਫਿਕੇਸ਼ਨ").issuer_id == "RRB"


def test_pasted_english_free_laptop_scores_high():
    """Confirm the pasted English free-laptop message from demo inputs scores HIGH."""
    from factcheck.api.app import _run_text_pipeline

    pasted = (
        "URGENT NOTICE: Ministry of Education is offering free laptops to all students. "
        "Click http://free-laptop-gov.in and pay Rs 500 registration fee to UPI account student@upi."
    )
    res = _run_text_pipeline(pasted, allow_fallback=False)
    assert res["forensics"]["risk_level"] == "high"
    assert res["forensics"]["risk_score"] >= 60
    assert res["verdict"]["verdict_key"] in ("debunked", "likely_forged")



def test_upi_payment_detection():
    from factcheck.forensics.checks import check_payment_to_account
    from factcheck.extract.ocr.fields import extract_fields

    # English: pay Rs 500 to student@upi
    res_en = check_payment_to_account("pay Rs 500 to student@upi")
    assert len(res_en) == 1
    assert res_en[0].cue_id == "payment_to_account"
    assert "student@upi" in res_en[0].evidence

    # Email must not fire payment_to_account
    res_email = check_payment_to_account("write to helpdesk@cbse.gov.in")
    assert len(res_email) == 0

    # Hindi examples: student@upi or user@oksbi
    res_hi = check_payment_to_account("student@upi पर ₹500 का भुगतान करें")
    assert len(res_hi) == 1
    assert res_hi[0].cue_id == "payment_to_account"
    assert "student@upi" in res_hi[0].evidence

    res_hi2 = check_payment_to_account("user@oksbi पर ₹500 भेजें")
    assert len(res_hi2) == 1
    assert res_hi2[0].cue_id == "payment_to_account"

    # Field extraction: UPI IDs extracted, emails not matched as UPI IDs
    f = extract_fields("pay Rs 500 to student@upi or write to helpdesk@cbse.gov.in")
    assert f.upi_ids == ["student@upi"]
    assert f.emails == ["helpdesk@cbse.gov.in"]


def test_free_offers_without_scheme():
    from factcheck.forensics.checks import check_too_good_offer

    phrases = [
        "offering free laptops",
        "free laptops for all students",
        "free gas cylinder",
        "free recharge",
        "free 5G tower",
        "giving free laptops",
        "muft laptop",
        "muft recharge",
        "मुफ्त गैस सिलेंडर",
        "फ्री मोबाइल रिचार्ज",
        "मोफत लॅपटॉप",
        "বিনামূল্যে ল্যাপটপ",
        "இலவச மடிக்கணினி",
        "ఉచిత ల్యాప్‌టాప్",
    ]
    for p in phrases:
        findings = check_too_good_offer(p)
        assert len(findings) >= 1, f"Expected too_good_offer for '{p}'"
        assert findings[0].cue_id == "too_good_offer"

    # Genuine circular line must NOT fire
    benign = check_too_good_offer("free of cost registration for students")
    assert len(benign) == 0
