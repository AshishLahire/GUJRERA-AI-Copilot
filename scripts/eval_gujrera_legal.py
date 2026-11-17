"""Evaluate legal retrieval (and optionally LLM summaries) on gold law questions.

    python scripts/eval_gujrera_legal.py          # retrieval only, no LLM
    python scripts/eval_gujrera_legal.py --llm    # also generate summaries with the local LLM

Needs the legal index (scripts/build_gujrera_legal_index.py). Writes docs/gujrera_legal_eval.md.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gujrera.legal.answer import answer  # noqa: E402
from gujrera.legal.gold import LEGAL_GOLD  # noqa: E402
from gujrera.legal.search import default_index  # noqa: E402

OUT = ROOT / "docs" / "gujrera_legal_eval.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()
    index = default_index()
    if index is None:
        print("Legal index missing: run scripts/build_gujrera_legal_index.py")
        return 1

    rows = []
    for lang, question, expected in LEGAL_GOLD:
        hits = index.search(question, k=3)
        got = [(h.chunk["kind"], h.chunk["number"]) for h in hits]
        if expected is None:
            ok1 = ok3 = not hits
        else:
            accepted = expected if isinstance(expected, list) else [expected]
            ok1 = bool(got) and got[0] in accepted
            ok3 = any(a in got for a in accepted)
        llm = None
        if args.llm and expected is not None:
            t0 = time.perf_counter()
            a = answer(question, lang, use_llm=True)
            llm = (a.card or {}).get("summary_by"), time.perf_counter() - t0
        rows.append((lang, question, expected, got, ok1, ok3, llm))

    answerable = [r for r in rows if r[2] is not None]
    offtopic = [r for r in rows if r[2] is None]
    by_lang = defaultdict(list)
    for r in answerable:
        by_lang[r[0]].append(r)
    lines = [
        "# Legal RAG evaluation",
        "",
        f"{len(answerable)} law questions with a known answering provision, plus {len(offtopic)} off-topic "
        "questions, over the RERA Act 2016 (OCR of the GUJRERA scan) and the Gujarat RERA General Rules 2017. "
        "Reproduce with `python scripts/eval_gujrera_legal.py`.",
        "",
        f"- Right provision ranked first: **{sum(r[4] for r in answerable)}/{len(answerable)}**",
        f"- Right provision in the top 3: **{sum(r[5] for r in answerable)}/{len(answerable)}**",
        f"- Off-topic questions correctly answered \"not found\": **{sum(r[5] for r in offtopic)}/{len(offtopic)}**",
        "",
        "| Language | Top 1 | Top 3 |",
        "|:--|:-:|:-:|",
        *[f"| {k} | {sum(r[4] for r in v)}/{len(v)} | {sum(r[5] for r in v)}/{len(v)} |" for k, v in by_lang.items()],
    ]
    if args.llm:
        llm_rows = [r for r in answerable if r[6]]
        kept = sum(1 for r in llm_rows if r[6][0] == "llm")
        avg = sum(r[6][1] for r in llm_rows) / max(len(llm_rows), 1)
        lines += ["", f"- LLM summaries that passed the citation guard: **{kept}/{len(llm_rows)}** "
                      f"(the rest fell back to quoting the provision); average {avg:.1f} s per answer"]
    misses = [r for r in rows if not r[5]]
    if misses:
        lines += ["", "## Misses", ""]
        lines += [f"- ({r[0]}) {r[1]}: expected {r[2]}, got {r[3]}" for r in misses]
    lines += ["", "Known limitation: 10 of the Act's 92 section headings could not be read from the scan "
                  "(e.g. sections 21, 22, 27, 44); their text is indexed under the preceding section."]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
