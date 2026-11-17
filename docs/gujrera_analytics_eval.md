# Officer analytics evaluation

Zero API calls unless `--llm` is passed. Reproduce with `python scripts/eval_gujrera_analytics.py`.

- Questions routed correctly (report, or "no standard report" → LLM): **27/27** across Gujarati, Hindi and English
- Questions answered by the wrong standard report: **0**
- Unsafe queries blocked by the guard: **30/30** (writes, schema changes, stacked statements, private tables, subquery/UNION/CTE leaks, qualified names, PRAGMA/ATTACH, file and extension functions)
- District scope held for every report and every district officer: **126/126**
- Standard report latency: p95 2.6 ms (read-only SQLite, CPU)

The LLM path (questions no standard report covers) was not run; pass `--llm`. With the installed thinking model `qwen3-vl:4b` one query takes about 30 s; a non-thinking SQL model is needed for interactive use.
