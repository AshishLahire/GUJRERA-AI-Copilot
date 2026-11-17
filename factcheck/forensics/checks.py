"""Rule-based forensic checks (a through k) operating on OCRResult text and extracted fields."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Literal

from factcheck.extract.ocr.fields import _levenshtein_distance, _normalize_hostname
from factcheck.forensics.rules import (
    ACCOUNT_DETAIL_RE,
    FEE_NEGATION_RE,
    FEE_PAYMENT_PATTERNS,
    FREE_EMAIL_DOMAINS,
    INDIVIDUAL_ADDRESSEE_RE,
    INSTITUTIONAL_ADDRESSEE_RE,
    ISSUER_ALIASES,
    KNOWN_MISSPELLINGS,
    LOAN_SANCTION_OFFER_RE,
    MIXED_AGENCY_GROUPS,
    OFFICIAL_HELPLINE_NUMBERS,
    OFFICIAL_TERM_GLOSSARY,
    PAYMENT_INSTRUCTION_RE,
    PIB_OVERLAY_LINE_PATTERNS,
    SEVERITY_WEIGHTS,
    SPELLING_ALLOWLIST,
    TOO_GOOD_OFFER_PATTERNS,
    URGENCY_THREAT_PATTERNS,
    load_issuer_registry,
    load_official_corpus_references,
)
from factcheck.schemas import (
    DetectedIssuer,
    ExtractedFields,
    ForensicFinding,
    OverlayLineSpan,
)


def _make_finding(
    *,
    cue_id: str,
    severity: Literal["info", "warning", "critical"],
    title: str,
    explanation: str,
    evidence: str,
    char_start: int,
    char_end: int,
    rule_status: Literal["verified", "unverified"] = "verified",
) -> ForensicFinding:
    return ForensicFinding(
        cue_id=cue_id,
        severity=severity,
        points=SEVERITY_WEIGHTS.get(severity, 0),
        title=title,
        explanation=explanation,
        evidence=evidence,
        char_start=max(0, char_start),
        char_end=max(0, char_end),
        rule_status=rule_status,
    )


def _find_span(text: str, snippet: str) -> tuple[int, int]:
    if not text or not snippet:
        return (0, 0)
    idx = text.find(snippet)
    if idx >= 0:
        return (idx, idx + len(snippet))
    idx_ci = text.lower().find(snippet.lower())
    if idx_ci >= 0:
        return (idx_ci, idx_ci + len(snippet))
    return (0, 0)


def filter_pib_overlay_lines(
    text: str,
) -> tuple[str, list[OverlayLineSpan], list[tuple[int, int]]]:
    """Filter out PIB fact-check overlay lines before forensics while preserving character offset mapping.

    Returns:
        cleaned_text: text with PIB overlay lines removed
        overlay_spans: list of ``OverlayLineSpan(char_start, char_end)`` in original ``text``
        line_map: list of ``(cleaned_line_start, original_line_start)`` for translating spans back to ``text``
    """
    if not text:
        return "", [], []

    overlay_spans: list[OverlayLineSpan] = []
    kept_lines: list[tuple[str, int]] = []
    pos = 0
    for line_with_end in text.splitlines(keepends=True):
        raw_line = line_with_end.rstrip("\r\n")
        line_start = pos
        line_end = pos + len(raw_line)
        pos += len(line_with_end)

        stripped = raw_line.strip()
        is_overlay = False
        if stripped:
            for pat in PIB_OVERLAY_LINE_PATTERNS:
                if pat.search(stripped):
                    is_overlay = True
                    break

        if is_overlay:
            overlay_spans.append(OverlayLineSpan(char_start=line_start, char_end=line_end))
        else:
            kept_lines.append((raw_line, line_start))

    cleaned_parts: list[str] = []
    line_map: list[tuple[int, int]] = []
    cleaned_pos = 0
    for idx, (raw_line, orig_start) in enumerate(kept_lines):
        line_map.append((cleaned_pos, orig_start))
        cleaned_parts.append(raw_line)
        cleaned_pos += len(raw_line)
        if idx < len(kept_lines) - 1:
            cleaned_parts.append("\n")
            cleaned_pos += 1

    return "".join(cleaned_parts), overlay_spans, line_map


def map_cleaned_span_to_original(
    char_start: int,
    char_end: int,
    line_map: list[tuple[int, int]],
    original_text: str,
    evidence: str,
) -> tuple[int, int]:
    """Translate ``[char_start, char_end)`` from ``cleaned_text`` back to ``original_text``."""
    if not original_text:
        return (0, 0)
    if not line_map or char_end <= char_start:
        return _find_span(original_text, evidence)

    # Locate the line in line_map whose cleaned_line_start <= char_start
    chosen_clean_start, chosen_orig_start = line_map[0]
    for c_start, o_start in line_map:
        if c_start <= char_start:
            chosen_clean_start, chosen_orig_start = c_start, o_start
        else:
            break

    offset_in_line = char_start - chosen_clean_start
    orig_start = chosen_orig_start + offset_in_line
    orig_end = orig_start + (char_end - char_start)
    if (
        0 <= orig_start < orig_end <= len(original_text)
        and evidence
        and original_text[orig_start:orig_end].lower() == evidence.lower()
    ):
        return (orig_start, orig_end)
    return _find_span(original_text, evidence)


def detect_issuer(text: str) -> DetectedIssuer | None:
    """(a) Detect the primary issuing authority from text, weighting the first 15 lines (letterhead) 3x higher."""
    if not text or not text.strip():
        return None
    registry = load_issuer_registry()
    lines = text.splitlines()
    header_text = "\n".join(lines[:15])
    body_text = "\n".join(lines[15:])

    best_id: str | None = None
    best_score = 0
    best_first_pos = len(text) + 1

    for issuer_id, aliases in ISSUER_ALIASES.items():
        if issuer_id not in registry:
            continue
        score = 0
        first_pos = len(text) + 1
        for alias in aliases:
            if not alias:
                continue
            # Use word boundaries for short ASCII acronyms
            if re.fullmatch(r"[A-Za-z0-9\-]+", alias) and len(alias) <= 6:
                pat = re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE)
            else:
                pat = re.compile(re.escape(alias), re.IGNORECASE)

            header_matches = list(pat.finditer(header_text))
            body_matches = list(pat.finditer(body_text))
            if header_matches or body_matches:
                # Longer full-name matches get slightly higher weight than short acronyms
                length_bonus = 2 if len(alias) > 10 else 1
                score += len(header_matches) * 3 * length_bonus + len(body_matches) * 1 * length_bonus
                for m in header_matches:
                    first_pos = min(first_pos, m.start())
                for m in body_matches:
                    first_pos = min(first_pos, len(header_text) + 1 + m.start())

        if score > best_score or (score > 0 and score == best_score and first_pos < best_first_pos):
            best_score = score
            best_id = issuer_id
            best_first_pos = first_pos

    if best_id is None:
        return None
    entry = registry[best_id]
    return DetectedIssuer(
        issuer_id=best_id,
        name=entry.get("name_en", best_id),
    )


def check_mixed_issuers(text: str) -> list[ForensicFinding]:
    """(b) Flag letters that mix multiple unrelated enforcement/judicial/ministry agencies."""
    if not text:
        return []
    matched_agencies: list[tuple[str, str, re.Match[str]]] = []
    seen_codes: set[str] = set()
    for code, label, pat in MIXED_AGENCY_GROUPS:
        m = pat.search(text)
        if m and code not in seen_codes:
            seen_codes.add(code)
            matched_agencies.append((code, label, m))

    # Flag if 3+ agencies appear, or specific known incompatible pairs (Supreme Court + Ministry of Finance,
    # Ministry of Commerce + Ministry of Civil Aviation, I4C + CBI/INTERPOL/IB/Delhi Police)
    codes = {c for c, _, _ in matched_agencies}
    incompatible_pair = (
        ("SCI" in codes and "MOF" in codes)
        or ("MOCI" in codes and "MOCA" in codes)
        or ("I4C" in codes and bool(codes & {"CBI", "INTERPOL", "IB", "DELHI_POLICE"}))
        or ("IB" in codes and "RAW" in codes)
    )
    if len(matched_agencies) >= 3 or incompatible_pair:
        first_m = matched_agencies[0][2]
        names = ", ".join(lbl for _, lbl, _ in matched_agencies)
        return [
            _make_finding(
                cue_id="mixed_issuers",
                severity="warning",
                title="Multiple unrelated agencies cited on one notice",
                explanation=(
                    f"This document combines multiple distinct authorities ({names}), "
                    "a common pattern in composite scam notices."
                ),
                evidence=first_m.group(0),
                char_start=first_m.start(),
                char_end=first_m.end(),
            )
        ]
    return []


def _clean_ref_prefix(ref: str) -> str:
    """Strip leading 'No.' or 'Ref:' prefixes when checking corpus or regex format."""
    cleaned = re.sub(r"\s+", " ", ref.strip())
    cleaned = re.sub(
        r"^(?:(?:Circular|Cir|Order|Ref(?:erence)?|File|Letter|Notification)\s*\.?\s*)?(?:No\.?|Ref\s*:)\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def check_reference_number(
    text: str,
    fields: ExtractedFields,
    issuer: DetectedIssuer | None,
) -> list[ForensicFinding]:
    """(c) Validate reference number format against verified issuer patterns and look up in official corpus."""
    if issuer is None or not fields.reference_numbers:
        return []

    registry = load_issuer_registry()
    entry = registry.get(issuer.issuer_id, {})
    patterns = entry.get("reference_patterns", [])
    verified_patterns = [p for p in patterns if p.get("status") == "verified"]
    corpus_refs = load_official_corpus_references()

    findings: list[ForensicFinding] = []
    # Check if any extracted reference (or its prefix-stripped form) is in the official corpus (02)
    for ref in fields.reference_numbers:
        candidates = [
            re.sub(r"\s+", " ", ref.strip()).upper(),
            _clean_ref_prefix(ref).upper(),
        ]
        for norm in candidates:
            if norm and norm in corpus_refs:
                r_start, r_end = _find_span(text, ref)
                findings.append(
                    _make_finding(
                        cue_id="ref_status",
                        severity="info",
                        title="Reference number: matches official record",
                        explanation=(
                            f"Reference '{ref}' matches official document "
                            f"{corpus_refs[norm].get('doc_id')} in the official corpus."
                        ),
                        evidence=ref,
                        char_start=r_start,
                        char_end=r_end,
                    )
                )
                return findings

    header_text = "\n".join(text.splitlines()[:15])
    header_refs = [r for r in fields.reference_numbers if r in header_text]
    if not header_refs:
        return []

    primary_ref = header_refs[0]
    start, end = _find_span(text, primary_ref)

    if not verified_patterns:
        findings.append(
            _make_finding(
                cue_id="ref_status",
                severity="info",
                title="Reference number: no pattern available for this issuer",
                explanation=(
                    f"No verified reference-number regex is registered for {issuer.name}; "
                    "format could not be checked automatically."
                ),
                evidence=primary_ref,
                char_start=start,
                char_end=end,
            )
        )
        return findings

    # Check if ANY header reference (or its prefix-stripped form) matches any verified pattern for this issuer
    any_valid = False
    matched_ref = primary_ref
    for ref in header_refs:
        for cand in (ref.strip(), _clean_ref_prefix(ref)):
            for pat_entry in verified_patterns:
                rx = pat_entry.get("regex", "")
                if rx and cand and re.fullmatch(rx, cand):
                    any_valid = True
                    matched_ref = ref
                    break
            if any_valid:
                break
        if any_valid:
            break

    if any_valid:
        m_start, m_end = _find_span(text, matched_ref)
        findings.append(
            _make_finding(
                cue_id="ref_status",
                severity="info",
                title="Reference number: format valid but not in our sample records",
                explanation=(
                    f"Reference '{matched_ref}' follows {issuer.issuer_id}'s verified house format, "
                    "though it is not among the sample documents in our offline corpus."
                ),
                evidence=matched_ref,
                char_start=m_start,
                char_end=m_end,
            )
        )
    else:
        expected_names = ", ".join(p.get("name", "house format") for p in verified_patterns)
        findings.append(
            _make_finding(
                cue_id="ref_format_wrong",
                severity="warning",
                title="Reference number: format does not match issuer pattern",
                explanation=(
                    f"Reference '{primary_ref}' does not match {issuer.name}'s verified "
                    f"format ({expected_names})."
                ),
                evidence=primary_ref,
                char_start=start,
                char_end=end,
            )
        )
    return findings


def check_domains(
    text: str,
    fields: ExtractedFields,
    issuer: DetectedIssuer | None,
) -> list[ForensicFinding]:
    """(d) Flag suspicious or lookalike domains as critical findings."""
    findings: list[ForensicFinding] = []
    flagged_hosts: list[str] = list(fields.suspicious_domains)

    # Also check if a fictional synthetic issuer points to a non-.example domain
    if issuer and issuer.issuer_id.startswith("FIC-"):
        registry = load_issuer_registry()
        off_doms = {
            d.lower() for d in registry.get(issuer.issuer_id, {}).get("official_domains", [])
        }
        for u in fields.urls:
            host = _normalize_hostname(u)
            if host and host not in off_doms and not host.endswith(".example"):
                if host not in flagged_hosts:
                    flagged_hosts.append(host)

    for host in flagged_hosts:
        # Locate raw URL/domain in text for accurate highlight span
        evidence_str = host
        start, end = _find_span(text, host)
        for u in fields.urls:
            if host in u.lower():
                u_start, u_end = _find_span(text, u)
                if u_end > u_start:
                    evidence_str = u
                    start, end = u_start, u_end
                    break

        findings.append(
            _make_finding(
                cue_id="lookalike_domain",
                severity="critical",
                title="Suspicious or lookalike domain",
                explanation=(
                    f"Domain '{host}' is not an official government domain (.gov.in / .nic.in) "
                    "or closely imitates an official issuer domain."
                ),
                evidence=evidence_str,
                char_start=start,
                char_end=end,
            )
        )
    return findings


def check_personal_contact(
    text: str,
    fields: ExtractedFields,
    issuer: DetectedIssuer | None,
) -> list[ForensicFinding]:
    """(e) Flag free-mail addresses (gmail/yahoo/outlook) or personal mobile numbers on official notices."""
    findings: list[ForensicFinding] = []

    for email in fields.emails:
        parts = email.lower().split("@")
        if len(parts) == 2 and parts[1] in FREE_EMAIL_DOMAINS:
            start, end = _find_span(text, email)
            findings.append(
                _make_finding(
                    cue_id="personal_contact",
                    severity="warning",
                    title="Free-mail address used as official contact",
                    explanation=(
                        f"Official government communications do not use personal webmail "
                        f"accounts such as '{email}'."
                    ),
                    evidence=email,
                    char_start=start,
                    char_end=end,
                )
            )
            return findings

    # Ensure phone numbers inside reference/ID codes (e.g. NHM7798904510) are not flagged as personal mobile numbers
    for phone in fields.phone_numbers:
        digits = re.sub(r"\D", "", phone)
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            digits = digits[1:]
        if digits.startswith("1800") or digits in OFFICIAL_HELPLINE_NUMBERS:
            continue
        if len(digits) == 10 and digits[0] in "6789":
            start, end = _find_span(text, phone)
            if start > 0 and text[start - 1].isalpha():
                continue
            findings.append(
                _make_finding(
                    cue_id="personal_contact",
                    severity="warning",
                    title="Personal mobile number given as contact",
                    explanation=(
                        f"A 10-digit mobile number ('{phone}') is listed as the contact channel "
                        "instead of an official landline or helpline."
                    ),
                    evidence=phone,
                    char_start=start,
                    char_end=end,
                )
            )
            return findings

    return findings


def check_payment_to_account(text: str) -> list[ForensicFinding]:
    """2(a) Flag instructions to pay/transfer/deposit within 2 lines of an account number, IFSC, or A/c No."""
    if not text:
        return []

    lines = text.splitlines()
    if not lines:
        return []

    # Precompute line start offsets in `text`
    line_starts: list[int] = []
    pos = 0
    for ln in text.splitlines(keepends=True):
        line_starts.append(pos)
        pos += len(ln)

    account_lines: list[tuple[int, re.Match[str]]] = []
    payment_lines: list[tuple[int, re.Match[str]]] = []

    for i, ln in enumerate(lines):
        m_acc = ACCOUNT_DETAIL_RE.search(ln)
        if m_acc:
            account_lines.append((i, m_acc))
        m_pay = PAYMENT_INSTRUCTION_RE.search(ln)
        if m_pay:
            # Ignore negated payment words on that line
            abs_s = line_starts[i] + m_pay.start()
            abs_e = line_starts[i] + m_pay.end()
            if not _is_negated_nearby(text, abs_s, abs_e):
                payment_lines.append((i, m_pay))

    if not account_lines or not payment_lines:
        return []

    for acc_idx, m_acc in account_lines:
        for pay_idx, _ in payment_lines:
            if abs(acc_idx - pay_idx) <= 2:
                ev = m_acc.group(0).strip()
                c_start = line_starts[acc_idx] + m_acc.start()
                c_end = line_starts[acc_idx] + m_acc.end()
                is_upi = "@" in ev
                finding_title = (
                    "Direct bank account or UPI payment instruction"
                    if is_upi
                    else "Direct bank account payment instruction"
                )
                finding_expl = (
                    f"Instructs the recipient to pay or transfer funds directly to a UPI account ('{ev}')."
                    if is_upi
                    else (
                        "Instructs the recipient to deposit or transfer funds directly into "
                        f"a specified bank account or IFSC ('{ev}') within 2 lines."
                    )
                )
                return [
                    _make_finding(
                        cue_id="payment_to_account",
                        severity="critical",
                        title=finding_title,
                        explanation=finding_expl,
                        evidence=ev,
                        char_start=c_start,
                        char_end=c_end,
                    )
                ]
    return []


def _is_negated_nearby(text: str, start: int, end: int) -> bool:
    """Return True only if a fee negation phrase directly modifies the fee word (within ~3 words).

    A bare 'free' or negation elsewhere in the message (e.g. 'free laptop') must NOT suppress it.
    """
    for m in FEE_NEGATION_RE.finditer(text):
        ns, ne = m.span()
        # Case 1: Overlaps the fee match span directly
        if ns <= end and ne >= start:
            return True
        # Case 2: Negation immediately precedes the fee match within ~3 words
        if ne <= start:
            intervening = text[ne:start]
            if not re.search(r"[\n\r.!?।;]", intervening):
                if len(intervening.strip().split()) <= 3:
                    return True
        # Case 3: Negation immediately follows the fee match within ~3 words
        elif ns >= end:
            intervening = text[end:ns]
            if not re.search(r"[\n\r.!?।;]", intervening):
                if len(intervening.strip().split()) <= 3:
                    return True
    return False


def check_fee_demand(text: str, fields: ExtractedFields, transliterated: bool = False) -> list[ForensicFinding]:
    """(f) Flag demands for registration, processing, file, or penalty fees (with negation handling)."""
    if not text:
        return []

    pats = FEE_PAYMENT_PATTERNS[:2] if transliterated else FEE_PAYMENT_PATTERNS
    for pat in pats:
        for m in pat.finditer(text):
            start, end = m.span()
            if _is_negated_nearby(text, start, end):
                continue
            evidence = m.group(0).strip()
            return [
                _make_finding(
                    cue_id="fee_demand",
                    severity="critical",
                    title="Payment or fee demand detected",
                    explanation=(
                        "Asks the recipient to pay a registration, processing, file, "
                        "or penalty charge — a primary indicator of financial fraud."
                    ),
                    evidence=evidence,
                    char_start=start,
                    char_end=end,
                )
            ]
    return []


def check_urgency_threat(text: str, transliterated: bool = False) -> list[ForensicFinding]:
    """(g) Flag 24-hour deadlines, arrest threats, account/SIM blocking threats, or panic triggers."""
    if not text:
        return []

    pats = URGENCY_THREAT_PATTERNS[:2] if transliterated else URGENCY_THREAT_PATTERNS
    for pat in pats:
        m = pat.search(text)
        if m:
            return [
                _make_finding(
                    cue_id="urgency_threat",
                    severity="warning",
                    title="Urgency deadline or coercive threat",
                    explanation=(
                        "Uses a short deadline (e.g., 24 hours / tonight) or threatens arrest, "
                        "legal action, or immediate service blocking to force quick compliance."
                    ),
                    evidence=m.group(0).strip(),
                    char_start=m.start(),
                    char_end=m.end(),
                )
            ]
    return []


def check_too_good_offer(text: str, fields: ExtractedFields | None = None, transliterated: bool = False) -> list[ForensicFinding]:
    """(h) Flag unrealistic benefits or individual loan sanction/approval offers."""
    if not text:
        return []

    pats = TOO_GOOD_OFFER_PATTERNS[:2] if transliterated else TOO_GOOD_OFFER_PATTERNS
    for pat in pats:
        for m in pat.finditer(text):
            start, end = m.span()
            # Ensure benign "free of cost" / "toll free" isn't matched
            ctx = text[max(0, start - 20) : min(len(text), end + 25)].lower()
            if "free of cost" in ctx or "toll free" in ctx or "toll-free" in ctx:
                continue
            return [
                _make_finding(
                    cue_id="too_good_offer",
                    severity="warning",
                    title="Unrealistic benefit or windfall offer",
                    explanation=(
                        "Promises an unusually large payout, grant, monthly tower rent, "
                        "or free hardware giveaway typical of lure-based scams."
                    ),
                    evidence=m.group(0).strip(),
                    char_start=start,
                    char_end=end,
                )
            ]

    # Rule 2(b): Loan sanction / approval offer + amount on a letter addressed to an individual
    has_amount = bool(fields and fields.rupee_amounts) or bool(
        re.search(r"(?:₹|Rs\.?|INR|रु\.?)\s*\d[\d,]*|\b\d+\s*(?:lakh|lakhs|लाख)\b", text, re.IGNORECASE)
    )
    if (
        has_amount
        and INDIVIDUAL_ADDRESSEE_RE.search(text)
        and not INSTITUTIONAL_ADDRESSEE_RE.search(text)
    ):
        m_loan = LOAN_SANCTION_OFFER_RE.search(text)
        if m_loan:
            return [
                _make_finding(
                    cue_id="too_good_offer",
                    severity="warning",
                    title="Individual loan sanction offer",
                    explanation=(
                        "Announces direct loan approval or sanction with a specific rupee amount "
                        "to an individual recipient."
                    ),
                    evidence=m_loan.group(0).strip(),
                    char_start=m_loan.start(),
                    char_end=m_loan.end(),
                )
            ]

    return []


def check_spelling_errors(text: str) -> list[ForensicFinding]:
    """(i) Flag misspellings of official English terms in headings and body."""
    if not text:
        return []

    for m in re.finditer(r"\b[A-Za-z]{6,18}\b", text):
        word = m.group(0)
        low = word.lower()
        if low in SPELLING_ALLOWLIST or low in OFFICIAL_TERM_GLOSSARY:
            continue

        # 1. Explicit known misspelling table
        if low in KNOWN_MISSPELLINGS:
            correct = KNOWN_MISSPELLINGS[low]
            return [
                _make_finding(
                    cue_id="spelling_errors",
                    severity="warning",
                    title="Spelling error in official terminology",
                    explanation=(
                        f"Found '{word}' (expected '{correct}'). Spelling mistakes in "
                        "official terms or headings are a common indicator of forged notices."
                    ),
                    evidence=word,
                    char_start=m.start(),
                    char_end=m.end(),
                )
            ]

        # 2. Fuzzy match (edit distance 1) against official glossary terms of length >= 8
        # Do not flag pure 1-character prefix/suffix truncations (e.g. PDF line-wrap splits like 'circula')
        for term in OFFICIAL_TERM_GLOSSARY:
            if len(term) >= 8 and abs(len(low) - len(term)) <= 1:
                if term.startswith(low) or term.endswith(low):
                    continue
                if _levenshtein_distance(low, term) == 1:
                    return [
                        _make_finding(
                            cue_id="spelling_errors",
                            severity="warning",
                            title="Spelling error in official terminology",
                            explanation=(
                                f"Found '{word}' (close misspelling of '{term.capitalize()}'). "
                                "Spelling errors in core terminology suggest a non-official source."
                            ),
                            evidence=word,
                            char_start=m.start(),
                            char_end=m.end(),
                        )
                    ]
    return []


def _parse_date_string(raw: str) -> date | None:
    s = re.sub(r"\s+", " ", raw.strip()).replace(",", "")
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%B %d %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def check_date_anomalies(text: str, fields: ExtractedFields) -> list[ForensicFinding]:
    """(j) Flag impossible calendar dates (e.g. 31/02/2026) or future issue dates."""
    if not text:
        return []

    # 1. Scan raw numeric dates DD/MM/YYYY or YYYY-MM-DD for impossible calendar days
    numeric_date_re = re.compile(r"\b(\d{1,2})[/.\\-](\d{1,2})[/.\\-]((?:19|20)\d{2})\b")
    for m in numeric_date_re.finditer(text):
        day_s, month_s, year_s = m.group(1), m.group(2), m.group(3)
        day_i, month_i, year_i = int(day_s), int(month_s), int(year_s)
        if month_i < 1 or month_i > 12:
            return [
                _make_finding(
                    cue_id="date_anomaly",
                    severity="warning",
                    title="Impossible calendar date",
                    explanation=f"Date '{m.group(0)}' has an invalid month ({month_i}).",
                    evidence=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                )
            ]
        max_day = calendar.monthrange(year_i, month_i)[1]
        if day_i < 1 or day_i > max_day:
            return [
                _make_finding(
                    cue_id="date_anomaly",
                    severity="warning",
                    title="Impossible calendar date",
                    explanation=(
                        f"Date '{m.group(0)}' does not exist on the calendar "
                        f"(month {month_i:02d}/{year_i} has at most {max_day} days)."
                    ),
                    evidence=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                )
            ]

    # Also check textual dates like "February 30, 2026" or "31 February 2026"
    textual_date_re = re.compile(
        r"\b(?:"
        r"(?P<m1>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?P<d1>\d{1,2}),?\s+(?P<y1>(?:19|20)\d{2})"
        r"|(?P<d2>\d{1,2})\s+(?P<m2>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?),?\s+(?P<y2>(?:19|20)\d{2})"
        r")\b",
        re.IGNORECASE,
    )
    for m in textual_date_re.finditer(text):
        raw_d = m.group(0)
        if _parse_date_string(raw_d) is None:
            return [
                _make_finding(
                    cue_id="date_anomaly",
                    severity="warning",
                    title="Impossible calendar date",
                    explanation=f"Date '{raw_d}' is not a valid calendar date.",
                    evidence=raw_d,
                    char_start=m.start(),
                    char_end=m.end(),
                )
            ]

    # 2. Check header / issue date in the future relative to today
    today = date.today()
    header_lines = text.splitlines()[:10]
    for line in header_lines:
        low_line = line.lower()
        if any(
            kw in low_line
            for kw in (
                "auction",
                "reversal",
                "settlement",
                "conduct",
                "effect from",
                "until",
                "last date",
                "schedule",
            )
        ):
            continue
        for d_str in fields.dates:
            if d_str not in line:
                continue
            parsed = _parse_date_string(d_str)
            if parsed and parsed > today:
                start, end = _find_span(text, d_str)
                return [
                    _make_finding(
                        cue_id="date_anomaly",
                        severity="warning",
                        title="Issue date is in the future",
                        explanation=(
                            f"The document header date '{d_str}' ({parsed.isoformat()}) is in the future."
                        ),
                        evidence=d_str,
                        char_start=start,
                        char_end=end,
                    )
                ]

    return []


def check_registry_rules(
    text: str,
    issuer: DetectedIssuer | None,
) -> list[ForensicFinding]:
    """(k) Check issuer-specific 'never_does' and signatory title rules from 03_issuer_registry."""
    if not text or issuer is None:
        return []

    findings: list[ForensicFinding] = []
    registry = load_issuer_registry()
    entry = registry.get(issuer.issuer_id, {})

    # 1. Wrong signatory title (e.g. RBI using 'Chairman', or synthetic issuers using wrong signatory)
    wrong_title_patterns: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bCustomer\s+Care\s+Manager\b", re.IGNORECASE), "Customer Care Manager"),
        (re.compile(r"\bChairman\s*&\s*CEO\b", re.IGNORECASE), "Chairman & CEO"),
        (re.compile(r"\bChief\s+Commissioner\s*\(\s*Finance\s*\)", re.IGNORECASE), "Chief Commissioner (Finance)"),
        (re.compile(r"\bAdditional\s+Chief\s+Secretary\b", re.IGNORECASE), "Additional Chief Secretary"),
        (re.compile(r"\bBranch\s+Head\b", re.IGNORECASE), "Branch Head"),
    ]
    if issuer.issuer_id == "RBI":
        wrong_title_patterns.append(
            (re.compile(r"\bChairman\s*,?\s*Reserve\s+Bank\b|\bRBI\s+Chairman\b", re.IGNORECASE), "Chairman")
        )

    expected_head = entry.get("head_title")
    for pat, label in wrong_title_patterns:
        m = pat.search(text)
        if m:
            head_note = f" (expected '{expected_head}')" if expected_head else ""
            findings.append(
                _make_finding(
                    cue_id="wrong_signatory_title",
                    severity="warning",
                    title="Signatory title does not match issuer",
                    explanation=(
                        f"Uses signatory title '{label}' which does not exist in {issuer.name}{head_note}."
                    ),
                    evidence=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    rule_status="unverified",
                )
            )
            break

    # 2. Issuer-specific "never_does" behavioral checks (marked rule_status="unverified")
    issuer_never_rules: dict[str, list[tuple[re.Pattern[str], str]]] = {
        "RBI": [
            (
                re.compile(r"\b(?:old\s+coins|lottery|prize\s+money|purane\s+sikke)\b|पुराने\s+सिक्कों|जुन्या\s+नाण्यांच्या|পুরনো\s+কয়েনের|பழைய\s+நாணயங்களுக்கு|పాత\s+నాణేలకు", re.IGNORECASE),
                "RBI never sends letters offering prize money or purchasing old coins/notes from individuals.",
            ),
        ],
        "I4C": [
            (
                re.compile(r"\b(?:illegal\s+content|illegal\s+videos|POCSO|digital\s+arrest)\b|अवैध\s+सामग्री|बेकायदेशीर\s+सामग्री|অবৈধ\s+কনটেন্ট|சட்டவிரோத\s+உள்ளடக்கத்தைப்|అక్రమ\s+కంటెంట్", re.IGNORECASE),
                "I4C never sends letters accusing citizens of viewing illegal content or demanding replies within 24 hours.",
            ),
        ],
        "MUDRA": [
            (
                re.compile(r"\b(?:Mudra\s+Finance|file\s+charge|agreement\s+charge)\b|फाइल\s+चार्ज|फाइल\s+शुल्क|ফাইল\s+চার্জ|கோப்புக்\s+கட்டணம்|ఫైల్\s+ఛార్జీ", re.IGNORECASE),
                "PM Mudra Yojana refinances banks/NBFCs and never lends directly to individuals or demands file charges.",
            ),
        ],
        "TRAI": [
            (
                re.compile(r"\b(?:mobile\s+tower|5G\s+tower|SIM\s+KYC|SIM\s+will\s+be\s+blocked)\b|मोबाइल\s+टावर|मोबाईल\s+टॉवर|মোবাইল\s+টাওয়ার|மொபைல்\s+டவர்|మొబైల్\s+టవర్|सिम\s+का\s+केवाईसी|सिमचे\s+केवायसी|সিমের\s+কেওয়াইসি|சிம்\s+கேஒய்சி|సిమ్\s+కేవైసీ", re.IGNORECASE),
                "TRAI never leases private land for mobile towers or suspends individual SIM card KYC.",
            ),
        ],
        "MOE": [
            (
                re.compile(r"\b(?:free\s+laptop)\b|फ्री\s+लैपटॉप|मोफत\s+लॅपटॉप|ফ্রি\s+ল্যাপটপ|இலவச\s+மடிக்கணினி|ఉచిత\s+ల్యాప్‌టాప్", re.IGNORECASE),
                "The Ministry of Education does not run a 'PM Free Laptop Scheme'.",
            ),
        ],
        "OMC": [
            (
                re.compile(r"\b(?:LPG\s+Gas\s+Agency|Distributorship\s+is\s+APPROVED|petrol\s+&\s+diesel\s+price\s+hiked)\b|गैस\s+एजेंसी|गॅस\s+एजन्सी|গ্যাস\s+এজেন্সি|எரிவாயு\s+முகமை|గ్యాస్\s+ఏజెన్సీ", re.IGNORECASE),
                "Oil Marketing Companies do not pre-approve dealerships by letter in exchange for refundable deposits.",
            ),
        ],
        "MOP": [
            (
                re.compile(r"\b(?:electricity\s+connection\s+will\s+be\s+disconnected|disconnection\s+tonight)\b", re.IGNORECASE),
                "The Ministry of Power does not send electricity disconnection notices to individual consumers.",
            ),
        ],
        "SCI": [
            (
                re.compile(r"\b(?:deposit\s+penalty\s+amount|penalty\s+jama\s+karo)\b|जुर्माना\s+राशि\s+जमा|दंडाची\s+रक्कम\s+भरावी|জরিমানার\s+টাকা\s+জমা|அபராதத்\s+தொகையைச்|జరిమానా\s+మొత్తం", re.IGNORECASE),
                "The Supreme Court of India never orders individuals to transfer penalty funds via informal notices.",
            ),
        ],
    }

    for pat, explanation in issuer_never_rules.get(issuer.issuer_id, []):
        m = pat.search(text)
        if m:
            findings.append(
                _make_finding(
                    cue_id="issuer_never_does",
                    severity="warning",
                    title=f"Contradicts known {issuer.issuer_id} practice",
                    explanation=explanation,
                    evidence=m.group(0),
                    char_start=m.start(),
                    char_end=m.end(),
                    rule_status="unverified",
                )
            )
            break

    return findings
