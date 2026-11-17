"""Tests for Pramaan Language Foundation (factcheck/lang).

Verifies:
1. SUPPORTED_LANGS definition and metadata (12 languages + hi-Latn).
2. Sentence-level detection across all 13 supported languages.
3. Indic & Arabic-Indic digit normalization across all 11 digit scripts.
4. Unicode NFC normalization.
5. Text direction: Urdu is RTL; others are LTR.
6. Integration with field extraction and OCRResult language detection.
"""

from __future__ import annotations

import unicodedata
import pytest

from factcheck.lang import (
    SUPPORTED_LANGUAGES,
    SUPPORTED_LANGS,
    detect_language,
    get_language_info,
    is_rtl,
    normalize_digits,
    normalize_text,
)
from factcheck.extract.ocr.fields import extract_fields, normalize_reference_number
from factcheck.schemas import OCRResult


def test_supported_languages_metadata() -> None:
    """1. SUPPORTED_LANGS contains en, hi, bn, mr, te, ta, gu, kn, ml, pa, or, ur, hi-Latn."""
    expected_codes = ["en", "hi", "bn", "mr", "te", "ta", "gu", "kn", "ml", "pa", "or", "ur", "hi-Latn"]
    for code in expected_codes:
        assert code in SUPPORTED_LANGS, f"{code} missing from SUPPORTED_LANGS"
        info = get_language_info(code)
        assert info is not None, f"Info missing for {code}"
        assert info.name, f"English name missing for {code}"
        assert info.native_name, f"Native name missing for {code}"
        assert info.script_code, f"Script code missing for {code}"
        assert info.direction in ("ltr", "rtl"), f"Invalid direction for {code}"


def test_urdu_is_rtl() -> None:
    """Urdu is RTL; all other supported languages are LTR."""
    assert is_rtl("ur") is True
    ur_info = get_language_info("ur")
    assert ur_info is not None and ur_info.direction == "rtl"

    ltr_codes = ["en", "hi", "bn", "mr", "te", "ta", "gu", "kn", "ml", "pa", "or", "hi-Latn"]
    for code in ltr_codes:
        assert is_rtl(code) is False, f"{code} should be LTR"
        info = get_language_info(code)
        assert info is not None and info.direction == "ltr"


# One clear sample sentence per language
SAMPLE_SENTENCES: dict[str, str] = {
    "en": "The Ministry of Education issued a revised academic circular for all schools.",
    "hi": "शिक्षा मंत्रालय ने सभी स्कूलों के लिए एक नया परिपत्र जारी किया है।",
    "bn": "শিক্ষা মন্ত্রক সমস্ত স্কুলের জন্য একটি নতুন বিজ্ঞপ্তি জারি করেছে।",
    "mr": "शालेय शिक्षण व क्रीडा विभागाने सर्व शाळांसाठी नवीन परिपत्रक जारी केले आहे.",
    "te": "విద్యా మంత్రిత్వ శాఖ అన్ని పాఠశాలల కోసం ఒక కొత్త సర్క్యులర్‌ను జారీ చేసింది.",
    "ta": "பள்ளிக் கல்வித் துறை அனைத்துப் பள்ளிகளுக்கும் புதிய சுற்றறிக்கையை வெளியிட்டுள்ளது.",
    "gu": "શિક્ષણ મંત્રાલયે તમામ શાળાઓ માટે નવો પરિપત્ર બહાર પાડ્યો છે.",
    "kn": "ಶಿಕ್ಷಣ ಸಚಿವಾಲಯವು ಎಲ್ಲಾ ಶಾಲೆಗಳಿಗೆ ಹೊಸ ಸುತ್ತೋಲೆಯನ್ನು ಹೊರಡಿಸಿದೆ.",
    "ml": "വിദ്യാഭ്യാസ മന്ത്രാലയം എല്ലാ സ്കൂളുകൾക്കുമായി പുതിയ സർക്കുലർ പുറത്തിറക്കി.",
    "pa": "ਸਿੱਖਿਆ ਮੰਤਰਾਲੇ ਨੇ ਸਾਰੇ ਸਕੂਲਾਂ ਲਈ ਇੱਕ ਨਵਾਂ ਸਰਕੂਲਰ ਜਾਰੀ ਕੀਤਾ ਹੈ।",
    "or": "ଶିକ୍ଷା ମନ୍ତ୍ରଣାଳୟ ସମସ୍ତ ବିଦ୍ୟାଳୟ ପାଇଁ ଏକ ନୂତନ ବିଜ୍ଞପ୍ତି ଜାରି କରିଛି।",
    "ur": "وزارت تعلیم نے تمام اسکولوں کے لیے ایک نیا سرکلر جاری کیا ہے۔",
    "hi-Latn": "Yeh fake circular WhatsApp pe viral ho raha hai please check karo bhai.",
}


@pytest.mark.parametrize("expected_lang, sentence", list(SAMPLE_SENTENCES.items()))
def test_detect_language_sample_sentences(expected_lang: str, sentence: str) -> None:
    """2. One sample sentence per language detects correctly."""
    res = detect_language(sentence)
    assert res.language == expected_lang, (
        f"Expected {expected_lang}, got {res.language} (script: {res.script}, conf: {res.confidence})"
    )
    assert res.confidence >= 0.70
    if expected_lang == "ur":
        assert res.direction == "rtl"
    else:
        assert res.direction == "ltr"


