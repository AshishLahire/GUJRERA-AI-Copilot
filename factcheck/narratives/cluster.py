"""Clustering debunks with PCA and HDBSCAN, automatic cluster naming, and centroid extraction for Stage 8."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer

from factcheck.forensics.rules import NARRATIVE_KEYWORD_RULES


def _clean_cluster_text(text: str) -> str:
    """Clean text for TF-IDF keyword extraction."""
    # Remove URLs, handles, emojis and special characters while preserving unicode words
    t = re.sub(r"https?://\S+|t\.me/\S+|@\w+", " ", text)
    t = re.sub(r"[^\w\s\u0900-\u097F]+", " ", t)
    return t.strip().lower()


def cluster_debunks(
    debunks: list[dict[str, Any]],
    embeddings: np.ndarray,
    *,
    min_cluster_size: int = 5,
    n_pca: int = 50,
    random_state: int = 42,
) -> dict[str, Any]:
    """L2-normalise embeddings, reduce to ~50 dims via PCA, cluster with HDBSCAN, and name clusters."""
    n_samples = len(debunks)
    if n_samples == 0:
        return {"clusters": [], "noise_count": 0, "noise_rate": 0.0, "labels": []}

    # 1. L2-normalise e5 embeddings
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    norm_embeddings = embeddings / norms

    # 2. PCA reduction to n_pca dimensions
    actual_pca_components = min(n_pca, n_samples, embeddings.shape[1])
    pca = PCA(n_components=actual_pca_components, random_state=random_state)
    pca_embeddings = pca.fit_transform(norm_embeddings)
    explained_var = float(np.sum(pca.explained_variance_ratio_))

    # 3. HDBSCAN clustering (explicit copy=True for scikit-learn compatibility)
    clusterer = HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean", copy=True)
    labels = clusterer.fit_predict(pca_embeddings)

    unique_labels = sorted(set(labels))
    noise_count = int(np.sum(labels == -1))
    noise_rate = noise_count / n_samples

    # Prepare corpus for TF-IDF naming across all debunks
    corpus_texts: list[str] = []
    for d in debunks:
        txt = f"{d.get('title', '')} {d.get('snippet', '')} {d.get('claim_text', '')}"
        corpus_texts.append(_clean_cluster_text(txt))

    vectorizer = TfidfVectorizer(
        max_features=1200,
        stop_words="english",
        token_pattern=r"(?u)\b[a-zA-Z\u0900-\u097F]{3,}\b",
        ngram_range=(1, 2),
        min_df=2,
    )
    try:
        tfidf_matrix = vectorizer.fit_transform(corpus_texts)
        feature_names = np.array(vectorizer.get_feature_names_out())
    except Exception:
        tfidf_matrix = None
        feature_names = np.array([])

    clusters_list: list[dict[str, Any]] = []

    for label_id in unique_labels:
        if label_id == -1:
            continue

        member_indices = [i for i, lbl in enumerate(labels) if lbl == label_id]
        member_debunks = [debunks[i] for i in member_indices]
        cluster_size = len(member_debunks)

        # 4. Centroid in normalized 384-d e5 space
        member_embs = norm_embeddings[member_indices]
        mean_vec = np.mean(member_embs, axis=0)
        mean_norm = np.linalg.norm(mean_vec)
        centroid = (mean_vec / mean_norm if mean_norm > 0 else mean_vec).astype(float).tolist()

        # 5. Find 3 exemplar posts closest to the centroid
        sims = np.dot(member_embs, np.array(centroid))
        closest_order = np.argsort(sims)[::-1]
        exemplar_indices = [member_indices[idx] for idx in closest_order[:3]]
        exemplars = [
            {
                "doc_id": debunks[idx]["doc_id"],
                "title": debunks[idx].get("title", "")[:120],
                "url": debunks[idx].get("url"),
                "date": debunks[idx].get("date"),
                "snippet": debunks[idx].get("snippet", "")[:240],
            }
            for idx in exemplar_indices
        ]

        # 6. Dates and monthly timelines
        dates = [d.get("date") for d in member_debunks if d.get("date")]
        valid_dates = sorted(dates)
        first_date = valid_dates[0] if valid_dates else None
        last_date = valid_dates[-1] if valid_dates else None
        skipped_undated = len(member_debunks) - len(valid_dates)

        monthly_counts: dict[str, int] = defaultdict(int)
        for dt in valid_dates:
            if len(dt) >= 7:
                monthly_counts[dt[:7]] += 1
        monthly_debunks = [
            {"month": m, "count": c}
            for m, c in sorted(monthly_counts.items())
        ]

        # 7. Issuers
        issuer_counter = Counter(
            d.get("claimed_issuer")
            for d in member_debunks
            if d.get("claimed_issuer") and d.get("claimed_issuer") != "Unknown"
        )
        top_issuers = [
            {"issuer": iss, "count": cnt}
            for iss, cnt in issuer_counter.most_common(5)
        ]
        dominant_issuer = top_issuers[0]["issuer"] if top_issuers else None

        # 8. Languages seen
        languages = sorted(
            {
                d.get("language") or "en"
                for d in member_debunks
            }
        )

        # 9. Closest keyword narrative_id from rules.py
        rule_nids = [
            d.get("narrative_id")
            for d in member_debunks
            if d.get("narrative_id") and d.get("narrative_id") != "approximate"
        ]
        dominant_rule_nid = Counter(rule_nids).most_common(1)[0][0] if rule_nids else None

        # 10. Distinctive TF-IDF terms
        distinctive_terms: list[str] = []
        if tfidf_matrix is not None and len(feature_names) > 0:
            cluster_tfidf = tfidf_matrix[member_indices]
            mean_tfidf = np.asarray(cluster_tfidf.mean(axis=0)).flatten()
            top_term_indices = np.argsort(mean_tfidf)[::-1][:6]
            for idx in top_term_indices:
                term = str(feature_names[idx])
                # Skip pure numbers or common stopwords
                if not term.isdigit() and len(term) >= 3:
                    distinctive_terms.append(term)
                if len(distinctive_terms) >= 3:
                    break

        # Human-readable cluster name: prefer keyword narrative if matched, else distinctive terms + issuer
        clean_nid = (
            dominant_rule_nid.replace("NAR-", "").replace("-", " ").title()
            if dominant_rule_nid
            else None
        )
        if clean_nid and dominant_issuer:
            if dominant_issuer.lower() in clean_nid.lower():
                cluster_name = clean_nid
            else:
                cluster_name = f"{dominant_issuer}: {clean_nid}"
        elif clean_nid:
            cluster_name = clean_nid
        elif dominant_issuer and distinctive_terms:
            terms_title = " ".join(t.capitalize() for t in distinctive_terms)
            cluster_name = f"{dominant_issuer}: {terms_title}"
        elif distinctive_terms:
            cluster_name = " ".join(t.capitalize() for t in distinctive_terms)
        elif dominant_issuer:
            cluster_name = f"{dominant_issuer} Related Notices"
        else:
            cluster_name = f"Narrative Cluster {label_id}"

        clusters_list.append({
            "id": f"cluster_{label_id:03d}",
            "numeric_id": int(label_id),
            "name": cluster_name,
            "size": cluster_size,
            "claimed_issuers": top_issuers,
            "first_date": first_date,
            "last_date": last_date,
            "languages": languages,
            "monthly_debunks": monthly_debunks,
            "exemplars": exemplars,
            "centroid": centroid,
            "keyword_narrative_id": dominant_rule_nid,
            "distinctive_terms": distinctive_terms,
            "skipped_undated_posts": skipped_undated,
            "member_doc_ids": [d["doc_id"] for d in member_debunks],
        })

    # Sort clusters by size descending
    clusters_list.sort(key=lambda c: c["size"], reverse=True)

    return {
        "clusters": clusters_list,
        "noise_count": noise_count,
        "noise_rate": noise_rate,
        "pca_explained_variance": explained_var,
        "labels": labels.tolist(),
        "total_clustered": n_samples - noise_count,
        "total_clusters": len(clusters_list),
    }
