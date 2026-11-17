# Pramaan — Project Target

_Last updated: 2026-11-09_

## 1. Project Target

Build **Pramaan (प्रमाण)**, a local-first verification engine that takes a suspicious Indian-language government notice, circular, letter, screenshot, PDF, pasted WhatsApp forward or voice note and returns an **evidence-backed verdict** — with the forensic cues, the matching official source or fact-check, and the scam narrative it belongs to.

What success looks like:

- A working end-to-end pipeline (ingest → extract → forensics → claim → source match → verdict → narrative) usable from a web console and an API.
- Coverage of the 22 scheduled Indian languages plus English, including Hinglish forwards and voice notes.
- Verdicts that never invent evidence: every verdict cites the official circular, PIB debunk or forensic cue it is based on.
- A fully offline mode (local models via Ollama, zero cloud calls) for air-gapped deployment.
- Measured, reproducible accuracy on offline benchmarks, so the system can serve as an India-specific verification layer alongside Fujitsu's Frontria engines.

## 2. Problem Statement

Developed for the **Nasscom × Fujitsu (FRIPL)** collaboration, **Problem Statement Area 7: multilingual claim verification and narrative detection**.

Fake government notices circulate widely in India on WhatsApp and Telegram: forged RBI, ministry and exam-board letters demanding fees, promising prizes, or announcing rules that do not exist. They are written in many Indian languages, often as images or voice notes, and reuse the same templates across years and issuers. Citizens, newsrooms and bank fraud teams have no fast way to check them:

- Official sources (gazettes, ministry circulars, PIB Fact Check) are scattered and hard to search, especially across languages.
- Forgeries are images or scans, so the text must be read before it can be checked.
- Manual fact-checking does not scale to the volume and repeats the same work for recycled scams.

Pramaan solves this by automatically reading the document, flagging manipulation cues, matching the claim against official sources and known debunks, and linking it to the scam family it comes from.

## 3. Steps to Complete

Status: ✅ done · 🟡 partial · ⬜ not started

| # | Step / Milestone | Status |
| :-: | :--- | :-: |
| 1 | Project skeleton, settings, test harness | ✅ |
| 2 | Integrate and preprocess the 6 core datasets | ✅ |
| 3 | Ingestion: file validation, PDF first page, audio intake | ✅ |
| 4 | Text extraction: hosted OCR + PDF text + Whisper voice notes | ✅ |
| 5 | Text forensics rule engine (14 rules) + PIB overlay removal | ✅ |
| 6 | Heuristic visual check (seal, signature, emblem, edit traces) | ✅ |
| 7 | Claim extraction into canonical English claims (cached) | ✅ |
| 8 | Hybrid retrieval (BM25 + multilingual-e5, RRF) + ground-truth check | ✅ |
| 9 | Verdict decision: 6 calibrated verdicts with evidence links | ✅ |
| 10 | Narrative clustering (HDBSCAN) + template-reuse graph | ✅ |
| 11 | FastAPI backend + React console, paste-text intake, report export | ✅ |
| 12 | Offline mode via Ollama (`qwen3-vl:4b`), zero cloud calls | ✅ |
| 13 | Offline benchmarks and documentation (forensics, retrieval, narratives, ASR, offline E2E) | ✅ |
| 14 | IndicConformer ASR for Dravidian / Eastern Indic voice notes | 🟡 built, disabled by default |
| 15 | Seal / emblem verification against a reference catalogue per issuer | ⬜ |
| 16 | Lightweight CNN/ViT stamp and emblem anomaly detector | ⬜ |
| 17 | Larger held-out test set (currently 12 real + 12 fake) | 🟡 |
| 18 | Scheduled scrapers for official sources beyond RBI, SEBI, CBSE | ⬜ |
| 19 | Re-calibrate retrieval / narrative thresholds after the index grows | ⬜ |

## 4. Execution Track

**Approach so far.** The pipeline was built stage by stage (Stages 0–6), each with its own offline evaluation before moving on, then wrapped in an API and console, then made to run fully offline. Rules that guide all work:

- **Offline-first and measurable**: every change is checked with zero-API benchmarks (`scripts/eval_*.py`, `pytest`, frontend build) before it is merged.
- **Evidence over guesses**: no verdict without a cited source or cue; no hallucinated reference numbers.
- **No silent threshold changes**: thresholds (`0.88`, `0.84`, `0.86`) change only after re-running `scripts/eval_retrieval.py` and `scripts/eval_narratives.py`.
- **No secrets or large data in git**: checked with `scripts/scan_secrets.py` and `.gitignore`.

**Plan for the remaining work, in order:**

1. **Expand the held-out set (step 17)** — collect more fresh 2026 circulars and fake notices; re-run all evaluations to get honest unseen-data numbers. This comes first because every later step needs it to be measured.
2. **Official source scrapers (step 18)** — scheduled scrapers for more ministries and regulators; rebuild the index with `scripts/build_index.py`.
3. **Threshold re-calibration (step 19)** — after the index grows, sweep thresholds on the held-out set and update docs with the new figures.
4. **IndicConformer ASR (step 14)** — make it an optional install, evaluate CER/WER per language against Whisper, and enable it by default for the languages where it wins.
5. **Visual forensics (steps 15–16)** — build a reference seal/emblem catalogue per issuer, then train a small stamp/emblem anomaly detector; add it to the forensic score only once its false-positive rate on genuine documents is measured.
6. **Keep this file current** — update the status table and this plan whenever a milestone changes, in the same commit as the work.
