# GujRERA Saathi (ગુજરેરા સાથી)

**A multilingual AI assistant for home buyers, promoters, agents and GUJRERA officers.**
Prototype by YellowSense Technologies for the GUJRERA use case of the Gujarat AI CoE AI Innovation Challenge, built on our Pramaan verification engine.

> Prototype on **demo data**. Not an official GUJRERA service. Every demo record is labelled (`is_mock`), demo names end in "(Demo)" and demo registration numbers use a `MOCK` code.

---

## What it does

| For | Capability | Where |
|:--|:--|:--|
| Home buyers | **Ask Saathi**: project and builder profiles, possession dates, complaints, in Gujarati, Hindi or English (typed or spoken). Every answer cites the registry record, or says "not found". | Ask Saathi |
| Home buyers | **Check an ad before you pay**: paste or photograph a brochure, hoarding or WhatsApp offer; the RERA number, promoter, dates and payment demands are checked against the registry. | Check an ad |
| Home buyers | **File and track complaints by chat**: the story becomes a Form A/B complaint with consent and review; a reference number and tracking code are given. | Ask Saathi |
| Everyone | **Know your rights**: answers from the RERA Act 2016 and Gujarat RERA Rules 2017, with the section shown. | Ask Saathi |
| Promoters and agents | **Compliance dashboard**: own dues, notices, quarterly reports, registration expiry, with the rule cited. | For promoters |
| GUJRERA officers | **Regulatory analytics**: plain-language questions → table, chart and the SQL used; read-only, district-scoped, logged. | For officers |

## How it stays trustworthy

- **Facts only from records.** Answers are built from registry values; the AI may classify a question, rephrase or summarise, but its output is kept only if every sentence stays cited and no new number appears.
- **Self-hosted AI.** `qwen2.5:7b-instruct` via Ollama, multilingual-e5 embeddings, faster-whisper and Tesseract all run locally; no paid API by default.
- **Access control in code.** A promoter sees only their own data; officers' SQL is parsed, restricted to reporting views, district-scoped and run on a read-only connection; private reads are audited.
- **Privacy.** Complainant mobiles and tracking codes are stored only as keyed hashes; uploaded files and recordings are deleted after reading.

## Measured (offline evaluations, `docs/`)

| Area | Result |
|:--|:--|
| Chat (300 gold questions, 100 per language) | 300/300 correct and cited; 0 unknown names answered as found |
| Ad trust check (178 template ads) | 178/178; 0 false alarms, 0 dangerous misses |
| Complaint filing (90 simulated conversations) | 90/90 complete with the right category and form |
| Legal RAG (25 law questions + 7 off-topic) | right provision in top 3 for 25/25; 7/7 off-topic "not found" |
| Officer analytics | 27/27 questions routed; 30/30 SQL attacks blocked; district scope held 126/126 |

These sets are generated from templates over demo data; real users' questions, photos and voice need a pilot set. See [docs/GUJRERA_PLAN.md](docs/GUJRERA_PLAN.md) for status and limitations.

---

## Run it (Windows)

