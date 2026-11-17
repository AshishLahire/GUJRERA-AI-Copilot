"""Self-hosted OCR for uploaded ads, brochures and letters: Tesseract with Gujarati, Hindi and English.

- PDFs: the first page's text layer is used when present; otherwise the page is rendered and OCR'd.
- Images are converted to greyscale, small ones upscaled, and contrast stretched before OCR.
- Returns the text plus Tesseract's mean word confidence, so a weak read can be flagged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gujrera.config import get_gujrera_settings

LANGS = "guj+hin+eng"


@dataclass
class OcrOut:
    text: str
    engine: str
    confidence: float | None  # mean word confidence 0-100
    note: str | None = None


def tesseract_available() -> bool:
    try:
        import pytesseract
    except ImportError:
        return False
    cmd = get_gujrera_settings().GUJRERA_TESSERACT_CMD
    if cmd and Path(cmd).exists():
        pytesseract.pytesseract.tesseract_cmd = cmd
    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:  # noqa: BLE001 - binary missing
        return False
    return {"guj", "eng"} <= langs


def _prepare(image):
    from PIL import ImageOps

    img = image.convert("L")
    if img.width < 1400:
        scale = 1400 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    return ImageOps.autocontrast(img)


def _ocr_pil(image) -> tuple[str, float | None]:
    import pytesseract

    img = _prepare(image)
    text = pytesseract.image_to_string(img, lang=LANGS, config="--psm 6")
    data = pytesseract.image_to_data(img, lang=LANGS, config="--psm 6", output_type=pytesseract.Output.DICT)
    confs = [float(c) for c, w in zip(data["conf"], data["text"]) if str(w).strip() and float(c) >= 0]
    return text.strip(), (round(sum(confs) / len(confs), 1) if confs else None)


def ocr_file(path: Path) -> OcrOut:
    """OCR an image or the first page of a PDF with Tesseract (raises RuntimeError if unavailable)."""
    if not tesseract_available():
        raise RuntimeError("Tesseract with Gujarati data is not installed")
    from PIL import Image

    if path.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium

        page = pdfium.PdfDocument(str(path))[0]
        layer = page.get_textpage().get_text_range().strip()
        if len(layer) >= 40:
            return OcrOut(layer, "pdf-text", None, "Only page 1 of the PDF was read.")
        text, conf = _ocr_pil(page.render(scale=300 / 72).to_pil())
        return OcrOut(text, "tesseract", conf, "Only page 1 of the PDF was read.")
    with Image.open(path) as img:
        text, conf = _ocr_pil(img)
    return OcrOut(text, "tesseract", conf)
