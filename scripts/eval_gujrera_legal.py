"""Evaluate legal retrieval on gold law questions, and optionally the model's pick and its summaries.

    python scripts/eval_gujrera_legal.py           # search only, no model
    python scripts/eval_gujrera_legal.py --rerank  # also let the local model pick the answering provision
    python scripts/eval_gujrera_legal.py --llm     # also generate the summaries (implies --rerank)

Two sets: the main set (English questions with Gujarati and Hindi versions, plus off-topic questions) and a
held-out set written in buyers' own words after search was tuned. Needs the legal index
(scripts/build_gujrera_legal_index.py). Writes docs/gujrera_legal_eval.md.
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
from gujrera.legal.gold import LEGAL_GOLD, LEGAL_HELD_OUT  # noqa: E402
from gujrera.legal.search import default_index  # noqa: E402

OUT = ROOT / "docs" / "gujrera_legal_eval.md"


def _rank(hits, expected) -> int | None:
    accepted = expected if isinstance(expected, list) else [expected]
    got = [(h.chunk["kind"], h.chunk["number"]) for h in hits]
    return next((i + 1 for i, k in enumerate(got) if k in accepted), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("--llm", action="store_true")
    args = ap.parse_args()
    rerank_on = args.rerank or args.llm
    index = default_index()
    if index is None:
        print("Legal index missing: run scripts/build_gujrera_legal_index.py")
        return 1
    if rerank_on:
        from gujrera.chat.llm import ollama_generate
        from gujrera.legal.rerank import rerank

    rows = []  # (set, lang, question, expected, search rank, rerank rank, got, summary)
    times = []
    for set_name, gold in (("main", LEGAL_GOLD), ("held-out", LEGAL_HELD_OUT)):
        for lang, question, expected in gold:
            hits = index.search(question, k=5)
            if expected is None:
                rows.append((set_name, lang, question, None, not hits, not hits, [], None))
                continue
            r_search = _rank(hits[:3], expected)
            r_pick = None
            if rerank_on:
                t0 = time.perf_counter()
                r_pick = _rank(rerank(question, hits, ollama_generate)[:3], expected)
                times.append(time.perf_counter() - t0)
            summary = None
            if args.llm:
                t0 = time.perf_counter()
                a = answer(question, lang, use_llm=True)
                summary = (a.card or {}).get("summary_by"), time.perf_counter() - t0
            rows.append((set_name, lang, question, expected, r_search, r_pick,
                         [(h.chunk["kind"], h.chunk["number"]) for h in hits[:3]], summary))

    def top(rs, i, n):
        return sum(1 for r in rs if r[i] is not None and r[i] is not True and r[i] <= n)

    lines = ["# Legal RAG evaluation", "",
             "Law questions with a known answering provision, over the RERA Act 2016 (OCR of the GUJRERA scan) and the "
             "Gujarat RERA General Rules 2017. The main set has English questions with Gujarati and Hindi versions; the "
             "held-out set was written in buyers' own words after search was tuned. Reproduce with "
             f"`python scripts/eval_gujrera_legal.py{' --rerank' if rerank_on else ''}`.", ""]
    for set_name in ("main", "held-out"):
        answerable = [r for r in rows if r[0] == set_name and r[3] is not None]
        offtopic = [r for r in rows if r[0] == set_name and r[3] is None]
        by_lang = defaultdict(list)
        for r in answerable:
            by_lang[r[1]].append(r)
        lines += [f"## {set_name.capitalize()} set ({len(answerable)} questions)", ""]
        head = "| Language | Search: first | Search: top 3 |" + (" With the model's pick: first | top 3 |" if rerank_on else "")
        lines += [head, "|:--|:-:|:-:|" + (":-:|:-:|" if rerank_on else "")]
        for k, v in list(by_lang.items()) + [("all", answerable)]:
            row = f"| {k} | {top(v, 4, 1)}/{len(v)} | {top(v, 4, 3)}/{len(v)} |"
            if rerank_on:
                row += f" {top(v, 5, 1)}/{len(v)} | {top(v, 5, 3)}/{len(v)} |"
            lines.append(row)
        if offtopic:
            lines += ["", f"- Off-topic questions correctly answered \"not found\": **{sum(r[4] for r in offtopic)}/{len(offtopic)}**"]
        lines.append("")
    if rerank_on and times:
        t = sorted(times)
        lines += [f"The model's pick takes {t[len(t) // 2]:.2f} s at the median ({t[-1]:.2f} s at most) with "
                  "qwen2.5:7b-instruct on the GPU; it reorders the top 5 found by search and never adds a provision.", ""]
    if args.llm:
        llm_rows = [r for r in rows if r[7]]
        kept = sum(1 for r in llm_rows if r[7][0] == "llm")
        avg = sum(r[7][1] for r in llm_rows) / max(len(llm_rows), 1)
        lines += [f"- Summaries that passed the citation guard: **{kept}/{len(llm_rows)}** "
                  f"(the rest quote the provision); average {avg:.1f} s per answer", ""]
    col = 5 if rerank_on else 4
    misses = [r for r in rows if r[3] is not None and r[col] != 1]
    if misses:
        lines += ["## Not ranked first" + (" (with the model's pick)" if rerank_on else ""), ""]
        lines += [f"- ({r[0]}, {r[1]}) {r[2]}: expected {r[3]}, search gave {r[6]}" for r in misses]
        lines.append("")
    lines += ["Known limitation: 10 of the Act's 92 section headings could not be read from the scan "
              "(e.g. sections 21, 22, 27, 44); their text is indexed under the preceding section."]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
