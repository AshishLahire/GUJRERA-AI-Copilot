"""Offline Stage 2 forensic evaluation script (ZERO API calls).

Evaluates `run_forensics` on:
(a) 79 genuine documents in `02_official_source_corpus/documents.jsonl`
(b) 120 multilingual claims in `04_multilingual_claims/claims.jsonl`
(c) Cached synthetic forgeries in `06_synthetic_forgeries/labels.jsonl`
(d) All cached real fake notices from `01_fake_notice_benchmark` (10 demo fakes + any eval-cached fakes)

Saves summary CSV to `data/eval/forensics_eval_summary.csv` and prints detailed tables.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from factcheck.config import get_settings
from factcheck.extract.ocr.cache import OCRCache, compute_cache_key
from factcheck.extract.ocr.fields import extract_fields, strip_synthetic_watermark
from factcheck.forensics.runner import run_forensics
from factcheck.schemas import OCRResult

DS1_PATH = REPO_ROOT / "data" / "dataset" / "01_fake_notice_benchmark" / "notices.jsonl"
DS1_DIR = REPO_ROOT / "data" / "dataset" / "01_fake_notice_benchmark"
PROC_FAKE_PATH = REPO_ROOT / "data" / "processed" / "fake_notices.jsonl"
DEMO_IMAGES_DIR = REPO_ROOT / "data" / "demo" / "images"
DS2_PATH = REPO_ROOT / "data" / "dataset" / "02_official_source_corpus" / "documents.jsonl"
DS4_PATH = REPO_ROOT / "data" / "dataset" / "04_multilingual_claims" / "claims.jsonl"
DS6_LABELS_PATH = REPO_ROOT / "data" / "dataset" / "06_synthetic_forgeries" / "labels.jsonl"
DS6_DIR = REPO_ROOT / "data" / "dataset" / "06_synthetic_forgeries"
EVAL_CSV_PATH = REPO_ROOT / "data" / "eval" / "forensics_eval_summary.csv"

PIB_OVERLAY_RE = re.compile(
    r"(?i)(?:\bPIB\s*Fact\s*Check\b|\bPIBFactCheck\b|\bfactcheck\.pib\.gov\.in\b|फर्जी|फ़र्ज़ी|\bFAKE\b)"
)


def _make_text_ocr_result(doc_id: str, text: str, *, is_synthetic: bool = False) -> OCRResult:
    display_text = strip_synthetic_watermark(text) if is_synthetic else text
    fields = extract_fields(display_text, strip_watermark=False)
    return OCRResult(
        image_hash=doc_id,
        final_text=display_text,
        engine_used="dataset_text",
        valid=True,
        fields=fields,
        from_cache=True,
    )


def evaluate_genuine_corpus() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """(a) Run forensics on all 79 genuine documents in 02_official_source_corpus."""
    docs = [
        json.loads(line)
        for line in DS2_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    counts = {"low": 0, "medium": 0, "high": 0}
    detailed: list[dict[str, Any]] = []

    for doc in docs:
        doc_id = doc.get("doc_id", "")
        text = doc.get("text") or doc.get("title") or ""
        ocr_res = _make_text_ocr_result(doc_id, text)
        f_res = run_forensics(ocr_res)
        counts[f_res.risk_level] += 1
        non_info = [
            f"{f.cue_id} ({f.severity}, +{f.points}: {f.evidence!r})"
            for f in f_res.findings
            if f.severity != "info"
        ]
        all_findings_str = [
            f"{f.cue_id} ({f.severity}, +{f.points}: {f.evidence!r})"
            for f in f_res.findings
        ]
        detailed.append(
            {
                "doc_id": doc_id,
                "issuer_id": doc.get("issuer_id", ""),
                "reference_no": doc.get("reference_no", ""),
                "title": (doc.get("title") or "")[:70],
                "risk_level": f_res.risk_level,
                "risk_score": f_res.risk_score,
                "non_info_findings": non_info,
                "all_findings": all_findings_str,
            }
        )

    detailed.sort(key=lambda d: (-d["risk_score"], d["doc_id"]))
    summary = {
        "total": len(docs),
        "low": counts["low"],
        "medium": counts["medium"],
        "high": counts["high"],
    }
    return summary, detailed


def evaluate_multilingual_claims() -> list[dict[str, Any]]:
    """(b) Run forensics on all 120 claims in 04_multilingual_claims.

    Reports fee and urgency detection strictly as:
    - claims with >=1 detection / claims in that slot (so numerator <= denominator)
    - extra detections on non-slot claims in a separate column
    """
    claims = [
        json.loads(line)
        for line in DS4_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_lang: dict[str, dict[str, int]] = {}

    for c in claims:
        lang = c.get("language", "en")
        verdict = c.get("verdict", "fake")
        slots = c.get("slots") or {}
        has_fee_slot = bool(slots.get("fee_inr"))
        has_deadline_slot = bool(slots.get("deadline"))

        if lang not in by_lang:
            by_lang[lang] = {
                "fake_total": 0,
                "fake_fee_slot": 0,
                "fake_fee_in_slot_detected": 0,
                "fake_fee_extra": 0,
                "fake_urgency_slot": 0,
                "fake_urgency_in_slot_detected": 0,
                "fake_urgency_extra": 0,
                "fake_any_cue_detected": 0,
                "true_total": 0,
                "true_fp_medium_high": 0,
            }

        ocr_res = _make_text_ocr_result(c.get("claim_id", ""), c.get("text", ""))
        f_res = run_forensics(ocr_res)
        cues_found = {f.cue_id for f in f_res.findings if f.severity != "info"}

        stats = by_lang[lang]
        if verdict == "fake":
            stats["fake_total"] += 1
            if has_fee_slot:
                stats["fake_fee_slot"] += 1
                if "fee_demand" in cues_found:
                    stats["fake_fee_in_slot_detected"] += 1
            else:
                if "fee_demand" in cues_found:
                    stats["fake_fee_extra"] += 1

            if has_deadline_slot:
                stats["fake_urgency_slot"] += 1
                if "urgency_threat" in cues_found:
                    stats["fake_urgency_in_slot_detected"] += 1
            else:
                if "urgency_threat" in cues_found:
                    stats["fake_urgency_extra"] += 1

            if cues_found:
                stats["fake_any_cue_detected"] += 1
        else:
            stats["true_total"] += 1
            if f_res.risk_level in ("medium", "high"):
                stats["true_fp_medium_high"] += 1

    rows: list[dict[str, Any]] = []
    for lang, s in sorted(by_lang.items()):
        rows.append({"language": lang, **s})
    return rows


def evaluate_cached_synthetics() -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    """(c) For synthetic images present in ocr_cache.sqlite, compare detected cues vs labels.jsonl."""
    cfg = get_settings()
    cache = OCRCache(REPO_ROOT / cfg.CACHE_DB_PATH)
    labels = [
        json.loads(line)
        for line in DS6_LABELS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    candidate_models = [
        ("gemini", cfg.GEMINI_MODEL),
        ("gemini", "gemini-2.5-flash"),
        ("gemini", "gemini-2.5-flash-lite"),
        ("ollama", cfg.VLM_MODEL),
    ]
    prompt_versions = ["v3", "v2", "v1"]

    sample_rows: list[dict[str, Any]] = []
    per_cue_stats: dict[str, dict[str, int]] = {}

    for item in labels:
        syn_id = item["synthetic_id"]
        img_path = DS6_DIR / item["file"]
        if not img_path.exists():
            continue
        img_bytes = img_path.read_bytes()
        cached_entry = None
        for pv in prompt_versions:
            for eng, mod in candidate_models:
                key = compute_cache_key(img_bytes, eng, mod, pv)
                hit = cache.get(key)
                if hit is not None and hit.get("valid"):
                    cached_entry = hit
                    break
            if cached_entry is not None:
                break

        if cached_entry is None:
            continue

        ocr_res = _make_text_ocr_result(
            syn_id, cached_entry["final_text"], is_synthetic=True
        )
        f_res = run_forensics(ocr_res)
        detected_cues = sorted(
            {f.cue_id for f in f_res.findings if f.severity != "info"}
        )
        expected_cues = sorted(item.get("cues", []))

        for c in set(expected_cues) | set(detected_cues):
            if c not in per_cue_stats:
                per_cue_stats[c] = {"tp": 0, "fn": 0, "fp": 0}
            if c in expected_cues and c in detected_cues:
                per_cue_stats[c]["tp"] += 1
            elif c in expected_cues and c not in detected_cues:
                per_cue_stats[c]["fn"] += 1
            elif c not in expected_cues and c in detected_cues:
                per_cue_stats[c]["fp"] += 1

        sample_rows.append(
            {
                "synthetic_id": syn_id,
                "label": item.get("label"),
                "risk_level": f_res.risk_level,
                "risk_score": f_res.risk_score,
                "expected_cues": expected_cues,
                "detected_cues": detected_cues,
            }
        )

    return sample_rows, per_cue_stats


def evaluate_cached_real_fakes() -> tuple[list[dict[str, Any]], dict[str, int]]:
    """(d) Run forensics on every real fake notice whose OCR text is in ocr_cache.sqlite."""
    cfg = get_settings()
    cache = OCRCache(REPO_ROOT / cfg.CACHE_DB_PATH)

    # Load hand-annotated metadata from notices.jsonl / fake_notices.jsonl
    meta_by_id: dict[str, dict[str, Any]] = {}
    if DS1_PATH.exists():
        for line in DS1_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                meta_by_id[row["notice_id"]] = row
    if PROC_FAKE_PATH.exists():
        for line in PROC_FAKE_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                nid = row.get("notice_id") or row.get("id")
                if nid and nid not in meta_by_id:
                    meta_by_id[nid] = row

    candidate_models = [
        ("gemini", cfg.GEMINI_MODEL),
        ("gemini", "gemini-2.5-flash"),
        ("gemini", "gemini-2.5-flash-lite"),
        ("ollama", cfg.VLM_MODEL),
    ]
    prompt_versions = ["v3", "v2", "v1"]

    # Check all demo images + all dataset fake notice images
    candidate_ids: list[str] = sorted(
        set(meta_by_id.keys())
        | {p.stem for p in (DS1_DIR / "images").glob("*.*")}
        | {p.stem for p in DEMO_IMAGES_DIR.glob("FN-*.*")}
    )

    results: list[dict[str, Any]] = []
    counts = {"high": 0, "medium": 0, "low": 0}

    for nid in candidate_ids:
        if not nid.startswith("FN-"):
            continue
        meta = meta_by_id.get(nid, {})
        # Prefer cropped demo image if present, then dataset image
        candidate_paths: list[Path] = []
        for ext in (".jpg", ".png", ".jpeg"):
            p_demo = DEMO_IMAGES_DIR / f"{nid}{ext}"
            if p_demo.exists():
                candidate_paths.append(p_demo)
        if meta.get("image"):
            p_ds = DS1_DIR / meta["image"]
            if p_ds.exists() and p_ds not in candidate_paths:
                candidate_paths.append(p_ds)
        for ext in (".jpg", ".png", ".jpeg"):
            p_raw = DS1_DIR / "images" / f"{nid}{ext}"
            if p_raw.exists() and p_raw not in candidate_paths:
                candidate_paths.append(p_raw)

        cached_hit: dict[str, Any] | None = None
        used_path: Path | None = None
        used_pv: str | None = None
        for p in candidate_paths:
            img_bytes = p.read_bytes()
            for pv in prompt_versions:
                for eng, mod in candidate_models:
                    key = compute_cache_key(img_bytes, eng, mod, pv)
                    hit = cache.get(key)
                    if hit is not None and hit.get("valid"):
                        cached_hit = hit
                        used_path = p
                        used_pv = pv
                        break
                if cached_hit is not None:
                    break
            if cached_hit is not None:
                break

        if cached_hit is None:
            continue

        text = cached_hit["final_text"]
        ocr_res = _make_text_ocr_result(nid, text)
        f_res = run_forensics(ocr_res)
        counts[f_res.risk_level] += 1

        cues_found = [f.cue_id for f in f_res.findings if f.severity != "info"]
        all_cues = [f"{f.cue_id} ({f.severity}, +{f.points})" for f in f_res.findings]
        hand_cues = meta.get("forgery_cues") or []
        has_pib_overlay = bool(PIB_OVERLAY_RE.search(text))
        is_demo = (DEMO_IMAGES_DIR / f"{nid}.jpg").exists() or (
            DEMO_IMAGES_DIR / f"{nid}.png"
        ).exists()

        results.append(
            {
                "notice_id": nid,
                "is_demo": is_demo,
                "image_source": str(used_path.relative_to(REPO_ROOT)) if used_path else "",
                "prompt_version": used_pv,
                "claimed_issuer": meta.get("claimed_issuer") or meta.get("claimed_issuer_id") or "—",
                "detected_issuer": (
                    f"{f_res.detected_issuer.name} ({f_res.detected_issuer.issuer_id})"
                    if f_res.detected_issuer
                    else "Not detected"
                ),
                "risk_score": f_res.risk_score,
                "risk_level": f_res.risk_level,
                "overlay_filtered_count": f_res.overlay_filtered_count,
                "cue_ids_found": cues_found,
                "all_findings": all_cues,
                "hand_forgery_cues": hand_cues,
                "note": meta.get("note") or "",
                "uncropped_pib_in_ocr": has_pib_overlay,
            }
        )

    results.sort(key=lambda r: (0 if r["is_demo"] else 1, -r["risk_score"], r["notice_id"]))
    return results, counts


def main() -> None:
    ds2_summary, ds2_detailed = evaluate_genuine_corpus()
    ds4_rows = evaluate_multilingual_claims()
    ds6_samples, ds6_cues = evaluate_cached_synthetics()
    ds1_fakes, ds1_counts = evaluate_cached_real_fakes()

    print("=== (a) 02_official_source_corpus (79 genuine documents) ===")
    print(
        f"Total: {ds2_summary['total']} | Low: {ds2_summary['low']} | "
        f"Medium: {ds2_summary['medium']} | High: {ds2_summary['high']}"
    )
    print("\nTop 5 genuine documents by risk_score:")
    for row in ds2_detailed[:5]:
        print(
            f"  {row['doc_id']} ({row['issuer_id']}, ref={row['reference_no']}): "
            f"score={row['risk_score']} ({row['risk_level']}) | "
            f"findings={row['non_info_findings'] or row['all_findings']}"
        )

    print("\n=== (b) 04_multilingual_claims (120 claims across 7 languages) ===")
    print(
        f"{'Lang':<8} {'Fake':<6} {'FeeSlot(det/slot)':<18} {'FeeExtra':<10} "
        f"{'UrgSlot(det/slot)':<18} {'UrgExtra':<10} {'AnyCue':<10} {'TrueCtrl':<10} {'TrueFP':<8}"
    )
    for r in ds4_rows:
        fee_str = f"{r['fake_fee_in_slot_detected']}/{r['fake_fee_slot']}"
        urg_str = f"{r['fake_urgency_in_slot_detected']}/{r['fake_urgency_slot']}"
        any_str = f"{r['fake_any_cue_detected']}/{r['fake_total']}"
        print(
            f"{r['language']:<8} {r['fake_total']:<6} {fee_str:<18} +{r['fake_fee_extra']:<9} "
            f"{urg_str:<18} +{r['fake_urgency_extra']:<9} {any_str:<10} "
            f"{r['true_total']:<10} {r['true_fp_medium_high']:<8}"
        )

    print(f"\n=== (c) 06_synthetic_forgeries ({len(ds6_samples)} cached samples) ===")
    for s in ds6_samples:
        print(
            f"  {s['synthetic_id']} ({s['label']}): score={s['risk_score']} ({s['risk_level']}) | "
            f"expected={s['expected_cues']} | detected={s['detected_cues']}"
        )

    print(
        f"\n=== (d) 01_fake_notice_benchmark ({len(ds1_fakes)} cached real fakes — in-sample: rules were designed after seeing these documents) ===\n"
        f"Summary: High={ds1_counts['high']} | Medium={ds1_counts['medium']} | Low={ds1_counts['low']}"
    )
    for rf in ds1_fakes:
        tag = "DEMO" if rf["is_demo"] else "EVAL"
        pib_tag = f" [PIB OVERLAY LINES FILTERED: {rf['overlay_filtered_count']}]" if rf["overlay_filtered_count"] else ""
        print(
            f"\n  [{tag}] {rf['notice_id']}{pib_tag}\n"
            f"    Score/Level     : {rf['risk_score']} / 100 ({rf['risk_level']})\n"
            f"    Claimed Issuer  : {rf['claimed_issuer']}\n"
            f"    Detected Issuer : {rf['detected_issuer']}\n"
            f"    Detected Cues   : {rf['cue_ids_found']} (all findings: {rf['all_findings']})\n"
            f"    Hand Cues       : {rf['hand_forgery_cues']}\n"
            f"    Dataset Note    : {rf['note']}"
        )

    # Save CSV
    EVAL_CSV_PATH.parent.mkdir(parents=True, encoding="utf-8") if False else EVAL_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVAL_CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["section", "item_or_group", "metric_1", "metric_2", "metric_3", "notes"])
        writer.writerow(
            [
                "02_official_source_corpus",
                "all_79_genuine",
                f"low={ds2_summary['low']}",
                f"medium={ds2_summary['medium']}",
                f"high={ds2_summary['high']}",
                f"fp_high_rate={ds2_summary['high']}/{ds2_summary['total']}",
            ]
        )
        for row in ds2_detailed[:5]:
            writer.writerow(
                [
                    "02_top5_genuine",
                    row["doc_id"],
                    f"issuer={row['issuer_id']}",
                    f"score={row['risk_score']} ({row['risk_level']})",
                    f"ref={row['reference_no']}",
                    "; ".join(row["non_info_findings"] or row["all_findings"]),
                ]
            )
        for r in ds4_rows:
            writer.writerow(
                [
                    "04_multilingual_claims",
                    r["language"],
                    f"fee_slot={r['fake_fee_in_slot_detected']}/{r['fake_fee_slot']} (+{r['fake_fee_extra']} extra)",
                    f"urgency_slot={r['fake_urgency_in_slot_detected']}/{r['fake_urgency_slot']} (+{r['fake_urgency_extra']} extra)",
                    f"any_cue={r['fake_any_cue_detected']}/{r['fake_total']}",
                    f"true_fp={r['true_fp_medium_high']}/{r['true_total']}",
                ]
            )
        for s in ds6_samples:
            writer.writerow(
                [
                    "06_synthetic_cached",
                    s["synthetic_id"],
                    f"label={s['label']}",
                    f"score={s['risk_score']} ({s['risk_level']})",
                    f"expected={','.join(s['expected_cues'])}",
                    f"detected={','.join(s['detected_cues'])}",
                ]
            )
        for rf in ds1_fakes:
            writer.writerow(
                [
                    "01_real_fakes_cached",
                    rf["notice_id"],
                    f"score={rf['risk_score']} ({rf['risk_level']})",
                    f"detected_issuer={rf['detected_issuer']}",
                    f"cues={','.join(rf['cue_ids_found'])}",
                    f"uncropped_pib={rf['uncropped_pib_in_ocr']} | hand_cues={'; '.join(rf['hand_forgery_cues'])}",
                ]
            )


if __name__ == "__main__":
    main()
