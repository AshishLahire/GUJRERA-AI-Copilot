# Held-out test set evaluation

35 items (Counter({'real': 12, 'fake': 11, 'synthetic_forged': 6, 'synthetic_clean': 6})); evaluated: 10; skipped (no OCR text, run with --live): 25.

| Group | n | With PIB archive: correct / safe miss / false alarm / dangerous | Unseen: correct / safe miss / false alarm / dangerous |
| :--- | ---: | :---: | :---: |
| real | 10 | 10 / 0 / 0 / 0 | 10 / 0 / 0 / 0 |

| ID | Label | Verdict (archive) | Verdict (unseen) | Risk | Decided by | Leftover giveaways |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| TR-01 | real | not run: no OCR text | | | | |
| TR-02 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-03 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-04 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-05 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-06 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-07 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-08 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-09 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-10 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-11 | real | matches_official (correct) | matches_official (correct) | low 0 | source_match | - |
| TR-12 | real | not run: no OCR text | | | | |
| TF-01 | fake | not run: no OCR text | | | | |
| TF-02 | fake | not run: no OCR text | | | | |
| TF-03 | fake | not run: no OCR text | | | | |
| TF-04 | fake | not run: no OCR text | | | | |
| TF-05 | fake | not run: no OCR text | | | | |
| TF-06 | fake | not run: no OCR text | | | | |
| TF-07 | fake | not run: no OCR text | | | | |
| TF-08 | fake | not run: no OCR text | | | | |
| TF-09 | fake | not run: no OCR text | | | | |
| TF-10 | fake | not run: no OCR text | | | | |
| TF-11 | fake | not run: no OCR text | | | | |
| SYN-0032 | synthetic_forged | not run: no OCR text | | | | |
| SYN-0034 | synthetic_forged | not run: no OCR text | | | | |
| SYN-0035 | synthetic_forged | not run: no OCR text | | | | |
| SYN-0036 | synthetic_forged | not run: no OCR text | | | | |
| SYN-0037 | synthetic_forged | not run: no OCR text | | | | |
| SYN-0038 | synthetic_forged | not run: no OCR text | | | | |
| SYN-0003 | synthetic_clean | not run: no OCR text | | | | |
| SYN-0004 | synthetic_clean | not run: no OCR text | | | | |
| SYN-0005 | synthetic_clean | not run: no OCR text | | | | |
| SYN-0006 | synthetic_clean | not run: no OCR text | | | | |
| SYN-0007 | synthetic_clean | not run: no OCR text | | | | |
| SYN-0008 | synthetic_clean | not run: no OCR text | | | | |

Correct = fake flagged or genuine verified. Safe miss = 'unverified' (the system declines to judge). Dangerous = fake verified as official. Synthetic forgeries were used to tune the text rules (in-sample).
