# Legal RAG evaluation

25 law questions with a known answering provision, plus 7 off-topic questions, over the RERA Act 2016 (OCR of the GUJRERA scan) and the Gujarat RERA General Rules 2017. Reproduce with `python scripts/eval_gujrera_legal.py`.

- Right provision ranked first: **22/25**
- Right provision in the top 3: **25/25**
- Off-topic questions correctly answered "not found": **7/7**

| Language | Top 1 | Top 3 |
|:--|:-:|:-:|
| en | 14/15 | 15/15 |
| gu | 5/5 | 5/5 |
| hi | 3/5 | 5/5 |

Known limitation: 10 of the Act's 92 section headings could not be read from the scan (e.g. sections 21, 22, 27, 44); their text is indexed under the preceding section.
