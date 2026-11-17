"""Build the legal search index (RERA Act, Gujarat Rules, RERA orders) for the copilot.

    python scripts/build_gujrera_legal_index.py

Expects the PDFs in data/gujrera/legal/ (downloaded from gujrera.gujarat.gov.in →
Acts, Rules, Regulations): rera_act_2016.pdf and gujarat_rera_general_rules_2017.pdf.
The Act PDF is scanned, so Tesseract OCR must be installed (GUJRERA_TESSERACT_CMD).
Orders are read from the GUJRERA database. Writes data/gujrera/legal_index/.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gujrera.db.session import make_engine, session_factory  # noqa: E402
from gujrera.legal.build import INDEX_DIR, LEGAL_DIR, build_index  # noqa: E402


def main() -> int:
    missing = [f for f in ("rera_act_2016.pdf", "gujarat_rera_general_rules_2017.pdf") if not (LEGAL_DIR / f).exists()]
    if missing:
        print(f"Missing in {LEGAL_DIR}: {', '.join(missing)} (indexing what is available)")
    started = time.time()
    with session_factory(make_engine())() as s:
        counts = build_index(s)
    print(f"Indexed in {time.time() - started:.0f} s → {INDEX_DIR}")
    for kind, n in counts.items():
        print(f"  {kind:<10}{n:>6} chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
