"""Stage 3 claim extraction + claim-level ground-truth evaluation (ported from members_4_5).

    python scripts/eval_claims.py ground-truth            # offline, zero API calls
    python scripts/eval_claims.py issuer [--live]         # issuer accuracy on the 90 PIB notices
    python scripts/eval_claims.py multilingual [--live]   # cross-language consistency on dataset 04

Without --live, `issuer` and `multilingual` use the gold annotations as a mock extractor, so they only
check the registry resolver and the scoring code (zero API calls). With --live, each text is sent through
`factcheck.claims.extract_claim` (Gemini, counted against API_DAILY_CALL_LIMIT and cached in SQLite, so
re-runs are free). Reports are written to docs/claims_eval.md.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from factcheck.claims.authority import resolve_issuer
from factcheck.retrieval.ground_truth import DATASET_DIR, GroundTruth, build_records
from factcheck.schemas import ClaimResult

DS1 = DATASET_DIR / "01_fake_notice_benchmark" / "notices.jsonl"
DS4 = DATASET_DIR / "04_multilingual_claims"
REPORT = REPO_ROOT / "docs" / "claims_eval.md"

UNRELATED = [
    "The Election Commission announces voter list revision from 1 December 2026.",
    "ISRO will launch a new weather satellite next month.",
    "The Ministry of Railways introduces a new Vande Bharat train between Pune and Nagpur.",
    "Your electricity connection will be cut tonight unless you call this number.",
    "Municipal corporation announces water supply cut in Sector 5 on Sunday.",
    "AICTE extends the last date for scholarship applications to 30 November 2026.",
]


def _load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _extract(text: str, live: bool, gold: ClaimResult) -> ClaimResult:
    if not live:
        return gold
    from factcheck.claims import extract_claim

    res = extract_claim(text, allow_cloud=True, use_cache=True)
    if not res.from_cache:
        time.sleep(1.0)  # be gentle with the free tier
    return res


# ---------------------------------------------------------------- ground truth (offline)


def eval_ground_truth() -> list[str]:
    claims = _load(DS4 / "claims.jsonl")
    # Without per-narrative pattern records, so a fake claim cannot match its own gold sentence.
    gt = GroundTruth(build_records(with_patterns=False, extra_path=None))

    def run(items: list[tuple[str, str | None]], want: str) -> tuple[int, list[float]]:
        results = [gt.match(t, i) for t, i in items]
        return sum(r.status == want for r in results), [r.similarity for r in results]

    def issuer(c: dict[str, Any]) -> str | None:
        return (c.get("slots") or {}).get("claimed_issuer_id")

    fake = [(c["canonical_claim_en"], issuer(c)) for c in claims if c["verdict"] == "fake"]
    true = [(c["canonical_claim_en"], issuer(c)) for c in claims if c["verdict"] == "true"]
    fake_en = [(c["text"], issuer(c)) for c in claims if c["verdict"] == "fake" and c["language"] == "en"]
    true_en = [(c["text"], issuer(c)) for c in claims if c["verdict"] == "true" and c["language"] == "en"]

    lines = ["## Ground-truth check (offline, 90 notices + official records, no pattern records)", ""]
    a, fake_sims = run(fake, "debunked")
    a2, _ = run(fake_en, "debunked")
    b, _ = run(true, "official")
    b2, _ = run(true_en, "official")
    c, unrel_sims = run([(u, None) for u in UNRELATED], "no_record")
    dangerous = sum(gt.match(t, i).status == "official" for t, i in fake) + sum(
        gt.match(t, i).status == "debunked" for t, i in true
    )
    lines += [
        "| Test | Result |",
        "| :--- | ---: |",
        f"| Fake claims (gold canonical) -> debunked | {a}/{len(fake)} |",
        f"| Fake claims (raw English text) -> debunked | {a2}/{len(fake_en)} |",
        f"| True claims (gold canonical) -> official | {b}/{len(true)} |",
        f"| True claims (raw English text) -> official | {b2}/{len(true_en)} |",
        f"| Unrelated claims -> no record | {c}/{len(UNRELATED)} |",
        f"| **Dangerous errors** (fake -> official, true -> debunked) | **{dangerous}** |",
        "",
        f"Fake similarity min/median: {min(fake_sims):.3f} / {statistics.median(fake_sims):.3f}; "
        f"unrelated max: {max(unrel_sims):.3f}.",
        "",
    ]
    return lines


# ---------------------------------------------------------------- issuer accuracy


def eval_issuer(live: bool, limit: int) -> list[str]:
    notices = _load(DS1)[: limit or None]
    hit = answerable = answerable_hit = 0
    misses: collections.Counter[tuple[str, str | None]] = collections.Counter()
    for n in notices:
        truth = n["claimed_issuer_id"]
        gold = ClaimResult(canonical_claim_en=n["claim"], claimed_issuer_id=resolve_issuer(n["claim"]))
        res = _extract(n["claim"], live, gold)
        got = res.claimed_issuer_id
        unnamed = truth in ("OTHER", "UNSPECIFIED")
        ok = (got is None) if unnamed else (got == truth)
        named = (not unnamed) and resolve_issuer(n["claim"]) == truth
        hit += ok
        answerable += named
        answerable_hit += named and ok
        if not ok:
            misses[(truth, got)] += 1
    mode = "live Gemini" if live else "mock (registry resolver on the annotated claim)"
    lines = [f"## Issuer accuracy on PIB fake notices ({mode})", ""]
    lines.append(f"- Strict: **{hit}/{len(notices)} = {hit / len(notices):.1%}**")
    if answerable:
        lines.append(
            f"- Where the text names the issuer: **{answerable_hit}/{answerable} = {answerable_hit / answerable:.1%}** "
            "(the fair score; elsewhere 'not stated' is the honest answer)"
        )
    if misses:
        lines.append("- Most common misses: " + ", ".join(f"{e}->{g}: {c}" for (e, g), c in misses.most_common(8)))
    lines.append("")
    return lines


# ---------------------------------------------------------------- multilingual consistency

_STOP = set("a an the of to in on for and or is are be has have been will by with from at as that this it its you your".split())


def _tokens(s: str | None) -> set[str]:
    return {t for t in re.findall(r"[a-z]+|\d+", (s or "").lower().replace(",", "")) if t not in _STOP}


def _jaccard(a: str | None, b: str | None) -> float:
    ta, tb = _tokens(a), _tokens(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def _auc(pos: list[float], neg: list[float]) -> float:
    if not pos or not neg:
        return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def eval_multilingual(live: bool, limit: int) -> list[str]:
    claims = _load(DS4 / "claims.jsonl")[: limit or None]
    pairs = _load(DS4 / "eval_pairs.jsonl")
    out: dict[str, ClaimResult] = {}
    for c in claims:
        slots = c.get("slots") or {}
        gold = ClaimResult(canonical_claim_en=c["canonical_claim_en"], claimed_issuer_id=slots.get("claimed_issuer_id"))
        out[c["claim_id"]] = _extract(c["text"], live, gold)

    groups: dict[str, list[str]] = collections.defaultdict(list)
    for c in claims:
        if out[c["claim_id"]].canonical_claim_en:
            groups[c["narrative_id"]].append(c["claim_id"])
    disagree = []
    for nid, ids in sorted(groups.items()):
        rows = [out[i] for i in ids]
        iss, iss_n = collections.Counter(r.claimed_issuer_id for r in rows).most_common(1)[0]
        dt, dt_n = collections.Counter(r.effective_date for r in rows).most_common(1)[0]
        if iss_n < len(rows) or dt_n < len(rows):
            disagree.append(f"{nid}: issuer {iss_n}/{len(rows)} ({iss}), date {dt_n}/{len(rows)} ({dt})")

    pos, neg = [], []
    for p in pairs:
        ra, rb = out.get(p["claim_a"]), out.get(p["claim_b"])
        if ra and rb and ra.canonical_claim_en and rb.canonical_claim_en:
            (pos if p["same_narrative"] else neg).append(_jaccard(ra.canonical_claim_en, rb.canonical_claim_en))
    failed = [k for k, v in out.items() if not v.canonical_claim_en]
    mode = "live Gemini" if live else "mock (gold canonical claims; checks the scoring only)"
    lines = [f"## Cross-language consistency on dataset 04 ({mode})", ""]
    lines.append(f"- Texts processed: {len(out)}; no claim extracted: {len(failed)}")
    if pos and neg:
        lines.append(
            f"- Same-narrative pairs: {len(pos)} (mean Jaccard {sum(pos) / len(pos):.2f}); "
            f"different: {len(neg)} (mean {sum(neg) / len(neg):.2f}); **AUC {_auc(pos, neg):.3f}**"
        )
    lines.append(f"- Narratives where issuer or date disagree across languages: {len(disagree)}")
    lines += [f"  - {d}" for d in disagree[:15]]
    lines.append("")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("suite", choices=["ground-truth", "issuer", "multilingual", "all"])
    ap.add_argument("--live", action="store_true", help="call Gemini via extract_claim (uses API quota)")
    ap.add_argument("--limit", type=int, default=0, help="only the first N items (cheap live trial)")
    a = ap.parse_args()

    lines = ["# Claim extraction & ground-truth evaluation", ""]
    if a.suite in ("ground-truth", "all"):
        lines += eval_ground_truth()
    if a.suite in ("issuer", "all"):
        lines += eval_issuer(a.live, a.limit)
    if a.suite in ("multilingual", "all"):
        lines += eval_multilingual(a.live, a.limit)
    text = "\n".join(lines)
    print(text)
    REPORT.write_text(text + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT}")


if __name__ == "__main__":
    main()
