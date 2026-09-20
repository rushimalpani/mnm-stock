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
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
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
        page=page,
        page_size=page_size,
    )


@router.get("/filters")
def filters(report_id: Optional[int] = None):
    return search_service.list_filter_options(report_id=report_id)
