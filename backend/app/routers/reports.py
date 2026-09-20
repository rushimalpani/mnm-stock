from __future__ import annotations

from fastapi import APIRouter

from app.services import import_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports():
    return {"reports": import_service.list_reports()}
