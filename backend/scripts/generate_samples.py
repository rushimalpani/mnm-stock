"""Generate sample stock report PDFs for local testing when real supplier PDFs are absent."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz


def _add_header(page, title: str, supplier: str, report_date: str) -> float:
    y = 40
    page.insert_text((40, y), title, fontsize=14, fontname="helv")
    y += 22
    page.insert_text((40, y), f"Supplier: {supplier}", fontsize=11, fontname="helv")
    y += 16
    page.insert_text((40, y), f"Report Date: {report_date}", fontsize=11, fontname="helv")
    y += 22
    headers = (
        "Product / Design Name | Item Code | Purchase Qty | Purchase Rate | "
        "Purchase Amount | Stock Qty | Difference | MRP | Stock Amount"
    )
    page.insert_text((40, y), headers, fontsize=8, fontname="helv")
    return y + 16


def create_fashion_sample(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    y = _add_header(page, "Supplier Wise Stock Report - Fashion / Lehenga", "MNM Fashion", "17/09/2026")

    rows = [
        "134-Digital Print-Women-36-Black | 200134001 | 50 | 800 | 40000 | 20 | 30 | 1200 | 24000",
        "134-Digital Print-Women-36-Blue | 200134002 | 40 | 800 | 32000 | 1 | 39 | 1200 | 1200",
        "134-Digital Print-Women-38-Black | 200134003 | 25 | 800 | 20000 | 12 | 13 | 1200 | 14400",
        "256-Bandhani-Girls-Free size-Pink | 200256001 | 30 | 500 | 15000 | 8 | 22 | 899 | 7192",
        "256-Bandhani-Girls-Free size-\nNavy\nBlue | 200256002 | 20 | 500 | 10000 | 5 | 15 | 899 | 4495",
        "890-Chaniya Choli-Women-40-Bottle\nGreen | 200890001 | 15 | 1100 | 16500 | 0 | 15 | 1899 | 0",
        "101-Lehenga-Boys-S-Red | 200101001 | 10 | 600 | 6000 | 3 | 7 | 999 | 2997",
    ]
    for row in rows:
        # Keep multiline product fragments as separate visual lines then continue columns on last
        if "\n" in row:
            parts = row.split("|")
            name = parts[0]
            rest = " | ".join(p.strip() for p in parts[1:])
            name_lines = [ln.strip() for ln in name.strip().splitlines()]
            for i, ln in enumerate(name_lines):
                if i < len(name_lines) - 1:
                    page.insert_text((40, y), ln, fontsize=9, fontname="helv")
                    y += 12
                else:
                    page.insert_text((40, y), f"{ln} | {rest}", fontsize=9, fontname="helv")
                    y += 14
        else:
            page.insert_text((40, y), row, fontsize=9, fontname="helv")
            y += 14

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


def create_jewellery_sample(path: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    y = _add_header(page, "Supplier Wise Stock Report - Jewellery", "MNM Jewels", "19/09/2026")
    rows = [
        "1501-Jewellery-Women------27-16 | 3001501001 | 20 | 250 | 5000 | 14 | 6 | 499 | 6986",
        "1501--------41-1657-1 | 3001501002 | 12 | 300 | 3600 | 7 | 5 | 599 | 4193",
        "2205-Jewellery-Women------18-9 | 3002205001 | 8 | 450 | 3600 | 0 | 8 | 799 | 0",
        "880-Jewellery-Men------22-11 | 300880001 | 5 | 200 | 1000 | 2 | 3 | 399 | 798",
    ]
    for row in rows:
        page.insert_text((40, y), row, fontsize=9, fontname="helv")
        y += 14
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2] / "samples"
    create_fashion_sample(root / "fashion_stock_sample.pdf")
    create_jewellery_sample(root / "jewellery_stock_sample.pdf")
    print("Sample PDFs written to", root)
