"""MongoDB Atlas persistence (stock data + PDF GridFS).

Set MONGODB_URI in the environment. Data survives Render restarts.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.collection import Collection
from pymongo.database import Database
from gridfs import GridFS

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

# Local temp cache for parsing only (ephemeral OK — PDFs live in GridFS)
UPLOADS_DIR = Path(os.environ.get("STOCK_UPLOAD_CACHE", str(_BACKEND_ROOT / "uploads")))
# Kept for any legacy imports / tests that still reference these
DATA_DIR = _BACKEND_ROOT / "data"
DB_PATH = DATA_DIR / "stock.db"

_client: Optional[MongoClient] = None
_db: Optional[Database] = None
_fs: Optional[GridFS] = None


def _uri() -> str:
    uri = (os.environ.get("MONGODB_URI") or "").strip()
    if not uri:
        raise RuntimeError(
            "MONGODB_URI is not set. Add it in Render Environment (or backend/.env locally)."
        )
    return uri


def get_client() -> MongoClient:
    global _client
    if _client is None:
        import certifi

        _client = MongoClient(
            _uri(),
            serverSelectionTimeoutMS=20000,
            connectTimeoutMS=20000,
            tls=True,
            tlsCAFile=certifi.where(),
        )
    return _client


def get_db() -> Database:
    global _db
    if _db is None:
        name = (os.environ.get("MONGODB_DB") or "mnm_stock").strip()
        _db = get_client()[name]
    return _db


def get_fs() -> GridFS:
    global _fs
    if _fs is None:
        _fs = GridFS(get_db(), collection="pdfs")
    return _fs


def col(name: str) -> Collection:
    return get_db()[name]


def next_id(sequence: str) -> int:
    """Integer auto-increment compatible with existing API ids."""
    doc = col("counters").find_one_and_update(
        {"_id": sequence},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


def ensure_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    """Ping Atlas and ensure indexes."""
    ensure_dirs()
    get_client().admin.command("ping")
    db = get_db()
    db.suppliers.create_index("name", unique=True)
    db.suppliers.create_index("id", unique=True)
    db.reports.create_index("id", unique=True)
    db.reports.create_index("filename")
    db.reports.create_index([("status", ASCENDING), ("uploaded_at", ASCENDING)])
    db.products.create_index("id", unique=True)
    db.products.create_index([("design_number", ASCENDING), ("category", ASCENDING)])
    db.variants.create_index("id", unique=True)
    db.variants.create_index([("product_id", ASCENDING), ("item_code", ASCENDING)])
    db.stock_snapshots.create_index("id", unique=True)
    db.stock_snapshots.create_index([("report_id", ASCENDING), ("variant_id", ASCENDING)])
    db.import_previews.create_index([("report_id", ASCENDING), ("row_index", ASCENDING)])


def reset_mongo_for_tests() -> None:
    """Drop app collections (used by pytest with a dedicated test DB)."""
    db = get_db()
    for name in (
        "suppliers",
        "reports",
        "products",
        "variants",
        "stock_snapshots",
        "import_previews",
        "counters",
        "pdfs.files",
        "pdfs.chunks",
    ):
        db[name].drop()
    global _fs
    _fs = None
    init_db()


def store_pdf_bytes(file_bytes: bytes, filename: str) -> str:
    """Save PDF into GridFS; returns hex GridFS file id."""
    file_id = get_fs().put(file_bytes, filename=Path(filename).name, content_type="application/pdf")
    return str(file_id)


def store_pdf_path(path: Path, filename: str) -> str:
    return store_pdf_bytes(path.read_bytes(), filename)


def delete_pdf(gridfs_id: Optional[str]) -> None:
    if not gridfs_id:
        return
    from bson import ObjectId
    from bson.errors import InvalidId

    try:
        oid = ObjectId(gridfs_id)
    except (InvalidId, TypeError):
        return
    fs = get_fs()
    if fs.exists(oid):
        fs.delete(oid)


def read_pdf_bytes(gridfs_id: str) -> bytes:
    from bson import ObjectId

    return get_fs().get(ObjectId(gridfs_id)).read()


def write_pdf_temp(gridfs_id: str, filename: str = "report.pdf") -> Path:
    """Materialize a GridFS PDF to a temp file for FileResponse / local tools."""
    ensure_dirs()
    data = read_pdf_bytes(gridfs_id)
    dest = Path(tempfile.mkdtemp(prefix="mnm_pdf_", dir=str(UPLOADS_DIR))) / Path(filename).name
    dest.write_bytes(data)
    return dest


def find_one(collection: str, query: dict) -> Optional[dict[str, Any]]:
    doc = col(collection).find_one(query)
    return dict(doc) if doc else None


def find_many(collection: str, query: dict | None = None, sort=None) -> list[dict[str, Any]]:
    cur = col(collection).find(query or {})
    if sort:
        cur = cur.sort(sort)
    return [dict(d) for d in cur]
