"""Build the held-out test set shown during testing: data/testset/{real,fake,synthetic}/ + manifest.json.

    python scripts/build_testset.py

- fake/      Real-world fakes from data/heldout/fake. These were collected as PIB fact-check graphics,
             so each carries PIB's answer (a red "FAKE" stamp, a "This letter is FAKE" caption,
             #PIBFactCheck banners). We crop to the forwarded letter and inpaint the red stamp, so the
             pipeline sees roughly what circulated on WhatsApp. Originals are kept in fake/original/.
- real/      Genuine circulars from data/heldout/real (page 1 rendered to PNG; the PDF is kept).
- synthetic/ A balanced subset of 06_synthetic_forgeries (fictional issuers, watermarked), excluding
             the images already used in the demo set.

Nothing here is used to build the retrieval index or tune thresholds. Where the same document or
incident IS in the reference data (an RBI circular in the official index, or a PIB debunk of the same
fake in the archive), the manifest says so, and scripts/eval_testset.py reports results with and
without the debunk archive.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factcheck.extract.ocr import render_pdf_first_page_to_png

HELDOUT = REPO_ROOT / "data" / "heldout"
SYN_DIR = REPO_ROOT / "data" / "dataset" / "06_synthetic_forgeries"
DEMO_SET = REPO_ROOT / "data" / "demo" / "demo_set.json"
OUT = REPO_ROOT / "data" / "testset"

# Crop box (x0, y0, x1, y1) as fractions of the image: the forwarded letter only, without PIB's
# headline, caption, logo or footer. Chosen by hand from the originals.
FAKE_SPECS: list[dict] = [
    {"src": "1781149504055-re-neet-2026-fake-notice-claims-versus-the-pib-fact-check-co.jpg",
     "crop": (0.27, 0.17, 0.70, 0.86), "title": "NTA: NEET (UG) 2026 re-examination circular", "issuer": "NTA",
     "lang": "en"},
    {"src": "202610013962123.webp", "crop": (0.16, 0.16, 0.80, 0.95),
     "title": "Gazette: all Saturdays public holiday for public sector banks", "issuer": "MOF", "lang": "hi/en"},
    {"src": "69084cde-1e9b-4c5d-bf01-17cde18bf3f3.png", "crop": (0.08, 0.02, 0.64, 0.92),
     "title": "Intelligence Bureau / I4C cyber-crime summons letter", "issuer": "IB", "lang": "en"},
    {"src": "FUowzR3aIAEPnYD.jpg", "crop": (0.43, 0.27, 0.98, 0.90),
     "title": "SMS: Rs 2,67,000 credited under government yojana, click link", "issuer": "UNSPECIFIED", "lang": "en"},
    {"src": "Fake43-ezgif.com-jpg-to-webp-converter-2.webp", "crop": (0.17, 0.19, 0.83, 0.96),
     "title": "MeitY notice banning use of recruitment names and logos", "issuer": "MEITY", "lang": "en"},
    {"src": "PIB-FACT-CHECK.webp", "crop": (0.30, 0.13, 0.70, 0.98),
     "title": "TRAI permission letter for mobile tower installation (fee demand)", "issuer": "TRAI", "lang": "en"},
    {"src": "Screenshot-2024-03-14-131202.png", "crop": (0.04, 0.37, 0.94, 0.885),
     "title": "Gazette: appointment of two Election Commissioners", "issuer": "MOLJ", "lang": "hi/en"},
    {"src": "Untitleddesign15-ezgif.com-png-to-webp-converter-2.webp", "crop": (0.54, 0.18, 0.99, 0.82),
     "title": "BSNL / TRAI notice: SIM card blocked within 24 hours", "issuer": "BSNL", "lang": "en"},
    {"src": "fake1.jpg", "crop": (0.33, 0.16, 0.70, 1.0),
     "title": "RBI foreign-exchange transfer approval notification", "issuer": "RBI", "lang": "en"},
    {"src": "phone_sideways.jpg.jpeg", "crop": (0.38, 0.25, 0.62, 0.70),
     "title": "NTA NEET re-exam circular (phone photo of a screen)", "issuer": "NTA", "lang": "en",
     "variant_of": "TF-01"},
    {"src": "phone_tilted.jpg.jpeg", "crop": (0.29, 0.52, 0.75, 0.765),
     "title": "Election Commissioners gazette (phone photo of a screen)", "issuer": "MOLJ", "lang": "hi/en",
     "variant_of": "TF-07"},
]
EXCLUDED_FAKES = {
    "fa445b7a-69d6-4ded-97a3-65005e20ca56.png": "PIB tweet text only; no copy of the fake document",
}
SYNTHETIC_PER_LABEL = 6


def _read(path: Path) -> np.ndarray:
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:  # e.g. .webp without codec support: fall back to Pillow
        from PIL import Image

        with Image.open(path) as im:
            img = cv2.cvtColor(np.asarray(im.convert("RGB")), cv2.COLOR_RGB2BGR)
    return img


def remove_red_stamp(img: np.ndarray) -> tuple[np.ndarray, float]:
    """Inpaint saturated red ink (PIB 'FAKE' stamps). Returns (image, fraction of pixels removed)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    red = (((h < 10) | (h > 165)) & (s > 90) & (v > 70)).astype(np.uint8) * 255
    red = cv2.dilate(red, np.ones((3, 3), np.uint8), iterations=2)
    return cv2.inpaint(img, red, 5, cv2.INPAINT_TELEA), float((red > 0).mean())


