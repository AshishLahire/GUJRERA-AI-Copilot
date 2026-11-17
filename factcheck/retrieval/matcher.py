"""Stage 4 hybrid retrieval (BM25 + multilingual-e5 with RRF k=60 and exact reference matching)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from factcheck.config import Settings, get_settings
from factcheck.retrieval.ground_truth import check_ground_truth
from factcheck.retrieval.indexer import load_or_build_index, tokenize_multilingual
from factcheck.schemas import ExtractedFields, MatchItem, RetrievalResult


from factcheck.extract.ocr.fields import (
    CLEAN_HINDI_PREFIX_RE,
    DEVANAGARI_DIGITS_TRANS,
    HINDI_PREFIX_MAPPING,
    normalize_reference_number,
)

GARBLED_HINDI_RE = re.compile(
    r"(?:"
    r"[\ufffd\u25cc]"
    r"|(?:^|\s)[\u093e-\u094f\u0951-\u0957]"
    r"|[\u0900-\u097f]\s+[\u093e-\u094f\u0951-\u0957]"
    r"|[\u094d][\u093e-\u094c]"
    r"|[\u093e-\u094f]{2,}"
    r")"
)

EMOJI_RE = re.compile(
    r"["
    r"\U00010000-\U0010FFFF"
    r"\u2600-\u27BF"
    r"\u2B50\u2B55\u231A\u231B\u23F0\u23F3\u25FD\u25FE"
    r"\u200D\uFE0F"
    r"]+",
    flags=re.UNICODE,
)


def clean_pib_snippet(snippet: str, post_text: str = "", title: str = "") -> str:
    """Strip emoji from PIB snippets; if empty or only emoji, fall back to first full sentence or title."""
    import re as _re
    cleaned = EMOJI_RE.sub("", snippet or "")
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    if not _re.search(r"\w", cleaned):
        cleaned_post = EMOJI_RE.sub("", post_text or "")
        cleaned_post = _re.sub(r"\s+", " ", cleaned_post).strip()
        sentences = [
            s.strip()
            for s in _re.split(r"(?<=[.!?।])\s+", cleaned_post)
            if _re.search(r"\w", s)
        ]
        if sentences:
            cleaned = sentences[0]
        else:
            cleaned = EMOJI_RE.sub("", title or "")
            cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_garbled_hindi(text: str) -> bool:
    """Return True if text has broken Unicode, isolated combining marks, or invalid Devanagari."""
    if not text:
        return False
    return bool(GARBLED_HINDI_RE.search(text))


HEADER_BOILERPLATE_RE = re.compile(
    r"(?i)(?:"
    r"Autonomous\s+Organisation\s+Under\s+the\s+Ministry"
    r"|अधीन\s+एक\s+स्वायत्त\s+संगठन"
    r"|Integrated\s+Office\s+Complex"
    r"|एकीकृत\s+कार्यालय\s+परिसर"
    r"|Sector\s*[-–—]\s*\d+|Dwarka|नई\s+दिल्ली\s*[-–—]\s*\d+|New\s+Delhi\s*[-–—]\s*\d+"
    r"|Telephone|फ़ोन|वेबसाइट|Website|ईमेल|e-mail|email"
    r"|CENTRAL\s+BOARD\s+OF\s+SECONDARY\s+EDUCATION|केन्द्रीय\s+माध्यमिक\s+शिक्षा\s+बोर्ड"
    r"|RESERVE\s+BANK\s+OF\s+INDIA|भारतीय\s+रिज़र्व\s+बैंक"
    r"|All\s+the\s+Heads\s+of\s+Schools|संबद्ध\s+सभी\s+विद्यालय"
    r"|Circular\s+No|परिपत्र\s+संख्या|Date\s*:|दिनांक\s*:"
    r")"
)
SUBJECT_RE = re.compile(r"(?im)^\s*(?:Subject|Sub|विषय)\s*[:\-–—]")
FOOTER_START_RE = re.compile(
    r"(?im)^\s*(?:Copy\s+to|प्रतिलिपि|निदेशालयों,\s*संगठनों\s*और\s*संस्थानों|1\.\s*The\s+Commissioner|1\.\s*आयुक्त)"
)


def strip_letterhead_boilerplate(text: str) -> str:
    """Remove header letterhead, ministry/office boilerplate, and routing lists so similarity focuses on circular body."""
    if not text:
        return ""
    lines = text.splitlines()
    body_lines: list[str] = []
    in_body = False
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if FOOTER_START_RE.search(s):
            break
        if SUBJECT_RE.search(s):
            in_body = True
            body_lines.append(s)
            continue
        if in_body:
            body_lines.append(s)
        else:
            if not HEADER_BOILERPLATE_RE.search(s) and len(s) > 25:
                body_lines.append(s)
    cleaned = "\n".join(body_lines).strip()
    return cleaned if len(cleaned) >= 50 else text.strip()


GENERIC_CIRCULAR_WORDS = frozenset({
    "cbse", "rbi", "sebi", "circular", "notice", "order", "letter",
    "reg", "regarding", "date", "no", "information", "guidelines",
    "सूचना", "परिपत्र", "आदेश", "संबंध", "दिशानिर्देश", "जानकारी",
    "सभी", "प्रमुख", "विद्यालय", "विद्यालयों",
    "2023", "2024", "2025", "2026", "2027", "2028", "2029",
})


def _substantive_tokens(text: str) -> set[str]:
    return {
        t for t in tokenize_multilingual(text)
        if len(t) >= 3 and t not in GENERIC_CIRCULAR_WORDS
    }


def _title_or_subject_matches(
    query_text: str,
    subject: str | None,
    doc_title: str,
) -> bool:
    """Check if the official document title matches the query subject or substantive text."""
    if not doc_title:
        return False
    title_toks = _substantive_tokens(doc_title)
    if not title_toks:
        return False
    if subject:
        sub_toks = _substantive_tokens(subject)
        overlap = title_toks & sub_toks
        if len(overlap) >= 2 or (len(title_toks) <= 2 and len(overlap) >= 1):
            return True
    body_toks = _substantive_tokens(query_text)
    overlap_body = title_toks & body_toks
    if len(overlap_body) >= 2 or (len(title_toks) <= 2 and len(overlap_body) >= 1):
        return True
    return False

CLEAN_REF_PREFIX_RE = re.compile(
    r"^(?:(?:Circular|Cir|Order|Ref(?:erence)?|File|Letter|Notification)\s*\.?\s*)?(?:No\.?|Ref)\s*[:\-]?\s*",
    re.IGNORECASE,
)


def _normalize_ref(ref: str) -> str:
    norm = normalize_reference_number(ref)
    cleaned = re.sub(r"\s+", " ", (norm or "").strip())
    cleaned = CLEAN_REF_PREFIX_RE.sub("", cleaned).strip()
    return cleaned.upper()


@lru_cache(maxsize=2)
def _load_embedding_model(model_name: str) -> Any:
    import os

    prev_hf = os.environ.get("HF_HUB_OFFLINE")
    prev_tr = os.environ.get("TRANSFORMERS_OFFLINE")
    try:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name, local_files_only=True)
    except Exception:
        if prev_hf is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = prev_hf
        if prev_tr is None:
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
        else:
            os.environ["TRANSFORMERS_OFFLINE"] = prev_tr
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name)


class HybridRetriever:
    """Hybrid BM25 + multilingual-e5 retriever with Reciprocal Rank Fusion (k=60)."""

    def __init__(
        self,
        index_dir: Path | None = None,
        *,
        settings: Settings | None = None,
        force_bm25_only: bool = False,
    ) -> None:
        self.settings = settings or get_settings()
        self.debunks, self.official, self.debunk_emb, self.official_emb = (
            load_or_build_index(index_dir)
        )
        self.bm25_debunks = (
            BM25Okapi([d.get("tokens") or ["_empty_"] for d in self.debunks])
            if self.debunks
            else None
        )
        self.bm25_official = (
            BM25Okapi([d.get("tokens") or ["_empty_"] for d in self.official])
            if self.official
            else None
        )

        self.model: Any = None
        self.retrieval_mode: str = "bm25_only"
        self.mode_note: str | None = None

        if (
            not force_bm25_only
            and self.debunk_emb is not None
            and self.official_emb is not None
        ):
            try:
                self.model = _load_embedding_model(self.settings.EMBEDDING_MODEL)
                self.retrieval_mode = "hybrid"
            except Exception as exc:
                self.model = None
                self.retrieval_mode = "bm25_only"
                self.mode_note = (
                    f"Running in BM25-only mode (embedding model unavailable: {exc})."
                )
        else:
            self.retrieval_mode = "bm25_only"
            self.mode_note = "Running in BM25-only mode (embeddings not loaded)."

        # Map normalized reference numbers -> index in self.official
        self.official_by_ref: dict[str, int] = {}
        for idx, doc in enumerate(self.official):
            for raw_r in doc.get("all_refs") or []:
                if raw_r:
                    norm_full = re.sub(r"\s+", " ", str(raw_r).strip()).upper()
                    norm_stripped = _normalize_ref(str(raw_r))
                    if norm_full:
                        self.official_by_ref[norm_full] = idx
                    if norm_stripped:
                        self.official_by_ref[norm_stripped] = idx

    def _encode_queries(self, queries: list[str]) -> np.ndarray | None:
        if self.model is None or not queries:
            return None
        prefixed = [f"query: {q}" for q in queries]
        vecs = self.model.encode(
            prefixed,
            batch_size=len(prefixed),
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.asarray(vecs, dtype=np.float32)

    def _label_score(
        self,
        collection: str,
        cosine_score: float | None,
        bm25_score: float,
    ) -> tuple[str, float]:
        cfg = self.settings
        if cosine_score is not None:
            strong_t = (
                cfg.DEBUNK_STRONG_THRESHOLD
                if collection == "debunks"
                else cfg.OFFICIAL_STRONG_THRESHOLD
            )
            poss_t = (
                cfg.DEBUNK_POSSIBLE_THRESHOLD
                if collection == "debunks"
                else cfg.OFFICIAL_POSSIBLE_THRESHOLD
            )
            if cosine_score >= strong_t:
                return "strong", round(float(cosine_score), 4)
            if cosine_score >= poss_t:
                return "possible", round(float(cosine_score), 4)
            return "none", round(float(cosine_score), 4)

        # BM25 scores are unbounded and grow with query length (long OCR text easily passes 18 on
        # unrelated posts), so BM25 alone never confirms a match: it is capped at "possible".
        # Only exact reference matches (set in search()) can be strong without embeddings.
        if bm25_score >= cfg.BM25_POSSIBLE_THRESHOLD:
            return "possible", round(float(bm25_score), 4)
        return "none", round(float(bm25_score), 4)

    def _rank_collection(
        self,
        records: list[dict[str, Any]],
        bm25: BM25Okapi | None,
        emb_matrix: np.ndarray | None,
        queries: list[str],
        query_vecs: np.ndarray | None,
        collection: str,
        *,
        top_k: int = 3,
        excluded_indices: set[int] | None = None,
        original_text: str | None = None,
        fields: ExtractedFields | None = None,
    ) -> list[MatchItem]:
        n = len(records)
        if n == 0 or not queries:
            return []

        excluded = excluded_indices or set()
        valid_mask = [i not in excluded for i in range(n)]
        if not any(valid_mask):
            return []

        k_rrf = self.settings.RRF_K
        rrf_scores = np.zeros(n, dtype=np.float64)
        max_bm25 = np.zeros(n, dtype=np.float64)
        max_cosine = np.full(n, -1.0, dtype=np.float64)
        has_cosine = emb_matrix is not None and query_vecs is not None

        for q_idx, q_str in enumerate(queries):
            q_tokens = tokenize_multilingual(q_str)
            if bm25 is not None and q_tokens:
                b_scores = np.asarray(bm25.get_scores(q_tokens), dtype=np.float64)
                for ex_i in excluded:
                    b_scores[ex_i] = -1.0
                max_bm25 = np.maximum(max_bm25, np.maximum(b_scores, 0.0))
                # Rank documents with positive BM25 score
                b_order = np.argsort(-b_scores)
                for rank_pos, doc_i in enumerate(b_order, start=1):
                    if b_scores[doc_i] <= 0.0 or doc_i in excluded:
                        break
                    rrf_scores[doc_i] += 1.0 / (k_rrf + rank_pos)

            if has_cosine and emb_matrix is not None and query_vecs is not None:
                c_scores = np.dot(emb_matrix, query_vecs[q_idx]).astype(np.float64)
                for ex_i in excluded:
                    c_scores[ex_i] = -2.0
                max_cosine = np.maximum(max_cosine, c_scores)
                c_order = np.argsort(-c_scores)
                for rank_pos, doc_i in enumerate(c_order, start=1):
                    if doc_i in excluded:
                        continue
                    rrf_scores[doc_i] += 1.0 / (k_rrf + rank_pos)

        for ex_i in excluded:
            rrf_scores[ex_i] = -1.0

        # Sort primarily by RRF score, tie-breaking by cosine similarity then BM25
        candidate_indices = [i for i in range(n) if i not in excluded and rrf_scores[i] > 0]
        candidate_indices.sort(
            key=lambda i: (rrf_scores[i], max_cosine[i], max_bm25[i]),
            reverse=True,
        )

        items: list[MatchItem] = []
        for idx in candidate_indices[:top_k]:
            rec = records[idx]
            cos_val = float(max_cosine[idx]) if has_cosine and max_cosine[idx] > -1.0 else None
            bm25_val = float(max_bm25[idx])
            label, primary_score = self._label_score(collection, cos_val, bm25_val)
            conf_label = "Strong" if label == "strong" else "Related" if label == "possible" else ""
            rel_note = None

            is_exact_ref = False
            if collection == "official":
                rec_ref = (rec.get("reference_no") or "").strip()
                if rec_ref and fields and fields.reference_numbers:
                    norm_rec_ref = _normalize_ref(rec_ref)
                    for q_ref in fields.reference_numbers:
                        norm_q = _normalize_ref(q_ref)
                        if (norm_rec_ref and norm_rec_ref == norm_q) or rec_ref.upper() == q_ref.strip().upper():
                            is_exact_ref = True
                            break
                if is_exact_ref:
                    label = "strong"
                    conf_label = "Exact reference"
                    rel_note = None
                elif label == "strong":
                    t_match = _title_or_subject_matches(
                        original_text or (queries[0] if queries else ""),
                        fields.subject if fields else None,
                        rec.get("title", ""),
                    )
                    if not t_match:
                        label = "possible"
                        conf_label = "Related"
                        rel_note = "Same issuer, different circular"

            raw_snippet = rec.get("snippet", "")
            if collection == "debunks":
                post_text = (
                    rec.get("claim_text")
                    or rec.get("search_text")
                    or rec.get("official_fact")
                    or rec.get("tg_text")
                    or ""
                )
                snippet_to_use = clean_pib_snippet(
                    raw_snippet, post_text=post_text, title=rec.get("title", "")
                )
            else:
                snippet_to_use = (
                    rec.get("title", "")
                    if is_garbled_hindi(raw_snippet)
                    else raw_snippet
                )

            items.append(
                MatchItem(
                    doc_id=rec["doc_id"],
                    collection=collection,  # type: ignore[arg-type]
                    title=rec["title"],
                    snippet=snippet_to_use,
                    date=rec.get("date"),
                    url=rec.get("url"),
                    reference_no=rec.get("reference_no"),
                    narrative_id=rec.get("narrative_id"),
                    narrative_status=rec.get("narrative_status"),
                    official_fact=rec.get("official_fact") or None,
                    score=primary_score,
                    rrf_score=round(float(rrf_scores[idx]), 6),
                    cosine_score=round(cos_val, 4) if cos_val is not None else None,
                    bm25_score=round(bm25_val, 4),
                    label=label,  # type: ignore[arg-type]
                    confidence_label=conf_label,
                    relation_note=rel_note,
                    exact_reference_match=is_exact_ref,
                )
            )
        return items

    def search(
        self,
        *,
        canonical_claim_en: str | None = None,
        original_text: str | None = None,
        fields: ExtractedFields | None = None,
        top_k: int = 3,
        exclude_debunk_id: str | None = None,
        exclude_url: str | None = None,
        exclude_post_id: int | None = None,
    ) -> RetrievalResult:
        """Query both debunks and official collections and merge results."""
        debunk_queries: list[str] = []
        if canonical_claim_en and canonical_claim_en.strip():
            debunk_queries.append(canonical_claim_en.strip())
        if original_text and original_text.strip():
            trimmed_orig = re.sub(r"\s+", " ", original_text.strip())[:600]
            if trimmed_orig and trimmed_orig not in debunk_queries:
                debunk_queries.append(trimmed_orig)

        official_queries: list[str] = []
        if canonical_claim_en and canonical_claim_en.strip():
            official_queries.append(canonical_claim_en.strip())
        if original_text and original_text.strip():
            body_only = strip_letterhead_boilerplate(original_text)
            trimmed_body = re.sub(r"\s+", " ", body_only.strip())[:600]
            if trimmed_body and trimmed_body not in official_queries:
                official_queries.append(trimmed_body)

        debunk_vecs = self._encode_queries(debunk_queries) if debunk_queries else None
        official_vecs = self._encode_queries(official_queries) if official_queries else None

        # Leave-one-out exclusion for debunks (matches doc_id, notice_id, url, or numeric Telegram post_id)
        excluded_debunk_indices: set[int] = set()
        inferred_post_id = exclude_post_id
        if inferred_post_id is None and exclude_debunk_id and exclude_debunk_id.startswith("FN-TG-"):
            tail = exclude_debunk_id.replace("FN-TG-", "").strip()
            if tail.isdigit():
                inferred_post_id = int(tail)

        if exclude_debunk_id or exclude_url or inferred_post_id is not None:
            for i, rec in enumerate(self.debunks):
                if exclude_debunk_id and rec.get("doc_id") == exclude_debunk_id:
                    excluded_debunk_indices.add(i)
                elif exclude_debunk_id and rec.get("notice_id") == exclude_debunk_id:
                    excluded_debunk_indices.add(i)
                elif exclude_url and rec.get("url") and rec.get("url") == exclude_url:
                    excluded_debunk_indices.add(i)
                elif inferred_post_id is not None and rec.get("post_id") == inferred_post_id:
                    excluded_debunk_indices.add(i)

        debunk_matches = self._rank_collection(
            self.debunks,
            self.bm25_debunks,
            self.debunk_emb,
            debunk_queries,
            debunk_vecs,
            "debunks",
            top_k=top_k,
            excluded_indices=excluded_debunk_indices,
            original_text=original_text,
            fields=fields,
        )

        official_matches = self._rank_collection(
            self.official,
            self.bm25_official,
            self.official_emb,
            official_queries,
            official_vecs,
            "official",
            top_k=top_k,
            original_text=original_text,
            fields=fields,
        )

        # Exact reference lookup on official records
        if fields and fields.reference_numbers:
            matched_off_idx: int | None = None
            for ref in fields.reference_numbers:
                for cand in (
                    re.sub(r"\s+", " ", ref.strip()).upper(),
                    _normalize_ref(ref),
                ):
                    if cand and cand in self.official_by_ref:
                        matched_off_idx = self.official_by_ref[cand]
                        break
                if matched_off_idx is not None:
                    break

            if matched_off_idx is not None:
                rec = self.official[matched_off_idx]
                raw_snip = rec.get("snippet", "")
                exact_item = MatchItem(
                    doc_id=rec["doc_id"],
                    collection="official",
                    title=rec["title"],
                    snippet=rec["title"] if is_garbled_hindi(raw_snip) else raw_snip,
                    date=rec.get("date"),
                    url=rec.get("url"),
                    reference_no=rec.get("reference_no"),
                    score=1.0,
                    rrf_score=1.0,
                    cosine_score=1.0 if self.retrieval_mode == "hybrid" else None,
                    bm25_score=100.0,
                    label="strong",
                    confidence_label="Exact reference",
                    exact_reference_match=True,
                )
                official_matches = [
                    exact_item,
                    *[m for m in official_matches if m.doc_id != rec["doc_id"]],
                ][:top_k]

        return RetrievalResult(
            debunks=debunk_matches,
            official=official_matches,
            retrieval_mode=self.retrieval_mode,  # type: ignore[arg-type]
            mode_note=self.mode_note,
            queries_used=debunk_queries,
        )


@lru_cache(maxsize=1)
def get_default_retriever() -> HybridRetriever:
    """Return a cached singleton HybridRetriever."""
    return HybridRetriever()


def match_sources(
    *,
    canonical_claim_en: str | None = None,
    original_text: str | None = None,
    fields: ExtractedFields | None = None,
    top_k: int = 3,
    exclude_debunk_id: str | None = None,
    exclude_url: str | None = None,
    exclude_post_id: int | None = None,
    retriever: HybridRetriever | None = None,
    claimed_issuer_id: str | None = None,
) -> RetrievalResult:
    """Run Stage 4 hybrid source matching plus the claim-level ground-truth check."""
    active_retriever = retriever or get_default_retriever()
    result = active_retriever.search(
        canonical_claim_en=canonical_claim_en,
        original_text=original_text,
        fields=fields,
        top_k=top_k,
        exclude_debunk_id=exclude_debunk_id,
        exclude_url=exclude_url,
        exclude_post_id=exclude_post_id,
    )
    result.ground_truth = check_ground_truth(
        canonical_claim_en,
        claimed_issuer_id,
        exclude_notice_id=exclude_debunk_id,
        exclude_url=exclude_url,
        exclude_post_id=exclude_post_id,
    )
    return result
