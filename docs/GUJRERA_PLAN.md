# GUJRERA AI Copilot: Architecture and Build Plan

_Drafted 2026-11-17. Status: draft for team review. Based on the problem brief; the Stage 2 requirements zip has not been read yet, so scope and dates may change (see section 11)._

---

## 1. Goal and Stage 2 scope

Build one multilingual copilot (Gujarati, Hindi, English, mixed input, text and voice) for citizens, developers, agents and GUJRERA officers, with four capabilities plus our differentiator:

| # | Capability | Who | Data in demo |
|:-:|:--|:--|:--|
| T | **RERA trust check** (differentiator) | Citizens | Public portal data where possible, else seeded |
| 1 | Promoter and project profiles | Everyone | Public portal data where possible, else seeded |
| 2 | Conversational complaint filing and tracking | Citizens | Mock complaint workflow adapter (labelled **MOCK**) |
| 3 | Developer self-service | Developers, agents | Seeded per-developer data (labelled **MOCK**) |
| 4 | Regulatory analytics | Officers | Same database, read-only |

**Order of work:** T first. It reuses the most Pramaan code and is what sets us apart. Next comes 1, which the chat and analytics both depend on. Then 2, 3 and 4.

**Non-negotiables (from the brief):**
- Every factual answer cites a RERA record (record type, ID, date). If no record supports an answer, the copilot says "not found" and never guesses.
- Mock data and mock integrations are visibly labelled in the UI and API responses (`is_mock: true`).
- Access control is enforced in code, never by the LLM.
- Everything runs fully offline (Ollama) so it can be hosted on-premise.

### 1.1 How the challenge is scored

From the AI CoE AI Innovation Challenge page (gujarat.coe-iot.com). The jury evaluates after mentoring sessions on proposals; winners get a paid PoC with GUJRERA.

| Parameter | Weight | What it means for the build |
|:--|:-:|:--|
| Solution relevance | 20% | Cover all four asks from the use case, plus the trust check |
| Technical capability | 20% | Show the stack working: hybrid RAG, guarded text-to-SQL, Gujarati speech and OCR, with measured numbers |
| Past experience | 15% | Pramaan and JanSeva Karnataka (from the deck) |
| Innovation and uniqueness | 15% | RERA trust check; open-source and self-hosted models |
| Scalability potential | 10% | Stateless API, Postgres-ready schema, async OCR/speech workers |
| Implementation readiness | 10% | **A working demo, not slides**: this is why the prototype matters |
| Security and privacy | 5% | Role scoping in code, read-only analytics, audit log, DPDP |
| Cost and timeline | 5% | Already set in the deck: 16 weeks, ₹26 L |

### 1.2 Commitments made in the Stage 1 deck

The prototype must not contradict these:
- Answers are cited to a RERA record, or the copilot says "not found".
- Self-hosted open models, no paid API by default, deployable on government cloud or on-premise.
- Gujarati, Hindi and English, by text, voice and scanned documents.
- Promoters see only their own data; officer queries are read-only, with the SQL shown and logged.
- Trust check verdicts named in the deck: registration not found, promoter name mismatch, registration lapsed, advertised details differ from approved. Each links to the registry record.
- Demo flows shown in the deck: Gujarati possession-date question answered from the registration record, then complaint filing and tracking; officer asks "Which Surat promoters have the most delayed projects?" and gets SQL, a table and a chart.
- Targets: 90%+ answers correct and cited, 80%+ complaints complete on first submission, 40%+ routine queries answered without the helpdesk, 100+ concurrent users with answers starting within 3 seconds.
- Testing: 300 gold questions, 100 per language, measuring accuracy and speech WER.

---

## 2. Architecture

