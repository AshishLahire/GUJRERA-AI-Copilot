# GujRERA Saathi: evaluation summary

_Prototype for the AI CoE AI Innovation Challenge (GUJRERA use case). Measured 2026-11-17 on one laptop
(16 CPU threads, RTX 3070 Ti) with self-hosted models only: qwen2.5:7b-instruct (Ollama), multilingual-e5,
Whisper small, Tesseract. Zero paid API calls. Every number below can be reproduced with the script or test
named, and each links to its full report._

**How to read these numbers.** They are measured on a test registry shaped like GUJRERA's records
(projects, promoters, agents, quarterly reports, approvals, complaints, orders), with question and ad sets
built from templates. They show that the logic, the legal rules, the guards and the stack work as designed.
The PoC repeats the same evaluations on GUJRERA's own data and on real citizens' questions, ads and voices.

## Against the targets in our Stage 1 deck

| Deck commitment | Target | Measured | Report |
|:--|:-:|:-:|:--|
| Answers correct and cited (300 gold questions, 100 per language) | 90%+ | **300/300**, 0 unknown names answered as found | [chat](gujrera_chat_eval.md) |
| Complaints complete on first submission | 80%+ | **90/90** (gu, hi, en; 8 turns on average) | [complaints](gujrera_complaints_eval.md) |
| 100+ users at once, answer starts within 3 s | 3 s | **538/541 complete answers within 3 s**, 0 errors (p50 0.09 s) | [load test](gujrera_load_test.md) |
| Self-hosted, deployable on-premise | offline | **10/10 demo flows** with all outside network blocked | [offline check](gujrera_offline_check.md) |
| Promoters see only their own data; officers read-only | 0 leaks | **31/31 attempts blocked**, 0 leaks; 30/30 unsafe SQL blocked | [access](gujrera_access_eval.md), [analytics](gujrera_analytics_eval.md) |
| Speech accuracy (WER) | measured | English computer voices so far: WER 14%; right answer in 9/10 (3 direct, 6 after one "Did you mean…?" tap). **Gujarati and Hindi need real recordings.** | [voice](gujrera_voice_eval.md) |

## Core capabilities

| Capability | Test | Result |
|:--|:--|:--|
| RERA trust check (ads) | 178 ads: genuine, not registered, lapsed, wrong promoter, later possession, no number, booking > 10% | **178/178**; 0 false alarms on 50 genuine ads; 0 dangerous misses on 103 problem ads ([report](gujrera_trust_eval.md)) |
| Gujarati OCR of ad images | 3 rendered ads (unit tests) | Read at 91–94% confidence in 1–2 s, right verdicts. Real photos not yet tested. |
| Project and promoter answers | 300 gold questions | 300/300; most answered by rules in milliseconds, the rest by the local LLM in a few seconds ([report](gujrera_chat_eval.md)) |
| Law questions (RERA Act, Gujarat Rules) | 25 questions + 7 off-topic | Right provision in top 3: **25/25** (first: 22/25); off-topic "not found": 7/7 ([report](gujrera_legal_eval.md)) |
| Complaint filing and tracking | 90 simulated conversations | 90/90 complete with the right project, category and form ([report](gujrera_complaints_eval.md)) |
| Officer analytics | 27 questions, 30 attacks, 126 district checks | 27/27 routed right, 30/30 attacks blocked, district scope held 126/126 ([report](gujrera_analytics_eval.md)) |
| Answers in English under Gujarati/Hindi | Same records, same sources | Built from the same templates (not machine translation); no second model call |

## Features built for the PoC

Each one is a working page in the dashboard and a chat answer, built on the same registry, the same legal
texts and the same access rules. The law each rests on was checked against the indexed Act, Rules and model
agreement, not from memory.

