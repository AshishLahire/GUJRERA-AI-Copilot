"""Stage 2b forensic check runner: executes all checks on an OCRResult and computes risk score/level."""

from __future__ import annotations

from typing import Literal

from factcheck.extract.ocr.fields import extract_fields
from factcheck.forensics.checks import (
    check_date_anomalies,
    check_domains,
    check_fee_demand,
    check_mixed_issuers,
    check_payment_to_account,
    check_personal_contact,
    check_reference_number,
    check_registry_rules,
    check_spelling_errors,
    check_too_good_offer,
    check_urgency_threat,
    detect_issuer,
    filter_pib_overlay_lines,
    map_cleaned_span_to_original,
)
from factcheck.forensics.rules import RISK_THRESHOLDS, SEVERITY_WEIGHTS
from factcheck.schemas import ForensicFinding, ForensicResult, OCRResult

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def run_forensics(ocr_result: OCRResult, is_audio: bool = False, transcript_transliterated: bool = False) -> ForensicResult:
    """Run all rule-based forensic checks on ``ocr_result`` and return a ``ForensicResult``.

    For audio transcripts (``is_audio=True``), runs only text rules (fee demand, urgency,
    too-good offer, domains, phones) and skips document-only checks (letterhead, reference
    format, date anomalies, signatory/spelling).
    Filters out PIB fact-check overlay lines before running checks, then maps all
    ``char_start`` / ``char_end`` spans back to ``ocr_result.final_text`` so UI highlights
    and greyed-out overlay tags align with the displayed text.
    """
    raw_text = ocr_result.final_text or ""
    cleaned_text, overlay_spans, line_map = filter_pib_overlay_lines(raw_text)

    # Re-extract fields on the overlay-filtered text so PIB overlay URLs/phones/emails are ignored
    fields = extract_fields(cleaned_text, strip_watermark=False)

    issuer = detect_issuer(cleaned_text)

    findings: list[ForensicFinding] = []
    # Text-based rules applicable to both documents and audio voice notes:
    is_translit = transcript_transliterated or getattr(ocr_result, "transcript_transliterated", False)
    findings.extend(check_domains(cleaned_text, fields, issuer))
    findings.extend(check_fee_demand(cleaned_text, fields, transliterated=is_translit))
    findings.extend(check_payment_to_account(cleaned_text))
    findings.extend(check_urgency_threat(cleaned_text, transliterated=is_translit))
    findings.extend(check_too_good_offer(cleaned_text, fields, transliterated=is_translit))
    findings.extend(check_personal_contact(cleaned_text, fields, issuer))

    # Document-only checks (skipped for audio transcripts):
    if not is_audio:
        findings.extend(check_mixed_issuers(cleaned_text))
        findings.extend(check_reference_number(cleaned_text, fields, issuer))
        findings.extend(check_spelling_errors(cleaned_text))
        findings.extend(check_date_anomalies(cleaned_text, fields))
        findings.extend(check_registry_rules(cleaned_text, issuer))

    # Map cleaned_text spans back to raw_text (displayed final_text) and compute dynamic points
    for f in findings:
        orig_s, orig_e = map_cleaned_span_to_original(
            f.char_start,
            f.char_end,
            line_map,
            raw_text,
            f.evidence,
        )
        f.char_start = orig_s
        f.char_end = orig_e
        f.points = SEVERITY_WEIGHTS.get(f.severity, 0)

    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9), f.char_start))

    raw_score = sum(f.points for f in findings)
    risk_score = min(100, max(0, raw_score))

    risk_level: Literal["low", "medium", "high"]
    if risk_score >= RISK_THRESHOLDS["high"]:
        risk_level = "high"
    elif risk_score >= RISK_THRESHOLDS["medium"]:
        risk_level = "medium"
    else:
        risk_level = "low"

    translit_note = (
        "Transcript is in a different script than the spoken language: checks may miss warning signs. Ran Hindi and English keyword lists only."
        if is_translit else None
    )
    return ForensicResult(
        risk_level=risk_level,
        risk_score=risk_score,
        detected_issuer=issuer,
        findings=findings,
        overlay_filtered_count=len(overlay_spans),
        overlay_line_spans=overlay_spans,
        transcript_transliterated=is_translit,
        transliteration_note=translit_note,
    )
