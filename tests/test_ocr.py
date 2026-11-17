"""Mocked unit tests for Stage 2a OCR (cache hit, fallback gating, regex field extraction)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pydantic import SecretStr

from factcheck.config import Settings
from factcheck.extract.ocr import (
    OCRCache,
    PROMPT_VERSION,
    VLM_OCR_PROMPT,
    compute_cache_key,
    compute_image_hash,
    extract_fields,
    is_valid_ocr_text,
    run_ocr,
    strip_markdown_formatting,
    strip_synthetic_watermark,
)


def _make_sample_image(path: Path, color: tuple[int, int, int] = (240, 240, 240)) -> bytes:
    im = Image.new("RGB", (200, 100), color=color)
    im.save(path, format="PNG")
    return path.read_bytes()


def test_cache_hit_skips_engine(tmp_path: Path, monkeypatch):
    img_path = tmp_path / "cached_doc.png"
    raw_bytes = _make_sample_image(img_path)
    img_hash = compute_cache_key(raw_bytes, "ollama", "qwen3-vl:8b", PROMPT_VERSION)

    db_path = tmp_path / "cache.sqlite"
    cache = OCRCache(db_path)
    cached_text = (
        "Reserve Bank of India\n"
        "Circular Ref: RBI/FED/2026-27/298\n"
        "Dated October 23, 2026\n"
        "Subject: Delegation of Compounding of Contraventions under FEMA, 1999"
    )
    cache.set(
        image_hash=img_hash,
        final_text=cached_text,
        engine_used="ollama:qwen3-vl:8b",
        valid=True,
        fields=extract_fields(cached_text).model_dump(),
    )

    # Any engine call must fail the test if invoked on a cache hit
    def _fail_engine(*args, **kwargs):
        raise AssertionError("OCR engine should not be called on a cache hit")

    monkeypatch.setattr("factcheck.extract.ocr.runner.try_run_paddleocr", _fail_engine)
    monkeypatch.setattr("factcheck.extract.ocr.runner.run_ollama_vlm", _fail_engine)
    monkeypatch.setattr("factcheck.extract.ocr.runner.run_gemini_fallback", _fail_engine)

    settings = Settings(_env_file=None, CACHE_DB_PATH=db_path)
    res = run_ocr(img_path, settings=settings)

    assert res.from_cache is True
    assert res.valid is True
    assert res.image_hash == img_hash
    assert res.engine_used == "ollama:qwen3-vl:8b"
    assert "RBI/FED/2026-27/298" in res.fields.reference_numbers


def test_fallback_not_called_when_vlm_output_is_valid(tmp_path: Path, monkeypatch):
    img_path = tmp_path / "valid_vlm.png"
    _make_sample_image(img_path, color=(200, 220, 240))
    db_path = tmp_path / "cache.sqlite"

    valid_vlm_text = (
        "RESERVE BANK OF INDIA\n"
        "Ref: RBI/2025-26/45\n"
        "Date: 12/08/2025\n"
        "Subject: Master Direction on Digital Payment Security Controls"
    )

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.try_run_paddleocr", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_ollama_vlm",
        lambda path, cfg: (valid_vlm_text, "ollama:qwen3-vl:8b", None),
    )

    fallback_called = False

    def _mock_gemini(*args, **kwargs):
        nonlocal fallback_called
        fallback_called = True
        return (" Gemini text ", "gemini:gemini-2.5-flash", None)

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_gemini_fallback", _mock_gemini
    )

    settings = Settings(
        _env_file=None,
        CACHE_DB_PATH=db_path,
        GEMINI_API_KEY=SecretStr("fake-test-key"),
    )
    res = run_ocr(img_path, settings=settings, allow_gemini_fallback=True)

    assert fallback_called is False
    assert res.valid is True
    assert res.from_cache is False
    assert res.engine_used == "ollama:qwen3-vl:8b"
    assert "RBI/2025-26/45" in res.fields.reference_numbers


def test_fields_extract_rbi_and_other_references():
    sample_text = (
        "SYNTHETIC - NOT A REAL DOCUMENT - FOR DETECTOR TRAINING\n"
        "Reserve Bank of India\n"
        "Circular No: RBI/FED/2026-27/298 and prior circular RBI/2025-26/45\n"
        "Also see RBI/2026-27/299, Gazette Notification S.O. 4268(E), and Order No. 68/2024/GOVT.\n"
        "Date: October 23, 2026 | Contact: +91-9876543210 | helpdesk@rbi.org.in\n"
        "Portal: https://www.rbi.org.in/scripts/Notification.aspx\n"
        "Processing fee demanded: Rs. 2,100 and ₹5,00,000 loan.\n"
        "Subject: Revised timelines for submission of quarterly returns\n"
    )

    cleaned = strip_synthetic_watermark(sample_text)
    assert "SYNTHETIC - NOT A REAL DOCUMENT" not in cleaned
    assert "FOR DETECTOR TRAINING" not in cleaned

    fields = extract_fields(sample_text)
    assert "RBI/FED/2026-27/298" in fields.reference_numbers
    assert "RBI/2025-26/45" in fields.reference_numbers
    assert "RBI/2026-27/299" in fields.reference_numbers
    assert any("S.O. 4268(E)" in r for r in fields.reference_numbers)
    assert any("No. 68/2024/GOVT" in r for r in fields.reference_numbers)
    assert "October 23, 2026" in fields.dates
    assert "+91-9876543210" in fields.phone_numbers
    assert "helpdesk@rbi.org.in" in fields.emails
    assert "https://www.rbi.org.in/scripts/Notification.aspx" in fields.urls
    assert "Rs. 2,100" in fields.rupee_amounts
    assert "₹5,00,000" in fields.rupee_amounts
    assert fields.subject == "Revised timelines for submission of quarterly returns"


def test_validation_rejects_empty_short_and_repetitive_text():
    assert is_valid_ocr_text("") is False
    assert is_valid_ocr_text("short") is False
    assert is_valid_ocr_text("aaaaaaaaaaaaaaaaaaaaaaaaaaaa") is False
    assert is_valid_ocr_text(("repeat line\n") * 10) is False
    assert is_valid_ocr_text("Government of India official circular dated 2026-10-23.") is True


def test_streamlit_app_demo_samples_end_to_end(tmp_path: Path, monkeypatch):
    """Verify Streamlit app end-to-end with one demo sample from each group (fake, genuine, synthetic)."""
    pytest.importorskip("streamlit", reason="optional 'ui' extra not installed")
    from streamlit.testing.v1 import AppTest

    db_path = tmp_path / "ui_cache.sqlite"
    settings = Settings(_env_file=None, CACHE_DB_PATH=db_path)
    monkeypatch.setattr("factcheck.extract.ocr.runner.get_settings", lambda: settings)
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.try_run_paddleocr", lambda *a, **kw: None
    )

    mock_texts = {
        "FN-TG-01999.jpg": (
            "GOVERNMENT OF INDIA - MINISTRY OF RAILWAYS\n"
            "RBE No. 101/2026\n"
            "No. E(P&A)II/2026/PLB-1\n"
            "Date: 15/10/2026\n"
            "Subject: Payment of Productivity Linked Bonus"
        ),
        "OFF-51452FA980__wa_compress.jpg": (
            "CENTRAL BOARD OF SECONDARY EDUCATION\n"
            "Circular No: Acad-67/2026\n"
            "Date: October 20, 2026\n"
            "Subject: Expression Series for Session 2026-27"
        ),
        "SYN-0001.png": (
            "SYNTHETIC - NOT A REAL DOCUMENT - FOR DETECTOR TRAINING\n"
            "National Financial Regulatory Authority (Fictional)\n"
            "Ref: NFRA/2024-25/260\n"
            "Date: 2024-12-09\n"
            "Subject: Revised timelines for submission of quarterly returns"
        ),
    }

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_ollama_vlm",
        lambda path, cfg: (
            mock_texts.get(Path(path).name, "Default valid OCR transcript text"),
            f"mock-ollama:{cfg.VLM_MODEL}",
            None,
        ),
    )

    app_path = Path(__file__).resolve().parents[1] / "factcheck" / "ui" / "app.py"
    at = AppTest.from_file(app_path, default_timeout=30)
    at.run()
    assert not at.exception

    # Default state: Allow Gemini fallback checkbox is False
    assert at.checkbox[0].value is False

    # Select 1 fake, 1 genuine, and 1 synthetic sample from the dropdown
    options = at.selectbox[0].options
    for target_prefix, expected_ref in [
        ("FN-TG-01999", "RBE No. 101/2026"),
        ("OFF-51452FA980__wa_compress", "Acad-67/2026"),
        ("SYN-0001", "NFRA/2024-25/260"),
    ]:
        matching_opt = next(o for o in options if o.startswith(target_prefix))
        at.selectbox[0].select(matching_opt).run()
        assert not at.exception
        code_vals = [c.value for c in at.code]
        assert any(expected_ref in c for c in code_vals)
        md_vals = "\n".join(m.value for m in at.markdown)
        assert "✅" in md_vals



def test_fallback_used_when_ollama_is_down(tmp_path: Path, monkeypatch):
    """If Ollama is unreachable AND Allow Gemini fallback is enabled AND GEMINI_API_KEY is set, use Gemini."""
    img_path = tmp_path / "ollama_down.png"
    _make_sample_image(img_path, color=(210, 210, 210))
    db_path = tmp_path / "cache.sqlite"

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.try_run_paddleocr", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_ollama_vlm",
        lambda path, cfg: (
            "",
            f"ollama:{cfg.VLM_MODEL}",
            "Ollama is not running or unreachable at http://localhost:11434: ConnectError",
        ),
    )

    gemini_text = (
        "RESERVE BANK OF INDIA\n"
        "Circular No: RBI/FED/2026-27/298\n"
        "Dated: October 23, 2026\n"
        "Subject: Delegation of Compounding of Contraventions under FEMA, 1999"
    )
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_gemini_fallback",
        lambda path, cfg: (gemini_text, f"gemini:{cfg.GEMINI_MODEL}", None),
    )

    settings = Settings(
        _env_file=None,
        CACHE_DB_PATH=db_path,
        GEMINI_API_KEY=SecretStr("test-gemini-key"),
    )
    res = run_ocr(img_path, settings=settings, allow_gemini_fallback=True)

    assert res.valid is True
    assert res.error is None
    assert res.engine_used == "gemini:gemini-3.5-flash-lite"
    assert "RBI/FED/2026-27/298" in res.fields.reference_numbers
    assert OCRCache(db_path).get_daily_api_calls() == 1


def test_mock_safety_no_ui_mock_and_never_cached(tmp_path: Path, monkeypatch):
    """Confirm app.py has no mock path and mock VLM outputs are never cached."""
    app_file = Path(__file__).resolve().parents[1] / "factcheck" / "ui" / "app.py"
    app_source = app_file.read_text(encoding="utf-8").lower()
    assert "mock" not in app_source

    img_path = tmp_path / "mock_doc.png"
    raw_bytes = _make_sample_image(img_path, color=(180, 200, 220))
    img_hash = compute_image_hash(raw_bytes)
    db_path = tmp_path / "cache.sqlite"

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.try_run_paddleocr", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_ollama_vlm",
        lambda path, cfg: (
            "Reserve Bank of India Circular RBI/2025-26/45 dated October 23, 2026",
            "mock-ollama:qwen3-vl:8b",
            None,
        ),
    )

    settings = Settings(_env_file=None, CACHE_DB_PATH=db_path)
    res = run_ocr(img_path, settings=settings, use_cache=True)
    assert res.valid is True
    assert OCRCache(db_path).get(img_hash) is None



def test_gemini_404_does_not_increment_counter(tmp_path: Path, monkeypatch):
    """A 400/401/403/404 Gemini configuration error must not increment the daily API counter."""
    img_path = tmp_path / "gemini_404.png"
    _make_sample_image(img_path, color=(225, 225, 225))
    db_path = tmp_path / "cache.sqlite"

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.try_run_paddleocr", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_ollama_vlm",
        lambda path, cfg: (
            "",
            f"ollama:{cfg.VLM_MODEL}",
            "Ollama is not running or unreachable at http://localhost:11434: timed out",
        ),
    )
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_gemini_fallback",
        lambda path, cfg: (
            "",
            f"gemini:{cfg.GEMINI_MODEL}",
            "Gemini API error: 404 NOT_FOUND. {'error': {'code': 404, 'status': 'NOT_FOUND'}}",
        ),
    )

    settings = Settings(
        _env_file=None,
        CACHE_DB_PATH=db_path,
        GEMINI_API_KEY=SecretStr("test-gemini-key"),
    )
    res = run_ocr(img_path, settings=settings, allow_gemini_fallback=True)

    assert res.valid is False
    assert res.error is not None and "404" in res.error
    assert OCRCache(db_path).get_daily_api_calls() == 0



def test_reference_substring_deduplication():
    """Drop a reference number when it is a substring of another reference in the same text."""
    text = (
        "GOVERNMENT OF INDIA\n"
        "MINISTRY OF RAILWAYS (RAILWAY BOARD)\n"
        "RBE No. 101/2026\n"
        "Circular No. E(P&A)II/2026/PLB-1 dated 15.10.2026\n"
    )
    fields = extract_fields(text)
    assert "RBE No. 101/2026" in fields.reference_numbers
    assert "No. 101/2026" not in fields.reference_numbers


def test_markdown_stripping_and_prompt_v2(tmp_path: Path, monkeypatch):
    """Prompt v3 requires plain text, and runner strips #, **, and ``` fences."""
    assert PROMPT_VERSION == "v3"
    assert "Output plain text only." in VLM_OCR_PROMPT
    assert "Do not use markdown, headings, bold, bullet symbols or code blocks." in VLM_OCR_PROMPT

    raw_md = "```text\n# FAKE\n## DOCUMENT ALERT\n❌ **The letter is FAKE.**\nRBE No. 101/2026\n```"
    cleaned, was_stripped = strip_markdown_formatting(raw_md)
    assert was_stripped is True
    assert "```" not in cleaned
    assert "# " not in cleaned
    assert "**" not in cleaned
    assert "FAKE" in cleaned

    img_path = tmp_path / "md_doc.png"
    _make_sample_image(img_path, color=(205, 210, 215))
    db_path = tmp_path / "cache.sqlite"

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.try_run_paddleocr", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_ollama_vlm",
        lambda path, cfg: (raw_md, f"ollama:{cfg.VLM_MODEL}", None),
    )

    settings = Settings(_env_file=None, CACHE_DB_PATH=db_path)
    res = run_ocr(img_path, settings=settings)
    assert res.valid is True
    assert res.markdown_stripped is True
    assert "**" not in res.final_text
    assert "```" not in res.final_text
    assert res.fields.reference_numbers == ["RBE No. 101/2026"]



