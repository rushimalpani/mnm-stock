"""Jewellery product-name parsing — do not force fashion rules."""
from __future__ import annotations

import re
from typing import Optional

from app.services.normalize import (
    collapse_whitespace,
    extract_design_name_label,
    extract_design_number,
    join_multiline_tokens,
    normalize_product_name,
)


def parse_jewellery_product_name(raw_name: str) -> dict:
    """
    Jewellery examples:
      1501-Jewellery-Women------27-16
      1501--------41-1657-1
    Preserve the complete original name. Extract design identifier when possible.
    """
    original = join_multiline_tokens(raw_name.splitlines()) if "\n" in raw_name else collapse_whitespace(raw_name)
    # Preserve repeated hyphens meaning empty segments — normalize lightly only
    original = re.sub(r"[ \t]+", " ", original).strip()
    design_number = extract_design_number(original)
    design_name = extract_design_name_label(original, design_number)

    # Split keeping empties to understand structure
    segments = original.split("-")
    non_empty = [s.strip() for s in segments if s.strip()]

    colour: Optional[str] = None
    size: Optional[str] = None

    # Heuristic: trailing numeric segments often encode size / codes — do not invent colour
    # If a clear size-like last numeric exists, capture as size only when unambiguous
    if non_empty:
        last = non_empty[-1]
        if re.fullmatch(r"\d+(\.\d+)?", last):
            size = last
        # Second-to-last sometimes another numeric attribute — leave as part of name only

    # Explicit Jewellery / Women tokens are category, not colour
    needs_review = False
    notes: list[str] = []
    if not design_number:
        needs_review = True
        notes.append("Could not extract jewellery design number from product name")

    # Sparse dash-only names still searchable via original + item code
    if len(non_empty) <= 1:
        needs_review = True
        notes.append("Sparse jewellery product name; verify fields")

    return {
        "original_product_text": original,
        "design_number": design_number,
        "design_name": design_name or original,
        "normalized_name": normalize_product_name(original).lower(),
        "colour": colour,
        "size": size,
        "needs_review": needs_review,
        "review_notes": notes,
        "category": "jewellery",
    }
