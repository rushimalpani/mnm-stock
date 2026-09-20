"""Fashion / Lehenga product-name parsing."""
from __future__ import annotations

import re
from typing import Optional

from app.services.normalize import (
    CATEGORY_TOKENS,
    collapse_whitespace,
    extract_design_number,
    join_multiline_tokens,
    looks_like_colour,
    looks_like_size,
    normalize_product_name,
)

SUPPLIER_NOISE = re.compile(
    r"\b(PADMAVATI(?:\s+SELECTION)?|SELECTION)\b",
    re.I,
)

TRAILING_JUNK = re.compile(
    r"^(?:\d+|size|free|freesize)(?:\s+.*)?$",
    re.I,
)


def clean_product_name(raw: str) -> str:
    text = join_multiline_tokens(raw.splitlines()) if "\n" in raw else collapse_whitespace(raw)
    text = SUPPLIER_NOISE.sub(" ", text)
    # Preserve '--' colour delimiter used by supplier fashion reports.
    text = re.sub(r"[ \t]+", " ", text).strip()
    text = re.sub(r"\s{2,}", " ", text).strip(" -")
    return text


def is_garment_size(token: str) -> bool:
    """True for real wearable sizes (36/40/44, S/M/L, Free size) — not codes like '1'."""
    t = collapse_whitespace(token).lower()
    if not t:
        return False
    if t in {"free size", "freesize", "free-size", "xs", "s", "m", "l", "xl", "xxl", "xxxl", "2xl", "3xl", "4xl", "5xl"}:
        return True
    if re.fullmatch(r"\d{2}", t):
        n = int(t)
        return 24 <= n <= 60
    return False


def merge_colour_fragments(parts: list[str]) -> list[str]:
    """Merge adjacent colour words like Navy + Blue into Navy Blue."""
    if not parts:
        return []
    merged: list[str] = []
    i = 0
    while i < len(parts):
        cur = parts[i]
        if (
            i + 1 < len(parts)
            and looks_like_colour(cur)
            and looks_like_colour(parts[i + 1])
            and " " not in cur
            and " " not in parts[i + 1]
        ):
            merged.append(f"{cur} {parts[i + 1]}")
            i += 2
            continue
        if (
            i + 1 < len(parts)
            and cur.lower() in {"navy", "bottle", "sky", "royal", "dark", "light", "off", "green"}
            and looks_like_colour(parts[i + 1])
        ):
            merged.append(f"{cur} {parts[i + 1]}")
            i += 2
            continue
        merged.append(cur)
        i += 1
    return merged


def extract_colour_and_size_after_double_dash(name: str) -> tuple[Optional[str], Optional[str]]:
    """
    Supplier fashion format examples:
      ...--Green Pista-36   → colour Green Pista, size 36
      ...--Pink-40          → colour Pink, size 40
      ...--Sky Blue-44      → colour Sky Blue, size 44
      ...--Morpankhi-1      → colour Morpankhi, size None (1 is not a garment size)
      ...--Block-36         → colour Block, size 36  (preserve PDF spelling)
    """
    if "--" not in name:
        return None, None
    after = name.split("--", 1)[1].strip()
    # Split on hyphens only so "Green Pista" / "Sky Blue" stay intact
    segments = [s.strip() for s in after.split("-") if s.strip()]
    if not segments:
        return None, None

    size: Optional[str] = None
    colour_segments = segments[:]

    if len(colour_segments) >= 2 and is_garment_size(colour_segments[-1]):
        size = colour_segments.pop().strip()
    else:
        # Drop trailing junk codes like "1" / "1 size-free"
        while colour_segments and TRAILING_JUNK.match(colour_segments[-1]) and not is_garment_size(colour_segments[-1]):
            colour_segments.pop()

    colour = " ".join(colour_segments).strip() if colour_segments else None
    if colour and colour.lower() in {"size", "free", "women", "men", "girls", "boys"}:
        colour = None
    return colour, size


def design_label_from_name(name: str, design_number: Optional[str]) -> str:
    """Prefer the shared design prefix before '--Colour'."""
    if "--" in name:
        return name.split("--", 1)[0].strip(" -")
    if design_number:
        parts = [p for p in re.split(r"-", name) if p]
        if len(parts) >= 2 and parts[0] == design_number:
            return f"{design_number}-{parts[1]}"
    return name


def parse_fashion_product_name(raw_name: str) -> dict:
    """
    Parse flexible fashion naming.
    Supports:
      134-Digital Print-Women-36-Black
      131-Digital Print-Women-Free size-36-44-3.5-2.25--Green Pista-36
      569-Work-Women-Free size-6-2.25--Morpankhi-1
    """
    original = clean_product_name(raw_name)
    design_number = extract_design_number(original)
    design_name = design_label_from_name(original, design_number)

    colour, size = extract_colour_and_size_after_double_dash(original)
    category_hint: Optional[str] = None

    raw_parts = [p.strip() for p in re.split(r"-", original) if p.strip()]
    parts = merge_colour_fragments(raw_parts)

    if colour is None:
        for token in reversed(parts[1:] if design_number and parts and parts[0] == design_number else parts):
            low = token.lower()
            if low in CATEGORY_TOKENS or low.replace(" ", "") in {"chaniyacholi", "lehenga"}:
                category_hint = token
                continue
            if looks_like_size(token) and size is None and is_garment_size(token):
                size = token
                continue
            if looks_like_colour(token) and colour is None:
                colour = token
                continue

    # "Free size" in the design prefix is a range label — only use it when
    # the variant itself has no concrete size after --Colour-SIZE
    if size is None and re.search(r"\b(free\s*size|freesize)\b", original, re.I):
        size = "Free size"

    needs_review = False
    notes: list[str] = []
    if not design_number:
        needs_review = True
        notes.append("Could not extract design number from product name")

    return {
        "original_product_text": original,
        "design_number": design_number,
        "design_name": design_name,
        "normalized_name": normalize_product_name(design_name).lower(),
        "colour": colour,
        "size": size,
        "category_hint": category_hint,
        "needs_review": needs_review,
        "review_notes": notes,
        "category": "fashion",
    }