def test_ollama_disabled_goes_straight_to_gemini(tmp_path: Path, monkeypatch):
    """When OLLAMA_ENABLED is False, skip Ollama entirely and call Gemini when allowed."""
    img_path = tmp_path / "ollama_disabled.png"
    _make_sample_image(img_path, color=(190, 210, 230))
    db_path = tmp_path / "cache.sqlite"

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.try_run_paddleocr", lambda *a, **kw: None
    )

    def _fail_ollama(*args, **kwargs):
        raise AssertionError("Ollama must not be called when OLLAMA_ENABLED=False")

    monkeypatch.setattr("factcheck.extract.ocr.runner.run_ollama_vlm", _fail_ollama)
    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.run_gemini_fallback",
        lambda path, cfg: (
            "CENTRAL BOARD OF SECONDARY EDUCATION Circular No: Acad-67/2026",
            f"gemini:{cfg.GEMINI_MODEL}",
            None,
        ),
    )

    settings = Settings(
        _env_file=None,
        OLLAMA_ENABLED=False,
        CACHE_DB_PATH=db_path,
        GEMINI_API_KEY=SecretStr("test-gemini-key"),
    )
    res = run_ocr(img_path, settings=settings, allow_gemini_fallback=True)
    assert res.valid is True
    assert res.engine_used == "gemini:gemini-3.5-flash-lite"
    assert res.fields.reference_numbers == ["Acad-67/2026"]


