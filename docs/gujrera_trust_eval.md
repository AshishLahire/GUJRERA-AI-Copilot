# RERA trust check evaluation

Synthetic ads built from the mock registry (seed 2016, as of 2026-11-01). Zero API calls. Reproduce with `python scripts/eval_gujrera_trust.py`.

These are template ads, so the numbers show that the checks and verdict logic work as designed. They do not measure OCR quality or performance on real-world ads; that needs a real ad set.

- **Overall: 179/179 correct (100.0%)**
- False alarms (genuine ad given a red verdict): **0/50**
- Dangerous misses (problem ad given a safe verdict): **0/104**

| Case kind | Expected | Correct | Verdicts returned |
|:--|:--|:-:|:--|
| genuine | verified or registered_with_warnings | 50/50 | verified 33, registered_with_warnings 17 |
| not_found | not_found | 25/25 | not_found 25 |
| lapsed_or_revoked | lapsed_or_revoked | 4/4 | lapsed_or_revoked 4 |
| promoter_mismatch | mismatch | 25/25 | mismatch 25 |
| possession_late | mismatch | 25/25 | mismatch 25 |
| no_number | no_rera_number | 25/25 | no_rera_number 25 |
| booking_over_limit | registered_with_warnings | 25/25 | registered_with_warnings 25 |
