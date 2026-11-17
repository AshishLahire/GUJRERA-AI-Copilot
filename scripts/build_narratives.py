"""Build Stage 8 narrative clusters and indicator graph (ZERO API calls).

Clusters the 1,968 debunk records using existing dense e5 embeddings, extracts normalized indicators
(phones, emails, bare domains, references, signatories), identifies template reuse across different
issuers/years, and persists data/index/narratives.json and data/index/indicator_graph.json.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from factcheck.config import get_settings
from factcheck.narratives.cluster import cluster_debunks
from factcheck.narratives.indicators import (
    build_indicator_graph,
    load_official_exclusion_sets,
)


def main() -> None:
    settings = get_settings()
    debunks_meta_path = settings.INDEX_DIR / "debunks_meta.json"
    debunks_emb_path = settings.INDEX_DIR / "debunks_embeddings.npy"

    if not debunks_meta_path.exists() or not debunks_emb_path.exists():
        print(f"Error: missing {debunks_meta_path} or {debunks_emb_path}")
        sys.exit(1)

    print(f"Loading metadata from {debunks_meta_path}...")
    debunks: list[dict[str, Any]] = json.loads(debunks_meta_path.read_text(encoding="utf-8"))
    print(f"Loading embeddings from {debunks_emb_path}...")
    embeddings: np.ndarray = np.load(debunks_emb_path)
    print(f"Loaded {len(debunks)} debunks, embeddings shape {embeddings.shape}")

    # Load official exclusion sets from registry and official corpus
    registry_path = REPO_ROOT / "data" / "dataset" / "03_issuer_registry" / "issuers.json"
    official_corpus_path = REPO_ROOT / "data" / "dataset" / "02_official_source_corpus" / "documents.jsonl"
    ex_phones, ex_emails, ex_domains = load_official_exclusion_sets(registry_path, official_corpus_path)
    print(f"Official exclusions: {len(ex_phones)} phones, {len(ex_emails)} emails, {len(ex_domains)} domains")

    # Load cached OCR texts exclusively from verified fake notices (benchmark and fake demo notices)
    cached_ocr_texts: list[dict[str, Any]] = []
    fake_notice_ids: set[str] = set()

    # 1. From benchmark fake notices
    fake_notices_path = REPO_ROOT / "data" / "processed" / "fake_notices.jsonl"
    if fake_notices_path.exists():
        try:
            for line in fake_notices_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                fn = json.loads(line)
                nid = fn.get("notice_id")
                if nid:
                    fake_notice_ids.add(nid)
        except Exception:
            pass

    # 2. From demo set (fake / forged items only)
    demo_set_path = REPO_ROOT / "data" / "demo" / "demo_set.json"
    demo_fake_hashes: dict[str, dict[str, Any]] = {}
    if demo_set_path.exists():
        try:
            demo_data = json.loads(demo_set_path.read_text(encoding="utf-8"))
            for item in demo_data.get("items", []):
                if item.get("label") in ("fake", "forged"):
                    fake_notice_ids.add(item["id"])
                    img_p = REPO_ROOT / item["image"]
                    if img_p.exists():
                        h = hashlib.sha256(img_p.read_bytes()).hexdigest()
                        demo_fake_hashes[h] = item
        except Exception:
            pass

    # 3. Read cached OCR for these fake notices from ocr_cache.sqlite
    cache_db_path = REPO_ROOT / settings.CACHE_DB_PATH
    if cache_db_path.exists():
        try:
            with sqlite3.connect(cache_db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT image_hash, final_text, fields_json FROM ocr_cache WHERE valid = 1")
                for img_h, f_txt, f_json in cur.fetchall():
                    if img_h in demo_fake_hashes:
                        item = demo_fake_hashes[img_h]
                        cached_ocr_texts.append({
                            "sample_id": item["id"],
                            "filename": item.get("filename") or item["id"],
                            "final_text": f_txt,
                            "expected_issuer": item.get("expected_issuer"),
                        })
        except Exception as e:
            print(f"Warning: could not read ocr_cache.sqlite: {e}")

    # 4. Also include eval fake notice OCRs if present
    eval_ocr_path = REPO_ROOT / "data" / "eval" / "fake_notice_ocr.jsonl"
    if eval_ocr_path.exists():
        try:
            for line in eval_ocr_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                doc = json.loads(line)
                f_txt = doc.get("ocr_result", {}).get("final_text", "")
                nid = doc.get("notice_id") or doc.get("sample_id")
                if f_txt and nid:
                    cached_ocr_texts.append({
                        "sample_id": nid,
                        "filename": doc.get("image", nid),
                        "final_text": f_txt,
                        "expected_issuer": doc.get("claimed_issuer_id"),
                    })
        except Exception:
            pass

    print(f"Loaded {len(cached_ocr_texts)} cached OCR records for indicator linking")

    # 1. Run clustering with min_cluster_size = 5 (optimal setting from sweep)
    min_size = settings.HDBSCAN_MIN_CLUSTER_SIZE
    pca_dims = settings.PCA_COMPONENTS
    print(f"\nClustering with HDBSCAN (min_cluster_size={min_size}, PCA dims={pca_dims})...")
    clustering_res = cluster_debunks(
        debunks,
        embeddings,
        min_cluster_size=min_size,
        n_pca=pca_dims,
    )

    clusters = clustering_res["clusters"]
    print(f"Produced {len(clusters)} narrative clusters.")
    print(f"Clustered posts: {clustering_res['total_clustered']} / {len(debunks)} ({clustering_res['total_clustered']/len(debunks)*100:.1f}%)")
    print(f"Noise posts: {clustering_res['noise_count']} ({clustering_res['noise_rate']*100:.1f}%)")

    # 2. Build indicator graph
    print("\nBuilding indicator graph and detecting template reuse...")
    graph = build_indicator_graph(
        debunks,
        cached_ocr_texts,
        excluded_phones=ex_phones,
        excluded_emails=ex_emails,
        excluded_domains=ex_domains,
    )

    template_reuse = graph["template_reuse"]
    print(f"Indicator nodes: {graph['summary']['total_indicators']}, Edges: {len(graph['edges'])}")
    print(f"Found {len(template_reuse)} template-reuse indicators across different agencies or years.")

    # 3. Associate shared indicators with their clusters
    doc_to_cluster: dict[str, str] = {}
    for c in clusters:
        for doc_id in c["member_doc_ids"]:
            doc_to_cluster[doc_id] = c["id"]

    for c in clusters:
        cluster_doc_ids = set(c["member_doc_ids"])
        c_shared_inds: list[dict[str, Any]] = []
        for tr in template_reuse:
            # Check if this template reuse indicator appears in this cluster
            intersection = cluster_doc_ids.intersection(tr["linked_records"])
            if intersection:
                c_shared_inds.append(tr)
        c["shared_indicators"] = c_shared_inds
        c["shared_indicators_count"] = len(c_shared_inds)

    # 4. Save to data/index/
    settings.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    narratives_payload = {
        "version": "1.0",
        "clustering_config": {
            "min_cluster_size": min_size,
            "pca_components": pca_dims,
            "explained_variance": round(clustering_res["pca_explained_variance"], 4),
        },
        "stats": {
            "total_debunks": len(debunks),
            "total_clusters": len(clusters),
            "total_clustered": clustering_res["total_clustered"],
            "noise_count": clustering_res["noise_count"],
            "noise_rate": round(clustering_res["noise_rate"], 4),
            "total_template_reuse_indicators": len(template_reuse),
        },
        "clusters": clusters,
    }

    print(f"\nWriting {settings.NARRATIVES_INDEX_PATH}...")
    settings.NARRATIVES_INDEX_PATH.write_text(
        json.dumps(narratives_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Writing {settings.INDICATOR_GRAPH_PATH}...")
    settings.INDICATOR_GRAPH_PATH.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Display Top 10 Narratives
    print("\n=== Top 10 Narratives by Size ===")
    for i, c in enumerate(clusters[:10], 1):
        issuers_str = ", ".join(x["issuer"] for x in c["claimed_issuers"][:2]) or "N/A"
        date_range = f"{c['first_date'] or 'N/A'} to {c['last_date'] or 'N/A'}"
        print(f"#{i:02d} [{c['id']}] {c['name']} | Size: {c['size']} | Issuers: {issuers_str} | Dates: {date_range} | Shared Inds: {c['shared_indicators_count']}")

    # Display Top 10 Template Reuse Findings
    print("\n=== Top 10 Template-Reuse Findings (Cross-Issuer / Cross-Year) ===")
    for i, tr in enumerate(template_reuse[:10], 1):
        print(f"#{i:02d} [{tr['kind']}] {tr['value']} -> Linked docs: {len(tr['linked_records'])} | Issuers: {', '.join(tr['issuers'])} | Years: {', '.join(tr['years'])}")
        print(f"     Summary: {tr['summary']}")

    print("\nBuild completed successfully.")


if __name__ == "__main__":
    main()
