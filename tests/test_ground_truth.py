"""Claim-level ground-truth check (ported from members_4_5) and its effect on the Stage 5 verdict."""

from __future__ import annotations

from factcheck.decide import decide_verdict
from factcheck.retrieval.ground_truth import GroundTruth, build_records, tokenize
from factcheck.schemas import ForensicResult, GroundTruthResult, RetrievalResult

RECORDS = [
    {
        "id": "FN-1",
        "verdict": "debunked",
        "kind": "notice",
        "claim": "Under PM Mudra Yojana a loan of Rs 5,00,000 is approved; pay a processing fee of Rs 2,100.",
        "official_fact": "MUDRA does not lend directly to individuals.",
        "issuer_id": "MUDRA",
        "reference_link": "https://pib.gov.in/x",
        "notice_ids": ["FN-1"],
    },
    {
        "id": "NAR-1:pattern",
        "verdict": "debunked",
        "kind": "pattern",
        "claim": "Free laptop scheme for all students announced by the Ministry of Education.",
        "official_fact": "No such scheme exists.",
        "issuer_id": "MOE",
        "reference_link": "https://pib.gov.in/y",
        "notice_ids": ["FN-2"],
    },
    {
        "id": "OFF-1",
        "verdict": "official",
        "kind": "official",
        "claim": "CBSE Class X board examinations 2027 date sheet released.",
        "issuer_id": "CBSE",
        "reference_no": "Acad-65/2026",
        "reference_link": "https://cbse.gov.in/z",
    },
]


def _low() -> ForensicResult:
    return ForensicResult(risk_level="low", risk_score=0)


def test_tokenize_normalises_rupees_and_months() -> None:
    assert "rupee2000" in tokenize("Pay ₹2,000 by November")
    assert "rupee2000" in tokenize("Pay Rs. 2000")
    assert "november" not in tokenize("Pay ₹2,000 by November")


def test_match_debunked_official_and_unrelated() -> None:
    gt = GroundTruth(RECORDS)
    deb = gt.match("PM Mudra Yojana loan of ₹5,00,000 approved, pay processing fee of ₹2,100.", "MUDRA")
    assert deb.status == "debunked" and deb.best is not None
    assert deb.best.record_id == "FN-1"
    assert deb.best.official_fact == "MUDRA does not lend directly to individuals."

    off = gt.match("CBSE releases Class X board examinations 2027 date sheet.", "CBSE")
    assert off.status == "official" and off.best is not None and off.best.record_id == "OFF-1"

    none = gt.match("ISRO will launch a new weather satellite next month.")
    assert none.status == "no_record" and none.best is None

    assert gt.match(None).status == "skipped"


def test_leave_one_out_drops_records_whose_only_evidence_is_excluded() -> None:
    gt = GroundTruth(RECORDS)
    claim = "Ministry of Education announces free laptop scheme for all students."
    assert gt.match(claim).status == "debunked"
    assert gt.match(claim, exclude_notice_id="FN-2").status == "no_record"


def test_build_records_from_datasets_has_citable_records() -> None:
    records = build_records(extra_path=None)
    kinds = {r["kind"] for r in records}
    assert {"notice", "pattern", "official"} <= kinds
    assert all(r.get("reference_link") for r in records if r["kind"] == "pattern")
    assert sum(r["kind"] == "notice" for r in records) == 90


def test_verdict_uses_ground_truth_debunk_when_retrieval_has_no_strong_match() -> None:
    gt = GroundTruth(RECORDS).match("PM Mudra loan of ₹5,00,000 approved; pay processing fee of ₹2,100.", "MUDRA")
    verdict = decide_verdict(_low(), RetrievalResult(ground_truth=gt))
    assert verdict.verdict_key == "debunked"
    assert verdict.decided_by == "ground_truth"
    assert verdict.official_clarification == "MUDRA does not lend directly to individuals."
    assert verdict.evidence_links[0].url == "https://pib.gov.in/x"


