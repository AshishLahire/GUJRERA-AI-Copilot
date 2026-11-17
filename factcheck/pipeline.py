"""End-to-end verification of one document image or PDF (Stages 1-6 + visual check).

Shared by the demo-sample and test-set API endpoints and by scripts/eval_testset.py, so the
console and the evaluation always run the same code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from factcheck.claims import extract_claim
from factcheck.config import get_settings
from factcheck.decide import decide_verdict
from factcheck.extract.ocr import run_ocr
from factcheck.extract.ocr.fields import extract_fields, strip_synthetic_watermark
from factcheck.forensics import run_forensics
from factcheck.forensics.checks import filter_pib_overlay_lines
from factcheck.forensics.visual import run_visual_forensics
from factcheck.narratives.assign import assign_document_narrative
from factcheck.retrieval import match_sources
from factcheck.retrieval.matcher import get_default_retriever
from factcheck.schemas import (
    ClaimResult,
    ForensicResult,
    NarrativeMatchResult,
    OCRResult,
    RetrievalResult,
    VerdictResult,
    VisualForensicResult,
)


@dataclass
class DocumentRun:
    raw: OCRResult  # OCR output as returned by run_ocr (error text unsanitised)
    ocr: OCRResult  # text shown to the user and checked by forensics (synthetic watermark removed)
    forensics: ForensicResult
    claim: ClaimResult
    matches: RetrievalResult
    verdict: VerdictResult
    narrative: NarrativeMatchResult
    visual: VisualForensicResult
    cleaned_text: str
    removed_overlay_text: str


def run_document_pipeline(
    path: Path | str,
    *,
    allow_fallback: bool = False,
    synthetic: bool = False,
    known_genuine: bool = False,
    exclude_debunk_id: str | None = None,
    image_for_visual: Path | None = None,
) -> DocumentRun:
    """Verify one document. `exclude_debunk_id` simulates an unseen fake (leave-one-out)."""
    cfg = get_settings()
    if cfg.OFFLINE_MODE:
        allow_fallback = False
    path = Path(path)
    res = run_ocr(path, allow_gemini_fallback=allow_fallback, use_cache=True)

    from factcheck.lang import detect_language
    display_text = strip_synthetic_watermark(res.final_text) if synthetic else res.final_text
    display_fields = extract_fields(display_text, strip_watermark=False) if synthetic else res.fields
    det = detect_language(display_text)
    ocr = res.model_copy(
        update={
            "final_text": display_text,
            "fields": display_fields,
            "language": det.language,
            "script": det.script,
            "language_confidence": det.confidence,
            "language_name": det.language_name,
            "text_direction": det.direction,
            "primary_language": det.primary_language,
            "languages_present": [
                {"language": s.language, "share": s.share, "language_name": s.language_name, "script": s.script}
                for s in det.languages_present
            ],
            "language_badge": det.display_badge,
            "is_language_uncertain": det.is_uncertain,
        }
    )
    forensics = run_forensics(ocr)

    cleaned_text, overlay_spans, _ = filter_pib_overlay_lines(display_text)
    removed_overlay_text = "\n".join(display_text[s.char_start : s.char_end] for s in overlay_spans)
    cleaned_fields = extract_fields(cleaned_text, strip_watermark=False) if overlay_spans else display_fields

    claim = extract_claim(cleaned_text, allow_cloud=allow_fallback, use_cache=True)
    matches = match_sources(
        canonical_claim_en=claim.canonical_claim_en,
        original_text=cleaned_text,
        fields=cleaned_fields,
        exclude_debunk_id=exclude_debunk_id,
        claimed_issuer_id=claim.claimed_issuer_id,
    )
    verdict = decide_verdict(
        forensics, matches, cleaned_body_text=cleaned_text, removed_overlay_text=removed_overlay_text,
        claimed_issuer_id=claim.claimed_issuer_id,
    )

    if known_genuine or verdict.verdict_key == "matches_official":
        narrative = NarrativeMatchResult(assigned=False, summary_text="No known scam narrative")
    else:
        retriever = get_default_retriever()
        doc_emb = None
        if retriever.model is not None and cleaned_text:
            try:
                doc_emb = retriever.model.encode([f"query: {cleaned_text}"], normalize_embeddings=True)[0]
            except Exception:
                doc_emb = None
        narrative = assign_document_narrative(cleaned_text, doc_embedding=doc_emb, exclude_doc_id=exclude_debunk_id)

    visual_src = image_for_visual or Path(path)
    return DocumentRun(
        raw=res,
        ocr=ocr,
        forensics=forensics,
        claim=claim,
        matches=matches,
        verdict=verdict,
        narrative=narrative,
        visual=run_visual_forensics(visual_src),
        cleaned_text=cleaned_text,
        removed_overlay_text=removed_overlay_text,
    )


def decide_without_archive(run: DocumentRun) -> VerdictResult:
    """Re-decide as if no PIB debunk of this document existed: forensics + official records only.

    Shows how the pipeline handles a brand-new fake (and that genuine circulars still verify).
    """
    gt = run.matches.ground_truth
    unseen = run.matches.model_copy(
        update={"debunks": [], "ground_truth": gt if gt is not None and gt.status == "official" else None},
        deep=True,
    )
    return decide_verdict(
        run.forensics, unseen, cleaned_body_text=run.cleaned_text, removed_overlay_text=run.removed_overlay_text,
        claimed_issuer_id=run.claim.claimed_issuer_id,
    )
