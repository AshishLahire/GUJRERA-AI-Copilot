"""Pydantic models and loader functions for the 6 benchmark datasets.

Reads from ``data/processed/`` when available (falling back to the read-only
``data/dataset/`` tree) and resolves all image/document paths to absolute
``Path`` objects, logging a warning if any file is missing on disk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = PROJECT_ROOT / "data" / "dataset"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def _resolve_and_check(base_dir: Path, rel_or_abs: str | Path) -> Path:
    """Resolve a path against ``base_dir`` (or ``PROJECT_ROOT``) and warn if missing."""
    p = Path(rel_or_abs)
    if not p.is_absolute():
        candidate = (base_dir / p).resolve()
        if not candidate.exists():
            alt = (PROJECT_ROOT / p).resolve()
            if alt.exists():
                candidate = alt
        p = candidate
    else:
        p = p.resolve()
    if not p.exists():
        logger.warning("Referenced file does not exist: %s", p)
    return p


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# 1. Fake Notice Benchmark (01_fake_notice_benchmark)
# ---------------------------------------------------------------------------


class FakeNotice(BaseModel):
    notice_id: str
    source: str
    source_url: str
    source_page: int | None = None
    post_date: str
    language: str
    doc_type: str
    doc_type_raw: str | None = None
    claimed_issuer: str | None = None
    claimed_issuer_id: str
    claim: str
    clean_claim: str | None = None
    verdict: str
    official_fact: str
    forgery_cues: list[str] = Field(default_factory=list)
    scam_type: str | None = None
    narrative_id: str
    note: str | None = None
    image: Path
    format_exemplars_ds2: list[str] = Field(default_factory=list)
    annotation: str
    image_contains_factcheck_overlay: bool
    reference_seen: str | None = None


def load_fake_notices(
    *,
    prefer_processed: bool = True,
    dataset_dir: Path = DATASET_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> list[FakeNotice]:
    """Load the 90 fake notices from processed or raw JSONL."""
    proc_file = processed_dir / "fake_notices.jsonl"
    raw_dir = dataset_dir / "01_fake_notice_benchmark"
    if prefer_processed and proc_file.exists():
        rows = _read_jsonl(proc_file)
        base = PROJECT_ROOT
    else:
        rows = _read_jsonl(raw_dir / "notices.jsonl")
        base = raw_dir

    notices: list[FakeNotice] = []
    for row in rows:
        img_val = row.get("image", "")
        resolved = _resolve_and_check(base, img_val)
        if not resolved.exists():
            resolved = _resolve_and_check(raw_dir, img_val)
        row = {**row, "image": resolved}
        notices.append(FakeNotice.model_validate(row))
    return notices


# ---------------------------------------------------------------------------
# 2. Official Source Corpus (02_official_source_corpus)
# ---------------------------------------------------------------------------


class OfficialDoc(BaseModel):
    doc_id: str
    issuer: str
    issuer_id: str
    doc_type: str
    language: str
    title: str
    url: str
    reference_no: str | None = None
    department_ref: str | None = None
    date: str | None = None
    date_raw: str | None = None
    text: str | None = None
    text_is_short: bool | None = None
    label: str
    local_file: Path | None = None


def load_official_docs(
    *,
    prefer_processed: bool = True,
    dataset_dir: Path = DATASET_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> list[OfficialDoc]:
    """Load the 79 official source documents from processed or raw JSONL."""
    proc_file = processed_dir / "official_docs.jsonl"
    raw_dir = dataset_dir / "02_official_source_corpus"
    if prefer_processed and proc_file.exists():
        rows = _read_jsonl(proc_file)
        base = PROJECT_ROOT
    else:
        rows = _read_jsonl(raw_dir / "documents.jsonl")
        base = raw_dir

    docs: list[OfficialDoc] = []
    for row in rows:
        lf = row.get("local_file")
        if lf:
            resolved = _resolve_and_check(base, lf)
            if not resolved.exists():
                resolved = _resolve_and_check(raw_dir, lf)
            row = {**row, "local_file": resolved}
        docs.append(OfficialDoc.model_validate(row))
    return docs


# ---------------------------------------------------------------------------
# 3. Issuer Registry (03_issuer_registry)
# ---------------------------------------------------------------------------


class GenuineExample(BaseModel):
    reference_no: str
    ds2_doc_id: str


class ReferencePattern(BaseModel):
    name: str
    regex: str
    status: str
    genuine_examples: list[GenuineExample] = Field(default_factory=list)
    genuine_matches: int = 0


class ImpersonationStats(BaseModel):
    fake_notices_in_ds1: int = 0
    narratives: dict[str, int] = Field(default_factory=dict)
    example_notice_ids: list[str] = Field(default_factory=list)
    observed_forgery_cues: list[str] = Field(default_factory=list)


class IssuerEntry(BaseModel):
    issuer_id: str
    name_en: str
    name_hi: str
    type: str
    official_domains: list[str] = Field(default_factory=list)
    head_title: str | None = None
    date_format: str | None = None
    languages_issued: list[str] | None = None
    never_does: list[str] = Field(default_factory=list)
    source: list[str] = Field(default_factory=list)
    reference_patterns: list[ReferencePattern] = Field(default_factory=list)
    genuine_docs_in_ds2: int = 0
    impersonation: ImpersonationStats = Field(default_factory=ImpersonationStats)
    official_channels: dict[str, str] | None = None
    bilingual_pairs: str | None = None


class FraudulentWebsites(BaseModel):
    source: str
    domains: list[str] = Field(default_factory=list)


class RefFormatCheck(BaseModel):
    issuer_id: str
    reference_no: str
    source: str
    label: str
    pattern: str | None = None
    format_valid: bool
    comment: str | None = None


class IssuerRegistry(BaseModel):
    issuers: list[IssuerEntry]
    known_fraudulent_websites: FraudulentWebsites
    issuers_seen_in_ds1_without_registry_entry: dict[str, int] = Field(
        default_factory=dict
    )
    ref_format_checks: list[RefFormatCheck] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.issuers)


def load_issuer_registry(
    *,
    dataset_dir: Path = DATASET_DIR,
) -> IssuerRegistry:
    """Load the issuer registry (35 issuers + reference format checks)."""
    reg_dir = dataset_dir / "03_issuer_registry"
    data = json.loads((reg_dir / "issuers.json").read_text(encoding="utf-8"))
    checks = _read_jsonl(reg_dir / "ref_format_check.jsonl")
    data["ref_format_checks"] = checks
    return IssuerRegistry.model_validate(data)


# ---------------------------------------------------------------------------
# 4. Multilingual Claims & Narratives (04_multilingual_claims)
# ---------------------------------------------------------------------------


class ClaimSlots(BaseModel):
    claimed_issuer_id: str | None = None
    action: str | None = None
    amount_inr: int | float | None = None
    fee_inr: int | float | None = None
    deadline: str | None = None


class ClaimRecord(BaseModel):
    claim_id: str
    narrative_id: str
    verdict: str
    language: str
    language_name: str
    script: str
    code_mixed: bool
    text: str
    canonical_claim_en: str
    slots: ClaimSlots | None = None
    provenance: str
    review_status: str


class NarrativeRecord(BaseModel):
    narrative_id: str
    verdict: str
    canonical_claim_en: str
    slots: ClaimSlots | None = None
    official_fact: str | None = None
    ds2_doc_id: str | None = None
    reference_no: str | None = None
    ds1_notice_ids: list[str] = Field(default_factory=list)
    debunks_by_month: dict[str, int] = Field(default_factory=dict)
    first_seen: str | None = None
    last_seen: str | None = None
    languages: list[str] = Field(default_factory=list)


class EvalPair(BaseModel):
    claim_a: str
    claim_b: str
    same_narrative: bool


class MultilingualClaimsBundle(BaseModel):
    claims: list[ClaimRecord]
    narratives: list[NarrativeRecord]
    eval_pairs: list[EvalPair]

    def __len__(self) -> int:
        return len(self.claims)


def load_multilingual_claims(
    *,
    dataset_dir: Path = DATASET_DIR,
) -> MultilingualClaimsBundle:
    """Load multilingual claims (120), narratives (20), and eval pairs (660)."""
    mc_dir = dataset_dir / "04_multilingual_claims"
    claims = [ClaimRecord.model_validate(r) for r in _read_jsonl(mc_dir / "claims.jsonl")]
    narratives = [
        NarrativeRecord.model_validate(r)
        for r in _read_jsonl(mc_dir / "narratives.jsonl")
    ]
    eval_pairs = [
        EvalPair.model_validate(r) for r in _read_jsonl(mc_dir / "eval_pairs.jsonl")
    ]
    return MultilingualClaimsBundle(
        claims=claims, narratives=narratives, eval_pairs=eval_pairs
    )


# ---------------------------------------------------------------------------
# 5. WhatsApp Variants (05_whatsapp_variants)
# ---------------------------------------------------------------------------


class WhatsAppSource(BaseModel):
    source_id: str
    label: str
    issuer_id: str
    file: Path
    origin: str


class WhatsAppVariant(BaseModel):
    variant_id: str
    source_id: str
    label: str
    issuer_id: str
    transform: str
    params: dict[str, Any] = Field(default_factory=dict)
    file: Path
    has_factcheck_stamp: bool | None = None


def load_whatsapp_variants(
    *,
    prefer_processed: bool = True,
    dataset_dir: Path = DATASET_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> list[WhatsAppVariant]:
    """Load the 150 WhatsApp variant records with resolved absolute file paths."""
    proc_file = processed_dir / "whatsapp_variants.jsonl"
    raw_dir = dataset_dir / "05_whatsapp_variants"
    if prefer_processed and proc_file.exists():
        rows = _read_jsonl(proc_file)
        base = PROJECT_ROOT
    else:
        rows = _read_jsonl(raw_dir / "variants.jsonl")
        base = raw_dir

    variants: list[WhatsAppVariant] = []
    for row in rows:
        fval = row.get("file", "")
        resolved = _resolve_and_check(base, fval)
        if not resolved.exists():
            resolved = _resolve_and_check(raw_dir, fval)
        row = {**row, "file": resolved}
        variants.append(WhatsAppVariant.model_validate(row))
    return variants


# ---------------------------------------------------------------------------
# 6. Synthetic Forgeries (06_synthetic_forgeries)
# ---------------------------------------------------------------------------


class SyntheticForgery(BaseModel):
    synthetic_id: str
    file: Path
    issuer_id: str
    issuer_name: str
    label: str
    cues: list[str] = Field(default_factory=list)
    cue_descriptions: list[str] = Field(default_factory=list)
    reference_no: str
    issue_date: str
    issue_weekday: str
    signatory_title: str
    subject: str
    language: str
    watermarked: bool


def load_synthetic_forgeries(
    *,
    dataset_dir: Path = DATASET_DIR,
) -> list[SyntheticForgery]:
    """Load the 60 synthetic forgery records with resolved absolute image paths."""
    syn_dir = dataset_dir / "06_synthetic_forgeries"
    rows = _read_jsonl(syn_dir / "labels.jsonl")
    records: list[SyntheticForgery] = []
    for row in rows:
        resolved = _resolve_and_check(syn_dir, row["file"])
        row = {**row, "file": resolved}
        records.append(SyntheticForgery.model_validate(row))
    return records
