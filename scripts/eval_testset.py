"""Evaluate the held-out test set (data/testset, built by scripts/build_testset.py).

    python scripts/eval_testset.py            # cached OCR / claims only, zero API calls
    python scripts/eval_testset.py --live     # Gemini for missing OCR + claims (counts against the daily cap)

Each item runs through the same pipeline as the console (factcheck.pipeline). Every item is scored
twice:
- "with archive":   normal operation, PIB debunk archive available;
- "unseen":         debunk archive removed (forensics + official records only), i.e. a brand-new
                    fake that nobody has debunked yet.

Outcome buckets (what a newsroom desk would do with the verdict):
- flagged   debunked / likely forged / suspicious / altered copy   -> correct for fakes
- verified  matches official record                                -> correct for genuine documents
- unverified                                                       -> safe miss (no claim either way)
A fake marked "verified" or a genuine document marked "flagged" is an error; "verified" on a fake
is the dangerous one.

The OCR text of every fake is also scanned for leftover fact-check giveaways (FAKE, PIB, फर्जी...),
so a result can't come from PIB's own stamp. Writes docs/testset_eval.md and data/testset/results.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from factcheck.pipeline import decide_without_archive, run_document_pipeline

TESTSET = REPO_ROOT / "data" / "testset"
REPORT = REPO_ROOT / "docs" / "testset_eval.md"
RESULTS = TESTSET / "results.json"

LEAK_RE = re.compile(
    r"\bfake\b|fact\s*-?\s*check|\bpib\b|फ़र्ज़ी|फर्जी|फ़र्जी|not\s+(?:been\s+)?issued|#\w*fake", re.IGNORECASE
)
FLAGGED = {"debunked", "likely_forged", "suspicious_unverified", "altered_official_copy"}


def bucket(verdict_key: str) -> str:
    if verdict_key == "matches_official":
        return "verified"
    if verdict_key in FLAGGED:
        return "flagged"
    return "unverified"


def expected(label: str) -> str:
    return "verified" if label in ("real", "synthetic_clean") else "flagged"


def outcome(label: str, b: str) -> str:
    if b == "unverified":
        return "safe miss"
    if b == expected(label):
        return "correct"
    return "DANGEROUS" if b == "verified" else "false alarm"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="allow Gemini OCR / claim extraction")
    ap.add_argument("--only", default="", help="comma-separated item ids")
    a = ap.parse_args()

    items = json.loads((TESTSET / "manifest.json").read_text(encoding="utf-8"))["items"]
    if a.only:
        keep = set(a.only.split(","))
        items = [it for it in items if it["id"] in keep]

    rows = []
    for it in items:
        image = TESTSET / it["file"]
        source = TESTSET / (it["original"] if it["label"] == "real" else it["file"])
        run = run_document_pipeline(
            source, allow_fallback=a.live, synthetic=it["label"].startswith("synthetic"), image_for_visual=image
        )
        if not run.raw.valid or not run.raw.final_text.strip():
            rows.append({"id": it["id"], "label": it["label"], "status": "no_text", "engine": run.raw.engine_used,
                         "error": (run.raw.error or "")[:120]})
            print(f"{it['id']:9s} {it['label']:16s} -- no text ({run.raw.engine_used}) {(run.raw.error or '')[:80]}")
            continue
        unseen = decide_without_archive(run)
        leaks = sorted({m.group(0).lower() for m in LEAK_RE.finditer(run.cleaned_text)}) if it["label"] == "fake" else []
        row = {
            "id": it["id"],
            "label": it["label"],
            "status": "ok",
            "engine": run.raw.engine_used,
            "verdict": run.verdict.verdict_key,
            "decided_by": run.verdict.decided_by,
            "outcome": outcome(it["label"], bucket(run.verdict.verdict_key)),
            "verdict_unseen": unseen.verdict_key,
            "outcome_unseen": outcome(it["label"], bucket(unseen.verdict_key)),
            "risk": f"{run.forensics.risk_level} {run.forensics.risk_score}",
            "top_findings": [f.title for f in run.forensics.findings if f.severity != "info"][:3],
            "claim": run.claim.canonical_claim_en,
            "top_debunk": run.matches.debunks[0].doc_id if run.matches.debunks else None,
            "top_debunk_label": run.matches.debunks[0].label if run.matches.debunks else None,
            "visual": {"seal": run.visual.has_seal, "signature": run.visual.has_signature, "emblem": run.visual.has_emblem},
            "leak_terms": leaks,
        }
        rows.append(row)
        print(
            f"{it['id']:9s} {it['label']:16s} {row['verdict']:22s} {row['outcome']:11s} | unseen: "
            f"{row['verdict_unseen']:22s} {row['outcome_unseen']:11s} | risk {row['risk']}"
            + (f" | LEAK {leaks}" if leaks else "")
        )

    RESULTS.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = [r for r in rows if r["status"] == "ok"]
    lines = ["# Held-out test set evaluation", ""]
    lines.append(
        f"{len(items)} items ({Counter(it['label'] for it in items)}); evaluated: {len(ok)}; "
        f"skipped (no OCR text, run with --live): {len(rows) - len(ok)}."
    )
    lines.append("")
    lines += ["| Group | n | With PIB archive: correct / safe miss / false alarm / dangerous | Unseen: correct / safe miss / false alarm / dangerous |",
              "| :--- | ---: | :---: | :---: |"]
    for label in ("real", "fake", "synthetic_clean", "synthetic_forged"):
        g = [r for r in ok if r["label"] == label]
        if not g:
            continue
        c1, c2 = Counter(r["outcome"] for r in g), Counter(r["outcome_unseen"] for r in g)
        fmt = lambda c: f"{c['correct']} / {c['safe miss']} / {c['false alarm']} / {c['DANGEROUS']}"
        lines.append(f"| {label} | {len(g)} | {fmt(c1)} | {fmt(c2)} |")
    lines += ["", "| ID | Label | Verdict (archive) | Verdict (unseen) | Risk | Decided by | Leftover giveaways |",
              "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
    for r in rows:
        if r["status"] != "ok":
            lines.append(f"| {r['id']} | {r['label']} | not run: no OCR text | | | | |")
            continue
        lines.append(
            f"| {r['id']} | {r['label']} | {r['verdict']} ({r['outcome']}) | {r['verdict_unseen']} ({r['outcome_unseen']}) "
            f"| {r['risk']} | {r['decided_by']} | {', '.join(r['leak_terms']) or '-'} |"
        )
    lines += [
        "",
        "Correct = fake flagged or genuine verified. Safe miss = 'unverified' (the system declines to judge). "
        "Dangerous = fake verified as official. Synthetic forgeries were used to tune the text rules (in-sample).",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines[:12]))
    print(f"\nWrote {REPORT} and {RESULTS}")


if __name__ == "__main__":
    main()
