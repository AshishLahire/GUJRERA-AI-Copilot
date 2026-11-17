"""Evaluate the RERA trust check on synthetic ads built from the mock registry.

    python scripts/eval_gujrera_trust.py              # 25 cases per kind
    python scripts/eval_gujrera_trust.py --per-kind 50

Builds its own temporary database with the default mock seed and a fixed
as-of date, so results are reproducible. Zero API calls. Writes
docs/gujrera_trust_eval.md.

Metrics:
- accuracy per case kind (verdict in the expected set)
- false alarms: genuine ads given a red verdict
- dangerous misses: problem ads given a safe verdict (verified / registered_with_warnings)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gujrera.db.repository import Principal, Repository  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import DEFAULT_AS_OF, MockConfig, generate  # noqa: E402
from gujrera.trust.checks import check_text  # noqa: E402
from gujrera.trust.samples import SAFE_VERDICTS, build_cases  # noqa: E402

OUT = ROOT / "docs" / "gujrera_trust_eval.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-kind", type=int, default=25)
    ap.add_argument("--seed", type=int, default=2016)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        engine = make_engine(f"sqlite:///{(Path(tmp) / 'eval.sqlite').as_posix()}")
        init_db(engine)
        Session = session_factory(engine)
        with Session() as s:
            generate(s, MockConfig(seed=args.seed))
        with Session() as s:
            cases = build_cases(s, as_of=DEFAULT_AS_OF, per_kind=args.per_kind)
            repo = Repository(s, Principal.anonymous())
            results = [(c, check_text(c.text, repo, as_of=DEFAULT_AS_OF).verdict) for c in cases]
        engine.dispose()

    by_kind: dict[str, list[tuple]] = defaultdict(list)
    for case, verdict in results:
        by_kind[case.kind].append((case, verdict))

    correct = sum(v in c.expected for c, v in results)
    genuine = by_kind["genuine"]
    false_alarms = [(c, v) for c, v in genuine if v not in SAFE_VERDICTS]
    problem = [(c, v) for c, v in results if c.kind not in ("genuine", "booking_over_limit")]
    misses = [(c, v) for c, v in problem if v in SAFE_VERDICTS]

    lines = [
        "# RERA trust check evaluation",
        "",
        f"Synthetic ads built from the mock registry (seed {args.seed}, as of {DEFAULT_AS_OF}). "
        "Zero API calls. Reproduce with `python scripts/eval_gujrera_trust.py`.",
        "",
        "These are template ads, so the numbers show that the checks and verdict logic work as designed. "
        "They do not measure OCR quality or performance on real-world ads; that needs a real ad set.",
        "",
        f"- **Overall: {correct}/{len(results)} correct ({100 * correct / len(results):.1f}%)**",
        f"- False alarms (genuine ad given a red verdict): **{len(false_alarms)}/{len(genuine)}**",
        f"- Dangerous misses (problem ad given a safe verdict): **{len(misses)}/{len(problem)}**",
        "",
        "| Case kind | Expected | Correct | Verdicts returned |",
        "|:--|:--|:-:|:--|",
    ]
    for kind, rows in by_kind.items():
        ok = sum(v in c.expected for c, v in rows)
        counts = ", ".join(f"{v} {n}" for v, n in Counter(v for _, v in rows).most_common())
        lines.append(f"| {kind} | {' or '.join(rows[0][0].expected)} | {ok}/{len(rows)} | {counts} |")
    wrong = [(c, v) for c, v in results if v not in c.expected]
    if wrong:
        lines += ["", "## Errors", ""]
        lines += [f"- `{c.id}` ({c.note}): expected {' or '.join(c.expected)}, got **{v}**" for c, v in wrong]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if not misses and not false_alarms else 1


if __name__ == "__main__":
    raise SystemExit(main())
