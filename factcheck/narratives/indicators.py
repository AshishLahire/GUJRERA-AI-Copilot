"""Indicator extraction, normalisation, and template-reuse graph linking for Stage 8."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from factcheck.forensics.rules import PIB_OVERLAY_LINE_PATTERNS
from factcheck.schemas import SharedIndicatorItem

# Official helplines, emergency numbers, and PIB contacts to exclude
OFFICIAL_EXCLUDED_PHONES: set[str] = {
    "1930",
    "112",
    "155260",
    "8799711259",  # PIB WhatsApp Fact-Check
    "100",
    "101",
    "102",
    "108",
    "1090",
    "1091",
    "1098",
    "14417",
}

OFFICIAL_EXCLUDED_EMAILS: set[str] = {
    "socialmedia@pib.gov.in",
    "factcheck@pib.gov.in",
    "contact@pib.gov.in",
    "report.phishing@sbi.co.in",
    "customercare@sbi.co.in",
}

# Platforms, shorteners, second-level generic suffixes, and government domains to exclude from indicator linking
EXCLUDED_DOMAINS: set[str] = {
    "pib.gov.in",
    "gov.in",
    "nic.in",
    "ac.in",
    "co.in",
    "org.in",
    "net.in",
    "res.in",
    "edu.in",
    "wa.me",
    "t.co",
    "bit.ly",
    "tinyurl.com",
    "t.me",
    "telegram.me",
    "twitter.com",
    "x.com",
    "facebook.com",
    "fb.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "google.com",
    "drive.google.com",
    "forms.gle",
    "docs.google.com",
    "linktr.ee",
    "whatsapp.com",
    "web.whatsapp.com",
    "static.pib.gov.in",
    "sbi.co.in",
    "onlinesbi.sbi",
    "rbi.org.in",
    "mudra.org.in",
    "cybercelldelhi.in",
}

MULTI_PART_TLDS: set[str] = {
    "gov.in",
    "nic.in",
    "org.in",
    "co.in",
    "ac.in",
    "net.in",
    "res.in",
    "edu.in",
    "mil.in",
    "gen.in",
    "ind.in",
    "co.uk",
    "org.uk",
    "ac.uk",
    "gov.uk",
    "me.uk",
    "net.uk",
    "com.au",
    "net.au",
    "org.au",
    "edu.au",
    "gov.au",
}

NON_DOMAIN_EXTENSIONS: set[str] = {
    "pdf", "jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "tiff",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf", "csv",
    "zip", "rar", "7z", "tar", "gz", "apk", "exe", "dmg", "iso",
    "html", "htm", "php", "asp", "aspx", "jsp", "js", "css", "py", "sh",
}

OFFICIAL_ADVICE_PATTERNS = [
    re.compile(r"(?i)\b(?:official\s+website|official\s+portal|official\s+information|authentic\s+information|authentic\s+details|official\s+source|official\s+link)\b"),
    re.compile(r"(?i)\b(?:visit\s+(?:the\s+)?(?:official\s+)?(?:website|portal)|visit\s*:\s*[a-zA-Z0-9.-]+\.(?:gov\.in|nic\.in|org\.in|co\.in|sbi|org))\b"),
    re.compile(r"(?i)\b(?:report\s+(?:immediately\s+)?(?:at|on)\s*[:\s]+[a-zA-Z0-9._%+-]+@)\b"),
    re.compile(r"(?i)(?:आधिकारिक\s+(?:वेबसाइट|पोर्टल|जानकारी|वित्तीय\s+जानकारी)|अधिक\s+जानकारी\s+के\s+लिए\s+विजिट|सत्यापित\s+करें|शिकायत\s+(?:दर्ज\s+करें|के\s+लिए))"),
]

# Words that indicate a job title / administrative position rather than an individual person's name
JOB_TITLE_WORDS: set[str] = {
    "DIRECTOR",
    "SECRETARY",
    "CHAIRMAN",
    "COMMISSIONER",
    "MANAGER",
    "GENERAL",
    "OFFICER",
    "UNDER",
    "ADDITIONAL",
    "CHIEF",
    "JOINT",
    "ASSISTANT",
    "SIGNATORY",
    "AUTHORIZED",
    "AUTHORISED",
    "SUPERINTENDENT",
    "MINISTER",
    "GOVERNOR",
    "PRESIDENT",
    "REGISTRAR",
    "HEAD",
    "MEMBER",
    "DEPUTY",
    "PRINCIPAL",
    "ACADEMICS",
    "EXAMINATION",
    "CONTROLLER",
    "COORDINATOR",
    "INSPECTOR",
    "ADVISER",
    "ADVISOR",
    "EXECUTIVE",
    "SPECIAL",
}

_CLEAN_REF_PREFIX_RE = re.compile(
    r"(?i)^(?:(?:Circular|Cir|Order|Ref(?:erence)?|File|Letter|Notification)\s*\.?\s*)?(?:No\.?|Ref)\s*[:\-]?\s*"
)


def extract_registered_domain(raw: str) -> str | None:
    """Extract registered domain, taking into account multi-part TLDs and filtering file extensions."""
    cleaned = raw.lower().strip()
    cleaned = re.sub(r"^https?://", "", cleaned).split("/")[0].split(":")[0].strip()
    cleaned = re.sub(r"^www\.", "", cleaned).strip(".,;:()<>[]\"' \t\n\r")
    parts = cleaned.split(".")
    if len(parts) < 2:
        return None
    tld = parts[-1]
    if not tld.isalpha() or len(tld) < 2 or tld in NON_DOMAIN_EXTENSIONS:
        return None
    if len(parts) >= 3 and f"{parts[-2]}.{parts[-1]}" in MULTI_PART_TLDS:
        return f"{parts[-3]}.{parts[-2]}.{parts[-1]}"
    return f"{parts[-2]}.{parts[-1]}"


def load_official_exclusion_sets(
    registry_path: Path | None = None,
    official_corpus_path: Path | None = None,
) -> tuple[set[str], set[str], set[str]]:
    """Load additional official phones, emails, and domains from the registry and official corpus."""
    phones = set(OFFICIAL_EXCLUDED_PHONES)
    emails = set(OFFICIAL_EXCLUDED_EMAILS)
    domains = set(EXCLUDED_DOMAINS)

    repo_root = Path(__file__).resolve().parents[2]
    reg_p = registry_path or (repo_root / "data" / "dataset" / "03_issuer_registry" / "issuers.json")
    off_p = official_corpus_path or (repo_root / "data" / "processed" / "official_docs.jsonl")
    if not off_p.exists():
        off_p = repo_root / "data" / "index" / "official_meta.json"

    if reg_p.exists():
        try:
            reg_raw = json.loads(reg_p.read_text(encoding="utf-8"))
            iss_list = reg_raw.get("issuers", []) if isinstance(reg_raw, dict) else reg_raw
            for iss in iss_list:
                for d in iss.get("official_domains", []):
                    cleaned_d = d.lower().strip()
                    if cleaned_d:
                        domains.add(cleaned_d)
                        reg_dom = extract_registered_domain(cleaned_d)
                        if reg_dom:
                            domains.add(reg_dom)
        except Exception:
            pass

    if off_p.exists():
        try:
            raw_text = off_p.read_text(encoding="utf-8")
            if off_p.suffix == ".jsonl":
                lines = raw_text.splitlines()
                docs = [json.loads(l) for l in lines if l.strip()]
            else:
                docs = json.loads(raw_text)
            for doc in docs:
                txt = f"{doc.get('url', '')} {doc.get('title', '')} {doc.get('text', '')}"
                for em in re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", txt):
                    emails.add(em.lower().strip())
                for cand in re.findall(r"(?:https?://)?\b([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+)(?:/[^\s\)\]\"\'<>]*)?", txt):
                    reg_dom = extract_registered_domain(cand)
                    if reg_dom:
                        domains.add(reg_dom)
        except Exception:
            pass

    return phones, emails, domains


def normalize_phone(raw: str, excluded_phones: set[str] | None = None) -> str | None:
    """Normalize phone to 10 digits (stripping +91, 0, spaces, dashes) and filter official numbers."""
    ex = excluded_phones if excluded_phones is not None else OFFICIAL_EXCLUDED_PHONES
    digits = re.sub(r"\D", "", raw)
    # Strip country code 91 if 12 digits
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    # Toll-free 1800 numbers (exclude from forgery linking)
    if digits.startswith("1800"):
        return None

    if len(digits) == 10 and digits[0] in "6789":
        if digits in ex:
            return None
        return digits
    return None


def normalize_email(raw: str, excluded_emails: set[str] | None = None) -> str | None:
    """Normalize email to lowercase, trimmed string and filter official / PIB emails."""
    ex = excluded_emails if excluded_emails is not None else OFFICIAL_EXCLUDED_EMAILS
    em = raw.lower().strip().strip(".,;:()<>[]\"' \t\n\r")
    if "@" in em and len(em) >= 6:
        if (
            em in ex
            or em.endswith(".gov.in")
            or em.endswith(".nic.in")
            or "@pib.gov.in" in em
            or "@nic.in" in em
            or "sbi.co.in" in em
        ):
            return None
        return em
    return None


def normalize_domain(raw: str, excluded_domains: set[str] | None = None) -> str | None:
    """Normalize bare domain or URL to registered domain hostname and filter official & platform domains."""
    ex = excluded_domains if excluded_domains is not None else EXCLUDED_DOMAINS
    domain = extract_registered_domain(raw)
    if not domain:
        return None
    if (
        domain in ex
        or domain.endswith(".gov.in")
        or domain.endswith(".nic.in")
        or any(domain.endswith(f".{p}") for p in ["gov.in", "nic.in", "pib.gov.in"])
    ):
        return None
    return domain


def normalize_reference(raw: str) -> str | None:
    """Normalize official / circular reference number (remove 'No.' prefixes and spaces)."""
    cleaned = _CLEAN_REF_PREFIX_RE.sub("", raw.strip())
    # Remove internal spaces
    cleaned = re.sub(r"\s+", "", cleaned).upper().strip(".:-")
    # Must be at least 6 characters and contain at least 1 digit
    if len(cleaned) < 6 or not any(c.isdigit() for c in cleaned):
        return None

    # Exclude PIB WhatsApp number accidentally matched as reference
    if cleaned in ("8799711259", "918799711259", "+918799711259"):
        return None

    # Exclude PIB PressRelease PRID numbers (pure 7-digit numbers like 1827203, 1828698)
    if cleaned.isdigit() and len(cleaned) == 7:
        return None

    # Exclude obvious non-reference tokens
    if cleaned in {"NOTICE", "CIRCULAR", "ORDER", "NOTIFICATION", "GOVERNMENT", "MINISTRY", "IMPORTANT"}:
        return None

    return cleaned


def extract_signatories(text: str) -> set[str]:
    """Extract signatory names (requiring 2+ capitalized words, not a job title alone)."""
    signatories: set[str] = set()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    title_trigger_re = re.compile(
        r"(?i)\b(?:Dr\.|Er\.|Prof\.|Shri|Smt\.|Mr\.|Mrs\.|Signature|Signatory|Director|Secretary|Commissioner|Officer|Manager|Sd/|Sd/-)\b"
    )

    for i, line in enumerate(lines):
        has_trigger = bool(title_trigger_re.search(line))
        has_neighbor_trigger = False
        if i > 0 and title_trigger_re.search(lines[i - 1]):
            has_neighbor_trigger = True
        if i < len(lines) - 1 and title_trigger_re.search(lines[i + 1]):
            has_neighbor_trigger = True

        if not (has_trigger or has_neighbor_trigger):
            continue

        # Clean line of prefixes and punctuation
        candidate = re.sub(
            r"(?i)^(?:sd/-?|signature|signatory|authorized\s+signatory|authorised\s+signatory|name\s*:?)\s*",
            "",
            line,
        )
        candidate = re.sub(r"(?i)\b(?:Dr\.|Er\.|Prof\.|Shri|Smt\.|Mr\.|Mrs\.)\s*", "", candidate)
        candidate = candidate.strip("()[]:,- \t\"'")

        words = candidate.split()
        if 2 <= len(words) <= 4:
            # Check capitalization and alphabetic tokens
            if all(w.isalpha() and w[0].isupper() and len(w) >= 2 for w in words):
                upper_set = {w.upper() for w in words}
                # Must not be solely composed of administrative job title words
                if not upper_set.issubset(JOB_TITLE_WORDS):
                    # Also avoid common words like 'Copy To', 'All Concerned', etc.
                    if not any(w.upper() in {"COPY", "RESPECTIVE", "HEADS", "ORGANIZATIONS", "INSTITUTIONS", "ROOM"} for w in words):
                        signatories.add(" ".join(w.capitalize() for w in words))

    return signatories


def extract_indicators_from_text(
    text: str,
    *,
    excluded_phones: set[str] | None = None,
    excluded_emails: set[str] | None = None,
    excluded_domains: set[str] | None = None,
) -> dict[str, set[str]]:
    """Extract and normalize all 5 kinds of indicators from raw text, filtering PIB overlay and official advice."""
    ex_phones = excluded_phones if excluded_phones is not None else OFFICIAL_EXCLUDED_PHONES
    ex_emails = excluded_emails if excluded_emails is not None else OFFICIAL_EXCLUDED_EMAILS
    ex_doms = excluded_domains if excluded_domains is not None else EXCLUDED_DOMAINS

    indicators: dict[str, set[str]] = {
        "phone": set(),
        "email": set(),
        "domain": set(),
        "reference": set(),
        "signatory": set(),
    }

    # 1. Pre-filter PIB overlay lines if present to prevent PIB handles/numbers from leaking
    lines: list[str] = []
    for line in text.splitlines():
        if any(pat.search(line) for pat in PIB_OVERLAY_LINE_PATTERNS):
            continue
        lines.append(line)

    # 2. Filter out official advice lines / clauses (where PIB points to authentic sources or reporting portals)
    non_advice_lines: list[str] = []
    for line in lines:
        if any(pat.search(line) for pat in OFFICIAL_ADVICE_PATTERNS):
            continue
        non_advice_lines.append(line)
    clean_indicator_text = "\n".join(non_advice_lines)

    # 3. Strip URLs before phone and reference extraction to prevent tweet status IDs and file URLs from polluting
    text_no_urls = re.sub(r"https?://\S+", " ", clean_indicator_text)

    # 3a. Phones (from text_no_urls)
    phone_candidates = re.findall(
        r"(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}|\b1800[\s-]?\d{3}[\s-]?\d{3,4}\b",
        text_no_urls,
    )
    for ph in phone_candidates:
        norm = normalize_phone(ph, ex_phones)
        if norm:
            indicators["phone"].add(norm)

    # 3b. Emails (from clean_indicator_text)
    email_candidates = re.findall(r"[\w\.-]+@[\w\.-]+\.\w+", clean_indicator_text)
    for em in email_candidates:
        norm = normalize_email(em, ex_emails)
        if norm:
            indicators["email"].add(norm)

    # 3c. Domains (from clean_indicator_text, using robust public suffix registered domain extraction)
    domain_candidates = re.findall(
        r"(?:https?://)?\b([a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+)(?:/[^\s\)\]\"\'<>]*)?",
        clean_indicator_text,
    )
    for dc in domain_candidates:
        norm = normalize_domain(dc, ex_doms)
        if norm:
            indicators["domain"].add(norm)

    # 3d. References (from text_no_urls)
    ref_candidates = re.findall(
        r"\b(?:[A-Z0-9]{2,10}[/\-][A-Z0-9\.\-/_]{3,25}|[A-Z]{2,8}/\d{2,4}/\d{1,6})\b",
        text_no_urls,
    )
    for rf in ref_candidates:
        norm = normalize_reference(rf)
        if norm:
            indicators["reference"].add(norm)

    # 3e. Signatories (from text_no_urls)
    sigs = extract_signatories(text_no_urls)
    indicators["signatory"].update(sigs)

    return indicators


def build_indicator_graph(
    records: list[dict[str, Any]],
    cached_ocr_texts: list[dict[str, Any]] | None = None,
    *,
    excluded_phones: set[str] | None = None,
    excluded_emails: set[str] | None = None,
    excluded_domains: set[str] | None = None,
) -> dict[str, Any]:
    """Build indicator bipartite graph and detect template reuse across issuers/years."""
    if excluded_phones is None or excluded_emails is None or excluded_domains is None:
        def_phones, def_emails, def_doms = load_official_exclusion_sets()
        ex_phones = excluded_phones or def_phones
        ex_emails = excluded_emails or def_emails
        ex_doms = excluded_domains or def_doms
    else:
        ex_phones = excluded_phones
        ex_emails = excluded_emails
        ex_doms = excluded_domains
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Map: (kind, value) -> set of record dicts {doc_id, issuer, year, title}
    indicator_to_records: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    record_nodes_seen: set[str] = set()

    def _ingest_record(doc_id: str, title: str, issuer: str | None, date_str: str | None, text_content: str, src: str):
        year = date_str[:4] if date_str and len(date_str) >= 4 and date_str[:4].isdigit() else "Unknown"
        iss = issuer or "Unknown"

        if doc_id not in record_nodes_seen:
            record_nodes_seen.add(doc_id)
            nodes.append({
                "id": doc_id,
                "type": "record",
                "title": title[:100],
                "issuer": iss,
                "year": year,
                "source": src,
            })

        extracted = extract_indicators_from_text(
            text_content,
            excluded_phones=excluded_phones,
            excluded_emails=excluded_emails,
            excluded_domains=excluded_domains,
        )

        for kind, vals in extracted.items():
            for val in vals:
                ind_id = f"{kind}:{val}"
                edges.append({"source": doc_id, "target": ind_id, "kind": "contains"})
                indicator_to_records[(kind, val)].append({
                    "doc_id": doc_id,
                    "issuer": iss,
                    "year": year,
                    "title": title[:80],
                })

    # Ingest debunk records
    for d in records:
        doc_id = d["doc_id"]
        title = d.get("title") or doc_id
        issuer = d.get("claimed_issuer")
        date_str = d.get("date")
        text_content = f"{d.get('title', '')}\n{d.get('snippet', '')}\n{d.get('claim_text', '')}\n{d.get('tg_text', '')}"
        _ingest_record(doc_id, title, issuer, date_str, text_content, "debunk_post")

    # Ingest cached OCR texts from fake notices if provided
    if cached_ocr_texts:
        for item in cached_ocr_texts:
            doc_id = item["sample_id"]
            title = item.get("filename") or doc_id
            issuer = item.get("expected_issuer")
            date_str = None
            text_content = item.get("final_text") or ""
            _ingest_record(doc_id, title, issuer, date_str, text_content, "cached_ocr")

    # Build indicator nodes and identify template reuse
    template_reuse: list[dict[str, Any]] = []

    for (kind, val), linked in indicator_to_records.items():
        ind_id = f"{kind}:{val}"
        nodes.append({
            "id": ind_id,
            "type": "indicator",
            "kind": kind,
            "value": val,
            "degree": len(linked),
        })

        if len(linked) >= 2:
            unique_issuers = sorted({item["issuer"] for item in linked if item["issuer"] != "Unknown"})
            unique_years = sorted({item["year"] for item in linked if item["year"] != "Unknown"})
            doc_ids = sorted({item["doc_id"] for item in linked})

            # Template reuse condition: appears across DIFFERENT claimed issuers OR across DIFFERENT years
            if len(unique_issuers) >= 2 or len(unique_years) >= 2:
                # Build human-readable summary
                if len(unique_issuers) >= 2 and len(unique_years) >= 2:
                    summary = f"Reused across {len(unique_issuers)} agencies ({', '.join(unique_issuers[:3])}) across {len(unique_years)} years ({', '.join(unique_years)})"
                elif len(unique_issuers) >= 2:
                    summary = f"Reused across {len(unique_issuers)} different agencies: {', '.join(unique_issuers[:3])}"
                else:
                    summary = f"Reused across {len(unique_years)} years: {', '.join(unique_years)}"

                template_reuse.append({
                    "indicator_id": ind_id,
                    "kind": kind,
                    "value": val,
                    "linked_records": doc_ids,
                    "issuers": unique_issuers,
                    "years": unique_years,
                    "summary": summary,
                })

    # Sort template reuse by number of linked records descending
    template_reuse.sort(key=lambda x: len(x["linked_records"]), reverse=True)

    return {
        "nodes": nodes,
        "edges": edges,
        "template_reuse": template_reuse,
        "summary": {
            "total_records": len(record_nodes_seen),
            "total_indicators": len(indicator_to_records),
            "total_template_reuse_indicators": len(template_reuse),
        },
    }