```
            ┌───────────── React console (existing frontend, new Copilot view) ─────────────┐
            │  Chat · voice · upload · tables/charts · complaint form preview · role switch │
            └───────────────────────────────────┬───────────────────────────────────────────┘
                                                │ /api/copilot/*
┌───────────────────────────────────────────────▼───────────────────────────────────────────┐
│ FastAPI (factcheck/api/app.py + new gujrera/api router)                                    │
│  Auth (JWT, roles) → Language layer (detect / normalise / translate / ASR)                 │
│  → Orchestrator (intent routing + fixed tool set, no free-form facts)                      │
│      ├─ trust_check     ── reuses factcheck ingest/OCR/forensics/claims                    │
│      ├─ profile         ── SQL fetch + RAG over orders/notices → cited summary             │
│      ├─ complaint       ── slot-filling form → ComplaintAdapter (Mock | GUJRERA API later) │
│      ├─ self_service    ── role-scoped repository queries                                  │
│      └─ analytics       ── guarded text-to-SQL over allow-listed views                     │
│  → Answer composer (citations, "not found", language of the user) → audit log             │
└───────────────┬─────────────────────────────────┬─────────────────────────────────────────┘
                │                                 │
     RERA database (SQLite now,          Document index (orders, notices, FAQs,
     Postgres-ready via SQLAlchemy)      Act and Rules text): BM25 + multilingual-e5
```

**Code layout:** a new `gujrera/` package next to `factcheck/`. It imports Pramaan modules and does not fork them, so both products keep working.

```
gujrera/
  db/          models.py, repository.py (all role filtering lives here), seed.py, views.sql
  ingest/      portal_scraper.py, mock_generator.py
  trust/       rera_number.py (parse/validate), extract.py, rules.py, verdict.py
  profile/     summarise.py
  complaints/  categories.py, form_flow.py, adapter.py (ComplaintAdapter, MockComplaintAdapter)
  selfservice/ queries.py
  analytics/   text_to_sql.py, sql_guard.py
  chat/        orchestrator.py, tools.py, composer.py, prompts.py
  i18n/        strings_{gu,hi,en}.json, translate.py
  api/         routes.py
```

**Models (as committed in the Stage 1 deck):**
- **LLM:** a self-hosted open LLM served through Ollama is the default, with **no paid API by default** (the deck promises ₹0 per-query fees). The final model is picked by a Gujarati benchmark. Pramaan's Gemini path stays available behind `OFFLINE_MODE=false` only if GUJRERA allows it.
- **Translation:** IndicTrans2 (AI4Bharat) normalises Gujarati and Hindi to English for retrieval and SQL, and translates answers back.
- **OCR:** AksharDrishti OCR (from JanSeva) plus Tesseract with Gujarati; Pramaan's OCR runner stays as the fallback chain.
- **Speech:** IndicConformer, benchmarked against Whisper small (about 64% error on Gujarati in the Pramaan evaluation).
- **Retrieval:** Pramaan's BM25 + multilingual-e5-small with rank fusion, run locally.

All model calls go through one interface, so models can be swapped without changing the app. Prompts are versioned and cached as in `factcheck/claims/cache.py`.

---

## 3. Data foundation

### 3.1 Schema (SQLAlchemy; SQLite for the demo, Postgres-ready)

| Table | Key fields |
|:--|:--|
| `promoters` | id, name, name_gu, pan_hash, type, address, district |
| `projects` | id, rera_no, promoter_id, name, name_gu, district, taluka, type, status, reg_date, proposed_completion, revised_completion, actual_completion, units, source_url, is_mock |
| `project_progress` | project_id, quarter, percent_complete, filed_on (quarterly progress reports) |
| `approvals` | project_id, kind (layout, building permission, NA, fire, env), authority, date, ref |
| `agents` | id, reg_no, name, district, valid_until, status |
| `complaints` | id, project_id, promoter_id, complainant_ref (hashed), form (A/B), category, filed_on, status, closed_on, outcome, is_mock |
| `complaint_events` | complaint_id, at, status, note (status history for tracking) |
| `orders` | id, complaint_id/project_id, date, type, summary, doc_path (indexed for RAG) |
| `dues_notices` | id, promoter_id, project_id, kind (fee, penalty, notice), amount, due_date, status, is_mock |
| `users` | id, role (citizen, developer, agent, officer), promoter_id/agent_id, district_scope |
| `audit_log` | at, user_id, role, tool, query, sql, record_ids_returned |

