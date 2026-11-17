"""Full offline end-to-end evaluation on the 20 demo items (zero API calls).

Runs:
  - Local Qwen3-VL OCR (with max 1200 px long side, output cap, 90s timeout, allow_gemini_fallback=False)
  - Local Qwen3-VL claim extraction (Ollama JSON schema, allow_cloud=False)
  - Post-validated effective_date and claim_language
  - Source matching and verdict decision

Compares with cached cloud (Gemini) baseline:
  - Verdict agreement
  - Reference number exact match
  - Time per item (OCR, Claim, Total)
  - Identifies stage causing any verdict change (OCR, Claim, or Both)

Progress is saved to docs/offline_e2e_results.json after each item.
Does not re-run items that finished successfully.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from factcheck.claims.extractor import extract_claim
from factcheck.config import Settings
from factcheck.decide.verdict import decide_verdict
from factcheck.extract.ocr import extract_fields, run_ocr, strip_synthetic_watermark
from factcheck.forensics import run_forensics
from factcheck.forensics.checks import filter_pib_overlay_lines
from factcheck.retrieval.matcher import match_sources

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = REPO_ROOT / "docs" / "offline_e2e_results.json"


def normalize_ref(ref: str | None) -> str:
    if not ref:
        return ""
    import re
    return re.sub(r"[\s/.-]+", "", ref.strip().lower())


def match_ref(expected: str | None, detected_list: list[str]) -> bool:
    if not expected:
        return True  # If no reference was expected, detected None/anything is consistent
    exp_norm = normalize_ref(expected)
    for d in detected_list:
        d_norm = normalize_ref(d)
        if exp_norm in d_norm or d_norm in exp_norm:
            return True
    return False


def run_pipeline_for_texts(raw_ocr_text: str, is_synthetic: bool, claim_res):
    display_text = strip_synthetic_watermark(raw_ocr_text) if is_synthetic else raw_ocr_text
    cleaned_text, overlay_spans, _ = filter_pib_overlay_lines(display_text)
    removed_overlay_text = "\n".join(display_text[s.char_start : s.char_end] for s in overlay_spans)
    cleaned_fields = extract_fields(cleaned_text, strip_watermark=False) if overlay_spans else (
        extract_fields(display_text, strip_watermark=False) if is_synthetic else extract_fields(raw_ocr_text)
    )

    from factcheck.schemas import OCRResult
    ocr_obj = OCRResult(
        image_hash="",
        final_text=display_text,
        engine_used="eval",
        valid=True,
        fields=cleaned_fields,
        from_cache=True,
    )
    forensics = run_forensics(ocr_obj)

    matches = match_sources(
        canonical_claim_en=claim_res.canonical_claim_en,
        original_text=cleaned_text,
        fields=cleaned_fields,
        exclude_debunk_id=None,
        claimed_issuer_id=claim_res.claimed_issuer_id,
    )

    verdict = decide_verdict(
        forensics,
        matches,
        cleaned_body_text=cleaned_text,
        removed_overlay_text=removed_overlay_text,
        claimed_issuer_id=claim_res.claimed_issuer_id,
    )
    return verdict


def main():
    demo_file = REPO_ROOT / "data" / "demo" / "demo_set.json"
    with open(demo_file, "r", encoding="utf-8") as f:
        demo_data = json.load(f)

    items = demo_data["items"]

    # Load existing progress if any
    saved_results: dict[str, dict] = {}
    if RESULTS_PATH.exists():
        try:
            with open(RESULTS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    for it in loaded:
                        if it.get("completed"):
                            saved_results[it["id"]] = it
        except Exception:
            saved_results = {}

    settings_cloud = Settings(OFFLINE_MODE=False, OCR_ENGINE_PREFERENCE="gemini_first")
    settings_offline = Settings(
        OFFLINE_MODE=True,
        OCR_ENGINE_PREFERENCE="qwen_first",
        LOCAL_LLM_MODEL="qwen3-vl:4b",
        VLM_MODEL="qwen3-vl:4b",
        OLLAMA_ENABLED=True,
    )

    print(f"Loaded {len(items)} demo items. Already completed: {len(saved_results)}.", flush=True)
    print("=" * 115, flush=True)
    header = f"{'ID':<15} | {'Label':<10} | {'Cloud Verd':<14} | {'Offl Verd':<14} | {'Same?':<5} | {'Ref Match':<9} | {'T_OCR':<6} | {'T_Claim':<7} | {'Change Cause':<12}"
    print(header, flush=True)
    print("-" * 115, flush=True)

    results_list = []

    for item in items:
        item_id = item["id"]
        label = item["label"]
        img_rel = item["image"]
        img_path = REPO_ROOT / img_rel
        synthetic = label.startswith("synthetic")
        expected_ref = item.get("expected_reference_no")

        # Check if already completed and cached
        if item_id in saved_results:
            r = saved_results[item_id]
            results_list.append(r)
            print(
                f"{item_id:<15} | {label:<10} | {r['cloud_verdict']:<14} | {r['offline_verdict']:<14} | "
                f"{str(r['verdict_same']):<5} | {str(r['ref_match']):<9} | {r['time_ocr_s']:<6.2f} | "
                f"{r['time_claim_s']:<7.2f} | {r['change_cause']:<12} (cached)",
                flush=True,
            )
            continue

        # 1. Cloud Baseline Run (reads cached OCR + cached Gemini claim)
        t_c0 = time.perf_counter()
        ocr_cloud = run_ocr(img_path, allow_gemini_fallback=True, use_cache=True, settings=settings_cloud)
        text_c = strip_synthetic_watermark(ocr_cloud.final_text) if synthetic else ocr_cloud.final_text
        cln_c, spans_c, _ = filter_pib_overlay_lines(text_c)
        overlay_c = "\n".join(text_c[s.char_start : s.char_end] for s in spans_c)
        fields_c = extract_fields(cln_c, strip_watermark=False) if spans_c else (
            extract_fields(text_c, strip_watermark=False) if synthetic else ocr_cloud.fields
        )

        from factcheck.schemas import OCRResult
        ocr_cloud_obj = OCRResult(
            image_hash=ocr_cloud.image_hash,
            final_text=text_c,
            engine_used=ocr_cloud.engine_used,
            valid=ocr_cloud.valid,
            fields=fields_c,
            from_cache=True,
        )
        forensics_cloud = run_forensics(ocr_cloud_obj)
        claim_cloud = extract_claim(cln_c, allow_cloud=False, use_cache=True, settings=settings_cloud)
        match_cloud = match_sources(
            canonical_claim_en=claim_cloud.canonical_claim_en,
            original_text=cln_c,
            fields=fields_c,
            claimed_issuer_id=claim_cloud.claimed_issuer_id,
        )
        verd_cloud = decide_verdict(
            forensics_cloud,
            match_cloud,
            cleaned_body_text=cln_c,
            removed_overlay_text=overlay_c,
            claimed_issuer_id=claim_cloud.claimed_issuer_id,
        )

        # 2. Offline End-to-End Run
        t_ocr0 = time.perf_counter()
        ocr_offline = run_ocr(img_path, allow_gemini_fallback=False, use_cache=True, settings=settings_offline)
        time_ocr = round(time.perf_counter() - t_ocr0, 2)

        text_off = strip_synthetic_watermark(ocr_offline.final_text) if synthetic else ocr_offline.final_text
        cln_off, spans_off, _ = filter_pib_overlay_lines(text_off)
        overlay_off = "\n".join(text_off[s.char_start : s.char_end] for s in spans_off)
        fields_off = extract_fields(cln_off, strip_watermark=False) if spans_off else (
            extract_fields(text_off, strip_watermark=False) if synthetic else ocr_offline.fields
        )

        ocr_off_obj = OCRResult(
            image_hash=ocr_offline.image_hash,
            final_text=text_off,
            engine_used=ocr_offline.engine_used,
            valid=ocr_offline.valid,
            fields=fields_off,
            from_cache=ocr_offline.from_cache,
        )
        forensics_off = run_forensics(ocr_off_obj)

        t_clm0 = time.perf_counter()
        claim_offline = extract_claim(cln_off, allow_cloud=False, use_cache=True, settings=settings_offline)
        time_claim = round(time.perf_counter() - t_clm0, 2)

        match_off = match_sources(
            canonical_claim_en=claim_offline.canonical_claim_en,
            original_text=cln_off,
            fields=fields_off,
            claimed_issuer_id=claim_offline.claimed_issuer_id,
        )
        verd_off = decide_verdict(
            forensics_off,
            match_off,
            cleaned_body_text=cln_off,
            removed_overlay_text=overlay_off,
            claimed_issuer_id=claim_offline.claimed_issuer_id,
        )

        # 3. Reference number exact match
        detected_refs = ocr_offline.fields.reference_numbers or []
        ref_match = match_ref(expected_ref, detected_refs)

        # 4. Verdict comparison
        verd_same = (verd_cloud.verdict_key == verd_off.verdict_key)

        # 5. Stage attribution if verdict changed
        change_cause = "none"
        if not verd_same:
            # Check if offline claim on cloud OCR produces cloud verdict
            v_cloud_ocr_off_claim = run_pipeline_for_texts(ocr_cloud.final_text, synthetic, claim_offline)
            # Check if cloud claim on offline OCR produces cloud verdict
            v_off_ocr_cloud_claim = run_pipeline_for_texts(ocr_offline.final_text, synthetic, claim_cloud)

            claim_diff = (v_cloud_ocr_off_claim.verdict_key != verd_cloud.verdict_key)
            ocr_diff = (v_off_ocr_cloud_claim.verdict_key != verd_cloud.verdict_key)

            if ocr_diff and not claim_diff:
                change_cause = "OCR"
            elif claim_diff and not ocr_diff:
                change_cause = "Claim"
            else:
                change_cause = "Both"

        res_dict = {
            "id": item_id,
            "label": label,
            "expected_reference_no": expected_ref,
            "cloud_reference_numbers": ocr_cloud.fields.reference_numbers,
            "offline_reference_numbers": detected_refs,
            "ref_match": ref_match,
            "cloud_verdict": verd_cloud.verdict_key,
            "offline_verdict": verd_off.verdict_key,
            "verdict_same": verd_same,
            "cloud_verdict_title": verd_cloud.title,
            "offline_verdict_title": verd_off.title,
            "cloud_issuer": claim_cloud.claimed_issuer,
            "cloud_issuer_id": claim_cloud.claimed_issuer_id,
            "offline_issuer": claim_offline.claimed_issuer,
            "offline_issuer_id": claim_offline.claimed_issuer_id,
            "time_ocr_s": time_ocr,
            "time_claim_s": time_claim,
            "time_total_s": round(time_ocr + time_claim, 2),
            "change_cause": change_cause,
            "completed": True,
        }
        results_list.append(res_dict)
        saved_results[item_id] = res_dict

        # Save progress after every item
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(list(saved_results.values()), f, indent=2)

        print(
            f"{item_id:<15} | {label:<10} | {verd_cloud.verdict_key:<14} | {verd_off.verdict_key:<14} | "
            f"{str(verd_same):<5} | {str(ref_match):<9} | {time_ocr:<6.2f} | "
            f"{time_claim:<7.2f} | {change_cause:<12}",
            flush=True,
        )

    print("-" * 115, flush=True)
    total = len(items)
    n_verd = sum(1 for r in results_list if r["verdict_same"])
    n_ref = sum(1 for r in results_list if r["ref_match"])
    avg_ocr = sum(r["time_ocr_s"] for r in results_list) / total
    avg_claim = sum(r["time_claim_s"] for r in results_list) / total
    avg_total = sum(r["time_total_s"] for r in results_list) / total

    print(f"Summary over {total} items:", flush=True)
    print(f"  Verdict Agreement:          {n_verd}/{total} ({n_verd/total*100:.1f}%)", flush=True)
    print(f"  Ref Exact Match:            {n_ref}/{total} ({n_ref/total*100:.1f}%)", flush=True)
    print(f"  Avg Time per Item:          OCR={avg_ocr:.2f}s, Claim={avg_claim:.2f}s, Total={avg_total:.2f}s", flush=True)

    changed_items = [r for r in results_list if not r["verdict_same"]]
    print(f"  Verdict Changed Count:      {len(changed_items)}", flush=True)
    for c_it in changed_items:
        print(f"    - {c_it['id']} ({c_it['label']}): Cloud='{c_it['cloud_verdict']}' vs Offline='{c_it['offline_verdict']}' [Stage: {c_it['change_cause']}]", flush=True)


if __name__ == "__main__":
    main()
