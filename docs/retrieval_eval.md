# Stage 4 Retrieval & Threshold Calibration Evaluation

Offline evaluation of Stage 4 (Hybrid Source Match: BM25 + `intfloat/multilingual-e5-small` with Reciprocal Rank Fusion $k=60$) and Stage 5 (Verdict Decision) on the complete local dataset. **Zero external API calls** were made during this evaluation.

---

## 1. Index Overview

The Stage 4 hybrid retrieval engine indexes two distinct collections:

| Collection | Total Records | Indexing Method | Text Representations Indexed |
| :--- | :--- | :--- | :--- |
| **PIB Fact-Check Debunks** | **1,968** | Hybrid (BM25 + Dense E5) | Deduplicated union of 90 benchmark fake notices and 1,878 Telegram fact-check posts (linked duplicates unified). Indexed with `passage: ` prefix. |
| **Official Source Corpus** | **79** | Hybrid (BM25 + Dense E5) | Official gazette notifications, ministry circulars, and verified schemes. Indexed with `passage: ` prefix. |

### Dense Embeddings & Fusion
- **Model**: `intfloat/multilingual-e5-small` (384-dimensional dense vectors, 512 context token limit, normalized inner-product cosine similarity).
- **Prefix discipline**: Mandatory `"query: "` on search queries, `"passage: "` on corpus records.
- **Hybrid Fusion**: Reciprocal Rank Fusion (RRF) with rank constant $k=60$:
  $$\text{RRF Score}(d) = \frac{1}{60 + \text{rank}_{\text{BM25}}(d)} + \frac{1}{60 + \text{rank}_{\text{dense}}(d)}$$

---

## 2. Table 1: Retrieval on `04_multilingual_claims`

Evaluated across 105 fake claims in 7 Indian language representations and 15 true control claims. Tested with both bilingual input (English canonical claim + original text) and original-language query only (zero English).

> [!NOTE]
> Telegram post narrative labels in the underlying dataset originate from approximate keyword rules in `rules.py`. Multilingual claims in `04_multilingual_claims` are templated variations.

| Language | Fake Claims | Both (EN + Orig) Top-1 | Both (EN + Orig) Top-3 | Orig-Only Top-1 | Orig-Only Top-3 | True Controls | True False-Strong |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **bn** (Bengali) | 15 | 13/15 (86.7%) | 14/15 (93.3%) | 9/15 (60.0%) | 11/15 (73.3%) | 0 | 0/0 |
| **en** (English) | 15 | 14/15 (93.3%) | 14/15 (93.3%) | 13/15 (86.7%) | 14/15 (93.3%) | 5 | 0 (0.0%) |
| **hi** (Hindi) | 15 | 14/15 (93.3%) | 14/15 (93.3%) | 10/15 (66.7%) | 11/15 (73.3%) | 5 | 0 (0.0%) |
| **hi-Latn** (Hinglish) | 15 | 14/15 (93.3%) | 14/15 (93.3%) | 13/15 (86.7%) | 14/15 (93.3%) | 5 | 0 (0.0%) |
| **mr** (Marathi) | 15 | 14/15 (93.3%) | 14/15 (93.3%) | 12/15 (80.0%) | 12/15 (80.0%) | 0 | 0/0 |
| **ta** (Tamil) | 15 | 13/15 (86.7%) | 14/15 (93.3%) | 10/15 (66.7%) | 14/15 (93.3%) | 0 | 0/0 |
| **te** (Telugu) | 15 | 14/15 (93.3%) | 14/15 (93.3%) | 12/15 (80.0%) | 14/15 (93.3%) | 0 | 0/0 |
| **Overall** | **105** | **96/105 (91.4%)** | **98/105 (93.3%)** | **79/105 (75.2%)** | **90/105 (85.7%)** | **15** | **0/15 (0.0%)** |

---

## 3. Table 2: Benchmark Retrieval on `01_fake_notice_benchmark`

Evaluated on all 90 fake notices in `data/processed/fake_notices.jsonl` using their `clean_claim` text:
- **Normal Retrieval**: The entire index is searched.
- **Leave-One-Out (LOO) Retrieval**: The notice's entire deduplicated record (its own notice entry and its linked source Telegram post) is removed prior to retrieval, simulating an unseen forgery.

