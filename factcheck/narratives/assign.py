"""Document narrative assignment and indicator linking for Stage 8."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

import numpy as np

from factcheck.config import Settings, get_settings
from factcheck.narratives.indicators import extract_indicators_from_text
from factcheck.schemas import NarrativeMatchResult, SharedIndicatorItem


@lru_cache(maxsize=1)
def load_narratives_index(
    narratives_path: Path | None = None,
    graph_path: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Load precomputed narratives and indicator graph from data/index."""
    settings = get_settings()
    n_path = narratives_path or settings.NARRATIVES_INDEX_PATH
    g_path = graph_path or settings.INDICATOR_GRAPH_PATH

    narratives: dict[str, Any] | None = None
    graph: dict[str, Any] | None = None

    if n_path.exists():
        try:
            narratives = json.loads(n_path.read_text(encoding="utf-8"))
        except Exception:
            narratives = None

    if g_path.exists():
        try:
            graph = json.loads(g_path.read_text(encoding="utf-8"))
        except Exception:
            graph = None

    return narratives, graph


def assign_document_narrative(
    doc_text: str,
    doc_embedding: np.ndarray | list[float] | None = None,
    *,
    narratives_data: dict[str, Any] | None = None,
    indicator_graph: dict[str, Any] | None = None,
    threshold: float | None = None,
    exclude_doc_id: str | None = None,
    settings: Settings | None = None,
) -> NarrativeMatchResult:
    """Assign document to nearest narrative cluster above threshold and find shared template indicators."""
    cfg = settings or get_settings()
    assign_threshold = threshold if threshold is not None else cfg.NARRATIVE_ASSIGN_THRESHOLD

    if narratives_data is None or indicator_graph is None:
        loaded_n, loaded_g = load_narratives_index(
            cfg.NARRATIVES_INDEX_PATH,
            cfg.INDICATOR_GRAPH_PATH,
        )
        narratives_data = narratives_data or loaded_n
        indicator_graph = indicator_graph or loaded_g

    if not narratives_data or not narratives_data.get("clusters"):
        return NarrativeMatchResult(assigned=False, summary_text="No narrative index loaded")

    clusters: list[dict[str, Any]] = narratives_data["clusters"]

    # 1. Centroid similarity check if doc_embedding is provided
    best_cluster: dict[str, Any] | None = None
    best_sim: float = 0.0

    if doc_embedding is not None:
        emb_vec = np.array(doc_embedding, dtype=float).flatten()
        emb_norm = np.linalg.norm(emb_vec)
        if emb_norm > 0:
            emb_unit = emb_vec / emb_norm
            for c in clusters:
                c_centroid = np.array(c.get("centroid") or [], dtype=float)
                if len(c_centroid) == len(emb_unit):
                    sim = float(np.dot(emb_unit, c_centroid))
                    if sim > best_sim:
                        best_sim = sim
                        best_cluster = c

    # 2. Extract indicators from document text
    extracted_indicators = extract_indicators_from_text(doc_text)

    # 3. Look up extracted indicators in the indicator graph
    matched_shared_indicators: list[SharedIndicatorItem] = []
    if indicator_graph:
        # Build lookup from indicator_id to template_reuse item or indicator node
        reuse_map = {
            item["indicator_id"]: item
            for item in indicator_graph.get("template_reuse", [])
        }
        # Also build lookup from indicator_id to all linked edges
        edge_targets: dict[str, list[str]] = {}
        for edge in indicator_graph.get("edges", []):
            edge_targets.setdefault(edge["target"], []).append(edge["source"])

        # Record metadata lookup
        node_lookup = {
            node["id"]: node
            for node in indicator_graph.get("nodes", [])
            if node.get("type") == "record"
        }

        for kind, values in extracted_indicators.items():
            for val in values:
                ind_id = f"{kind}:{val}"
                raw_linked = edge_targets.get(ind_id, [])

                # Leave-one-out filter: exclude sample's own record
                linked_filtered = [r for r in raw_linked if r != exclude_doc_id]

                if linked_filtered:
                    # Gather unique issuers and years from remaining linked records
                    issuers_set = {
                        node_lookup[r].get("issuer")
                        for r in linked_filtered
                        if r in node_lookup and node_lookup[r].get("issuer") and node_lookup[r].get("issuer") != "Unknown"
                    }
                    years_set = {
                        node_lookup[r].get("year")
                        for r in linked_filtered
                        if r in node_lookup and node_lookup[r].get("year") and node_lookup[r].get("year") != "Unknown"
                    }

                    issuers_list = sorted(issuers_set)
                    years_list = sorted(years_set)

                    if len(issuers_list) >= 2 or len(years_list) >= 2:
                        summary = f"Shared across {len(linked_filtered)} debunked documents"
                        if issuers_list:
                            summary += f" ({', '.join(issuers_list[:2])})"
                        if years_list:
                            summary += f" from {', '.join(years_list)}"
                    else:
                        summary = f"Appears in {len(linked_filtered)} other debunked record(s)"
                        if years_list:
                            summary += f" ({', '.join(years_list)})"

                    matched_shared_indicators.append(
                        SharedIndicatorItem(
                            indicator_id=ind_id,
                            kind=kind,  # type: ignore[arg-type]
                            value=val,
                            linked_records=linked_filtered,
                            issuers=issuers_list,
                            years=years_list,
                            summary=summary,
                        )
                    )

    # 4. Check if similarity meets assign_threshold
    assigned = bool(best_cluster is not None and best_sim >= assign_threshold)

    if assigned and best_cluster is not None:
        # Calculate cluster size taking into account exclude_doc_id
        member_ids = best_cluster.get("member_doc_ids", [])
        cluster_size = len([m for m in member_ids if m != exclude_doc_id]) if member_ids else best_cluster["size"]
        first_date = best_cluster.get("first_date")
        last_date = best_cluster.get("last_date")
        c_name = best_cluster["name"]

        first_year = first_date[:4] if first_date and len(first_date) >= 4 else "recent years"
        summary = f"Debunked {cluster_size} times since {first_year} (latest {last_date or 'N/A'})"

        return NarrativeMatchResult(
            assigned=True,
            cluster_id=best_cluster["id"],
            narrative_name=c_name,
            size=cluster_size,
            first_date=first_date,
            last_date=last_date,
            debunks_count=cluster_size,
            similarity=round(best_sim, 3),
            shared_indicators=matched_shared_indicators,
            summary_text=summary,
        )

    # Not assigned to a cluster, but may still have shared template indicators
    return NarrativeMatchResult(
        assigned=False,
        similarity=round(best_sim, 3),
        shared_indicators=matched_shared_indicators,
        summary_text=None,
    )
