"""Stage 3: Structured claim extraction from overlay-filtered OCR text."""

from factcheck.claims.authority import normalise_authority, resolve_issuer
from factcheck.claims.cache import ClaimCache, compute_claim_cache_key
from factcheck.claims.extractor import extract_claim
from factcheck.claims.prompts import CLAIM_EXTRACTION_PROMPT, CLAIM_PROMPT_VERSION

__all__ = [
    "CLAIM_EXTRACTION_PROMPT",
    "CLAIM_PROMPT_VERSION",
    "ClaimCache",
    "compute_claim_cache_key",
    "extract_claim",
    "normalise_authority",
    "resolve_issuer",
]
