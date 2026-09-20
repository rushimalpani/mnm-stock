"""CSV / Excel export of search results."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.services import search_service

router = APIRouter(prefix="/api/export", tags=["export"])


def _flatten(results: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for g in results:
        for v in g.get("variants") or []:
            rows.append(
                {
                    "design_number": g.get("design_number"),
                    "design_name": g.get("design_name"),
                    "category": g.get("category"),
                    "supplier": g.get("supplier"),
                    "report_date": g.get("report_date"),
                    "colour": v.get("colour"),
                    "size": v.get("size"),
                    "stock_qty": v.get("stock_qty"),
                    "mrp": v.get("mrp"),
                    "item_code": v.get("item_code"),
                    "purchase_qty": v.get("purchase_qty"),
                    "purchase_rate": v.get("purchase_rate"),
                    "purchase_amount": v.get("purchase_amount"),
                    "difference": v.get("difference"),
                    "stock_amount": v.get("stock_amount"),
                    "pdf_page": v.get("pdf_page"),
                    "filename": v.get("filename") or g.get("filename"),
                }
            )
    return rows


@router.get("/csv")
def export_csv(
    q: str = "",
    report_id: Optional[int] = None,
    latest: bool = True,
    category: Optional[str] = None,
    colour: Optional[str] = None,
    design_number: Optional[str] = None,
):
    data = search_service.search_stock(
        q,
        report_id=report_id,
        latest=latest,
        category=category,
        colour=colour,
        design_number=design_number,
    )
    rows = _flatten(data["results"])
    design = design_number or (q.strip().split()[0] if q.strip() else "search")
    filename = f"design_{design}_stock.csv"

    buf = io.StringIO()
    fieldnames = [
        "design_number",
        "design_name",
        "category",
        "supplier",
        "report_date",
        "colour",
        "size",
        "stock_qty",
        "mrp",
        "item_code",
        "purchase_qty",
        "purchase_rate",
        "purchase_amount",
        "difference",
        "stock_amount",
        "pdf_page",
        "filename",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/xlsx")
def export_xlsx(
    q: str = "",
    report_id: Optional[int] = None,
    latest: bool = True,
    category: Optional[str] = None,
    colour: Optional[str] = None,
    design_number: Optional[str] = None,
):
    data = search_service.search_stock(
        q,
        report_id=report_id,
        latest=latest,
        category=category,
        colour=colour,
        design_number=design_number,
    )
    rows = _flatten(data["results"])
    design = design_number or (q.strip().split()[0] if q.strip() else "search")
    filename = f"design_{design}_stock.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "Stock"
    headers = [
        "design_number",
        "design_name",
        "category",
        "supplier",
        "report_date",
        "colour",
        "size",
        "stock_qty",
        "mrp",
        "item_code",
        "purchase_qty",
        "purchase_rate",
        "purchase_amount",
        "difference",
        "stock_amount",
        "pdf_page",
        "filename",
    ]
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h) for h in headers])
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
