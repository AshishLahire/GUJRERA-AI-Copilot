"""Offline Stage 4 & 5 retrieval and threshold calibration evaluation (ZERO API calls).

Evaluates HybridRetriever (BM25 + intfloat/multilingual-e5-small with RRF k=60) on:
1. `04_multilingual_claims` (105 fake claims across 7 languages + 15 true controls) — normal retrieval
   (no single source post; Telegram post narrative labels from keyword rules in rules.py are marked 'approximate').
2. `01_fake_notice_benchmark` (`data/processed/fake_notices.jsonl`, 90 notices) — `clean_claim` queries
   in both normal mode and Leave-One-Out (LOO) mode (removing the entire deduplicated record).
3. Threshold calibration sweep across candidate cosine thresholds, reporting precision, recall, and
   false-strong rates on true controls and genuine official documents.
4. First 5 demo samples in `demo_order` using overlay-filtered OCR text only (no LLM).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from factcheck.config import get_settings
from factcheck.decide.verdict import decide_verdict
from factcheck.extract.ocr.cache import OCRCache, compute_cache_key
from factcheck.extract.ocr.fields import extract_fields
from factcheck.forensics.checks import filter_pib_overlay_lines
from factcheck.forensics.runner import run_forensics
from factcheck.retrieval.matcher import HybridRetriever
from factcheck.schemas import OCRResult

DS1_PROC_PATH = REPO_ROOT / "data" / "processed" / "fake_notices.jsonl"
DS2_PATH = REPO_ROOT / "data" / "dataset" / "02_official_source_corpus" / "documents.jsonl"
DS4_PATH = REPO_ROOT / "data" / "dataset" / "04_multilingual_claims" / "claims.jsonl"
DEMO_SET_PATH = REPO_ROOT / "data" / "demo" / "demo_set.json"


def eval_multilingual_claims(retriever: HybridRetriever) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Evaluate normal retrieval on 04_multilingual_claims (no single source post)."""
    claims = [
        json.loads(line)
        for line in DS4_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_lang: dict[str, dict[str, int]] = {}
    all_fake_top1: list[dict[str, Any]] = []
    all_true_top1: list[dict[str, Any]] = []

    for c in claims:
        lang = c.get("language", "en")
        verdict = c.get("verdict", "fake")
        nar_id = c.get("narrative_id")
        if lang not in by_lang:
            by_lang[lang] = {
                "fake_total": 0,
                "both_top1": 0,
                "both_top3": 0,
                "orig_only_top1": 0,
                "orig_only_top3": 0,
                "true_total": 0,
                "true_false_strong_debunk": 0,
                "true_official_top1": 0,
            }

        stats = by_lang[lang]
        # 1) Query with canonical_claim_en + original text
        res_both = retriever.search(
            canonical_claim_en=c.get("canonical_claim_en"),
            original_text=c.get("text"),
            top_k=3,
        )
        # 2) Query with original-language text only (no English canonical claim)
        res_orig = retriever.search(
            canonical_claim_en=None,
            original_text=c.get("text"),
            top_k=3,
        )

        if verdict == "fake":
            stats["fake_total"] += 1
            deb_both = res_both.debunks
            deb_orig = res_orig.debunks

            if deb_both and deb_both[0].narrative_id == nar_id:
                stats["both_top1"] += 1
            if any(m.narrative_id == nar_id for m in deb_both[:3]):
                stats["both_top3"] += 1

            if deb_orig and deb_orig[0].narrative_id == nar_id:
                stats["orig_only_top1"] += 1
            if any(m.narrative_id == nar_id for m in deb_orig[:3]):
                stats["orig_only_top3"] += 1

            if deb_both:
                all_fake_top1.append(
                    {
                        "query_id": c["claim_id"],
                        "expected_narrative": nar_id,
                        "matched_narrative": deb_both[0].narrative_id,
                        "cosine": deb_both[0].cosine_score or 0.0,
                        "correct": deb_both[0].narrative_id == nar_id,
                    }
                )
        else:
            stats["true_total"] += 1
            deb_both = res_both.debunks
            if deb_both and deb_both[0].label == "strong":
                stats["true_false_strong_debunk"] += 1
            if res_both.official and res_both.official[0].label in ("strong", "possible"):
                stats["true_official_top1"] += 1
            if deb_both:
                all_true_top1.append(
                    {
                        "query_id": c["claim_id"],
                        "cosine": deb_both[0].cosine_score or 0.0,
                        "top_debunk_id": deb_both[0].doc_id,
                    }
                )

    rows = [{"language": k, **v} for k, v in sorted(by_lang.items())]
    return rows, all_fake_top1, all_true_top1


def eval_fake_notices_loo(retriever: HybridRetriever) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Evaluate normal and Leave-One-Out (LOO) retrieval on 01_fake_notice_benchmark clean_claim queries."""
    notices = [
        json.loads(line)
        for line in DS1_PROC_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    total = len(notices)
    normal_exact_top1 = 0
    normal_nar_top1 = 0
    normal_nar_top3 = 0
    loo_nar_top1 = 0
    loo_nar_top3 = 0
    loo_records: list[dict[str, Any]] = []

    # Count how many debunks exist per narrative in the index
    nar_counts: dict[str, int] = {}
    for d in retriever.debunks:
        nid = d.get("narrative_id")
        if nid:
            nar_counts[nid] = nar_counts.get(nid, 0) + 1

    singleton_narratives = 0

    for row in notices:
        nid = row["notice_id"]
        src_url = row.get("source_url")
        nar_id = row.get("narrative_id")
        query_text = row.get("clean_claim") or row.get("claim") or ""

        if nar_id and nar_counts.get(nar_id, 0) <= 1:
            singleton_narratives += 1

        # Normal retrieval
        res_norm = retriever.search(
            canonical_claim_en=query_text,
            original_text=None,
            top_k=3,
        )
        if res_norm.debunks:
            if res_norm.debunks[0].doc_id == nid:
                normal_exact_top1 += 1
            if res_norm.debunks[0].narrative_id == nar_id:
                normal_nar_top1 += 1
            if any(m.narrative_id == nar_id for m in res_norm.debunks[:3]):
                normal_nar_top3 += 1

        # Leave-One-Out retrieval (removes the whole deduplicated record: notice_id + linked Telegram post)
        res_loo = retriever.search(
            canonical_claim_en=query_text,
            original_text=None,
            top_k=3,
            exclude_debunk_id=nid,
            exclude_url=src_url if src_url and "t.me/" in src_url else None,
        )
        if res_loo.debunks:
            assert all(m.doc_id != nid for m in res_loo.debunks), f"Leakage: {nid} not removed!"
            top1_ok = res_loo.debunks[0].narrative_id == nar_id
            top3_ok = any(m.narrative_id == nar_id for m in res_loo.debunks[:3])
            if top1_ok:
                loo_nar_top1 += 1
            if top3_ok:
                loo_nar_top3 += 1
            loo_records.append(
                {
                    "query_id": nid,
                    "expected_narrative": nar_id,
                    "matched_doc_id": res_loo.debunks[0].doc_id,
                    "matched_narrative": res_loo.debunks[0].narrative_id,
                    "matched_status": res_loo.debunks[0].narrative_status,
                    "cosine": res_loo.debunks[0].cosine_score or 0.0,
                    "correct": top1_ok,
                }
            )

    summary = {
        "total": total,
        "singleton_narratives": singleton_narratives,
        "normal_exact_top1": normal_exact_top1,
        "normal_nar_top1": normal_nar_top1,
        "normal_nar_top3": normal_nar_top3,
        "loo_nar_top1": loo_nar_top1,
        "loo_nar_top3": loo_nar_top3,
    }
    return summary, loo_records


def calibrate_thresholds(
    retriever: HybridRetriever,
    fake_claim_top1: list[dict[str, Any]],
    loo_top1: list[dict[str, Any]],
    true_claim_top1: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sweep candidate cosine similarity thresholds and compute precision & false-strong rates."""
    # Also query the 79 genuine official documents against debunks as negative controls
    docs = [
        json.loads(line)
        for line in DS2_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    genuine_debunk_cosines: list[float] = []
    for doc in docs:
        q = f"{doc.get('title') or ''} {(doc.get('text') or '')[:300]}".strip()
        res = retriever.search(canonical_claim_en=None, original_text=q, top_k=1)
        if res.debunks and res.debunks[0].cosine_score is not None:
            genuine_debunk_cosines.append(res.debunks[0].cosine_score)

    candidate_thresholds = [0.78, 0.80, 0.82, 0.84, 0.85, 0.86, 0.87, 0.88, 0.89, 0.90]
    rows: list[dict[str, Any]] = []

    for th in candidate_thresholds:
        # On 105 fake claims + 90 LOO fake notices + 15 true claims + 79 genuine docs
        fc_pred = [x for x in fake_claim_top1 if x["cosine"] >= th]
        fc_tp = [x for x in fc_pred if x["correct"]]

        loo_pred = [x for x in loo_top1 if x["cosine"] >= th]
        loo_tp = [x for x in loo_pred if x["correct"]]

        tc_fp = [x for x in true_claim_top1 if x["cosine"] >= th]
        gen_fp = [c for c in genuine_debunk_cosines if c >= th]

        total_pred_strong = len(fc_pred) + len(loo_pred) + len(tc_fp) + len(gen_fp)
        total_tp_strong = len(fc_tp) + len(loo_tp)
        precision = (total_tp_strong / total_pred_strong * 100.0) if total_pred_strong > 0 else 100.0

        rows.append(
            {
                "threshold": th,
                "fake_claims_strong": f"{len(fc_tp)}/{len(fake_claim_top1)}",
                "loo_notices_strong": f"{len(loo_tp)}/{len(loo_top1)}",
                "true_claims_fp": f"{len(tc_fp)}/{len(true_claim_top1)}",
                "genuine_docs_fp": f"{len(gen_fp)}/{len(genuine_debunk_cosines)}",
                "overall_strong_precision_pct": round(precision, 1),
            }
        )
    return rows


def eval_all_12_demo_fakes(retriever: HybridRetriever) -> list[dict[str, Any]]:
    """Run Stage 2 + Stage 4 + Stage 5 on all 12 demo fakes with simulate_unseen OFF and ON (overlay-filtered OCR text only, no LLM)."""
    cfg = get_settings()
    cache = OCRCache(REPO_ROOT / cfg.CACHE_DB_PATH)
    demo_data = json.loads(DEMO_SET_PATH.read_text(encoding="utf-8"))
    fake_items = sorted(
        [it for it in demo_data.get("items", []) if it.get("label") == "fake"],
        key=lambda it: (it.get("demo_order") is None, it.get("demo_order", 9999)),
    )

    candidate_models = [
        ("gemini", cfg.GEMINI_MODEL),
        ("gemini", "gemini-2.5-flash"),
        ("gemini", "gemini-2.5-flash-lite"),
        ("ollama", cfg.VLM_MODEL),
    ]
    prompt_versions = ["v3", "v2", "v1"]

    results: list[dict[str, Any]] = []
    for item in fake_items:
        sid = item["id"]
        img_path = REPO_ROOT / item["image"]
        img_bytes = img_path.read_bytes()
        cached_hit = None
        for pv in prompt_versions:
            for eng, mod in candidate_models:
                key = compute_cache_key(img_bytes, eng, mod, pv)
                hit = cache.get(key)
                if hit is not None and hit.get("valid"):
                    cached_hit = hit
                    break
            if cached_hit is not None:
                break

        raw_text = cached_hit["final_text"] if cached_hit else ""
        ocr_res = OCRResult(
            image_hash=sid,
            final_text=raw_text,
            engine_used="cached_ocr",
            valid=True,
            fields=extract_fields(raw_text, strip_watermark=False),
            from_cache=True,
        )
        forensics = run_forensics(ocr_res)
        cleaned_text, spans, _ = filter_pib_overlay_lines(raw_text)
        removed_overlay_text = "\n".join(raw_text[s.char_start : s.char_end] for s in spans)
        cleaned_fields = extract_fields(cleaned_text, strip_watermark=False)

        # 1. Toggle OFF (normal retrieval)
        ret_off = retriever.search(
            canonical_claim_en=None,
            original_text=cleaned_text,
            fields=cleaned_fields,
            top_k=3,
        )
        verdict_off = decide_verdict(
            forensics,
            ret_off,
            cleaned_body_text=cleaned_text,
            removed_overlay_text=removed_overlay_text,
        )
        downgraded_off = any(m.downgraded_from_overlay_overlap for m in ret_off.debunks)

        # 2. Toggle ON (simulate unseen forgery / leave-one-out)
        ret_on = retriever.search(
            canonical_claim_en=None,
            original_text=cleaned_text,
            fields=cleaned_fields,
            top_k=3,
            exclude_debunk_id=sid,
        )
        verdict_on = decide_verdict(
            forensics,
            ret_on,
            cleaned_body_text=cleaned_text,
            removed_overlay_text=removed_overlay_text,
        )
        downgraded_on = any(m.downgraded_from_overlay_overlap for m in ret_on.debunks)

        top_deb_off = ret_off.debunks[0] if ret_off.debunks else None
        top_deb_on = ret_on.debunks[0] if ret_on.debunks else None

        results.append(
            {
                "demo_order": item.get("demo_order"),
                "sample_id": sid,
                "forensic_score": f"{forensics.risk_score} ({forensics.risk_level})",
                "overlay_lines_removed": len(spans),
                "off_top_debunk": (
                    f"{top_deb_off.doc_id} ({top_deb_off.score:.4f}, {top_deb_off.label})"
                    if top_deb_off
                    else "—"
                ),
                "off_verdict": f"{verdict_off.title} [{verdict_off.color}]",
                "on_top_debunk": (
                    f"{top_deb_on.doc_id} ({top_deb_on.score:.4f}, {top_deb_on.label})"
                    if top_deb_on
                    else "—"
                ),
                "on_verdict": f"{verdict_on.title} [{verdict_on.color}]",
                "overlay_downgraded": downgraded_off or downgraded_on,
                "talking_point": item.get("talking_point"),
            }
        )
    return results


def main() -> None:
    retriever = HybridRetriever()
    print(f"Retrieval mode: {retriever.retrieval_mode} | Debunks indexed: {len(retriever.debunks)} | Official indexed: {len(retriever.official)}")

    # 1. 04_multilingual_claims
    lang_rows, fake_claim_top1, true_claim_top1 = eval_multilingual_claims(retriever)
    print("\n=== 1. 04_multilingual_claims (Normal Retrieval — TG narrative labels marked 'approximate') ===")
    print(
        f"{'Lang':<8} {'Fake':<6} {'Both(en+orig) Top1':<20} {'Both(en+orig) Top3':<20} "
        f"{'OrigOnly Top1':<16} {'OrigOnly Top3':<16} {'TrueCtrl':<10} {'TrueFalseStrong':<16}"
    )
    for r in lang_rows:
        b1 = f"{r['both_top1']}/{r['fake_total']}"
        b3 = f"{r['both_top3']}/{r['fake_total']}"
        o1 = f"{r['orig_only_top1']}/{r['fake_total']}"
        o3 = f"{r['orig_only_top3']}/{r['fake_total']}"
        tfp = f"{r['true_false_strong_debunk']}/{r['true_total']}"
        print(
            f"{r['language']:<8} {r['fake_total']:<6} {b1:<20} {b3:<20} "
            f"{o1:<16} {o3:<16} {r['true_total']:<10} {tfp:<16}"
        )

    # 2. 01_fake_notice_benchmark clean_claim (Normal vs Leave-One-Out)
    loo_summary, loo_top1 = eval_fake_notices_loo(retriever)
    tot = loo_summary["total"]
    print("\n=== 2. 01_fake_notice_benchmark clean_claim Queries (Normal vs. Leave-One-Out) ===")
    print(f"Total notices evaluated           : {tot}")
    print(f"Normal Exact-Record Match Top-1   : {loo_summary['normal_exact_top1']}/{tot} ({loo_summary['normal_exact_top1']/tot*100:.1f}%)")
    print(f"Normal Narrative Match Top-1      : {loo_summary['normal_nar_top1']}/{tot} ({loo_summary['normal_nar_top1']/tot*100:.1f}%)")
    print(f"Normal Narrative Match Top-3      : {loo_summary['normal_nar_top3']}/{tot} ({loo_summary['normal_nar_top3']/tot*100:.1f}%)")
    print(f"Leave-One-Out Narrative Top-1     : {loo_summary['loo_nar_top1']}/{tot} ({loo_summary['loo_nar_top1']/tot*100:.1f}%)")
    print(f"Leave-One-Out Narrative Top-3     : {loo_summary['loo_nar_top3']}/{tot} ({loo_summary['loo_nar_top3']/tot*100:.1f}%)")

    # 3. Threshold calibration sweep
    cal_rows = calibrate_thresholds(retriever, fake_claim_top1, loo_top1, true_claim_top1)
    print("\n=== 3. Cosine Similarity Threshold Calibration Sweep ===")
    print(
        f"{'Threshold':<11} {'FakeClaimsStrong':<18} {'LOONoticesStrong':<18} "
        f"{'TrueClaimsFP':<15} {'GenuineDocsFP':<16} {'StrongPrecision%':<18}"
    )
    for cr in cal_rows:
        print(
            f"{cr['threshold']:<11.2f} {cr['fake_claims_strong']:<18} {cr['loo_notices_strong']:<18} "
            f"{cr['true_claims_fp']:<15} {cr['genuine_docs_fp']:<16} {cr['overall_strong_precision_pct']:<18.1f}"
        )

    # 4. All 12 demo fakes (Simulate Unseen Forgery toggle OFF vs ON)
    demo_fakes = eval_all_12_demo_fakes(retriever)
    print("\n=== 4. 12 Demo Fake Samples: Simulate Unseen Forgery Toggle OFF vs. ON (Overlay-Filtered OCR Only) ===")
    for d in demo_fakes:
        print(
            f"  #{d['demo_order']:<2} {d['sample_id']} | Forensics: {d['forensic_score']:<12} | OverlayRemoved: {d['overlay_lines_removed']:<2} | OverlayDowngraded: {d['overlay_downgraded']}\n"
            f"    Toggle OFF (Normal) : Debunk={d['off_top_debunk']:<34} -> Verdict={d['off_verdict']}\n"
            f"    Toggle ON  (Unseen) : Debunk={d['on_top_debunk']:<34} -> Verdict={d['on_verdict']}"
        )


if __name__ == "__main__":
    main()