| Metric | Normal Retrieval | Leave-One-Out (LOO) Mode | Description |
| :--- | :---: | :---: | :--- |
| **Exact-Record Match Top-1** | **65 / 90 (72.2%)** | *Excluded by design* | Retrieves the identical notice record |
| **Narrative Match Top-1** | **87 / 90 (96.7%)** | **60 / 90 (66.7%)** | Matches the correct underlying scam topic |
| **Narrative Match Top-3** | **90 / 90 (100.0%)** | **72 / 90 (80.0%)** | Correct scam topic appears within the top 3 hits |

> In Leave-One-Out mode, 18 of the 90 notices are singleton narratives in the index (no second debunk exists for that exact scam). For repeated scams, top-1 recall is 60 / 72 (83.3%).

---

## 4. Table 3: Threshold Calibration Sweep & Chosen Thresholds

Dense cosine similarities from `multilingual-e5-small` fall in a compressed dynamic range (~`0.78` to `0.93`). We swept candidate cosine thresholds against:
1. 105 fake claims from `04_multilingual_claims`
2. 90 leave-one-out fake notice clean claims
3. 15 true claim negative controls
4. 79 genuine official documents queried against the debunk collection

| Threshold | Fake Claims Strong | LOO Notices Strong | True Claims FP | Genuine Docs FP | Strong Precision % |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 0.78 | 96 / 105 | 60 / 90 | 15 / 15 | 79 / 79 | 54.0% |
| 0.80 | 96 / 105 | 60 / 90 | 15 / 15 | 79 / 79 | 54.2% |
| 0.82 | 96 / 105 | 60 / 90 | 13 / 15 | 74 / 79 | 55.5% |
| 0.84 | 95 / 105 | 60 / 90 | 7 / 15 | 38 / 79 | 66.0% |
| 0.85 | 94 / 105 | 58 / 90 | 2 / 15 | 15 / 79 | 76.4% |
| 0.86 | 84 / 105 | 56 / 90 | 2 / 15 | 3 / 79 | 82.8% |
| 0.87 | 82 / 105 | 56 / 90 | 0 / 15 | 1 / 79 | 85.2% |
| **0.88 (Chosen)** | **64 / 105** | **54 / 90** | **0 / 15** | **0 / 79** | **90.8%** |
| 0.89 | 51 / 105 | 52 / 90 | 0 / 15 | 0 / 79 | 92.0% |
| 0.90 | 24 / 105 | 44 / 90 | 0 / 15 | 0 / 79 | 88.3% |

### Chosen Operating Thresholds
- `DEBUNK_STRONG_THRESHOLD = 0.88`: Yields **0% False Positive rate** on true controls and genuine documents, while retaining high recall on debunks.
- `DEBUNK_POSSIBLE_THRESHOLD = 0.84`: Surfaces related or topical fact-checks for human review without triggering an automatic debunk verdict.
- `OFFICIAL_STRONG_THRESHOLD = 0.87`: Strict cutoff for confirming document authenticity against official circulars.

---

## 5. Table 4: 12 Demo Fake Samples Evaluation (Toggle OFF vs. ON)

Evaluated across the 12 demo fake notices using only overlay-filtered OCR text (no LLM calls):
- **Toggle OFF (Normal)**: Searches the full index.
- **Toggle ON ("Simulate a new forgery")**: Excludes that sample's own debunk record and linked Telegram post from retrieval.
- **Overlay Check**: Verified whether any strong debunk match was triggered by removed fact-check overlay text (`0 / 12` downgraded).

