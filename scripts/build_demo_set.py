"""Build the curated demo set in ``data/demo/`` with ``demo_set.json`` and copied images.

Selection rules:
- Up to 10 fake notices from ``fake_notices.jsonl``:
  1. All 4 fake notices with a non-null ``reference_seen`` (note:
     "format-valid reference on a fake: needs registry lookup").
  2. Best candidate from each required narrative:
     ``NAR-I4C-LETTER``, ``NAR-MUDRA-LOAN``, ``NAR-JOB-FEE``, ``NAR-OMC-DEALERSHIP``
     (preferring Hindi items, then largest pixel area).
  3. Additional top-ranked Hindi / large-resolution fake notices up to 10 total.
  All fake notices are marked ``needs_manual_crop: true``.
- 4 genuine documents from ``05_whatsapp_variants`` (one each of
  ``wa_compress``, ``rephoto``, ``screenshot``, ``crop``).
- 4 synthetic images from ``06_synthetic_forgeries`` (2 clean, 2 forged with
  the most labelled cues).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image

from factcheck.data.loaders import (
    FakeNotice,
    load_fake_notices,
    load_official_docs,
    load_synthetic_forgeries,
    load_whatsapp_variants,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = PROJECT_ROOT / "data" / "demo"
DEMO_IMAGES_DIR = DEMO_DIR / "images"

REQUIRED_NARRATIVES = [
    "NAR-I4C-LETTER",
    "NAR-MUDRA-LOAN",
    "NAR-JOB-FEE",
    "NAR-OMC-DEALERSHIP",
]

NARRATIVE_DEMO_NOTES: dict[str, str] = {
    "NAR-I4C-LETTER": "Digital-arrest / cyber-crime intimidation letter impersonating I4C",
    "NAR-MUDRA-LOAN": "PM Mudra Yojana loan-approval scam demanding an upfront fee",
    "NAR-JOB-FEE": "Fake government recruitment / appointment letter demanding a fee",
    "NAR-OMC-DEALERSHIP": "Fraudulent LPG / fuel dealership approval letter requesting deposit",
}


def _image_area(path: Path) -> int:
    try:
        with Image.open(path) as im:
            w, h = im.size
            return w * h
    except Exception:
        return 0


def _fake_rank_key(notice: FakeNotice) -> tuple[int, int, str]:
    is_hi = 1 if notice.language == "hi" else 0
    area = _image_area(notice.image)
    return (is_hi, area, notice.notice_id)


def build_demo_set(max_fakes: int = 10) -> list[dict[str, Any]]:
    DEMO_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    notices = load_fake_notices(prefer_processed=True)
    official_docs = {d.doc_id: d for d in load_official_docs(prefer_processed=True)}
    variants = load_whatsapp_variants(prefer_processed=True)
    synthetics = load_synthetic_forgeries()

    selected_fakes: list[tuple[FakeNotice, str]] = []
    seen_ids: set[str] = set()

    # 1a. All 4 fake notices with non-null reference_seen
    for n in notices:
        if n.reference_seen:
            selected_fakes.append(
                (n, "format-valid reference on a fake: needs registry lookup")
            )
            seen_ids.add(n.notice_id)

    # 1b. At least one from each required narrative (preferring Hindi + larger image)
    covered_narratives = {n.narrative_id for n, _ in selected_fakes}
    for nar_id in REQUIRED_NARRATIVES:
        if nar_id in covered_narratives:
            continue
        candidates = [
            n
            for n in notices
            if n.narrative_id == nar_id and n.notice_id not in seen_ids
        ]
        if candidates:
            best = max(candidates, key=_fake_rank_key)
            note = NARRATIVE_DEMO_NOTES.get(
                nar_id, f"Fake notice illustrating narrative {nar_id}"
            )
            if best.language == "hi":
                note = f"Hindi {note[0].lower() + note[1:]}"
            selected_fakes.append((best, note))
            seen_ids.add(best.notice_id)
            covered_narratives.add(nar_id)

    # 1c. Fill remaining slots up to max_fakes (preferring Hindi + larger images)
    remaining = sorted(
        [n for n in notices if n.notice_id not in seen_ids],
        key=_fake_rank_key,
        reverse=True,
    )
    for n in remaining:
        if len(selected_fakes) >= max_fakes:
            break
        base_note = NARRATIVE_DEMO_NOTES.get(
            n.narrative_id,
            f"Fake {n.doc_type} impersonating {n.claimed_issuer or n.claimed_issuer_id} ({n.narrative_id})",
        )
        if n.language == "hi" and not base_note.lower().startswith("hindi"):
            base_note = f"Hindi {base_note[0].lower() + base_note[1:]}"
        selected_fakes.append((n, base_note))
        seen_ids.add(n.notice_id)

    manifest_entries: list[dict[str, Any]] = []

    for n, note in selected_fakes:
        dest_name = f"{n.notice_id}{n.image.suffix}"
        dest_path = DEMO_IMAGES_DIR / dest_name
        shutil.copy2(n.image, dest_path)
        manifest_entries.append(
            {
                "id": n.notice_id,
                "source_dataset": "01_fake_notice_benchmark",
                "label": n.verdict,
                "language": n.language,
                "narrative": n.narrative_id,
                "expected_issuer": n.claimed_issuer or n.claimed_issuer_id,
                "expected_issuer_id": n.claimed_issuer_id,
                "expected_reference_no": n.reference_seen,
                "needs_manual_crop": True,
                "image": f"data/demo/images/{dest_name}",
                "note": note,
            }
        )

    # 2. 4 genuine documents from 05_whatsapp_variants (wa_compress, rephoto, screenshot, crop)
    transform_notes = {
        "wa_compress": "Genuine CBSE circular after multi-hop WhatsApp JPEG compression",
        "rephoto": "Genuine CBSE circular photographed at an angle (perspective + lighting)",
        "screenshot": "Genuine CBSE circular framed inside a mobile chat screenshot",
        "crop": "Genuine CBSE circular body-zoomed crop testing partial layout extraction",
    }
    used_sources: set[str] = set()
    for transform in ["wa_compress", "rephoto", "screenshot", "crop"]:
        candidates = [
            v
            for v in variants
            if v.label == "genuine"
            and v.transform == transform
            and not v.has_factcheck_stamp
            and v.source_id in official_docs
            and official_docs[v.source_id].reference_no
        ]
        # Prefer distinct source documents
        distinct = [v for v in candidates if v.source_id not in used_sources]
        chosen = (distinct or candidates)[0]
        used_sources.add(chosen.source_id)
        src_doc = official_docs.get(chosen.source_id)
        dest_name = f"{chosen.variant_id}{chosen.file.suffix}"
        dest_path = DEMO_IMAGES_DIR / dest_name
        shutil.copy2(chosen.file, dest_path)
        manifest_entries.append(
            {
                "id": chosen.variant_id,
                "source_dataset": "05_whatsapp_variants",
                "label": "genuine",
                "language": src_doc.language if src_doc else "en",
                "narrative": None,
                "expected_issuer": src_doc.issuer if src_doc else chosen.issuer_id,
                "expected_issuer_id": chosen.issuer_id,
                "expected_reference_no": src_doc.reference_no if src_doc else None,
                "needs_manual_crop": False,
                "image": f"data/demo/images/{dest_name}",
                "note": transform_notes[transform],
            }
        )

    # 3. 4 synthetic images: 2 clean, 2 forged with the most labelled cues
    clean_syns = [s for s in synthetics if s.label == "clean"][:2]
    forged_syns = sorted(
        [s for s in synthetics if s.label == "forged"],
        key=lambda s: (-len(s.cues), s.synthetic_id),
    )[:2]

    for s in clean_syns:
        dest_name = f"{s.synthetic_id}{s.file.suffix}"
        dest_path = DEMO_IMAGES_DIR / dest_name
        shutil.copy2(s.file, dest_path)
        manifest_entries.append(
            {
                "id": s.synthetic_id,
                "source_dataset": "06_synthetic_forgeries",
                "label": "clean",
                "language": s.language,
                "narrative": None,
                "expected_issuer": s.issuer_name,
                "expected_issuer_id": s.issuer_id,
                "expected_reference_no": s.reference_no,
                "needs_manual_crop": False,
                "image": f"data/demo/images/{dest_name}",
                "note": f"Clean synthetic control from {s.issuer_id} (house-style compliant, 0 cues)",
            }
        )

    for s in forged_syns:
        dest_name = f"{s.synthetic_id}{s.file.suffix}"
        dest_path = DEMO_IMAGES_DIR / dest_name
        shutil.copy2(s.file, dest_path)
        cues_str = ", ".join(s.cues)
        manifest_entries.append(
            {
                "id": s.synthetic_id,
                "source_dataset": "06_synthetic_forgeries",
                "label": "forged",
                "language": s.language,
                "narrative": None,
                "expected_issuer": s.issuer_name,
                "expected_issuer_id": s.issuer_id,
                "expected_reference_no": s.reference_no,
                "needs_manual_crop": False,
                "image": f"data/demo/images/{dest_name}",
                "note": f"Synthetic forgery with {len(s.cues)} labelled cues ({cues_str})",
            }
        )

    manifest_path = DEMO_DIR / "demo_set.json"
    manifest_payload = {
        "count": len(manifest_entries),
        "items": manifest_entries,
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"=== Demo Set Built ({len(manifest_entries)} items) ===")
    for item in manifest_entries:
        print(
            f"  {item['id']:28s} | {item['label']:7s} | lang={item['language']:2s} | "
            f"nar={str(item['narrative'] or '-'):25s} | ref={str(item['expected_reference_no'] or '-'):22s} | {item['note']}"
        )
    return manifest_entries


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build_demo_set()
