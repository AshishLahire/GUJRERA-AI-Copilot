"""Parse and normalise GUJRERA registration numbers.

Assumed formats (from public certificates; VERIFY on real documents before relying on them):

    Project: PR/GJ/<DISTRICT>/<TALUKA>/<AUTHORITY>/<CODE>/<DDMMYY>[/<DDMMYY>...]
             e.g. PR/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/RAA01234/150321
             newer numbers add a date: .../Gandhinagar Municipal Corporation/MAA14450/301124/311228
    Agent:   AG/GJ/<DISTRICT>/<TALUKA>[/<AUTHORITY>]/<CODE>/<DDMMYY>[R<n>]
             e.g. AG/GJ/GANDHINAGAR/GANDHINAGAR/AA06250/240231R1 (as on the public portal, 2026)

The parser is lenient: it tolerates OCR noise (spaces around separators,
backslashes or pipes instead of slashes, letter O for digit 0 in numeric
parts), trailing words after the number, and a missing date. Mock data uses a
``MOCK`` code prefix (``MOCK01234``) so demo numbers can never be mistaken for
real ones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Real prefixes: RAA/MAA/PAA... (projects), AA (agents), RN366AA / MN51AA (portal, 2026); MOCK for demo data.
_CODE_RE = re.compile(r"^(MOCK|[A-Z]{2,3}|[A-Z]{2}[0-9]{1,4}[A-Z]{2})([0-9OIlSB]{4,6})$")  # also RN366AA10266
# DDMMYY, optionally with a renewal suffix as on agent numbers (240231R1).
_DATE_RE = re.compile(r"^([0-9OIl]{6})(R[0-9]{1,2})?(?![0-9A-Za-z])")
# Markers seen between the code and the dates on portal numbers: EX1/EX2 (extension), A1M/A2R (alteration).
_MARKER_RE = re.compile(r"^(EX[0-9]{1,2}|A[0-9]{1,2}[A-Z]?)$")
_START_RE = re.compile(r"\b(PR|AG)\s*[/\\|]\s*GJ\s*[/\\|]", re.IGNORECASE)
_DIGIT_FIXES = str.maketrans({"O": "0", "I": "1", "l": "1", "S": "5", "B": "8"})


@dataclass(frozen=True)
class ReraNumber:
    kind: str  # "project" | "agent"
    district: str | None
    taluka: str | None
    authority: str | None
    code: str | None
    reg_date: date | None
    normalised: str
    is_mock: bool
    warnings: tuple[str, ...] = ()


def _parse_ddmmyy(token: str) -> date | None:
    try:
        return date(2000 + int(token[4:6]), int(token[2:4]), int(token[0:2]))
    except ValueError:
        return None


def _date_token(segment: str) -> str:
    """The DDMMYY[Rn] token at the start of a segment, with OCR letter/digit fixes on the date part."""
    m = _DATE_RE.match(segment.split(" ")[0])
    if not m:
        return segment
    return m.group(1).translate(_DIGIT_FIXES) + (m.group(2) or "")


def _match_code(segment: str) -> str | None:
    # "RAA 01234" (OCR split) or "RAA01234 CALL NOW" (trailing words, no date)
    for token in (segment.replace(" ", ""), segment.split(" ")[0]):
        m = _CODE_RE.match(token.rstrip(".,:;)!"))
        if m:
            return m.group(1) + m.group(2).translate(_DIGIT_FIXES)
    return None


def parse_rera_number(raw: str) -> ReraNumber | None:
    """Parse one registration number. Returns None if it is not recognisable."""
    if not raw:
        return None
    text = raw.strip().upper()
    text = re.sub(r"\s*[/\\|]\s*", "/", text)
    text = re.sub(r"\s+", " ", text)
    parts = [p.strip() for p in text.split("/") if p.strip()]
    if len(parts) < 4 or parts[0] not in ("PR", "AG") or parts[1] != "GJ":
        return None

    warnings: list[str] = []
    kind = "project" if parts[0] == "PR" else "agent"
    rest = parts[2:]

    # Numbers as shown on the portal can carry markers and more dates after the code:
    # .../MAA14450/301124/311228, .../RAA01953/EX1/170621, .../RAA15048/A1M/131025/311230.
    # Find the code segment followed only by marker/date segments; the first date is the registration date.
    code = None
    reg_date = None
    tail_tokens: list[str] = []  # everything after the code, in the original order
    for i in range(len(rest) - 2, 0, -1):
        heads = [seg.split(" ")[0] for seg in rest[i + 1:]]
        if not all(_DATE_RE.match(h) or _MARKER_RE.match(h) for h in heads):
            continue
        if not any(_DATE_RE.match(h) for h in heads):
            break
        found = _match_code(rest[i])
        here = rest[i].split(" ")[0]
        if not found and (_DATE_RE.match(here) or _MARKER_RE.match(here)):
            continue  # still inside the markers/dates; the code is further left
        if found:
            code = found
            tail_tokens = [_date_token(h) if _DATE_RE.match(h) else h for h in heads]
            first = next(tok for tok in tail_tokens if _DATE_RE.match(tok))
            reg_date = _parse_ddmmyy(first[:6])
            if reg_date is None:
                warnings.append("invalid_date")
            rest = rest[:i]
        break

    if code is None:
        # Registration date: last segment; anything after its first token is trailing text.
        m = _DATE_RE.match(rest[-1])
        if m and len(rest) > 1:
            tail_tokens = [_date_token(rest[-1])]
            reg_date = _parse_ddmmyy(tail_tokens[0][:6])
            if reg_date is None:
                warnings.append("invalid_date")
            rest = rest[:-1]
        else:
            warnings.append("missing_date")

        code = _match_code(rest[-1]) if rest else None
        if code:
            rest = rest[:-1]
        else:
            warnings.append("missing_code")

    district = rest[0] if len(rest) >= 1 else None
    taluka = rest[1] if len(rest) >= 2 else None
    authority = rest[2] if len(rest) >= 3 else None
    if len(rest) > 3:
        warnings.append("extra_segments")
    if district is None:
        warnings.append("missing_district")

    segments = [parts[0], "GJ", *rest]
    if code:
        segments.append(code)
    segments.extend(tail_tokens)

    return ReraNumber(
        kind=kind,
        district=district,
        taluka=taluka,
        authority=authority,
        code=code,
        reg_date=reg_date,
        normalised="/".join(segments),
        is_mock=bool(code and code.startswith("MOCK")),
        warnings=tuple(warnings),
    )


def find_rera_numbers(text: str) -> list[ReraNumber]:
    """Find registration numbers in free text (OCR output, ads, chat messages)."""
    found: dict[str, ReraNumber] = {}
    lines = [ln for ln in text.splitlines()]
    for idx, line in enumerate(lines):
        starts = [m.start() for m in _START_RE.finditer(line)]
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(line)
            chunk = re.split(r"[,;]", line[start:end])[0]
            parsed = parse_rera_number(chunk)
            is_last_on_line = i + 1 == len(starts)
            if is_last_on_line and (parsed is None or not parsed.code or "missing_date" in parsed.warnings):
                # Long numbers often wrap in brochures and OCR output: "…/SURAT/SURAT" + "CITY/SUDA/…"
                nxt = next((ln.strip() for ln in lines[idx + 1:idx + 3] if ln.strip()), "")
                if "/" in nxt and not _START_RE.search(nxt):
                    joined = parse_rera_number(chunk.rstrip() + " " + re.split(r"[,;]", nxt)[0])
                    if joined and joined.code and (parsed is None or len(joined.warnings) <= len(parsed.warnings)):
                        parsed = joined
            if parsed and parsed.code and parsed.normalised not in found:
                found[parsed.normalised] = parsed
    return list(found.values())
