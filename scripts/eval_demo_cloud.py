import json
from pathlib import Path
from factcheck.config import Settings
from factcheck.extract.ocr import run_ocr, extract_fields, strip_synthetic_watermark
from factcheck.forensics.checks import filter_pib_overlay_lines
from factcheck.forensics import run_forensics
from factcheck.schemas import OCRResult
from factcheck.claims.extractor import extract_claim
from factcheck.retrieval.matcher import match_sources
from factcheck.decide.verdict import decide_verdict

repo_root = Path(__file__).resolve().parents[1]
demo_file = repo_root / "data" / "demo" / "demo_set.json"
with open(demo_file, "r", encoding="utf-8") as f:
    demo_data = json.load(f)

settings_cloud = Settings(OFFLINE_MODE=False, OCR_ENGINE_PREFERENCE="gemini_first")

print(f"{'ID':<25} | {'Label':<10} | {'Toggle OFF':<20} | {'Toggle ON':<20} | {'Previous Ref Table':<20}")
print("-" * 105)

results = []

for item in demo_data["items"]:
    item_id = item["id"]
    label = item["label"]
    img_rel = item["image"]
    img_path = repo_root / img_rel
    synthetic = label.startswith("synthetic") or label in ("clean", "forged")
    
    # 1. OCR (cached)
    ocr_cloud = run_ocr(img_path, allow_gemini_fallback=True, use_cache=True, settings=settings_cloud)
    text_c = strip_synthetic_watermark(ocr_cloud.final_text) if synthetic else ocr_cloud.final_text
    cln_c, spans_c, _ = filter_pib_overlay_lines(text_c)
    overlay_c = "\n".join(text_c[s.char_start : s.char_end] for s in spans_c)
    fields_c = extract_fields(cln_c, strip_watermark=False) if spans_c else (
        extract_fields(text_c, strip_watermark=False) if synthetic else ocr_cloud.fields
    )
    
    ocr_cloud_obj = OCRResult(
        image_hash=ocr_cloud.image_hash,
        final_text=text_c,
        engine_used=ocr_cloud.engine_used,
        valid=ocr_cloud.valid,
        fields=fields_c,
        from_cache=True,
    )
    forensics_cloud = run_forensics(ocr_cloud_obj)
    
    # 2. Claim (cached)
    claim_cloud = extract_claim(cln_c, allow_cloud=False, use_cache=True, settings=settings_cloud)
    
    # 3. Matcher Toggle OFF
    match_off = match_sources(
        canonical_claim_en=claim_cloud.canonical_claim_en,
        original_text=cln_c,
        fields=fields_c,
        claimed_issuer_id=claim_cloud.claimed_issuer_id,
    )
    verd_off = decide_verdict(
        forensics_cloud,
        match_off,
        cleaned_body_text=cln_c,
        removed_overlay_text=overlay_c,
        claimed_issuer_id=claim_cloud.claimed_issuer_id,
    )
    
    # 4. Matcher Toggle ON (exclude own debunk)
    match_on = match_sources(
        canonical_claim_en=claim_cloud.canonical_claim_en,
        original_text=cln_c,
        fields=fields_c,
        exclude_debunk_id=item_id if label == "fake" else None,
        claimed_issuer_id=claim_cloud.claimed_issuer_id,
    )
    verd_on = decide_verdict(
        forensics_cloud,
        match_on,
        cleaned_body_text=cln_c,
        removed_overlay_text=overlay_c,
        claimed_issuer_id=claim_cloud.claimed_issuer_id,
    )
    
    entry = {
        "id": item_id,
        "label": label,
        "verdict_off": verd_off.verdict_key,
        "verdict_off_title": verd_off.title,
        "verdict_on": verd_on.verdict_key,
        "verdict_on_title": verd_on.title,
        "fields_ref": fields_c.reference_numbers,
    }
    results.append(entry)
    print(f"{item_id:<25} | {label:<10} | {verd_off.verdict_key:<20} | {verd_on.verdict_key:<20}")

out_path = repo_root / "docs" / "cloud_demo_eval_results.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print("\nDone. Saved to", out_path)
