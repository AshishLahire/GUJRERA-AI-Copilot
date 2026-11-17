# Claim extraction & ground-truth evaluation

## Ground-truth check (offline, 90 notices + official records, no pattern records)

| Test | Result |
| :--- | ---: |
| Fake claims (gold canonical) -> debunked | 70/105 |
| Fake claims (raw English text) -> debunked | 9/15 |
| True claims (gold canonical) -> official | 15/15 |
| True claims (raw English text) -> official | 5/5 |
| Unrelated claims -> no record | 6/6 |
| **Dangerous errors** (fake -> official, true -> debunked) | **0** |

Fake similarity min/median: 0.079 / 0.449; unrelated max: 0.179.

## Issuer accuracy on PIB fake notices (mock (registry resolver on the annotated claim))

- Strict: **65/90 = 72.2%**
- Where the text names the issuer: **63/63 = 100.0%** (the fair score; elsewhere 'not stated' is the honest answer)
- Most common misses: IB->None: 5, MOP->None: 3, MOD->None: 3, INC->None: 2, TRAI->BSNL: 2, MEITY->None: 2, RRB->None: 1, MOF->None: 1

## Cross-language consistency on dataset 04 (mock (gold canonical claims; checks the scoring only))

- Texts processed: 120; no claim extracted: 0
- Same-narrative pairs: 330 (mean Jaccard 1.00); different: 330 (mean 0.03); **AUC 1.000**
- Narratives where issuer or date disagree across languages: 0

