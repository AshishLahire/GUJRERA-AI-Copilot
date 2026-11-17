"""Claim-level ground-truth check (ported from members_4_5/build_db.py + matcher.py).

Stage 4 hybrid retrieval searches ~2,000 debunk posts with the raw document text. This module
answers a narrower question on the *canonical English claim* from Stage 3: "is this exact claim
already settled by a curated record?" It compares the claim with a small, citable database:

- DEBUNKED records: the 90 annotated PIB fake notices (dataset 01), one "pattern" record per fake
  narrative (dataset 04, cites the newest PIB debunk of that scam), and hand-added records.
- VERIFIED OFFICIAL records: the genuine narratives of dataset 04 and the official documents of
  dataset 02 (matched on their title), each with its real source URL.

Every record carries a reference link, and debunk records carry PIB's official clarification, so
the UI can show "what the government actually said". Scoring is TF-IDF cosine on unigrams +
bigrams (pure Python, no model), with the thresholds members_4_5 tuned on dataset 04
(0 fake->official and 0 true->debunked errors offline).
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from factcheck.schemas import GroundTruthMatch, GroundTruthResult

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "data" / "dataset"
GROUND_TRUTH_PATH = REPO_ROOT / "data" / "index" / "ground_truth.json"
EXTRA_RECORDS_PATH = REPO_ROOT / "data" / "curated" / "extra_records.json"

DEBUNK_T = 0.25  # similarity >= this to a debunked record -> debunked (unrelated text scored <= 0.18)
OFFICIAL_T = 0.35  # similarity >= this to an official record -> verified official
ISSUER_BOOST = 0.05  # small bonus when the claimed issuer equals the record's issuer
MARGIN = 0.03  # if both pass, official must beat debunked by this much

STOP = set(
    """a an the of to in on at for by with from and or is are was were be been this that these those it its as
