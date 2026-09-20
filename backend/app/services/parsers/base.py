from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class ParsedRow:
    original_product_text: str
    design_number: Optional[str] = None
    design_name: Optional[str] = None
    normalized_name: str = ""
    category: str = "unknown"  # fashion | jewellery | unknown
    item_code: Optional[str] = None
    colour: Optional[str] = None
    size: Optional[str] = None
    purchase_qty: Optional[float] = None
    purchase_rate: Optional[float] = None
    purchase_amount: Optional[float] = None
    stock_qty: Optional[float] = None
    difference: Optional[float] = None
    mrp: Optional[float] = None
    stock_amount: Optional[float] = None
    supplier: Optional[str] = None
    report_date: Optional[str] = None
    pdf_page: Optional[int] = None
    needs_review: bool = False
    review_notes: list[str] = field(default_factory=list)

    def mark_review(self, note: str) -> None:
        self.needs_review = True
        if note and note not in self.review_notes:
            self.review_notes.append(note)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["review_notes"] = "; ".join(self.review_notes)
        return data


@dataclass
class ParseResult:
    rows: list[ParsedRow]
    supplier: Optional[str] = None
    report_date: Optional[str] = None
    category: str = "unknown"
    total_pages: int = 0
    extraction_method: str = "pymupdf"
    warnings: list[str] = field(default_factory=list)

    @property
    def rows_parsed(self) -> int:
        return sum(1 for r in self.rows if not r.needs_review)

    @property
    def rows_review(self) -> int:
        return sum(1 for r in self.rows if r.needs_review)
