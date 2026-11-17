# Curated ground-truth records

Hand-added records for the claim-level ground-truth check (`factcheck/retrieval/ground_truth.py`).
Put records inside the `[ ]` of `extra_records.json`, using REAL text and REAL links:

```json
[
  {
    "verdict": "official",
    "claim": "RBI announces <what the circular says> on <date>.",
    "issuer_id": "RBI",
    "reference_no": "<circular number>",
    "reference_link": "https://www.rbi.org.in/<real link>",
    "source": "RBI circular"
  }
]
```

`verdict` is `official` or `debunked` (`VERIFIED OFFICIAL` / `DEBUNKED` also accepted).
Records without a `reference_link` are skipped: every verdict must be citable.
Rebuild with `python scripts/build_ground_truth.py`, then restart the API.
