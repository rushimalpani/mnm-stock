from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.schemas import ConfirmImportRequest
from app.services import import_service

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("/pdf")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    path = import_service.save_upload(data, file.filename)
    try:
        preview = import_service.create_preview(path, file.filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Failed to parse PDF: {exc}") from exc
    return preview


@router.get("/preview/{report_id}")
def get_preview(report_id: int):
    try:
        return import_service.get_preview(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/confirm/{report_id}")
def confirm_import(report_id: int, body: ConfirmImportRequest | None = None):
    include = body.include_review_rows if body else False
    try:
        return import_service.confirm_import(report_id, include_review_rows=include)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
