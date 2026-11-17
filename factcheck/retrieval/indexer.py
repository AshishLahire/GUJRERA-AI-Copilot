"""Build and persist the deduplicated debunk and official document indices in `data/index/`."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from factcheck.config import get_settings
from factcheck.forensics.rules import infer_narrative_from_text

REPO_ROOT = Path(__file__).resolve().parents[2]
TG_POSTS_PATH = REPO_ROOT / "data" / "dataset" / "_raw" / "tg_posts.jsonl"
PROC_FAKE_PATH = REPO_ROOT / "data" / "processed" / "fake_notices.jsonl"
RAW_FAKE_PATH = REPO_ROOT / "data" / "dataset" / "01_fake_notice_benchmark" / "notices.jsonl"
OFFICIAL_DOCS_PATH = REPO_ROOT / "data" / "dataset" / "02_official_source_corpus" / "documents.jsonl"

TOKEN_RE = re.compile(r"[\w\u0900-\u0DFF]+", re.UNICODE)
TG_URL_ID_RE = re.compile(r"t\.me/PIB_FactCheck/(\d+)", re.IGNORECASE)

# Strip repetitive PIB social footer boilerplate from indexed search text so unrelated posts don't match on helpline/handle
PIB_BOILERPLATE_STRIP_RE = re.compile(
    r"(?i)(?:"
    r"#\s*PIBFactCheck|@\s*PIBFactCheck|t\.me/PIB_FactCheck|socialmedia@pib\.gov\.in|factcheck@pib\.gov\.in"
    r"|\+?91\s*87997\s*11259|Follow\s+us\s+on\s+social\s+media[^\n]*|Report\s+suspicious\s+content[^\n]*"
    r"|Do\s+not\s+share\s+or\s+rely\s+on\s+unverified\s+documents[^\n]*"
    r"|संदिग्ध\s+जानकारी\s+यहाँ\s+साझा\s+करें[^\n]*|सोशल\s+मीडिया\s+पर\s+हमें\s+फॉलो\s+करें[^\n]*"
    r")"
)


def tokenize_multilingual(text: str) -> list[str]:
    """Simple multilingual word/number tokenizer supporting Latin and Indic scripts."""
    if not text:
        return []
    return [tok.lower() for tok in TOKEN_RE.findall(text) if len(tok) > 1 or tok.isdigit()]


def _clean_for_index(text: str) -> str:
    cleaned = PIB_BOILERPLATE_STRIP_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _extract_tg_post_id(url: str | None, notice_id: str | None = None) -> int | None:
    if url:
        m = TG_URL_ID_RE.search(url)
        if m:
            return int(m.group(1))
    if notice_id and notice_id.startswith("FN-TG-"):
        tail = notice_id.replace("FN-TG-", "").strip()
        if tail.isdigit():
            return int(tail)
    return None


def load_deduplicated_debunks() -> list[dict[str, Any]]:
    """Load and deduplicate fake_notices.jsonl and tg_posts.jsonl into ONE record per debunk."""
    fake_rows: list[dict[str, Any]] = []
    source_fake_path = PROC_FAKE_PATH if PROC_FAKE_PATH.exists() else RAW_FAKE_PATH
    if source_fake_path.exists():
        for line in source_fake_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                fake_rows.append(json.loads(line))

    tg_by_id: dict[int, dict[str, Any]] = {}
    if TG_POSTS_PATH.exists():
        for line in TG_POSTS_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            pid = row.get("post_id")
            if isinstance(pid, int):
                tg_by_id[pid] = row

    records: list[dict[str, Any]] = []
    consumed_tg_ids: set[int] = set()

    # 1. Process all annotated fake_notices entries first, merging their source Telegram post if any
    for fn in fake_rows:
        nid = fn.get("notice_id") or fn.get("id") or ""
        src_url = fn.get("source_url")
        pid = _extract_tg_post_id(src_url, nid)
        tg_post = tg_by_id.get(pid) if pid is not None else None
        if pid is not None and tg_post is not None:
            consumed_tg_ids.add(pid)

        claim_text = (fn.get("clean_claim") or fn.get("claim") or "").strip()
        official_fact = (fn.get("official_fact") or "").strip()
        tg_text = (tg_post.get("text") or "").strip() if tg_post else ""

        date_str = fn.get("post_date")
        if not date_str and tg_post and tg_post.get("datetime"):
            date_str = str(tg_post["datetime"])[:10]

        url_str = src_url or (tg_post.get("url") if tg_post else None)
        narrative_id = fn.get("narrative_id")
        narrative_status = "annotated" if narrative_id else None
        if not narrative_id:
            inferred = infer_narrative_from_text(f"{claim_text} {official_fact} {tg_text}")
            if inferred:
                narrative_id = inferred
                narrative_status = "approximate"

        title = claim_text[:140] if claim_text else (tg_text[:140] if tg_text else nid)
        snippet_parts = [p for p in (claim_text, official_fact) if p]
        if not snippet_parts and tg_text:
            snippet_parts = [tg_text]
        snippet = " — ".join(snippet_parts)[:320]

        # Combine unique text parts for indexing
        combined_parts = [
            _clean_for_index(claim_text),
            _clean_for_index(official_fact),
        ]
        cleaned_tg = _clean_for_index(tg_text)
        if cleaned_tg and cleaned_tg not in combined_parts[0] and cleaned_tg not in combined_parts[1]:
            combined_parts.append(cleaned_tg)
        search_text = " ".join(p for p in combined_parts if p).strip()

        records.append(
            {
                "doc_id": nid,
                "collection": "debunks",
                "notice_id": nid,
                "post_id": pid,
                "url": url_str,
                "date": date_str,
                "claimed_issuer": fn.get("claimed_issuer") or fn.get("claimed_issuer_id"),
                "narrative_id": narrative_id,
                "narrative_status": narrative_status,
                "claim_text": claim_text,
                "official_fact": official_fact,
                "tg_text": tg_text,
                "title": title,
                "snippet": snippet,
                "search_text": search_text,
                "tokens": tokenize_multilingual(search_text),
            }
        )

    # 2. Process remaining Telegram posts not already linked to a fake_notices entry
    for pid, tg_post in sorted(tg_by_id.items()):
        if pid in consumed_tg_ids:
            continue
        tg_text = (tg_post.get("text") or "").strip()
        cleaned_tg = _clean_for_index(tg_text)
        if len(cleaned_tg) < 25:
            continue

        date_str = str(tg_post.get("datetime") or "")[:10] or None
        url_str = tg_post.get("url")
        inferred_nar = infer_narrative_from_text(tg_text)
        first_line = next(
            (
                ln.strip()
                for ln in cleaned_tg.splitlines()
                if len(tokenize_multilingual(ln)) >= 3
            ),
            cleaned_tg[:140] or f"PIB Fact Check #{pid}",
        )

        records.append(
            {
                "doc_id": f"TG-{pid:04d}",
                "collection": "debunks",
                "notice_id": None,
                "post_id": pid,
                "url": url_str,
                "date": date_str,
                "claimed_issuer": None,
                "narrative_id": inferred_nar,
                "narrative_status": "approximate" if inferred_nar else None,
                "claim_text": "",
                "official_fact": "",
                "tg_text": tg_text,
                "title": first_line[:140],
                "snippet": cleaned_tg[:320],
                "search_text": cleaned_tg,
                "tokens": tokenize_multilingual(cleaned_tg),
            }
        )

    return records


def load_official_records() -> list[dict[str, Any]]:
    """Load official documents from `02_official_source_corpus/documents.jsonl`."""
    records: list[dict[str, Any]] = []
    if not OFFICIAL_DOCS_PATH.exists():
        return records

    for line in OFFICIAL_DOCS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        doc_id = doc.get("doc_id") or ""
        title = (doc.get("title") or doc_id).strip()
        text = (doc.get("text") or "").strip()
        ref_no = doc.get("reference_no")
        dept_ref = doc.get("department_ref")
        issuer_id = doc.get("issuer_id")
        url = doc.get("pdf_url") or doc.get("source_url")
        date_str = doc.get("date_published")

        ref_display = ref_no or dept_ref
        snippet = text[:300] if text else title
        search_text = " ".join(
            p for p in (issuer_id, ref_no, dept_ref, title, text[:1500]) if p
        ).strip()

        records.append(
            {
                "doc_id": doc_id,
                "collection": "official",
                "issuer_id": issuer_id,
                "reference_no": ref_display,
                "all_refs": [r for r in (ref_no, dept_ref) if r],
                "url": url,
                "date": date_str,
                "title": f"{issuer_id}: {title}" if issuer_id and not title.startswith(issuer_id) else title,
                "snippet": snippet,
                "search_text": search_text,
                "tokens": tokenize_multilingual(search_text),
            }
        )
    return records


def build_and_save_index(
    index_dir: Path | None = None,
    embedding_model_name: str | None = None,
) -> dict[str, Any]:
    """Build BM25 metadata and multilingual-e5 passage embeddings and save to `data/index/`."""
    cfg = get_settings()
    target_dir = index_dir or (
        cfg.INDEX_DIR if cfg.INDEX_DIR.is_absolute() else REPO_ROOT / cfg.INDEX_DIR
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    model_name = embedding_model_name or cfg.EMBEDDING_MODEL

    debunks = load_deduplicated_debunks()
    official = load_official_records()

    debunk_meta_path = target_dir / "debunks_meta.json"
    official_meta_path = target_dir / "official_meta.json"
    debunk_emb_path = target_dir / "debunks_embeddings.npy"
    official_emb_path = target_dir / "official_embeddings.npy"
    manifest_path = target_dir / "index_manifest.json"

    debunk_meta_path.write_text(json.dumps(debunks, ensure_ascii=False), encoding="utf-8")
    official_meta_path.write_text(json.dumps(official, ensure_ascii=False), encoding="utf-8")

    embeddings_built = False
    error_msg: str | None = None
    try:
        from sentence_transformers import SentenceTransformer

        try:
            model = SentenceTransformer(model_name, local_files_only=True)
        except Exception:
            model = SentenceTransformer(model_name)
        debunk_passages = [f"passage: {r['search_text']}" for r in debunks]
        official_passages = [f"passage: {r['search_text']}" for r in official]

        debunk_vecs = model.encode(
            debunk_passages,
            batch_size=64,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        official_vecs = model.encode(
            official_passages,
            batch_size=64,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        np.save(debunk_emb_path, np.asarray(debunk_vecs, dtype=np.float32))
        np.save(official_emb_path, np.asarray(official_vecs, dtype=np.float32))
        embeddings_built = True
    except Exception as exc:
        error_msg = str(exc)

    manifest = {
        "debunks_count": len(debunks),
        "official_count": len(official),
        "embedding_model": model_name,
        "embeddings_built": embeddings_built,
        "error": error_msg,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_or_build_index(index_dir: Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], np.ndarray | None, np.ndarray | None]:
    """Load prebuilt metadata and embeddings from `data/index/` (or build metadata on the fly if missing)."""
    cfg = get_settings()
    target_dir = index_dir or (
        cfg.INDEX_DIR if cfg.INDEX_DIR.is_absolute() else REPO_ROOT / cfg.INDEX_DIR
    )
    debunk_meta_path = target_dir / "debunks_meta.json"
    official_meta_path = target_dir / "official_meta.json"
    debunk_emb_path = target_dir / "debunks_embeddings.npy"
    official_emb_path = target_dir / "official_embeddings.npy"

    if debunk_meta_path.exists() and official_meta_path.exists():
        debunks = json.loads(debunk_meta_path.read_text(encoding="utf-8"))
        official = json.loads(official_meta_path.read_text(encoding="utf-8"))
    else:
        debunks = load_deduplicated_debunks()
        official = load_official_records()

    debunk_emb: np.ndarray | None = None
    official_emb: np.ndarray | None = None
    if debunk_emb_path.exists() and official_emb_path.exists():
        try:
            debunk_emb = np.load(debunk_emb_path)
            official_emb = np.load(official_emb_path)
            if len(debunk_emb) != len(debunks) or len(official_emb) != len(official):
                debunk_emb = None
                official_emb = None
        except Exception:
            debunk_emb = None
            official_emb = None

    return debunks, official, debunk_emb, official_emb
