# Pramaan (प्रमाण) — Anti-Misinformation Verification Engine

Pramaan checks suspicious Indian-language government notices, circulars, letters, screenshots, PDFs, and WhatsApp voice notes, and returns an evidence-backed verification verdict. Developed as an empirical prototype for the Nasscom × Fujitsu (FRIPL) collaboration under Problem Statement Area 7 (multilingual claim verification and narrative detection), Pramaan serves as an India-specific verification layer that complements Fujitsu's Frontria engines by cross-referencing circulating claims against official gazettes, ministry circulars, and PIB Fact Check archives.

---

## 1. How It Works (Pipeline)

Pramaan processes uploaded documents or audio clips through a local-first 6-stage pipeline:

```
Document / Audio ──▶ 1 Extraction ──▶ 2 Forensics ──▶ 3 Claim Extraction ──▶ 4 Source Match ──▶ 5 Verdict ──▶ 6 Narrative & Template Reuse
```

| Stage | What It Does | Main Module | API Calls | Status |
| :--- | :--- | :--- | :---: | :---: |
| **Ingestion** | Validates MIME type, file size limits (10 MB doc, 25 MB audio), extracts first page of multi-page PDFs, and prepares audio samples. | [`factcheck/ingest/`](factcheck/ingest/) | **No** | **Done** |
| **1. Text Extraction** | Extracts text from images and scanned PDFs via Gemini Flash Lite (hosted fallback model) or PyPDFium2, or transcribes voice notes via faster-whisper. PaddleOCR and local Ollama VLM are optional offline engines (currently not installed). | [`factcheck/extract/ocr/`](factcheck/extract/ocr/)<br>[`factcheck/ingest/audio/`](factcheck/ingest/audio/) | Yes (hosted Gemini) / Optional | **Done** |
| **2. Forensic Check** | Flags text manipulation cues (fee demands, tight deadlines, lookalike domains, non-existent ministries, anomalous dates, personal bank payment details), strips fact-check banner/stamp overlays, and runs visual document checks (heuristic detection of coloured ink seals/stamps, handwritten signature area, letterhead emblem, editing-software EXIF tags, and JPEG error-level traces; observations only: 0 risk points). | [`factcheck/forensics/`](factcheck/forensics/)<br>[`factcheck/forensics/visual.py`](factcheck/forensics/visual.py) | **No** | **Done** |
| **3. Claim Extraction** | Distills core assertion, claimed issuing agency, effective date, and rupee amounts into a structured canonical English claim representation via Gemini Flash Lite (cached). | [`factcheck/claims/`](factcheck/claims/) | Optional (cached) | **Done** |
| **4. Source Match** | Hybrid retrieval using BM25 and dense `multilingual-e5-small` embeddings fused with Reciprocal Rank Fusion ($k=60$) against 1,968 debunks and 79 official circulars, combined with canonical claim ground-truth checks (ported from `members_4_5`, TF-IDF over 183 curated records supplying official clarifications). | [`factcheck/retrieval/`](factcheck/retrieval/)<br>[`factcheck/retrieval/ground_truth.py`](factcheck/retrieval/ground_truth.py) | **No** | **Done** |
| **5. Verdict Decision** | Combines forensic risk score, circular reference lookups, ground-truth match, and hybrid retrieval scores into one of 6 calibrated verdicts with structured reasoning and evidence links. | [`factcheck/decide/`](factcheck/decide/) | **No** | **Done** |
| **6. Narrative & Template Reuse** | Maps the claim to 60 HDBSCAN scam clusters and links shared template indicators (bare domains, phone numbers, signatories, references) across different issuers and years. | [`factcheck/narratives/`](factcheck/narratives/) | **No** | **Done** |

