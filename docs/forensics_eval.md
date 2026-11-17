# Stage 2 Forensic Check — Evaluation Report

This document summarizes the offline evaluation of Stage 2 (`factcheck/forensics/`) across all four benchmark datasets in the repository (`01_fake_notice_benchmark`, `02_official_source_corpus`, `04_multilingual_claims`, and `06_synthetic_forgeries`). All evaluations ran on cached OCR outputs and dataset text with **0 API calls**.

---

## 1. Real Fake Notices (`01_fake_notice_benchmark` — 12 Cached Notices)

> **In-sample note**: `in-sample: rules were designed after seeing these documents` (for the PIB overlay filter, `payment_to_account`, individual loan sanction `too_good_offer`, and `NHM`/`NHAI` issuer aliases).

`run_forensics` was evaluated on all **12 real fake notices** present in `data/cache/ocr_cache.sqlite` (all 12 are now included in `data/demo/demo_set.json`).

### Summary of Risk Levels on Cached Real Fakes (Before vs. After)
- **Before (baseline Stage 2)**: High: `1 / 12` (`8.3%`) | Medium: `6 / 12` (`50.0%`) | Low: `5 / 12` (`41.7%`)
- **After (overlay filter + `payment_to_account` + loan sanction offer + aliases — *in-sample: rules were designed after seeing these documents*)**:
  - **High risk (`>= 60`)**: `2 / 12` (`16.7%`) — `FN-TG-01595` (`100`), `FN-TG-00988` (`85`)
  - **Medium risk (`25–59`)**: `5 / 12` (`41.7%`) — `FN-TG-00130` (`50`), `FN-TG-01746` (`50`), `FN-TG-01540` (`45`), `FN-PDF-0002` (`30`), `FN-TG-01896` (`30`)
  - **Low risk (`< 25`)**: `5 / 12` (`41.7%`) — `FN-TG-01749` (`15`), `FN-TG-00385` (`0`), `FN-TG-00427` (`0`), `FN-TG-00902` (`0`), `FN-TG-01999` (`0`)

### Before / After Score Table (`in-sample: rules were designed after seeing these documents`)

| ID | Before Score & Level | After Score & Level | Before Detected Issuer | After Detected Issuer | Before Cue IDs | After Cue IDs | PIB Overlay Lines Filtered |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :---: |
| **`FN-TG-01595`** | `100 / 100` (`high`) | **`100 / 100` (`high`)** | `RBI` | `RBI` | `fee_demand`, `lookalike_domain` | `fee_demand`, `lookalike_domain` | 5 |
| **`FN-TG-00988`** | `50 / 100` (`medium`) | **`85 / 100` (`high`)** | `MNRE` | `MNRE` | `fee_demand`, `wrong_signatory_title` | `fee_demand`, **`payment_to_account`**, `wrong_signatory_title` | 3 |
| **`FN-TG-00130`** | `50 / 100` (`medium`) | **`50 / 100` (`medium`)** | `OMC` | `OMC` | `fee_demand`, `urgency_threat` | `fee_demand`, `urgency_threat` | 8 |
| **`FN-TG-01746`** | `50 / 100` (`medium`) | **`50 / 100` (`medium`)** | `MHA` | `MHA` | `lookalike_domain`, `spelling_errors` | `lookalike_domain`, `spelling_errors` | 7 |
| **`FN-TG-01540`** | `30 / 100` (`medium`) | **`45 / 100` (`medium`)** | `MOCI` | `MOCI` | `mixed_issuers`, `wrong_signatory_title` | **`date_anomaly`**, `mixed_issuers`, `wrong_signatory_title` | 5 |
| **`FN-PDF-0002`** | `30 / 100` (`medium`) | **`30 / 100` (`medium`)** | `I4C` | `I4C` | `urgency_threat`, `issuer_never_does` | `urgency_threat`, `issuer_never_does` | 9 |
| **`FN-TG-01896`** | `30 / 100` (`medium`) | **`30 / 100` (`medium`)** | `SCI` | `SCI` | `urgency_threat`, `mixed_issuers` | `urgency_threat`, `mixed_issuers` | 2 |
| **`FN-TG-01749`** | `0 / 100` (`low`) | **`15 / 100` (`low`)** | `MUDRA` | `MUDRA` | `[]` | **`too_good_offer`** | 7 |
| **`FN-TG-00902`** | `15 / 100` (`low`) | **`0 / 100` (`low`)** | Not detected | **`MOHFW`** | `personal_contact` *(on `NHM7798904510` ID)* | `[]` *(ID prefix excluded from mobile check)* | 4 |
| **`FN-TG-00385`** | `0 / 100` (`low`) | **`0 / 100` (`low`)** | Not detected | **`MORTH`** | `[]` | `[]` | 9 |
| **`FN-TG-00427`** | `0 / 100` (`low`) | **`0 / 100` (`low`)** | Not detected | **`MORTH`** | `[]` | `[]` | 8 |
| **`FN-TG-01999`** | `0 / 100` (`low`) | **`0 / 100` (`low`)** | `RRB` | `RRB` | `[]` (`ref_status` info) | `[]` (`ref_status` info) | 6 |

