"""Detect report category and orchestrate row parsing."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.services.normalize import collapse_whitespace, parse_number
from app.services.parsers.base import ParseResult, ParsedRow
from app.services.parsers.fashion import parse_fashion_product_name
from app.services.parsers.jewellery import parse_jewellery_product_name
from app.services.pdf_extract import extract_pdf_text

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b"),
    re.compile(r"Report\s*Date\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.I),
]

SUPPLIER_PATTERNS = [
    re.compile(r"Supplier\s*[:\-]\s*(.+)", re.I),
    re.compile(r"Supplier\s+Name\s*[:\-]\s*(.+)", re.I),
    re.compile(r"Party\s*[:\-]\s*(.+)", re.I),
]

HEADER_HINTS = re.compile(
    r"item\s*code|purchase\s*qty|purchase\s*quantity|stock\s*qty|stock\s*quantity|mrp|stock\s*amount",
    re.I,
)

SKIP_LINE = re.compile(
    r"^(page\s*\d+|supplier\s*wise|stock\s*report|total|grand\s*total|s\.?\s*no\.?|sr\.?\s*no\.?)\b",
    re.I,
)


def detect_category(text: str, filename: str = "") -> str:
    low = (text + " " + filename).lower()
    jewellery_score = 0
    fashion_score = 0
    if "jewell" in low or "jewelry" in low:
        jewellery_score += 3
    if any(
        w in low
        for w in (
            "lehenga",
            "chaniya",
            "fashion",
            "bandhani",
            "digital print",
            "free size",
            "freesize",
            "-work-women",
            "padmavati",
        )
    ):
        fashion_score += 3
    # Fashion colour marker used by supplier reports: --Morpankhi / --Purple
    if re.search(r"--[A-Za-z]{3,}", text):
        fashion_score += 4
    if "women------" in low or re.search(r"\d+-{4,}\d", low):
        jewellery_score += 2
    if fashion_score > jewellery_score and fashion_score > 0:
        return "fashion"
    if jewellery_score > fashion_score and jewellery_score > 0:
        return "jewellery"
    if fashion_score and jewellery_score:
        return "mixed"
    return "unknown"


def normalize_report_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    text = collapse_whitespace(raw)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text


def extract_report_date(text: str) -> Optional[str]:
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            return normalize_report_date(m.group(1))
    return None


def extract_supplier(text: str) -> Optional[str]:
    for pat in SUPPLIER_PATTERNS:
        m = pat.search(text)
        if m:
            value = collapse_whitespace(m.group(1))
            # Cut trailing labels
            value = re.split(r"\s{2,}|\t|Report\s*Date|Date\s*:", value, maxsplit=1)[0]
            return value.strip(" :-") or None
    # Fallback: first non-empty line that isn't a header
    for line in text.splitlines()[:15]:
        line = collapse_whitespace(line)
        if not line or HEADER_HINTS.search(line) or SKIP_LINE.search(line):
            continue
        if re.search(r"supplier", line, re.I):
            continue
        if len(line) > 3 and not re.fullmatch(r"[\d/.\-]+", line):
            # Avoid grabbing report titles
            if "stock" in line.lower() and "report" in line.lower():
                continue
    return None


def _is_item_code(token: str) -> bool:
    t = token.strip()
    return bool(re.fullmatch(r"\d{6,}", t))


def _split_row_tokens(line: str) -> list[str]:
    if "|" in line:
        parts = [collapse_whitespace(p) for p in line.split("|")]
        return [p for p in parts if p]
    # Multiple spaces / tabs as separators
    parts = re.split(r"\s{2,}|\t+", line.strip())
    parts = [collapse_whitespace(p) for p in parts if collapse_whitespace(p)]
    if len(parts) >= 5:
        return parts
    # Fallback: single-space split for denser lines ending with numbers
    return [collapse_whitespace(p) for p in line.split() if collapse_whitespace(p)]


def _parse_numeric_tail(tokens: list[str]) -> tuple[dict, list[str]]:
    """
    From the right, pull: stock_amount, mrp, difference, stock_qty,
    purchase_amount, purchase_rate, purchase_qty (when present).
    Returns (fields, remaining_tokens).
    """
    nums: list[Optional[float]] = []
    consumed = 0
    for tok in reversed(tokens):
        n = parse_number(tok)
        if n is None:
            break
        nums.append(n)
        consumed += 1
    nums.reverse()
    remaining = tokens[: len(tokens) - consumed] if consumed else tokens[:]

    fields = {
        "purchase_qty": None,
        "purchase_rate": None,
        "purchase_amount": None,
        "stock_qty": None,
        "difference": None,
        "mrp": None,
        "stock_amount": None,
    }

    # Expected order of numeric columns (left→right):
    # purchase_qty, purchase_rate, purchase_amount, stock_qty, difference, mrp, stock_amount
    mapping = [
        "purchase_qty",
        "purchase_rate",
        "purchase_amount",
        "stock_qty",
        "difference",
        "mrp",
        "stock_amount",
    ]
    if len(nums) >= 7:
        for key, val in zip(mapping, nums[-7:]):
            fields[key] = val
    elif len(nums) == 6:
        # Assume purchase_rate omitted or difference omitted — prefer keeping stock_qty & mrp
        # purchase_qty, purchase_amount, stock_qty, difference, mrp, stock_amount
        keys = ["purchase_qty", "purchase_amount", "stock_qty", "difference", "mrp", "stock_amount"]
        for key, val in zip(keys, nums):
            fields[key] = val
    elif len(nums) == 5:
        keys = ["purchase_qty", "stock_qty", "difference", "mrp", "stock_amount"]
        for key, val in zip(keys, nums):
            fields[key] = val
    elif len(nums) == 4:
        keys = ["purchase_qty", "stock_qty", "mrp", "stock_amount"]
        for key, val in zip(keys, nums):
            fields[key] = val
    elif len(nums) == 3:
        keys = ["stock_qty", "mrp", "stock_amount"]
        for key, val in zip(keys, nums):
            fields[key] = val
    elif len(nums) == 2:
        fields["stock_qty"] = nums[0]
        fields["mrp"] = nums[1]
    elif len(nums) == 1:
        fields["stock_qty"] = nums[0]

    return fields, remaining


def parse_data_line(
    line: str,
    *,
    page: int,
    supplier: Optional[str],
    report_date: Optional[str],
    category: str,
) -> Optional[ParsedRow]:
    text = collapse_whitespace(line)
    if not text or SKIP_LINE.search(text) or HEADER_HINTS.search(text):
        return None
    if re.fullmatch(r"[\d.\s]+", text):
        return None

    tokens = _split_row_tokens(text)
    if len(tokens) < 2:
        return None

    item_code: Optional[str] = None
    # Item code often after product name
    for i, tok in enumerate(tokens):
        if _is_item_code(tok):
            item_code = tok
            product_tokens = tokens[:i]
            after = tokens[i + 1 :]
            break
    else:
        # No item code — try last non-numeric-looking chunk as product, rest numbers
        product_tokens = []
        after = tokens
        # Find first parseable number index
        first_num_idx = None
        for i, tok in enumerate(tokens):
            if parse_number(tok) is not None and re.fullmatch(r"[-+]?\d[\d,]*(\.\d+)?", tok.replace(",", "")):
                first_num_idx = i
                break
        if first_num_idx is None or first_num_idx == 0:
            return None
        product_tokens = tokens[:first_num_idx]
        after = tokens[first_num_idx:]

    product_name = collapse_whitespace(" ".join(product_tokens))
    # If product was space-joined hyphen names, restore hyphens when tokens were split badly
    if product_tokens and all("-" not in t for t in product_tokens) and len(product_tokens) > 3:
        # already fine as spaces
        pass

    # When pipe/table format kept product with hyphens in one cell
    if len(product_tokens) == 1:
        product_name = product_tokens[0]

    fields, leftover = _parse_numeric_tail(after if item_code else after)
    if leftover and not item_code:
        # leftover may include fragments
        pass

    # Choose name parser
    effective_category = category
    if effective_category == "unknown":
        if "jewell" in product_name.lower() or re.search(r"\d+-{3,}", product_name):
            effective_category = "jewellery"
        else:
            effective_category = "fashion"
    if effective_category == "mixed":
        if "jewell" in product_name.lower() or re.search(r"\d+-{3,}", product_name):
            effective_category = "jewellery"
        else:
            effective_category = "fashion"

    if effective_category == "jewellery":
        meta = parse_jewellery_product_name(product_name)
    else:
        meta = parse_fashion_product_name(product_name)

    row = ParsedRow(
        original_product_text=meta["original_product_text"],
        design_number=meta.get("design_number"),
        design_name=meta.get("design_name"),
        normalized_name=meta.get("normalized_name") or "",
        category=meta.get("category") or effective_category,
        item_code=item_code,
        colour=meta.get("colour"),
        size=meta.get("size"),
        purchase_qty=fields["purchase_qty"],
        purchase_rate=fields["purchase_rate"],
        purchase_amount=fields["purchase_amount"],
        stock_qty=fields["stock_qty"],
        difference=fields["difference"],
        mrp=fields["mrp"],
        stock_amount=fields["stock_amount"],
        supplier=supplier,
        report_date=report_date,
        pdf_page=page,
        needs_review=bool(meta.get("needs_review")),
        review_notes=list(meta.get("review_notes") or []),
    )

    if row.stock_qty is None:
        row.mark_review("Missing stock quantity")
    if not row.item_code:
        row.mark_review("Missing item code")
    if row.mrp is None:
        row.mark_review("Missing MRP")

    return row


def _continue_multiline_product(buffer: str, line: str) -> bool:
    """Detect continuation lines that are colour/name fragments without numbers."""
    text = collapse_whitespace(line)
    if not text:
        return False
    if parse_number(text) is not None and re.fullmatch(r"[-+]?\d[\d,]*(\.\d+)?", text.replace(",", "")):
        return False
    if _is_item_code(text):
        return False
    if HEADER_HINTS.search(text) or SKIP_LINE.search(text):
        return False
    # Short alphabetic fragment
    if re.fullmatch(r"[A-Za-z][A-Za-z\s\-]*", text) and len(text) <= 40:
        return True
    return False


def parse_pages(pages: list, filename: str = "") -> ParseResult:
    full_text = "\n".join(p.text for p in pages)
    category = detect_category(full_text, filename)
    supplier = extract_supplier(full_text)
    report_date = extract_report_date(full_text)

    rows: list[ParsedRow] = []
    warnings: list[str] = []

    for page in pages:
        lines = (page.text or "").splitlines()
        buffer = ""
        for raw in lines:
            line = raw.rstrip()
            if not collapse_whitespace(line):
                continue
            if buffer and _continue_multiline_product(buffer, line):
                buffer = f"{buffer} {collapse_whitespace(line)}"
                continue
            if buffer:
                parsed = parse_data_line(
                    buffer,
                    page=page.page_number,
                    supplier=supplier,
                    report_date=report_date,
                    category=category,
                )
                if parsed:
                    rows.append(parsed)
                buffer = ""
            # Start new potential row
            if HEADER_HINTS.search(line) or SKIP_LINE.search(line):
                continue
            buffer = collapse_whitespace(line)
        if buffer:
            parsed = parse_data_line(
                buffer,
                page=page.page_number,
                supplier=supplier,
                report_date=report_date,
                category=category,
            )
            if parsed:
                rows.append(parsed)

    if not rows:
        warnings.append("No stock rows detected — check PDF text extraction")

    # Refine overall category from rows
    cats = {r.category for r in rows}
    if cats == {"fashion"}:
        category = "fashion"
    elif cats == {"jewellery"}:
        category = "jewellery"
    elif len(cats) > 1:
        category = "mixed"

    return ParseResult(
        rows=rows,
        supplier=supplier,
        report_date=report_date,
        category=category,
        total_pages=len(pages),
        warnings=warnings,
    )


def _raw_table_to_parsed(
    raw,
    *,
    supplier: Optional[str],
    report_date: Optional[str],
    category: str,
) -> ParsedRow:
    from app.services.parsers.jewellery import merge_wrapped_jewellery_name

    product_name = raw.product_name
    if raw.secondary_label:
        # Join PDF line-wrap mid-code: "...27-16" + "93-1" → "...27-1693-1"
        product_name = merge_wrapped_jewellery_name(product_name, raw.secondary_label)

    effective = category
    low = product_name.lower()
    # Fashion colour marker is '--Colour'; jewellery empty fields look like '------27'
    has_fashion_colour = bool(re.search(r"--[A-Za-z]{3,}", product_name))
    if (
        has_fashion_colour
        or "free size" in low
        or "freesize" in low
        or "-work-women" in low
        or "lehenga" in low
        or "bandhani" in low
    ):
        effective = "fashion"
    elif "jewell" in low or "jewelry" in low:
        effective = "jewellery"
    elif effective in {"unknown", "mixed"}:
        if re.search(r"\d+-{3,}\d", product_name):
            effective = "jewellery"
        else:
            effective = "fashion"

    if effective == "jewellery":
        meta = parse_jewellery_product_name(product_name)
    else:
        meta = parse_fashion_product_name(product_name)

    row = ParsedRow(
        original_product_text=meta["original_product_text"],
        design_number=meta.get("design_number"),
        design_name=meta.get("design_name"),
        normalized_name=meta.get("normalized_name") or "",
        category=meta.get("category") or effective,
        item_code=raw.item_code,
        colour=meta.get("colour"),
        size=meta.get("size"),
        purchase_qty=raw.purchase_qty,
        purchase_rate=raw.purchase_rate,
        purchase_amount=raw.purchase_amount,
        stock_qty=raw.stock_qty,
        difference=raw.difference,
        mrp=raw.mrp,
        stock_amount=raw.stock_amount,
        supplier=supplier,
        report_date=report_date,
        pdf_page=raw.pdf_page,
        needs_review=bool(meta.get("needs_review")),
        review_notes=list(meta.get("review_notes") or []),
    )
    if row.stock_qty is None:
        row.mark_review("Missing stock quantity")
    if not row.item_code:
        row.mark_review("Missing item code")
    if row.mrp is None:
        row.mark_review("Missing MRP")
    return row


def parse_stock_pdf(path: str | Path) -> ParseResult:
    """
    Prefer position-based table extraction (real Supplier Wise Stock Reports),
    then fall back to plain-text line parsing.
    """
    path = Path(path)
    from app.services.pdf_rows import extract_tabular_rows

    try:
        raw_rows, tab_supplier, tab_date, page_count = extract_tabular_rows(path)
    except Exception:
        raw_rows, tab_supplier, tab_date, page_count = [], None, None, 0

    # Only trust tabular extraction when it found complete stock rows
    good_tabular = [r for r in raw_rows if r.item_code and r.stock_qty is not None]
    if len(good_tabular) >= 3:
        # Avoid a second full-file text pass (memory/time) — use product names + filename.
        sample_text = " ".join(r.product_name for r in good_tabular[:40]) + " " + path.name
        category = detect_category(sample_text, path.name)
        supplier = tab_supplier
        report_date = normalize_report_date(tab_date) if tab_date else None

        rows = [
            _raw_table_to_parsed(r, supplier=supplier, report_date=report_date, category=category)
            for r in good_tabular
        ]
        cats = {r.category for r in rows}
        if cats == {"fashion"}:
            category = "fashion"
        elif cats == {"jewellery"}:
            category = "jewellery"
        elif len(cats) > 1:
            category = "mixed"

        return ParseResult(
            rows=rows,
            supplier=supplier,
            report_date=report_date,
            category=category,
            total_pages=page_count,
            extraction_method="pymupdf-words",
            warnings=[],
        )

    extracted = extract_pdf_text(path)
    result = parse_pages(extracted.pages, filename=path.name)
    result.extraction_method = extracted.method
    result.total_pages = extracted.total_pages
    return result