into than then so such not no will shall has have had may can could would should about over under per via also""".split()
)
_MONTHS = set("january february march april may june july august september october november december".split())

_TAIL = re.compile(r"\s*(?:🔗|💡|📱|📧|👉|🔎|📌).*$", re.S)
_HEAD = re.compile(r"^\W*(?:FAKE\s+(?:\w+\s+)?ALERT|#?PIB\s*FACT\s*CHECK|CLAIM|CAUTION|ALERT)\W*", re.I)
_URL = re.compile(r"https?://[^\s)>\]]+")
_HASHTAG = re.compile(r"#\w+")


# ---------------------------------------------------------------- tokenising / scoring


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokenize(text: str) -> list[str]:
    """English tokens with rupee amounts and percentages normalised (₹2,000 / Rs 2000 -> rupee2000)."""
    t = (text or "").lower()
    t = re.sub(r"(?:₹|rs\.?|inr)\s*([\d,]+)", lambda m: " rupee" + m.group(1).replace(",", "") + " ", t)
    t = re.sub(r"(\d+)\s*%", r" pct\1 ", t)
    t = re.sub(r"(\d[\d,]*)", lambda m: m.group(1).replace(",", ""), t)
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", t) if w not in STOP and w not in _MONTHS]


def _features(text: str) -> list[str]:
    toks = tokenize(text)
    return toks + [a + "_" + b for a, b in zip(toks, toks[1:])]


# ---------------------------------------------------------------- building the database


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def clean_claim(s: str) -> str:
    s = _TAIL.sub("", s or "")
    s = _HASHTAG.sub("", s)
    for _ in range(3):
        s = _HEAD.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s and s[-1] not in ".!?":
        s += "."
    return s


def _split_fact(s: str | None) -> tuple[str, str | None]:
    """(official fact without contact/emoji tail, first link in it or None)."""
    s = s or ""
    m = _URL.search(s)
    link = m.group(0).rstrip(".,;") if m else None
    return re.sub(r"\s+", " ", _TAIL.sub("", s)).strip(), link


def _guess_issuer(narrative_id: str) -> str | None:
    for key in ("RBI", "CBSE", "SEBI", "PIB"):
        if key in narrative_id.upper():
            return key
    return None


def build_records(
    data_dir: Path = DATASET_DIR,
    *,
    with_patterns: bool = True,
    with_official: bool = True,
    extra_path: Path | None = EXTRA_RECORDS_PATH,
) -> list[dict[str, Any]]:
    """Assemble the ground-truth records from datasets 01, 02, 04 and curated extras."""
    notices = _load_jsonl(data_dir / "01_fake_notice_benchmark" / "notices.jsonl")
    narratives = _load_jsonl(data_dir / "04_multilingual_claims" / "narratives.jsonl")

    records: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for n in notices:
        fact, link = _split_fact(n.get("official_fact"))
        rec = {
            "id": n["notice_id"],
            "verdict": "debunked",
            "kind": "notice",
            "claim": clean_claim(n.get("claim", "")),
            "official_fact": fact,
            "issuer_id": n.get("claimed_issuer_id"),
            "narrative_id": n.get("narrative_id"),
            "date": n.get("post_date"),
            "language": n.get("language"),
            "source": n.get("source"),
            "reference_link": n.get("source_url") or link,
            "notice_ids": [n["notice_id"]],
        }
        records.append(rec)
        by_id[rec["id"]] = rec

    if with_patterns:
        for nar in narratives:
            if nar.get("verdict") != "fake":
                continue
            ids = [i for i in (nar.get("ds1_notice_ids") or []) if i in by_id]
            if not ids:
                continue  # no PIB debunk to cite
            newest = max((by_id[i] for i in ids), key=lambda r: r.get("date") or "")
            records.append(
                {
                    "id": nar["narrative_id"] + ":pattern",
                    "verdict": "debunked",
                    "kind": "pattern",
                    "claim": nar["canonical_claim_en"],
                    "official_fact": nar.get("official_fact") or newest["official_fact"],
                    "issuer_id": (nar.get("slots") or {}).get("claimed_issuer_id"),
                    "narrative_id": nar["narrative_id"],
                    "date": nar.get("last_seen") or newest.get("date"),
                    "language": "en",
                    "source": "PIB Fact Check (latest debunk of this scam pattern)",
                    "reference_link": newest["reference_link"],
                    "notice_ids": ids,
                }
            )

    if with_official:
        by_doc: dict[str, dict[str, Any]] = {}
        for nar in narratives:
            if nar.get("verdict") != "true":
                continue
            rec = {
                "id": nar["narrative_id"],
                "verdict": "official",
                "kind": "official",
                "claim": nar["canonical_claim_en"],
                "official_fact": None,
                "issuer_id": (nar.get("slots") or {}).get("claimed_issuer_id") or _guess_issuer(nar["narrative_id"]),
                "narrative_id": nar["narrative_id"],
                "reference_no": nar.get("reference_no"),
                "date": None,
                "language": "en",
                "source": "Official circular (dataset 02)",
                "reference_link": None,
            }
            records.append(rec)
            if nar.get("ds2_doc_id"):
                by_doc[nar["ds2_doc_id"]] = rec
        for d in _load_jsonl(data_dir / "02_official_source_corpus" / "documents.jsonl"):
            url = d.get("pdf_url") or d.get("source_url") or d.get("url")
            if d.get("label", "genuine") != "genuine" or not url:
                continue
            title = re.sub(r"\s+", " ", d.get("title") or "").strip()
            known = by_doc.get(d["doc_id"])
            if known:  # genuine narrative already present: attach the real link
                known["reference_link"] = url
                known["reference_no"] = known.get("reference_no") or d.get("reference_no")
                known["official_fact"] = title
                known["date"] = d.get("date_published") or d.get("date")
                continue
            records.append(
                {
                    "id": d["doc_id"],
                    "verdict": "official",
                    "kind": "official",
                    "claim": f"{d.get('issuer_id') or ''} {title}".strip(),
                    "official_fact": title,
                    "issuer_id": d.get("issuer_id"),
                    "reference_no": d.get("reference_no"),
                    "date": d.get("date_published") or d.get("date"),
                    "language": d.get("language"),
                    "source": f"{d.get('issuer') or d.get('issuer_id')} ({d.get('doc_type') or 'document'})",
                    "reference_link": url,
                }
            )

    # Hand-added real records: each needs claim, verdict (debunked|official) and reference_link.
    if extra_path is not None and extra_path.exists():
        for i, r in enumerate(json.loads(extra_path.read_text(encoding="utf-8") or "[]")):
            verdict = {"DEBUNKED": "debunked", "VERIFIED OFFICIAL": "official"}.get(r.get("verdict"), r.get("verdict"))
            if not r.get("claim") or verdict not in ("debunked", "official") or not r.get("reference_link"):
                continue
            records.append({**r, "verdict": verdict, "id": r.get("id") or f"EXTRA-{i + 1:03d}", "kind": "extra"})
    return records


def build_and_save(path: Path = GROUND_TRUTH_PATH, **kwargs: Any) -> dict[str, int]:
    records = build_records(**kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "records": records}, ensure_ascii=False, indent=1), encoding="utf-8")
    return dict(Counter(r["kind"] for r in records))


# ---------------------------------------------------------------- matching


class GroundTruth:
    """TF-IDF cosine matcher over the ground-truth records."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        docs = [Counter(_features(r["claim"])) for r in records]
        df: Counter[str] = Counter()
        for d in docs:
            df.update(d.keys())
        self._n = len(docs)
        self.idf = {t: math.log((1 + self._n) / (1 + c)) + 1 for t, c in df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, counts: Counter[str]) -> dict[str, float]:
        unseen_idf = math.log(1 + self._n) + 1
        v = {t: (1 + math.log(c)) * self.idf.get(t, unseen_idf) for t, c in counts.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def scores(
        self,
        claim: str,
        issuer_id: str | None = None,
        exclude_notice_id: str | None = None,
        exclude_url: str | None = None,
        exclude_post_id: int | None = None,
    ) -> list[tuple[float, dict[str, Any]]]:
        q = self._vec(Counter(_features(claim)))
        out = []
        for r, v in zip(self.records, self.vecs):
            if _is_excluded(r, exclude_notice_id, exclude_url, exclude_post_id):
                continue
            s = sum(w * v.get(t, 0.0) for t, w in q.items())
            if issuer_id and r.get("issuer_id") == issuer_id:
                s += ISSUER_BOOST
            out.append((min(s, 1.0), r))
        out.sort(key=lambda x: -x[0])
        return out

    def match(
        self,
        canonical_claim: str | None,
        issuer_id: str | None = None,
        *,
        top_k: int = 3,
        exclude_notice_id: str | None = None,
        exclude_url: str | None = None,
        exclude_post_id: int | None = None,
    ) -> GroundTruthResult:
        if not (canonical_claim or "").strip():
            return GroundTruthResult(status="skipped", note="Needs a canonical claim from Stage 3.")
        ranked = self.scores(
            canonical_claim or "",
            issuer_id,
            exclude_notice_id=exclude_notice_id,
            exclude_url=exclude_url,
            exclude_post_id=exclude_post_id,
        )
        best_deb = next(((s, r) for s, r in ranked if r["verdict"] == "debunked"), (0.0, None))
        best_off = next(((s, r) for s, r in ranked if r["verdict"] == "official"), (0.0, None))
        top = [_to_match(s, r) for s, r in ranked[:top_k]]

        deb_ok = best_deb[1] is not None and best_deb[0] >= DEBUNK_T
        off_ok = best_off[1] is not None and best_off[0] >= OFFICIAL_T
        if off_ok and (not deb_ok or best_off[0] >= best_deb[0] + MARGIN):
            return _result("official", best_off, top, "Claim matches a genuine official record.", len(self.records))
        if deb_ok:
            return _result("debunked", best_deb, top, "Claim matches one already debunked by PIB Fact Check.", len(self.records))
        return GroundTruthResult(
            status="no_record",
            similarity=round(max(best_deb[0], best_off[0]), 3),
            top_matches=top,
            note="No close record in the curated ground-truth set. This does NOT mean the claim is true.",
            database_size=len(self.records),
        )


def _is_excluded(
    record: dict[str, Any],
    exclude_notice_id: str | None = None,
    exclude_url: str | None = None,
    exclude_post_id: int | None = None,
) -> bool:
    """Leave-one-out: drop any record representing or citing the sample being simulated (same notice_id, post_id, or URL)."""
    if not (exclude_notice_id or exclude_url or exclude_post_id is not None):
        return False

    rec_id = record.get("id") or ""
    rec_link = record.get("reference_link") or ""
    notice_ids = record.get("notice_ids") or []

    # 1. Direct ID match
    if exclude_notice_id:
        if rec_id == exclude_notice_id:
            return True
        if notice_ids and all(i == exclude_notice_id for i in notice_ids):
            return True

    # 2. Inferred post_id (only from strict FN-TG-<digits> notice_ids)
    target_post_id = exclude_post_id
    if target_post_id is None and exclude_notice_id and exclude_notice_id.startswith("FN-TG-"):
        tail = exclude_notice_id[6:].strip()
        if tail.isdigit():
            target_post_id = int(tail)
    if target_post_id is None and exclude_url:
        m = re.search(r"t\.me/(?:PIB_FactCheck|pibfactcheck)/(\d+)(?:[/?#]|$)", exclude_url, re.I)
        if m:
            target_post_id = int(m.group(1))

    # 3. URL match
    target_urls = set()
    if exclude_url:
        target_urls.add(exclude_url.rstrip("/"))
    if target_post_id is not None:
        target_urls.add(f"https://t.me/PIB_FactCheck/{target_post_id}")
        target_urls.add(f"http://t.me/PIB_FactCheck/{target_post_id}")
        target_urls.add(f"https://t.me/pibfactcheck/{target_post_id}")
        target_urls.add(f"http://t.me/pibfactcheck/{target_post_id}")

    if rec_link:
        clean_link = rec_link.rstrip("/")
        if clean_link in target_urls:
            return True
        if exclude_url and clean_link == exclude_url.rstrip("/"):
            return True

    # 4. Post ID match (strict against PIB telegram URLs or exact record ID)
    if target_post_id is not None:
        if rec_id == f"FN-TG-{target_post_id:05d}" or rec_id == f"FN-TG-{target_post_id}":
            return True
        if re.search(rf"t\.me/(?:PIB_FactCheck|pibfactcheck)/(?:0*)?{target_post_id}(?:[/?#]|$)", rec_link, re.I):
            return True

    return False


def _is_only_evidence(record: dict[str, Any], notice_id: str) -> bool:
    """Leave-one-out: drop a record whose only supporting PIB notice is the one being simulated."""
    return _is_excluded(record, exclude_notice_id=notice_id)


def _to_match(score: float, r: dict[str, Any]) -> GroundTruthMatch:
    return GroundTruthMatch(
        record_id=r["id"],
        verdict=r["verdict"],
        kind=r.get("kind", "notice"),
        score=round(score, 3),
        claim=r.get("claim", ""),
        official_fact=r.get("official_fact"),
        issuer_id=r.get("issuer_id"),
        reference_no=r.get("reference_no"),
        reference_link=r.get("reference_link"),
        source=r.get("source"),
        date=r.get("date"),
        narrative_id=r.get("narrative_id"),
    )


def _result(
    status: str, best: tuple[float, Any], top: list[GroundTruthMatch], note: str, db_size: int
) -> GroundTruthResult:
    score, rec = best
    return GroundTruthResult(
        status=status,  # type: ignore[arg-type]
        similarity=round(score, 3),
        best=_to_match(score, rec),
        top_matches=top,
        note=note,
        database_size=db_size,
    )


@lru_cache(maxsize=1)
def get_ground_truth() -> GroundTruth:
    """Load data/index/ground_truth.json, building it from the datasets when missing."""
    if GROUND_TRUTH_PATH.exists():
        records = json.loads(GROUND_TRUTH_PATH.read_text(encoding="utf-8"))["records"]
    else:
        records = build_records()
    return GroundTruth(records)


def check_ground_truth(
    canonical_claim: str | None,
    issuer_id: str | None = None,
    *,
    exclude_notice_id: str | None = None,
    exclude_url: str | None = None,
    exclude_post_id: int | None = None,
) -> GroundTruthResult:
    try:
        return get_ground_truth().match(
            canonical_claim,
            issuer_id,
            exclude_notice_id=exclude_notice_id,
            exclude_url=exclude_url,
            exclude_post_id=exclude_post_id,
        )
    except Exception as exc:  # a broken DB file must never take down the pipeline
        return GroundTruthResult(status="skipped", note=f"Ground-truth check unavailable: {exc}")
