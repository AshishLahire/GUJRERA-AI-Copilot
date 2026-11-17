"""Comprehensive audit and comparison between cached Gemini and local Ollama (qwen3-vl:4b) claims.

Runs pipeline separately with Gemini claim vs Local claim for all demo items.
ZERO Gemini API calls are made: all data is read from local cache.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from factcheck.claims.extractor import extract_claim
from factcheck.config import Settings
from factcheck.decide import decide_verdict
from factcheck.extract.ocr import extract_fields, run_ocr, strip_synthetic_watermark
from factcheck.forensics import run_forensics
from factcheck.forensics.checks import filter_pib_overlay_lines
from factcheck.retrieval import match_sources

REPO_ROOT = Path(__file__).resolve().parents[1]


def get_top_source(match_res):
    if match_res.debunks:
        d = match_res.debunks[0]
        return f"Debunk:{d.doc_id} ({d.label}, score={d.score:.2f})"
    if match_res.official:
        o = match_res.official[0]
        return f"Official:{o.doc_id} ({o.label}, score={o.score:.2f})"
    if match_res.ground_truth and match_res.ground_truth.best:
        b = match_res.ground_truth.best
        return f"GT:{b.record_id} ({match_res.ground_truth.status}, sim={match_res.ground_truth.similarity:.2f})"
    return "None"


def main():
    demo_file = REPO_ROOT / "data" / "demo" / "demo_set.json"
    with open(demo_file, "r", encoding="utf-8") as f:
        demo_data = json.load(f)

    items = demo_data["items"]
    settings_gemini = Settings(OFFLINE_MODE=False)
    settings_offline = Settings(OFFLINE_MODE=True, LOCAL_LLM_MODEL="qwen3-vl:4b")

    results = []
    audit_5_items = {}

    target_5_ids = {"SYN-0001", "SYN-0002", "FN-PDF-0002", "FN-TG-00130", "OFF-51452FA980__wa_compress"}

    iss_match_count = 0
    src_match_count = 0
    verd_match_count = 0

    print("=" * 120, flush=True)
    print("DEMO ITEMS AUDIT: GEMINI vs LOCAL OLLAMA CLAIMS", flush=True)
    print("=" * 120, flush=True)

    header = f"{'ID':<15} | {'Gemini Issuer (ID)':<24} | {'Local Issuer (ID)':<24} | {'Iss?':<5} | {'Gemini Verdict':<15} | {'Local Verdict':<15} | {'Verd?':<5} | {'Src Match Same?':<15}"
    print(header, flush=True)
    print("-" * 120, flush=True)

    for item in items:
        item_id = item["id"]
        label = item["label"]
        img_rel = item["image"]
        img_path = REPO_ROOT / img_rel
        synthetic = label.startswith("synthetic")

        # 1. Cached OCR
        ocr_res = run_ocr(img_path, allow_gemini_fallback=True, use_cache=True, settings=settings_gemini)
        display_text = strip_synthetic_watermark(ocr_res.final_text) if synthetic else ocr_res.final_text
        cleaned_text, overlay_spans, _ = filter_pib_overlay_lines(display_text)
        removed_overlay_text = "\n".join(display_text[s.char_start : s.char_end] for s in overlay_spans)
        cleaned_fields = extract_fields(cleaned_text, strip_watermark=False) if overlay_spans else (
            extract_fields(display_text, strip_watermark=False) if synthetic else ocr_res.fields
        )

        ocr_for_forensics = ocr_res.model_copy(update={"final_text": display_text, "fields": cleaned_fields})
        forensics = run_forensics(ocr_for_forensics)

        # 2. Extract / load claims
        cg = extract_claim(cleaned_text, allow_cloud=False, use_cache=True, settings=settings_gemini)
        cl = extract_claim(cleaned_text, allow_cloud=False, use_cache=True, settings=settings_offline)

        # 3. Source matching separately
        mg = match_sources(
            canonical_claim_en=cg.canonical_claim_en,
            original_text=cleaned_text,
            fields=cleaned_fields,
            exclude_debunk_id=None,
            claimed_issuer_id=cg.claimed_issuer_id,
        )
        ml = match_sources(
            canonical_claim_en=cl.canonical_claim_en,
            original_text=cleaned_text,
            fields=cleaned_fields,
            exclude_debunk_id=None,
            claimed_issuer_id=cl.claimed_issuer_id,
        )

        # 4. Final verdicts separately
        vg = decide_verdict(
            forensics, mg,
            cleaned_body_text=cleaned_text,
            removed_overlay_text=removed_overlay_text,
            claimed_issuer_id=cg.claimed_issuer_id,
        )
        vl = decide_verdict(
            forensics, ml,
            cleaned_body_text=cleaned_text,
            removed_overlay_text=removed_overlay_text,
            claimed_issuer_id=cl.claimed_issuer_id,
        )

        # Issuer strings
        iss_g_str = f"{cg.claimed_issuer or 'None'} ({cg.claimed_issuer_id or 'None'})"
        iss_l_str = f"{cl.claimed_issuer or 'None'} ({cl.claimed_issuer_id or 'None'})"

        # Issuer match logic: compare normalized claimed_issuer_id or claimed_issuer
        gid = (cg.claimed_issuer_id or "").strip().upper()
        lid = (cl.claimed_issuer_id or "").strip().upper()
        gnm = (cg.claimed_issuer or "").strip().lower()
        lnm = (cl.claimed_issuer or "").strip().lower()
        iss_match = (bool(gid and lid) and gid == lid) or (bool(gnm and lnm) and (gnm == lnm or gnm in lnm or lnm in gnm))
        if iss_match:
            iss_match_count += 1

        top_src_g = get_top_source(mg)
        top_src_l = get_top_source(ml)
        src_same = (top_src_g == top_src_l)
        if src_same:
            src_match_count += 1

        verd_same = (vg.verdict_key == vl.verdict_key)
        if verd_same:
            verd_match_count += 1

        # Safe line print for terminal (strip non-ascii)
        safe_iss_g = iss_g_str[:22]
        safe_iss_l = iss_l_str[:22]
        print(f"{item_id:<15} | {safe_iss_g:<24} | {safe_iss_l:<24} | {str(iss_match):<5} | {vg.verdict_key:<15} | {vl.verdict_key:<15} | {str(verd_same):<5} | {str(src_same):<15}", flush=True)

        res_item = {
            "id": item_id,
            "label": label,
            "gemini_claim": cg.model_dump(),
            "local_claim": cl.model_dump(),
            "gemini_issuer": cg.claimed_issuer,
            "gemini_issuer_id": cg.claimed_issuer_id,
            "local_issuer": cl.claimed_issuer,
            "local_issuer_id": cl.claimed_issuer_id,
            "issuer_match": iss_match,
            "gemini_top_source": top_src_g,
            "local_top_source": top_src_l,
            "top_source_same": src_same,
            "gemini_verdict": vg.verdict_key,
            "local_verdict": vl.verdict_key,
            "verdict_same": verd_same,
            "gemini_verdict_title": vg.title,
            "local_verdict_title": vl.title,
            "gemini_verdict_reason": vg.reason,
            "local_verdict_reason": vl.reason,
        }
        results.append(res_item)

        if item_id in target_5_ids:
            audit_5_items[item_id] = res_item

    print("-" * 120, flush=True)
    total = len(items)
    print(f"Summary over {total} items:", flush=True)
    print(f"  Claim Issuer Agreement:  {iss_match_count}/{total} ({iss_match_count/total*100:.1f}%)", flush=True)
    print(f"  Top-Source Agreement:    {src_match_count}/{total} ({src_match_count/total*100:.1f}%)", flush=True)
    print(f"  Verdict Agreement:       {verd_match_count}/{total} ({verd_match_count/total*100:.1f}%)", flush=True)

    out_path = REPO_ROOT / "docs" / "offline_claim_comparison.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nWritten updated results to {out_path}", flush=True)

    audit_out_path = REPO_ROOT / "docs" / "audit_5_items.json"
    with open(audit_out_path, "w", encoding="utf-8") as f:
        json.dump(audit_5_items, f, indent=2)
    print(f"Written 5 target items audit to {audit_out_path}", flush=True)


if __name__ == "__main__":
    main()
