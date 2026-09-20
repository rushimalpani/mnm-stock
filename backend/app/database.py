"""SQLite database connection and schema initialization."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
# On Render, set STOCK_DATA_DIR=/data (persistent disk) so DB/uploads survive restarts
_DATA_ROOT = Path(os.environ.get("STOCK_DATA_DIR", str(_BACKEND_ROOT)))
DATA_DIR = _DATA_ROOT / "data" if _DATA_ROOT == _BACKEND_ROOT else _DATA_ROOT
UPLOADS_DIR = (
    _BACKEND_ROOT / "uploads"
    if _DATA_ROOT == _BACKEND_ROOT
    else _DATA_ROOT / "uploads"
)
DB_PATH = DATA_DIR / "stock.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    report_date TEXT,
    category TEXT NOT NULL CHECK(category IN ('fashion', 'jewellery', 'mixed', 'unknown')),
    supplier_id INTEGER REFERENCES suppliers(id),
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    total_pages INTEGER DEFAULT 0,
    total_rows INTEGER DEFAULT 0,
    rows_parsed INTEGER DEFAULT 0,
    rows_review INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'preview', 'imported', 'failed')),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    design_number TEXT,
    original_name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('fashion', 'jewellery', 'unknown')),
    UNIQUE(design_number, normalized_name, category)
);

CREATE TABLE IF NOT EXISTS variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    item_code TEXT,
    colour TEXT,
    size TEXT,
    original_variant_name TEXT NOT NULL,
    UNIQUE(product_id, item_code, colour, size, original_variant_name)
);

CREATE TABLE IF NOT EXISTS stock_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variant_id INTEGER NOT NULL REFERENCES variants(id),
    report_id INTEGER NOT NULL REFERENCES reports(id),
    purchase_qty REAL,
    purchase_rate REAL,
    purchase_amount REAL,
    stock_qty REAL,
    difference REAL,
    mrp REAL,
    stock_amount REAL,
    pdf_page INTEGER,
    original_product_text TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_notes TEXT,
    UNIQUE(variant_id, report_id, pdf_page)
);

CREATE TABLE IF NOT EXISTS import_previews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_notes TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    design_number,
    design_name,
    normalized_name,
    colour,
    size,
    item_code,
    supplier,
    category,
    content='',
    tokenize='porter unicode61'
);
"""


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    ensure_dirs()
    with db_session() as conn:
        conn.executescript(SCHEMA)
