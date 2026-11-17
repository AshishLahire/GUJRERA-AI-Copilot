# Pramaan Developer Handover Guide

A one-page reference for teammates continuing development on Pramaan.

---

### 1. What Pramaan Is
Pramaan is a verification and narrative-tracking pipeline for suspicious Indian-language government notices, circulars, PDFs, and WhatsApp voice notes. Built as part of the Nasscom × Fujitsu (FRIPL) collaboration (Area 7), it provides an India-specific verification layer that cross-checks claims against official gazettes, ministry circulars, and PIB Fact Check archives.

### 2. How to Run Locally (Windows)
```powershell
# 1. Activate venv and run demo launcher (starts backend on :8000 and frontend on :5173)
.\scripts\run_demo.ps1

# Or run manually in separate terminals:
.venv\Scripts\python.exe -m uvicorn factcheck.api.app:app --host 0.0.0.0 --port 8000
npm --prefix frontend run dev
```
Open **`http://localhost:5173`** in your browser. API docs are at **`http://localhost:8000/docs`**.

### 3. API Quota & Zero-Call Discipline
- Local components (PaddleOCR, PyPDFium2, faster-whisper, BM25, and E5 embeddings) run offline without API calls.
- Gemini Flash Lite is strictly a fallback for difficult OCR and claim extraction when enabled by the user (`API_DAILY_CALL_LIMIT = 50`).
- Daily call counts are tracked persistently in `data/cache/ocr_cache.sqlite`.
- Tests and benchmark evaluations **never make external API calls** (they use mock fixtures or cached responses).
- **Never commit `.env` or real API keys.**

### 4. Datasets & Build Scripts
The 6 benchmark datasets live in `data/dataset/` and held-out files in `data/heldout/` (both are gitignored).
If setting up a fresh clone or rebuilding retrieval structures:
```powershell
.venv\Scripts\python.exe scripts/prepare_dataset.py       # Rebuilds processed JSONL records
.venv\Scripts\python.exe scripts/build_index.py           # Rebuilds BM25 & dense e5 retrieval index
.venv\Scripts\python.exe scripts/build_narratives.py      # Rebuilds HDBSCAN clusters and indicator graph
.venv\Scripts\python.exe scripts/download_asr_model.py   # Downloads Whisper small model once
```

### 5. Audio Intake & Whisper Rules
- Handled under `factcheck/ingest/audio/` (supports `.mp3`, `.ogg`, `.opus`, `.wav`, `.m4a` up to 25 MB and 180 seconds).
- Runs `faster-whisper` (`small`, `int8` on CPU).
- `USE_INDIC_CONFORMER` is `false` by default to avoid heavy PyTorch/torchaudio dependencies.
- Languages in `WHISPER_WEAK_LANGS` (`kn`, `te`, `ml`, `bn`, `gu`) trigger an amber UI note recommending IndicConformer and automatically have their claim extraction confidence capped at 0.35.

### 6. PIB Caption & Stamp Overlay Filter
- Many real-world fact-checked notices are single-panel graphics overlaid with `#PIBFactCheck`, "FAKE" rubber stamps, or helpline phone numbers (`1930`, `1800-xxx`).
- `factcheck/forensics/checks.py::filter_pib_overlay_lines` strips fact-check captions and contact lines before forensics and claim extraction to prevent fact-check metadata from leaking into extraction.
- If a retrieval match relies on removed overlay text, `decide_verdict` automatically downgrades the match from strong to possible.

### 7. Retrieval Indexes & Thresholds
- Dense embeddings use `intfloat/multilingual-e5-small` (384 dimensions). Search queries **must** use `"query: "` prefix; indexed passages **must** use `"passage: "` prefix.
- Fusion uses Reciprocal Rank Fusion (RRF $k=60$) combining BM25 and dense scores.
- Thresholds in `factcheck/config.py`:
  - `DEBUNK_STRONG_THRESHOLD = 0.88` (verified 0% false positives on genuine controls)
  - `DEBUNK_POSSIBLE_THRESHOLD = 0.84`
  - `OFFICIAL_STRONG_THRESHOLD = 0.88`
