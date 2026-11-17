"""Shared pydantic models passed between pipeline stages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedFields(BaseModel):
    """Structured fields extracted from OCR text via regex."""

    reference_numbers: list[str] = Field(default_factory=list)
    normalized_reference_numbers: list[str] = Field(default_factory=list)
    near_duplicate_references: list[list[str]] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    phone_numbers: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    upi_ids: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    suspicious_domains: list[str] = Field(default_factory=list)
    rupee_amounts: list[str] = Field(default_factory=list)
    subject: str | None = None


class OCRResult(BaseModel):
    """Output of Stage 2a (OCR) for a single image."""

    image_hash: str
    final_text: str
    engine_used: str
    valid: bool
    fields: ExtractedFields = Field(default_factory=ExtractedFields)
    from_cache: bool = False
    markdown_stripped: bool = False
    time_ms: float = 0.0
    note: str | None = None
    error: str | None = None
    cache_source: str | None = None
    older_ocr_settings: bool = False
    narrative_result: NarrativeMatchResult | None = None
    language: str | None = None
    script: str | None = None
    language_confidence: float | None = None
    language_name: str | None = None
    text_direction: Literal["ltr", "rtl"] = "ltr"
    primary_language: str | None = None
    languages_present: list[dict] = Field(default_factory=list)
    language_badge: str | None = None
    is_language_uncertain: bool = False
    transcript_transliterated: bool = False
    transliteration_note: str | None = None


class DetectedIssuer(BaseModel):
    """Detected issuing authority from letterhead / text."""

    issuer_id: str
    name: str


class ForensicFinding(BaseModel):
    """A single rule-based forensic indicator found in the document text."""

    cue_id: str
    severity: Literal["info", "warning", "critical"]
    points: int = 0
    title: str
    explanation: str
    evidence: str
    char_start: int = 0
    char_end: int = 0
    rule_status: Literal["verified", "unverified"] = "verified"


class OverlayLineSpan(BaseModel):
    """Character span [char_start, char_end) of a PIB fact-check overlay line in final_text."""

    char_start: int
    char_end: int


class ForensicResult(BaseModel):
    """Output of Stage 2b (Forensic check) for an OCRResult."""

    risk_level: Literal["low", "medium", "high"]
    risk_score: int = Field(ge=0, le=100)
    detected_issuer: DetectedIssuer | None = None
    findings: list[ForensicFinding] = Field(default_factory=list)
    overlay_filtered_count: int = 0
    overlay_line_spans: list[OverlayLineSpan] = Field(default_factory=list)
    transcript_transliterated: bool = False
    transliteration_note: str | None = None


class VisualRegion(BaseModel):
    """A region found on the page image; box = [x, y, w, h] as fractions of width/height."""

    kind: Literal["seal", "signature", "emblem", "edit_trace"]
    box: list[float]
    confidence: float = 0.0
    note: str = ""


class VisualForensicResult(BaseModel):
    """Output of Stage 2c (visual document check) for a page image."""

    analysed: bool = False
    regions: list[VisualRegion] = Field(default_factory=list)
    findings: list[ForensicFinding] = Field(default_factory=list)
    editing_software: str | None = None
    has_seal: bool = False
    has_signature: bool = False
    has_emblem: bool = False
    note: str | None = None


class ClaimResult(BaseModel):
    """Output of Stage 3 (Claim extraction) for overlay-filtered OCR text."""

    canonical_claim_en: str | None = None
    claim_language: str = "en"
    claimed_issuer: str | None = None
    claimed_issuer_id: str | None = None
    action: str | None = None
    effective_date: str | None = None
    effective_date_raw: str | None = None
    amounts: list[str] = Field(default_factory=list)
    audience: str | None = None
    claim_type: Literal["forged_document", "rumour", "official_notice", "other"] = "other"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    from_cache: bool = False
    status_note: str | None = None
    error: str | None = None


class MatchItem(BaseModel):
    """A single retrieved debunk or official document from Stage 4."""

    doc_id: str
    collection: Literal["debunks", "official"]
    title: str
    snippet: str
    date: str | None = None
    url: str | None = None
    reference_no: str | None = None
    narrative_id: str | None = None
    narrative_status: Literal["annotated", "approximate"] | None = None
    official_fact: str | None = None
    score: float = 0.0
    rrf_score: float = 0.0
    cosine_score: float | None = None
    bm25_score: float = 0.0
    label: Literal["strong", "possible", "none", "related"] = "none"
    confidence_label: str = ""
    relation_note: str | None = None
    exact_reference_match: bool = False
    downgraded_from_overlay_overlap: bool = False
    downgrade_note: str | None = None


class GroundTruthMatch(BaseModel):
    """A curated ground-truth record compared with the canonical claim."""

    record_id: str
    verdict: Literal["debunked", "official"]
    kind: str = "notice"
    score: float = 0.0
    claim: str = ""
    official_fact: str | None = None
    issuer_id: str | None = None
    reference_no: str | None = None
    reference_link: str | None = None
    source: str | None = None
    date: str | None = None
    narrative_id: str | None = None


class GroundTruthResult(BaseModel):
    """Claim-level check of the canonical claim against curated PIB / official records."""

    status: Literal["debunked", "official", "no_record", "skipped"] = "skipped"
    similarity: float = 0.0
    best: GroundTruthMatch | None = None
    top_matches: list[GroundTruthMatch] = Field(default_factory=list)
    note: str | None = None
    database_size: int = 0


class RetrievalResult(BaseModel):
    """Output of Stage 4 (Source match) across debunks and official corpus."""

    debunks: list[MatchItem] = Field(default_factory=list)
    official: list[MatchItem] = Field(default_factory=list)
    retrieval_mode: Literal["hybrid", "bm25_only"] = "hybrid"
    mode_note: str | None = None
    queries_used: list[str] = Field(default_factory=list)
    ground_truth: GroundTruthResult | None = None


class EvidenceLink(BaseModel):
    """Clickable evidence reference included in Stage 5 VerdictResult."""

    title: str
    url: str | None = None
    collection: Literal["debunks", "official"]
    doc_id: str
    label: str


class VerdictResult(BaseModel):
    """Output of Stage 5 (Verdict decision) combining forensics and source matches."""

    verdict_key: Literal[
        "debunked",
        "matches_official",
        "altered_official_copy",
        "likely_forged",
        "suspicious_unverified",
        "unverified",
    ]
    color: Literal["red", "green", "amber", "grey"]
    title: str
    reason: str
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    overlay_downgrade_note: str | None = None
    official_clarification: str | None = None
    decided_by: Literal["source_match", "ground_truth", "forensics", "none"] = "none"


class SharedIndicatorItem(BaseModel):
    """An indicator (phone, domain, ref, email, signatory) linking records across issuers or years."""

    indicator_id: str
    kind: Literal["phone", "email", "domain", "reference", "signatory"]
    value: str
    linked_records: list[str] = Field(default_factory=list)
    issuers: list[str] = Field(default_factory=list)
    years: list[str] = Field(default_factory=list)
    summary: str


class NarrativeExemplarPost(BaseModel):
    """An exemplar debunk post representing a cluster."""

    doc_id: str
    title: str
    url: str | None = None
    date: str | None = None
    snippet: str | None = None


class MonthlyDebunkCount(BaseModel):
    """Monthly timeline count for a narrative."""

    month: str
    count: int


class NarrativeClusterSummary(BaseModel):
    """Summary of a debunk narrative cluster for listing and timeline views."""

    id: str
    name: str
    size: int
    claimed_issuers: list[dict[str, Any]] = Field(default_factory=list)
    first_date: str | None = None
    last_date: str | None = None
    languages: list[str] = Field(default_factory=list)
    monthly_debunks: list[MonthlyDebunkCount] = Field(default_factory=list)
    exemplars: list[NarrativeExemplarPost] = Field(default_factory=list)
    shared_indicators_count: int = 0
    keyword_narrative_id: str | None = None


class NarrativeClusterDetail(NarrativeClusterSummary):
    """Detailed view of a narrative cluster including shared indicators."""

    shared_indicators: list[SharedIndicatorItem] = Field(default_factory=list)
    skipped_undated_posts: int = 0


class NarrativeMatchResult(BaseModel):
    """Output of Stage 8 (Narrative detection and indicator linking) for an analyzed document."""

    assigned: bool = False
    cluster_id: str | None = None
    narrative_name: str | None = None
    size: int = 0
    first_date: str | None = None
    last_date: str | None = None
    debunks_count: int = 0
    similarity: float = 0.0
    shared_indicators: list[SharedIndicatorItem] = Field(default_factory=list)
    summary_text: str | None = None