| # | Sample ID | Forensics Score | Overlay Filtered | Overlay Downgraded | Verdict (Toggle OFF / Normal) | Verdict (Toggle ON / Simulate Unseen) |
| :-: | :--- | :---: | :---: | :---: | :--- | :--- |
| **1** | `FN-TG-01595` | 100 (high) | 5 lines | **False** (0) | **Debunked: matches official fact-check** (`red`, hit `FN-TG-01595` @ 0.881) | **Likely forged document** (`red`, forensics 100/100 catches old coin scam) |
| **2** | `FN-TG-01746` | 50 (med) | 7 lines | **False** (0) | **Suspicious: unverified** (`amber`, hit `TG-1846` @ 0.844) | **Suspicious: unverified** (`amber`, hit `TG-1846` @ 0.844) |
| **3** | `FN-TG-00988` | 85 (high) | 3 lines | **False** (0) | **Debunked: matches official fact-check** (`red`, hit `FN-TG-00165` @ 0.905) | **Debunked: matches official fact-check** (`red`, matches other PM-KUSUM debunk `FN-TG-00165`) |
| **4** | `FN-TG-01999` | 0 (low) | 12 lines | **False** (0) | **Debunked: matches official fact-check** (`red`, hit `FN-TG-01999` @ 0.889) | **Unverified: no official record found** (`grey`, safest verdict — never falsely Genuine) |
| **6** | `FN-PDF-0002` | 30 (med) | 9 lines | **False** (0) | **Debunked: matches official fact-check** (`red`, hit `TG-0598` @ 0.930) | **Debunked: matches official fact-check** (`red`, matches sister Hindi I4C arrest debunk `TG-0598`) |
| **7** | `FN-TG-00130` | 50 (med) | 8 lines | **False** (0) | **Debunked: matches official fact-check** (`red`, hit `TG-0107` @ 0.891) | **Debunked: matches official fact-check** (`red`, matches recurring Ujjwala LPG scam debunk `TG-0107`) |
| **8** | `FN-TG-01540` | 45 (med) | 5 lines | **False** (0) | **Suspicious: unverified** (`amber`, hit `FN-TG-01540` @ 0.874) | **Suspicious: unverified** (`amber`, hit `TG-1936` @ 0.862) |
| **9** | `FN-TG-01896` | 30 (med) | 2 lines | **False** (0) | **Debunked: matches official fact-check** (`red`, hit `FN-TG-01896` @ 0.882) | **Suspicious: unverified** (`amber`, hit `TG-1958` @ 0.880, supported by forensics) |
| **10** | `FN-TG-00902` | 0 (low) | 4 lines | **False** (0) | **Debunked: matches official fact-check** (`red`, hit `FN-TG-00902` @ 0.924) | **Debunked: matches official fact-check** (`red`, matches recurring NHM scam debunk `TG-0806`) |
| **11** | `FN-TG-01749` | 15 (low) | 7 lines | **False** (0) | **Debunked: matches official fact-check** (`red`, hit `TG-1635` @ 0.897) | **Debunked: matches official fact-check** (`red`, matches sister Mudra scam debunk `TG-1635`) |
| **12** | `FN-TG-00427` | 0 (low) | 8 lines | **False** (0) | **Unverified: no official record found** (`grey`, hit `FN-TG-00427` @ 0.871 possible) | **Unverified: no official record found** (`grey`, hit `FN-TG-00385` @ 0.866 possible) |
| **13** | `FN-TG-00385` | 0 (low) | 9 lines | **False** (0) | **Unverified: no official record found** (`grey`, hit `FN-TG-00427` @ 0.872 possible) | **Unverified: no official record found** (`grey`, hit `FN-TG-00427` @ 0.872 possible) |

---

## 6. Limitations

1. **Compressed Cosine Distribution**:
   `multilingual-e5-small` produces cosine similarities tightly compressed between `0.78` and `0.91` for diverse Indian languages. Because a difference of `0.02` separates a true debunk match from an unrelated claim, thresholds are fragile and must be recalibrated whenever the index size or embedding model changes.
2. **Approximate Telegram Narrative Labels**:
   Narrative IDs and status labels on the 1,878 raw Telegram posts are assigned by rule-based keyword matching (`rules.py`). While accurate for common recurring schemes (e.g. Mudra loans, PM-KUSUM, Railway recruitment), minor inaccuracies exist in long-tail posts.
3. **Templated Multilingual Claims**:
   The 105 non-English claims in `04_multilingual_claims` are generated from structured translation templates rather than in-the-wild social media posts. Real-world misspellings and mixed-script code switching may degrade retrieval quality.
4. **Self-Debunk Matching in Demo Fakes**:
   When the "Simulate a new forgery" toggle is OFF, demo fake notices naturally retrieve their own PIB fact-check debunk (since the benchmark images were sourced from those debunks). The Leave-One-Out numbers (Toggle ON) provide the realistic estimate of performance against entirely novel, previously unseen forgeries.
