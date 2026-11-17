# Access-control evaluation (cross-tenant attempts)

31 attempts to read someone else's data through the real API, as demo users, in Gujarati, Hindi and English. Zero model calls. Reproduce with `python scripts/eval_gujrera_access.py`.

An attempt passes only if it is refused and nothing belonging to someone else is in the response (cited due notices are checked against their owner, analytics rows against the officer's district, complaint replies for the other buyer's status or name).

- **Blocked with no leak: 31/31** (plan target: 0 leaks)
- Languages: en 13, gu 9, hi 9

| Attempt type | Blocked |
|:--|:-:|
| Promoter reads another promoter's dues | 6/6 |
| Promoter reads another promoter's notices | 6/6 |
| Anonymous asks for dues | 3/3 |
| Agent or buyer asks for dues | 3/3 |
| Non-officer calls analytics API | 3/3 |
| Buyer calls promoter self-service API | 1/1 |
| District officer reads other districts | 3/3 |
| Buyer tracks another buyer's complaint | 3/3 |
| Reuse another user's chat session | 1/1 |
| Forged token | 1/1 |
| Expired token | 1/1 |

<details><summary>All attempts</summary>

| # | Type | Lang | Attempt | Result | Detail |
|:-:|:--|:-:|:--|:-:|:--|
| 1 | Promoter reads another promoter's dues | en | dev_001 → Aangan Developers | ✅ | intent=access_denied |
| 2 | Promoter reads another promoter's dues | en | dev_002 → Suvarna Builders | ✅ | intent=access_denied |
| 3 | Promoter reads another promoter's notices | en | dev_001 → Aangan Developers | ✅ | intent=promoter_profile |
| 4 | Promoter reads another promoter's notices | en | dev_002 → Suvarna Builders | ✅ | intent=promoter_profile |
| 5 | Promoter reads another promoter's dues | gu | dev_002 → Suvarna Builders | ✅ | intent=access_denied |
| 6 | Promoter reads another promoter's dues | gu | dev_005 → Girnar Infra | ✅ | intent=access_denied |
| 7 | Promoter reads another promoter's notices | gu | dev_002 → Suvarna Builders | ✅ | intent=promoter_profile |
| 8 | Promoter reads another promoter's notices | gu | dev_005 → Girnar Infra | ✅ | intent=promoter_profile |
| 9 | Promoter reads another promoter's dues | hi | dev_005 → Girnar Infra | ✅ | intent=access_denied |
| 10 | Promoter reads another promoter's dues | hi | dev_006 → Kesar Builders | ✅ | intent=access_denied |
| 11 | Promoter reads another promoter's notices | hi | dev_005 → Girnar Infra | ✅ | intent=promoter_profile |
| 12 | Promoter reads another promoter's notices | hi | dev_006 → Kesar Builders | ✅ | intent=promoter_profile |
| 13 | Anonymous asks for dues | en | no login | ✅ | intent=login_required |
| 14 | Anonymous asks for dues | gu | no login | ✅ | intent=login_required |
| 15 | Anonymous asks for dues | hi | no login | ✅ | intent=login_required |
| 16 | Agent or buyer asks for dues | en | agent_001 | ✅ | intent=self_service |
| 17 | Agent or buyer asks for dues | gu | citizen_01 | ✅ | intent=login_required |
| 18 | Agent or buyer asks for dues | hi | citizen_02 | ✅ | intent=login_required |
| 19 | Non-officer calls analytics API | en | anonymous | ✅ | HTTP 403 |
| 20 | Non-officer calls analytics API | gu | citizen_03 | ✅ | HTTP 403 |
| 21 | Non-officer calls analytics API | hi | dev_001 | ✅ | HTTP 403 |
| 22 | Buyer calls promoter self-service API | en | citizen_04 | ✅ | HTTP 403 |
| 23 | District officer reads other districts | en | officer_ahmedabad (Ahmedabad) | ✅ | 1 rows, 0 outside scope |
| 24 | District officer reads other districts | gu | officer_surat (Surat) | ✅ | 1 rows, 0 outside scope |
| 25 | District officer reads other districts | hi | officer_vadodara (Vadodara) | ✅ | 1 rows, 0 outside scope |
| 26 | Buyer tracks another buyer's complaint | en | citizen_01 → DEMO-CMP-2025-00013 | ✅ | intent=complaint_tracking |
| 27 | Buyer tracks another buyer's complaint | gu | citizen_01 → DEMO-CMP-2026-00022 | ✅ | intent=complaint_tracking |
| 28 | Buyer tracks another buyer's complaint | hi | citizen_01 → DEMO-CMP-2023-00025 | ✅ | intent=complaint_tracking |
| 29 | Reuse another user's chat session | en | dev_002 uses dev_001's session | ✅ | new session issued |
| 30 | Forged token | en | signature altered | ✅ | HTTP 401 |
| 31 | Expired token | en | 8.0 h + 1 min later | ✅ | HTTP 401 |

</details>
