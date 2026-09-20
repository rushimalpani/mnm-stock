from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services import search_service

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    q: str = "",
    report_id: Optional[int] = None,
    latest: bool = True,
    category: Optional[str] = None,
    supplier: Optional[str] = None,
    design_number: Optional[str] = None,
    colour: Optional[str] = None,
    size: Optional[str] = None,
    stock_status: Optional[str] = None,
):
    return search_service.search_stock(
        q,
        report_id=report_id,
        latest=latest,
        category=category,
        supplier=supplier,
        design_number=design_number,
        colour=colour,
        size=size,
        stock_status=stock_status,
    )


@router.get("/filters")
def filters(report_id: Optional[int] = None):
    return search_service.list_filter_options(report_id=report_id)
