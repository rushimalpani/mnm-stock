from __future__ import annotations

import io
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.database import UPLOADS_DIR, init_db
from app.routers import designs, export, reports, search, upload

app = FastAPI(title="Supplier Stock Search", version="1.0.0")

_cors = os.environ.get("CORS_ORIGINS", "*").strip()
allow_origins = ["*"] if _cors == "*" else [o.strip() for o in _cors.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(search.router)
app.include_router(designs.router)
app.include_router(reports.router)
app.include_router(export.router)

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        # Don't crash boot on transient Atlas TLS — requests will retry connect
        import logging

        logging.getLogger("uvicorn.error").error("MongoDB init failed on startup: %s", exc)


@app.api_route("/", methods=["GET", "HEAD"])
@app.get("/api/health")
def health():
    """Root also serves health so Render's default HEAD / check does not 404."""
    mongo = "unset"
    if os.environ.get("MONGODB_URI"):
        try:
            from app.database import get_client

            get_client().admin.command("ping")
            mongo = "ok"
        except Exception as exc:  # noqa: BLE001
            mongo = f"error:{type(exc).__name__}"
    return {"status": "ok", "mongo": mongo}


@app.get("/api/pdf/{report_id}")
def get_pdf(report_id: int):
    from app import database as db

    row = db.col("reports").find_one({"id": report_id})
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    filename = row.get("filename") or "report.pdf"
    gridfs_id = row.get("gridfs_id")
    if gridfs_id:
        try:
            data = db.read_pdf_bytes(gridfs_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=404, detail="PDF file missing in MongoDB") from exc
        return StreamingResponse(
            io.BytesIO(data),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    path = Path(row.get("stored_path") or "")
    if path.exists():
        from fastapi.responses import FileResponse

        return FileResponse(path, media_type="application/pdf", filename=filename)
    raise HTTPException(status_code=404, detail="PDF file missing on disk")
