"""Unit tests for Stages 3–5 (Claim Extraction, Hybrid Source Match, Verdict Decision) — mocked, ZERO API calls."""

from __future__ import annotations

import json
from pathlib import Path

from factcheck.claims.extractor import extract_claim
from factcheck.config import Settings
from factcheck.decide.verdict import decide_verdict
from factcheck.forensics.checks import filter_pib_overlay_lines
from factcheck.retrieval.matcher import HybridRetriever
from factcheck.schemas import (
    ExtractedFields,
    ForensicResult,
    MatchItem,
    RetrievalResult,
)


def _test_settings(tmp_path: Path) -> Settings:
    return Settings(
        CACHE_DB_PATH=tmp_path / "test_cache.sqlite",
        GEMINI_MODEL="gemini-2.5-flash-lite",
        API_DAILY_CALL_LIMIT=50,
    )


def test_claim_json_validation_and_retry_succeeds_on_second_attempt(tmp_path: Path) -> None:
    """1. Invalid JSON on first LLM response triggers 1 retry; valid JSON on second response succeeds."""
    cfg = _test_settings(tmp_path)
    calls: list[str] = []

    def _mock_llm(prompt: str, settings: Settings) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "NOT VALID JSON {broken"
        return json.dumps(
            {
                "canonical_claim_en": "Under PM Mudra Yojana a loan of Rs 5,00,000 has been approved on payment of Rs 2,100.",
                "claim_language": "hi",
                "claimed_issuer": "MUDRA",
                "action": "loan approved",
                "effective_date": "2026-10-01",
                "amounts": ["₹5,00,000", "₹2,100"],
                "audience": "individual applicant",
                "claim_type": "forged_document",
                "confidence": 0.95,
            }
        )

    res = extract_claim(
        "प्रधानमंत्री मुद्रा योजना के तहत ₹5,00,000 का लोन स्वीकृत हुआ है।",
        allow_cloud=True,
        use_cache=True,
        settings=cfg,
        llm_fn=_mock_llm,
    )
    assert len(calls) == 2
    assert res.canonical_claim_en == (
        "Under PM Mudra Yojana a loan of Rs 5,00,000 has been approved on payment of Rs 2,100."
    )
    assert res.claimed_issuer == "MUDRA"
    assert res.claim_type == "forged_document"
    assert res.from_cache is False


def test_claim_json_fails_gracefully_after_two_invalid_responses(tmp_path: Path) -> None:
    """1b. Two consecutive invalid JSON responses fail gracefully without raising."""
    cfg = _test_settings(tmp_path)
    calls = 0

    def _always_bad_llm(prompt: str, settings: Settings) -> str:
        nonlocal calls
        calls += 1
        return "{not_valid_json"

    res = extract_claim(
        "Sample document text",
        allow_cloud=True,
        use_cache=True,
        settings=cfg,
        llm_fn=_always_bad_llm,
    )
    assert calls == 2
    assert res.canonical_claim_en is None
    assert res.error is not None and "Invalid claim JSON" in res.error
    assert res.status_note == "Claim extraction failed after retry"


def test_claim_cache_hit_skips_llm_even_when_cloud_disabled(tmp_path: Path) -> None:
    """2. A cached claim entry returns immediately and never invokes the LLM."""
    cfg = _test_settings(tmp_path)
    llm_calls = 0

    def _mock_llm(prompt: str, settings: Settings) -> str:
        nonlocal llm_calls
        llm_calls += 1
        return json.dumps(
            {
                "canonical_claim_en": "CBSE has announced the CBSE Science Challenge 2026-27.",
                "claim_language": "en",
                "claimed_issuer": "CBSE",
                "action": "science challenge announced",
                "effective_date": None,
                "amounts": [],
                "audience": "affiliated schools",
                "claim_type": "official_notice",
                "confidence": 0.98,
            }
        )

    text = "CENTRAL BOARD OF SECONDARY EDUCATION Circular No. Acad-67/2026"
    first = extract_claim(text, allow_cloud=True, use_cache=True, settings=cfg, llm_fn=_mock_llm)
    assert llm_calls == 1
    assert first.from_cache is False

    def _fail_if_called(prompt: str, settings: Settings) -> str:
        raise AssertionError("LLM must not be called on a claim cache hit")

    second = extract_claim(
        text,
        allow_cloud=False,
        use_cache=True,
        settings=cfg,
        llm_fn=_fail_if_called,
    )
    assert second.from_cache is True
    assert second.canonical_claim_en == first.canonical_claim_en


