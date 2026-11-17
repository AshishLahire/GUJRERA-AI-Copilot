"""Search the legal index: exact section/rule lookup, then hybrid dense + keyword ranking.

- "Section 18", "કલમ 18", "धारा 18", "Rule 7", "નિયમ 7", "नियम 7" go straight to that provision.
- Otherwise multilingual-e5 cosine similarity (works across Gujarati/Hindi/English) is fused
  with BM25 keyword scores by reciprocal rank fusion.
- If the best semantic match is weak, nothing is returned, so the copilot says "not found"
  instead of quoting an unrelated provision.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from factcheck.lang.normalize import normalize_digits
from gujrera.legal.build import INDEX_DIR, embed, tokenize
from gujrera.legal.glossary import expand

STRONG_COSINE = 0.86
STOPWORDS = {"what", "which", "who", "whom", "when", "where", "why", "how", "the", "and", "for", "are", "was", "were",
             "can", "could", "does", "did", "will", "would", "should", "shall", "may", "might", "must", "have", "has",
             "had", "this", "that", "these", "those", "with", "from", "into", "about", "today", "yesterday", "tell",
             "please", "there", "their", "them", "they", "you", "your", "our", "any", "all", "not", "but", "its"}
MIN_COSINE = 0.80  # below this the best hit is treated as unrelated (calibrated on tests/test_gujrera_legal.py)
RRF_K = 60

SECTION_RE = re.compile(r"(?:\bsection|\bsec\.?|\bs\.|કલમ|धारा)\s*(\d{1,3}[A-Z]?)", re.IGNORECASE)
RULE_RE = re.compile(r"(?:\brule|નિયમ|नियम)\s*(\d{1,3}[A-Z]?)", re.IGNORECASE)


ORDER_WORDS = ("order", "orders", "judgment", "judgement", "penalty imposed", "decided", "આદેશ", "ચુકાદો", "आदेश", "फैसला")
AGREEMENT_WORDS = ("agreement", "clause", "કરાર", "अनुबंध", "agreement for sale")
ANNEXURE_WEIGHT = 0.85  # the long model agreement otherwise outranks the specific section


def default_kinds(text: str) -> tuple[str, ...]:
    """Search orders only when the question is about orders or decisions."""
    lc = text.lower()
    base = ("act", "rules", "annexure")
    return base + ("order",) if any(w in lc for w in ORDER_WORDS) else base


@dataclass
class Hit:
    chunk: dict[str, Any]
    score: float
    cosine: float
    exact: bool = False

    @property
    def label(self) -> str:
        c = self.chunk
        if c["kind"] == "order":
            return f"Order {c['number']}"
        if c["kind"] == "annexure":
            return f"{c['doc_title']}, Annexure A (model agreement for sale)"
        unit = "Section" if c["kind"] == "act" else "Rule"
        return f"{c['doc_title']}, {unit} {c['number']}"

    def citation(self) -> dict[str, Any]:
        return {"type": f"legal_{self.chunk['kind']}", "id": self.label, "is_mock": bool(self.chunk.get("is_mock"))}


class LegalIndex:
    def __init__(self, chunks: list[dict[str, Any]], vectors: np.ndarray):
        self.chunks = chunks
        self.vectors = vectors
        self.df: Counter[str] = Counter()
        for c in chunks:
            self.df.update(set(c["tokens"]))
        self.avgdl = sum(len(c["tokens"]) for c in chunks) / max(len(chunks), 1)

    @classmethod
    def load(cls, index_dir: Path = INDEX_DIR) -> LegalIndex | None:
        if not (index_dir / "chunks.json").exists():
            return None
        chunks = json.loads((index_dir / "chunks.json").read_text(encoding="utf-8"))
        return cls(chunks, np.load(index_dir / "vectors.npy"))

    def _bm25(self, query_tokens: list[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
        n = len(self.chunks)
        scores = np.zeros(n, dtype=np.float32)
        for i, c in enumerate(self.chunks):
            tf = Counter(c["tokens"])
            dl = len(c["tokens"])
            for t in query_tokens:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                scores[i] += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / self.avgdl))
        return scores

    def lookup(self, kind: str, number: str) -> list[Hit]:
        return [Hit(c, 1.0, 1.0, exact=True) for c in self.chunks
                if c["kind"] == kind and c["number"].upper() == number.upper()]

    def search(self, query: str, *, k: int = 5, kinds: tuple[str, ...] | None = None) -> list[Hit]:
        text = normalize_digits(query or "")
        exact: list[Hit] = []
        m = SECTION_RE.search(text)
        if m:
            exact = self.lookup("act", m.group(1))
        m = RULE_RE.search(text)
        if m and not exact:
            exact = self.lookup("rules", m.group(1))
        if exact:
            return exact[:k]

        text = expand(text)  # Gujarati/Hindi RERA terms → English legal terms
        qvec = embed([text], "query: ")[0]
        cos = self.vectors @ qvec
        bm = self._bm25(tokenize(text))
        if kinds is None:
            kinds = default_kinds(text)
        wants_agreement = any(w in text.lower() for w in AGREEMENT_WORDS)
        allowed = np.array([c["kind"] in kinds for c in self.chunks])
        dense_rank = {int(i): r for r, i in enumerate(np.argsort(-np.where(allowed, cos, -9)))}
        bm_rank = {int(i): r for r, i in enumerate(np.argsort(-np.where(allowed, bm, -9)))}
        fused = {i: (1 / (RRF_K + dense_rank[i]) + (1 / (RRF_K + bm_rank[i]) if bm[i] > 0 else 0))
                 * (ANNEXURE_WEIGHT if self.chunks[i]["kind"] == "annexure" and not wants_agreement else 1.0)
                 for i in range(len(self.chunks)) if allowed[i]}
        best = sorted(fused, key=lambda i: -fused[i])
        if not best or float(cos[best[0]]) < MIN_COSINE and float(cos.max()) < MIN_COSINE:
            return []
        # Off-topic guard: the best hit needs some content-word overlap with the question, unless the
        # semantic match is strong on its own. ("what is the weather today" shares only filler words.)
        content = [t for t in tokenize(text) if t not in STOPWORDS and len(t) > 2]
        overlap = self._bm25(content) if content else np.zeros(len(self.chunks), dtype=np.float32)
        if float(overlap[best[0]]) <= 0 and float(cos[best[0]]) < STRONG_COSINE:
            return []
        hits, seen = [], set()
        for i in best:
            c = self.chunks[i]
            key = (c["kind"], c["number"])
            if key in seen or float(cos[i]) < MIN_COSINE - 0.03:
                continue
            seen.add(key)
            hits.append(Hit(c, fused[i], float(cos[i])))
            if len(hits) >= k:
                break
        return hits


@lru_cache(maxsize=1)
def default_index() -> LegalIndex | None:
    return LegalIndex.load()
