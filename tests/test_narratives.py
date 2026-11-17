"""Unit tests for Stage 8: narrative detection, HDBSCAN clustering, indicator extraction, and template reuse."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np

from factcheck.api.app import app
from factcheck.narratives.assign import assign_document_narrative
from factcheck.narratives.cluster import cluster_debunks
from factcheck.narratives.indicators import (
    build_indicator_graph,
    extract_indicators_from_text,
    extract_registered_domain,
    extract_signatories,
    normalize_domain,
    normalize_email,
    normalize_phone,
    normalize_reference,
)
from factcheck.schemas import ExtractedFields, OCRResult


def test_clustering_runs_on_small_fixture():
    """1. HDBSCAN clustering with PCA reduction runs on a small synthetic fixture."""
    # 15 synthetic items across 3 distinct clusters + 1 outlier
    rng = np.random.RandomState(42)
    c1 = rng.normal(loc=0.8, scale=0.05, size=(5, 384))
    c2 = rng.normal(loc=-0.8, scale=0.05, size=(5, 384))
    c3 = rng.normal(loc=0.0, scale=0.05, size=(5, 384))
    embs = np.vstack([c1, c2, c3])

    debunks = [
        {"doc_id": f"D1_{i}", "title": "MUDRA Loan Approval Letter Scheme", "snippet": "Approved loan fee", "date": "2023-01-15", "claimed_issuer": "MUDRA"}
        for i in range(5)
    ] + [
        {"doc_id": f"D2_{i}", "title": "Railway Board Contractual Appointment", "snippet": "Railway jobs regularized", "date": "2024-03-20", "claimed_issuer": "Railway Board"}
        for i in range(5)
    ] + [
        {"doc_id": f"D3_{i}", "title": "TRAI 5G Mobile Tower Installation", "snippet": "Tower rent monthly fee", "date": "2025-05-10", "claimed_issuer": "TRAI"}
        for i in range(5)
    ]

    res = cluster_debunks(debunks, embs, min_cluster_size=3, n_pca=10)
    assert res["total_clusters"] >= 2
    assert res["total_clustered"] > 0
    assert len(res["clusters"]) >= 2
    first_c = res["clusters"][0]
    assert "centroid" in first_c
    assert len(first_c["centroid"]) == 384
    assert first_c["size"] >= 3
    assert first_c["exemplars"]


def test_indicator_extraction_and_normalization():
    """2. Extract and normalize phone, email, bare domain, reference, and signatory."""
    text = (
        "GOVERNMENT NOTICE\n"
        "Reference No: CIRCULAR/2024/09812\n"
        "For verification, visit http://www.fraud-portal.online/apply or email support@fraud-portal.online\n"
        "Contact officer on +91 98765 43210.\n"
        "Sd/-\n"
        "(Dr. Ramesh Sharma)\n"
        "Director (Administration)\n"
    )
    inds = extract_indicators_from_text(text)
    assert "9876543210" in inds["phone"]
    assert "support@fraud-portal.online" in inds["email"]
    assert "fraud-portal.online" in inds["domain"]
    assert "CIRCULAR/2024/09812" in inds["reference"]
    assert "Ramesh Sharma" in inds["signatory"]


def test_pib_contacts_and_official_helplines_excluded():
    """3. PIB WhatsApp, PIB emails, official helplines (1930, 112, 1800), and job titles alone are excluded."""
    # PIB contacts
    assert normalize_phone("+91 87997 11259") is None
    assert normalize_phone("1930") is None
    assert normalize_phone("1800-11-2233") is None
    assert normalize_email("socialmedia@pib.gov.in") is None
    assert normalize_email("factcheck@pib.gov.in") is None
    assert normalize_email("officer@incometax.gov.in") is None
    assert normalize_domain("https://pib.gov.in/factcheck") is None
    assert normalize_domain("https://www.nic.in") is None
    assert normalize_domain("wa.me/918799711259") is None
    assert normalize_reference("8799711259") is None
    assert normalize_reference("SHORT") is None  # < 6 chars

    # Job titles alone are not signatory person names
    assert "Director" not in extract_signatories("Director\nMinistry of Finance")
    assert "Authorised Signatory" not in extract_signatories("Authorised Signatory\nNew Delhi")


def test_cross_issuer_and_cross_year_template_reuse_detection():
    """4. An indicator appearing in 2+ records across different issuers or years is identified as template reuse."""
    records = [
        {
            "doc_id": "REC_A",
            "title": "Mudra Loan Approval",
            "claimed_issuer": "MUDRA",
            "date": "2023-04-10",
            "claim_text": "Call +91 99998 88877 or visit http://scam-network.top",
        },
        {
            "doc_id": "REC_B",
            "title": "TRAI 5G Tower Scheme",
            "claimed_issuer": "TRAI",
            "date": "2024-06-15",
            "claim_text": "Deposit fee to call +91 99998 88877, visit http://scam-network.top",
        },
    ]
    graph = build_indicator_graph(records)
    reused = graph["template_reuse"]
    assert len(reused) >= 2  # both phone 9999888877 and domain scam-network.top reused
    phone_reuse = next(r for r in reused if r["kind"] == "phone")
    assert phone_reuse["value"] == "9999888877"
    assert set(phone_reuse["issuers"]) == {"MUDRA", "TRAI"}
    assert set(phone_reuse["years"]) == {"2023", "2024"}
    assert "REC_A" in phone_reuse["linked_records"] and "REC_B" in phone_reuse["linked_records"]


def test_nearest_narrative_assignment_and_threshold():
    """5. Nearest cluster is assigned when cosine similarity >= threshold; below threshold returns assigned=False."""
    # Fake cluster with centroid along first dimension
    c_centroid = [1.0] + [0.0] * 383
    fake_clusters = {
        "clusters": [
            {
                "id": "cluster_001",
                "name": "MUDRA: Loan Scheme Scam",
                "size": 2,
                "first_date": "2022-03-01",
                "last_date": "2025-08-01",
                "centroid": c_centroid,
                "member_doc_ids": ["DOC_1", "DOC_2"],
            }
        ]
    }
    fake_graph = {
        "nodes": [
            {"id": "DOC_1", "type": "record", "issuer": "MUDRA", "year": "2023"},
            {"id": "phone:9876543210", "type": "indicator", "kind": "phone", "value": "9876543210"},
        ],
        "edges": [
            {"source": "DOC_1", "target": "phone:9876543210", "kind": "contains"},
        ],
        "template_reuse": [],
    }

    # Query with high alignment (cosine = 1.0 >= 0.83)
    matching_emb = [1.0] + [0.0] * 383
    res_high = assign_document_narrative(
        "Call 9876543210 for MUDRA loan",
        doc_embedding=matching_emb,
        narratives_data=fake_clusters,
        indicator_graph=fake_graph,
        threshold=0.83,
    )
    assert res_high.assigned is True
    assert res_high.cluster_id == "cluster_001"
    assert "MUDRA" in (res_high.narrative_name or "")
    assert res_high.debunks_count == 2
    assert len(res_high.shared_indicators) == 1
    assert res_high.shared_indicators[0].value == "9876543210"

    # Query with orthogonal vector (cosine = 0.0 < 0.83)
    unrelated_emb = [0.0, 1.0] + [0.0] * 382
    res_low = assign_document_narrative(
        "School summer vacation circular",
        doc_embedding=unrelated_emb,
        narratives_data=fake_clusters,
        indicator_graph=fake_graph,
        threshold=0.83,
    )
    assert res_low.assigned is False


def test_simulate_unseen_forgery_excludes_own_record():
    """6. When simulate_unseen is active, the document's own record is excluded from narrative stats and indicator links."""
    c_centroid = [1.0] + [0.0] * 383
    fake_clusters = {
        "clusters": [
            {
                "id": "cluster_001",
                "name": "PM Mudra Scheme",
                "size": 5,
                "first_date": "2023-01-01",
                "last_date": "2025-01-01",
                "centroid": c_centroid,
                "member_doc_ids": ["SAMPLE_001", "OTHER_1", "OTHER_2", "OTHER_3", "OTHER_4"],
            }
        ]
    }
    fake_graph = {
        "nodes": [
            {"id": "SAMPLE_001", "type": "record", "issuer": "MUDRA", "year": "2023"},
        ],
        "edges": [
            {"source": "SAMPLE_001", "target": "phone:9111222333", "kind": "contains"},
        ],
        "template_reuse": [],
    }

    # When exclude_doc_id="SAMPLE_001", size is decremented from 5 to 4
    # and the phone indicator only linking to SAMPLE_001 is omitted
    res = assign_document_narrative(
        "Call 9111222333 for mudra loan",
        doc_embedding=c_centroid,
        narratives_data=fake_clusters,
        indicator_graph=fake_graph,
        threshold=0.80,
        exclude_doc_id="SAMPLE_001",
    )
    assert res.assigned is True
    assert res.debunks_count == 4  # decremented
    assert len(res.shared_indicators) == 0  # own record excluded, no remaining links