### Worked Example: `FN-TG-01595` (Fake RBI Old-Coin Order)
1. **Ingest**: JPEG image validated and scaled to $\le 1600\text{px}$ long edge.
2. **Extraction**: Gemini Flash Lite extracts English and Hindi text (PaddleOCR and Ollama are optional offline engines, not installed in this environment). PIB Fact Check overlay captions (`#PIBFactCheck`, `FAKE` stamp) are stripped by [`filter_pib_overlay_lines`](factcheck/forensics/checks.py).
3. **Forensic Check**: Flags `fee_demand` (+35: Rs 700 form charge + delivery fee), `lookalike_domain` (+35: `governorb.org`, `governor.org.in`), and `mixed_issuers` (Finance Ministry addressed on an RBI letterhead). Forensic score: **100/100 (High Risk)**.
4. **Claim Extraction**: Distills canonical claim: *"RBI charges a refundable form fee of Rs 700 and delivery fee to buy or sell old coins."*
5. **Source Match**: Multilingual-E5 retrieves PIB debunk `FN-TG-01595` at cosine similarity **0.881** ($\ge 0.88$ strong threshold).
6. **Verdict**: **Debunked: matches official fact-check** (`red` badge). If "Simulate a new forgery" is toggled ON, it falls back cleanly to **Likely forged document** based on the 100/100 forensic score.
7. **Narrative**: Maps to cluster `cluster_010` (*RBI: Prize Exchange / Old Coin Scam*, 38 debunks since 2021).

---

## 2. Status

- **Completed**:
  - Inference pipeline across images, PDFs, and 22 scheduled Indian languages + English; 5 have low accuracy without IndicConformer voice notes.
  - Text-based forensics with 14 heuristic rules, issuer alias matching, automated PIB overlay stamp removal, and heuristic visual check (seal, signature, emblem, edit traces).
  - Hybrid retrieval engine with 1,968 deduplicated debunks, 79 official source documents, and claim ground-truth check (members 4 + 5) against 183 curated records.
  - Unsupervised HDBSCAN narrative clustering and cross-issuer template reuse graph.
  - Interactive React + TypeScript + Tailwind console with dark mode, sample selector, "Simulate new forgery" toggle, and audio waveform player.
  - Paste-text intake (WhatsApp forwards in English / Hindi / Hinglish) in the console, with sample forwards.
  - Official clarification in the verdict, and JSON / plain-text report export (`pramaan.verification_report/v1`) for newsroom desks, bank fraud teams or Frontria.
  - Visual document check (seal, signature, emblem, edit traces) drawn as boxes on the document.
- **Partial / Deferred**:
  - **IndicConformer ASR**: Disabled by default (`USE_INDIC_CONFORMER=false`) to avoid heavy PyTorch dependencies and gated Hugging Face auth. Whisper small CPU runs in its place, with an amber UI quality warning shown for non-Devanagari scripts.
  - **Visual Forensics**: Heuristic visual check built; seal verification against references not built. Classical OpenCV heuristics locate seals, signatures and emblems and flag edit traces, but matching against reference seals per issuer is not built.
  - **Held-Out Document Set**: Initial collection has 12 real PDFs and 12 fake images (10 real PDFs overlap circular index; 2 real and 12 fakes are completely fresh).
- **Next Steps**:
  - Lightweight CNN/ViT stamp and emblem anomaly detector.
  - Scheduled scrapers to expand official gazettes beyond RBI, SEBI, and CBSE.

---

## 3. Quick Start (Windows)

