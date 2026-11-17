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

**LLM:** keep Pramaan's provider setup. Gemini is the hosted fallback; Ollama (Qwen) is the offline default for on-premise. All model calls go through one interface, so hosting can be decided later. Prompts are versioned and cached as in `factcheck/claims/cache.py`.

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
| OCR | `factcheck/extract/ocr/` | Add `gu` to `OCR_LANGUAGES`; Gujarati OCR evaluation (section 9) |
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

Scripts go in `scripts/eval_gujrera_*.py` and results in `docs/gujrera_eval.md`, as for the existing evaluations.

---

## 10. Milestones

Relative order. Map to calendar dates once the deadline is known.

| Phase | Deliverable | Depends on | Effort |
|:-:|:--|:--|:-:|
| 0 | Read the requirements zip; confirm deliverables, deadline, scoring, hosting; check portal terms | none | S |
| 1 | Schema, mock generator, portal scraper (1–2 districts), views, RAG index of Act/Rules | 0 | M |
| 2 | Trust check end to end, with API + UI card + eval set | 1 | M |
| 3 | Profiles + chat orchestrator (citizen role) + citations + "not found" | 1 | M |
| 4 | Auth + roles; developer/agent self-service | 1, 3 | S–M |
| 5 | Complaint filing (Form A/B, slot filling, mock adapter) + tracking | 3 | M–L |
| 6 | Officer analytics: text-to-SQL guard, canned reports, exports | 1, 4 | M |
| 7 | Gujarati/Hindi pass: UI strings, mixed input, IndicConformer, OCR eval | 2, 3 | M |
| 8 | Full eval run, offline-mode check, demo script and recording, docs | all | S–M |

Phases 2, 3 and 6 can run in parallel once phase 1 is done, and 4 and 5 can follow 3 in parallel.

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

1. What exactly must be delivered at Stage 2: demo, working prototype, document? Deadline and demo format?
2. Will GUJRERA share data samples, the complaint form spec, or API access?
3. Hosting: cloud, on-premise, or government cloud?
4. Evaluation criteria and weighting?
5. Is public-portal scraping acceptable for the prototype?