def build_fakes(manifest: list[dict]) -> None:
    out_dir = OUT / "fake"
    (out_dir / "original").mkdir(parents=True, exist_ok=True)
    for i, spec in enumerate(FAKE_SPECS, 1):
        src = HELDOUT / "fake" / spec["src"]
        img = _read(src)
        H, W = img.shape[:2]
        x0, y0, x1, y1 = spec["crop"]
        crop = img[int(y0 * H) : int(y1 * H), int(x0 * W) : int(x1 * W)]
        cleaned, removed = remove_red_stamp(crop)
        if max(cleaned.shape[:2]) < 1000:  # small social-media crops: upscale for OCR
            f = 1000 / max(cleaned.shape[:2])
            cleaned = cv2.resize(cleaned, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
        tid = f"TF-{i:02d}"
        ok, buf = cv2.imencode(".png", cleaned)
        assert ok
        (out_dir / f"{tid}.png").write_bytes(buf.tobytes())
        orig_name = f"{tid}_original{src.suffix.lower()}"
        shutil.copyfile(src, out_dir / "original" / orig_name)
        manifest.append(
            {
                "id": tid,
                "label": "fake",
                "file": f"fake/{tid}.png",
                "original": f"fake/original/{orig_name}",
                "source": f"data/heldout/fake/{spec['src']}",
                "title": spec["title"],
                "claimed_issuer_id": spec["issuer"],
                "language": spec["lang"],
                "variant_of": spec.get("variant_of"),
                "cleaning": f"cropped to the letter; red stamp inpainted ({removed:.1%} of pixels)",
            }
        )


def build_real(manifest: list[dict]) -> None:
    out_dir = OUT / "real"
    out_dir.mkdir(parents=True, exist_ok=True)
    held = {m["file"]: m for m in json.loads((HELDOUT / "manifest.json").read_text(encoding="utf-8"))}
    for i, pdf in enumerate(sorted((HELDOUT / "real").glob("*.pdf")), 1):
        tid = f"TR-{i:02d}"
        shutil.copyfile(pdf, out_dir / f"{tid}.pdf")
        render_pdf_first_page_to_png(out_dir / f"{tid}.pdf", dpi=200, output_path=out_dir / f"{tid}.png")
        info = held.get(f"real/{pdf.name}", {})
        manifest.append(
            {
                "id": tid,
                "label": "real",
                "file": f"real/{tid}.png",
                "original": f"real/{tid}.pdf",
                "source": f"data/heldout/real/{pdf.name}",
                "title": None,
                "in_official_index": bool(info.get("in_index")),
                "index_note": info.get("reason"),
            }
        )


def build_synthetic(manifest: list[dict]) -> None:
    out_dir = OUT / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    demo_ids = {it.get("id") for it in json.loads(DEMO_SET.read_text(encoding="utf-8")).get("items", [])}
    labels = [json.loads(l) for l in (SYN_DIR / "labels.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for want in ("forged", "clean"):
        picked = [r for r in labels if r["label"] == want and r["synthetic_id"] not in demo_ids][:SYNTHETIC_PER_LABEL]
        for r in picked:
            src = SYN_DIR / r["file"]
            shutil.copyfile(src, out_dir / f"{r['synthetic_id']}.png")
            manifest.append(
                {
                    "id": r["synthetic_id"],
                    "label": "synthetic_forged" if want == "forged" else "synthetic_clean",
                    "file": f"synthetic/{r['synthetic_id']}.png",
                    "source": f"data/dataset/06_synthetic_forgeries/{r['file']}",
                    "title": r.get("subject"),
                    "claimed_issuer_id": r.get("issuer_id"),
                    "cues": r.get("cues", []),
                    "note": "Fictional issuer, watermarked. Forensic rules were tuned on this dataset (in-sample).",
                }
            )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    manifest: list[dict] = []
    build_real(manifest)
    build_fakes(manifest)
    build_synthetic(manifest)
    payload = {
        "description": "Held-out test set: real circulars, real-world fakes with PIB stamps/captions removed, "
        "and synthetic forgeries. Not used to build the index or tune thresholds.",
        "excluded": EXCLUDED_FAKES,
        "items": manifest,
    }
    (OUT / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    counts: dict[str, int] = {}
    for m in manifest:
        counts[m["label"]] = counts.get(m["label"], 0) + 1
    print(f"Wrote {len(manifest)} items to {OUT}: {counts}")


if __name__ == "__main__":
    main()
