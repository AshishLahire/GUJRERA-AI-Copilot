"""Stage 2a - OCR package."""

from factcheck.extract.ocr.cache import OCRCache, compute_cache_key, compute_image_hash
from factcheck.extract.ocr.fields import extract_fields, strip_synthetic_watermark
from factcheck.extract.ocr.prompts import PROMPT_VERSION, VLM_OCR_PROMPT
from factcheck.extract.ocr.runner import (
    render_pdf_first_page_to_png,
    run_ocr,
    strip_markdown_formatting,
)
from factcheck.extract.ocr.validation import is_valid_ocr_text

__all__ = [
    "OCRCache",
    "PROMPT_VERSION",
    "VLM_OCR_PROMPT",
    "compute_cache_key",
    "compute_image_hash",
    "extract_fields",
    "is_valid_ocr_text",
    "render_pdf_first_page_to_png",
    "run_ocr",
    "strip_markdown_formatting",
    "strip_synthetic_watermark",
]
