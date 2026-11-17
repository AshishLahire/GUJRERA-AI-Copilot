"""Evaluation script for ASR transcription: measure accuracy across test clips.

Note: Evaluation clips are short scripted clips (4–8 s); 12 of 20 are synthetic TTS voices.

Usage:
  python scripts/eval_asr.py           # Auto-detect mode (tests language detection + transcription)
  python scripts/eval_asr.py --manual  # Manual language mode (ground-truth language supplied)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import jiwer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from factcheck.ingest.audio.transcribe import transcribe_audio

ASR_DIR = REPO_ROOT / "data" / "eval" / "asr"
MANIFEST_PATH = ASR_DIR / "manifest.csv"

# Nukta marks across Indic scripts
NUKTA_RE = re.compile(r"[\u093C\u09BC\u0A3C\u0ABC\u0B3C\u0CBC\u0CBD]")

# Common Hindi and English number words mapped to Arabic numerals
NUMBER_WORD_MAP = {
    "दो हज़ार": "2000",
    "दो हजार": "2000",
    "पांच सौ": "500",
    "पाँच सौ": "500",
    "पाँच": "5",
    "पांच": "5",
    "दस": "10",
    "पंद्रह": "15",
    "पन्द्रह": "15",
    "two thousand": "2000",
    "five hundred": "500",
    "five": "5",
    "ten": "10",
    "fifteen": "15",
}

# Indic digits to ASCII digits
INDIC_DIGITS = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4", "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
    "০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4", "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9",
    "૦": "0", "૧": "1", "૨": "2", "૩": "3", "૪": "4", "૫": "5", "૬": "6", "૭": "7", "૮": "8", "૯": "9",
    "੦": "0", "੧": "1", "੨": "2", "੩": "3", "੪": "4", "੫": "5", "੬": "6", "੭": "7", "੮": "8", "੯": "9",
    "୦": "0", "୧": "1", "୨": "2", "୩": "3", "୪": "4", "୫": "5", "୬": "6", "୭": "7", "୮": "8", "୯": "9",
    "௦": "0", "௧": "1", "௨": "2", "௩": "3", "௪": "4", "௫": "5", "௬": "6", "௭": "7", "௮": "8", "௯": "9",
    "౦": "0", "౧": "1", "౨": "2", "౩": "3", "౪": "4", "౫": "5", "౬": "6", "౭": "7", "౮": "8", "౯": "9",
    "೦": "0", "೧": "1", "೨": "2", "೩": "3", "೪": "4", "೫": "5", "೬": "6", "೭": "7", "೮": "8", "೯": "9",
    "൦": "0", "൧": "1", "൨": "2", "൩": "3", "൪": "4", "൫": "5", "൬": "6", "൭": "7", "൮": "8", "൯": "9",
}

# Languages identified as weak under Whisper small (non-Latin, non-Devanagari Dravidian/Eastern scripts)
WHISPER_WEAK_LANGS = {"kn", "te", "ml", "bn", "gu"}


def old_norm(s: str) -> str:
    """Original un-normalized metric: punctuation strip and lowercasing."""
    s = re.sub(r"[^\w\s]", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def normalize_text_for_asr(text: str, drop_digits: bool = False) -> str:
    """Fair normalization before CER / WER calculation:
    - Unicode NFC normalization
    - Nukta removal (U+093C and Indic equivalents)
    - Indic digits mapped to ASCII digits
    - Common Hindi and English number words mapped to digits
    - Punctuation removal (including Devanagari danda '।')
    - Optional: digits-insensitive mode (drops all numbers)
    """
    s = unicodedata.normalize("NFC", text or "")
    s = s.lower()
    s = NUKTA_RE.sub("", s)
    for ind_d, asc_d in INDIC_DIGITS.items():
        s = s.replace(ind_d, asc_d)
    for word, dig in NUMBER_WORD_MAP.items():
        s = re.sub(rf"\b{re.escape(word)}\b", dig, s)
    s = re.sub(r"[^\w\s]", " ", s)
    if drop_digits:
        s = re.sub(r"\b\d+\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolve_clip_path(raw_file_str: str) -> Path:
    p = Path(raw_file_str)
    if p.exists():
        return p
    parts = list(p.parts)
    if parts and parts[0] == "data":
        cand = ASR_DIR / Path(*parts[1:])
        if cand.exists():
            return cand
    cand2 = ASR_DIR / p.name
    if cand2.exists():
        return cand2
    for sub in ["test_audio", "step7_check"]:
        cand3 = ASR_DIR / sub / p.name
        if cand3.exists():
            return cand3
    return p


def run_evaluation(manual_language: bool = False, use_cache: bool = True) -> dict:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found at {MANIFEST_PATH}")

    rows = list(csv.DictReader(MANIFEST_PATH.open(encoding="utf-8")))
    records: list[dict] = []
    total_time = 0.0
    lang_ok = 0
    asked = 0

    mode_name = "manual (language given)" if manual_language else "auto-detect"
    print("=" * 100)
    print(f"ASR EVALUATION: {mode_name.upper()} (Fair Normalization + WER)")
    print("Dataset note: short scripted clips (4–8 s); 12 of 20 are synthetic TTS voices")
    print("=" * 100)
    print(f"{'File':<24} {'True':<5} {'Pred':<5} {'Conf?':<6} {'OldCER':>7} {'NewCER':>7} {'NoDigCER':>9} {'WER':>6} {'Time(s)':>8}")
    print("-" * 100)

    for r in rows:
        path = resolve_clip_path(r["file"])
        if not path.exists():
            print(f"{path.name:<24} MISSING FILE: {r['file']}")
            continue

        target_lang = r["lang"] if manual_language else None
        t0 = time.perf_counter()
        out = transcribe_audio(path, language=target_lang, use_cache=use_cache)
        elapsed = round(time.perf_counter() - t0, 3)
        total_time += elapsed

        pred_text = out.get("text", "")
        pred_lang = out.get("language", "")
        needs_conf = bool(out.get("detection", {}).get("needs_confirmation", False))
        ref = r["reference"]

        # Calculate metrics
        ref_old = old_norm(ref)
        pred_old = old_norm(pred_text)
        old_cer = min(jiwer.cer(ref_old, pred_old), 1.0) if pred_old else 1.0

        ref_new = normalize_text_for_asr(ref, drop_digits=False)
        pred_new = normalize_text_for_asr(pred_text, drop_digits=False)
        new_cer = min(jiwer.cer(ref_new, pred_new), 1.0) if pred_new else 1.0

        ref_nodig = normalize_text_for_asr(ref, drop_digits=True)
        pred_nodig = normalize_text_for_asr(pred_text, drop_digits=True)
        nodig_cer = min(jiwer.cer(ref_nodig, pred_nodig), 1.0) if pred_nodig else 1.0

        wer = min(jiwer.wer(ref_new, pred_new), 1.0) if pred_new else 1.0

        if pred_lang == r["lang"]:
            lang_ok += 1
        if needs_conf:
            asked += 1

        rec = {
            "file": path.name,
            "lang": r["lang"],
            "pred_lang": pred_lang,
            "needs_conf": needs_conf,
            "old_cer": old_cer,
            "new_cer": new_cer,
            "nodig_cer": nodig_cer,
            "wer": wer,
            "time": elapsed,
            "ref": ref,
            "hyp": pred_text,
            "is_weak": r["lang"] in WHISPER_WEAK_LANGS,
        }
        records.append(rec)

        flag = "YES" if needs_conf else ""
        print(f"{path.name:<24} {r['lang']:<5} {pred_lang:<5} {flag:<6} {old_cer:>7.3f} {new_cer:>7.3f} {nodig_cer:>9.3f} {wer:>6.3f} {elapsed:>8.2f}")
        if new_cer > 0.35:
            print(f"   Ref: {ref}")
            print(f"   Hyp: {pred_text}")

    done = len(records)
    n = max(done, 1)

    # Grouped breakdowns
    strong_recs = [rec for rec in records if not rec["is_weak"]]
    weak_recs = [rec for rec in records if rec["is_weak"]]

    def avg(lst, key):
        return sum(x[key] for x in lst) / len(lst) if lst else 0.0

    print("=" * 100)
    print(f"OVERALL SUMMARY ({mode_name}):")
    print(f"  Clips processed:          {done}/{len(rows)}")
    print(f"  Old Average CER:          {avg(records, 'old_cer'):.3f} ({avg(records, 'old_cer')*100:.1f}%)")
    print(f"  New Average CER:          {avg(records, 'new_cer'):.3f} ({avg(records, 'new_cer')*100:.1f}%)")
    print(f"  Digits-insensitive CER:   {avg(records, 'nodig_cer'):.3f} ({avg(records, 'nodig_cer')*100:.1f}%)")
    print(f"  Average WER:              {avg(records, 'wer'):.3f} ({avg(records, 'wer')*100:.1f}%)")
    print(f"  Language Identification:  {lang_ok}/{done} ({(lang_ok / n) * 100:.1f}%)")
    print(f"  Confirmation Requested:   {asked}/{done} ({(asked / n) * 100:.1f}%)")
    print(f"  Average Time per clip:    {total_time / n:.2f} s")
    print("-" * 100)
    print(f"Whisper-strong in our tests (langs: en, hi, mr, ta, ur, ne | n={len(strong_recs)}):")
    print(f"  Old CER: {avg(strong_recs, 'old_cer'):.3f} -> New CER: {avg(strong_recs, 'new_cer'):.3f} | NoDig CER: {avg(strong_recs, 'nodig_cer'):.3f} | WER: {avg(strong_recs, 'wer'):.3f}")
    print("-" * 100)
    print(f"Whisper-weak in our tests (langs: kn, te, ml, bn, gu | n={len(weak_recs)}):")
    print(f"  Old CER: {avg(weak_recs, 'old_cer'):.3f} -> New CER: {avg(weak_recs, 'new_cer'):.3f} | NoDig CER: {avg(weak_recs, 'nodig_cer'):.3f} | WER: {avg(weak_recs, 'wer'):.3f}")
    print("=" * 100)

    return {
        "clips": done,
        "old_cer": round(avg(records, "old_cer"), 4),
        "new_cer": round(avg(records, "new_cer"), 4),
        "nodig_cer": round(avg(records, "nodig_cer"), 4),
        "wer": round(avg(records, "wer"), 4),
        "strong": {
            "count": len(strong_recs),
            "new_cer": round(avg(strong_recs, "new_cer"), 4),
            "wer": round(avg(strong_recs, "wer"), 4),
        },
        "weak": {
            "count": len(weak_recs),
            "new_cer": round(avg(weak_recs, "new_cer"), 4),
            "wer": round(avg(weak_recs, "wer"), 4),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ASR pipeline")
    parser.add_argument("--manual", action="store_true", help="Pass ground-truth language")
    parser.add_argument("--no-cache", action="store_true", help="Bypass SQLite transcript cache")
    args = parser.parse_args()

    run_evaluation(manual_language=args.manual, use_cache=not args.no_cache)


if __name__ == "__main__":
    main()
