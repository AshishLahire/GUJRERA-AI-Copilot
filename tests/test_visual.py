"""Stage 2c visual document check: synthetic pages with a stamp, a signature and an emblem."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from factcheck.api.app import app
from factcheck.forensics.visual import run_visual_forensics


def _page(tmp_path: Path, *, seal: bool, signature: bool, name: str = "page.png") -> Path:
    img = np.full((1400, 1000, 3), 255, np.uint8)
    for row in range(300, 1100, 28):  # printed text lines
        for col in range(80, 900, 14):
            cv2.rectangle(img, (col, row), (col + 8, row + 12), (20, 20, 20), -1)
    cv2.circle(img, (120, 110), 55, (30, 30, 30), -1)  # letterhead emblem (solid, top-left)
    cv2.circle(img, (120, 110), 30, (255, 255, 255), -1)
    if seal:
        cv2.circle(img, (300, 1230), 70, (200, 60, 40), 5)  # blue ring stamp (BGR)
        cv2.circle(img, (300, 1230), 50, (200, 60, 40), 3)
    if signature:
        xs = np.linspace(650, 860, 120)
        pts = np.stack([xs, 1180 + 22 * np.sin((xs - 650) / 14)], axis=1).astype(np.int32)
        cv2.polylines(img, [pts], False, (90, 40, 10), 2)
    path = tmp_path / name
    Image.fromarray(img[:, :, ::-1]).save(path)
    return path


def test_detects_seal_signature_and_emblem(tmp_path: Path) -> None:
    res = run_visual_forensics(_page(tmp_path, seal=True, signature=True))
    assert res.analysed
    assert res.has_seal and res.has_signature and res.has_emblem
    assert all(f.points == 0 for f in res.findings)  # never changes the calibrated risk score
    for r in res.regions:
        assert len(r.box) == 4 and all(0.0 <= v <= 1.0 for v in r.box)


def test_reports_missing_seal_and_signature(tmp_path: Path) -> None:
    res = run_visual_forensics(_page(tmp_path, seal=False, signature=False))
    assert not res.has_seal and not res.has_signature
    assert any(f.cue_id == "visual_no_seal_signature" for f in res.findings)


def test_flags_editing_software_metadata(tmp_path: Path) -> None:
    src = _page(tmp_path, seal=False, signature=True)
    out = tmp_path / "edited.jpg"
    with Image.open(src) as im:
        exif = im.getexif()
        exif[0x0131] = "Adobe Photoshop 25.0"
        im.convert("RGB").save(out, "JPEG", quality=92, exif=exif)
    res = run_visual_forensics(out)
    assert res.editing_software and "Photoshop" in res.editing_software
    assert any(f.cue_id == "visual_editing_software" for f in res.findings)


def test_missing_or_bad_file_never_raises(tmp_path: Path) -> None:
    assert run_visual_forensics(None).analysed is False
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not an image")
    assert run_visual_forensics(bad).analysed is False


def test_sample_endpoint_includes_visual_block() -> None:
    data = TestClient(app).post("/api/ocr/sample/FN-TG-01999?allow_fallback=false").json()
    assert data["visual"]["analysed"] is True
    assert "regions" in data["visual"]
    assert data["matches"]["ground_truth"]["status"] in ("skipped", "debunked", "official", "no_record")
