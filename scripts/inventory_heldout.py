"""Inventory held-out documents without running OCR."""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
HELDOUT_DIR = REPO_ROOT / "data" / "heldout"


def inspect_heldout() -> list[dict]:
    items = []
    if not HELDOUT_DIR.exists():
        print(f"Error: {HELDOUT_DIR} does not exist.")
        return items

    for folder in ["real", "fake"]:
        dir_p = HELDOUT_DIR / folder
        if not dir_p.exists():
            continue
        for p in sorted(dir_p.iterdir()):
            if p.is_dir():
                continue
            size_kb = round(p.stat().st_size / 1024, 1)
            ext = p.suffix.lower()
            pages = 1
            status = "readable"
            note = ""

            if ext == ".pdf":
                try:
                    reader = pypdf.PdfReader(str(p))
                    pages = len(reader.pages)
                except Exception as e:
                    status = "unreadable"
                    note = f"PDF read error: {e}"
            else:
                try:
                    with Image.open(p) as im:
                        im.verify()
                        # check format
                        note = f"{im.format} {im.size[0]}x{im.size[1]}"
                except Exception as e:
                    status = "unreadable"
                    note = f"Image decode error: {e}"

            if ".jpg_large" in p.name or ext not in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
                status = "unreadable / abnormal extension"
                note = f"Abnormal extension '{p.suffix}'"

            items.append({
                "group": folder,
                "filename": p.name,
                "ext": ext,
                "size_kb": size_kb,
                "pages": pages,
                "status": status,
                "note": note,
            })
    return items


if __name__ == "__main__":
    inventory = inspect_heldout()
    print(f"\n=== Held-Out Documents Inventory ({len(inventory)} files) ===")
    print(f"{'Group':<6} | {'Filename':<32} | {'Ext':<10} | {'Size':<10} | {'Pages':<6} | {'Status'}")
    print("-" * 90)
    for it in inventory:
        sz_str = f"{it['size_kb']} KB"
        print(f"{it['group']:<6} | {it['filename']:<32} | {it['ext']:<10} | {sz_str:<10} | {it['pages']:<6} | {it['status']} ({it['note']})")
