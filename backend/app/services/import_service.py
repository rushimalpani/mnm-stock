"""Import preview and confirm into SQLite."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.database import UPLOADS_DIR, db_session, init_db
from app.services.normalize import normalize_for_search
from app.services.parsers import parse_stock_pdf


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _filename_key(filename: str) -> str:
    """Normalize for matching: basename, case-insensitive."""
    return Path(filename).name.strip().casefold()


def _unlink_quiet(path: str | Path | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _get_or_create_supplier(conn, name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    row = conn.execute("SELECT id FROM suppliers WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO suppliers (name) VALUES (?)", (name,))
    return cur.lastrowid


def _get_or_create_product(conn, row: dict) -> int:
    design_number = row.get("design_number")
    category = row.get("category") or "unknown"
    # Prefer stable design label (without colour/size) so variants share one product
    original = row.get("design_name") or row.get("original_product_text") or ""
    normalized = (row.get("design_name") or row.get("normalized_name") or "").lower()

    if design_number:
        existing = conn.execute(
            """
            SELECT id FROM products
            WHERE design_number = ? AND category = ?
            """,
            (design_number, category),
        ).fetchone()
        if existing:
            return existing["id"]
    else:
        existing = conn.execute(
            """
            SELECT id FROM products
            WHERE IFNULL(design_number, '') = ''
              AND normalized_name = ?
              AND category = ?
            """,
            (normalized, category),
        ).fetchone()
        if existing:
            return existing["id"]

    cur = conn.execute(
        """
        INSERT INTO products (design_number, original_name, normalized_name, category)
        VALUES (?, ?, ?, ?)
        """,
        (design_number, original, normalized, category),
    )
    return cur.lastrowid


def _get_or_create_variant(conn, product_id: int, row: dict) -> int:
    item_code = row.get("item_code")
    colour = row.get("colour")
    size = row.get("size")
    original_variant = row.get("original_product_text") or ""
    existing = conn.execute(
        """
        SELECT id FROM variants
        WHERE product_id = ?
          AND IFNULL(item_code, '') = IFNULL(?, '')
          AND IFNULL(colour, '') = IFNULL(?, '')
          AND IFNULL(size, '') = IFNULL(?, '')
          AND original_variant_name = ?
        """,
        (product_id, item_code, colour, size, original_variant),
    ).fetchone()
    if existing:
        return existing["id"]
    cur = conn.execute(
        """
        INSERT INTO variants (product_id, item_code, colour, size, original_variant_name)
        VALUES (?, ?, ?, ?, ?)
        """,
        (product_id, item_code, colour, size, original_variant),
    )
    return cur.lastrowid


def _upsert_search_index(conn, *, design_number, design_name, normalized_name, colour, size, item_code, supplier, category):
    conn.execute(
        """
        INSERT INTO search_index (
            design_number, design_name, normalized_name, colour, size, item_code, supplier, category
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            normalize_for_search(design_number),
            normalize_for_search(design_name),
            normalize_for_search(normalized_name),
            normalize_for_search(colour),
            normalize_for_search(size),
            normalize_for_search(item_code),
            normalize_for_search(supplier),
            normalize_for_search(category),
        ),
    )


def _find_reports_same_filename(conn, filename: str) -> list:
    key = _filename_key(filename)
    rows = conn.execute(
        "SELECT id, filename, stored_path FROM reports ORDER BY id ASC"
    ).fetchall()
    return [r for r in rows if _filename_key(r["filename"]) == key]


def _purge_report_children(conn, report_id: int) -> None:
    conn.execute("DELETE FROM stock_snapshots WHERE report_id = ?", (report_id,))
    conn.execute("DELETE FROM import_previews WHERE report_id = ?", (report_id,))


def _same_file(a: Path, b: Path) -> bool:
    try:
        if a.exists() and b.exists():
            return a.samefile(b)
    except OSError:
        pass
    try:
        return a.resolve().as_posix().casefold() == b.resolve().as_posix().casefold()
    except OSError:
        return False