**Derived views** (the only things text-to-SQL may read): `v_project_delays` (delay in days, delayed flag), `v_promoter_scorecard` (projects, delayed, complaints open/closed, orders), `v_complaint_stats`, `v_agent_status`.

### 3.2 Sources
1. **Public portal data:** a scraper for GUJRERA public project and agent search. **Check the portal's terms and robots.txt first**, and rate-limit requests. Start with 1–2 districts (Ahmedabad, Surat).
2. **Mock generator:** a seeded, reproducible generator for complaints, dues, notices and developer accounts, with realistic distributions (delay rates, complaint mix). Every generated row has `is_mock = 1`.
3. **Regulatory text:** RERA Act 2016 and Gujarat RERA Rules 2017 text, FAQs and sample orders, indexed with the existing `factcheck/retrieval/indexer.py` (e5 `passage:` / `query:` prefixes) for citing law in answers.

**Effort: M.** Everything else depends on this.

---

## 4. Capability T: RERA trust check (differentiator)

**Flow:** upload (brochure, ad, allotment letter, WhatsApp screenshot/forward, voice note) → OCR/ASR → extract RERA facts → look up the registry → run checks → verdict with evidence.

| Step | Reuse from Pramaan | New |
|:--|:--|:--|
| Ingest | `factcheck/ingest/`, `/api/check/text` paste intake | none |
| OCR | `factcheck/extract/ocr/` | Add AksharDrishti + Tesseract (`guj`) engines; add `gu` to `OCR_LANGUAGES`; Gujarati OCR evaluation (section 9) |
| Extract | `factcheck/claims/extractor.py` pattern + cache | New prompt/schema `RERAClaim`: rera_no, project, promoter, district, price, carpet area, possession date, payment instructions |
| RERA number | none | `rera_number.py`: regex parse + normalise. The Gujarat format is believed to be `PR/GJ/<DISTRICT>/.../RAA#####/<DDMMYY>` and agents `AG/GJ/...`; **verify on real certificates** |
| Lookup | none | Exact match on rera_no; fuzzy match (rapidfuzz) on project and promoter name when the number is missing or wrong |
| Fraud cues | `factcheck/forensics/rules.py` (fee demand, deadlines, lookalike domains, personal bank accounts) | RERA rules below |
| Verdict | evidence-first logic in `factcheck/decide/verdict.py` | New verdict set below |

**New RERA rules:** registration not found; registration expired or revoked; promoter name mismatch; project name or district mismatch; possession date later than the registered completion date; advertisement with no RERA number (Section 11(2)); booking amount above 10% before an agreement for sale (Section 13); payment asked to a personal account; key approvals missing; many unresolved complaints or adverse orders; agent named but not registered.

**Verdicts:** `Verified match` · `Registered, with warnings` · `Mismatch with registry` · `Not found in registry` · `Could not read document`. Each verdict lists the checks run, the matching registry record (with source link), and what the buyer should do next.

**Effort: M.**

---

## 5. Capability 1: Promoter and project profiles

- `profile.summarise(entity)` fetches structured facts by SQL (projects, delays, complaints by status, orders, approvals, quarterly progress filings) and retrieves the relevant order and notice passages.
- The LLM writes the summary **only from those facts**, and every sentence carries a citation tag (`[project:PR/GJ/...]`, `[order:123]`). A post-check rejects any sentence without a valid tag or containing a number missing from the fetched facts, and regenerates or drops it.
- The UI shows a scorecard card (numbers come straight from SQL, not the LLM) plus the cited summary.
- Entity resolution: fuzzy name search with a "did you mean" choice when more than one match.

**Effort: M.**

---

## 6. Capability 2: Complaint filing and tracking

