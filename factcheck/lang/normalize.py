"""Unicode normalization and Indic digit normalization.

Used across Pramaan to ensure NFC Unicode form and ASCII digits for reference/date matching
while preserving original text for human display.
"""

from __future__ import annotations

import unicodedata

# Explicit translation table converting all Indic & Arabic-Indic digits to ASCII 0-9
# Devanagari:       ०१२३४५६७८९ (0x0966 - 0x096F)
# Bengali:          ০১২৩৪৫৬৭৮৯ (0x09E6 - 0x09EF)
# Gurmukhi:         ੦੧੨੩੪੫੬੭੮੯ (0x0A66 - 0x0A6F)
# Gujarati:         ૦૧૨૩૪૫૬૭૮૯ (0x0AE6 - 0x0AEF)
# Odia:             ୦୧୨୩୪୫୬୭୮୯ (0x0B66 - 0x0B6F)
# Tamil:            ௦௧௨௩௪௫௬௭௮௯ (0x0BE6 - 0x0BEF)
# Telugu:           ౦౧౨౩౪౫౬౭౮౯ (0x0C66 - 0x0C6F)
# Kannada:          ೦೧೨೩೪೫೬೭೮೯ (0x0CE6 - 0x0CEF)
# Malayalam:        ൦൧൨൩൪൫൬൭൮൯ (0x0D66 - 0x0D6F)
# Arabic-Indic:     ٠١٢٣٤٥٦٧٨٩ (0x0660 - 0x0669)
# Ext Arabic-Indic: ۰۱۲۳۴۵۶۷۸۹ (0x06F0 - 0x06F9 - used in Urdu/Sindhi/Persian)

_DIGIT_RANGES: list[tuple[int, int]] = [
    (0x0966, 0x096F),  # Devanagari
    (0x09E6, 0x09EF),  # Bengali
    (0x0A66, 0x0A6F),  # Gurmukhi (Punjabi)
    (0x0AE6, 0x0AEF),  # Gujarati
    (0x0B66, 0x0B6F),  # Odia
    (0x0BE6, 0x0BEF),  # Tamil
    (0x0C66, 0x0C6F),  # Telugu
    (0x0CE6, 0x0CEF),  # Kannada
    (0x0D66, 0x0D6F),  # Malayalam
    (0x0660, 0x0669),  # Arabic-Indic
    (0x06F0, 0x06F9),  # Extended Arabic-Indic (Urdu)
]

INDIC_DIGITS_TRANS: dict[int, int] = {}
for start, end in _DIGIT_RANGES:
    for code in range(start, end + 1):
        ascii_digit = ord("0") + (code - start)
        INDIC_DIGITS_TRANS[code] = ascii_digit


def normalize_digits(text: str) -> str:
    """Convert any Indic or Arabic-Indic digits to ASCII 0-9."""
    if not text:
        return ""
    return text.translate(INDIC_DIGITS_TRANS)


def normalize_text(text: str, *, convert_digits: bool = False) -> str:
    """Normalize text using Unicode NFC form, with optional Indic digit conversion to ASCII."""
    if not text:
        return ""
    nfc = unicodedata.normalize("NFC", text)
    if convert_digits:
        return normalize_digits(nfc)
    return nfc
