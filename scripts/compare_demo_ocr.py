import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

from factcheck.claims import extract_claim
from factcheck.config import get_settings
from factcheck.decide import decide_verdict
from factcheck.extract.ocr.cache import OCRCache, compute_cache_key
from factcheck.extract.ocr.engines import run_ollama_vlm
from factcheck.extract.ocr.fields import extract_fields, strip_synthetic_watermark
from factcheck.extract.ocr.prompts import PROMPT_VERSION
from factcheck.extract.ocr.runner import strip_markdown_formatting
from factcheck.extract.ocr.validation import is_valid_ocr_text
from factcheck.forensics import run_forensics
from factcheck.forensics.checks import filter_pib_overlay_lines
from factcheck.lang import detect_language
from factcheck.retrieval import match_sources
from factcheck.schemas import ExtractedFields, OCRResult

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_PATH = REPO_ROOT / "data" / "demo" / "demo_set.json"
CACHE_PATH = REPO_ROOT / "data" / "cache" / "ocr_cache.sqlite"

def get_ollama_ps():
    try:
        out = subprocess.check_output(["ollama", "ps"], stderr=subprocess.STDOUT, text=True)
        return out.strip()
    except Exception:
        ollama_exe = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
        if Path(ollama_exe).exists():
            try:
                out = subprocess.check_output([ollama_exe, "ps"], stderr=subprocess.STDOUT, text=True)
                return out.strip()
            except Exception as e:
                return f"Error: {e}"
        return "ollama.exe not found"

def extract_digits(text: str) -> list[str]:
    return re.findall(r"\d+", text or "")

