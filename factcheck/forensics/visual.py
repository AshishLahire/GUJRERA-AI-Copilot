"""Stage 2c visual document check: seal / stamp, signature area, letterhead emblem, edit traces.

Text rules (Stage 2b) cannot see the parts of an "official" letter that forgers copy or paste:
the seal, the signature block and the letterhead emblem. This module looks at the image itself
with classical OpenCV (no model download, ~100 ms per page) and reports:

- where a coloured ink seal / rubber stamp, a handwritten signature and a letterhead emblem were
  found (normalised boxes the UI draws on the document);
- editing-software metadata (EXIF "Software": Photoshop, Canva, PicsArt, ...);
- for JPEGs, error-level analysis (ELA): a region recompressing very differently from the rest of
  the page is a classic sign of a pasted seal, signature or edited figure.

These are observations for a human reviewer, not proof: WhatsApp recompression, phone photos and
PIB fact-check "FAKE" stamps all leave visual traces. Findings therefore carry 0 risk points and
rule_status="unverified", so the calibrated text risk score and its evaluations are unchanged.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from factcheck.schemas import ForensicFinding, VisualForensicResult, VisualRegion

MAX_SIDE = 1400  # analysis resolution (long edge)
EDITING_SOFTWARE = (
    "photoshop", "gimp", "canva", "picsart", "snapseed", "pixlr", "illustrator", "coreldraw",
    "paint.net", "affinity", "lightroom", "inshot", "polarr", "photopea", "meitu",
)


def _load(path: Path) -> np.ndarray | None:
    if path.suffix.lower() == ".pdf":
        try:
            import pypdfium2 as pdfium
            doc = pdfium.PdfDocument(str(path))
            if len(doc) > 0:
                bitmap = doc[0].render(scale=200 / 72)
                pil_image = bitmap.to_pil()
                img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                h, w = img.shape[:2]
                scale = MAX_SIDE / max(h, w)
                if scale < 1.0:
                    img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                return img
        except Exception:
            pass
    data = np.fromfile(str(path), dtype=np.uint8)  # handles non-ASCII Windows paths
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def _box(x: int, y: int, w: int, h: int, W: int, H: int) -> list[float]:
    return [round(x / W, 4), round(y / H, 4), round(w / W, 4), round(h / H, 4)]


def _vertical(y: int, h: int, H: int) -> str:
    c = (y + h / 2) / H
    return "top" if c < 0.33 else "middle" if c < 0.66 else "bottom"


def _horizontal(x: int, w: int, W: int) -> str:
    c = (x + w / 2) / W
    return "left" if c < 0.33 else "centre" if c < 0.66 else "right"


def detect_seals(img: np.ndarray) -> list[VisualRegion]:
    """Coloured ink stamps: saturated blue / violet / red / green blobs that are roundish or boxy."""
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat_ink = (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 40) & (hsv[:, :, 2] < 245)
    mask = sat_ink.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)), iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    page_area = H * W
    out: list[VisualRegion] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < 0.004 * page_area or area > 0.25 * page_area:
            continue
        aspect = w / max(h, 1)
        if not 0.4 <= aspect <= 2.5:
            continue
        # A stamp is ink on paper: the box must be partly empty (rings, letters), not a solid photo/banner.
        fill = float(sat_ink[y : y + h, x : x + w].mean())
        if not 0.08 <= fill <= 0.75:
            continue
        perim = cv2.arcLength(c, True) or 1.0
        circularity = 4 * np.pi * cv2.contourArea(c) / (perim * perim)
        hue = float(np.median(hsv[y : y + h, x : x + w, 0][sat_ink[y : y + h, x : x + w]]))
        colour = "red" if hue < 10 or hue > 160 else "blue/violet" if 95 <= hue <= 160 else "green" if 35 <= hue < 95 else "orange"
        shape = "round" if circularity > 0.55 else "rectangular"
        conf = min(0.95, 0.4 + 0.4 * min(circularity, 1.0) + 0.2 * (1 - abs(fill - 0.3)))
        out.append(
            VisualRegion(
                kind="seal",
                box=_box(x, y, w, h, W, H),
                confidence=round(conf, 2),
                note=f"{shape} {colour} ink stamp, {_vertical(y, h, H)}-{_horizontal(x, w, W)}",
            )
        )
    out.sort(key=lambda r: -r.confidence)
    return out[:3]


def _ink_mask(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)


def detect_signature(img: np.ndarray) -> VisualRegion | None:
    """Handwritten signature: a loose, curvy ink cluster in the lower 40% of the page.

    Only reported when region is in the lower 40% of the page (y >= 0.60 * H), not inside
    a dense text block, and passes confidence threshold >= 0.60.
    """
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ink = _ink_mask(gray)
    y0, y1 = int(H * 0.60), int(H * 0.95)
    region = ink[y0:y1, :]
    n0, _, stats0, _ = cv2.connectedComponentsWithStats(region, connectivity=8)
    heights = stats0[1:, cv2.CC_STAT_HEIGHT] if n0 > 1 else np.array([10])
    text_h = float(np.median(heights[heights > 3])) if np.any(heights > 3) else 10.0
    k = max(3, int(text_h * 0.35)) | 1
    joined = cv2.morphologyEx(region, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    best: tuple[float, tuple[int, int, int, int]] | None = None
    for i in range(1, n):
        x, y, w, h, _ = stats[i]
        abs_y = y + y0
        if abs_y < 0.60 * H or abs_y + h > 0.95 * H:
            continue
        if h < 1.6 * text_h or h > 4.5 * text_h or w < 2.5 * text_h or w > 0.35 * W:
            continue
        aspect = w / max(h, 1)
        if not 1.2 <= aspect <= 5.5:
            continue
        ink_box = region[y : y + h, x : x + w] > 0
        density = float(ink_box.mean())
        if not 0.04 <= density <= 0.22:
            continue

        # Check if inside a dense text block (text lines immediately above and below)
        line_h = int(text_h * 1.5)
        y_top = max(0, y - line_h)
        y_bot = min(region.shape[0], y + h + line_h)
        above_ink = float((region[y_top:y, x : x + w] > 0).mean()) if y > y_top else 0.0
        below_ink = float((region[y + h : y_bot, x : x + w] > 0).mean()) if y_bot > y + h else 0.0
        if above_ink > 0.035 and below_ink > 0.035:
            continue

        # Check horizontal text continuity across the page
        x_left = max(0, x - int(w * 0.5))
        x_right = min(W, x + int(w * 1.5))
        left_ink = float((region[y : y + h, x_left:x] > 0).mean()) if x > x_left else 0.0
        right_ink = float((region[y : y + h, x + w : x_right] > 0).mean()) if x_right > x + w else 0.0
        if left_ink > 0.045 and right_ink > 0.045:
            continue

        # Stroke continuity: a signature is few long strokes, text is many small glyphs.
        m, _, s2, _ = cv2.connectedComponentsWithStats(ink_box.astype(np.uint8), connectivity=8)
        big = int(np.sum(s2[1:, cv2.CC_STAT_AREA] > 0.15 * ink_box.sum())) if m > 1 else 0
        glyphs = m - 1
        if glyphs > 8 or big == 0:
            continue
        score = (1 - density) * (1 + big) / (1 + glyphs / 4)
        if best is None or score > best[0]:
            best = (score, (x, abs_y, w, h))
    if best is None:
        return None
    conf = round(min(0.85, 0.3 + 0.25 * best[0]), 2)
    if conf < 0.60:
        return None
    x, y, w, h = best[1]
    return VisualRegion(
        kind="signature",
        box=_box(x, y, w, h, W, H),
        confidence=conf,
        note=f"handwritten stroke cluster, {_vertical(y, h, H)}-{_horizontal(x, w, W)}",
    )


def detect_emblem(img: np.ndarray) -> VisualRegion | None:
    """Letterhead emblem / logo: a compact graphic blob in the top 25% that is not a text line."""
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    top = _ink_mask(gray[: int(H * 0.25)])
    top = cv2.morphologyEx(top, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    contours, _ = cv2.findContours(top, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: tuple[float, tuple[int, int, int, int]] | None = None
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 0.05 * W or h < 0.04 * H or w > 0.3 * W:
            continue
        aspect = w / max(h, 1)
        if not 0.5 <= aspect <= 1.8:
            continue  # text lines are wide; emblems are roughly square
        density = float(top[y : y + h, x : x + w].mean()) / 255
        if density < 0.15:
            continue
        score = w * h * density
        if best is None or score > best[0]:
            best = (score, (x, y, w, h))
    if best is None:
        return None
    x, y, w, h = best[1]
    return VisualRegion(
        kind="emblem",
        box=_box(x, y, w, h, W, H),
        confidence=0.6,
        note=f"letterhead graphic, top-{_horizontal(x, w, W)}",
    )


def error_level_regions(path: Path, img_size: tuple[int, int]) -> list[VisualRegion]:
    """JPEG error-level analysis: blocks that recompress far worse than the page around them."""
    if path.suffix.lower() not in (".jpg", ".jpeg"):
        return []
    import io

    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        buf.seek(0)
        resaved = Image.open(buf).convert("RGB")
        diff = np.abs(np.asarray(im, dtype=np.int16) - np.asarray(resaved, dtype=np.int16)).max(axis=2)
    H, W = diff.shape
    bs = 16
    hb, wb = H // bs, W // bs
    if hb < 4 or wb < 4:
        return []
    blocks = diff[: hb * bs, : wb * bs].reshape(hb, bs, wb, bs).mean(axis=(1, 3))
    med = float(np.median(blocks))
    mad = float(np.median(np.abs(blocks - med))) or 0.5
    hot = (blocks > med + 14 * mad) & (blocks > 10.0)
    if hot.mean() > 0.04:  # the whole page is noisy (screenshot of a screenshot): ELA says nothing
        return []
    hot_u8 = cv2.dilate(hot.astype(np.uint8), np.ones((2, 2), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(hot_u8, connectivity=8)
    out: list[VisualRegion] = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 6 or area > 0.02 * hb * wb * 4:
            continue
        out.append(
            VisualRegion(
                kind="edit_trace",
                box=_box(x * bs, y * bs, w * bs, h * bs, W, H),
                confidence=round(min(0.8, 0.3 + area / 100), 2),
                note=f"recompresses unlike the rest of the page, {_vertical(y * bs, h * bs, H)}-{_horizontal(x * bs, w * bs, W)}",
            )
        )
    out.sort(key=lambda r: -r.confidence)
    return out[:3]


def editing_software(path: Path) -> str | None:
    try:
        with Image.open(path) as im:
            sw = str(im.getexif().get(0x0131, "") or "")
    except Exception:
        return None
    low = sw.lower()
    return sw if any(k in low for k in EDITING_SOFTWARE) else None


def _overlap(a: list[float], b: list[float]) -> float:
    """Intersection area over the smaller box."""
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    smaller = min(a[2] * a[3], b[2] * b[3]) or 1e-9
    return ix * iy / smaller


def _finding(cue: str, severity: str, title: str, explanation: str, evidence: str = "") -> ForensicFinding:
    return ForensicFinding(
        cue_id=cue,
        severity=severity,  # type: ignore[arg-type]
        points=0,
        title=title,
        explanation=explanation,
        evidence=evidence,
        rule_status="unverified",
    )


def run_visual_forensics(image_path: Path | str | None) -> VisualForensicResult:
    """Analyse one page image. Never raises: failures come back as `analysed=False`."""
    if not image_path:
        return VisualForensicResult(analysed=False, note="No page image available.")
    path = Path(image_path)
    try:
        img = _load(path)
        if img is None:
            return VisualForensicResult(analysed=False, note="Could not decode the page image.")
        H, W = img.shape[:2]
        seals = detect_seals(img)
        signature = detect_signature(img)
        emblem = detect_emblem(img)
        if emblem is not None:
            seals = [s for s in seals if _overlap(s.box, emblem.box) < 0.3]
        edits = error_level_regions(path, (W, H))
        software = editing_software(path)
    except Exception as exc:
        return VisualForensicResult(analysed=False, note=f"Visual check failed: {exc}")

    regions: list[VisualRegion] = [*seals, *([signature] if signature else []), *([emblem] if emblem else []), *edits]
    findings: list[ForensicFinding] = []
    if software:
        findings.append(
            _finding(
                "visual_editing_software",
                "warning",
                "Image saved by editing software",
                "The file's metadata names a photo/graphic editor. Genuine circulars are usually "
                "exported PDFs or scans; an edited image deserves a closer look.",
                software,
            )
        )
    if edits:
        findings.append(
            _finding(
                "visual_edit_trace",
                "warning",
                "Possible pasted or edited region",
                "Part of the page recompresses very differently from the rest (error-level analysis). "
                "Compression artefacts are common in forwarded images; not evidence on its own.",
                "; ".join(r.note for r in edits),
            )
        )
    if seals:
        findings.append(
            _finding(
                "visual_seal_present",
                "info",
                "Coloured stamp or seal found",
                "Compare it with the issuer's real seal. A PIB fact-check 'FAKE' stamp is also detected here.",
                "; ".join(r.note for r in seals),
            )
        )
    if not signature:
        findings.append(
            _finding(
                "visual_no_signature",
                "info",
                "No signature area detected",
                "No signature area detected in the lower 40% of the page.",
            )
        )
    else:
        findings.append(
            _finding(
                "visual_signature_present",
                "info",
                "Signature area found",
                "Check that the signatory's name and designation below it are real for this office.",
                signature.note,
            )
        )
    if not seals and not signature:
        findings.append(
            _finding(
                "visual_no_seal_signature",
                "info",
                "No seal or signature found",
                "Official orders usually carry a signature block and often a seal. Their absence is not "
                "proof of forgery (many digital circulars are unsigned), but worth noting.",
            )
        )
    return VisualForensicResult(
        analysed=True,
        regions=regions,
        findings=findings,
        editing_software=software,
        has_seal=bool(seals),
        has_signature=signature is not None,
        has_emblem=emblem is not None,
    )
