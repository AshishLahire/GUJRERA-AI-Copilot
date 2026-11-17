"""RERA trust check: compare an ad or document against the GUJRERA registry.

Every check records what it compared, the text it found, and the registry
record it used, so the verdict is fully explainable. Nothing is decided by an
LLM here.

Verdicts (worst first):
    unreadable         too little text to check
    not_found          a RERA number is shown but is not in the registry
    lapsed_or_revoked  registration lapsed or revoked
    mismatch           promoter, possession date or agent differs from the registry
    no_rera_number     a property offer without any RERA number (s.11(2) requires it on ads)
    registered_with_warnings
    verified           registered, valid, and the stated details match
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select

from factcheck.extract.ocr.fields import extract_fields
from factcheck.forensics.checks import (
    check_domains,
    check_payment_to_account,
    check_too_good_offer,
    check_urgency_threat,
)
from gujrera.db.models import Approval, Promoter
from gujrera.db.repository import Repository
from gujrera.trust.extract import TrustClaim, extract_claim

MIN_TEXT_CHARS = 20
OPEN_COMPLAINTS_WARN = 5
BOOKING_LIMIT_PERCENT = 10.0  # s.13: no more than 10% before a registered agreement for sale
NAME_MATCH = 85  # fuzzy score for "this name appears in the text"
OTHER_PROMOTER_MATCH = 92  # stricter: naming a different registered promoter

GUJARAT_DISTRICTS = {
    "ahmedabad": "Ahmedabad", "અમદાવાદ": "Ahmedabad", "surat": "Surat", "સુરત": "Surat",
    "vadodara": "Vadodara", "baroda": "Vadodara", "વડોદરા": "Vadodara", "rajkot": "Rajkot",
    "રાજકોટ": "Rajkot", "gandhinagar": "Gandhinagar", "ગાંધીનગર": "Gandhinagar",
    "bhavnagar": "Bhavnagar", "ભાવનગર": "Bhavnagar",
}

# Severity order for picking the verdict.
VERDICT_ORDER = ["unreadable", "not_found", "lapsed_or_revoked", "mismatch", "no_rera_number",
                 "registered_with_warnings", "verified"]

# Native-speaker review pending for the Gujarati and Hindi strings.
HEADLINES = {
    "verified": {
        "en": "Registered with GUJRERA and the details match the registry",
        "gu": "GUJRERA માં નોંધાયેલ છે અને વિગતો રેકોર્ડ સાથે મેળ ખાય છે",
        "hi": "GUJRERA में पंजीकृत है और विवरण रिकॉर्ड से मेल खाते हैं",
    },
    "registered_with_warnings": {
        "en": "Registered, but check the warnings before you pay",
        "gu": "નોંધાયેલ છે, પણ ચુકવણી પહેલાં ચેતવણીઓ તપાસો",
        "hi": "पंजीकृत है, पर भुगतान से पहले चेतावनियाँ देखें",
    },
    "mismatch": {
        "en": "Details do not match the GUJRERA registry",
        "gu": "વિગતો GUJRERA રેકોર્ડ સાથે મેળ ખાતી નથી",
        "hi": "विवरण GUJRERA रिकॉर्ड से मेल नहीं खाते",
    },
    "not_found": {
        "en": "Registration not found in the GUJRERA registry",
        "gu": "આ નોંધણી નંબર GUJRERA રેકોર્ડમાં મળ્યો નથી",
        "hi": "यह पंजीकरण संख्या GUJRERA रिकॉर्ड में नहीं मिली",
    },
    "lapsed_or_revoked": {
        "en": "Registration has lapsed or been revoked",
        "gu": "નોંધણીની મુદત પૂરી થઈ ગઈ છે અથવા રદ થઈ છે",
        "hi": "पंजीकरण की अवधि समाप्त हो गई है या रद्द हो गया है",
    },
    "no_rera_number": {
        "en": "No RERA registration number shown",
        "gu": "કોઈ RERA નોંધણી નંબર દર્શાવેલ નથી",
        "hi": "कोई RERA पंजीकरण संख्या नहीं दिखाई गई",
    },
    "unreadable": {
        "en": "Could not read enough text to check",
        "gu": "તપાસ માટે પૂરતું લખાણ વાંચી શકાયું નથી",
        "hi": "जाँच के लिए पर्याप्त पाठ नहीं पढ़ा जा सका",
    },
}

NEXT_STEPS = {
    "verified": "Open the registry record and confirm the project page yourself before signing. "
                "Pay only to the project's designated bank account named in the agreement.",
    "registered_with_warnings": "Read each warning. Ask the promoter to explain them in writing, and check "
                                "the project's complaints and progress reports before paying.",
    "mismatch": "Do not pay yet. Ask the promoter for the registration certificate and compare it with the "
                "registry record shown here.",
    "not_found": "Do not pay. Ask for the registration certificate and search the number on the GUJRERA "
                 "portal. Unregistered sale or advertising can be reported to GUJRERA.",
    "lapsed_or_revoked": "Do not pay. The project cannot be sold under a lapsed or revoked registration. "
                         "Check the registry record for any extension order.",
    "no_rera_number": "Ask for the GUJRERA registration number. Advertisements for registered projects "
                      "must show it.",
    "unreadable": "Upload a clearer photo or paste the text of the ad.",
}


@dataclass
class Check:
    id: str
    status: str  # pass | fail | warn | info
    severity: str  # critical | warning | info
    title: str
    detail: str
    evidence: str | None = None
    source: dict[str, Any] | None = None
    verdict_hint: str | None = None  # the verdict this check forces when it fails


@dataclass
class TrustReport:
    verdict: str
    headline: dict[str, str]
    next_steps: str
    checks: list[Check]
    claim: dict[str, Any]
    records: list[dict[str, Any]] = field(default_factory=list)
    is_mock: bool = False
    as_of: date | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat() if self.as_of else None
        return d


def _core(name: str) -> str:
    return re.sub(r"\s*\((?:demo|ડેમો)\)\s*$", "", name or "", flags=re.IGNORECASE).strip()


def _mentioned(name: str | None, text_lc: str) -> float:
    core = _core(name or "").lower()
    if len(core) < 4:
        return 0.0
    if core in text_lc:
        return 100.0
    if len(core) < 8 or not stem_present(core, text_lc):
        return 0.0
    return float(fuzz.partial_ratio(core, text_lc))


def stem_present(name_lc: str, text_lc: str) -> bool:
    """The distinctive first word must appear (allowing a typo), so a shared suffix such as
    "Developers" or "Residency" cannot carry a fuzzy match on its own."""
    stem = name_lc.split()[0]
    if len(stem) < 4:
        return stem in text_lc.split()
    return fuzz.partial_ratio(stem, text_lc) >= 85


def check_text(text: str, repo: Repository, *, as_of: date | None = None) -> TrustReport:
    as_of = as_of or date.today()
    claim = extract_claim(text)
    checks: list[Check] = []
    records: list[dict[str, Any]] = []

    if len(claim.text.strip()) < MIN_TEXT_CHARS:
        checks.append(Check("readable", "fail", "critical", "Not enough text",
                            f"Only {len(claim.text.strip())} characters could be read.", verdict_hint="unreadable"))
        return _finish(checks, claim, records, as_of)

    text_lc = claim.text.lower()
    checks.extend(_forensic_checks(claim.text))

    if not claim.project_numbers:
        if claim.looks_like_property_offer:
            checks.append(Check(
                "rera_number_present", "fail", "warning", "No RERA registration number",
                "This looks like a property offer but shows no GUJRERA project registration number. "
                "Advertisements for real estate projects must show it (RERA Act, Section 11(2)).",
                verdict_hint="no_rera_number"))
        else:
            checks.append(Check("rera_number_present", "info", "info", "No RERA registration number",
                                "No GUJRERA project registration number was found in the text."))
    for number in claim.project_numbers:
        checks.extend(_check_project(number, claim, text_lc, repo, as_of, records))
    for number in claim.agent_numbers:
        checks.extend(_check_agent(number, repo, as_of, records))
    _check_booking(claim, checks)
    return _finish(checks, claim, records, as_of)


def _finish(checks: list[Check], claim: TrustClaim, records: list[dict[str, Any]], as_of: date) -> TrustReport:
    hints = {c.verdict_hint for c in checks if c.status == "fail" and c.verdict_hint}
    if not hints and any(c.status in ("fail", "warn") for c in checks):
        hints.add("registered_with_warnings")
    if not hints:
        hints.add("verified" if claim.project_numbers else "no_rera_number")
    verdict = min(hints, key=VERDICT_ORDER.index)
    # "verified" needs a found, valid registration; without one, say what is missing.
    if verdict == "verified" and not any(c.id == "registry_lookup" and c.status == "pass" for c in checks):
        verdict = "no_rera_number"
    status_rank = {"fail": 0, "warn": 1, "pass": 2, "info": 3}
    checks.sort(key=lambda c: status_rank.get(c.status, 9))
    return TrustReport(
        verdict=verdict, headline=HEADLINES[verdict], next_steps=NEXT_STEPS[verdict], checks=checks,
        claim=claim.to_dict(), records=records,
        is_mock=any(r.get("source", {}).get("is_mock") for r in records), as_of=as_of,
    )


def _forensic_checks(text: str) -> list[Check]:
    """Reuse Pramaan's text forensics for payment, urgency, offer and domain cues."""
    fields = extract_fields(text)
    findings = [
        *check_payment_to_account(text),
        *check_urgency_threat(text),
        *check_too_good_offer(text, fields),
        *check_domains(text, fields, None),
    ]
    out = []
    for f in findings:
        status = "warn"
        title = f.title
        detail = f.explanation
        if f.cue_id == "payment_to_account":
            title = "Payment asked to an account in the ad"
            detail = ("The ad asks for payment to an account number. Under RERA, buyer payments should go to "
                      "the project's designated bank account named in the registration and agreement. "
                      "Confirm the account with the promoter in writing before paying.")
        out.append(Check(f"forensic_{f.cue_id}", status, f.severity, title, detail, evidence=f.evidence))
    return out