def evaluate_pipeline_for_text(raw_text: str, is_synthetic: bool = False):
    display_text = strip_synthetic_watermark(raw_text) if is_synthetic else raw_text
    display_fields = extract_fields(display_text, strip_watermark=False) if is_synthetic else extract_fields(raw_text)
    det = detect_language(display_text)
    ocr = OCRResult(
        image_hash="",
        final_text=display_text,
        engine_used="test",
        valid=is_valid_ocr_text(display_text),
        fields=display_fields,
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
    forensics = run_forensics(ocr)

    cleaned_text, overlay_spans, _ = filter_pib_overlay_lines(display_text)
    removed_overlay_text = "\n".join(display_text[s.char_start : s.char_end] for s in overlay_spans)
    cleaned_fields = extract_fields(cleaned_text, strip_watermark=False) if overlay_spans else display_fields

    claim = extract_claim(cleaned_text, allow_cloud=False, use_cache=True)
    matches = match_sources(
        canonical_claim_en=claim.canonical_claim_en,
        original_text=cleaned_text,
        fields=cleaned_fields,
        claimed_issuer_id=claim.claimed_issuer_id,
    )
    verdict = decide_verdict(
        forensics, matches, cleaned_body_text=cleaned_text, removed_overlay_text=removed_overlay_text
    )
    return forensics, verdict

def run_comparison():
    settings = get_settings()
    cache = OCRCache(CACHE_PATH)
    demo_items = json.loads(DEMO_PATH.read_text(encoding="utf-8"))["items"]

    print("=== Ollama GPU Status before run ===")
    print(get_ollama_ps())
    print("====================================\n")

    results = []

    for idx, item in enumerate(demo_items, start=1):
        item_id = item["id"]
        rel_img = item["image"]
        img_path = REPO_ROOT / rel_img
        is_synth = item.get("group") == "synthetic" or item_id.startswith("SYN-")

        if not img_path.exists():
            print(f"[{idx:02d}/20] {item_id}: file not found {img_path}")
            continue

        img_bytes = img_path.read_bytes()
        vlm_key = compute_cache_key(img_bytes, "ollama", settings.VLM_MODEL, PROMPT_VERSION)
        gem_key = compute_cache_key(img_bytes, "gemini", settings.GEMINI_MODEL, PROMPT_VERSION)

        # 1. Get cached Gemini text
        gem_cached = cache.get(gem_key)
        if not gem_cached:
            for pv in ("v3", "v2", "v1"):
                ck = compute_cache_key(img_bytes, "gemini", settings.GEMINI_MODEL, pv)
                gem_cached = cache.get(ck)
                if gem_cached:
                    break

        gem_text = gem_cached["final_text"] if gem_cached else ""
        gem_fields = extract_fields(gem_text)

        # 2. Run Local Qwen3-VL OCR
        t0 = time.perf_counter()
        vlm_raw, vlm_engine, vlm_err = run_ollama_vlm(img_path, settings, timeout=120.0)
        t_sec = time.perf_counter() - t0
        time_ms = round(t_sec * 1000.0, 2)

        vlm_clean, _ = strip_markdown_formatting(vlm_raw)
        vlm_valid = is_valid_ocr_text(vlm_clean)
        vlm_fields = extract_fields(vlm_clean)

        # Save to cache under vlm_key so local OCR stays cached
        if vlm_valid:
            cache.set(
                image_hash=vlm_key,
                final_text=vlm_clean,
                engine_used=vlm_engine,
                valid=True,
                fields=vlm_fields.model_dump(),
                time_ms=time_ms,
            )

        # 3. Compare reference numbers
        gem_refs = sorted(list(set(gem_fields.reference_numbers)))
        vlm_refs = sorted(list(set(vlm_fields.reference_numbers)))
        ref_exact_match = (gem_refs == vlm_refs)

        # 4. Compare lengths and digits
        gem_len = len(gem_text)
        vlm_len = len(vlm_clean)
        len_diff = vlm_len - gem_len

        gem_digits = set(extract_digits(gem_text))
        vlm_digits = set(extract_digits(vlm_clean))
        digit_overlap = len(gem_digits & vlm_digits)
        digit_total = len(gem_digits | vlm_digits)
        digit_sim = (digit_overlap / digit_total) if digit_total > 0 else 1.0

        # 5. Run forensics and verdict comparison
        forensic_gem, verdict_gem = evaluate_pipeline_for_text(gem_text, is_synthetic=is_synth)
        forensic_vlm, verdict_vlm = evaluate_pipeline_for_text(vlm_clean, is_synthetic=is_synth)

        score_gem = forensic_gem.risk_score
        score_vlm = forensic_vlm.risk_score
        verdict_match = (verdict_gem.verdict_key == verdict_vlm.verdict_key)

        res_entry = {
            "idx": idx,
            "id": item_id,
            "time_sec": round(t_sec, 2),
            "vlm_valid": vlm_valid,
            "gem_len": gem_len,
            "vlm_len": vlm_len,
            "len_diff": len_diff,
            "ref_match": ref_exact_match,
            "gem_refs": gem_refs,
            "vlm_refs": vlm_refs,
            "digit_sim": round(digit_sim, 2),
            "score_gem": score_gem,
            "score_vlm": score_vlm,
            "verdict_gem": verdict_gem.verdict_key,
            "verdict_vlm": verdict_vlm.verdict_key,
            "verdict_match": verdict_match,
        }
        results.append(res_entry)

        v_flag = "MATCH" if verdict_match else f"DIFF ({verdict_gem.verdict_key} -> {verdict_vlm.verdict_key})"
        ref_flag = "MATCH" if ref_exact_match else f"DIFF (gem={gem_refs} vs vlm={vlm_refs})"
        print(
            f"[{idx:02d}/20] {item_id:28s} | {t_sec:5.2f}s | valid={vlm_valid} | "
            f"len={vlm_len:4d} (diff={len_diff:+4d}) | refs={ref_flag} | "
            f"score={score_gem:.2f}->{score_vlm:.2f} | verdict={v_flag}"
        )

    print("\n=== Ollama GPU Status after run ===")
    print(get_ollama_ps())
    print("===================================\n")

    with open("demo_comparison_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Saved results to demo_comparison_results.json")

if __name__ == "__main__":
    run_comparison()