### Per-Notice Side-by-Side Comparison

| ID | Set | Risk Score & Level | Claimed Issuer | Detected Issuer | Cue IDs Found (`run_forensics`) | Hand-Annotated `forgery_cues` (`fake_notices.jsonl`) | Uncropped PIB Overlay in OCR? |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :---: |
| **`FN-TG-01595`** | Eval | **`100 / 100` (`high`)** | RBI | Reserve Bank of India (`RBI`) | `fee_demand` (+35), `lookalike_domain` (+35 × 2: `governorb.org`, `governor.org.in`) | `'24 hours express delivery' and 'special offer' stamps`; `fees: 'income tax department office form charge Rs 700', 'delivery permission charge'`; `lists Finance Secretary and Ministry of Finance as addressees on an RBI letter`; `'Government RBI all-India permission'`; `Hinglish line 'delivery payment prapt karne ka time'` | Yes (`#PIBFactCheck`, `FAKE` stamp) |
| **`FN-TG-00130`** | Demo | **`50 / 100` (`medium`)** | OMC (BPCL / Ujjwala) | Oil Marketing Companies / MoPNG (`OMC`) | `fee_demand` (+35: `registration fees of Rs. 12,500/-`), `urgency_threat` (+15: `within 24 hours`) | *(None annotated in `fake_notices.jsonl`)* | Yes (`#PIBFactCheck`, `यह पत्र भारत पेट्रोलियम द्वारा जारी नहीं किया गया है!`) |
| **`FN-TG-00988`** | Demo | **`50 / 100` (`medium`)** | MNRE (PM-KUSUM) | Ministry of New and Renewable Energy (`MNRE`) | `fee_demand` (+35: `Registration Charges is Refundable Rs. 8000.00`), `wrong_signatory_title` (+15: `Branch Head`) | `bank account named 'PM Kusum Yojna' at a branch`; `'Registration Charges is Refundable Rs. 8000.00'`; `signatory 'Branch Head' for a ministry scheme`; `same 'At the outset we welcome you to world of...' phrasing as fake MUDRA letters` | Yes (`This letter is #fake`, `@PIBFactCheck`) |
| **`FN-TG-01746`** | Eval | **`50 / 100` (`medium`)** | MHA | Ministry of Home Affairs (`MHA`) | `lookalike_domain` (+35: `mina.gov.is`), `spelling_errors` (+15: `Goverment`) | *(None annotated in `fake_notices.jsonl`)* | Yes (`Fake letter attributed to Union Home Minister`, `@PIBFactCheck`) |
| **`FN-PDF-0002`** | Demo | **`30 / 100` (`medium`)** | I4C | Indian Cyber Crime Coordination Centre (`I4C`) | `urgency_threat` (+15: `24 घंटे के भीतर`), `issuer_never_does` (+15: `POCSO`) | `fear/urgency: reply within 24 hours or face arrest`; `mixes logos of I4C, Delhi Police, Intelligence Bureau and 'Cyber Crime' seals on one letter`; `rubber stamp 'certified copy' placed over body text`; `signatory named as Director of Intelligence Bureau on an I4C letter` | Yes (`PIB Fact Check`, `यह पत्र फ़र्ज़ी है`) |
| **`FN-TG-01540`** | Demo | **`30 / 100` (`medium`)** | Dept. of Commerce (MOCI) | Ministry of Commerce and Industry (`MOCI`) | `mixed_issuers` (+15: `Ministry of Commerce` + `Ministry of Civil Aviation`), `wrong_signatory_title` (+15: `Additional Chief Secretary`) | `shared via a propaganda X account with a news-style link`; `reference 'No.68/03' lacks the department/file structure of real GoI letters`; `Ministry of Civil Aviation address in the footer of a Commerce letter`; `signatory title 'Additional Chief Secretary, India's Ministry of Commerce' (ACS is a state cadre post)` | Yes (`Fake claims about suspension of trade`, `#PIBFactCheck`, `FAKE`) |
| **`FN-TG-01896`** | Demo | **`30 / 100` (`medium`)** | Supreme Court + Ministry of Finance | Supreme Court of India (`SCI`) | `urgency_threat` (+15: `within one hour`), `mixed_issuers` (+15: `Ministry of Finance` + `Supreme Court` + `CBI`) | `heading 'GOVERNMENTAL AFFAIR' and 'Financial Transaction Committee Order' - no such body`; `Supreme Court and Ministry of Finance on one letterhead`; `orders transfer of all funds to an individual's SBI savings account`; `signed by 'Prosecutor CBI' with Supreme Court Bar Association seal`; `deadline: within one hour of opening` | Yes (`Fake notice impersonating Supreme Court`, `@PIBFactCheck`) |
| **`FN-TG-00902`** | Demo | **`15 / 100` (`low`)** | MOHFW (NHM) | Not detected | `personal_contact` (+15: `7798904510` inside `NHM7798904510`) | *(None annotated in `fake_notices.jsonl`)* | Yes (`यह नियुक्ति पत्र फ़र्ज़ी है`, `@PIBFactCheck`) |
| **`FN-TG-00385`** | Demo | **`0 / 100` (`low`)** | MORTH | Not detected | `[]` | *(None annotated in `fake_notices.jsonl` — viral Hindi WhatsApp text graphic claiming 12-hour return toll slips are free)* | Yes (`यह दावा फ़र्ज़ी है!`, `#PIBFACTCHECK`) |
| **`FN-TG-00427`** | Demo | **`0 / 100` (`low`)** | MORTH | Not detected | `[]` | *(None annotated in `fake_notices.jsonl` — duplicate graphic of the 12-hour toll plaza rumour attributed to Nitin Gadkari)* | Yes (`यह दावा फ़र्ज़ी है!`, `#PIBFACTCHECK`) |
| **`FN-TG-01749`** | Demo | **`0 / 100` (`low`)** | MUDRA | PM Mudra Yojana (`MUDRA`) | `[]` | *(None annotated in `fake_notices.jsonl` — fake Mudra loan approval table with `AN ISO 9001:2008 CERTIFICATES COMPANY` and `Kye Verfications`, no upfront fee amount printed on this page)* | Yes (`pib FACT CHECK`, `This letter is Fake`) |
| **`FN-TG-01999`** | Demo | **`0 / 100` (`low`)** | Railway Board (`RRB`) | Railway Recruitment Boards / Ministry of Railways (`RRB`) | `[]` (`ref_status` info +0) | `high-quality forgery: correct Railway Board letterhead, bilingual header and RBE-style reference`; `dated 06.10.2026 with a plausible PLB amount - only a lookup in Railway Board's RBE index can refute it`; `official-looking email of a named Deputy Director` | Yes (`FPIB FACT CHECK`, `The letter is FAKE`, `#PIBFactCheck`) |

