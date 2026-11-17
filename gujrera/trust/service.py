"""Entry points for the trust check: pasted text or an uploaded image/PDF."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from gujrera.db.repository import Repository
from gujrera.trust.checks import check_text


def check_document(path: Path, repo: Repository, *, allow_cloud: bool = False,
                   as_of: date | None = None) -> dict[str, Any]:
    """OCR the document with Pramaan's OCR chain, then run the trust check on its text.

    ``allow_cloud`` stays False by default: the deck commits to self-hosted models
    and no paid API calls.
    """
    from factcheck.extract.ocr import render_pdf_first_page_to_png, run_ocr  # heavy imports, load lazily

    target = path
    note = None
    if path.suffix.lower() == ".pdf":
        target = render_pdf_first_page_to_png(path, dpi=200)
        note = "Only page 1 of the PDF was read."
    ocr = run_ocr(target, allow_gemini_fallback=allow_cloud, use_cache=True)
    report = check_text(ocr.final_text or "", repo, as_of=as_of).to_dict()
    report["ocr"] = {
        "text": ocr.final_text,
        "engine": ocr.engine_used,
        "valid": ocr.valid,
        "note": note,
    }
    return report
