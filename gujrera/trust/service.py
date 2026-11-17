"""Entry points for the trust check: pasted text or an uploaded image/PDF."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from gujrera.db.repository import Repository
from gujrera.trust.checks import check_text
from gujrera.trust.ocr import OcrOut, ocr_file

LOW_CONFIDENCE = 55  # mean Tesseract word confidence below this is flagged to the user
MIN_TEXT_CHARS = 20


def _pramaan_ocr(path: Path, allow_cloud: bool) -> OcrOut:
    """Pramaan's OCR chain (local VLM via Ollama; Gemini only if explicitly allowed)."""
    from factcheck.extract.ocr import render_pdf_first_page_to_png, run_ocr  # heavy imports, load lazily

    target, note = path, None
    if path.suffix.lower() == ".pdf":
        target = render_pdf_first_page_to_png(path, dpi=200)
        note = "Only page 1 of the PDF was read."
    res = run_ocr(target, allow_gemini_fallback=allow_cloud, use_cache=True)
    return OcrOut(res.final_text or "", res.engine_used, None, note)


def read_document(path: Path, *, allow_cloud: bool = False) -> OcrOut:
    """Tesseract (Gujarati + Hindi + English) first, as committed in the deck; Pramaan's chain if
    Tesseract is missing or reads almost nothing."""
    try:
        out = ocr_file(path)
        if len(out.text.strip()) >= MIN_TEXT_CHARS:
            return out
    except RuntimeError:
        out = None
    try:
        fallback = _pramaan_ocr(path, allow_cloud)
        if len(fallback.text.strip()) > len((out.text if out else "").strip()):
            return fallback
    except Exception:  # noqa: BLE001 - optional engines not installed
        pass
    return out or OcrOut("", "none", None, "No OCR engine could read this file.")


def check_document(path: Path, repo: Repository, *, allow_cloud: bool = False,
                   as_of: date | None = None) -> dict[str, Any]:
    """OCR the document, then run the trust check on its text.

    ``allow_cloud`` stays False by default: the deck commits to self-hosted models and no paid API calls.
    """
    ocr = read_document(path, allow_cloud=allow_cloud)
    report = check_text(ocr.text, repo, as_of=as_of).to_dict()
    low = ocr.confidence is not None and ocr.confidence < LOW_CONFIDENCE
    report["ocr"] = {
        "text": ocr.text,
        "engine": ocr.engine,
        "valid": bool(ocr.text.strip()),
        "confidence": ocr.confidence,
        "low_confidence": low,
        "note": ocr.note or ("The photo was hard to read; check the text below before relying on the result."
                             if low else None),
    }
    return report