def test_claim_needs_cloud_access_when_allow_cloud_false(tmp_path: Path) -> None:
    """2b. When allow_cloud=False and uncached, returns status_note 'Claim extraction needs cloud access'."""
    cfg = _test_settings(tmp_path)
    res = extract_claim("Uncached document text", allow_cloud=False, use_cache=True, settings=cfg)
    assert res.canonical_claim_en is None
    assert res.status_note == "Claim extraction needs cloud access"


def test_exact_reference_match_wins_in_official_collection() -> None:
    """3. Exact OCR reference match on an official document promotes it to rank 1 with label='strong'."""
    retriever = HybridRetriever(force_bm25_only=True)
    fields = ExtractedFields(reference_numbers=["Circular No.: Acad-67/2026"])
    res = retriever.search(
        canonical_claim_en="Unrelated query text",
        original_text="Unrelated text",
        fields=fields,
        top_k=3,
    )
    assert len(res.official) >= 1
    top_off = res.official[0]
    assert top_off.exact_reference_match is True
    assert top_off.label == "strong"
    assert top_off.score == 1.0
    assert top_off.reference_no == "Acad-67/2026"


def test_leave_one_out_removes_source_debunk_record() -> None:
    """4. Leave-one-out removes the entire deduplicated record (both notice_id and linked Telegram URL/post_id)."""
    retriever = HybridRetriever(force_bm25_only=True)
    query = "A purported Railway Board letter regarding payment of Productivity Linked Bonus (PLB) for FY 2025-26"

    # Normal search finds FN-TG-01999 at rank 1
    norm_res = retriever.search(canonical_claim_en=query, top_k=3)
    assert any(m.doc_id == "FN-TG-01999" for m in norm_res.debunks)

    # Leave-one-out by notice_id removes FN-TG-01999 (and its deduplicated TG post 1999)
    loo_res = retriever.search(
        canonical_claim_en=query,
        top_k=5,
        exclude_debunk_id="FN-TG-01999",
    )
    assert all(m.doc_id != "FN-TG-01999" for m in loo_res.debunks)
    assert all(m.doc_id != "TG-1999" for m in loo_res.debunks)


def test_all_six_verdict_branches() -> None:
    """5. Verify all 6 branches of the Stage 5 Verdict decision matrix."""
    strong_debunk = MatchItem(
        doc_id="FN-TG-01595",
        collection="debunks",
        title="RBI old coin exchange scam",
        snippet="RBI does not exchange old coins for Rs 34 lakh.",
        score=0.92,
        label="strong",
    )
    strong_official = MatchItem(
        doc_id="OFF-51452FA980",
        collection="official",
        title="CBSE Science Challenge",
        snippet="CBSE Science Challenge 2026-27",
        reference_no="Acad-67/2026",
        score=1.0,
        label="strong",
        exact_reference_match=True,
    )
    weak_debunk = MatchItem(
        doc_id="FN-TG-00130",
        collection="debunks",
        title="Weak match",
        snippet="Unrelated snippet",
        score=0.50,
        label="none",
    )

    f_low = ForensicResult(risk_level="low", risk_score=0)
    f_med = ForensicResult(risk_level="medium", risk_score=35)
    f_high = ForensicResult(risk_level="high", risk_score=85)

    # Branch 1: debunk strong match -> "❌ FAKE DOCUMENT" (red), even if forensics is low
    v1 = decide_verdict(
        f_low,
        RetrievalResult(debunks=[strong_debunk.model_copy()], official=[strong_official.model_copy()]),
    )
    assert v1.verdict_key == "debunked"
    assert v1.color == "red"
    assert v1.title == "❌ FAKE DOCUMENT"

    # Branch 2: official strong match + forensics low -> "✅ GENUINE DOCUMENT" (green)
    v2 = decide_verdict(
        f_low,
        RetrievalResult(debunks=[weak_debunk.model_copy()], official=[strong_official.model_copy()]),
    )
    assert v2.verdict_key == "matches_official"
    assert v2.color == "green"
    assert v2.title == "✅ GENUINE DOCUMENT"

    # Branch 3: official strong match + forensics medium/high -> altered copy warning (amber)
    v3 = decide_verdict(
        f_high,
        RetrievalResult(debunks=[weak_debunk.model_copy()], official=[strong_official.model_copy()]),
    )
    assert v3.verdict_key == "altered_official_copy"
    assert v3.color == "amber"
    assert v3.title == "⚠️ CAUTION DOCUMENT"

    # Branch 4: no strong match + forensics high -> "❌ LIKELY FAKE DOCUMENT" (red)
    v4 = decide_verdict(
        f_high,
        RetrievalResult(debunks=[weak_debunk.model_copy()], official=[]),
    )
    assert v4.verdict_key == "likely_forged"
    assert v4.color == "red"
    assert v4.title == "❌ LIKELY FAKE DOCUMENT"

    # Branch 5: no strong match + forensics medium -> "⚠️ SUSPICIOUS DOCUMENT" (amber)
    v5 = decide_verdict(
        f_med,
        RetrievalResult(debunks=[weak_debunk.model_copy()], official=[]),
    )
    assert v5.verdict_key == "suspicious_unverified"
    assert v5.color == "amber"
    assert v5.title == "⚠️ SUSPICIOUS DOCUMENT"

    # Branch 6: no strong match + forensics low -> "❔ UNVERIFIED DOCUMENT" (grey)
    v6 = decide_verdict(
        f_low,
        RetrievalResult(debunks=[weak_debunk.model_copy()], official=[]),
    )
    assert v6.verdict_key == "unverified"
    assert v6.color == "grey"
    assert v6.title == "❔ UNVERIFIED DOCUMENT"
    assert "authentic" not in v6.title.lower()