### Uncropped Demo Fakes Note
All **10 demo fake images** (`FN-PDF-0002`, `FN-TG-00130`, `FN-TG-00385`, `FN-TG-00427`, `FN-TG-00902`, `FN-TG-00988`, `FN-TG-01540`, `FN-TG-01749`, `FN-TG-01896`, `FN-TG-01999`) — as well as the 2 eval-cached images (`FN-TG-01595`, `FN-TG-01746`) — still contain **PIB Fact Check overlay text** in their cached OCR (`#PIBFactCheck`, `यह पत्र फ़र्ज़ी है`, `The letter is FAKE`, `+91 8799711259`, `socialmedia@pib.gov.in`, `t.me/PIB_FactCheck`) because the image files on disk are single-panel PIB Fact Check composite graphics where the stamp and header/footer banners are drawn directly over or around the letter.
- **How this affects scores**:
  1. The PIB Fact Check banner prepend shifts line numbers downward, pushing parts of the actual forged letterhead past the 15-line letterhead window (`detect_issuer` and `check_reference_number`).
  2. The red `"FAKE"` / `"फ़र्ज़ी"` rubber stamp placed across the middle of letters (e.g., `FN-TG-01999`, `FN-TG-01540`, `FN-TG-00130`) occludes words in the body, causing OCR to produce broken word fragments (`"egiste"`, `"depo"`, `"surri"`).