def _check_project(number, claim: TrustClaim, text_lc: str, repo: Repository, as_of: date,
                   records: list[dict[str, Any]]) -> list[Check]:
    out: list[Check] = []
    project = repo.get_project(number.normalised)
    if project is None:
        out.append(Check(
            "registry_lookup", "fail", "critical", "Registration number not found",
            f"{number.normalised} is not in the GUJRERA registry data available to this copilot.",
            evidence=number.normalised, verdict_hint="not_found"))
        return out

    src = project["source"]
    records.append(project)
    exact = project["rera_no"] == number.normalised
    out.append(Check(
        "registry_lookup", "pass", "info", "Registration found",
        f"{project['name']} by {_core(project['promoter_name'])}, {project['district']}."
        + ("" if exact else f" The number in the document ({number.normalised}) differs from the registry "
                            f"({project['rera_no']}) in some segments."),
        evidence=number.normalised, source=src))
    if not exact:
        out.append(Check("number_segments", "warn", "warning", "Registration number partly differs",
                         f"Registry: {project['rera_no']}; document: {number.normalised}.",
                         evidence=number.normalised, source=src))
    if src.get("is_mock"):
        out.append(Check("mock_record", "info", "info", "Demo record",
                         "This registry record is mock data for the prototype, not a real GUJRERA project.",
                         source=src))

    # Registration validity
    valid_until = project["reg_valid_until"]
    if project["status"] == "revoked":
        out.append(Check("registration_valid", "fail", "critical", "Registration revoked",
                         "The registry shows this registration as revoked.", source=src,
                         verdict_hint="lapsed_or_revoked"))
    elif project["status"] == "lapsed" or (project["status"] != "completed" and valid_until < as_of):
        out.append(Check("registration_valid", "fail", "critical", "Registration lapsed",
                         f"Registration was valid until {valid_until.isoformat()} and no extension is recorded.",
                         source=src, verdict_hint="lapsed_or_revoked"))
    else:
        out.append(Check("registration_valid", "pass", "info", "Registration valid",
                         f"Status {project['status']}; valid until {valid_until.isoformat()}.", source=src))

    # Promoter named in the document
    out.append(_promoter_check(project, text_lc, repo))

    # Project name
    if max(_mentioned(project["name"], text_lc), _mentioned(project.get("name_gu"), text_lc)) >= NAME_MATCH:
        out.append(Check("project_name", "pass", "info", "Project name matches",
                         f"The document names {project['name']}.", source=src))
    else:
        out.append(Check("project_name", "warn", "warning", "Project name not found",
                         f"The registered name {project['name']} does not appear in the document.", source=src))

    # District
    named = {d for k, d in GUJARAT_DISTRICTS.items() if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text_lc)}
    if named and project["district"] not in named:
        out.append(Check("district", "warn", "warning", "Location differs",
                         f"The document mentions {', '.join(sorted(named))}; the registered project is in "
                         f"{project['district']}.", source=src))

    # Advertised possession vs registered completion
    if claim.possession:
        if claim.possession.value > valid_until:
            out.append(Check(
                "possession_date", "fail", "critical", "Advertised possession is after the registered date",
                f"The document promises possession around {claim.possession.text!r}, later than the registered "
                f"completion date {valid_until.isoformat()}.", evidence=claim.possession.text, source=src,
                verdict_hint="mismatch"))
        else:
            out.append(Check("possession_date", "pass", "info", "Possession date consistent",
                             f"Registered completion: {valid_until.isoformat()}.",
                             evidence=claim.possession.text, source=src))

    # Registry facts a buyer should know
    if project["is_delayed"] and project["status"] != "completed":
        out.append(Check("delay", "warn", "warning", "Project is delayed",
                         f"{project['delay_days']} days past its original completion date "
                         f"({project['proposed_completion'].isoformat()}).", source=src))
    pending = repo.s.scalars(select(Approval).where(Approval.project_id == project["id"],
                                                    Approval.status == "pending")).all()
    if pending:
        out.append(Check("approvals", "warn", "warning", "Approvals pending",
                         "Pending: " + ", ".join(a.kind.replace("_", " ") for a in pending) + ".", source=src))
    card = repo.promoter_scorecard(project["promoter_id"])
    if card:
        records.append(card)
        if card["complaints_open"] >= OPEN_COMPLAINTS_WARN or card["adverse_orders"]:
            out.append(Check(
                "promoter_record", "warn", "warning", "Promoter has open complaints or adverse orders",
                f"{card['complaints_open']} open complaints, {card['adverse_orders']} show-cause, penalty or "
                f"revocation orders across {card['projects']} projects.", source=card["source"]))
    return out


