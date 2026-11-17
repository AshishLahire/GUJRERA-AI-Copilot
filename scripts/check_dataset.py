"""Verify every file and image path in ``data/processed/`` and ``data/demo/`` exists.

Exits with code 1 if any required file or referenced image/document path is missing.
"""

from __future__ import annotations

import json
import sys
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
DEMO_DIR = PROJECT_ROOT / "data" / "demo"


def check_all() -> int:
    errors: list[str] = []

    required_files = [
        PROCESSED_DIR / "fake_notices.jsonl",
        PROCESSED_DIR / "excluded_images.txt",
        PROCESSED_DIR / "official_docs.jsonl",
        PROCESSED_DIR / "whatsapp_variants.jsonl",
        DEMO_DIR / "demo_set.json",
    ]
    for req in required_files:
        if not req.exists():
            errors.append(f"Missing required file: {req}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    # Verify processed datasets via loaders
    fake_notices = load_fake_notices(prefer_processed=True)
    for n in fake_notices:
        if not n.image.is_absolute() or not n.image.exists():
            errors.append(f"Missing fake notice image for {n.notice_id}: {n.image}")

    official_docs = load_official_docs(prefer_processed=True)
    for d in official_docs:
        if d.local_file is not None and (
            not d.local_file.is_absolute() or not d.local_file.exists()
        ):
            errors.append(f"Missing official local_file for {d.doc_id}: {d.local_file}")

    issuer_reg = load_issuer_registry()
    claims_bundle = load_multilingual_claims()

    wa_variants = load_whatsapp_variants(prefer_processed=True)
    for v in wa_variants:
        if not v.file.is_absolute() or not v.file.exists():
            errors.append(f"Missing WhatsApp variant file for {v.variant_id}: {v.file}")

    synthetics = load_synthetic_forgeries()
    for s in synthetics:
        if not s.file.is_absolute() or not s.file.exists():
            errors.append(f"Missing synthetic forgery image for {s.synthetic_id}: {s.file}")

    # Verify excluded_images.txt
    excluded = [
        line.strip()
        for line in (PROCESSED_DIR / "excluded_images.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    referenced_names = {n.image.name for n in fake_notices}
    overlap = referenced_names.intersection(excluded)
    if overlap:
        errors.append(f"Excluded images found in processed fake_notices.jsonl: {sorted(overlap)}")

    # Verify demo_set.json
    demo_payload = json.loads((DEMO_DIR / "demo_set.json").read_text(encoding="utf-8"))
    demo_items = (
        demo_payload["items"] if isinstance(demo_payload, dict) else demo_payload
    )
    for item in demo_items:
        img_path = (PROJECT_ROOT / item["image"]).resolve()
        if not img_path.exists():
            errors.append(f"Missing demo image for {item['id']}: {img_path}")

    print("=== Dataset & Demo Verification Counts ===")
    print(f"Processed fake_notices.jsonl     : {len(fake_notices)} records (all images exist)")
    print(f"Excluded benchmark images        : {len(excluded)} filenames (0 overlap)")
    print(
        f"Processed official_docs.jsonl    : {len(official_docs)} records "
        f"({sum(1 for d in official_docs if d.local_file)} PDFs verified)"
    )
    print(
        f"Issuer registry                  : {len(issuer_reg.issuers)} issuers, "
        f"{len(issuer_reg.ref_format_checks)} ref checks"
    )
    print(
        f"Multilingual claims              : {len(claims_bundle.claims)} claims, "
        f"{len(claims_bundle.narratives)} narratives, "
        f"{len(claims_bundle.eval_pairs)} eval pairs"
    )
    print(f"Processed whatsapp_variants.jsonl: {len(wa_variants)} records (all images exist)")
    print(f"Synthetic forgeries              : {len(synthetics)} records (all images exist)")
    print(f"Demo set (demo_set.json)         : {len(demo_items)} items (all copied images exist)")

    if errors:
        print(f"\nFAILED with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("\nALL CHECKS PASSED.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(check_all())
