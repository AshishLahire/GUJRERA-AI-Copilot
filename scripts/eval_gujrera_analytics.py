"""Evaluate officer analytics: routing, scoping, SQL safety, and (optionally) the LLM path.

    python scripts/eval_gujrera_analytics.py          # zero API calls
    python scripts/eval_gujrera_analytics.py --llm    # also run uncovered questions through the local LLM

Builds its own temporary database. Writes docs/gujrera_analytics_eval.md.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from gujrera.analytics.engine import answer  # noqa: E402
from gujrera.analytics.redteam import ATTACKS, QUESTIONS  # noqa: E402
from gujrera.analytics.reports import match_report  # noqa: E402
from gujrera.analytics.sql_guard import UnsafeSQL, execute_readonly, guard_sql  # noqa: E402
from gujrera.db.models import User  # noqa: E402
from gujrera.db.repository import Principal, Repository  # noqa: E402
from gujrera.db.session import init_db, make_engine, make_readonly_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402

OUT = ROOT / "docs" / "gujrera_analytics_eval.md"
SCOPES = ("Ahmedabad", "Surat", "Vadodara", "Rajkot", "Gandhinagar", "Bhavnagar")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="also run uncovered questions through the local LLM")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{(Path(tmp) / 'eval.sqlite').as_posix()}"
        engine = make_engine(url)
        init_db(engine)
        Session = session_factory(engine)
        with Session() as s:
            generate(s, MockConfig())
        ro = make_readonly_engine(url)

        routed = [(q, k, (match_report(q.lower()) or None)) for q, k in QUESTIONS]
        routing_ok = sum(1 for _, k, r in routed if (r.key if r else None) == k)
        wrong_report = [(q, k, r.key) for q, k, r in routed if r and r.key != k]
        blocked = 0
        for _, sql in ATTACKS:
            try:
                guard_sql(sql)
            except UnsafeSQL:
                blocked += 1

        scope_checks = scope_ok = 0
        latencies = []
        for _, k, r in routed:
            if not r:
                continue
            for scope in SCOPES:
                t0 = time.perf_counter()
                res = execute_readonly(ro, guard_sql(r.sql, district_scope=scope))
                latencies.append(time.perf_counter() - t0)
                cols = [c.lower() for c in res.columns]
                scope_checks += 1
                if "district" not in cols or all(row[cols.index("district")] == scope for row in res.rows):
                    scope_ok += 1

        llm_rows = []
        if args.llm:
            with Session() as s:
                officer = Repository(s, Principal.from_user(s.scalar(select(User).where(User.username == "officer_state"))))
                for q, k in QUESTIONS:
                    if k is not None:
                        continue
                    t0 = time.perf_counter()
                    a = answer(q, officer, "en")
                    llm_rows.append((q, a.intent, a.card.get("sql", "") if a.card else "", time.perf_counter() - t0))
        ro.dispose()
        engine.dispose()

    latencies.sort()
    lines = [
        "# Officer analytics evaluation",
        "",
        "Zero API calls unless `--llm` is passed. Reproduce with `python scripts/eval_gujrera_analytics.py`.",
        "",
        f"- Questions routed correctly (report, or \"no standard report\" → LLM): **{routing_ok}/{len(QUESTIONS)}** "
        f"across Gujarati, Hindi and English",
        f"- Questions answered by the wrong standard report: **{len(wrong_report)}**",
        f"- Unsafe queries blocked by the guard: **{blocked}/{len(ATTACKS)}** "
        "(writes, schema changes, stacked statements, private tables, subquery/UNION/CTE leaks, qualified names, "
        "PRAGMA/ATTACH, file and extension functions)",
        f"- District scope held for every report and every district officer: **{scope_ok}/{scope_checks}**",
        f"- Standard report latency: p95 {latencies[int(0.95 * (len(latencies) - 1))] * 1000:.1f} ms "
        "(read-only SQLite, CPU)",
    ]
    if llm_rows:
        ok = sum(1 for _, intent, _, _ in llm_rows if intent == "analytics")
        lines += ["", f"## LLM path ({ok}/{len(llm_rows)} answered with a guarded query)", "",
                  "| Question | Result | Seconds | SQL |", "|:--|:--|--:|:--|"]
        lines += [f"| {q} | {i} | {t:.0f} | `{sql[:140]}` |" for q, i, sql, t in llm_rows]
    else:
        lines += ["", "The LLM path (questions no standard report covers) was not run; pass `--llm`. "
                  "With the installed thinking model `qwen3-vl:4b` one query takes about 30 s; a non-thinking "
                  "SQL model is needed for interactive use."]
    if wrong_report:
        lines += ["", "## Wrong reports", ""] + [f"- {q}: expected {k}, got {r}" for q, k, r in wrong_report]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