### Most Common Missed Cue Types (from Hand Annotations in `01_fake_notice_benchmark`)
Across the 130 hand-annotated `forgery_cues` in `notices.jsonl`, the cues missed by Stage 2 text forensics fall into five main categories:
1. **Visual Stamps, Seals & Watermarks (Cannot be seen by text rules)**:
   - Rubber stamps placed over body text (`"rubber stamp 'certified copy' placed over body text"`, `"'GOVT OF INDIA' rubber stamp"`, `"'Loan Approved' circular stamp"`, `"'PAID' stamp"`, `"'24 hours express delivery' and 'special offer' stamps"`, `"amateur round seal 'Department of Income Tax'"`, `"Supreme Court Bar Association seal"`).
2. **Composite Logos, Emblem Misuse & Photos (Visual-only)**:
   - Stacked or mismatched agency emblems (`"mixes logos of I4C, Delhi Police, Intelligence Bureau and 'Cyber Crime' seals on one letter"`, `"HP Gas, HPCL and cylinder logos stacked"`, `"G20 and Azadi ka Amrit Mahotsav logos as decoration"`, `"PM photo on loan letter"`, `"WhatsApp logo"`, `"Skill India logo used on a recruitment letter"`).
3. **Payee Bank Account & Private Address Anomalies (Semantic / Entity-level)**:
   - Transferring funds to an individual's personal savings account or a scheme-named account at a commercial branch (`"orders transfer of all funds to an individual's SBI savings account"`, `"bank account named 'PM Kusum Yojna' at a branch"`, `"'mudra finance' payee account at India Post Payments Bank"`, `"private Gurgaon address (Udyog Vihar) for a government scheme"`).
4. **Cross-Document Template Reuse & Grammar/Style Cues**:
   - Boilerplate scam templates reused across unrelated schemes (`"same 'At the outset we welcome you to world of...' phrasing as fake MUDRA letters"`, `"signatory 'Er. Soumyendu Ganguly' - same name as on FN-PDF-0249 and FN-PDF-0016"`), awkward grammar (`"'AN ISO 9001:2008 CERTIFICATES TELECOM COMPANY' grammar error"`), or non-existent body names (`"heading 'GOVERNMENTAL AFFAIR' and 'Financial Transaction Committee Order' - no such body"`).
5. **High-Quality Format-Valid Forgeries Requiring Corpus/Index Lookup (Stage 3/4)**:
   - Notices like `FN-TG-01999` (Railway Board PLB circular `RBE No. 101/2026`) and `FN-PDF-0149` (Gazette `S.O.` notification) have clean typography, valid reference formats, and no fee demands or threats; as noted in the dataset annotations, *only an official-source index lookup can refute them*.

---

## 2. Genuine Official Corpus (`02_official_source_corpus` — 79 Documents)

| Metric | BEFORE General Rule Tuning | AFTER General Rule Tuning |
| :--- | :---: | :---: |
| **Low risk (`< 25`)** | **75 / 79** (`94.9%`) | **79 / 79** (`100.0%`) |
| **Medium risk (`25–59`)** | **4 / 79** (`5.1%`) | **0 / 79** (`0.0%`) |
| **High risk (`>= 60`)** | **0 / 79** (`0.0%`) | **0 / 79** (`0.0%`) |