- Do not lower these thresholds without checking against `scripts/eval_retrieval.py`.

### 8. Narrative Detection & Template Reuse
- Clusters 1,968 debunks into 60 scam campaigns using PCA (50 components) + HDBSCAN (`min_cluster_size=5`).
- Live documents are assigned to a narrative cluster only if cosine similarity is $\ge 0.86$ (`NARRATIVE_ASSIGN_THRESHOLD = 0.86`).
- Template reuse indicators (`factcheck/narratives/indicators.py`) track bare domains, phone numbers, circular references, and signatories across different issuers or years (e.g. `sarvashikshaabhiyan.com` used across 2024–2026). Official registry domains and helplines are strictly excluded.

### 9. Caching & Safe Prompt Invalidation
- Cached OCR results, claim extractions, and speech transcripts reside in `data/cache/*.sqlite`.
- Cache keys use SHA-256 hashes of input text/bytes + model name + prompt version string (`CLAIM_PROMPT_VERSION = "v2"` in `factcheck/claims/extractor.py`).
- When modifying prompts, bump the version string (`"v3"`) to cleanly invalidate stale extractions without corrupting database integrity.

### 10. Top Next Steps
1. **Visual Forensics**: Train or integrate a lightweight computer vision detector for forged rubber stamps, composite emblems, and cut-and-paste logos that pure text forensics cannot see.
2. **Enable IndicConformer**: Install PyTorch and configure Hugging Face token to activate IndicConformer for Dravidian and Eastern Indian languages (`USE_INDIC_CONFORMER=true`).
3. **Expand Held-Out Test Set**: Ingest additional fresh 2026 PDF circulars and viral WhatsApp forward images to grow `data/heldout/`.
4. **Official Domain Expansion**: Expand `data/dataset/03_issuer_registry/issuers.json` with additional state government departments.

### 11. Integration Update (2026-10-25): members 4 + 5, text intake, visual check
- **Embedding model**: `intfloat/multilingual-e5-small` must be in the local Hugging Face cache, otherwise retrieval silently drops to BM25-only. Download once with `python -c "from huggingface_hub import snapshot_download; snapshot_download('intfloat/multilingual-e5-small')"`.
- **BM25-only safety**: BM25 alone can no longer label a match `strong` (raw BM25 grows with query length and produced false "Debunked" verdicts on long OCR text). Only cosine scores or exact reference matches can be strong.
- **Claim ground-truth check** (`factcheck/retrieval/ground_truth.py`, ported from `members_4_5/build_db.py` + `matcher.py`): runs inside `match_sources()` on the canonical claim; result in `matches.ground_truth`. `decide_verdict` uses it after hybrid retrieval (`decided_by = "ground_truth"`) and copies PIB's official clarification into `verdict.official_clarification`. Rebuild with `python scripts/build_ground_truth.py`; add citable records in `data/curated/extra_records.json`.
- **Evaluation**: `python scripts/eval_claims.py all` (offline) reproduces members 4 + 5: ground truth 70/105 fake claims matched without pattern records, 15/15 true, 6/6 unrelated, **0 dangerous errors**; issuer resolver 63/63 where the notice names its issuer. Add `--live` to run Gemini extraction (uses quota, cached). Report: `docs/claims_eval.md`. `eval_retrieval.py` is unchanged (0/15 false strong on controls, 0/79 on officials).
- **Visual check** (`factcheck/forensics/visual.py`): `visual` block on sample and upload responses. Findings have 0 points and `rule_status="unverified"`, so `eval_forensics.py` numbers are unchanged. PIB "FAKE" stamps are also detected as seals.
- **UI**: "Text" intake tab, Claim Ground-Truth card, Visual Document Check card with region boxes ("Regions" toggle), "Export JSON" / "Note" buttons on the verdict banner.
- **Dev servers**: the API runs on port 8000 (`python -m uvicorn factcheck.api.app:app --port 8000`) and the console on port 5173 (`npm run dev` in `frontend/`).