- **Category selection:** classify the user's story into the complaint type. Route to **Form A** (complaint to the Authority, Section 31) or **Form B** (compensation to the adjudicating officer, Section 71). This split is believed to match the Gujarat Rules; **confirm against the rules text**. Sub-categories: delay in possession, structural defects, refund, deviation from plan, false advertisement, agent misconduct, etc.
- **Form filling:** slot-filling dialogue driven by a JSON schema of the form (complainant, respondent promoter or project, which is auto-resolved from the database, facts, relief sought, documents). The copilot asks only for missing slots, in the user's language, and saves fields in English with the original text kept.
- **Review:** the user sees the completed form, edits it, and explicitly confirms before submission.
- **Integration:** a `ComplaintAdapter` interface with `submit`, `status` and `upload_document` methods. The only implementation for now is `MockComplaintAdapter`, which writes to `complaints` and `complaint_events` and returns a reference number with a **MOCK** banner. When GUJRERA provides an API, a real adapter replaces it with no other changes.
- **Tracking:** "What is the status of my complaint X?" reads the status history for that complainant only.

**Effort: M–L.**

---

## 7. Capabilities 3 and 4: Self-service and analytics

### 7.1 Developer and agent self-service
- Log in as a seeded developer or agent account. The repository layer injects `promoter_id = :me` / `agent_id = :me` into every query, so a prompt cannot widen scope.
- Fixed tools: application status, approvals pending, dues, notices, quarterly progress filings due or late, registration validity, and complaints against own projects.
- Proactive summary on login: "2 notices, 1 quarterly report overdue, fee of ₹X due on <date>".

**Effort: S–M.**

### 7.2 Officer analytics (text-to-SQL)
1. The LLM receives only the schema of the allow-listed views, plus 20–30 example question/SQL pairs.
2. `sql_guard.py` parses the generated SQL with `sqlglot` and rejects it unless it is a single `SELECT` statement that reads allow-listed views only. Anything else (DML, DDL, PRAGMA, ATTACH, multiple statements) is rejected.
3. The officer's scope (for example, district) is added by rewriting the parsed SQL, not by prompting.
4. Execution runs on a **read-only connection** with a row limit and a timeout.
5. The response shows the answer, the table, an optional chart, **the SQL used**, and a CSV/PDF export option. All queries are written to `audit_log`.
6. Common reports (delayed projects by district, complaint ageing, promoter scorecard) are canned queries, so they are fast and exact.

**Effort: M.**

---

## 8. Cross-cutting

### 8.1 Orchestrator
- An intent router (LLM tool-calling over a **fixed tool list**, with a keyword fallback offline) picks one of: trust_check, profile, complaint_file, complaint_status, self_service, analytics, legal_faq, or smalltalk/refuse.
- Tools are filtered by role before the LLM sees them. For example, a citizen never sees `analytics`.
- The composer renders the answer in the user's language and attaches citations. If a tool returns nothing, the reply is a fixed "not found" message, not generated text.
- Conversation state per session (current entity, open complaint draft).

### 8.2 Languages and voice
- Detection reuses `factcheck/lang/detect.py`. Mixed input (Gujlish, Hinglish, Gujarati in Latin script) is normalised before entity lookup. Names are matched against both `name` and `name_gu`.
- UI strings exist in Gujarati, Hindi and English (Gujarati first).
- **Voice:** turn on IndicConformer for `gu` and `hi` (already built, disabled by default) and compare it with Whisper using `scripts/eval_asr.py`. Keep the low-confidence warning that already applies to `gu`.
- Optional TTS for replies (Indic TTS) if time allows.

### 8.3 Security and privacy
- JWT auth with four roles. Demo has a role switcher with seeded users.
- Complainant personal data is stored hashed or separately, retained minimally, and covered by a consent notice (DPDP Act 2023).
- No personal data in logs or prompts beyond what the task needs.
- In offline mode, zero external calls. Reuse `scripts/scan_secrets.py`.

---

## 9. Evaluation (offline, in the Pramaan style)