def test_devanagari_hindi_vs_marathi() -> None:
    """Devanagari text distinguishes Hindi vs Marathi accurately."""
    hi_text = "यह आदेश तत्काल प्रभाव से लागू किया गया है। सभी संबंधित अधिकारी इसका पालन करें।"
    mr_text = "हा शासन निर्णय तात्काळ प्रभावाने लागू करण्यात आला आहे. सर्व संबंधित अधिकाऱ्यांनी याचे पालन करावे."
    assert detect_language(hi_text).language == "hi"
    assert detect_language(mr_text).language == "mr"


def test_latin_english_vs_hinglish() -> None:
    """Latin text distinguishes English vs Hinglish accurately."""
    en_text = "This circular contains official instructions for secondary examinations and registration fees."
    hinglish_text = "Suno bhai yeh circular fake hai koi bhi fees mat dena aur aage share mat karo"
    assert detect_language(en_text).language == "en"
    assert detect_language(hinglish_text).language == "hi-Latn"


# 11 scripts of digits: 0-9
DIGIT_SCRIPTS: dict[str, str] = {
    "devanagari": "०१२३४५६७८९",
    "bengali": "০১২৩৪৫৬৭৮৯",
    "gurmukhi": "੦੧੨੩੪੫੬੭੮੯",
    "gujarati": "૦૧૨૩૪૫૬૭૮૯",
    "odia": "୦୧୨୩୪୫୬୭୮୯",
    "tamil": "௦௧௨௩௪௫௬௭௮௯",
    "telugu": "౦౧౨౩౪౫౬౭౮౯",
    "kannada": "೦೧೨೩೪೫೬೭೮೯",
    "malayalam": "൦൧൨൩൪൫൬൭൮൯",
    "arabic_indic": "٠١٢٣٤٥٦٧٨٩",
    "extended_arabic_indic": "۰۱۲۳۴۵۶۷۸۹",
}


@pytest.mark.parametrize("script_name, digit_str", list(DIGIT_SCRIPTS.items()))
def test_all_indic_digits_normalize_to_ascii(script_name: str, digit_str: str) -> None:
    """3. Digits from every Indic script convert to ASCII 0123456789."""
    normalized = normalize_digits(digit_str)
    assert normalized == "0123456789", f"{script_name} failed to normalize: got {normalized}"


def test_normalize_text_unicode_nfc() -> None:
    """normalize_text ensures Unicode NFC normalization."""
    # Decomposed e with acute (e + U+0301) -> composed é (U+00E9)
    decomposed = "e\u0301"
    composed = "\u00e9"
    assert unicodedata.is_normalized("NFD", decomposed)
    norm = normalize_text(decomposed)
    assert unicodedata.is_normalized("NFC", norm)
    assert norm == composed


def test_reference_extraction_with_indic_digits() -> None:
    """Field extraction normalizes reference numbers with Indic digits into ASCII."""
    # Devanagari digits in reference
    ref_hi = "परिपत्र संख्या: शैक्ष-५५/२०२६"
    fields_hi = extract_fields(ref_hi)
    assert "Acad-55/2026" in fields_hi.reference_numbers

    # Bengali digits in reference
    ref_bn = "Ref No: CEB/Acad-৭৬৮/২০২৬"
    fields_bn = extract_fields(ref_bn)
    assert "CEB/Acad-768/2026" in fields_bn.reference_numbers

    # Gujarati digits in circular and date
    text_gu = "Circular No: Acad-૫૫/૨૦૨૬ Date: ૧૫/૦૮/૨૦૨૬"
    fields_gu = extract_fields(text_gu)
    assert "Acad-55/2026" in fields_gu.reference_numbers
    assert "15/08/2026" in fields_gu.dates


def test_ocr_result_populates_language_fields() -> None:
    """OCRResult includes language, script, confidence, and text direction."""
    hi_sample = "केन्द्रीय माध्यमिक शिक्षा बोर्ड परिपत्र संख्या: शैक्ष-५५/२०२६"
    det = detect_language(hi_sample)
    ocr = OCRResult(
        image_hash="sample_hash",
        final_text=hi_sample,
        engine_used="paddleocr",
        valid=True,
        language=det.language,
        script=det.script,
        language_confidence=det.confidence,
        language_name=det.language_name,
        text_direction=det.direction,
    )
    assert ocr.language == "hi"
    assert ocr.script == "Deva"
    assert ocr.language_name == "Hindi"
    assert ocr.text_direction == "ltr"
    assert ocr.language_confidence is not None and ocr.language_confidence >= 0.70


def test_mixed_language_shares_and_badge() -> None:
    """Mixed-language documents return primary_language, shares, and 'Hindi + English' when secondary >= 20%."""
    # Hindi text + English text
    mixed_text = (
        "केन्द्रीय माध्यमिक शिक्षा बोर्ड द्वारा जारी परिपत्र। सभी विद्यार्थियों को सूचित किया जाता है। "
        "Central Board of Secondary Education official circular for all affiliated schools."
    )
    det = detect_language(mixed_text)
    assert det.primary_language in ("hi", "en")
    assert len(det.languages_present) >= 2
    # At least Hindi and English shares present
    langs = {s.language for s in det.languages_present}
    assert "hi" in langs and "en" in langs
    # Display badge shows secondary if >= 20%
    if det.languages_present[1].share >= 0.20:
        assert "+" in det.display_badge


def test_out_of_list_nepali_clip_uncertain() -> None:
    """Nepali ASR clip transcript is flagged as language uncertain with confidence < 0.6."""
    # From data/eval/asr/step7_check/ne.mp3
    nepali_ref = "सरकारले सबै विद्यार्थीलाई निःशुल्क ल्यापटप दिने सन्देश फैलिएको छ।"
    det = detect_language(nepali_ref)
    assert det.is_uncertain is True
    assert det.confidence < 0.60
    assert det.display_badge == "language uncertain"