def test_api_narratives_endpoints():
    """7. GET /api/narratives returns sorted cluster list; GET /api/narratives/{id} returns details."""
    client = TestClient(app)

    # 1. List narratives
    resp = client.get("/api/narratives")
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert data["count"] > 0
    items = data["items"]
    assert len(items) > 0
    first = items[0]
    assert "id" in first
    assert "name" in first
    assert "size" in first
    assert "claimed_issuers" in first
    assert "monthly_debunks" in first

    # 2. Sort by recent
    resp_recent = client.get("/api/narratives?sort=recent")
    assert resp_recent.status_code == 200
    items_recent = resp_recent.json()["items"]
    assert len(items_recent) == len(items)

    # 3. Get detail
    cluster_id = first["id"]
    resp_detail = client.get(f"/api/narratives/{cluster_id}")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["id"] == cluster_id
    assert "exemplars" in detail
    assert "shared_indicators" in detail

    # 4. 404 on nonexistent cluster
    resp_404 = client.get("/api/narratives/cluster_nonexistent_999")
    assert resp_404.status_code == 404


def test_multipart_tlds_and_brand_domains():
    """8. Domain extractor does not truncate multi-part TLDs (.org.in, .co.in) and recognizes brand TLDs (.sbi)."""
    assert extract_registered_domain("rbi.org.in") == "rbi.org.in"
    assert extract_registered_domain("sbi.co.in") == "sbi.co.in"
    assert extract_registered_domain("mudra.org.in") == "mudra.org.in"
    assert extract_registered_domain("https://www.onlinesbi.sbi") == "onlinesbi.sbi"
    assert extract_registered_domain("sub.cybercelldelhi.in") == "cybercelldelhi.in"

    # From raw text extraction (without exclusions)
    inds_raw = extract_indicators_from_text(
        "Check fraud.org.in and scam.co.in or https://fake-site.sbi",
        excluded_domains=set(),
    )
    assert "fraud.org.in" in inds_raw["domain"]
    assert "scam.co.in" in inds_raw["domain"]
    assert "fake-site.sbi" in inds_raw["domain"]

    # Official guidance clause filtering ("visit rbi.org.in for details")
    inds_guidance = extract_indicators_from_text("visit rbi.org.in for details")
    assert "rbi.org.in" not in inds_guidance["domain"]

    # Official registry domains excluded by default
    inds_off = extract_indicators_from_text("rbi.org.in sbi.co.in mudra.org.in onlinesbi.sbi")
    assert len(inds_off["domain"]) == 0
