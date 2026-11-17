"""Build data/index/ground_truth.json for the claim-level ground-truth check (no API calls).

    python scripts/build_ground_truth.py
"""

from __future__ import annotations

from factcheck.retrieval.ground_truth import GROUND_TRUTH_PATH, build_and_save

if __name__ == "__main__":
    counts = build_and_save()
    print(f"Wrote {sum(counts.values())} records to {GROUND_TRUTH_PATH}: {counts}")