### Top 5 Genuine Documents by Risk Score (After Tuning)
1. **`OFF-0B6328356A`** (`CBSE`, ref `Acad-56/2026`) — **`15 / 100` (`low`)**: `personal_contact` (`warning`, `+15`: `'9205855997'`)
2. **`OFF-4A2E01CE80`** (`CBSE`, ref `Acad-65/2026`) — **`15 / 100` (`low`)**: `personal_contact` (`warning`, `+15`: `'manjit.cbse@gmail.com'`)
3. **`OFF-5E1BCD9F8C`** (`CBSE`, ref `Acad-64/2026`) — **`15 / 100` (`low`)**: `personal_contact` (`warning`, `+15`: `'manjit.cbse@gmail.com'`)
4. **`OFF-BBBE3D2F96`** (`CBSE`, ref `None`) — **`15 / 100` (`low`)**: `personal_contact` (`warning`, `+15`: `'manjit.cbse@gmail.com'`)
5. **`OFF-BE0799B271`** (`RBI`, ref `2026-2027/1377`) — **`15 / 100` (`low`)**: `personal_contact` (`warning`, `+15`: `'92298 29909'`)

---

## 3. Multilingual Claims (`04_multilingual_claims` — 120 Claims Across 7 Languages)

In `eval_forensics.py`, fee and urgency recall are reported strictly on **claims annotated with that slot** (`claims with >=1 detection / claims in that slot`, so the numerator never exceeds the denominator), with **extra detections** on fake claims outside that slot reported in a separate column:
- **Fee-slot claims (`slots.fee_inr != null`)**: `5` per language (`NAR-MUDRA-LOAN`, `NAR-TRAI-TOWER`, `NAR-RBI-PRIZE-EXCHANGE`, `NAR-OMC-DEALERSHIP`, `NAR-JOB-FEE`).
- **Extra `fee_demand` detections (`+1` per language)**: `NAR-COURT-NOTICE` demands immediate payment of a penalty amount (`"deposit penalty amount immediately to avoid arrest"`), which triggers `fee_demand` even though `slots.fee_inr` is `null` (unquantified amount).
- **Urgency-slot claims (`slots.deadline != null`)**: `5` per language (`NAR-I4C-LETTER`, `NAR-BSNL-KYC`, `NAR-POLICY-ORDER`, `NAR-COURT-NOTICE`, `NAR-BANK-KYC-BLOCK`).
- **Extra `urgency_threat` detections (`+2` to `+3` per language)**: `NAR-MUDRA-LOAN` (`"in 24 hrs"`), `NAR-DEFENCE-FORGED-LETTER` (`"Share before it is deleted!"`), and `NAR-EPAN-PHISHING` (`"download your e-PAN card immediately"`).