Prerequisites: Windows 10/11, [Anaconda / Miniconda](https://www.anaconda.com/download), Node.js 18+, and git.

### 1. Python Environment Setup
```powershell
# Create a clean Python 3.11 environment via conda (bypasses Windows Store Python restrictions)
C:\Users\ashis\anaconda3\Scripts\conda.exe create -y -n factcheck311 python=3.11

# Build the project venv from that conda interpreter
C:\Users\ashis\anaconda3\envs\factcheck311\python.exe -m venv .venv

# Install project and development dependencies with network timeout flags
.venv\Scripts\python.exe -m pip install --timeout 180 --retries 10 -e ".[dev]"
```

### 2. Configuration & Frontend Installation
```powershell
# Copy configuration template
Copy-Item .env.example .env

# Install frontend npm dependencies
npm --prefix frontend install
```
*Note: Edit `.env` to set `GEMINI_API_KEY` if you wish to enable the optional cloud fallback. Never commit `.env`!*

### 3. Build Retrieval & Narrative Indexes (Zero API Calls)
```powershell
# 1. Build BM25 and dense e5 retrieval index (persists to data/index/)
.venv\Scripts\python.exe scripts/build_index.py

# 2. Build HDBSCAN narrative clusters and template-reuse graph
.venv\Scripts\python.exe scripts/build_narratives.py

# 3. Pre-download the Whisper small model into cache (one-time setup)
.venv\Scripts\python.exe scripts/download_asr_model.py
```

### 4. Run the Application
Launch both backend (`:8000`) and frontend (`:5173`):
```powershell
.\scripts\run_demo.ps1
```
Or start them manually in separate shells:
```powershell
# Terminal 1 — FastAPI Backend
.venv\Scripts\python.exe -m uvicorn factcheck.api.app:app --host 0.0.0.0 --port 8000

# Terminal 2 — Vite React Frontend
npm --prefix frontend run dev
```

### 5. Access Endpoints
- **Frontend Console**: [http://localhost:5173](http://localhost:5173)
- **Backend Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Common Problems and Fixes
- **Slow PyPI Installs**: Always use `--timeout 180 --retries 10` with `pip`.
- **Microsoft Store Python**: Windows Store Python lacks build tools and fails in sandboxed environments. Always use the conda-provided Python interpreter.
- **Ollama Not Installed**: Set `OLLAMA_ENABLED=false` in `.env` to bypass local VLM checks.
- **First Audio Request Latency**: The first voice note request loads Whisper into RAM (~1.5s); subsequent requests transcribe in <10ms from cache.
- **Daily Quota Reached**: The daily limit is controlled by `API_DAILY_CALL_LIMIT = 50`. When reached, the system falls back to local rules and caches.

---

## 4. Project Map

```
factcheck/
  api/               FastAPI backend endpoints and upload handlers
  claims/            Stage 3: claim distillation prompt and cache logic
  config.py          Pydantic Settings loaded from .env
  decide/            Stage 5: calibrated verdict determination
  extract/           Stage 1: PaddleOCR, PyPDFium2, and field extraction
  forensics/         Stage 2: heuristic rule engine, issuer detection, and overlay filter
  ingest/            File validation, downscaling, and voice note audio intake
    audio/           Whisper speech-to-text, IndicConformer stubs, and language definitions
  narratives/        Stage 6: HDBSCAN clustering, naming, and indicator extraction
  schemas.py         Shared Pydantic data models across all stages
data/
  dataset/           [Gitignored] 6 core benchmark datasets
  processed/         [Gitignored] Extracted and normalized JSONL records
  index/             [Gitignored] BM25 indexes, dense e5 embeddings, and narrative graphs
  cache/             [Gitignored] SQLite caches (OCR, claims, transcripts)
  demo/              Demo sample images and demo_set.json metadata
  eval/              Evaluation manifests, test audio clips, and summary CSVs
  heldout/           [Gitignored] Unseen evaluation files (12 real PDFs, 12 fake images)
frontend/            Vite + React + TypeScript + Tailwind CSS console
docs/                Evaluation reports and handover documentation
scripts/             Index builders, evaluation runners, and demo launchers
tests/               Pytest test suite (unit and integration tests, 100% offline)
```

---

## 5. Configuration Settings

All settings live in [`factcheck/config.py`](factcheck/config.py) and can be overridden via `.env`:

| Setting | Default | Description |
| :--- | :--- | :--- |
| `OLLAMA_ENABLED` | `true` | Enables local Ollama VLM escalation for low-confidence OCR. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint for local Ollama daemon. |
| `VLM_MODEL` | `qwen3-vl:8b` | Model served by Ollama for OCR escalation. |
| `GEMINI_API_KEY` | `None` | Google Gemini API key for hosted fallback (never commit!). |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Cloud fallback model used for OCR and claim extraction. |
| `GEMINI_TIMEOUT_SECONDS` | `30` | Timeout in seconds for Gemini HTTP calls. |
| `API_DAILY_CALL_LIMIT` | `50` | Maximum hosted API calls permitted per calendar day. |
| `OCR_LANGUAGES` | `["hi", "en"]` | Languages passed to PaddleOCR. |
| `TIER1_CONFIDENCE_THRESHOLD` | `0.80` | Threshold below which OCR escalates to VLM fallback. |
| `CACHE_DB_PATH` | `data/cache/ocr_cache.sqlite` | SQLite database storing OCR and API usage counts. |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | 384-dimensional dense semantic embedding model. |
| `RRF_K` | `60` | Rank constant $k$ for Reciprocal Rank Fusion. |
| `DEBUNK_STRONG_THRESHOLD` | `0.88` | Cosine similarity threshold for decisive debunk match. |
| `DEBUNK_POSSIBLE_THRESHOLD` | `0.84` | Cosine similarity threshold for related/possible match. |
| `OFFICIAL_STRONG_THRESHOLD` | `0.88` | Cosine threshold for authenticating official circulars. |
| `HDBSCAN_MIN_CLUSTER_SIZE` | `5` | Minimum cluster size for narrative density clustering. |
| `PCA_COMPONENTS` | `50` | Number of PCA dimensions before HDBSCAN clustering. |
| `NARRATIVE_ASSIGN_THRESHOLD`| `0.86` | Centroid cosine threshold required to assign a narrative. |
| `MAX_AUDIO_MB` | `25` | Maximum upload size for audio voice notes. |
| `MAX_AUDIO_SECONDS` | `180` | Maximum duration limit in seconds for voice notes. |
| `WHISPER_MODEL` | `small` | Faster-whisper model variant (CPU `int8`). |
| `USE_INDIC_CONFORMER` | `false` | Enables IndicConformer PyTorch model (requires auth). |
| `WHISPER_WEAK_LANGS` | `["kn", "te", "ml", "bn", "gu"]` | Languages triggering low-quality UI warning under Whisper small. |

---

## 6. API Calls, Quota and Caching

Pramaan enforces a strict zero-call discipline for core workflows:

1. **Where Gemini Is Called**:
   - Stage 1 OCR: Primary engine actually used for image OCR (PaddleOCR and local Ollama VLM are optional and not installed in this environment). Enabled via "Allow cloud fallback" (on by default when OLLAMA_ENABLED=false).
   - Stage 3 Claim Extraction: Gemini Flash Lite extracts canonical claims; cached responses in SQLite avoid repeated calls.
2. **Daily Quota Enforcement**:
   - `API_DAILY_CALL_LIMIT = 50`. Persistent daily usage is tracked in `data/cache/ocr_cache.sqlite`. Once 50 is reached, cloud fallback is rejected with an error.
3. **Cache Keying & Prompt Invalidation**:
   - Caches are keyed by `SHA-256(normalized_text + model_name + prompt_version)`.
   - The active prompt version is tracked via `CLAIM_PROMPT_VERSION = "v2"` in [`factcheck/claims/extractor.py`](factcheck/claims/extractor.py). Bumping the prompt version invalidates stale claim outputs automatically without database corruption.
4. **Cache Warm-Up**:
   - Run `python scripts/warm_demo_cache.py` to pre-seed OCR and claim records for the 20 demo items.

---

## 7. API Endpoints

| Method | Path | What It Returns |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Service health, Ollama status, Gemini model, daily call quota usage (`0 of 50 used`), and speech model state. |
| `GET` | `/api/samples` | List of 20 benchmark demo items with metadata and talking points. |
| `GET` | `/api/samples/{sample_id}/image` | Serves demo sample image file. |
| `POST` | `/api/ocr/sample/{sample_id}` | Runs full verification pipeline on a pre-cached demo sample. |
| `POST` | `/api/ocr/upload` | Runs verification on an uploaded image or PDF document. |
| `GET` | `/api/uploads/{filename}` | Serves uploaded document image. |
| `GET` | `/api/narratives` | Lists 60 scam narrative clusters (supports `sort`, `search`, `issuer` params). |
| `GET` | `/api/narratives/{cluster_id}` | Detailed cluster breakdown with monthly debunks, exemplars, and indicators. |
| `GET` | `/api/languages` | Supported 23 Indian languages, script tags, and engine recommendations. |
| `POST` | `/api/check/text` | Verifies a pasted message (JSON `{text, allow_fallback}`): same stages minus OCR. |
| `POST` | `/api/transcribe/upload` | Ingests and transcribes uploaded voice notes (`.mp3`, `.ogg`, `.wav`, etc.). |
| `GET` | `/api/transcribe/{job_id}/audio` | Streams uploaded voice note audio for playback. |
| `POST` | `/api/transcribe/{job_id}/language` | Re-transcribes an existing audio clip with a manual language override. |

---

## 8. Using the UI and Demo Set

The Pramaan console features two main views:
- **Document Verification (`/`)**: Dual-pane workspace with uploaded image on the left and verification cards on the right.
- **Narratives Explorer (`/?tab=narratives`)**: Interactive timeline and search view across all 60 known scam campaigns.

### Key Controls
- **"Allow cloud fallback"**: Checkbox (on by default when OLLAMA_ENABLED=false) that controls whether low-confidence items or fresh claim extraction may query Gemini.
- **"Simulate a new forgery (hide its own PIB debunk)"**: Toggle shown on demo fake notices that performs Leave-One-Out retrieval (excludes the sample's own debunk record, URL, and post ID to demonstrate how the pipeline handles an unseen forgery).

### Demo Samples & Talking Points
From [`data/demo/demo_set.json`](data/demo/demo_set.json):

1. **`FN-TG-01595`** (RBI Old-Coin Scam): Crude forgery with upfront fee and fake domains; caught as *Debunked* (normal) or *Likely forged* (with simulate toggle ON via 100/100 forensics).
2. **`SYN-0031`** (Telecom Regulatory Authority - Phishing): Planted phishing lookalike domain (`www.tca-online-apply.in` vs official `tca-fictional.example`) + personal Gmail helpline + urgency + Rs 5,00,000 payout: scores 80/100 (*Likely forged*).
3. **`FN-TG-00988`** (PM-KUSUM Solar): Demands deposit into personal bank account; matches sister PM-KUSUM debunks even with toggle ON.
4. **`FN-TG-01999`** (Railway Board PLB): Perfect visual formatting scores 0/100 on forensics, but is caught decisively by PIB debunk match. With toggle ON, it becomes *Unverified*, never falsely *Genuine*.
5. **`OFF-4A2E01CE80__screenshot`** (CBSE Circular in WhatsApp Screenshot): Genuine circular with official reference `Acad-65/2026`; scores 15/100 (Low risk) due to `personal_contact` (+15 warning for Gmail helpline).

*(`FN-TG-01746` moved to demo slot 20 as an OCR nuance case study: shows why Pramaan surfaces verbatim text evidence for every cue, including the `mina.gov.is` OCR misread.)*

---

## 9. Evaluation Results

All evaluation figures come from offline benchmarks using local embeddings and cached OCR with **zero external API calls**:

### 1. Forensics ([`docs/forensics_eval.md`](docs/forensics_eval.md))
- **12 Real Fake Notices**: High risk: 2/12 (16.7%), Medium risk: 5/12 (41.7%), Low risk: 5/12 (41.7%).
- **79 Genuine Official Documents**: 79/79 (100.0%) scored Low risk; 0 false positives for High risk.
- **Cached Synthetic Forgeries**: Clean controls: 2/2 scored 0 risk (0% false alarms); Forged notices: 2/2 flagged (100% detection). (4 of 60 cached in `ocr_cache.sqlite`; un-cached samples deferred to preserve quota).
- *Limitation*: Text rules cannot see rubber stamps, embossed seals, or pasted logos; rules were tuned in-sample.

### 2. Retrieval & Matching ([`docs/retrieval_eval.md`](docs/retrieval_eval.md))
- **`04_multilingual_claims` (105 fake claims across 7 languages)**:
  - Bilingual (English + Original) Top-1 Recall: **96 / 105 (91.4%)**, Top-3: **98 / 105 (93.3%)**.
  - Original-only Top-3 Recall: **90 / 105 (85.7%)**.
  - True control false strong matches: **0 / 15 (0.0%)**.
- **`01_fake_notice_benchmark` (90 fake notices in Leave-One-Out Mode)**:
  - Top-1 Narrative Recall: **60 / 90 (66.7%)**, Top-3: **72 / 90 (80.0%)**.
  - For repeated scam families (excluding 18 singleton notices): Top-1 Recall is **60 / 72 (83.3%)**.
- *Limitation*: E5 dense cosine similarity falls in a compressed range (~0.78 to 0.92), making threshold tuning sensitive.

### 3. Narrative Clustering ([`docs/narratives_eval.md`](docs/narratives_eval.md))
- **HDBSCAN Parameter Sweep**: `min_cluster_size = 5` yields 60 clusters, 1,042 noise posts (52.9%), and **99.1% weighted purity** against keyword labels.
- **Multilingual Claim Assignment**:
  - Part 1 (Nearest cluster, no threshold over 15 fakes): **11 / 15 (73.3%)** across all 7 languages.
  - Part 2 (Production threshold 0.86): Fakes assigned: **10 / 15 (66.7%)** with **100.0% precision** (10/10). True controls assigned: **0 / 15 (0.0%)**.
- *Limitation*: Captions on Telegram often omit verbatim circular numbers; purity is partly circular with keyword heuristics.

### 4. Speech Recognition / Voice Notes ([`scripts/eval_asr.py`](scripts/eval_asr.py))
- Evaluated on 20 test clips (4–8s; 12 synthetic TTS, 8 natural/noisy) with fair Unicode NFC, nukta-removal, and number-word normalisation:
  - **Whisper-strong (en, hi, mr, ta, ur, ne | n=13)**: Auto CER **0.248**, WER **0.400**; Manual CER **0.164**, WER **0.312**.
  - **Whisper-weak (kn, te, ml, bn, gu | n=7)**: Auto CER **0.670**, WER **0.990**; Manual CER **0.777**, WER **1.000**.
  - Language Identification Accuracy: **16 / 20 (80.0%)**.
- *Limitation*: Whisper small has Devanagari transliteration bias on Dravidian scripts; IndicConformer is needed for production Dravidian ASR.

### 5. Held-Out Document Overlap ([`data/heldout/manifest.json`](data/heldout/manifest.json))
- 12 real PDFs evaluated with `pypdfium2`: 10 matched existing circulars in the official index via exact reference numbers (`RBI/2026-27/290` through `299`); 2 are fresh (`20260720623209264.pdf`, `Reminder_6_Submission_LOC_21102026.pdf`).
- 12 fake images: **12 / 12 are fresh unindexed fakes** (0 exact image-hash duplicates).

---

## 10. Tests

Run the full offline test suite and frontend compilation:
```powershell
# Run backend pytest suite (68 tests, ~20s, 0 API calls)
.venv\Scripts\python.exe -m pytest tests/

# Verify frontend TypeScript compilation and production bundle
npm --prefix frontend run build
```

| Test File | What It Covers |
| :--- | :--- |
| [`tests/test_api.py`](tests/test_api.py) | FastAPI endpoints, health check, sample serving, and error sanitization. |
| [`tests/test_audio.py`](tests/test_audio.py) | Audio ingestion limits (25 MB, 180s), Whisper transcription, confirmation flags, weak-language warnings, and confidence capping. |
| [`tests/test_config.py`](tests/test_config.py) | Settings validation, language parsing, and default thresholds. |
| [`tests/test_dataset.py`](tests/test_dataset.py) | Integrity checks on processed JSONL benchmark datasets. |
| [`tests/test_forensics.py`](tests/test_forensics.py) | Heuristic rule cues, issuer detection, lookalike domains, and PIB overlay filtering. |
| [`tests/test_narratives.py`](tests/test_narratives.py) | HDBSCAN clustering fixture, multi-part TLD extraction, and template-reuse indicator graphs. |
| [`tests/test_ocr.py`](tests/test_ocr.py) | PaddleOCR fallback handling, image downscaling, and cache retrieval. |
| [`tests/test_stages_3_to_5.py`](tests/test_stages_3_to_5.py) | Claim extraction mocking, BM25 + dense retrieval fusion, and verdict decision logic. |

---

## 11. Credits

- **Ashish Lahire**: System architecture, Stages 1–6, FastAPI backend, React/Vite user console, hybrid BM25/E5 retrieval engine, HDBSCAN narrative clustering, text forensics rules, PIB overlay removal filter, heuristic visual check, and benchmark evaluations.
- **members_4_5 Author**: Ground-truth check module (`build_db.py`, `matcher.py`), curated ground-truth database (PIB notices, scam patterns, verified official circulars), and claim-level TF-IDF evaluation.
- **Teammate (Voice Notes)**: Audio intake module (`languages.py`, `indic_asr.py`, `transcribe.py`), speech evaluation clips, and held-out evaluation documents. *(Note: Her 4.4% CER was measured with IndicConformer, which is currently disabled by default).*
- **Teammate (Dataset)**: Curation of the six core datasets (`01_fake_notice_benchmark`, `02_official_source_corpus`, `03_issuer_registry`, `04_multilingual_claims`, `05_whatsapp_variants`, `06_synthetic_forgeries`) and empirical analysis in `data/dataset/`.

---

## 12. Known Limitations and Next Steps

1. **Visual Forensics Scope**: Heuristic visual check built; seal verification against references not built. Classical OpenCV heuristics locate seals, signatures, emblems, and edit traces, but matching against an authoritative reference seal catalog is not built.
2. **IndicConformer Disabled**: `USE_INDIC_CONFORMER` is turned off to keep the repository lightweight and runnable without PyTorch or Hugging Face logins. As a result, Dravidian and Eastern Indic voice notes experience high error rates under Whisper small.
3. **Small Held-Out Test Corpus**: The held-out set currently contains only 12 real PDFs and 12 fake images; additional 2026 circulars are needed for long-term validation.
4. **Retrieval Threshold Sensitivity**: Because `multilingual-e5-small` embeddings are compressed, thresholds (`0.88`, `0.84`, `0.86`) must be re-calibrated whenever the document index grows significantly.
5. **PIB Overlay Graphics in Benchmarks**: Benchmark fake notices are single-panel PIB composite images where rubber stamps occlude parts of the underlying letter text.

---

## 13. Rules for Contributors

1. **Zero Secret Leaks**: Never commit `.env`, API keys, or raw credentials.
2. **Preserve Gitignore Discipline**: Never commit `data/dataset/`, `data/heldout/`, `data/cache/`, `node_modules/`, or model binaries.
3. **Network Flags on Pip**: Always run package installations with `--timeout 180 --retries 10`.
4. **Pre-Commit Verification**: Run `.venv\Scripts\python.exe -m pytest tests/` and `npm --prefix frontend run build` before pushing any commit.
5. **Prompt Version Bumping**: When changing OCR or claim prompts, bump `CLAIM_PROMPT_VERSION` in [`factcheck/claims/extractor.py`](factcheck/claims/extractor.py) to safely invalidate SQLite caches.
6. **No Arbitrary Thresholds**: Never change retrieval or narrative thresholds (`0.88`, `0.84`, `0.86`) without executing `scripts/eval_retrieval.py` and `scripts/eval_narratives.py`.

---

## 14. Offline Deployment

Pramaan supports a fully air-gapped, zero-cloud offline mode. When enabled, all Gemini cloud calls are blocked at the code level, and OCR and claim extraction run entirely via local models served by Ollama.

### 14.1 Hardware Requirements

| Component | Minimum Specification | Recommended |
| :--- | :--- | :--- |
| **GPU VRAM** | 4.0 GB (e.g. RTX 3050 / GTX 1660) | 6.0+ GB (e.g. RTX 4060 / RTX 3060) |
| **Model Footprint** | `qwen3-vl:4b`: **3.6 GB VRAM** (100% GPU offload) | `qwen3-vl:4b` fits comfortably on standard laptops |
| **CPU Fallback** | 8+ GB RAM (execution time ~15–25s per call) | GPU execution recommended (~2.1s per call) |

### 14.2 Models to Pull

Ensure Ollama is installed and running, then pull the vision-language model:

```bash
ollama pull qwen3-vl:4b
```

### 14.3 Configuration

In `.env`, set:

```bash
OFFLINE_MODE=true
OCR_ENGINE_PREFERENCE=qwen_first
LOCAL_LLM_MODEL=qwen3-vl:4b
```

- **Zero Cloud Leakage**: `run_gemini_fallback` and `_call_gemini_claim_llm` raise immediate `RuntimeError` if invoked, and network requests to Gemini endpoints are blocked.
- **Safety Safeguards**: Images are downscaled to max 1200 px long side, output is capped, and queries have a 90-second timeout.
- **Cache Isolation**: Claim cache entries are keyed with `ollama:{model}`, completely separating offline entries from hosted Gemini cache entries.
- **UI State**: The UI renders a prominent **Fully offline** green status pill and automatically hides cloud fallback toggles.

### 14.4 Full Offline End-to-End Evaluation (20 Demo Items Benchmark)

Evaluated end-to-end on the 20 benchmark demo items (`data/demo/demo_set.json`) with `OFFLINE_MODE=true`, local vision OCR (`qwen3-vl:4b` at 1200 px), and local claim extraction (`qwen3-vl:4b` via Ollama):

| Metric | Hosted Cloud (`gemini-3.5-flash-lite`) | Local Offline (`qwen3-vl:4b`) | Agreement |
| :--- | :---: | :---: | :---: |
| **Final Verdict Agreement** | 20 / 20 | 18 / 20 | **90.0%** (18/20) |
| **Genuine Official Accuracy** | 4 / 4 `matches_official` | 4 / 4 `matches_official` | **100.0%** (4/4) |
| **Synthetic Forgery Agreement** | 4 / 4 | 4 / 4 | **100.0%** (4/4) |
| **Reference Number Match** | 20 / 20 | 18 / 20 | **90.0%** (18/20) |
| **Hallucinated References** | 0 | 0 | **0 (Zero)** |
| **Average Latency per Item** | ~1.8s (network dependent) | **OCR 2.22s + Claim 0.33s = 2.55s** | Local GPU |

#### Verdict Stage Attribution (Items where Verdict Changed)
Across the 20 demo items, only 2 items differed in final verdict after extending the PIB overlay filter:
1. **`FN-TG-01746` (fake)**: Cloud produced `suspicious_unverified` vs. Offline `unverified` (*Stage: OCR*). Small compressed footer text (`mha.gov.in`) was an OCR misread of small text as `mina.gov.is` under cloud OCR (triggering a 45-point suspicious penalty). Local Qwen3-VL OCR did not produce `mina.gov.is`, scoring 0 forensic penalty -> `unverified`.
2. **`FN-TG-00385` (fake)**: Cloud produced `unverified` vs. Offline `debunked` (*Stage: Claim*). Local claim extraction generated a concise claim (`Government of India informs about toll charges for 12 hours`) that matched the curated ground-truth database record `FN-TG-00427` (claim TF-IDF similarity 0.264 vs 0.25 threshold), whereas Gemini's longer claim phrasing stayed below the threshold.
*(Note: `FN-TG-00427` previously differed due to OCR caption leakage, but with the extended PIB overlay filter stripping Hindi caption OCR variants like `यह दावा फ़्रूजी है!`, its retrieval score drops below 0.88, resolving cleanly to `unverified` in agreement with cloud).*


