"""Warm the claim extraction cache for all 20 demo items using cached OCR text only."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factcheck.claims.cache import ClaimCache, compute_claim_cache_key
from factcheck.claims.extractor import extract_claim
from factcheck.claims.prompts import CLAIM_PROMPT_VERSION
from factcheck.config import get_settings
from factcheck.extract.ocr import run_ocr
from factcheck.extract.ocr.cache import OCRCache
from factcheck.extract.ocr.fields import strip_synthetic_watermark
from factcheck.forensics.checks import filter_pib_overlay_lines

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("warm_demo_claims")


def warm_claims() -> None:
    cfg = get_settings()
    db_path = cfg.CACHE_DB_PATH if cfg.CACHE_DB_PATH.is_absolute() else REPO_ROOT / cfg.CACHE_DB_PATH
    ocr_cache = OCRCache(db_path)
    claim_cache = ClaimCache(db_path)

    demo_p = REPO_ROOT / "data" / "demo" / "demo_set.json"
    demo_set = json.loads(demo_p.read_text(encoding="utf-8"))
    items = demo_set.get("items", [])

    safety_limit = cfg.API_DAILY_CALL_LIMIT - 5
    initial_calls = ocr_cache.get_daily_api_calls()
    logger.info(
        "Starting claim warm-up. Daily counter: %d / %d (Safety cutoff: %d). Demo items: %d",
        initial_calls,
        cfg.API_DAILY_CALL_LIMIT,
        safety_limit,
        len(items),
    )

    for i, it in enumerate(items, 1):
        item_id = it["id"]
        img_path = REPO_ROOT / it["image"]
        if not img_path.exists():
            logger.error("[%02d/%02d] File not found: %s", i, len(items), img_path)
            continue

        # Load cached OCR ONLY (zero API calls for OCR)
        ocr_res = run_ocr(str(img_path), allow_gemini_fallback=False, use_cache=True)
        if not ocr_res.valid or not ocr_res.final_text:
            logger.error("[%02d/%02d] %s: No cached OCR text found!", i, len(items), item_id)
            continue

        display_text = strip_synthetic_watermark(ocr_res.final_text) if ocr_res.final_text else ""
        cleaned_text, _, _ = filter_pib_overlay_lines(display_text)
        norm_text = (cleaned_text or "").strip()

        # Check claim cache
        cache_key = compute_claim_cache_key(norm_text, cfg.GEMINI_MODEL, CLAIM_PROMPT_VERSION)
        cached_entry = claim_cache.get(cache_key)
        if cached_entry is not None:
            c_claim = (cached_entry.get("canonical_claim_en") or "")[:50]
            logger.info(
                "[%02d/%02d] %-25s [CACHED] type=%-15s claim='%s...'",
                i,
                len(items),
                item_id,
                cached_entry.get("claim_type", ""),
                c_claim,
            )
            continue

        # Check safety budget before making an API call
        current_calls = ocr_cache.get_daily_api_calls()
        if current_calls >= safety_limit:
            logger.warning(
                "Stopping claim warm-up early: daily counter %d reached safety limit %d",
                current_calls,
                safety_limit,
            )
            break

        logger.info(
            "[%02d/%02d] %-25s [CALLING GEMINI] (counter: %d -> %d / %d)...",
            i,
            len(items),
            item_id,
            current_calls,
            current_calls + 1,
            cfg.API_DAILY_CALL_LIMIT,
        )

        res = extract_claim(cleaned_text, allow_cloud=True, use_cache=True)
        new_calls = ocr_cache.get_daily_api_calls()
        c_claim = (res.canonical_claim_en or "")[:50]
        logger.info(
            "[%02d/%02d] %-25s [EXTRACTED] type=%-15s claim='%s...' (daily counter now: %d)",
            i,
            len(items),
            item_id,
            res.claim_type,
            c_claim,
            new_calls,
        )

    final_calls = ocr_cache.get_daily_api_calls()
    logger.info("Claim warm-up finished. Final daily API calls: %d / %d", final_calls, cfg.API_DAILY_CALL_LIMIT)


if __name__ == "__main__":
    warm_claims()