| Area | Test set | Target metric |
|:--|:--|:--|
| Trust check | 40 documents: 20 genuine (real ads with valid RERA numbers), 20 doctored (wrong number, expired, mismatched promoter, no number) | 0 genuine flagged as fake; ≥ 90% of fakes flagged; every verdict cites a record |
| RERA number parsing | 100 strings incl. OCR noise | ≥ 98% exact parse |
| Profiles | 30 entities | 100% of numbers traceable to SQL; 0 uncited sentences |
| "Not found" | 30 questions about entities not in the database | 100% answered "not found", 0 invented |
| Complaint category | 60 stories (20 each in gu, hi, en) | ≥ 85% correct form and category |
| Text-to-SQL | 50 officer questions with gold SQL/results | ≥ 85% result match; 100% of unsafe queries blocked (red-team set of 30) |
| Access control | 30 cross-tenant attempts ("show developer Y's dues") | 0 leaks |
| Gujarati OCR | 30 real Gujarati brochures/ads | CER reported per engine |
| Gujarati ASR | 30 voice clips | WER: IndicConformer vs Whisper |
| **Gold question set (deck)** | 300 questions, 100 each in gu, hi, en, across all four capabilities | ≥ 90% correct and cited |
| Complaint completeness | Simulated filing dialogues | ≥ 80% complete on first submission |
| Latency | 100 concurrent users (load test) | Answer starts within 3 s |

Scripts go in `scripts/eval_gujrera_*.py` and results in `docs/gujrera_eval.md`, as for the existing evaluations.

---

## 10. Milestones

Build steps for the jury prototype, mapped to the four phases of the 16-week PoC promised in the deck. The prototype runs the same steps faster, on mock and public data; the PoC repeats them on GUJRERA's real data.

| Step | Deliverable | Depends on | Effort | Deck PoC phase |
|:-:|:--|:--|:-:|:--|
| 0 | Confirm Stage 2 deliverables, deadline and hosting; check portal terms | none | S | 1 · Foundations (wk 1–3) |
| 1 | Schema, mock generator, portal scraper (1–2 districts), views, RAG index of Act/Rules | 0 | M | 1 · Foundations |
| 1b | Gujarati voice and OCR benchmarks (IndicConformer, AksharDrishti, Tesseract) | 0 | S–M | 1 · Foundations |
| 2 | Trust check end to end, with API + UI card + eval set | 1 | M | 2 · Citizen copilot (wk 4–8) |
| 3 | Profiles + chat orchestrator (citizen role) + citations + "not found"; IndicTrans2 | 1 | M | 2 · Citizen copilot |
| 7 | Gujarati/Hindi pass: UI strings, mixed input, voice input | 2, 3 | M | 2 · Citizen copilot |
| 4 | Auth + roles; developer/agent self-service (promoter login) | 1, 3 | S–M | 3 · Complaints (wk 9–12) |
| 5 | Complaint filing (Form A/B, slot filling, mock adapter) + tracking | 3 | M–L | 3 · Complaints |
| 6 | Officer analytics: text-to-SQL guard, canned reports, exports | 1, 4 | M | 4 · Officers and pilot (wk 13–16) |
| 8 | 300-question gold set, load test, offline-mode check, demo script and recording, docs | all | S–M | 4 · Officers and pilot |

Steps 2, 3 and 6 can run in parallel once step 1 is done, and 4 and 5 can follow 3 in parallel. For the jury, the demo should cover all four deck flows even if some parts run on mock data, since implementation readiness is scored.

### Progress

**Phase 1 (2026-11-17): partly done.**
- Done: schema (`gujrera/db/models.py`), four analytics views (`gujrera/db/views.py`), read-only engine, role-scoped repository with audit log (`gujrera/db/repository.py`), seeded mock generator (`gujrera/ingest/mock_generator.py`), public-records CSV importer, RERA number parser (`gujrera/trust/rera_number.py`), `scripts/seed_gujrera.py`, 29 tests (`tests/test_gujrera_*.py`).
- Mock data safety: names end in "(Demo)", registration numbers use the `MOCK` code prefix, and every row has `is_mock=1`.
- Not done: portal scraper (waiting on the portal terms check; use the CSV importer meanwhile), and the RAG index of the Act and Gujarat Rules (needs the source texts).

