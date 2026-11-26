# Legal RAG evaluation

Law questions with a known answering provision, over the RERA Act 2016 (OCR of the GUJRERA scan) and the Gujarat RERA General Rules 2017. The main set has English questions with Gujarati and Hindi versions; the held-out set was written in buyers' own words after search was tuned. Reproduce with `python scripts/eval_gujrera_legal.py --rerank`.

## Main set (46 questions)

| Language | Search: first | Search: top 3 | With the model's pick: first | top 3 |
|:--|:-:|:-:|:-:|:-:|
| en | 14/15 | 14/15 | 15/15 | 15/15 |
| gu | 16/16 | 16/16 | 16/16 | 16/16 |
| hi | 15/15 | 15/15 | 14/15 | 15/15 |
| all | 45/46 | 45/46 | 45/46 | 46/46 |

- Off-topic questions correctly answered "not found": **7/7**

## Held-out set (23 questions)

| Language | Search: first | Search: top 3 | With the model's pick: first | top 3 |
|:--|:-:|:-:|:-:|:-:|
| hi | 7/9 | 8/9 | 9/9 | 9/9 |
| gu | 6/8 | 8/8 | 8/8 | 8/8 |
| en | 3/6 | 6/6 | 6/6 | 6/6 |
| all | 16/23 | 22/23 | 23/23 | 23/23 |

The model's pick takes 0.09 s at the median (3.76 s at most) with qwen2.5:7b-instruct on the GPU; it reorders the top 5 found by search and never adds a provision.

## Not ranked first (with the model's pick)

- (main, hi) प्रमोटर को कन्वेयंस डीड कब करनी होती है?: expected ('act', '17'), search gave [('act', '17'), ('act', '11'), ('act', '15')]

Known limitation: 10 of the Act's 92 section headings could not be read from the scan (e.g. sections 21, 22, 27, 44); their text is indexed under the preceding section.
