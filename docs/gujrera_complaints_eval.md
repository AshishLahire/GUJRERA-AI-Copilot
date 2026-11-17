# Complaint filing evaluation (simulated conversations)

90 scripted conversations: 6 complaint types × 3 languages × 5 projects, on the mock registry. Zero API calls. Reproduce with `python scripts/eval_gujrera_complaints.py`.

Stories come from templates, so this checks the flow and rules, not understanding of free-form real complaints.

- Submitted and complete on first submission: **90/90** (deck target: 80%+)
- Right project picked from the story: **90/90**
- Category guessed correctly from the story: **90/90**
- Right form (A, or B for compensation): **90/90**
- Stayed in the buyer's language throughout: **90/90**
- Average turns per complaint: **8.0**

| Language | Complete | Category right |
|:--|:-:|:-:|
| en | 30/30 | 30/30 |
| gu | 30/30 | 30/30 |
| hi | 30/30 | 30/30 |

| Complaint type | Complete | Category right | Form right |
|:--|:-:|:-:|:-:|
| possession_delay | 15/15 | 15/15 | 15/15 |
| refund | 15/15 | 15/15 | 15/15 |
| structural_defect | 15/15 | 15/15 | 15/15 |
| amenities_not_provided | 15/15 | 15/15 | 15/15 |
| agreement_violation | 15/15 | 15/15 | 15/15 |
| false_advertisement | 15/15 | 15/15 | 15/15 |
