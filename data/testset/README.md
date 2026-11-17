# Held-out test set

Built by `python scripts/build_testset.py`; evaluated by `python scripts/eval_testset.py [--live]`
(report: `docs/testset_eval.md`, per-item results: `results.json`). Shown in the console under
**Held-out Test Set** (Real / Fake / Synthetic tabs, with an "Unseen mode" toggle).

| Folder | Items | What it is |
| :--- | ---: | :--- |
| `real/` | 12 | Genuine RBI / CBSE PDFs from `data/heldout/real` (`TR-xx.pdf` + page-1 `TR-xx.png`). 10 are also in the official index (matched by exact reference number); TR-01 and TR-12 are not. 10 are born-digital and read from the PDF text layer; TR-01 and TR-12 are scanned and need OCR. |
| `fake/` | 11 | Real-world fakes from `data/heldout/fake`, collected as PIB fact-check graphics. Cropped to the forwarded letter and the red "FAKE" stamp inpainted, so PIB's verdict can't leak into the test. Originals with the stamp are in `fake/original/`. TF-10 and TF-11 are phone photos of TF-01 and TF-07. |
| `synthetic/` | 12 | 6 forged + 6 clean from `06_synthetic_forgeries` (fictional issuers, watermarked), excluding demo images. The text forensic rules were tuned on this dataset, so treat these as in-sample. |

Excluded: `fa445b7a-…png`, which is PIB's tweet text only, with no copy of the fake document.

Every item is scored twice: with the PIB debunk archive (normal use) and in **unseen mode**, where the
archive is hidden, as if nobody had debunked the fake yet. The eval also scans each fake's OCR text
for leftover giveaways (FAKE, PIB, फर्जी, "not issued") and lists any it finds.
