# Offline (on-premise) check

Every demo flow run through the API with all network connections to other machines blocked inside Python (sockets and DNS); only the local Ollama server on this machine is reachable. The self-hosted LLM paths were switched on. Reproduce with `python scripts/check_gujrera_offline.py`.

- **Flows that worked offline: 10/10**
- Outside connections attempted (all blocked): **0**

| Flow | Worked | Time | Blocked attempts | Detail |
|:--|:-:|--:|:-:|:--|
| Gujarati ad image → trust check | ✅ | 2.0 s | 0 | verdict=not_found, OCR engine=tesseract |
| Gujarati possession question | ✅ | 0.1 s | 0 | intent=possession, 2 sources |
| Builder profile | ✅ | 0.1 s | 0 | intent=promoter_profile |
| Law question (local LLM summary on) | ✅ | 24.4 s | 0 | intent=legal, cites s.13: True |
| Free-form question | ✅ | 0.1 s | 0 | intent=project_profile, understood_by=rules |
| Hindi complaint filing and tracking | ✅ | 0.5 s | 0 | filed MOCK-CMP-2026-00001; tracking intent=complaint_status |
| Promoter login: own dues, other refused | ✅ | 0.5 s | 0 | own=self_service, other=access_denied |
| Officer: Surat delayed promoters (report) | ✅ | 0.1 s | 0 | 8 rows, SQL shown |
| Officer: AI-written SQL (local LLM) | ✅ | 3.7 s | 0 | 4 rows, llm |
| English voice input (Whisper) | ✅ | 5.0 s | 0 | "When will I get possession of my flat?" |

Times include loading each model the first time it is used.
