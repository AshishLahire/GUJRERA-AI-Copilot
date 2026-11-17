"""Validation rules for OCR output text."""

from __future__ import annotations

import re
from collections import Counter


def is_valid_ocr_text(text: str | None) -> bool:
    """Return True if OCR text is non-empty, >= 10 chars, and not highly repetitive."""
    if not text:
        return False
    stripped = text.strip()
    if len(stripped) < 10:
        return False

    # Check character-level repetition (ignoring whitespace)
    non_ws = re.sub(r"\s+", "", stripped)
    if len(non_ws) < 8:
        return False
    char_counts = Counter(non_ws.lower())
    if len(char_counts) <= 2:
        return False
    most_common_char_count = char_counts.most_common(1)[0][1]
    if most_common_char_count / len(non_ws) > 0.60:
        return False

    # Check line-level repetition when there are multiple lines
    lines = [ln.strip().lower() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) >= 5:
        unique_line_ratio = len(set(lines)) / len(lines)
        if unique_line_ratio < 0.30:
            return False

    # Check word / 3-gram repetition for hallucinated VLM loops
    words = re.findall(r"\w+", stripped.lower())
    if len(words) >= 12:
        unique_word_ratio = len(set(words)) / len(words)
        if unique_word_ratio < 0.15:
            return False
        trigrams = [tuple(words[i : i + 3]) for i in range(len(words) - 2)]
        if trigrams:
            top_trigram_count = Counter(trigrams).most_common(1)[0][1]
            if top_trigram_count >= 5 and (top_trigram_count / len(trigrams)) > 0.35:
                return False

    return True
