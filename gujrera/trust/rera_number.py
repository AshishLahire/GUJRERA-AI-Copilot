"""Parse and normalise GUJRERA registration numbers.

Assumed formats (from public certificates; VERIFY on real documents before relying on them):

    Project: PR/GJ/<DISTRICT>/<TALUKA>/<AUTHORITY>/<CODE>/<DDMMYY>
             e.g. PR/GJ/AHMEDABAD/AHMEDABAD CITY/AUDA/RAA01234/150321
    Agent:   AG/GJ/<DISTRICT>/<TALUKA>/<AUTHORITY>/<CODE>/<DDMMYY>

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

# 3-letter real prefix (e.g. RAA) or the 4-letter MOCK prefix, then 4-6 digit-like chars.
_CODE_RE = re.compile(r"^(MOCK|[A-Z]{3})([0-9OIlSB]{4,6})$")
_DATE_RE = re.compile(r"^([0-9OIl]{6})(?:\s|$)")
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


def _match_code(segment: str) -> str | None:
    # "RAA 01234" (OCR split) or "RAA01234 CALL NOW" (trailing words, no date)
    for token in (segment.replace(" ", ""), segment.split(" ")[0]):
        m = _CODE_RE.match(token)
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

    # Registration date: last segment; anything after its first token is trailing text.
    reg_date = None
    date_token = None
    m = _DATE_RE.match(rest[-1])
    if m and len(rest) > 1:
        date_token = m.group(1).translate(_DIGIT_FIXES)
        reg_date = _parse_ddmmyy(date_token)
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
    if date_token:
        segments.append(date_token)

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
    for line in text.splitlines():
        starts = [m.start() for m in _START_RE.finditer(line)]
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(line)
            chunk = re.split(r"[,;]", line[start:end])[0]
            parsed = parse_rera_number(chunk)
            if parsed and parsed.code and parsed.normalised not in found:
                found[parsed.normalised] = parsed
    return list(found.values())
