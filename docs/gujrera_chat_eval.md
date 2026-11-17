# Chat evaluation (gold questions)

300 template-generated questions, 100 per language, built from the mock registry. Zero API calls. Reproduce with `python scripts/eval_gujrera_chat.py`.

A question passes when the reply has the expected intent, contains the expected fact in the question's language, cites a record for every factual sentence, and answers in that language. The questions come from templates, so this measures routing, matching, facts and citations, not how well the copilot handles free-form questions from real users.

- **Passed: 300/300 (100.0%)** (deck target: 90%+ correct and cited)
- Unknown names or off-topic questions answered as if found: **0**
- Latency: p95 45 ms, total 12.3 s on CPU (template answers, no LLM)

| Language | Passed |
|:--|:-:|
| gu | 100/100 |
| hi | 100/100 |
| en | 100/100 |

| Question kind | Passed |
|:--|:-:|
| possession | 90/90 |
| promoter | 60/60 |
| project | 60/60 |
| complaints | 45/45 |
| not_found | 30/30 |
| out_of_scope | 15/15 |