def test_verdict_downgrades_strong_debunk_when_overlapping_mainly_removed_overlay() -> None:
    """6. If a strong debunk match overlaps mainly with removed overlay lines rather than body text, downgrade to 'possible'."""
    leaked_debunk = MatchItem(
        doc_id="TG-9999",
        collection="debunks",
        title="Clarification regarding fabricated viral screenshot on WhatsApp",
        snippet="Press Information Bureau clarified that the viral screenshot shared on WhatsApp is fabricated.",
        score=0.88,
        label="strong",
    )
    ret = RetrievalResult(debunks=[leaked_debunk], official=[])
    forensics = ForensicResult(risk_level="low", risk_score=0)

    # Document body is about routine school holidays, while the removed overlay has the exact words from leaked_debunk
    cleaned_body = "Notice: School summer vacation starts from 15 May 2026 for all classes."
    removed_overlay = (
        "Press Information Bureau has clarified that the viral screenshot shared on WhatsApp is fake/fabricated."
    )

    verdict = decide_verdict(
        forensics,
        ret,
        cleaned_body_text=cleaned_body,
        removed_overlay_text=removed_overlay,
    )
    assert ret.debunks[0].label == "possible"
    assert ret.debunks[0].downgraded_from_overlay_overlap is True
    assert ret.debunks[0].downgrade_note is not None
    assert verdict.verdict_key == "unverified"
    assert verdict.overlay_downgrade_note is not None


def test_extended_pib_caption_leakage_lines_filtered() -> None:
    """7. Caption lines with 'purported', 'has clarified', 'is being circulated', 'fake/fabricated', 'भ्रामक', etc. are filtered."""
    raw_text = (
        "FAKE DOCUMENT ALERT\n"
        "A purported Railway Board letter is being circulated on social media.\n"
        "Railway Board has clarified that the letter is fake/fabricated and has not been issued.\n"
        "यह दावा भ्रामक है और सोशल मीडिया पर दावा किया जा रहा है।\n"
        "GOVERNMENT OF INDIA\n"
        "MINISTRY OF RAILWAYS\n"
        "RBE No. 101/2026"
    )
    cleaned, spans, _ = filter_pib_overlay_lines(raw_text)
    assert len(spans) == 4
    assert "FAKE DOCUMENT ALERT" not in cleaned
    assert "purported" not in cleaned
    assert "has clarified" not in cleaned
    assert "भ्रामक" not in cleaned
    assert "MINISTRY OF RAILWAYS" in cleaned
    assert "RBE No. 101/2026" in cleaned


def test_post_merge_demo_regression_score_and_debunk() -> None:
    """Regression test: FN-TG-00988 has forensic score > 60 and FN-TG-00130 is debunked with toggle off."""
    import sqlite3
    from factcheck.config import get_settings
    from factcheck.extract.ocr.fields import extract_fields
    from factcheck.forensics import run_forensics
    from factcheck.pipeline import run_document_pipeline
    from factcheck.schemas import OCRResult

    cfg = get_settings()
    repo_root = Path(__file__).resolve().parents[1]
    db_path = cfg.CACHE_DB_PATH if cfg.CACHE_DB_PATH.is_absolute() else repo_root / cfg.CACHE_DB_PATH

    # Check cached OCR for FN-TG-00988 scores > 60
    conn = sqlite3.connect(db_path)
    row988 = conn.execute(
        "SELECT final_text FROM ocr_cache WHERE image_hash='58af656768e4deadc901de09780d5c1a1d39dec764b1b7552bff0ea4cd84e7de'"
    ).fetchone()
    assert row988 is not None, "FN-TG-00988 must be in ocr_cache.sqlite"
    t988 = row988[0]
    ocr_res_988 = OCRResult(
        image_hash="FN-TG-00988",
        final_text=t988,
        engine_used="cached_ocr",
        valid=True,
        fields=extract_fields(t988),
        from_cache=True,
    )
    forensics_988 = run_forensics(ocr_res_988)
    assert forensics_988.risk_score > 60, f"Expected risk_score > 60, got {forensics_988.risk_score}"

    # Check FN-TG-00130 image pipeline run with toggle OFF is debunked
    img_130 = repo_root / "data/demo/images/FN-TG-00130.jpg"
    assert img_130.exists(), "FN-TG-00130.jpg demo image must exist"
    run_130 = run_document_pipeline(img_130, allow_fallback=False, exclude_debunk_id=None)
    assert run_130.ocr.from_cache is True
    assert run_130.verdict.verdict_key == "debunked"



