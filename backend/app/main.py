from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import UPLOADS_DIR, init_db
from app.routers import designs, export, reports, search, upload

app = FastAPI(title="Supplier Stock Search", version="1.0.0")

# Comma-separated list, e.g. https://mnm-stock.vercel.app,http://localhost:5173
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
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/pdf/{report_id}")
def get_pdf(report_id: int):
    from app.database import db_session

    with db_session() as conn:
        row = conn.execute("SELECT stored_path, filename FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Report not found")
        path = Path(row["stored_path"])
        if not path.exists():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="PDF file missing on disk")
        return FileResponse(path, media_type="application/pdf", filename=row["filename"])
