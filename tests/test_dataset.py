"""Tests for dataset loaders and processed dataset exclusions."""

from __future__ import annotations

import json
from pathlib import Path

from factcheck.data.loaders import (
    load_fake_notices,
    load_issuer_registry,
    load_multilingual_claims,
    load_official_docs,
    load_synthetic_forgeries,
    load_whatsapp_variants,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def test_loaders_expected_counts_and_existing_paths():
    fake_notices = load_fake_notices()
    official_docs = load_official_docs()
    issuer_registry = load_issuer_registry()
    claims_bundle = load_multilingual_claims()
    wa_variants = load_whatsapp_variants()
    synthetics = load_synthetic_forgeries()

    assert len(fake_notices) == 90
    assert len(synthetics) == 60
    assert len(wa_variants) == 150
    assert len(official_docs) == 79
    assert len(issuer_registry.issuers) == 35
    assert len(claims_bundle.claims) == 120

    for n in fake_notices:
        assert n.image.is_absolute()
        assert n.image.exists()

    for s in synthetics:
        assert s.file.is_absolute()
        assert s.file.exists()

    for v in wa_variants:
        assert v.file.is_absolute()
        assert v.file.exists()


def test_no_excluded_image_in_processed_fake_notices():
    excluded_path = PROCESSED_DIR / "excluded_images.txt"
    proc_notices_path = PROCESSED_DIR / "fake_notices.jsonl"

    assert excluded_path.exists(), "Run scripts/prepare_dataset.py first"
    assert proc_notices_path.exists(), "Run scripts/prepare_dataset.py first"

    excluded = {
        line.strip()
        for line in excluded_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert len(excluded) == 113

    rows = [
        json.loads(line)
        for line in proc_notices_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 90

    referenced_filenames = {Path(r["image"]).name for r in rows}
    assert referenced_filenames.isdisjoint(excluded)