def test_cached_gemini_result_returned_when_fallback_toggle_is_off(
    tmp_path: Path, monkeypatch
):
    """A cached Gemini result must be returned even when allow_gemini_fallback=False, calling no API."""
    img_path = tmp_path / "cached_gemini_doc.png"
    raw_bytes = _make_sample_image(img_path, color=(230, 220, 210))
    db_path = tmp_path / "cache.sqlite"

    gem_key = compute_cache_key(
        raw_bytes, "gemini", "gemini-3.5-flash-lite", PROMPT_VERSION
    )
    cached_text = (
        "GOVERNMENT OF INDIA\n"
        "MINISTRY OF RAILWAYS\n"
        "RBE No. 101/2026\n"
        "Subject: Productivity Linked Bonus"
    )
    cache = OCRCache(db_path)
    cache.set(
        image_hash=gem_key,
        final_text=cached_text,
        engine_used="gemini:gemini-3.5-flash-lite",
        valid=True,
        fields=extract_fields(cached_text).model_dump(),
    )

    def _fail_any_engine(*args, **kwargs):
        raise AssertionError("No engine or API may be called on a cache hit")

    monkeypatch.setattr("factcheck.extract.ocr.runner.try_run_paddleocr", _fail_any_engine)
    monkeypatch.setattr("factcheck.extract.ocr.runner.run_ollama_vlm", _fail_any_engine)
    monkeypatch.setattr("factcheck.extract.ocr.runner.run_gemini_fallback", _fail_any_engine)

    settings = Settings(_env_file=None, CACHE_DB_PATH=db_path)
    res = run_ocr(img_path, settings=settings, allow_gemini_fallback=False, use_cache=True)

    assert res.from_cache is True
    assert res.valid is True
    assert res.engine_used == "gemini:gemini-3.5-flash-lite"
    assert "RBE No. 101/2026" in res.fields.reference_numbers
    assert cache.get_daily_api_calls() == 0


