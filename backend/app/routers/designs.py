from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.services import search_service

router = APIRouter(prefix="/api", tags=["designs"])


@router.get("/designs/{product_id}")
def design_detail(product_id: int, report_id: Optional[int] = None):
    try:
        return search_service.get_design_detail(product_id, report_id=report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/source/{snapshot_id}")
def source(snapshot_id: int):
    try:
        return search_service.get_source(snapshot_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/dashboard")
def dashboard():
    return search_service.get_dashboard()
