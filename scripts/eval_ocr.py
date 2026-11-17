"""Evaluate the OCR pipeline across synthetic forgeries, genuine WhatsApp variants, and fake notices.

Sections:
a) Synthetic forgeries: strip watermark lines ("SYNTHETIC - NOT A REAL DOCUMENT"
   and "FOR DETECTOR TRAINING", including fragments), then compute exact-match
   rate for ``reference_no`` and ``subject`` against ``labels.jsonl``.
b) Genuine WhatsApp variants (English only, ``has_factcheck_stamp=False``):
   extract page-1 text only from the source PDF in ``02_official_source_corpus/files/``
   using ``pypdf``, apply Unicode NFC normalisation, and report both Character
   Error Rate (CER) and Word Recall per transform type.
c) Fake notices: save OCR output to ``data/eval/fake_notice_ocr.jsonl`` for
   manual review (no scoring).

Prints a summary table and saves ``data/eval/ocr_eval_summary.csv``.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from factcheck.data.loaders import (
    OfficialDoc,
    load_fake_notices,
    load_official_docs,
    load_synthetic_forgeries,
    load_whatsapp_variants,
)
from factcheck.extract.ocr.engines import is_gemini_config_error
from factcheck.extract.ocr.fields import extract_fields, strip_synthetic_watermark
from factcheck.extract.ocr.runner import run_ocr

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = PROJECT_ROOT / "data" / "eval"


def normalize_nfc(text: str) -> str:
    """Apply Unicode NFC normalisation and collapse whitespace."""
    norm = unicodedata.normalize("NFC", text or "")
    return re.sub(r"\s+", " ", norm).strip()


def levenshtein_distance(s1: str, s2: str) -> int:
    """Space-efficient Levenshtein edit distance between ``s1`` and ``s2``."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)
    if len(s1) < len(s2):
        s1, s2 = s2, s1
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1, start=1):
        curr = [i]
        for j, c2 in enumerate(s2, start=1):
            ins = curr[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if c1 == c2 else 1)
            curr.append(min(ins, delete, sub))
        prev = curr
    return prev[-1]


def compute_cer(reference: str, hypothesis: str) -> float:
    """Compute Character Error Rate after Unicode NFC normalisation."""
    ref_norm = normalize_nfc(reference)
    hyp_norm = normalize_nfc(hypothesis)
    if not ref_norm:
        return 0.0 if not hyp_norm else 1.0
    dist = levenshtein_distance(ref_norm, hyp_norm)
    return round(dist / len(ref_norm), 4)


def compute_word_recall(reference: str, hypothesis: str) -> float:
    """Share of reference page-1 words (lowercased alphanumeric tokens) present in OCR text."""
    ref_words = re.findall(r"\w+", normalize_nfc(reference).lower())
    if not ref_words:
        return 0.0
    hyp_word_set = set(re.findall(r"\w+", normalize_nfc(hypothesis).lower()))
    matched = sum(1 for w in ref_words if w in hyp_word_set)
    return round(matched / len(ref_words), 4)


def extract_pdf_page1_text(pdf_path: Path) -> str:
    """Extract text from page 1 (index 0) of ``pdf_path`` using pypdf."""
    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        return ""
    return (reader.pages[0].extract_text() or "").strip()