def test_pdf_first_page_converted_at_200_dpi_and_noted(tmp_path: Path, monkeypatch):
    """A 1-page PDF input is rendered at 200 DPI via pypdfium2 and notes only page 1 was read."""
    pdf_path = tmp_path / "sample_notice.pdf"
    im = Image.new("RGB", (400, 300), color=(255, 255, 255))
    im.save(pdf_path, format="PDF", resolution=72.0)

    db_path = tmp_path / "cache.sqlite"
    rendered_paths: list[Path] = []

    monkeypatch.setattr(
        "factcheck.extract.ocr.runner.try_run_paddleocr", lambda *a, **kw: None
    )

    def _mock_vlm(path: Path, cfg: Settings):
        rendered_paths.append(Path(path))
        return (
            "CENTRAL BOARD OF SECONDARY EDUCATION\nCircular No: Acad-67/2026\nSubject: Demo PDF",
            f"ollama:{cfg.VLM_MODEL}",
            None,
        )

    monkeypatch.setattr("factcheck.extract.ocr.runner.run_ollama_vlm", _mock_vlm)

    settings = Settings(_env_file=None, CACHE_DB_PATH=db_path)
    res = run_ocr(pdf_path, settings=settings, allow_gemini_fallback=False)

    assert res.valid is True
    assert res.note is not None and "page 1" in res.note.lower()
    assert len(rendered_paths) == 1
    assert rendered_paths[0].suffix.lower() == ".png"
    assert rendered_paths[0].exists()
    with Image.open(rendered_paths[0]) as rendered_im:
        # 400x300 pt at 200/72 scale -> ~1111x833 px
        assert rendered_im.width > 1000
        assert rendered_im.height > 800
    assert "Acad-67/2026" in res.fields.reference_numbers


