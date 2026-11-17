"""Clean raw dataset files into ``data/processed/`` without modifying ``data/dataset/``.

Outputs:
- ``data/processed/fake_notices.jsonl`` (90 records, ``clean_claim``, mapped ``doc_type``)
- ``data/processed/excluded_images.txt`` (unreferenced images in 01_fake_notice_benchmark/images)
- ``data/processed/official_docs.jsonl`` (79 records, ISO ``date``, ``text_is_short``)
- ``data/processed/whatsapp_variants.jsonl`` (150 records, ``has_factcheck_stamp``)
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = PROJECT_ROOT / "data" / "dataset"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

ALLOWED_DOC_TYPES = {
    "letter",
    "notice",
    "order",
    "approval",
    "email",
    "notification",
    "press_release",
    "other",
}

DOC_TYPE_MAP: dict[str, str] = {
    "letter": "letter",
    "पत्र": "letter",
    "appointment letter": "letter",
    "lottery letter": "letter",
    "permission letter": "letter",
    "letter of transmittal": "letter",
    "notice": "notice",
    "recruitment notice": "notice",
    "notice / order": "notice",
    "order": "order",
    "आदेश": "order",
    "circular / order": "order",
    "approval": "approval",
    "approval letter": "approval",
    "loan approval letter": "approval",
    "invoice / approval": "approval",
    "permission certificate": "approval",
    "appointment": "approval",
    "email": "email",
    "email / court order": "email",
    "notification": "notification",
    "gazette notification": "notification",
    "press release": "press_release",
    "press_release": "press_release",
    "receipt": "other",
    "forwarded message": "other",
}

# Emoji & symbol ranges
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\u2600-\u27BF"
    "\uFE0E\uFE0F"
    "\u200d"
    "]+",
    flags=re.UNICODE,
)

# Boilerplate prefixes/wrappers in PIB Telegram claims
_BOILERPLATE_PREFIXES = [
    r"^FAKE\s+NOTICE\s+ALERT\s*[:\-!]?\s*",
    r"^FAKE\s+DOCUMENT\s+ALERT\s*[:\-!]?\s*",
    r"^Beware\s+of\s+Fraudsters!\s*",
    r"^Alert!\s*",
    r"^Claim:\s*",
    r"^Have\s+you\s+also\s+received\s+",
    r"^Have\s+you\s+received\s+",
    r"^Received\s+a\s+similar\s+",
    r"^Received\s+an?\s+",
]

_BOILERPLATE_SUFFIXES = [
    r"\s*This\s+Claim\s+is\s+#?fake.*$",
    r"\s*Beware\s*!*\s*This\s+could\s+be\s+a\s+phishing\s+scam\s+targeting\s+you\.?.*$",
    r"\s*Be\s+cautious\.?\s*$",
]


def clean_claim_text(claim: str) -> str:
    """Remove emojis and social-media question wrappers while preserving core claim text."""
    text = _EMOJI_RE.sub(" ", claim)
    text = re.sub(r"\s+", " ", text).strip()

    changed = True
    while changed:
        changed = False
        for pat in _BOILERPLATE_PREFIXES:
            new_text = re.sub(pat, "", text, flags=re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                changed = True

    for pat in _BOILERPLATE_SUFFIXES:
        text = re.sub(pat, "", text, flags=re.IGNORECASE).strip()

    # Clean hashtags like #Pakistani -> Pakistani, #fake -> fake
    text = re.sub(r"#(\w+)", r"\1", text)
    # Trim trailing question marks left over from "Have you also received ... ?"
    text = re.sub(r"\s*\?+\s*$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()

    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text or claim.strip()


def map_doc_type(raw_doc_type: str) -> str:
    key = raw_doc_type.strip().lower()
    mapped = DOC_TYPE_MAP.get(raw_doc_type.strip()) or DOC_TYPE_MAP.get(key, "other")
    return mapped if mapped in ALLOWED_DOC_TYPES else "other"


def parse_iso_date(raw_date: str | None) -> str | None:
    """Convert date strings from the official corpus to YYYY-MM-DD, or None if missing."""
    if not raw_date or not raw_date.strip():
        return None
    s = raw_date.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s

    # Format: "October 23, 2026"
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %b, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Format: "23 Oct, 2026 +0530"
    cleaned = re.sub(r"\s+[+-]\d{4}$", "", s)
    for fmt in ("%d %b, %Y", "%d %B, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Format: "Fri, 23 Oct 2026 19:25:00" (RFC 2822)
    try:
        dt = parsedate_to_datetime(s)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    raise ValueError(f"Unrecognised date format: {raw_date!r}")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def prepare_all() -> dict[str, Any]:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fake notices
    fn_dir = DATASET_DIR / "01_fake_notice_benchmark"
    raw_notices = _read_jsonl(fn_dir / "notices.jsonl")
    referenced_images: set[str] = set()
    cleaned_notices: list[dict[str, Any]] = []

    for row in raw_notices:
        img_name = Path(row["image"]).name
        referenced_images.add(img_name)
        raw_dt = row["doc_type"]
        new_row = {
            **row,
            "doc_type_raw": raw_dt,
            "doc_type": map_doc_type(raw_dt),
            "clean_claim": clean_claim_text(row["claim"]),
            "image": f"data/dataset/01_fake_notice_benchmark/images/{img_name}",
        }
        cleaned_notices.append(new_row)

    all_disk_images = sorted(
        p.name for p in (fn_dir / "images").iterdir() if p.is_file()
    )
    excluded_images = [name for name in all_disk_images if name not in referenced_images]

    _write_jsonl(PROCESSED_DIR / "fake_notices.jsonl", cleaned_notices)
    (PROCESSED_DIR / "excluded_images.txt").write_text(
        "\n".join(excluded_images) + ("\n" if excluded_images else ""),
        encoding="utf-8",
    )

    # 2. Official source corpus
    oc_dir = DATASET_DIR / "02_official_source_corpus"
    raw_docs = _read_jsonl(oc_dir / "documents.jsonl")
    cleaned_docs: list[dict[str, Any]] = []
    missing_dates = 0
    short_texts = 0

    for row in raw_docs:
        raw_date = row.get("date")
        iso_date = parse_iso_date(raw_date)
        if iso_date is None:
            missing_dates += 1
        text_val = row.get("text") or ""
        is_short = len(text_val) < 300
        if is_short:
            short_texts += 1
        new_row = {
            **row,
            "date_raw": raw_date,
            "date": iso_date,
            "text_is_short": is_short,
        }
        if row.get("local_file"):
            lf_name = Path(row["local_file"]).name
            new_row["local_file"] = (
                f"data/dataset/02_official_source_corpus/files/{lf_name}"
            )
        cleaned_docs.append(new_row)

    _write_jsonl(PROCESSED_DIR / "official_docs.jsonl", cleaned_docs)

    # 3. WhatsApp variants
    wa_dir = DATASET_DIR / "05_whatsapp_variants"
    raw_sources = _read_jsonl(wa_dir / "sources.jsonl")
    fake_source_ids = {
        s["source_id"]
        for s in raw_sources
        if s.get("label") == "fake" or str(s.get("source_id", "")).startswith("FN-")
    }
    raw_variants = _read_jsonl(wa_dir / "variants.jsonl")
    cleaned_variants: list[dict[str, Any]] = []
    stamped_count = 0

    for row in raw_variants:
        has_stamp = (
            row.get("label") == "fake"
            or row.get("source_id") in fake_source_ids
            or str(row.get("source_id", "")).startswith("FN-")
        )
        if has_stamp:
            stamped_count += 1
        var_name = Path(row["file"]).name
        new_row = {
            **row,
            "file": f"data/dataset/05_whatsapp_variants/variants/{var_name}",
            "has_factcheck_stamp": bool(has_stamp),
        }
        cleaned_variants.append(new_row)

    _write_jsonl(PROCESSED_DIR / "whatsapp_variants.jsonl", cleaned_variants)

    # Other dataset counts (read-only inspection)
    reg_data = json.loads(
        (DATASET_DIR / "03_issuer_registry" / "issuers.json").read_text(encoding="utf-8")
    )
    claims_count = len(
        _read_jsonl(DATASET_DIR / "04_multilingual_claims" / "claims.jsonl")
    )
    narratives_count = len(
        _read_jsonl(DATASET_DIR / "04_multilingual_claims" / "narratives.jsonl")
    )
    eval_pairs_count = len(
        _read_jsonl(DATASET_DIR / "04_multilingual_claims" / "eval_pairs.jsonl")
    )
    syn_count = len(
        _read_jsonl(DATASET_DIR / "06_synthetic_forgeries" / "labels.jsonl")
    )

    summary = {
        "fake_notices": len(cleaned_notices),
        "excluded_images": len(excluded_images),
        "total_benchmark_images_on_disk": len(all_disk_images),
        "official_docs": len(cleaned_docs),
        "official_docs_missing_dates": missing_dates,
        "official_docs_short_texts": short_texts,
        "issuer_registry_issuers": len(reg_data.get("issuers", [])),
        "multilingual_claims": claims_count,
        "multilingual_narratives": narratives_count,
        "multilingual_eval_pairs": eval_pairs_count,
        "whatsapp_variants": len(cleaned_variants),
        "whatsapp_variants_with_factcheck_stamp": stamped_count,
        "synthetic_forgeries": syn_count,
    }

    print("=== Dataset Preparation Summary ===")
    print(
        f"01_fake_notice_benchmark : {summary['fake_notices']} notices kept, "
        f"{summary['excluded_images']} unreferenced images excluded "
        f"(of {summary['total_benchmark_images_on_disk']} on disk)"
    )
    print(
        f"02_official_source_corpus: {summary['official_docs']} documents "
        f"({summary['official_docs_missing_dates']} missing dates -> null, "
        f"{summary['official_docs_short_texts']} short texts < 300 chars)"
    )
    print(f"03_issuer_registry       : {summary['issuer_registry_issuers']} issuers")
    print(
        f"04_multilingual_claims   : {summary['multilingual_claims']} claims, "
        f"{summary['multilingual_narratives']} narratives, "
        f"{summary['multilingual_eval_pairs']} eval pairs"
    )
    print(
        f"05_whatsapp_variants     : {summary['whatsapp_variants']} variants "
        f"({summary['whatsapp_variants_with_factcheck_stamp']} marked has_factcheck_stamp=true)"
    )
    print(f"06_synthetic_forgeries   : {summary['synthetic_forgeries']} synthetic images")
    return summary


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    prepare_all()
