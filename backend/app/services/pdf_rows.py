"""Extract stock rows from supplier PDFs using word positions (real report layout).

Uses PyMuPDF (fitz) instead of pdfplumber so large reports stay within Render
free-tier memory (~512MB). pdfplumber word extraction on ~170 pages peaks near 1GB.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pymupdf as fitz

PRODUCT_RE = re.compile(r"^\d{2,}[-–].+")
ITEM_CODE_RE = re.compile(r"^\d{6,}$")
NUMBER_RE = re.compile(r"^-?\d+(?:,\d{3})*(?:\.\d+)?$")
SECONDARY_RE = re.compile(r"^\d{1,4}-\d{1,4}$")
# Fashion designs sometimes split as "577-3" + "Piece-Women-Free" across words
DESIGN_PREFIX_RE = re.compile(r"^\d{2,}-\d{1,4}$")
SUPPLIER_LINE_RE = re.compile(r"^(PADMAVATI|SELECTION|SUPPLIER|TOTAL|PAGE)$", re.I)


@dataclass
class RawTableRow:
    product_name: str
    item_code: Optional[str]
    purchase_qty: Optional[float]
    purchase_rate: Optional[float]
    purchase_amount: Optional[float]
    stock_qty: Optional[float]
    difference: Optional[float]
    mrp: Optional[float]
    stock_amount: Optional[float]
    pdf_page: int
    secondary_label: Optional[str] = None


def _to_float(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return None


def _is_product_name(text: str) -> bool:
    if not PRODUCT_RE.match(text):
        return False
    if SECONDARY_RE.match(text):
        return False
    return True


def _is_product_anchor(text: str, same_line_texts: list[str]) -> bool:
    """True for a full product token, or a split design prefix like '577-3' + 'Piece-…'."""
    if _is_product_name(text):
        return True
    if not DESIGN_PREFIX_RE.match(text):
        return False
    # Require alphabetic continuation on the same line (not a lone jewellery code like 93-1)
    joined = " ".join(same_line_texts)
    return bool(re.search(r"[A-Za-z]{3,}", joined))


def _words_from_page(page: fitz.Page) -> list[dict]:
    """Normalize PyMuPDF word tuples to {text, x0, top} dicts."""
    # (x0, y0, x1, y1, word, block, line, word_no)
    return [
        {"text": w[4], "x0": float(w[0]), "top": float(w[1])}
        for w in page.get_text("words")
        if w[4] and str(w[4]).strip()
    ]


def extract_supplier_from_words(words: list[dict]) -> Optional[str]:
    """Real reports put supplier code/name on a line under the header (e.g. KM)."""
    candidates = [
        w
        for w in words
        if w["top"] < 120 and w["x0"] < 80 and re.fullmatch(r"[A-Za-z]{2,20}", w["text"])
    ]
    skip = {
        "supplier",
        "and",
        "product",
        "name",
        "item",
        "code",
        "pur",
        "qty",
        "rate",
        "stock",
        "diff",
        "mrp",
        "amt",
        "wise",
        "report",
    }
    for w in sorted(candidates, key=lambda x: x["top"]):
        if w["text"].lower() not in skip:
            return w["text"]
    return None


def extract_date_from_words(words: list[dict]) -> Optional[str]:
    for w in words:
        if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", w["text"]) and w["top"] < 50:
            return w["text"]
    return None


def extract_rows_from_words(words: list[dict], page_number: int) -> list[RawTableRow]:
    if not words:
        return []

    header_y = None
    for w in words:
        low = w["text"].lower()
        if low in {"supplier", "item"} and w["top"] < 120:
            header_y = w["top"]
            break

    # Product anchors: full names, or split prefixes like "577-3" + "Piece-Women-Free"
    products: list[dict] = []
    for w in words:
        if w["x0"] >= 120:
            continue
        same_line = [
            x["text"]
            for x in words
            if x is not w and abs(x["top"] - w["top"]) <= 3 and w["x0"] < x["x0"] < 175
        ]
        if _is_product_anchor(w["text"], same_line):
            products.append(w)
    products.sort(key=lambda w: w["top"])
    if not products:
        return []

    rows: list[RawTableRow] = []
    for idx, pw in enumerate(products):
        y0 = pw["top"] - 3
        # Keep band tight so supplier section headers are not merged into the row
        next_y = products[idx + 1]["top"] - 2 if idx + 1 < len(products) else pw["top"] + 28
        y1 = min(next_y, pw["top"] + 28)

        band = [
            w
            for w in words
            if y0 <= w["top"] < y1 and (header_y is None or w["top"] > header_y + 8)
        ]
        band.sort(key=lambda w: (round(w["top"], 1), w["x0"]))

        left_parts: list[str] = []
        item_code: Optional[str] = None
        nums: list[tuple[float, float]] = []  # x, value
        secondary: Optional[str] = None

        for w in band:
            t = w["text"].strip()
            if SUPPLIER_LINE_RE.match(t):
                continue
            if ITEM_CODE_RE.match(t) and item_code is None and w["x0"] < 260:
                item_code = t
                continue
            if w["x0"] < 175:
                # Split fashion start: "577-3" then "Piece-Women-Free…"
                if DESIGN_PREFIX_RE.match(t) and not left_parts:
                    left_parts.append(t)
                    continue
                # Jewellery wrap code on the next line (e.g. 93-1 under the name).
                # Never treat this as fashion text — fashion uses '--Colour' continuations.
                if SECONDARY_RE.match(t) and left_parts and abs(w["top"] - pw["top"]) > 8:
                    joined = " ".join(left_parts).lower()
                    if (
                        "jewell" in joined
                        or "jewelry" in joined
                        or re.search(r"\d-{5,}\d", joined)
                    ):
                        secondary = t
                    continue
                if not ITEM_CODE_RE.match(t) and not NUMBER_RE.match(t.replace(",", "")):
                    left_parts.append(t)
                continue
            cleaned = t.replace(",", "")
            if NUMBER_RE.match(cleaned) and abs(w["top"] - pw["top"]) <= 8:
                val = _to_float(cleaned)
                if val is not None:
                    nums.append((w["x0"], val))

        product_name = re.sub(r"\s+", " ", " ".join(left_parts).strip() or pw["text"])

        nums.sort(key=lambda n: n[0])
        values = [v for _, v in nums]

        purchase_qty = purchase_rate = purchase_amount = None
        stock_qty = difference = mrp = stock_amount = None

        # Pur Qty | Pur Rate | P Amount | Stock Qty | Diff | MRP | Stock Amt
        if len(values) >= 7:
            (
                purchase_qty,
                purchase_rate,
                purchase_amount,
                stock_qty,
                difference,
                mrp,
                stock_amount,
            ) = values[:7]
        elif len(values) == 6:
            purchase_qty, purchase_rate, purchase_amount, stock_qty, mrp, stock_amount = values
        elif len(values) == 5:
            purchase_qty, purchase_rate, stock_qty, mrp, stock_amount = values
        elif len(values) >= 2:
            stock_qty = values[-4] if len(values) >= 4 else values[0]
            mrp = values[-2]
            stock_amount = values[-1]

        if not item_code and not values:
            continue

        rows.append(
            RawTableRow(
                product_name=product_name,
                item_code=item_code,
                purchase_qty=purchase_qty,
                purchase_rate=purchase_rate,
                purchase_amount=purchase_amount,
                stock_qty=stock_qty,
                difference=difference,
                mrp=mrp,
                stock_amount=stock_amount,
                pdf_page=page_number,
                secondary_label=secondary,
            )
        )
    return rows


def extract_rows_from_page(page, page_number: int) -> list[RawTableRow]:
    """Backward-compatible helper (pdfplumber page or any object with extract_words)."""
    if hasattr(page, "extract_words"):
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False) or []
        return extract_rows_from_words(words, page_number)
    if isinstance(page, fitz.Page):
        return extract_rows_from_words(_words_from_page(page), page_number)
    return []


def extract_tabular_rows(path: str | Path) -> tuple[list[RawTableRow], Optional[str], Optional[str], int]:
    """Return (rows, supplier, report_date, page_count) from a real supplier PDF."""
    pdf_path = Path(path)
    all_rows: list[RawTableRow] = []
    supplier: Optional[str] = None
    report_date: Optional[str] = None

    doc = fitz.open(pdf_path)
    try:
        page_count = doc.page_count
        for i in range(page_count):
            words = _words_from_page(doc.load_page(i))
            if i == 0:
                supplier = extract_supplier_from_words(words)
                report_date = extract_date_from_words(words)
            all_rows.extend(extract_rows_from_words(words, i + 1))
    finally:
        doc.close()

    return all_rows, supplier, report_date, page_count
