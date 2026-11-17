"""Main OCR orchestration: caching, engine routing, markdown stripping, validation, and field extraction."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from factcheck.config import Settings, get_settings
from factcheck.extract.ocr.cache import OCRCache, compute_cache_key
from factcheck.extract.ocr.engines import (
    run_gemini_fallback,
    run_ollama_vlm,
    should_count_gemini_call,
    try_run_paddleocr,
)
from factcheck.extract.ocr.fields import extract_fields
from factcheck.extract.ocr.prompts import PROMPT_VERSION
from factcheck.extract.ocr.validation import is_valid_ocr_text
from factcheck.lang import detect_language
from factcheck.schemas import ExtractedFields, OCRResult

_CODE_FENCE_LINE_RE = re.compile(r"(?m)^\s*```[^\n]*\n?|^\s*```\s*$")

REPO_ROOT = Path(__file__).resolve().parents[3]
_HEADING_PREFIX_RE = re.compile(r"(?m)^(\s*)#{1,6}\s+")
_BOLD_MARKER_RE = re.compile(r"\*\*")


def render_pdf_first_page_to_png(
    pdf_path: str | Path,
    dpi: int = 200,
    output_path: str | Path | None = None,
) -> Path:
    """Render page 1 (index 0) of a PDF at ``dpi`` (default 200) to a PNG file using pypdfium2."""
    import pypdfium2 as pdfium

    src = Path(pdf_path).resolve()
    out = (
        Path(output_path).resolve()
        if output_path is not None
        else src.with_suffix(".page1.png")
    )
    doc = pdfium.PdfDocument(str(src))
    try:
        if len(doc) == 0:
            raise ValueError("PDF has no pages")
        page = doc[0]
        try:
            bitmap = page.render(scale=dpi / 72.0)
            pil_image = bitmap.to_pil()
            pil_image.save(out, format="PNG")
        finally:
            page.close()
    finally:
        doc.close()
    return out


def _make_ocr_result(
    *,
    image_hash: str,
    final_text: str,
    engine_used: str,
    valid: bool,
    fields: ExtractedFields,
    from_cache: bool = False,
    markdown_stripped: bool = False,
    time_ms: float = 0.0,
    note: str | None = None,
    error: str | None = None,
    cache_source: str | None = None,
    older_ocr_settings: bool = False,
) -> OCRResult:
    det = detect_language(final_text)
    return OCRResult(
        image_hash=image_hash,
        final_text=final_text,
        engine_used=engine_used,
        valid=valid,
        fields=fields,
        from_cache=from_cache,
        markdown_stripped=markdown_stripped,
        time_ms=time_ms,
        note=note,
        error=error,
        cache_source=cache_source,
        older_ocr_settings=older_ocr_settings,
        language=det.language,
        script=det.script,
        language_confidence=det.confidence,
        language_name=det.language_name,
        text_direction=det.direction,
        primary_language=det.primary_language,
        languages_present=[
            {"language": s.language, "share": s.share, "language_name": s.language_name, "script": s.script}
            for s in det.languages_present
        ],
        language_badge=det.display_badge,
        is_language_uncertain=det.is_uncertain,
    )


MIN_TEXT_LAYER_CHARS = 200


def read_pdf_text_layer(pdf_path: str | Path) -> str | None:
    """Return page 1's embedded text when the PDF is born-digital, else None (scanned / image-only).

    Legacy Hindi fonts (Kruti Dev etc.) extract as gibberish, so the text must also pass the same
    validity check as OCR output; otherwise the page is rendered and OCR'd as before.
    """
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(str(pdf_path))
    except Exception:
        return None
    try:
        if len(doc) == 0:
            return None
        page = doc[0]
        try:
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            textpage.close()
        finally:
            page.close()
    finally:
        doc.close()
    text = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if len(text) < MIN_TEXT_LAYER_CHARS or not is_valid_ocr_text(text):
        return None
    return text


def strip_markdown_formatting(text: str) -> tuple[str, bool]:
    """Strip leading '#' heading markers, '**' bold markers, and ``` fences from OCR output.

    Returns ``(cleaned_text, was_stripped)``.
    """
    if not text:
        return "", False
    cleaned = _CODE_FENCE_LINE_RE.sub("", text)
    cleaned = _HEADING_PREFIX_RE.sub(r"\1", cleaned)
    cleaned = _BOLD_MARKER_RE.sub("", cleaned)
    cleaned = cleaned.strip()
    was_stripped = cleaned != text.strip()
    return cleaned, was_stripped


def run_ocr(
    image_path: str | Path,
    *,
    settings: Settings | None = None,
    allow_gemini_fallback: bool = True,
    use_cache: bool = True,
    gemini_model: str | None = None,
    media_resolution: str | None = None,
) -> OCRResult:
    """Run the OCR pipeline on ``image_path`` and return an ``OCRResult``."""
    t0 = time.perf_counter()
    cfg = settings or get_settings()
    updates: dict[str, str] = {}
    if gemini_model:
        updates["GEMINI_MODEL"] = gemini_model
    if media_resolution:
        updates["GEMINI_MEDIA_RESOLUTION"] = media_resolution
    if updates:
        cfg = cfg.model_copy(update=updates)
    if cfg.OFFLINE_MODE:
        allow_gemini_fallback = False
    path = Path(image_path).resolve()

    if not path.exists():
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return _make_ocr_result(
            image_hash="",
            final_text="",
            engine_used="none",
            valid=False,
            fields=ExtractedFields(),
            from_cache=False,
            markdown_stripped=False,
            time_ms=elapsed_ms,
            error=f"Image file does not exist: {path}",
        )

    pdf_note: str | None = None
    if path.suffix.lower() == ".pdf":
        # Born-digital circulars carry an exact text layer: use it instead of OCR when it is usable.
        layer_text = read_pdf_text_layer(path)
        if layer_text is not None:
            fields = extract_fields(layer_text)
            return _make_ocr_result(
                image_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
                final_text=layer_text,
                engine_used="pdf_text_layer",
                valid=True,
                fields=fields,
                from_cache=False,
                markdown_stripped=False,
                time_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                note="Read from the PDF's embedded text layer (page 1); no OCR needed.",
                error=None,
            )
        path = render_pdf_first_page_to_png(path, dpi=200)
        pdf_note = "Only page 1 of the PDF was read."

    image_bytes = path.read_bytes()
    db_path = (
        cfg.CACHE_DB_PATH
        if cfg.CACHE_DB_PATH.is_absolute()
        else (REPO_ROOT / cfg.CACHE_DB_PATH if (REPO_ROOT / cfg.CACHE_DB_PATH).exists() else cfg.CACHE_DB_PATH)
    )
    cache = OCRCache(db_path)

    vlm_cache_key = compute_cache_key(
        image_bytes, "ollama", cfg.VLM_MODEL, PROMPT_VERSION
    )
    gem_cache_key = compute_cache_key(
        image_bytes, "gemini", cfg.GEMINI_MODEL, PROMPT_VERSION
    )
    paddle_cache_key = compute_cache_key(
        image_bytes, "paddleocr", "default", PROMPT_VERSION
    )

    if use_cache:
        if cfg.OFFLINE_MODE:
            candidate_entries: list[tuple[str, str, bool]] = [
                (
                    vlm_cache_key,
                    f"{PROMPT_VERSION} / {cfg.VLM_MODEL}",
                    False,
                ),
                (
                    paddle_cache_key,
                    f"{PROMPT_VERSION} / paddleocr",
                    False,
                ),
            ]
            candidate_engines_models = [
                ("ollama", cfg.VLM_MODEL),
                ("paddleocr", "default"),
            ]
        elif cfg.OCR_ENGINE_PREFERENCE == "gemini_first":
            candidate_entries: list[tuple[str, str, bool]] = [
                (
                    gem_cache_key,
                    f"{PROMPT_VERSION} / {cfg.GEMINI_MODEL} / {cfg.GEMINI_MEDIA_RESOLUTION} resolution",
                    False,
                ),
                (
                    vlm_cache_key,
                    f"{PROMPT_VERSION} / {cfg.VLM_MODEL}",
                    not cfg.OLLAMA_ENABLED,
                ),
                (
                    paddle_cache_key,
                    f"{PROMPT_VERSION} / paddleocr",
                    False,
                ),
            ]
            candidate_engines_models = [
                ("gemini", cfg.GEMINI_MODEL),
                ("gemini", "gemini-3.5-flash-lite"),
                ("gemini", "gemini-3.8-flash"),
                ("gemini", "gemini-2.5-flash"),
                ("gemini", "gemini-2.5-flash-lite"),
                ("gemini", "gemini-flash-latest"),
                ("ollama", cfg.VLM_MODEL),
                ("paddleocr", "default"),
            ]
        else:
            # qwen_first
            candidate_entries: list[tuple[str, str, bool]] = [
                (
                    vlm_cache_key,
                    f"{PROMPT_VERSION} / {cfg.VLM_MODEL}",
                    False,
                ),
                (
                    gem_cache_key,
                    f"{PROMPT_VERSION} / {cfg.GEMINI_MODEL} / {cfg.GEMINI_MEDIA_RESOLUTION} resolution",
                    True,
                ),
                (
                    paddle_cache_key,
                    f"{PROMPT_VERSION} / paddleocr",
                    False,
                ),
            ]
            candidate_engines_models = [
                ("ollama", cfg.VLM_MODEL),
                ("gemini", cfg.GEMINI_MODEL),
                ("gemini", "gemini-3.5-flash-lite"),
                ("gemini", "gemini-3.8-flash"),
                ("gemini", "gemini-2.5-flash"),
                ("gemini", "gemini-2.5-flash-lite"),
                ("gemini", "gemini-flash-latest"),
                ("paddleocr", "default"),
            ]
        seen_keys = {k for k, _, _ in candidate_entries}
        for pv in ("v3", "v2", "v1"):
            for eng, mod in candidate_engines_models:
                ck = compute_cache_key(image_bytes, eng, mod, pv)
                if ck not in seen_keys:
                    seen_keys.add(ck)
                    is_fallback = (
                        (pv != PROMPT_VERSION)
                        or (eng == "gemini" and mod != cfg.GEMINI_MODEL)
                        or (eng == "ollama" and not cfg.OLLAMA_ENABLED)
                    )
                    desc = f"{pv} / {mod}"
                    if eng == "gemini":
                        desc += f" / {cfg.GEMINI_MEDIA_RESOLUTION} resolution"
                    candidate_entries.append((ck, desc, is_fallback))
        raw_sha = hashlib.sha256(image_bytes).hexdigest()
        if raw_sha not in seen_keys:
            candidate_entries.append((raw_sha, "raw_sha256 / legacy hash", True))

        for ckey, src_desc, is_fallback in candidate_entries:
            cached = cache.get(ckey)
            if cached is not None:
                cached_time = cached.get("time_ms")
                reported_time_ms = (
                    round(float(cached_time), 2)
                    if cached_time is not None
                    else 0.0
                )
                cleaned_text, stripped = strip_markdown_formatting(cached["final_text"])
                fields = extract_fields(cleaned_text)
                if is_fallback:
                    import logging
                    logging.getLogger("factcheck.api").warning(
                        "OCR cache fallback used for %s: %s (key=%s, engine=%s)",
                        path.name,
                        src_desc,
                        ckey,
                        cached.get("engine_used", "none"),
                    )
                return _make_ocr_result(
                    image_hash=ckey,
                    final_text=cleaned_text,
                    engine_used=cached["engine_used"],
                    valid=bool(cached["valid"]),
                    fields=fields,
                    from_cache=True,
                    markdown_stripped=stripped,
                    time_ms=reported_time_ms,
                    note=pdf_note,
                    error=None,
                    cache_source=src_desc if is_fallback else None,
                    older_ocr_settings=is_fallback,
                )

    # 1. Optional Tier-1 PaddleOCR (used only if importable and high confidence)
    paddle_res = try_run_paddleocr(path, cfg)
    if paddle_res is not None:
        p_text, p_conf, p_engine = paddle_res
        p_clean, p_stripped = strip_markdown_formatting(p_text)
        if p_conf >= cfg.TIER1_CONFIDENCE_THRESHOLD and is_valid_ocr_text(p_clean):
            p_model = p_engine.split(":", 1)[1] if ":" in p_engine else "default"
            p_key = compute_cache_key(
                image_bytes, "paddleocr", p_model, PROMPT_VERSION
            )
            fields = extract_fields(p_clean)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if use_cache:
                cache.set(
                    image_hash=p_key,
                    final_text=p_clean,
                    engine_used=p_engine,
                    valid=True,
                    fields=fields.model_dump(),
                    time_ms=elapsed_ms,
                )
            return _make_ocr_result(
                image_hash=p_key,
                final_text=p_clean,
                engine_used=p_engine,
                valid=True,
                fields=fields,
                from_cache=False,
                markdown_stripped=p_stripped,
                time_ms=elapsed_ms,
                note=pdf_note,
                error=None,
            )

    # 2. Main Engine: Local VLM via Ollama (skipped when OLLAMA_ENABLED is False and not OFFLINE_MODE)
    if cfg.OLLAMA_ENABLED or cfg.OFFLINE_MODE:
        vlm_max_side = 1200 if cfg.OFFLINE_MODE else None
        vlm_timeout = 90.0 if cfg.OFFLINE_MODE else 120.0
        try:
            vlm_raw_text, vlm_engine, vlm_error = run_ollama_vlm(
                path,
                cfg,
                max_image_long_side=vlm_max_side,
                timeout=vlm_timeout,
            )
        except TypeError:
            vlm_raw_text, vlm_engine, vlm_error = run_ollama_vlm(path, cfg)
        vlm_text, vlm_stripped = strip_markdown_formatting(vlm_raw_text)
        vlm_valid = is_valid_ocr_text(vlm_text)
    else:
        vlm_text, vlm_stripped = "", False
        vlm_engine = f"ollama:{cfg.VLM_MODEL}"
        vlm_error = "Ollama is disabled (OLLAMA_ENABLED=false)"
        vlm_valid = False

    if vlm_valid:
        fields = extract_fields(vlm_text)
        is_mock_engine = "mock" in vlm_engine.lower()
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if use_cache and not is_mock_engine:
            cache.set(
                image_hash=vlm_cache_key,
                final_text=vlm_text,
                engine_used=vlm_engine,
                valid=True,
                fields=fields.model_dump(),
                time_ms=elapsed_ms,
            )
        return _make_ocr_result(
            image_hash=vlm_cache_key,
            final_text=vlm_text,
            engine_used=vlm_engine,
            valid=True,
            fields=fields,
            from_cache=False,
            markdown_stripped=vlm_stripped,
            time_ms=elapsed_ms,
            note=pdf_note,
            error=None,
        )

    # 3. Fallback Engine: Gemini (only when VLM output fails validation AND key is set AND allowed)
    has_gemini_key = bool(
        cfg.GEMINI_API_KEY and cfg.GEMINI_API_KEY.get_secret_value().strip()
    )
    if allow_gemini_fallback and has_gemini_key:
        daily_calls = cache.get_daily_api_calls()
        if daily_calls >= cfg.API_DAILY_CALL_LIMIT:
            fallback_err = (
                f"Gemini daily call limit reached ({daily_calls}/{cfg.API_DAILY_CALL_LIMIT})"
            )
            combined_err = (
                f"{vlm_error}; {fallback_err}" if vlm_error else fallback_err
            )
        else:
            cached_gem = cache.get(gem_cache_key) if use_cache else None
            if cached_gem is not None:
                cleaned_text, stripped = strip_markdown_formatting(cached_gem["final_text"])
                fields = extract_fields(cleaned_text)
                return _make_ocr_result(
                    image_hash=gem_cache_key,
                    final_text=cleaned_text,
                    engine_used=cached_gem["engine_used"],
                    valid=bool(cached_gem["valid"]),
                    fields=fields,
                    from_cache=True,
                    markdown_stripped=stripped,
                    time_ms=round(float(cached_gem.get("time_ms") or 0.0), 2),
                    note=pdf_note,
                    error=None,
                    older_ocr_settings=True,
                )
            gem_raw_text, gem_engine, gem_error = run_gemini_fallback(path, cfg)
            if should_count_gemini_call(gem_error):
                cache.increment_daily_api_calls()
            gem_text, gem_stripped = strip_markdown_formatting(gem_raw_text)
            gem_valid = is_valid_ocr_text(gem_text)
            fields = extract_fields(gem_text)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if gem_valid and use_cache and "mock" not in gem_engine.lower():
                cache.set(
                    image_hash=gem_cache_key,
                    final_text=gem_text,
                    engine_used=gem_engine,
                    valid=True,
                    fields=fields.model_dump(),
                    time_ms=elapsed_ms,
                )
            return _make_ocr_result(
                image_hash=gem_cache_key,
                final_text=gem_text,
                engine_used=gem_engine,
                valid=gem_valid,
                fields=fields,
                from_cache=False,
                markdown_stripped=gem_stripped,
                time_ms=elapsed_ms,
                note=pdf_note,
                error=gem_error if not gem_valid else None,
            )
    else:
        combined_err = vlm_error or "VLM output failed validation (empty, <10 chars, or repetitive)"

    fields = extract_fields(vlm_text)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return _make_ocr_result(
        image_hash=vlm_cache_key,
        final_text=vlm_text,
        engine_used=vlm_engine,
        valid=False,
        fields=fields,
        from_cache=False,
        markdown_stripped=vlm_stripped,
        time_ms=elapsed_ms,
        note=pdf_note,
        error=combined_err,
    )
