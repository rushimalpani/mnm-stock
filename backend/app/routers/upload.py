from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from app.schemas import ConfirmImportRequest
from app.services import import_service
from app import database as db

router = APIRouter(prefix="/api/upload", tags=["upload"])
log = logging.getLogger("uvicorn.error")


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


@router.get("/confirm/{report_id}/status")
def confirm_status(report_id: int):
    report = db.col("reports").find_one({"id": report_id}, {"status": 1, "rows_parsed": 1, "rows_review": 1, "notes": 1})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        "report_id": report_id,
        "status": report.get("status"),
        "imported_rows": report.get("rows_parsed") or 0,
        "skipped_review_rows": report.get("rows_review") or 0,
        "message": report.get("notes"),
    }


def _run_confirm_job(report_id: int, include_review_rows: bool) -> None:
    try:
        import_service.confirm_import(
            report_id,
            include_review_rows=include_review_rows,
            resume=True,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Background confirm failed for report %s: %s", report_id, exc)


@router.post("/confirm/{report_id}")
def confirm_import(
    report_id: int,
    background_tasks: BackgroundTasks,
    body: ConfirmImportRequest | None = None,
):
    """Start save in the background so Render does not 502 on large PDFs."""
    include = body.include_review_rows if body else False
    report = db.col("reports").find_one({"id": report_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if report.get("status") == "imported":
        return {
            "report_id": report_id,
            "status": "imported",
            "imported_rows": report.get("rows_parsed") or 0,
            "skipped_review_rows": report.get("rows_review") or 0,
            "message": "Already imported",
        }

    if report.get("status") == "importing":
        return {
            "report_id": report_id,
            "status": "importing",
            "imported_rows": 0,
            "skipped_review_rows": 0,
            "message": "Save already in progress",
        }

    # Small reports: finish inline (faster UX). Large: background to avoid proxy 502.
    rows = int(report.get("total_rows") or 0)
    if rows <= 400:
        try:
            return import_service.confirm_import(report_id, include_review_rows=include)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Save failed: {exc}") from exc

    db.col("reports").update_one({"id": report_id}, {"$set": {"status": "importing"}})
    background_tasks.add_task(_run_confirm_job, report_id, include)
    return {
        "report_id": report_id,
        "status": "importing",
        "imported_rows": 0,
        "skipped_review_rows": 0,
        "message": "Save started in background",
    }