def test_near_duplicate_references_flagged():
    """Keep both similar references (differing by 1-2 chars with same prefix) and flag near_duplicate_references."""
    text = (
        "GOVERNMENT OF INDIA\n"
        "MINISTRY OF RAILWAYS (RAILWAY BOARD)\n"
        "RBE No. 191/2026\n"
        "New Delhi, dt. 06/10/2026\n"
        "Railway Board has clarified that the purported letter bearing RBE No. 101/2026 is fake.\n"
    )
    fields = extract_fields(text)
    assert "RBE No. 191/2026" in fields.reference_numbers
    assert "RBE No. 101/2026" in fields.reference_numbers
    assert fields.near_duplicate_references == [
        ["RBE No. 191/2026", "RBE No. 101/2026"]
    ]

    result_panel_src = (
        Path(__file__).resolve().parents[1]
        / "frontend"
        / "src"
        / "components"
        / "ResultPanel.tsx"
    ).read_text(encoding="utf-8")
    assert (
        "Two similar reference numbers found: possible OCR misread or"
        in result_panel_src
    )
    assert "tampering. Check the document." in result_panel_src


def test_bare_domain_extraction_and_suspicious_domains():
    """Extract bare domains and flag suspicious lookalike/non-official/fraudulent domains, never flagging mha.gov.in."""
    text = (
        "MINISTRY OF HOME AFFAIRS\n"
        "Ref No: GOI/MHA/2026/S-202 and DOR.ORG.REC.22/21.06.050/2026-27\n"
        "Amount: Rs. 2,550.50 (rate 3.14)\n"
        "Contact email: support@mha.gov.in\n"
        "For verification visit mina.gov.is or nic.in.co or https://mha.gov.in/notifications\n"
        "Also reported: nchmr.com and rbi.org.is\n"
    )
    fields = extract_fields(text)

    # Emails stay in emails
    assert "support@mha.gov.in" in fields.emails

    # Bare domains and URLs extracted without false matches on decimals or reference numbers
    assert "mina.gov.is" in fields.urls
    assert "nic.in.co" in fields.urls
    assert "https://mha.gov.in/notifications" in fields.urls
    assert "nchmr.com" in fields.urls
    assert "rbi.org.is" in fields.urls
    assert not any("21.06" in u or "2550.50" in u or "3.14" in u for u in fields.urls)
    assert not any("DOR.ORG" in u for u in fields.urls)

    # Suspicious domains flagged, while official mha.gov.in is NOT flagged
    assert "mina.gov.is" in fields.suspicious_domains
    assert "nic.in.co" in fields.suspicious_domains
    assert "nchmr.com" in fields.suspicious_domains
    assert "rbi.org.is" in fields.suspicious_domains
    assert "mha.gov.in" not in fields.suspicious_domains

    result_panel_src = (
        Path(__file__).resolve().parents[1]
        / "frontend"
        / "src"
        / "components"
        / "ResultPanel.tsx"
    ).read_text(encoding="utf-8")
    assert "Lookalike or non-official domain: verify" in result_panel_src


