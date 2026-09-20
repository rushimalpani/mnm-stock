"""Shared normalization helpers for search and parsing."""
from __future__ import annotations

import re
from typing import Optional


WHITESPACE_RE = re.compile(r"\s+")
HYPHEN_RE = re.compile(r"-{2,}")
NON_ALNUM_SPACE_RE = re.compile(r"[^0-9a-zA-Z\s\-]+")


def collapse_whitespace(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value.replace("\n", " ").replace("\r", " ")).strip()


def join_multiline_tokens(lines: list[str]) -> str:
    """Join colour/product fragments split across lines, e.g. Navy\\nBlue -> Navy Blue."""
    cleaned = [collapse_whitespace(x) for x in lines if collapse_whitespace(x)]
    return " ".join(cleaned)


def normalize_for_search(value: Optional[str]) -> str:
    if not value:
        return ""
    text = collapse_whitespace(str(value)).lower()
    text = HYPHEN_RE.sub("-", text)
    text = NON_ALNUM_SPACE_RE.sub(" ", text)
    text = collapse_whitespace(text)
    text = text.replace("-", " ")
    return collapse_whitespace(text)


def normalize_product_name(value: Optional[str]) -> str:
    if not value:
        return ""
    text = collapse_whitespace(str(value))
    text = HYPHEN_RE.sub("-", text)
    return text


def parse_number(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    text = collapse_whitespace(str(value))
    if not text or text in {"-", "--", "—", "N/A", "n/a"}:
        return None
    text = text.replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "")
    text = text.strip()
    # Handle parentheses negatives
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return None


def extract_design_number(product_name: str) -> Optional[str]:
    """
    Extract design number from product/design name only.
    Never use PDF page, report entry, or item code as design number.
    Example: '134-Digital Print' -> '134'
    """
    name = collapse_whitespace(product_name)
    if not name:
        return None
    # Leading design number before first hyphen or space-hyphen pattern
    m = re.match(r"^(\d+)\s*[-–—]", name)
    if m:
        return m.group(1)
    # Bare leading digits when followed by letters (rare)
    m = re.match(r"^(\d+)(?=[A-Za-z])", name)
    if m:
        return m.group(1)
    return None


def extract_design_name_label(product_name: str, design_number: Optional[str]) -> str:
    """Human-friendly design label, e.g. '134-Digital Print'."""
    name = normalize_product_name(product_name)
    if not design_number:
        return name
    # Prefer first meaningful segment after design number
    parts = [p for p in re.split(r"-+", name) if p]
    if len(parts) >= 2 and parts[0] == design_number:
        # Take next non-empty textual segment(s) until category/size-like tokens
        meaningful = [parts[1]]
        return f"{design_number}-{meaningful[0]}"
    return name


COLOUR_WORDS = {
    "black", "blue", "navy", "green", "bottle", "red", "wine", "maroon", "pink",
    "peach", "yellow", "gold", "golden", "silver", "white", "cream", "beige",
    "brown", "grey", "gray", "orange", "purple", "violet", "magenta", "cyan",
    "teal", "olive", "mustard", "coral", "ivory", "offwhite", "off-white",
    "multicolor", "multicolour", "multi", "rani", "mehendi", "rama", "firozi",
    "sky", "royal", "dark", "light", "neon", "pastel",
}

SIZE_TOKENS = {
    "free", "freesize", "free-size", "free size", "xs", "s", "m", "l", "xl",
    "xxl", "xxxl", "2xl", "3xl", "4xl", "5xl",
}

CATEGORY_TOKENS = {
    "girls", "women", "boys", "men", "kids", "ladies", "gents",
    "lehenga", "chaniya", "choli", "jewellery", "jewelry", "fashion",
}


def looks_like_size(token: str) -> bool:
    t = token.strip().lower()
    if t in SIZE_TOKENS:
        return True
    if re.fullmatch(r"\d{1,3}", t):
        # clothing size like 36, 38 or jewellery size-ish
        return True
    if re.fullmatch(r"\d+(\.\d+)?", t) and float(t) <= 60:
        return True
    return False


def looks_like_colour(token: str) -> bool:
    t = collapse_whitespace(token).lower()
    if not t:
        return False
    words = t.split()
    if any(w in COLOUR_WORDS for w in words):
        return True
    # Compound colours already joined: Navy Blue
    if t.replace(" ", "") in {c.replace(" ", "").replace("-", "") for c in COLOUR_WORDS}:
        return True
    return False