def run_evaluation(
    *,
    limit: int = 10,
    skip_api: bool = True,
    mock_vlm: bool = False,
    output_dir: Path = EVAL_DIR,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    allow_gemini = not skip_api
    use_cache = not mock_vlm

    if mock_vlm:
        print("=" * 72)
        print("MOCK RUN: results are not real OCR accuracy")
        print("=" * 72)

    summary_rows: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # (a) Synthetic forgeries: reference_no and subject exact match rate
    # ------------------------------------------------------------------
    synthetics = load_synthetic_forgeries()[:limit]
    ref_matches = 0
    sub_matches = 0
    syn_times: list[float] = []

    for syn in synthetics:
        res = run_ocr(
            syn.file,
            allow_gemini_fallback=allow_gemini,
            use_cache=use_cache,
        )
        if is_gemini_config_error(res.error):
            raise RuntimeError(
                f"Stopping evaluation batch due to Gemini configuration error: {res.error}"
            )
        syn_times.append(res.time_ms)
        cleaned_text = strip_synthetic_watermark(res.final_text)
        cleaned_fields = extract_fields(cleaned_text, strip_watermark=True)

        exp_ref = normalize_nfc(syn.reference_no)
        extracted_refs = {normalize_nfc(r) for r in cleaned_fields.reference_numbers}
        if exp_ref in extracted_refs:
            ref_matches += 1

        exp_sub = normalize_nfc(syn.subject).rstrip(".")
        ext_sub = normalize_nfc(cleaned_fields.subject or "").rstrip(".")
        if exp_sub and (exp_sub == ext_sub or exp_sub in normalize_nfc(cleaned_text)):
            sub_matches += 1

    n_syn = len(synthetics)
    summary_rows.append(
        {
            "section": "synthetic",
            "group": "all",
            "count": n_syn,
            "ref_exact_match_rate": round(ref_matches / n_syn, 4) if n_syn else 0.0,
            "subject_exact_match_rate": round(sub_matches / n_syn, 4) if n_syn else 0.0,
            "mean_cer": None,
            "mean_word_recall": None,
            "mean_time_ms": round(sum(syn_times) / n_syn, 2) if n_syn else 0.0,
        }
    )

    # ------------------------------------------------------------------
    # (b) Genuine WhatsApp variants (English only, has_factcheck_stamp=False)
    #     Compare against Page 1 of the PDF in 02_official_source_corpus/files/
    # ------------------------------------------------------------------
    official_by_id: dict[str, OfficialDoc] = {
        d.doc_id: d for d in load_official_docs(prefer_processed=True)
    }
    page1_cache: dict[str, str] = {}
    all_variants = load_whatsapp_variants(prefer_processed=True)

    eligible_variants = []
    for v in all_variants:
        if v.label != "genuine" or v.has_factcheck_stamp:
            continue
        src_doc = official_by_id.get(v.source_id)
        if src_doc is None or src_doc.language != "en":
            continue
        if src_doc.local_file is None or not src_doc.local_file.exists():
            logger.warning(
                "Skipping variant %s: source %s has no matching PDF in 02_official_source_corpus/files/",
                v.variant_id,
                v.source_id,
            )
            continue
        eligible_variants.append(v)

    selected_variants = eligible_variants[:limit]
    by_transform: dict[str, list[tuple[float, float, float]]] = defaultdict(list)

    for v in selected_variants:
        src_doc = official_by_id[v.source_id]
        if v.source_id not in page1_cache:
            page1_cache[v.source_id] = extract_pdf_page1_text(src_doc.local_file)  # type: ignore[arg-type]
        ref_page1 = page1_cache[v.source_id]
        if not ref_page1:
            logger.warning(
                "Skipping variant %s: empty page-1 text in %s",
                v.variant_id,
                src_doc.local_file,
            )
            continue
        res = run_ocr(
            v.file,
            allow_gemini_fallback=allow_gemini,
            use_cache=use_cache,
        )
        if is_gemini_config_error(res.error):
            raise RuntimeError(
                f"Stopping evaluation batch due to Gemini configuration error: {res.error}"
            )
        cer = compute_cer(ref_page1, res.final_text)
        w_rec = compute_word_recall(ref_page1, res.final_text)
        by_transform[v.transform].append((cer, w_rec, res.time_ms))

    for transform, metrics in sorted(by_transform.items()):
        cnt = len(metrics)
        mean_cer = round(sum(m[0] for m in metrics) / cnt, 4) if cnt else 0.0
        mean_wr = round(sum(m[1] for m in metrics) / cnt, 4) if cnt else 0.0
        mean_t = round(sum(m[2] for m in metrics) / cnt, 2) if cnt else 0.0
        summary_rows.append(
            {
                "section": "whatsapp_variants_page1",
                "group": transform,
                "count": cnt,
                "ref_exact_match_rate": None,
                "subject_exact_match_rate": None,
                "mean_cer": mean_cer,
                "mean_word_recall": mean_wr,
                "mean_time_ms": mean_t,
            }
        )

    # ------------------------------------------------------------------
    # (c) Fake notices: save OCR output to data/eval/fake_notice_ocr.jsonl
    # ------------------------------------------------------------------
    fake_notices = load_fake_notices(prefer_processed=True)[:limit]
    fake_filename = (
        "fake_notice_ocr_MOCK.jsonl" if mock_vlm else "fake_notice_ocr.jsonl"
    )
    fake_out_path = output_dir / fake_filename
    fake_times: list[float] = []
    with fake_out_path.open("w", encoding="utf-8", newline="\n") as fh:
        for fn in fake_notices:
            res = run_ocr(
                fn.image,
                allow_gemini_fallback=allow_gemini,
                use_cache=use_cache,
            )
            if is_gemini_config_error(res.error):
                raise RuntimeError(
                    f"Stopping evaluation batch due to Gemini configuration error: {res.error}"
                )
            fake_times.append(res.time_ms)
            record = {
                "notice_id": fn.notice_id,
                "language": fn.language,
                "narrative_id": fn.narrative_id,
                "claimed_issuer_id": fn.claimed_issuer_id,
                "reference_seen": fn.reference_seen,
                "image": str(fn.image),
                "ocr_result": res.model_dump(),
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    n_fake = len(fake_notices)
    summary_rows.append(
        {
            "section": "fake_notices",
            "group": "saved_for_review",
            "count": n_fake,
            "ref_exact_match_rate": None,
            "subject_exact_match_rate": None,
            "mean_cer": None,
            "mean_word_recall": None,
            "mean_time_ms": round(sum(fake_times) / n_fake, 2) if n_fake else 0.0,
        }
    )

    # Save CSV
    csv_filename = (
        "ocr_eval_summary_MOCK.csv" if mock_vlm else "ocr_eval_summary.csv"
    )
    csv_path = output_dir / csv_filename
    fieldnames = [
        "section",
        "group",
        "count",
        "ref_exact_match_rate",
        "subject_exact_match_rate",
        "mean_cer",
        "mean_word_recall",
        "mean_time_ms",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    # Print summary table
    print("\n=== OCR Evaluation Summary ===")
    header = (
        f"{'Section':24s} | {'Group':18s} | {'N':>4s} | {'RefEM':>7s} | "
        f"{'SubjEM':>7s} | {'CER':>7s} | {'WordRec':>7s} | {'Time(ms)':>9s}"
    )
    print(header)
    print("-" * len(header))
    for r in summary_rows:
        ref_s = (
            f"{r['ref_exact_match_rate']:.2%}"
            if r["ref_exact_match_rate"] is not None
            else "-"
        )
        sub_s = (
            f"{r['subject_exact_match_rate']:.2%}"
            if r["subject_exact_match_rate"] is not None
            else "-"
        )
        cer_s = f"{r['mean_cer']:.4f}" if r["mean_cer"] is not None else "-"
        wr_s = (
            f"{r['mean_word_recall']:.2%}"
            if r["mean_word_recall"] is not None
            else "-"
        )
        print(
            f"{r['section']:24s} | {r['group']:18s} | {r['count']:4d} | {ref_s:>7s} | "
            f"{sub_s:>7s} | {cer_s:>7s} | {wr_s:>7s} | {r['mean_time_ms']:9.2f}"
        )
    print(f"\nSaved fake notice OCR outputs to: {fake_out_path}")
    print(f"Saved evaluation summary CSV to : {csv_path}")
    return summary_rows


def _build_mock_vlm_lookup() -> dict[Path, str]:
    """Build deterministic mock VLM outputs (with synthetic watermarks) when Ollama is unavailable."""
    lookup: dict[Path, str] = {}
    for syn in load_synthetic_forgeries():
        lookup[syn.file.resolve()] = (
            "SYNTHETIC - NOT A REAL DOCUMENT - FOR DETECTOR TRAINING\n"
            f"{syn.issuer_name}\n"
            f"Ref. No: {syn.reference_no}\n"
            f"Date: {syn.issue_date} ({syn.issue_weekday})\n"
            f"Subject: {syn.subject}\n"
            f"Signed by: {syn.signatory_title}\n"
            "FOR DETECTOR TRAINING"
        )
    official_by_id = {d.doc_id: d for d in load_official_docs(prefer_processed=True)}
    p1_cache: dict[str, str] = {}
    for v in load_whatsapp_variants(prefer_processed=True):
        doc = official_by_id.get(v.source_id)
        if doc and doc.local_file and doc.local_file.exists():
            if v.source_id not in p1_cache:
                p1_cache[v.source_id] = extract_pdf_page1_text(doc.local_file)
            lookup[v.file.resolve()] = p1_cache[v.source_id]
    for fn in load_fake_notices(prefer_processed=True):
        ref_line = f"Ref No: {fn.reference_seen}\n" if fn.reference_seen else ""
        lookup[fn.image.resolve()] = (
            f"{fn.claimed_issuer or fn.claimed_issuer_id}\n"
            f"Date: {fn.post_date}\n"
            f"{ref_line}"
            f"{fn.clean_claim or fn.claim}"
        )
    return lookup


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Evaluate OCR across dataset splits.")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum items to evaluate per section (default: 10)",
    )
    parser.add_argument(
        "--skip-api",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip hosted Gemini fallback API (default: True)",
    )
    parser.add_argument(
        "--mock-vlm",
        action="store_true",
        default=False,
        help="Use deterministic mock VLM outputs when local Ollama is not installed",
    )
    args = parser.parse_args()
    if args.mock_vlm:
        import factcheck.extract.ocr.runner as ocr_runner

        lookup = _build_mock_vlm_lookup()
        ocr_runner.run_ollama_vlm = lambda path, cfg, **kw: (  # type: ignore[assignment]
            lookup.get(Path(path).resolve(), "Sample mock OCR text for document."),
            f"mock-ollama:{cfg.VLM_MODEL}",
            None,
        )
    run_evaluation(
        limit=args.limit,
        skip_api=args.skip_api,
        mock_vlm=args.mock_vlm,
    )


if __name__ == "__main__":
    main()