def test_cached_result_stores_and_returns_original_ocr_time(tmp_path: Path):
    """Cache entries store original time_ms and return it on cache hit; entries without time_ms return 0.0."""
    img_path = tmp_path / "timed_doc.png"
    raw_bytes = _make_sample_image(img_path, color=(215, 225, 235))
    db_path = tmp_path / "cache.sqlite"
    cache = OCRCache(db_path)

    key_with_time = compute_cache_key(
        raw_bytes, "gemini", "gemini-3.5-flash-lite", PROMPT_VERSION
    )
    sample_text = "RESERVE BANK OF INDIA\nCircular Ref: RBI/2026-27/299\nSubject: Test"
    cache.set(
        image_hash=key_with_time,
        final_text=sample_text,
        engine_used="gemini:gemini-3.5-flash-lite",
        valid=True,
        fields=extract_fields(sample_text).model_dump(),
        time_ms=20712.4,
    )

    settings = Settings(_env_file=None, CACHE_DB_PATH=db_path)
    res = run_ocr(img_path, settings=settings, allow_gemini_fallback=False, use_cache=True)
    assert res.from_cache is True
    assert res.time_ms == 20712.4

    # Entry without stored time_ms returns 0.0 (which the UI renders as "cached")
    cache.set(
        image_hash=key_with_time,
        final_text=sample_text,
        engine_used="gemini:gemini-3.5-flash-lite",
        valid=True,
        fields=extract_fields(sample_text).model_dump(),
        time_ms=None,
    )
    res_no_time = run_ocr(
        img_path, settings=settings, allow_gemini_fallback=False, use_cache=True
    )
    assert res_no_time.from_cache is True
    assert res_no_time.time_ms == 0.0


