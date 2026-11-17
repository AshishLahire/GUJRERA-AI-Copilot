# GujRERA Saathi: evaluation summary

_Prototype for the AI CoE AI Innovation Challenge (GUJRERA use case). Measured 2026-11-17 on one laptop
(16 CPU threads, RTX 3070 Ti) with self-hosted models only: qwen2.5:7b-instruct (Ollama), multilingual-e5,
Whisper small, Tesseract. Zero paid API calls. Every number below can be reproduced with the script named,
and each links to its full report._

**Read this first.** The registry, complaints and accounts are **mock data** (labelled MOCK / "(Demo)"),
generated to look like GUJRERA records. Most question and ad sets come from templates. So these numbers
show that the logic, the guards and the stack work as designed. They do not yet measure real citizens'
free-form questions, real photographed ads or real voices; those come with GUJRERA data in the PoC.

## Against the targets in our Stage 1 deck

| Deck commitment | Target | Measured | Report |
|:--|:-:|:-:|:--|
| Answers correct and cited (300 gold questions, 100 per language) | 90%+ | **300/300**, 0 unknown names answered as found | [chat](gujrera_chat_eval.md) |
| Complaints complete on first submission | 80%+ | **90/90** (gu, hi, en; 8 turns on average) | [complaints](gujrera_complaints_eval.md) |
| 100+ users at once, answer starts within 3 s | 3 s | **538/541 complete answers within 3 s**, 0 errors (p50 0.07 s) | [load test](gujrera_load_test.md) |
| Self-hosted, deployable on-premise | offline | **10/10 demo flows** with all outside network blocked | [offline check](gujrera_offline_check.md) |
| Promoters see only their own data; officers read-only | 0 leaks | **31/31 attempts blocked**, 0 leaks; 30/30 unsafe SQL blocked | [access](gujrera_access_eval.md), [analytics](gujrera_analytics_eval.md) |
| Speech accuracy (WER) | measured | English computer voices only so far: WER 14%; right answer in 9/10 (3 direct, 6 after one "Did you mean…?" tap). **Gujarati and Hindi need real recordings.** | [voice](gujrera_voice_eval.md) |

## By capability

| Capability | Test | Result |
|:--|:--|:--|
| RERA trust check (ads) | 178 ads: genuine, not registered, lapsed, wrong promoter, later possession, no number, booking > 10% | **178/178**; 0 false alarms on 50 genuine ads; 0 dangerous misses on 103 problem ads ([report](gujrera_trust_eval.md)) |
| Gujarati OCR of ad images | 3 rendered ads (unit tests) | Read at 91–94% confidence in 1–2 s, right verdicts. Real photos not yet tested. |
| Project and promoter answers | 300 gold questions | 300/300; 259 answered by rules (p95 60 ms), 41 by the local LLM (p95 3.7 s) ([report](gujrera_chat_eval.md)) |
| Law questions (RERA Act, Gujarat Rules) | 25 questions + 7 off-topic | Right provision in top 3: **25/25** (first: 22/25); off-topic "not found": 7/7 ([report](gujrera_legal_eval.md)) |
| Complaint filing and tracking | 90 simulated conversations | 90/90 complete with the right project, category and form ([report](gujrera_complaints_eval.md)) |
| Officer analytics | 27 questions, 30 attacks, 126 district checks | 27/27 routed right, 30/30 attacks blocked, district scope held 126/126, p95 2.6 ms ([report](gujrera_analytics_eval.md)) |
| Access control | 31 cross-tenant attempts via the API | 31/31 blocked, no data from another user in any reply ([report](gujrera_access_eval.md)) |
| Offline operation | All demo flows, outside network blocked | 10/10 worked; 0 outside connections ([report](gujrera_offline_check.md)) |
| Load | 100 users at once | Realistic use: 538/541 within 3 s, 0 errors. No-pause stress: 0 errors, 53% within 3 s ([report](gujrera_load_test.md)) |
| Automated tests | `pytest tests/test_gujrera_*.py` | 213 passed |

## What this testing found and fixed

- **Law answers failed without internet.** The embedding model asked huggingface.co a question on every
  start-up even when cached; Whisper did too. Both now load from the local copy (found by the offline check).
- **The server failed under 100 users.** The first load test had 165 errors and a median of 35 s:
  "database is locked", and slow LLM questions holding every worker. Audit rows now commit at once,
  SQLite runs in WAL mode, and the worker and connection pools are larger. After the fix: 0 errors.
- **Misheard names.** Whisper writes Gujarati names as they sound ("Mongol arcade" for Mangal Arcade).
  "Did you mean…?" now compares how names sound, so the right project is offered with one tap (English
  voice: right answer in 2/10 clips before, 9/10 after).
- **"Towers" read as "owe".** A project named "… Towers" that wasn't recognised got "please log in to see
  your dues". Words now match whole words only.

## Known limits (honest answers for the jury)

| Limit | Why | Plan |
|:--|:--|:--|
| Mock registry and template questions | No GUJRERA data access yet | Run the same evaluations on registry exports and real questions in PoC phase 1 |
| Gujarati / Hindi voice not measured | No recordings yet; Whisper small is weak in Gujarati | 30-clip sheet ready (`docs/gujrera_voice_recording_sheet.md`); IndicConformer in the PoC. The app shows the transcript for checking before sending. |
| LLM questions queue on one GPU | About 15% of questions need the LLM; under heavy load they wait (p50 about 10 s) | Stream answers; serve the model with vLLM on a GPU server |
| One API process | Chat state is in memory | Shared store (Redis/Postgres), then several processes |
| IndicTrans2, IndicConformer, AksharDrishti not in the prototype | Time; IndicConformer needs a gated download | Native-language templates, Whisper and Tesseract stand in; all three are in the PoC plan |
| Real ad photos | Only clean rendered ads tested | Collect 20–40 real ads and hoardings |

## Before a live demo

1. Start Ollama and the API, then ask one law question and one free-form question to load the models
   (the first law question after start-up takes about a minute; afterwards about 4 s).
2. Use typed questions for Gujarati; voice works best in English for now.
3. Demo accounts and the flows to show: `docs/GUJRERA_PLAN.md` section 12.