**Step 2, RERA trust check (2026-11-17): done for text; image upload wired but untested on real ads.**
- `gujrera/trust/`: rule-based extraction in English, Gujarati and Hindi (`extract.py`); registry checks and verdicts (`checks.py`), reusing Pramaan's payment, urgency, offer and domain forensics; demo/eval cases (`samples.py`); OCR entry point (`service.py`, cloud OCR off by default).
- Checks: number found, registration valid/lapsed/revoked, promoter match or mismatch, project name, district, advertised possession vs registered completion, delay, pending approvals, promoter complaints and adverse orders, agent registration, booking above 10% (s.13), payment to an account.
- API: `/api/gujrera/trust/{samples,text,upload}`, mounted on the main backend; `gujrera/api/dev_app.py` serves only these routes when the full Pramaan stack is not installed.
- Console: "RERA check" tab (now the default), with samples, upload, Gujarati/Hindi/English headline, registry record and checks.
- Evaluation: `scripts/eval_gujrera_trust.py` → `docs/gujrera_trust_eval.md` (179/179 on template ads, 0 false alarms, 0 dangerous misses). Template ads only: real ads and Gujarati OCR still need testing (step 1b).

**Step 3, profiles and chat (2026-11-17): done for the citizen role; IndicTrans2 not started.**
- `gujrera/profile/summarise.py`: project, promoter and agent profiles. Every sentence is a Gujarati/Hindi/English template (`gujrera/i18n.py`) filled from registry values and carries its source records.
- `gujrera/chat/`: language detection (scripts plus romanised Gujarati/Hindi), keyword intents, registry name matching (exact, or fuzzy ≥ 94 for typos), conversation memory for follow-ups, "which one did you mean?" for duplicate names, and fixed replies for not found, out of scope and greetings. A pasted ad goes to the trust check. Complaint requests get an honest "not available yet".
- Optional local-LLM rephrasing (`gujrera/chat/llm.py`, `GUJRERA_LLM_PHRASING=false` by default): output is kept only if every sentence keeps a citation and no new number appears. With the installed `qwen3-vl:4b` it took about 22 s and its output failed the guard, so the template answer was used; a faster Gujarati-capable model is needed before turning it on.
- API: `POST /api/gujrera/chat`, `GET /api/gujrera/chat/starters`, `GET /api/gujrera/profile/{project,promoter}/{id}`. Chat state is in memory (single process).
- Console: "Ask" tab with citation markers, sources list, project/promoter/trust cards, choice buttons and follow-up suggestions.
- Evaluation: `scripts/eval_gujrera_chat.py` → `docs/gujrera_chat_eval.md`: 300 template questions (100 per language), 300/300 pass, 0 unknown names answered as found, p95 latency about 50 ms on CPU. These are generated from templates the router was tuned on; real user questions must be collected in the pilot.
- Not done: IndicTrans2 (answers use native templates instead, so translation is only needed for free-form text such as order summaries, which are shown in English).

**Step 5, complaint filing and tracking (2026-11-17): done on a mock workflow; built before step 4 (login).**
- `gujrera/complaints/`: step-by-step filing in chat (project → story → category → relief → name → mobile → optional email and unit → consent → review → submit), in Gujarati, Hindi and English. The category is guessed from the story and confirmed at review; the form follows from the relief (Form B for compensation, Section 71; otherwise Form A, Section 31; verify against the Gujarat Rules). Cancel at any point; nothing is sent without consent and a final "Submit"; any field can be changed from the review.
- Hand-off: `ComplaintAdapter` interface with `MockComplaintAdapter` (labelled MOCK). Contact details go only to the mock portal table, as the real portal would hold them; the copilot's complaint row keeps an HMAC of the mobile, never the number.
- Tracking without login: reference number plus a 6-digit code given at filing, stored only as an HMAC (`GUJRERA_HASH_SECRET`); three wrong codes lock that reference for the session. Complaints filed outside the copilot have no code and are pointed to the portal.
- Console: review card, receipt card with copy button, status timeline; option buttons show their label and old buttons are disabled.
- Evaluation: `scripts/eval_gujrera_complaints.py` → `docs/gujrera_complaints_eval.md`: 90 simulated conversations (6 types × 3 languages × 5 projects), 90/90 submitted complete with the right project, category and form, staying in the buyer's language, 8 turns on average. Template stories only.
- Fix found on the way: a shared word such as "Developers" could carry a fuzzy promoter match; the distinctive first word must now match too (trust check and chat).
- Next: replace the mock adapter once GUJRERA shares the complaint hand-off format.

