"""Jewellery product-name parsing — do not force fashion rules."""
from __future__ import annotations

import re
from typing import Optional

from app.services.normalize import (
    collapse_whitespace,
    join_multiline_tokens,
    normalize_product_name,
)

# Style / article codes look like 1693-1, 1657-1 (not the series prefix 1501).
STYLE_CODE_RE = re.compile(r"(?<!\d)(\d{2,5})-(\d{1,2})(?!\d)")
SERIES_RE = re.compile(r"^(\d{2,})")
# PDF wraps mid-code: "...27-16" + next line "93-1" → "...27-1693-1"
SECONDARY_CODE_RE = re.compile(r"^(\d{1,4})-(\d{1,2})$")
WRAPPED_SPACE_RE = re.compile(r"-(\d+)\s+(\d+)-(\d{1,2})$")


def merge_wrapped_jewellery_name(product_name: str, secondary: Optional[str] = None) -> str:
    """
    Join a line-wrapped jewellery style code.

    PDF often breaks mid-number:
      1501-Jewellery-Women------27-16
      93-1
    → 1501-Jewellery-Women------27-1693-1  (search key 1693)

      1501-Jewellery-Women------100-1
      685-1
    → 1501-Jewellery-Women------100-1685-1
    """
    text = collapse_whitespace(product_name or "").strip()
    sec = (secondary or "").strip()

    if sec and SECONDARY_CODE_RE.fullmatch(sec):
        m_end = re.search(r"-(\d+)$", text)
        if m_end:
            left = m_end.group(1)
            right, var = sec.split("-", 1)
            return f"{text[: m_end.start()]}-{left}{right}-{var}"

    # Already joined with a space between wrap fragments: "...-16 93-1"
    m = WRAPPED_SPACE_RE.search(text)
    if m:
        left, right, var = m.group(1), m.group(2), m.group(3)
        return f"{text[: m.start()]}-{left}{right}-{var}"

    if sec:
        return f"{text} {sec}".strip()
    return text


def extract_jewellery_style_code(original: str) -> tuple[Optional[str], Optional[str]]:
    """
    Return (design_number, design_label) from the jewellery style code.

    Examples:
      1501-Jewellery-Women------27-1693-1 → ("1693", "1693-1")
      1501--------41-1657-1               → ("1657", "1657-1")
      1657-1                              → ("1657", "1657-1")
    """
    series: Optional[str] = None
    m_series = SERIES_RE.match(original.strip())
    if m_series:
        series = m_series.group(1)

    matches = list(STYLE_CODE_RE.finditer(original))
    if not matches:
        return None, None

    chosen = None
    for m in reversed(matches):
        code, suffix = m.group(1), m.group(2)
        if series and code == series:
            continue
        chosen = (code, f"{code}-{suffix}")
        break

    if chosen is None:
        m = matches[-1]
        chosen = (m.group(1), f"{m.group(1)}-{m.group(2)}")

    return chosen


def parse_jewellery_product_name(raw_name: str, secondary: Optional[str] = None) -> dict:
    """
    Jewellery examples:
      1501-Jewellery-Women------27-16   + secondary 93-1  → style 1693
      1501--------41-1657-1             → style 1657
      1501-Jewellery-Women------1693-1  → style 1693

    Search key is the style code (1693 / 1657), not the series prefix (1501).
    """
    original = join_multiline_tokens(raw_name.splitlines()) if "\n" in raw_name else collapse_whitespace(raw_name)
    original = re.sub(r"[ \t]+", " ", original).strip()
    original = merge_wrapped_jewellery_name(original, secondary)

    design_number, design_label = extract_jewellery_style_code(original)
    design_name = design_label or original

    colour: Optional[str] = None
    size: Optional[str] = None

    needs_review = False
    notes: list[str] = []
    if not design_number:
        m = SERIES_RE.match(original)
        if m:
            design_number = m.group(1)
            design_name = original
            notes.append("Used series prefix as design; style code not found")
        else:
            needs_review = True
            notes.append("Could not extract jewellery style code from product name")

    non_empty = [s.strip() for s in original.split("-") if s.strip()]
    if len(non_empty) <= 1:
        needs_review = True
        notes.append("Sparse jewellery product name; verify fields")

    return {
        "original_product_text": original,
        "design_number": design_number,
        "design_name": design_name,
        "normalized_name": normalize_product_name(design_name or original).lower(),
        "colour": colour,
        "size": size,
        "needs_review": needs_review,
        "review_notes": notes,
        "category": "jewellery",
    }
