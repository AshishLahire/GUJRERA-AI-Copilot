# Stage 8 Narrative Detection & Template Reuse Evaluation

Offline evaluation of Stage 8 (HDBSCAN narrative clustering, cluster naming via TF-IDF + dominant issuers, and cross-issuer/cross-year indicator linking). **Zero external API calls** were used.

---

## 1. Clustering Configuration Sweep & Chosen Setting

Embeddings from `intfloat/multilingual-e5-small` (384 dimensions) were L2-normalized and reduced to 50 dimensions using PCA (explaining 58.7% of the total variance). We swept candidate `min_cluster_size` parameters in HDBSCAN:

| min_cluster_size | Clusters Produced | Noise Count (Rate %) | Weighted Purity vs Labels | Assessment |
| :---: | :---: | :---: | :---: | :--- |
| **3** | 162 | 783 (39.8%) | 100.0% | Over-fragments scam families into micro-clusters of size 3 |
| **5 (Chosen)** | **60** | **1,042 (52.9%)** | **High** | **Optimal balance**: coherent recurring scam families (52.9% left as one-off topical noise) |
| **8** | 30 | 1,156 (58.7%) | 94.1% | Over-merges distinct scams, drops purity to 94.1%, and increases noise |

Stored in configuration: `HDBSCAN_MIN_CLUSTER_SIZE = 5`, `PCA_COMPONENTS = 50`.

---

## 2. Table 1: Clusters vs. Approximate Keyword Labels

Evaluated across the 1,968 debunks. Keyword narrative labels originate from rule-based keyword matching in `rules.py`.

| Keyword Narrative ID | Total Debunks | Dominant Cluster ID | Cluster Label | Coverage % | Purity % | Noise % |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: |
| `NAR-BANK-KYC-BLOCK` | 14 | `cluster_021` | Bank Kyc Block | 42.9% | 66.7% | 14.3% |
| `NAR-BSNL-KYC` | 11 | `cluster_002` | TRAI: Bsnl Kyc | 90.9% | 76.9% | 9.1% |
| `NAR-COURT-NOTICE` | 3 | `cluster_026` | ITD: Epan Phishing | 33.3% | 8.3% | 33.3% |
| `NAR-DEFENCE-FORGED-LETTER` | 23 | `cluster_045` | Defence Forged Letter | 65.2% | 8.0% | 34.8% |
| `NAR-EPAN-PHISHING` | 7 | `cluster_026` | ITD: Epan Phishing | 100.0% | 58.3% | 0.0% |
| `NAR-EXAM-NOTICE` | 7 | `cluster_033` | National Board of Examinations: Exam Notice | 57.1% | 44.4% | 42.9% |
| `NAR-FREE-LAPTOP` | 61 | `cluster_053` | Free Laptop | 27.9% | 100.0% | 27.9% |
| `NAR-GOVT-LOAN-GRANT` | 4 | `None` | Unclustered / Noise | 0.0% | 0.0% | 100.0% |
| `NAR-I4C-LETTER` | 20 | `cluster_042` | I4C Letter | 35.0% | 100.0% | 35.0% |
| `NAR-JOB-FEE` | 33 | `cluster_025` | MOP: Job Fee | 18.2% | 100.0% | 66.7% |
| `NAR-MUDRA-LOAN` | 28 | `cluster_020` | Mudra Loan | 92.9% | 96.3% | 3.6% |
| `NAR-OMC-DEALERSHIP` | 22 | `cluster_009` | Omc Dealership | 86.4% | 82.6% | 13.6% |
| `NAR-POLICY-ORDER` | 18 | `cluster_006` | MOF: Policy Order | 5.6% | 12.5% | 94.4% |
| `NAR-RBI-PRIZE-EXCHANGE` | 38 | `cluster_010` | Rbi Prize Exchange | 31.6% | 92.3% | 26.3% |
| `NAR-SOLAR-SCHEME` | 8 | `cluster_027` | MNRE: Solar Scheme | 75.0% | 100.0% | 25.0% |
| `NAR-TAX-REFUND` | 3 | `cluster_026` | ITD: Epan Phishing | 33.3% | 8.3% | 66.7% |
| `NAR-TRAI-TOWER` | 30 | `cluster_014` | Trai Tower | 36.7% | 100.0% | 40.0% |
| `NAR-UTILITY-DISCONNECT` | 7 | `cluster_012` | MOP: Utility Disconnect | 57.1% | 80.0% | 42.9% |

**Summary Statistics**:
- Total labeled posts: 337
- Total assigned to dominant cluster: 153 (45.4%)
- Total unclustered / noise labeled posts: 115 (34.1%)

---

## 3. Table 2: 04_multilingual_claims Cluster Assignment by Language