def _promoter_check(project: dict[str, Any], text_lc: str, repo: Repository) -> Check:
    src = project["source"]
    promoter = repo.s.get(Promoter, project["promoter_id"])
    if max(_mentioned(promoter.name, text_lc), _mentioned(promoter.name_gu, text_lc)) >= NAME_MATCH:
        return Check("promoter_match", "pass", "info", "Promoter matches",
                     f"The document names the registered promoter, {_core(promoter.name)}.", source=src)
    for other in repo.s.scalars(select(Promoter).where(Promoter.id != promoter.id)):
        score = max(_mentioned(other.name, text_lc), _mentioned(other.name_gu, text_lc))
        if score >= OTHER_PROMOTER_MATCH:
            return Check(
                "promoter_match", "fail", "critical", "Promoter name mismatch",
                f"The document names {_core(other.name)}, but this registration belongs to "
                f"{_core(promoter.name)}.", evidence=_core(other.name), source=src, verdict_hint="mismatch")
    return Check("promoter_match", "info", "info", "Promoter not named",
                 f"The document does not name the registered promoter ({_core(promoter.name)}).", source=src)


def _check_agent(number, repo: Repository, as_of: date, records: list[dict[str, Any]]) -> list[Check]:
    agent = repo.get_agent(number.normalised)
    if agent is None:
        return [Check("agent_registration", "fail", "critical", "Agent registration not found",
                      f"{number.normalised} is not in the GUJRERA agent registry data.",
                      evidence=number.normalised, verdict_hint="mismatch")]
    records.append(agent)
    if agent["status"] != "active" or agent["valid_until"] < as_of:
        return [Check("agent_registration", "fail", "critical", "Agent registration not valid",
                      f"{_core(agent['name'])}: status {agent['status']}, valid until "
                      f"{agent['valid_until'].isoformat()}.", source=agent["source"], verdict_hint="mismatch")]
    return [Check("agent_registration", "pass", "info", "Agent registered",
                  f"{_core(agent['name'])}, valid until {agent['valid_until'].isoformat()}.", source=agent["source"])]


def _check_booking(claim: TrustClaim, checks: list[Check]) -> None:
    pct = None
    evidence = None
    if claim.booking_percent:
        pct, evidence = float(claim.booking_percent.value), claim.booking_percent.text
    elif claim.booking_amount and claim.price and claim.price.value:
        pct = 100.0 * float(claim.booking_amount.value) / float(claim.price.value)
        evidence = f"{claim.booking_amount.text} / {claim.price.text}"
    if pct is not None and pct > BOOKING_LIMIT_PERCENT:
        checks.append(Check(
            "booking_over_limit", "warn", "critical", "Booking amount above 10%",
            f"The document asks for about {pct:.0f}% at booking. A promoter cannot take more than 10% of the "
            "cost before a registered agreement for sale (RERA Act, Section 13).", evidence=evidence))

