"""Evaluate the chat on 300 template-generated gold questions (100 per language).

    python scripts/eval_gujrera_chat.py

Builds its own temporary database with the default mock seed. Zero API calls.
A question passes when the reply has the expected intent, contains the expected
fact (date, count or registration number) in the question's language, cites a
record for every factual sentence, and answers in the question's language.
Writes docs/gujrera_chat_eval.md.
"""

from __future__ import annotations

import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gujrera.chat.gold import build_gold  # noqa: E402
from gujrera.chat.orchestrator import ChatState, respond  # noqa: E402
from gujrera.db.repository import Principal, Repository  # noqa: E402
from gujrera.db.session import init_db, make_engine, session_factory  # noqa: E402
from gujrera.ingest.mock_generator import MockConfig, generate  # noqa: E402

OUT = ROOT / "docs" / "gujrera_chat_eval.md"
UNCITED_OK = {"demo_note"}


def judge(q, reply: dict) -> list[str]:
    problems = []
    if reply["intent"] not in q.expect_intent:
        problems.append(f"intent {reply['intent']}")
    if reply["lang"] != q.lang:
        problems.append(f"lang {reply['lang']}")
    for fact in q.must_contain:
        if fact not in reply["text"]:
            problems.append(f"missing {fact!r}")
    if reply["intent"] in ("possession", "project_profile", "promoter_profile", "complaints"):
        # every sentence except the demo-data note must carry a citation
        uncited = [s for s in reply["sentences"][:-1] if not s["refs"]] if reply["is_mock"] else \
            [s for s in reply["sentences"] if not s["refs"]]
        if uncited:
            problems.append(f"{len(uncited)} uncited sentence(s)")
    return problems


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        engine = make_engine(f"sqlite:///{(Path(tmp) / 'eval.sqlite').as_posix()}")
        init_db(engine)
        Session = session_factory(engine)
        with Session() as s:
            generate(s, MockConfig())
        with Session() as s:
            gold = build_gold(s)
            repo = Repository(s, Principal.anonymous())
            results = []
            started = time.perf_counter()
            for q in gold:
                t0 = time.perf_counter()
                reply = respond(q.question, ChatState(), repo).to_dict()
                results.append((q, reply, judge(q, reply), time.perf_counter() - t0))
            total_s = time.perf_counter() - started
        engine.dispose()

    passed = sum(1 for _, _, p, _ in results if not p)
    by_lang: dict[str, list] = defaultdict(list)
    by_kind: dict[str, list] = defaultdict(list)
    for r in results:
        by_lang[r[0].lang].append(r)
        by_kind[r[0].kind].append(r)
    latencies = sorted(r[3] for r in results)
    p95 = latencies[int(0.95 * (len(latencies) - 1))]
    invented = [r for r in results if r[0].kind in ("not_found", "out_of_scope") and r[2]]

    lines = [
        "# Chat evaluation (gold questions)",
        "",
        f"{len(results)} template-generated questions, 100 per language, built from the mock registry. "
        "Zero API calls. Reproduce with `python scripts/eval_gujrera_chat.py`.",
        "",
        "A question passes when the reply has the expected intent, contains the expected fact in the "
        "question's language, cites a record for every factual sentence, and answers in that language. "
        "The questions come from templates, so this measures routing, matching, facts and citations, "
        "not how well the copilot handles free-form questions from real users.",
        "",
        f"- **Passed: {passed}/{len(results)} ({100 * passed / len(results):.1f}%)** (deck target: 90%+ correct and cited)",
        f"- Unknown names or off-topic questions answered as if found: **{len(invented)}**",
        f"- Latency: p95 {p95 * 1000:.0f} ms, total {total_s:.1f} s on CPU (template answers, no LLM)",
        "",
        "| Language | Passed |",
        "|:--|:-:|",
        *[f"| {lang} | {sum(1 for r in rows if not r[2])}/{len(rows)} |" for lang, rows in by_lang.items()],
        "",
        "| Question kind | Passed |",
        "|:--|:-:|",
        *[f"| {kind} | {sum(1 for r in rows if not r[2])}/{len(rows)} |" for kind, rows in by_kind.items()],
    ]
    failed = [r for r in results if r[2]]
    if failed:
        lines += ["", "## Failures", ""]
        lines += [f"- `{q.id}` {q.question!r}: {', '.join(p)}" for q, _, p, _ in failed[:60]]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