def test_claim_post_validation_relative_date_fn_pdf_0002(tmp_path: Path) -> None:
    """Post-validation: relative dates ('within 24 hours') set effective_date to None; claim_language uses detector."""
    from factcheck.claims.extractor import extract_claim

    cfg = _test_settings(tmp_path)
    raw_json = json.dumps({
        "canonical_claim_en": "I4C requests response regarding alleged cyber crimes within 24 hours",
        "claim_language": "en",  # Model guessed en, but source text is Hindi
        "claimed_issuer": "I4C",
        "action": "respond to allegations",
        "effective_date": "2026-11-01",  # Hallucinated today's date
        "effective_date_raw": "24 घंटे के भीतर",
        "amounts": [],
        "claim_type": "forged_document",
        "confidence": 0.95,
    })

    hindi_text = "भारतीय साइबर अपराध समन्वय केंद्र (I4C) का नोटिस। कृपया 24 घंटे के भीतर जवाब दें।"
    res = extract_claim(
        hindi_text,
        allow_cloud=True,
        use_cache=False,
        settings=cfg,
        llm_fn=lambda prompt, settings: raw_json,
    )
    assert res.effective_date is None, f"Expected None, got {res.effective_date}"
    assert res.effective_date_raw == "24 घंटे के भीतर"
    assert res.claim_language == "hi", f"Expected hi, got {res.claim_language}"


def test_claim_post_validation_date_derived_off_51452fa980(tmp_path: Path) -> None:
    """Post-validation: effective_date derives from effective_date_raw (13.10.2026 -> 2026-10-13), not hallucinated run date."""
    from factcheck.claims.extractor import extract_claim

    cfg = _test_settings(tmp_path)
    raw_json = json.dumps({
        "canonical_claim_en": "CBSE organises Science Challenge",
        "claim_language": "hi",  # Model guessed hi, but source text is English
        "claimed_issuer": "CBSE",
        "action": "organises",
        "effective_date": "2026-10-31",  # Hallucinated run date
        "effective_date_raw": "13.10.2026",
        "amounts": [],
        "claim_type": "official_notice",
        "confidence": 0.95,
    })

    cbse_text = "CENTRAL BOARD OF SECONDARY EDUCATION Circular No. Acad-67/2026 Dated: 13.10.2026. CBSE Science Challenge from 13 October 2026."
    res = extract_claim(
        cbse_text,
        allow_cloud=True,
        use_cache=False,
        settings=cfg,
        llm_fn=lambda prompt, settings: raw_json,
    )
    assert res.effective_date == "2026-10-13", f"Expected 2026-10-13, got {res.effective_date}"
    assert res.effective_date_raw == "13.10.2026"
    assert res.claim_language == "en", f"Expected en, got {res.claim_language}"


def test_claim_post_validation_absent_date_never_fills_today(tmp_path: Path) -> None:
    """Post-validation: absent effective_date_raw and no date in text forces effective_date to None."""
    from factcheck.claims.extractor import extract_claim

    cfg = _test_settings(tmp_path)
    raw_json = json.dumps({
        "canonical_claim_en": "General notice without dates",
        "claim_language": "en",
        "claimed_issuer": "CBSE",
        "action": "notice",
        "effective_date": "2026-11-02",  # Hallucinated today's date
        "effective_date_raw": None,
        "amounts": [],
        "claim_type": "official_notice",
        "confidence": 0.95,
    })

    res = extract_claim(
        "CBSE notice with no calendar date mentioned anywhere.",
        allow_cloud=True,
        use_cache=False,
        settings=cfg,
        llm_fn=lambda prompt, settings: raw_json,
    )
    assert res.effective_date is None
    assert res.effective_date_raw is None