def test_hindi_reference_numbers_extraction_and_normalization():
    from factcheck.extract.ocr.fields import extract_fields, normalize_reference_number

    sample = """
    केन्द्रीय माध्यमिक शिक्षा बोर्ड
    परिपत्र संख्या: शैक्ष-55/2026
    दिनांक: 17.08.2026
    पत्रांक: 123/2026
    क्रमांक: 987/2026
    सं.: 456/2026
    विषय: नशा मुक्त विद्यालय अभियान
    """
    fields = extract_fields(sample)
    # Check that original Devanagari references are stored
    assert any("शैक्ष-55/2026" in r for r in fields.reference_numbers)
    # Check that normalized Acad form is stored
    assert "Acad-55/2026" in fields.reference_numbers
    assert "Acad-55/2026" in fields.normalized_reference_numbers
    assert "123/2026" in fields.reference_numbers
    assert "987/2026" in fields.reference_numbers
    assert "456/2026" in fields.reference_numbers


def test_devanagari_digits_transliteration():
    from factcheck.extract.ocr.fields import extract_fields

    sample = "परिपत्र संख्या: शैक्ष-५५/२०२६"
    fields = extract_fields(sample)
    assert "Acad-55/2026" in fields.reference_numbers
    assert "Acad-55/2026" in fields.normalized_reference_numbers


def test_plain_number_slash_number_reference_extraction():
    from factcheck.extract.ocr.fields import extract_fields

    sample_order = "Order No. 163/0224\nSubmitting Assets for Law Enforcement Inspection"
    fields = extract_fields(sample_order)
    assert "163/0224" in fields.reference_numbers

    sample_standalone = "SUPREME COURT OF INDIA\n\n163/0224\n\nSubmitting Assets"
    fields = extract_fields(sample_standalone)
    assert "163/0224" in fields.reference_numbers

    dates_and_amounts = (
        "Date of circular: 15/02/2026\n"
        "Effective: 10/2024\n"
        "Application fee: Rs. 500/1000\n"
        "Monthly rent Rs 2500/month\n"
        "Deposit: 2500/-\n"
    )
    fields = extract_fields(dates_and_amounts)
    assert not fields.reference_numbers