def save_upload(file_bytes: bytes, filename: str) -> Path:
    init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name
    # Microseconds avoid collisions; keep original casing only in DB filename field
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = UPLOADS_DIR / f"{stamp}_{safe}"
    dest.write_bytes(file_bytes)
    return dest


def create_preview(stored_path: Path, original_filename: str) -> dict[str, Any]:
    """Parse PDF into a preview.

    Same original filename (case-insensitive) replaces the previous report of
    that name: stock data is cleared, old PDF file is deleted, report id reused.
    Different filenames keep separate reports.
    """
    init_db()
    result = parse_stock_pdf(stored_path)
    replaced = False
    old_paths: list[str] = []

    with db_session() as conn:
        supplier_id = _get_or_create_supplier(conn, result.supplier)
        same = _find_reports_same_filename(conn, original_filename)

        if same:
            replaced = True
            keep = same[-1]
            for r in same[:-1]:
                old_paths.append(r["stored_path"])
                _purge_report_children(conn, r["id"])
                conn.execute("DELETE FROM reports WHERE id = ?", (r["id"],))

            old_paths.append(keep["stored_path"])
            _purge_report_children(conn, keep["id"])
            conn.execute(
                """
                UPDATE reports SET
                    filename = ?,
                    stored_path = ?,
                    report_date = ?,
                    category = ?,
                    supplier_id = ?,
                    uploaded_at = ?,
                    total_pages = ?,
                    total_rows = ?,
                    rows_parsed = ?,
                    rows_review = ?,
                    status = 'preview',
                    notes = ?
                WHERE id = ?
                """,
                (
                    original_filename,
                    str(stored_path),
                    result.report_date,
                    result.category,
                    supplier_id,
                    _utcnow(),
                    result.total_pages,
                    len(result.rows),
                    result.rows_parsed,
                    result.rows_review,
                    "; ".join(result.warnings) if result.warnings else None,
                    keep["id"],
                ),
            )
            report_id = keep["id"]
        else:
            cur = conn.execute(
                """
                INSERT INTO reports (
                    filename, stored_path, report_date, category, supplier_id,
                    uploaded_at, total_pages, total_rows, rows_parsed, rows_review, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'preview', ?)
                """,
                (
                    original_filename,
                    str(stored_path),
                    result.report_date,
                    result.category,
                    supplier_id,
                    _utcnow(),
                    result.total_pages,
                    len(result.rows),
                    result.rows_parsed,
                    result.rows_review,
                    "; ".join(result.warnings) if result.warnings else None,
                ),
            )
            report_id = cur.lastrowid

        for idx, row in enumerate(result.rows):
            payload = row.to_dict()
            conn.execute(
                """
                INSERT INTO import_previews (report_id, row_index, payload_json, needs_review, review_notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    idx,
                    json.dumps(payload),
                    1 if row.needs_review else 0,
                    "; ".join(row.review_notes),
                ),
            )

    # Free disk: remove previous PDF(s) for this filename (not the new file)
    for p in old_paths:
        op = Path(p)
        if _same_file(op, stored_path):
            continue
        _unlink_quiet(op)

    sample = [r.to_dict() for r in result.rows[:25]]
    return {
        "report_id": report_id,
        "filename": original_filename,
        "report_date": result.report_date,
        "category": result.category,
        "supplier": result.supplier,
        "pages": result.total_pages,
        "rows_detected": len(result.rows),
        "rows_parsed": result.rows_parsed,
        "rows_review": result.rows_review,
        "extraction_method": result.extraction_method,
        "warnings": result.warnings,
        "sample_rows": sample,
        "status": "preview",
        "replaced": replaced,
    }


def get_preview(report_id: int) -> dict[str, Any]:
    with db_session() as conn:
        report = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not report:
            raise ValueError("Report not found")
        supplier = None
        if report["supplier_id"]:
            s = conn.execute("SELECT name FROM suppliers WHERE id = ?", (report["supplier_id"],)).fetchone()
            supplier = s["name"] if s else None
        previews = conn.execute(
            "SELECT * FROM import_previews WHERE report_id = ? ORDER BY row_index",
            (report_id,),
        ).fetchall()
        rows = [json.loads(p["payload_json"]) for p in previews]
    return {
        "report_id": report_id,
        "filename": report["filename"],
        "report_date": report["report_date"],
        "category": report["category"],
        "supplier": supplier,
        "pages": report["total_pages"],
        "rows_detected": report["total_rows"],
        "rows_parsed": report["rows_parsed"],
        "rows_review": report["rows_review"],
        "warnings": [report["notes"]] if report["notes"] else [],
        "sample_rows": rows[:50],
        "all_rows": rows,
        "status": report["status"],
        "replaced": False,
    }


def confirm_import(report_id: int, include_review_rows: bool = False) -> dict[str, Any]:
    """Insert preview rows as stock snapshots for this report."""
    with db_session() as conn:
        report = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not report:
            raise ValueError("Report not found")
        if report["status"] == "imported":
            return {
                "report_id": report_id,
                "status": "imported",
                "imported_rows": report["rows_parsed"] or 0,
                "skipped_review_rows": report["rows_review"] or 0,
                "message": "Already imported",
            }

        supplier_name = None
        if report["supplier_id"]:
            s = conn.execute("SELECT name FROM suppliers WHERE id = ?", (report["supplier_id"],)).fetchone()
            supplier_name = s["name"] if s else None

        previews = conn.execute(
            "SELECT * FROM import_previews WHERE report_id = ? ORDER BY row_index",
            (report_id,),
        ).fetchall()

        imported = 0
        skipped = 0
        for p in previews:
            row = json.loads(p["payload_json"])
            if p["needs_review"] and not include_review_rows:
                skipped += 1
                continue
            product_id = _get_or_create_product(conn, row)
            variant_id = _get_or_create_variant(conn, product_id, row)
            conn.execute(
                """
                INSERT OR IGNORE INTO stock_snapshots (
                    variant_id, report_id, purchase_qty, purchase_rate, purchase_amount,
                    stock_qty, difference, mrp, stock_amount, pdf_page,
                    original_product_text, needs_review, review_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    variant_id,
                    report_id,
                    row.get("purchase_qty"),
                    row.get("purchase_rate"),
                    row.get("purchase_amount"),
                    row.get("stock_qty"),
                    row.get("difference"),
                    row.get("mrp"),
                    row.get("stock_amount"),
                    row.get("pdf_page"),
                    row.get("original_product_text"),
                    1 if row.get("needs_review") else 0,
                    row.get("review_notes"),
                ),
            )
            _upsert_search_index(
                conn,
                design_number=row.get("design_number"),
                design_name=row.get("design_name"),
                normalized_name=row.get("normalized_name"),
                colour=row.get("colour"),
                size=row.get("size"),
                item_code=row.get("item_code"),
                supplier=row.get("supplier") or supplier_name,
                category=row.get("category"),
            )
            imported += 1

        conn.execute(
            "UPDATE reports SET status = 'imported', rows_parsed = ?, rows_review = ? WHERE id = ?",
            (imported, skipped, report_id),
        )

    return {
        "report_id": report_id,
        "status": "imported",
        "imported_rows": imported,
        "skipped_review_rows": skipped,
    }


def list_reports() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT r.*, s.name AS supplier_name
            FROM reports r
            LEFT JOIN suppliers s ON s.id = r.supplier_id
            ORDER BY
                CASE WHEN r.report_date IS NULL THEN 1 ELSE 0 END,
                date(substr(r.report_date, 7, 4) || '-' || substr(r.report_date, 4, 2) || '-' || substr(r.report_date, 1, 2)) DESC,
                r.uploaded_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
