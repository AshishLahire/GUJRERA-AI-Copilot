"""Held-out dataset leakage check:
1. Real PDFs: extract page 1 text using pypdfium2 (no OCR, no external API).
   Check overlap with official index: exact reference match, same URL/title, or e5 similarity > 0.95.
2. Fake images: check against debunk index and demo images by image hash (SHA-256 & MD5) and perceptual match.
3. Write data/heldout/manifest.json.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pypdfium2 as pdfium
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from factcheck.extract.ocr.fields import extract_fields
from factcheck.retrieval.matcher import get_default_retriever

HELDOUT_DIR = REPO_ROOT / "data" / "heldout"
OFFICIAL_META_PATH = REPO_ROOT / "data" / "index" / "official_meta.json"
OFFICIAL_EMBS_PATH = REPO_ROOT / "data" / "index" / "official_embeddings.npy"
OFFICIAL_DOCS_PATH = REPO_ROOT / "data" / "processed" / "official_docs.jsonl"
DEBUNKS_META_PATH = REPO_ROOT / "data" / "index" / "debunks_meta.json"
DEMO_IMAGES_DIR = REPO_ROOT / "data" / "demo" / "images"
BENCHMARK_IMAGES_DIR = REPO_ROOT / "data" / "dataset" / "01_fake_notice_benchmark" / "images"


def hash_file(p: Path) -> tuple[str, str]:
    data = p.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    return md5, sha256


def normalize_ref(ref: str) -> str:
    return re.sub(r"[\s/\\.-]", "", ref.lower())


def run_leakage_check() -> list[dict[str, Any]]:
    manifest_entries: list[dict[str, Any]] = []

    # 1. Load official records
    official_meta = json.loads(OFFICIAL_META_PATH.read_text(encoding="utf-8")) if OFFICIAL_META_PATH.exists() else []
    official_embs = np.load(OFFICIAL_EMBS_PATH) if OFFICIAL_EMBS_PATH.exists() else None
    
    retriever = get_default_retriever()

    # Pre-index official references, titles, and URLs
    official_refs: dict[str, str] = {}  # norm_ref -> doc_id
    official_titles: dict[str, str] = {}
    official_urls: dict[str, str] = {}

    for doc in official_meta:
        doc_id = doc.get("doc_id", "")
        for ref in doc.get("reference_numbers", []):
            official_refs[normalize_ref(ref)] = doc_id
        if doc.get("title"):
            official_titles[doc["title"].strip().lower()] = doc_id
        if doc.get("url"):
            official_urls[doc["url"].strip().lower()] = doc_id

    # Also check official_docs.jsonl if present
    if OFFICIAL_DOCS_PATH.exists():
        for line in OFFICIAL_DOCS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                did = d.get("doc_id", "")
                if d.get("reference_no"):
                    official_refs[normalize_ref(d["reference_no"])] = did
                if d.get("url"):
                    official_urls[d["url"].strip().lower()] = did
                if d.get("title"):
                    official_titles[d["title"].strip().lower()] = did

    # 2. Check Real PDFs
    real_dir = HELDOUT_DIR / "real"
    print("\n--- CHECKING HELD-OUT REAL PDFs ---")
    for pdf_file in sorted(real_dir.glob("*.pdf")):
        doc = pdfium.PdfDocument(str(pdf_file))
        n_pages = len(doc)
        page1 = doc[0]
        textpage = page1.get_textpage()
        page1_text = textpage.get_text_range().strip()

        in_index = False
        reasons = []

        # Check references in page 1 text
        fields = extract_fields(page1_text) if page1_text else None
        extracted_refs = fields.reference_numbers if fields else []
        for ref in extracted_refs:
            norm_r = normalize_ref(ref)
            if norm_r in official_refs:
                in_index = True
                reasons.append(f"exact reference match '{ref}' -> {official_refs[norm_r]}")

        # Check title / filename
        fn_clean = pdf_file.stem.lower()
        if fn_clean in official_titles:
            in_index = True
            reasons.append(f"title match -> {official_titles[fn_clean]}")

        # Check embedding similarity > 0.95
        if page1_text and retriever.model is not None and official_embs is not None and len(official_embs) > 0:
            query_emb = retriever.model.encode([f"query: {page1_text[:500]}"], normalize_embeddings=True)[0]
            sims = np.dot(official_embs, query_emb)
            max_idx = int(np.argmax(sims))
            max_sim = float(sims[max_idx])
            if max_sim > 0.95:
                in_index = True
                reasons.append(f"high embedding similarity ({max_sim:.3f}) with {official_meta[max_idx]['doc_id']}")

        reason_str = "; ".join(reasons) if reasons else "No match in official index"
        print(f"[{'IN INDEX' if in_index else 'FRESH'}] {pdf_file.name} ({n_pages} pages, {len(page1_text)} chars): {reason_str}")

        manifest_entries.append({
            "file": f"real/{pdf_file.name}",
            "group": "real",
            "pages": n_pages,
            "in_index": in_index,
            "reason": reason_str,
            "duplicate_of": None,
            "has_pib_overlay": None,
        })

    # 3. Check Fake Images
    fake_dir = HELDOUT_DIR / "fake"
    print("\n--- CHECKING HELD-OUT FAKE IMAGES ---")

    # Build lookup of demo images and benchmark images by MD5 and SHA256
    known_image_hashes: dict[str, str] = {}  # sha256 -> id/path
    for d_img in DEMO_IMAGES_DIR.glob("*.*"):
        if d_img.is_file():
            _, sha = hash_file(d_img)
            known_image_hashes[sha] = f"demo/{d_img.name}"
    for b_img in BENCHMARK_IMAGES_DIR.glob("*.*"):
        if b_img.is_file():
            _, sha = hash_file(b_img)
            known_image_hashes[sha] = f"benchmark/{b_img.name}"

    debunks_meta = json.loads(DEBUNKS_META_PATH.read_text(encoding="utf-8")) if DEBUNKS_META_PATH.exists() else []
    for d in debunks_meta:
        if d.get("image_hash"):
            known_image_hashes[d["image_hash"]] = d["doc_id"]

    for fake_file in sorted(fake_dir.glob("*.*")):
        if fake_file.name == "manifest.json":
            continue

        md5, sha = hash_file(fake_file)
        duplicate_of = known_image_hashes.get(sha) or known_image_hashes.get(md5)
        in_index = duplicate_of is not None
        reason = f"Exact image duplicate of {duplicate_of}" if duplicate_of else "New unindexed fake image"

        print(f"[{'DUPLICATE' if in_index else 'FRESH'}] {fake_file.name}: {reason}")

        manifest_entries.append({
            "file": f"fake/{fake_file.name}",
            "group": "fake",
            "pages": 1,
            "in_index": in_index,
            "reason": reason,
            "duplicate_of": duplicate_of,
            "has_pib_overlay": None,
        })

    # Write data/heldout/manifest.json
    out_manifest = HELDOUT_DIR / "manifest.json"
    out_manifest.write_text(json.dumps(manifest_entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {len(manifest_entries)} entries to {out_manifest}")

    return manifest_entries


if __name__ == "__main__":
    run_leakage_check()
