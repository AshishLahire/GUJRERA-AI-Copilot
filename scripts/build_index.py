"""Build and persist the Stage 4 retrieval index (BM25 + multilingual-e5 embeddings) in `data/index/`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factcheck.retrieval.indexer import build_and_save_index


def main() -> None:
    manifest = build_and_save_index()
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