Prerequisites: Python 3.11+ (Anaconda), Node.js 18+, [Ollama](https://ollama.com), and [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) with Gujarati, Hindi and English data.

```powershell
# 1. Python packages (core + GUJRERA AI extras)
python -m pip install -e ".[dev,gujrera-ai]"
Copy-Item .env.example .env          # then set GUJRERA_AUTH_SECRET and GUJRERA_HASH_SECRET

# 2. Local model
ollama pull qwen2.5:7b-instruct

# 3. Demo database (mock registry, demo accounts)
python scripts/seed_gujrera.py

# 4. Legal index: put the RERA Act and Gujarat RERA General Rules PDFs from the GUJRERA website
#    (Acts, Rules, Regulations) in data/gujrera/legal/ as rera_act_2016.pdf and
#    gujarat_rera_general_rules_2017.pdf, then:
python scripts/build_gujrera_legal_index.py

# 5. Run: API on :8000 and the app on :5173. The launcher moves to free ports if another
#    program (for example another project's dev server) already uses them.
powershell -ExecutionPolicy Bypass -File scripts\run_gujrera.ps1
```

Or by hand: `python -m uvicorn gujrera.api.dev_app:app --port 8000` and `npm --prefix frontend run dev`
(set `PRAMAAN_API` and `PRAMAAN_UI_PORT` to use other ports).

Open the address the launcher prints (http://localhost:5173 by default). Demo walkthrough: [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). Demo accounts: `dev_002` (promoter), `agent_001` (agent), `citizen_01` (home buyer), `officer_surat` / `officer_state` (officers); password = `GUJRERA_DEMO_PASSWORD` in `.env`.

### POC: citizen and authority assistants

The department's POC sample questions (projects in a locality, agents by district, projects under scrutiny,
notices and defaults in a period, projects past their completion date, penalty orders) are answered in
Gujarati, Hindi and English. Officer answers come from read-only, validated SQL over reporting views, with
the SQL shown and logged; a district officer sees only their district; requests to change data are refused.

```
python scripts/seed_gujrera.py --add-authority-data   # officer test records on an existing database
python scripts/eval_gujrera_poc.py                    # sample questions + paraphrases -> docs/gujrera_poc_eval.md
```

### Running on public GUJRERA records

Projects and agents downloaded from the public GUJRERA portal (CSV, Excel or JSON, as downloaded) can be
loaded into a separate database; the demo database is never touched.

```
python scripts/import_gujrera_public.py projects.xlsx agents.csv
powershell -ExecutionPolicy Bypass -File scripts\run_gujrera.ps1 -Db data\gujrera\gujrera_public.sqlite
```

- Column names are matched loosely ("Project Registration No", "RERA No", "projectRegNo", ...); dates may be
  dd/mm/yyyy as on the portal. A ready-to-fill template with the portal's column names is in
  `gujrera/ingest/public_records_template.xlsx`.
- Rows with problems are listed with their row number and skipped; unused columns are listed too.
- Running again updates existing records; `--fresh` starts over. Officer and buyer logins are created
  (`officer_state`, `officer_<largest district>`, `citizen_01`, demo password).
- The app labels the data "Public GUJRERA records" instead of "Demo data". Complaints, dues, notices and
  orders are not public, so those features stay empty until GUJRERA's own data is connected.

`gujrera.api.dev_app` serves only the GujRERA Saathi endpoints. The full Pramaan backend (`factcheck.api.app`) also mounts them, but needs Pramaan's retrieval indexes and extra packages.

### Tests and evaluations

```powershell
python -m pytest tests/test_gujrera_*.py
python scripts/eval_gujrera_chat.py
python scripts/eval_gujrera_trust.py
python scripts/eval_gujrera_complaints.py
python scripts/eval_gujrera_legal.py --llm
python scripts/eval_gujrera_analytics.py
```

## Code layout

```
gujrera/        GujRERA Saathi backend
  db/           schema, reporting views, role-scoped repository
  chat/         language, intents, entities, orchestrator, LLM fallback
  profile/      cited project/promoter/agent profiles
  trust/        ad trust check: RERA number parser, Tesseract OCR, checks
  complaints/   filing and tracking flow, mock GUJRERA workflow adapter
  selfservice/  promoter and agent compliance summary
  analytics/    officer reports, LLM text-to-SQL, SQL guard
  legal/        legal RAG over the Act, Rules and orders
  api/          FastAPI routes (/api/gujrera/*)
frontend/src/saathi/   app shell, home, promoter and officer pages
frontend/src/components/   Ask Saathi, ad check, analytics cards
factcheck/      the Pramaan engine this builds on (see docs/PRAMAAN_README.md)
```

## Built on Pramaan

GujRERA Saathi reuses Pramaan's multilingual retrieval, OCR chain, forensic text checks, speech pipeline and language tools. Pramaan's original README is in [docs/PRAMAAN_README.md](docs/PRAMAAN_README.md); its console is kept in `frontend/src/App.tsx` but is no longer part of the app.