| Language | Fake Claims | Fee-Slot Recall (`det / slot`) | Extra Fee Detections (non-slot fakes) | Urgency-Slot Recall (`det / slot`) | Extra Urgency Detections (non-slot fakes) | Any Forensic Cue (`det / fake`) | True Control Claims | True Control False Positives (`med`/`high`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`bn`** (Bengali) | 15 | **5 / 5** | `+1` | **5 / 5** | `+3` | 13 / 15 | 0 | 0 |
| **`en`** (English) | 15 | **5 / 5** | `+1` | **5 / 5** | `+2` | 13 / 15 | 5 | **0 (0%)** |
| **`hi`** (Hindi) | 15 | **5 / 5** | `+1` | **5 / 5** | `+3` | 13 / 15 | 5 | **0 (0%)** |
| **`hi-Latn`** (Hinglish) | 15 | **5 / 5** | `+1` | **5 / 5** | `+2` | 12 / 15 | 5 | **0 (0%)** |
| **`mr`** (Marathi) | 15 | **5 / 5** | `+1` | **5 / 5** | `+3` | 13 / 15 | 0 | 0 |
| **`ta`** (Tamil) | 15 | **5 / 5** | `+1` | **5 / 5** | `+3` | 13 / 15 | 0 | 0 |
| **`te`** (Telugu) | 15 | **5 / 5** | `+1` | **5 / 5** | `+3` | 13 / 15 | 0 | 0 |

---

## 4. Synthetic Forgeries (`06_synthetic_forgeries` — 4 Cached Samples)

| Sample ID | Label | Risk Score & Level | Ground-Truth Cues (`labels.jsonl`) | Detected Cues (`run_forensics`) |
| :--- | :---: | :---: | :--- | :--- |
| **`SYN-0001`** | `clean` | **`0 / 100` (`low`)** | `[]` | `[]` |
| **`SYN-0002`** | `clean` | **`0 / 100` (`low`)** | `[]` | `[]` |
| **`SYN-0031`** | `forged` | **`80 / 100` (`high`)** | `lookalike_domain`, `personal_contact`, `too_good_offer`, `urgency_threat` | `lookalike_domain`, `personal_contact`, `too_good_offer`, `urgency_threat` |
| **`SYN-0033`** | `forged` | **`60 / 100` (`high`)** | `ref_format_wrong`, `spelling_errors`, `urgency_threat`, `wrong_signatory_title` | `ref_format_wrong`, `spelling_errors`, `urgency_threat`, `wrong_signatory_title` |

---

## 5. Limitations

1. **In-Sample Rule Tuning on the Genuine Corpus**: The four general rule refinements (subdomain handling for `.gov.in` / `mygov.in`, header-scoped reference format checks, event-date context filtering, and PDF line-wrap truncation guards) were inspected and tuned on the same 79 genuine documents in `02_official_source_corpus` on which false-positive rates are reported. Held-out genuine circulars from unseen ministries may still trigger warnings (for example, when an official circular uses a non-`.gov.in` project domain or lists a coordinator's personal webmail/mobile number).
2. **Templated, LLM-Assisted Multilingual Claims**: The 120 claims in `04_multilingual_claims` were authored (with LLM assistance) from 15 canonical narrative templates across 7 languages and are pending native-speaker review. Real-world social media forwards exhibit noisier spelling, regional dialects, and indirect phrasing than templated sentences.
3. **Small Cached Synthetic Sample Size**: Only **4 of the 60** synthetic images (`SYN-0001`, `SYN-0002`, `SYN-0031`, `SYN-0033`) are currently in `ocr_cache.sqlite` because live OCR calls were restricted to preserve the daily API quota. Full precision/recall across all 60 synthetic images remains to be measured once local VLM OCR or additional cache warming is run.
4. **Visual Forgery Cues Are Not Checked**: Stage 2 operates strictly on OCR text and extracted fields. It cannot inspect visual forgery cues such as pasted logos, mismatched agency emblems, fake circular rubber stamps (`"Loan Approved"`, `"PAID"`), celebrity/PM photographs, or forged signatures.
5. **Uncropped PIB Fact Check Overlays in Cached Real Fakes**: The 12 cached real fake notices in `01_fake_notice_benchmark` are PIB Fact Check composite graphics whose OCR text includes PIB's debunking headers/footers and `"FAKE"` stamp text, which shifts line positions and partially occludes underlying letter text.
6. **Plausible Policy & Exam Rumours Require Stage 3/4 Source Matching**: High-quality forgeries with valid formatting and no payment/threat language (such as `FN-TG-01999` on Railway PLB bonus or `FN-TG-00385` on toll-plaza rules) score `0 / 100` (`low`) in text forensics by design; catching them requires Stage 3/4 claim extraction and verification against official source records.

---

## 6. Multilingual Forensics Expansion across all 12 SUPPORTED_LANGS

Forensic checks in `factcheck/forensics/rules.py` and `factcheck/extract/ocr/fields.py` have been extended from the initial 7 languages (`en, hi, hi-Latn, mr, bn, ta, te`) to all **12 official languages plus Hinglish** (`en, hi, bn, mr, te, ta, gu, kn, ml, pa, or, ur, hi-Latn`).

### 1. Keyword Cues Across All Languages
The following cue dictionaries were expanded:
- **`FEE_PAYMENT_PATTERNS`**: Demands for registration, processing, file, or allotment charges across all 12 languages.
- **`FEE_NEGATION_RE`**: Phrases clarifying absence of fees ("no fee", "free of cost", "no registration fee", "વિનામૂલ્યે", "ಶುಲ್ಕವಿಲ್ಲ", "സൗജന്യം", "ਮੁਫ਼ਤ", "ମାଗଣା", "بلا معاوضہ") across all 12 languages to suppress false positives on legitimate notices.
- **`URGENCY_THREAT_PATTERNS`**: 24/48-hour deadlines, arrest warrants ("ڈیجیٹل گرفتاری", "ਗ੍ਰਿਫ਼ਤਾਰੀ ਵਾਰੰਟ", "ધરપકડ"), and SIM/account suspension threats across all 12 languages.
- **`TOO_GOOD_OFFER_PATTERNS`**: Lures such as free laptop schemes, 5G tower rent promises, and old coin windfalls across all 12 languages.
- **`PAYMENT_INSTRUCTION_RE` & `ACCOUNT_DETAIL_RE`**: Bank transfer verbs and account number/IFSC cues across all 12 languages.

> **Status Notice**: All newly added keyword lists for **Gujarati (`gu`)**, **Kannada (`kn`)**, **Malayalam (`ml`)**, **Punjabi (`pa`)**, **Odia (`or`)**, and **Urdu (`ur`)** are marked **`needs native-speaker review`** in `factcheck/forensics/rules.py` and require linguistic verification against regional vernacular spam samples.

### 2. Multilingual Reference Number Extraction
`factcheck/extract/ocr/fields.py` now recognizes reference number and circular prefixes across all Indic scripts (Devanagari, Bengali, Gujarati, Gurmukhi, Odia, Tamil, Telugu, Kannada, Malayalam, and Arabic/Urdu scripts) and normalizes native Indic digits to standard ASCII numerals before matching.

### 3. Regional Issuer Aliases
Regional script names for major central issuing authorities were added to `ISSUER_ALIASES` in `factcheck/forensics/rules.py` for:
- Reserve Bank of India (`RBI`)
- Securities and Exchange Board of India (`SEBI`)
- Central Board of Secondary Education (`CBSE`)
- Press Information Bureau (`PIB`)
- Ministry of Home Affairs (`MHA`)
- Ministry of Education (`MOE`)
- Ministry of Health & Family Welfare (`MOHFW`)
- Ministry of New and Renewable Energy (`MNRE`)
- Railway Recruitment Boards / Ministry of Railways (`RRB`)

> **Status Notice**: All regional issuer aliases in regional scripts (`gu`, `kn`, `ml`, `pa`, `or`, `ur`, `mr`, `bn`, `ta`, `te`) in `factcheck/forensics/rules.py` are marked **`needs native-speaker review`**.

### 5. Negation Scope Constraint
Fee negation only suppresses a `fee_demand` finding when the negation phrase directly modifies the fee term (within ~3 words without crossing sentence boundaries, e.g., "no fee", "fee-free", "free of cost", "शुल्क नहीं"). A bare "free" modifying an item or offer elsewhere in the message (e.g. "Free laptop scheme. Registration fee Rs 199.") strictly does NOT suppress the fee demand, ensuring fraudulent lures with upfront application charges are reliably detected.

### 4. Transliterated Transcript Handling
When an audio voice note is tagged with an Indic language (e.g., `te`, `bn`, `gu`, `ml`) but the transcribed text is rendered in a different script (e.g., Whisper outputting Devanagari phonetically instead of the language's native script):
- `transcript_transliterated` is set to `True`.
- Claim confidence is capped at `<= 0.35` (treated as weak language recognition).
- An amber warning banner is displayed: *"Transcript is in a different script than the spoken language: checks may miss warning signs. Enable IndicConformer for this language."*
- To prevent spurious matches or misses from applying mismatched script rules, forensic text analysis skips non-applicable native script patterns and evaluates Hindi and English keyword lists only.
