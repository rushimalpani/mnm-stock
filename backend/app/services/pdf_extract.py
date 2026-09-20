"""PDF text extraction with PyMuPDF first, pdfplumber fallback."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pymupdf as fitz


@dataclass
class PageText:
    page_number: int  # 1-indexed
    text: str
    method: str


@dataclass
class ExtractedDocument:
    pages: list[PageText]
    method: str

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)

    @property
    def total_pages(self) -> int:
        return len(self.pages)


def _page_has_enough_text(text: str, min_chars: int = 40) -> bool:
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch.isspace())
    return len(cleaned.strip()) >= min_chars


def extract_with_pymupdf(path: Path) -> ExtractedDocument:
    pages: list[PageText] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            pages.append(PageText(page_number=i + 1, text=text, method="pymupdf"))
    return ExtractedDocument(pages=pages, method="pymupdf")


def extract_with_pdfplumber(path: Path) -> ExtractedDocument:
    import pdfplumber

    pages: list[PageText] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            # Also try tables for denser reports
            tables = page.extract_tables() or []
            if tables:
                table_lines: list[str] = []
                for table in tables:
                    for row in table:
                        cells = [str(c).strip() if c is not None else "" for c in row]
                        if any(cells):
                            table_lines.append(" | ".join(cells))
                if table_lines:
                    text = (text + "\n" + "\n".join(table_lines)).strip()
            pages.append(PageText(page_number=i + 1, text=text, method="pdfplumber"))
    return ExtractedDocument(pages=pages, method="pdfplumber")


def extract_pdf_text(path: str | Path) -> ExtractedDocument:
    """
    Extract selectable text. Prefer PyMuPDF; fall back to pdfplumber when
    extraction looks incomplete. OCR is intentionally NOT used by default.
    """
    pdf_path = Path(path)
    primary = extract_with_pymupdf(pdf_path)
    weak_pages = [p for p in primary.pages if not _page_has_enough_text(p.text)]
    if not weak_pages:
        return primary

    # Partial fallback: only re-extract weak pages with pdfplumber if possible
    try:
        fallback = extract_with_pdfplumber(pdf_path)
    except Exception:
        return primary

    merged: list[PageText] = []
    for p in primary.pages:
        if _page_has_enough_text(p.text):
            merged.append(p)
        else:
            alt = next((x for x in fallback.pages if x.page_number == p.page_number), None)
            if alt and _page_has_enough_text(alt.text):
                merged.append(alt)
            else:
                merged.append(p)

    method = "pymupdf+pdfplumber" if any(p.method == "pdfplumber" for p in merged) else "pymupdf"
    return ExtractedDocument(pages=merged, method=method)
