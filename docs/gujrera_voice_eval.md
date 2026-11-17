# Voice evaluation

Spoken questions about the demo registry, transcribed with the self-hosted Whisper small the app uses (language as picked in the app), then sent to the chat. Reproduce with `python scripts/eval_gujrera_voice.py`; the prompts and how to record them are in `docs/gujrera_voice_recording_sheet.md`.

- **WER / CER**: word / character error rate against the prompt text (lower is better).
- **Task success**: the transcript, sent to the chat, gets the expected answer type and cites the expected project, builder or section. This is what matters to a user: a transcript with errors can still be answered correctly.
- **Right name offered**: the heard name was close but not exact, and the chat asked "Did you mean …?" with the right project or builder, so the user gets the answer with one tap (☝️ below).

## Real speakers

No clips yet. Record them with the sheet above.

## Computer voices (Windows, offline; much easier than real speech)

| Language | Clips | WER | CER | Answered right | Right name offered (one tap) | Avg. transcription time |
|:--|:-:|:-:|:-:|:-:|:-:|:-:|
| Gujarati | 0 of 10 | – | – | – | – | – |
| Hindi | 0 of 10 | – | – | – | – | – |
| English | 10 of 10 | 14% | 6% | 3/10 | 6/10 | 2.3 s |

<details><summary>Every clip</summary>

| ID | Said | Heard | WER | Task |
|:--|:--|:--|:-:|:-:|
| en_01 | When will I get possession of my flat in Aangan Vihar? | When will I get possession of my flat in Angon, Vihar? | 9% | ☝️ (did_you_mean) |
| en_02 | When will I get possession of my flat in Sarjan Homes? | When will I get possession of my flat and sergeant homes? | 18% | ☝️ (did_you_mean) |
| en_03 | When will I get possession of my flat in Mangal Arcade? | When will I get possession of my flat in Mongol arcade? | 9% | ☝️ (did_you_mean) |
| en_04 | Tell me about the builder Suvarna Builders | Tell me about the builders sovarna builders. | 29% | ☝️ (did_you_mean) |
| en_05 | Tell me about the builder Girnar Infra | Tell me about the Builder-Gerner Infra. | 14% | ☝️ (did_you_mean) |
| en_06 | Give me the details of Navrang Elite | Give me the details of Navrang Elite. | 0% | ✅ (project_profile) |
| en_07 | Give me the details of Aangan Homes | Give me the details of Angan homes. | 14% | ☝️ (did_you_mean) |
| en_08 | How many complaints are there against Utsav Arcade? | How many complaints are there against Utsav arcade? | 0% | ✅ (complaints) |
| en_09 | How many complaints are there against Utsav Vihar? | How many complaints are there against its abhihar? | 25% | ❌ (officer_only) |
| en_10 | What does section eighteen of the RERA Act say about refunds? | What does Section 18 of the RERI Act say about refunds? | 18% | ✅ (legal) |

</details>

Gujarati is the known weak spot of Whisper small (the deck cites about 64% WER). The app therefore puts the transcript in the text box for the user to check before sending, and warns for Gujarati. The PoC plan replaces it with IndicConformer for Gujarati and Hindi.
