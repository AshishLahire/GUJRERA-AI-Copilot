"""Warm the SQLite OCR cache for all demo images in ``data/demo/demo_set.json``.

Runs each demo image sequentially through ``run_ocr`` with ``allow_gemini_fallback=True``
and ``use_cache=True``, skipping any image already cached under the current key
``SHA-256(image_bytes + engine + model_name + prompt_version)``.

Stops early if the daily API call counter would exceed ``API_DAILY_CALL_LIMIT - 5``
or if a Gemini configuration error (400/401/403/404) occurs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from factcheck.config import get_settings
from factcheck.extract.ocr.cache import OCRCache, compute_cache_key
from factcheck.extract.ocr.engines import is_gemini_config_error
from factcheck.extract.ocr.prompts import PROMPT_VERSION
from factcheck.extract.ocr.runner import run_ocr

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_MANIFEST_PATH = PROJECT_ROOT / "data" / "demo" / "demo_set.json"


def warm_demo_cache() -> int:
    settings = get_settings()
    cache = OCRCache(settings.CACHE_DB_PATH)
    max_allowed_calls = max(0, settings.API_DAILY_CALL_LIMIT - 5)

    if not DEMO_MANIFEST_PATH.exists():
        print(f"ERROR: Demo manifest not found at {DEMO_MANIFEST_PATH}", file=sys.stderr)
        return 1

    payload = json.loads(DEMO_MANIFEST_PATH.read_text(encoding="utf-8"))
    items = payload["items"] if isinstance(payload, dict) else payload
    total = len(items)

    print(
        f"=== Warming Demo OCR Cache ({total} items, prompt={PROMPT_VERSION}, "
        f"stop threshold={max_allowed_calls}/{settings.API_DAILY_CALL_LIMIT}) ==="
    )

    for idx, item in enumerate(items, start=1):
        item_id = item["id"]
        img_path = (PROJECT_ROOT / item["image"]).resolve()
        if not img_path.exists():
            print(f"[{idx:02d}/{total:02d}] {item_id}: MISSING FILE ({img_path})")
            continue

        img_bytes = img_path.read_bytes()
        vlm_key = compute_cache_key(
            img_bytes, "ollama", settings.VLM_MODEL, PROMPT_VERSION
        )
        gem_key = compute_cache_key(
            img_bytes, "gemini", settings.GEMINI_MODEL, PROMPT_VERSION
        )

        if cache.get(vlm_key) is not None or cache.get(gem_key) is not None:
            daily = cache.get_daily_api_calls()
            print(
                f"[{idx:02d}/{total:02d}] {item_id:28s} | SKIPPED (already cached) | "
                f"daily_calls={daily}/{settings.API_DAILY_CALL_LIMIT}"
            )
            continue

        daily = cache.get_daily_api_calls()
        if daily >= max_allowed_calls:
            print(
                f"\nStopping warm-up: daily counter ({daily}) reached safety cap "
                f"(API_DAILY_CALL_LIMIT - 5 = {max_allowed_calls})."
            )
            break

        res = run_ocr(
            img_path,
            settings=settings,
            allow_gemini_fallback=True,
            use_cache=True,
        )
        daily_after = cache.get_daily_api_calls()
        status = "OK" if res.valid else f"FAIL ({res.error})"
        print(
            f"[{idx:02d}/{total:02d}] {item_id:28s} | {status} | "
            f"engine={res.engine_used} | time={res.time_ms:.1f}ms | "
            f"refs={res.fields.reference_numbers} | "
            f"daily_calls={daily_after}/{settings.API_DAILY_CALL_LIMIT}"
        )

        if is_gemini_config_error(res.error):
            print(
                f"\nStopping warm-up due to Gemini configuration error: {res.error}",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(warm_demo_cache())
