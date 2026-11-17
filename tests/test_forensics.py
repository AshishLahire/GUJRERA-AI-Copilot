"""Unit tests for Stage 2b rule-based forensic checks (ZERO API calls)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from factcheck.api.app import create_app
from factcheck.extract.ocr.fields import extract_fields
from factcheck.forensics.rules import SEVERITY_WEIGHTS
from factcheck.forensics.runner import run_forensics
from factcheck.schemas import OCRResult


def _ocr_from_text(text: str) -> OCRResult:
    return OCRResult(
        image_hash="test_hash",
        final_text=text,
        engine_used="test_engine",
        valid=True,
        fields=extract_fields(text, strip_watermark=False),
        from_cache=True,
    )


def test_fee_demand_in_hindi() -> None:
    """1. Fee demand in Hindi ('शुल्क' / '₹') triggers critical fee_demand finding."""
    text = (
        "प्रधानमंत्री मुद्रा योजना के तहत आपका ₹5,00,000 का लोन स्वीकृत हो गया है। "
        "आज ही ₹2,100 फाइल चार्ज जमा करें और पंजीकरण शुल्क ₹500 दें।"
    )
    res = run_forensics(_ocr_from_text(text))
    cues = {f.cue_id for f in res.findings}
    assert "fee_demand" in cues
    fee_finding = next(f for f in res.findings if f.cue_id == "fee_demand")
    assert fee_finding.severity == "critical"
    assert fee_finding.points == 35
    assert text[fee_finding.char_start : fee_finding.char_end] == fee_finding.evidence


def test_negated_fee_not_flagged() -> None:
    """2. Negated fee ('There is no fee for students participating') scores no fee_demand finding."""
    text = (
        "Central Board of Secondary Education\n"
        "Circular No.: Acad-67/2026\n"
        "Subject: CBSE Science Challenge 2026-27\n"
        "There is no fee for students participating in the first stage of the challenge."
    )
    res = run_forensics(_ocr_from_text(text))
    cues = {f.cue_id for f in res.findings}
    assert "fee_demand" not in cues
    assert res.risk_level == "low"
    assert res.risk_score == 0


def test_urgency_in_tamil() -> None:
    """3. Urgency and arrest warrant threat in Tamil triggers urgency_threat warning."""
    text = (
        "அவசரம்: இந்திய சைபர் குற்ற ஒருங்கிணைப்பு மையம் உங்கள் மீது வழக்குப் பதிவு செய்துள்ளது. "
        "24 மணி நேரத்திற்குள் இந்தக் கடிதத்திற்குப் பதில் அளிக்காவிட்டால் கைது வாரண்ட் பிறப்பிக்கப்படும்."
    )
    res = run_forensics(_ocr_from_text(text))
    cues = {f.cue_id for f in res.findings}
    assert "urgency_threat" in cues
    urg = next(f for f in res.findings if f.cue_id == "urgency_threat")
    assert urg.severity == "warning"
    assert text[urg.char_start : urg.char_end] == urg.evidence


def test_gmail_on_government_letter() -> None:
    """4. Free-mail address (gmail.com) on a government notice triggers personal_contact warning."""
    text = (
        "Ministry of Finance\n"
        "Department of Revenue\n"
        "For verification of your allotment, send documents to finmin.helpdesk2026@gmail.com."
    )
    res = run_forensics(_ocr_from_text(text))
    cues = {f.cue_id for f in res.findings}
    assert "personal_contact" in cues
    pc = next(f for f in res.findings if f.cue_id == "personal_contact")
    assert pc.evidence == "finmin.helpdesk2026@gmail.com"
    assert text[pc.char_start : pc.char_end] == "finmin.helpdesk2026@gmail.com"


def test_goverment_misspelling() -> None:
    """5. Misspelling 'Goverment' in official terminology triggers spelling_errors warning."""
    text = (
        "GOVERMENT OF INDIA\n"
        "MINISTRY OF HOME AFFAIRS\n"
        "Notice regarding departmental verification."
    )
    res = run_forensics(_ocr_from_text(text))
    cues = {f.cue_id for f in res.findings}
    assert "spelling_errors" in cues
    sp = next(f for f in res.findings if f.cue_id == "spelling_errors")
    assert sp.evidence.lower() == "goverment"
    assert text[sp.char_start : sp.char_end] == sp.evidence


def test_mina_gov_is_lookalike_domain_critical() -> None:
    """6. Lookalike domain 'mina.gov.is' triggers critical lookalike_domain finding."""
    text = (
        "Ministry of Home Affairs\n"
        "Visit the official portal at https://mina.gov.is/verify to submit your form."
    )
    res = run_forensics(_ocr_from_text(text))
    cues = {f.cue_id for f in res.findings}
    assert "lookalike_domain" in cues
    dom_f = next(f for f in res.findings if f.cue_id == "lookalike_domain")
    assert dom_f.severity == "critical"
    assert dom_f.points == 35
    assert "mina.gov.is" in dom_f.evidence
    assert text[dom_f.char_start : dom_f.char_end] == dom_f.evidence


def test_mixed_issuers_warning() -> None:
    """7. Letter combining I4C, CBI, INTERPOL, and Delhi Police triggers mixed_issuers warning."""
    text = (
        "Indian Cyber Crime Coordination Centre (I4C)\n"
        "In joint collaboration with Central Bureau of Investigation (CBI), INTERPOL and Delhi Police.\n"
        "Subject: Notice of investigation."
    )
    res = run_forensics(_ocr_from_text(text))
    cues = {f.cue_id for f in res.findings}
    assert "mixed_issuers" in cues


def test_impossible_date_anomaly() -> None:
    """8. Impossible calendar date '31/02/2026' triggers date_anomaly warning."""
    text = (
        "Reserve Bank of India\n"
        "Date: 31/02/2026\n"
        "Circular regarding quarterly reporting."
    )
    res = run_forensics(_ocr_from_text(text))
    cues = {f.cue_id for f in res.findings}
    assert "date_anomaly" in cues
    da = next(f for f in res.findings if f.cue_id == "date_anomaly")
    assert da.evidence == "31/02/2026"
    assert text[da.char_start : da.char_end] == "31/02/2026"


def test_clean_genuine_cbse_paragraph_scores_low() -> None:
    """9. Clean genuine CBSE circular paragraph with official corpus reference scores 0 (low)."""
    text = (
        "CENTRAL BOARD OF SECONDARY EDUCATION\n"
        "Circular No.: Acad-67/2026\n"
        "Date: 13.10.2026\n"
        "Subject: CBSE Science Challenge 2026-27\n"
        "Science is an integral part of our everyday lives and helps us understand the world around us. "
        "Schools may register students on https://cbse.gov.in and https://cbseacademic.nic.in."
    )
    res = run_forensics(_ocr_from_text(text))
    assert res.detected_issuer is not None
    assert res.detected_issuer.issuer_id == "CBSE"
    assert res.risk_score == 0
    assert res.risk_level == "low"
    ref_findings = [f for f in res.findings if f.cue_id == "ref_status"]
    assert len(ref_findings) == 1
    assert "matches official record" in ref_findings[0].title


def test_forensics_not_cached_recomputes_on_weight_change(monkeypatch) -> None:
    """10. Changing a rule weight dynamically changes the forensic score for a cached OCR entry."""
    client = TestClient(create_app())

    # Default critical weight = 35; SYN-0031 has lookalike_domain (critical) in cached OCR
    resp1 = client.post("/api/ocr/sample/SYN-0031?allow_fallback=false")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["from_cache"] is True
    assert "ocr" in data1 and "forensics" in data1
    score_default = data1["forensics"]["risk_score"]
    crit_points_default = next(
        f["points"]
        for f in data1["forensics"]["findings"]
        if f["severity"] == "critical"
    )
    assert crit_points_default == 35

    # Modify SEVERITY_WEIGHTS["critical"] in memory and call the endpoint again on the SAME cached OCR entry
    monkeypatch.setitem(SEVERITY_WEIGHTS, "critical", 50)
    resp2 = client.post("/api/ocr/sample/SYN-0031?allow_fallback=false")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["from_cache"] is True
    score_modified = data2["forensics"]["risk_score"]
    crit_points_modified = next(
        f["points"]
        for f in data2["forensics"]["findings"]
        if f["severity"] == "critical"
    )
    assert crit_points_modified == 50
    assert score_modified != score_default


def test_pib_overlay_filter_ignores_overlay_lines_and_preserves_char_offsets() -> None:
    """11. PIB Fact Check overlay lines are stripped before forensics, and char offsets map back to original text."""
    text = (
        "#PIBFactCheck\n"
        "यह पत्र फ़र्ज़ी है\n"
        "The letter is FAKE\n"
        "GOVERMENT OF INDIA\n"
        "MINISTRY OF HOME AFFAIRS\n"
        "Visit https://mina.gov.is for registration.\n"
        "FAKE\n"
        "socialmedia@pib.gov.in\n"
        "+91 8799711259"
    )
    res = run_forensics(_ocr_from_text(text))
    assert res.overlay_filtered_count == 6
    assert len(res.overlay_line_spans) == 6
    # Verify that every finding's char_start:char_end slices the exact evidence from the original text
    for f in res.findings:
        if f.char_end > f.char_start:
            assert text[f.char_start : f.char_end] == f.evidence
    # Ensure socialmedia@pib.gov.in and t.me/PIB_FactCheck are not falsely treated as document content
    cues = {f.cue_id for f in res.findings}
    assert "spelling_errors" in cues
    assert "lookalike_domain" in cues


def test_payment_to_account_positive_and_negative_rbi_circular() -> None:
    """12. payment_to_account fires on payment instruction near account/IFSC, NOT on RBI circular about savings accounts."""
    # Positive case: direct instruction to pay/deposit within 2 lines of account/IFSC
    scam_text = (
        "Ministry of New and Renewable Energy\n"
        "Applicant must deposit the registration amount into the following account:\n"
        "A/c No.: 32462666959\n"
        "IFSC: SBIN0008384"
    )
    res_pos = run_forensics(_ocr_from_text(scam_text))
    cues_pos = {f.cue_id for f in res_pos.findings}
    assert "payment_to_account" in cues_pos
    pta = next(f for f in res_pos.findings if f.cue_id == "payment_to_account")
    assert pta.severity == "critical"
    assert pta.points == 35
    assert scam_text[pta.char_start : pta.char_end] == pta.evidence

    # Negative case: RBI circular sentence describing savings accounts without a payment instruction
    rbi_circular_text = (
        "Reserve Bank of India\n"
        "Master Direction - Know Your Customer (KYC) Direction, 2026\n"
        "Regulated entities shall ensure that periodic updation of KYC records is carried out "
        "for all savings account holders and current account customers in accordance with risk categorization."
    )
    res_neg = run_forensics(_ocr_from_text(rbi_circular_text))
    cues_neg = {f.cue_id for f in res_neg.findings}
    assert "payment_to_account" not in cues_neg
    assert res_neg.risk_level == "low"
    assert res_neg.risk_score == 0


def test_loan_sanction_offer_positive_individual_and_negative_bank_circular() -> None:
    """13. Loan sanction offer fires when addressed to an individual, NOT on a circular to banks mentioning loan disbursement."""
    # Positive case: loan approved + amount on a letter addressed to an individual
    individual_letter = (
        "Pradhan Mantri Mudra Yojana\n"
        "Dear Sir/Madam,\n"
        "We are pleased to inform you that your Mudra loan approved for Rs. 5,00,000/- "
        "has been sanctioned in favour of the applicant."
    )
    res_pos = run_forensics(_ocr_from_text(individual_letter))
    cues_pos = {f.cue_id for f in res_pos.findings}
    assert "too_good_offer" in cues_pos
    tgo = next(f for f in res_pos.findings if f.cue_id == "too_good_offer")
    assert tgo.severity == "warning"
    assert tgo.points == 15
    assert individual_letter[tgo.char_start : tgo.char_end] == tgo.evidence

    # Negative case: official circular addressed to banks/institutions mentioning loan disbursement
    bank_circular = (
        "Reserve Bank of India\n"
        "To,\n"
        "All Scheduled Commercial Banks and Regional Rural Banks\n"
        "Madam / Dear Sir,\n"
        "Subject: Quarterly reporting of priority sector loan disbursed above Rs. 10,00,000\n"
        "Banks are advised to report all agricultural loans sanctioned and loan disbursed during the quarter."
    )
    res_neg = run_forensics(_ocr_from_text(bank_circular))
    cues_neg = {f.cue_id for f in res_neg.findings}
    assert "too_good_offer" not in cues_neg
    assert res_neg.risk_level == "low"
    assert res_neg.risk_score == 0