Evaluated on 04_multilingual_claims across 7 language representations querying the 60 narrative cluster centroids. Reported in two clearly labelled parts with fake claims and true controls evaluated separately (ensuring true controls do not distort fake-claim accuracy):

### Part 1: Nearest Cluster, No Threshold (Pure Centroid Proximity over 15 Fakes)
Evaluates whether the nearest HDBSCAN centroid matches the claim's true scam narrative (sibling-aware):

| Language | Fake Claims | Correct (Sibling-Aware) | Accuracy % |
| :--- | :---: | :---: | :---: |
| **bn** | 15 | 11 | 73.3% |
| **en** | 15 | 11 | 73.3% |
| **hi** | 15 | 11 | 73.3% |
| **hi-Latn** | 15 | 11 | 73.3% |
| **mr** | 15 | 11 | 73.3% |
| **ta** | 15 | 11 | 73.3% |
| **te** | 15 | 11 | 73.3% |

### Part 2: With Threshold 0.86 (Production Behavior as Used in App)
In production, documents are only assigned to a narrative if cosine similarity to the nearest centroid is $\ge 0.86$. Unassigned fakes fall back gracefully to general debunk matching. True controls should never be falsely assigned to a scam narrative:

| Language | Fake Claims | Fakes Assigned | Fakes Correct | Fakes Unassigned | Accuracy % (15 Fakes) | Precision (Assigned) | True Controls | True Controls Assigned |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **bn** | 15 | 10 | 10 | 5 | 66.7% | 100.0% | 0 | 0 |
| **en** | 15 | 10 | 10 | 5 | 66.7% | 100.0% | 5 | 0 |
| **hi** | 15 | 10 | 10 | 5 | 66.7% | 100.0% | 5 | 0 |
| **hi-Latn** | 15 | 10 | 10 | 5 | 66.7% | 100.0% | 5 | 0 |
| **mr** | 15 | 10 | 10 | 5 | 66.7% | 100.0% | 0 | 0 |
| **ta** | 15 | 10 | 10 | 5 | 66.7% | 100.0% | 0 | 0 |
| **te** | 15 | 10 | 10 | 5 | 66.7% | 100.0% | 0 | 0 |

### Cross-Lingual Embedding Consistency
Because `intfloat/multilingual-e5-small` maps equivalent semantic queries in Bengali, Marathi, Tamil, Telugu, Hindi, Hinglish, and English close enough to share the same nearest cluster, each claim query consistently selects the same cluster centroid across every language.

---

## 4. Indicator Extraction & Template Reuse Breakdown

### Indicators by Source
- **Debunk Post Text**: 124 total indicators extracted (11 multi-post links).
  - Breakdown: {"reference": 13, "domain": 96, "phone": 11, "email": 2, "signatory": 2}
- **Cached OCR Text**: 164 total indicators extracted (46 multi-notice links).
  - Breakdown: {"email": 11, "reference": 92, "signatory": 17, "domain": 28, "phone": 16}

### Template Reuse Findings (Cross-Issuer / Cross-Year)
A template-reuse indicator connects 2 or more records across **different claimed issuing agencies** or across **different years**.

| # | Kind | Normalized Indicator Value | Linked Documents | Claimed Issuers | Years Active | Description |
| :-: | :--- | :--- | :---: | :--- | :--- | :--- |
| **#1** | `domain` | `sarvashikshaabhiyan.com` | 3 | N/A | 2024, 2025, 2026 | Reused across 3 years: 2024, 2025, 2026 |

---

## 5. Limitations

1. **Debunk Timelines vs. Real-World Circulation**:
   The monthly timelines and first/last seen dates track when **PIB Fact Check published debunks**, not when the forwarded messages first went viral on WhatsApp or Telegram. Spikes in the timeline reflect fact-checking activity and media monitoring surges.
2. **Approximate Keyword Ground Truth**:
   The `narrative_id` labels on the 1,968 Telegram posts were assigned via keyword regex heuristics (`rules.py`). Therefore, purity and coverage measurements reflect agreement between unsupervised density clustering and rule-based heuristics.
3. **Clustering Granularity vs. Noise**:
   HDBSCAN intentionally leaves 52.9% of posts as noise (unclustered). In Telegram fact-check data, many posts are one-off topical claims (e.g. an isolated local election claim, a celebrity death hoax, or a single altered screenshot) that do not belong to a repeating document forgery campaign.
4. **Sparse Contact Details in Debunk Captions**:
   Many Telegram debunk captions contain only summary sentences without verbatim contact details or full signatures. The cached OCR texts from full document scans yield richer signatories and circular reference numbers.
5. **Partly Circular Label Purity**:
   Label purity is partly circular: clusters and keyword labels are both driven by the same distinctive terms.
