"""Stage 4: Hybrid BM25 + multilingual-e5 retrieval over PIB debunks and official records."""

from factcheck.retrieval.indexer import build_and_save_index, load_or_build_index
from factcheck.retrieval.matcher import HybridRetriever, match_sources

__all__ = [
    "HybridRetriever",
    "build_and_save_index",
    "load_or_build_index",
    "match_sources",
]