def test_verdict_uses_ground_truth_official_and_respects_forensics() -> None:
    gt = GroundTruth(RECORDS).match("CBSE releases Class X board examinations 2027 date sheet.", "CBSE")
    green = decide_verdict(_low(), RetrievalResult(ground_truth=gt))
    assert green.verdict_key == "matches_official" and green.decided_by == "ground_truth"
    altered = decide_verdict(ForensicResult(risk_level="high", risk_score=80), RetrievalResult(ground_truth=gt))
    assert altered.verdict_key == "altered_official_copy"


def test_verdict_unchanged_without_ground_truth() -> None:
    verdict = decide_verdict(_low(), RetrievalResult(ground_truth=GroundTruthResult(status="no_record")))
    assert verdict.verdict_key == "unverified"


def test_leakage_exclusion_excludes_by_notice_id_post_id_and_url() -> None:
    records = [
        {
            "id": "FN-TG-01999",
            "verdict": "debunked",
            "kind": "notice",
            "claim": "Railway Board letter regarding payment of Productivity Linked Bonus for FY 2025-26.",
            "official_fact": "The letter is fake.",
            "issuer_id": "RRB",
            "reference_link": "https://t.me/PIB_FactCheck/1999",
            "notice_ids": ["FN-TG-01999"],
        },
        {
            "id": "NAR-POLICY-ORDER:pattern",
            "verdict": "debunked",
            "kind": "pattern",
            "claim": "Railway Board sanctions Productivity Linked Bonus for employees.",
            "official_fact": "No such order has been issued.",
            "issuer_id": "RRB",
            "reference_link": "https://t.me/PIB_FactCheck/1999",
            "notice_ids": ["FN-PDF-0069", "FN-TG-01999"],
        },
    ]
    gt = GroundTruth(records)
    claim = "Railway Board sanctions Productivity Linked Bonus for employees."

    # Without exclude: matches debunked
    res_normal = gt.match(claim)
    assert res_normal.status == "debunked"

    # With exclude_notice_id='FN-TG-01999': drops both notice and pattern sharing post 1999 / URL
    res_ex_id = gt.match(claim, exclude_notice_id="FN-TG-01999")
    assert res_ex_id.status == "no_record"

    # With exclude_url='https://t.me/PIB_FactCheck/1999': drops both
    res_ex_url = gt.match(claim, exclude_url="https://t.me/PIB_FactCheck/1999")
    assert res_ex_url.status == "no_record"

    # With exclude_post_id=1999: drops both
    res_ex_post = gt.match(claim, exclude_post_id=1999)
    assert res_ex_post.status == "no_record"


def test_fn_tg_01999_not_red_when_simulate_toggle_on() -> None:
    from factcheck.pipeline import run_document_pipeline
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[1]
    demo_img = repo_root / "data" / "demo" / "images" / "FN-TG-01999.jpg"
    assert demo_img.exists()

    # Normal mode: caught as debunked (red)
    normal_run = run_document_pipeline(demo_img, allow_fallback=False, exclude_debunk_id=None)
    assert normal_run.verdict.color == "red"

    # Simulate unseen forgery toggle ON: must NOT be red
    sim_run = run_document_pipeline(demo_img, allow_fallback=False, exclude_debunk_id="FN-TG-01999")
    assert sim_run.verdict.color != "red"
    assert sim_run.verdict.verdict_key == "unverified"


def test_fn_tg_00130_debunked_via_sister_with_toggle_on() -> None:
    from factcheck.pipeline import run_document_pipeline
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[1]
    demo_img = repo_root / "data" / "demo" / "images" / "FN-TG-00130.jpg"
    assert demo_img.exists()

    sim_run = run_document_pipeline(demo_img, allow_fallback=False, exclude_debunk_id="FN-TG-00130")
    assert sim_run.verdict.color == "red"
    assert sim_run.verdict.verdict_key == "debunked"
    assert len(sim_run.matches.debunks) > 0
    assert sim_run.matches.debunks[0].doc_id == "TG-0107"