**Step 4, login and promoter/agent self-service (2026-11-17): done for demo accounts.**
- `gujrera/auth.py`: PBKDF2-SHA256 passwords, HMAC-signed tokens that expire (`GUJRERA_TOKEN_HOURS`) and are refused if the user's role changes, lockout after 5 wrong passwords, the same error for unknown users and wrong passwords. Seeded accounts share `GUJRERA_DEMO_PASSWORD`. GUJRERA's own sign-in (portal SSO or OTP) would replace `authenticate()`; the token carries only user id and role.
- The token's role flows into the existing `Repository`, so every rule stays enforced in one place. Chat sessions are bound to their user: another user (or logging out) gets a fresh session.
- `gujrera/selfservice/summary.py`: promoter summary (pending and overdue dues with ₹ totals, notices awaiting a reply, unfiled quarterly reports for ongoing projects with Section 11 cited, next report due date, registrations ending within 180 days with Section 6 cited, pending approvals, open complaints) and agent summary (registration, renewal reminder with Section 9 cited, complaints naming the agent). Gujarati, Hindi and English.
- Chat: "my dues", "મારી બાકી ચુકવણી", "pending notices", "my compliance summary" answer from the user's own records; asking for another promoter's dues gets "you can only see your own"; asking without login gets a login prompt. Logged-in buyers can list their complaints and track them without a code; complaints they file are linked to their account.
- API: `POST /auth/login`, `GET /auth/me`, `GET /self-service/summary`; chat reads `Authorization: Bearer`.
- Console: login panel with demo-account picks (password typed, never stored in the frontend), account bar, compliance summary on login, dues/reports/registrations card.
- Tests: `tests/test_gujrera_auth.py` (12), including "every dues record a promoter is shown belongs to that promoter".
- Officers can log in, but officer analytics is step 6.

---

## 11. Risks and mitigations

| Risk | Mitigation |
|:--|:--|
| No real data or API access | Public portal data where permitted; labelled mock data elsewhere; adapter interfaces so real APIs drop in |
| Portal terms forbid scraping | Use manually collected samples + mock data; ask GUJRERA for a data extract |
| Gujarati ASR quality | IndicConformer; text fallback; show transcript for user confirmation before acting |
| Gujarati OCR quality untested | Evaluate early (phase 1–2) on real brochures; Gemini fallback when online |
| LLM invents facts | Facts only from tools; citation post-check; fixed "not found" path |
| Unsafe or over-broad SQL | Parser-level allow-list, scope rewrite, read-only connection, audit log, red-team tests |
| Legal details wrong (form types, RERA number format, sections) | Verify against the Act and Gujarat Rules text before demo; cite the section in answers |
| Scope too large for the deadline | Order above puts the differentiator and profiles first; complaints and analytics can be scripted demos if time is short |

---

## 12. Demo script (draft)

1. Citizen, in Gujarati voice: "Is this flat offer genuine?" + WhatsApp image → trust check flags expired registration and a personal bank account, cites the registry record.
2. Citizen: "Tell me about this builder" → cited profile with delay and complaint scorecard.
3. Citizen: describes a possession delay in Hindi → copilot picks the form, fills it, user confirms → MOCK reference number → "status?" shows the timeline.
4. Developer login: "What do I owe and what's pending?" → own dues and notices only. Attempt to view another developer's data → refused.
5. Officer: "Which promoters in Surat have the most delayed projects?" → table, chart, SQL shown, export.
6. Same flow with networking disabled (offline mode), to show the on-premise option.

---

## 13. Open questions

1. What exactly must be delivered at Stage 2 (mentoring session or jury): live demo, recording, revised proposal? Deadline and demo format?
2. Will GUJRERA share data samples, the complaint form spec, or API access? (The deck asks for registry exports, sample orders, anonymised complaints and the complaint hand-off format.)
3. Hosting: government cloud or on-premise?
4. Is public-portal scraping acceptable for the prototype?
5. The deck's OCR line relies on AksharDrishti from JanSeva, which is not in this repo. Where does that code live, and can it be brought in?

Evaluation criteria and weights are now known (section 1.1).