| # | Feature | Who | What it does | Measured / checked |
|:-:|:--|:--|:--|:--|
| 1 | Delay interest and refund calculator | Buyers | Interest for late possession or refund with interest, at the agreement rate or SBI MCLR + 2% (Section 18; Rules 16, 17) | Hand-checked: ₹40 lakh × 10.95% × 144 days = ₹1,72,800; refund of ₹40 lakh paid in two parts = ₹49,31,800 due in 45 days. 16 tests |
| 2 | Project risk early warning | Officers | 0–100 score from named signals (pace, projected finish, missing quarterly reports, extensions, registration ending, approvals, complaints, promoter's record), each with its reason and source | 74 ongoing projects: 8 high, 23 medium, 43 low. District officers see only their district. 6 tests |
| 3 | Unregistered-project watch | Buyers → officers | A failed ad check can be reported; reports are grouped into cases (Section 3 unregistered, lapsed, Section 12 misleading) with phones, websites, "pay to account" and evidence; officers move cases to notice and closure | 41 reports in 22 cases; the server re-checks every report, the same ad counts once, the reporter's name and number are not stored. 7 tests |
| 4 | Before-you-buy report (PDF) | Buyers | One-page cited report: registration, dates, progress chart, approvals, complaint counts, orders and compliance, promoter's record, questions to ask, buyer's rights | Prints to a clean 2-page A4 PDF with correct Gujarati (checked with Edge). Complaints as counts only. 4 tests |
| 5 | Complaint desk | Officers | Open complaints ranked against the 60-day disposal period (Section 29(4)) with reasons; group hearings; a hearing brief with sections, precedents and points to put; status updates that the buyer's tracking shows | 131 open complaints, 104 past 60 days; 27 projects with several complaints to hear together. 5 tests |
| 6 | Order tracking in plain language | Buyers, officers | What an order directs, by when, whether it was done; if not, what the buyer can do (Section 40 recovery, Section 63 penalty); appeal route for dismissals (Section 44); officers' list of orders to enforce | 105 orders tracked: 60 complied, 27 overdue, 8 partly, 8 in recovery. 5 tests |
| 7 | Quarterly report assistant | Promoters | Drafts the next report from the last one and checks it before filing: completion, bookings, 70% in the project account and withdrawals in step with construction (Sections 11, 4(2)(l)(D)), pace vs registered date (Section 6) | Errors block filing; a filed report updates the registry, the risk score and the reports. 4 tests |
| 8 | Project watch alerts | Buyers | Follow a project; alerts when a quarterly report is filed (red if completion fell) or missed, an extension or order is issued, an order is overdue, the registration is ending, or complaints come in; unread bell; SMS/WhatsApp hand-off | Alerts built from the registry's dated records, each cited; digest script shows what each buyer would receive in their language. 4 tests |
| 9 | Agreement-for-sale checker | Buyers | Compares a draft agreement with the model agreement in the Gujarat RERA Rules (Annexure A) and the Act: 14 checks from carpet area to the right to complain, each with the sentence, the clause and what to ask | One-sided sample: 11 problems, 2 to check; fair sample: 13/13 in order. PDFs read page by page; uploads deleted after reading. 18 tests |

Automated tests: `pytest tests/test_gujrera_*.py`: **285 passed**.

## System checks

| Check | Result |
|:--|:--|
| Access control | 31 cross-tenant attempts through the API: 31/31 blocked, no data from another user in any reply ([report](gujrera_access_eval.md)) |
| Offline operation | All 10 demo flows worked with every outside connection blocked and the local LLM on; 0 outside connections attempted ([report](gujrera_offline_check.md)) |
| Load | 100 users reading between questions: 538/541 complete answers within 3 s, 0 errors (p50 0.09 s). No-pause stress: 0 errors, 50% within 3 s. Questions that need the LLM: p50 4.7 s on one laptop GPU ([report](gujrera_load_test.md)) |

## What this testing found and fixed

- **Law answers failed without internet.** The embedding model and Whisper contacted huggingface.co on every
  start-up even when cached. Both now load from the local copy (found by the offline check).
- **The server failed under 100 users.** The first load test had 165 errors: "database is locked" and slow LLM
  questions holding every worker. Audit rows commit at once, SQLite runs in WAL mode, larger pools. After: 0 errors.
- **A request that saves data and then logs an audit row locked itself up.** Audit rows now join the request's
  own transaction when it has already written.
- **About 70 semi-transparent colour styles produced nothing.** The sticky header was see-through and several
  markers were invisible; one fix in the colour setup made all of them work.
- **Uploaded PDFs could not be deleted on Windows.** The PDF library kept them open; buyers' agreements would
  have stayed on disk. Fixed and checked.
- **Misheard names.** Whisper writes Gujarati names as they sound ("Mongol arcade"); "Did you mean…?" now
  compares how names sound (English voice: right answer in 2/10 clips before, 9/10 after).
- **Smaller wording and matching fixes:** "owe" matched inside "Towers"; "interest for delay" without a project
  name went unanswered; a complaint's new timeline step showed only after reload; "Rs." was read as a sentence end.

## Known limits (honest answers for the jury)

| Limit | Why | Plan |
|:--|:--|:--|
| Test registry and template questions | No GUJRERA data access yet | Run the same evaluations on registry exports and real questions in PoC phase 1 |
| Gujarati / Hindi voice not measured | No recordings yet; Whisper small is weak in Gujarati | 30-clip sheet ready (`docs/gujrera_voice_recording_sheet.md`); IndicConformer in the PoC. The app shows the transcript for checking before sending. |
| Agreement checks read English wording | Gujarati agreements need the same rules in Gujarati | Add Gujarati wording rules in the PoC |
| Order deadlines are standard periods | The prototype uses a standard number of days per kind of direction | Read the deadline from each order's text in the PoC |
| Risk weights are a starting point | No history of which projects actually stalled | Calibrate on GUJRERA's history; add the project-account (escrow) signal |
| SMS/WhatsApp alerts | No phone numbers stored in the prototype | GUJRERA's gateway plugs into the Notifier hand-off |
| LLM questions queue on one GPU | A minority of questions need the LLM; under heavy load they wait | Stream answers; serve the model with vLLM on a GPU server |
| One API process | Chat state is in memory | Shared store (Redis/Postgres), then several processes |
| IndicTrans2, IndicConformer, AksharDrishti not in the prototype | Time; IndicConformer needs a gated download | Native-language templates, Whisper and Tesseract stand in; all three are in the PoC plan |
| Real ad photos | Only clean rendered ads tested | Collect 20–40 real ads and hoardings |

## Before a live demo

1. Start Ollama and the API, then ask one law question and one free-form question to load the models
   (the first law question after start-up takes about a minute; afterwards a few seconds).
2. Use typed questions for Gujarati; voice works best in English for now.
3. Demo logins (password `gujrera-demo`): buyer `citizen_01`, promoter `dev_002`, officers `officer_state`
   (all districts) and `officer_surat`.
4. A short route through the features: Overview → Ask Saathi (Gujarati possession question) → Before-you-buy
   report (save as PDF, watch the project) → Interest calculator → Check an ad (report it) → Agreement checker
   (one-sided sample) → as `officer_state`: Complaint desk, Risk watch, Ad enforcement → as `dev_002`:
   Quarterly reports.
