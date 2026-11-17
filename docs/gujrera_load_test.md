# Load test

Real API server (one uvicorn process, default settings, self-hosted LLM on) on this laptop (16 CPU threads, RTX 3070 Ti), mock registry. Reproduce with `python scripts/load_test_gujrera.py`.

The API returns each answer in one piece, so the times below run until the **whole** answer has arrived, which is stricter than the deck's "answer starts within 3 seconds". Requests are a mix of questions in Gujarati, Hindi and English from the gold set, pasted-ad checks, project and promoter profiles, and promoter login plus "my dues". Questions the rules passed to the LLM are reported in part 3.

## 1. 100 users at once, reading between questions (deck target)

100 users each send 5 requests, pausing 5–15 s between them to read the answer, as people do.

- Requests: **541** in 68.6 s (7.9 per second), errors: **0**
- Complete answer within 3 s: **538/541** (99%; p50 0.07 s, p95 0.20 s, slowest 5.55 s)

| Request | Count | p50 | p95 | Slowest | Errors |
|:--|--:|--:|--:|--:|--:|
| RERA check (pasted ad) | 89 | 0.02 s | 0.05 s | 0.08 s | 0 |
| chat question | 228 | 0.08 s | 0.20 s | 5.55 s | 0 |
| login | 80 | 0.15 s | 0.23 s | 0.35 s | 0 |
| profile | 64 | 0.02 s | 0.06 s | 0.13 s | 0 |
| promoter: my dues | 80 | 0.07 s | 0.18 s | 0.25 s | 0 |

## 2. Stress: 100 users with no pause

The same 100 users fire all 5 requests back to back. Far heavier than real use; shows where one process saturates.

- Requests: **548** in 78.4 s (7.0 per second), errors: **0**
- Complete answer within 3 s: **290/548** (53%; p50 2.32 s, p95 6.46 s, slowest 53.90 s)

| Request | Count | p50 | p95 | Slowest | Errors |
|:--|--:|--:|--:|--:|--:|
| RERA check (pasted ad) | 63 | 0.37 s | 1.52 s | 2.35 s | 0 |
| chat question | 243 | 4.66 s | 6.86 s | 53.90 s | 0 |
| login | 81 | 0.62 s | 1.35 s | 1.51 s | 0 |
| profile | 80 | 0.50 s | 1.32 s | 2.67 s | 0 |
| promoter: my dues | 81 | 5.29 s | 6.49 s | 6.70 s | 0 |

## 3. Questions that need the self-hosted LLM

10 free-form and law questions sent at once, plus the 72 gold questions in parts 1–2 that the rules passed to the LLM; one laptop GPU, one Ollama model.

- Answers: **82**, errors **0**; within 3 s: 3; p50 10.1 s, p95 46.1 s, slowest 52.5 s

One GPU answers LLM questions one after another, so they queue when many arrive together. For the PoC: stream answers so the first words arrive in about a second, serve the model with parallel batching (e.g. vLLM on a GPU server), and keep the rule-based path for routine questions, as now. More API processes need the chat state moved to a shared store (Redis or Postgres), as noted in the plan.
