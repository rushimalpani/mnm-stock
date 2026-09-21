"""Import preview and confirm into MongoDB Atlas."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app import database as db
from app.services.normalize import normalize_for_search
from app.services.parsers import parse_stock_pdf

UPLOADS_DIR = db.UPLOADS_DIR


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _filename_key(filename: str) -> str:
    return Path(filename).name.strip().casefold()


def _unlink_quiet(path: str | Path | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _get_or_create_supplier(name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    existing = db.col("suppliers").find_one({"name": name})
    if existing:
        return int(existing["id"])
    sid = db.next_id("suppliers")
    db.col("suppliers").insert_one({"id": sid, "name": name})
    return sid


def _get_or_create_product(row: dict, cache: Optional[dict] = None) -> int:
    design_number = row.get("design_number")
    category = row.get("category") or "unknown"
    item_code = row.get("item_code")
    original = row.get("design_name") or row.get("original_product_text") or ""
    normalized = (row.get("design_name") or row.get("normalized_name") or "").lower()
    cache = cache if cache is not None else {}

    design_key = (str(design_number or ""), category)
    if design_number and design_key in cache.get("by_design", {}):
        return cache["by_design"][design_key]
    if item_code and (item_code, category) in cache.get("by_item_product", {}):
        return cache["by_item_product"][(item_code, category)]

    if item_code:
        variant = db.col("variants").find_one({"item_code": item_code}, sort=[("id", -1)])
        if variant:
            product = db.col("products").find_one({"id": variant["product_id"], "category": category})
            if product:
                db.col("products").update_one(
                    {"id": product["id"]},
                    {
                        "$set": {
                            "design_number": design_number,
                            "original_name": original,
                            "normalized_name": normalized,
                        }
                    },
                )
                pid = int(product["id"])
                cache.setdefault("by_design", {})[design_key] = pid
                cache.setdefault("by_item_product", {})[(item_code, category)] = pid
                return pid

    if design_number:
        existing = db.col("products").find_one(
            {"design_number": design_number, "category": category}
        )
        if existing:
            pid = int(existing["id"])
            cache.setdefault("by_design", {})[design_key] = pid
            return pid
    else:
        existing = db.col("products").find_one(
            {
                "$or": [{"design_number": None}, {"design_number": ""}],
                "normalized_name": normalized,
                "category": category,
            }
        )
        if existing:
            return int(existing["id"])

    pid = db.next_id("products")
    db.col("products").insert_one(
        {
            "id": pid,
            "design_number": design_number,
            "original_name": original,
            "normalized_name": normalized,
            "category": category,
        }
    )
    cache.setdefault("by_design", {})[design_key] = pid
    if item_code:
        cache.setdefault("by_item_product", {})[(item_code, category)] = pid
    return pid


def _get_or_create_variant(product_id: int, row: dict, cache: Optional[dict] = None) -> int:
    item_code = row.get("item_code")
    colour = row.get("colour")
    size = row.get("size")
    original_variant = row.get("original_product_text") or ""
    cache = cache if cache is not None else {}
    vkey = (product_id, item_code or "", colour or "", size or "")
    if vkey in cache.get("variants", {}):
        return cache["variants"][vkey]

    if item_code:
        existing = db.col("variants").find_one(
            {"product_id": product_id, "item_code": item_code}
        )
        if existing:
            db.col("variants").update_one(
                {"id": existing["id"]},
                {
                    "$set": {
                        "colour": colour,
                        "size": size,
                        "original_variant_name": original_variant,
                    }
                },
            )
            vid = int(existing["id"])
            cache.setdefault("variants", {})[vkey] = vid
            return vid

    existing = db.col("variants").find_one(
        {
            "product_id": product_id,
            "item_code": item_code,
            "colour": colour,
            "size": size,
            "original_variant_name": original_variant,
        }
    )
    if existing:
        vid = int(existing["id"])
        cache.setdefault("variants", {})[vkey] = vid
        return vid

    vid = db.next_id("variants")
    db.col("variants").insert_one(
        {
            "id": vid,
            "product_id": product_id,
            "item_code": item_code,
            "colour": colour,
            "size": size,
            "original_variant_name": original_variant,
        }
    )
    cache.setdefault("variants", {})[vkey] = vid
    return vid


def _find_reports_same_filename(filename: str) -> list[dict]:
    key = _filename_key(filename)
    return [
        r
        for r in db.col("reports").find().sort("id", 1)
        if _filename_key(r.get("filename") or "") == key
    ]


def _purge_report_children(report_id: int) -> None:
    db.col("stock_snapshots").delete_many({"report_id": report_id})
    db.col("import_previews").delete_many({"report_id": report_id})


def _delete_report_pdf(report: dict) -> None:
    grid_id = report.get("gridfs_id")
    if grid_id:
        db.delete_pdf(grid_id)
    stored = report.get("stored_path")
    if stored and not str(stored).startswith("gridfs:"):
        _unlink_quiet(stored)


def save_upload(file_bytes: bytes, filename: str) -> Path:
    """Write a local temp copy for parsing; GridFS upload happens in create_preview."""
    db.init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = UPLOADS_DIR / f"{stamp}_{safe}"
    dest.write_bytes(file_bytes)
    return dest


def create_preview(stored_path: Path, original_filename: str) -> dict[str, Any]:
    """Parse PDF into a preview and persist metadata + PDF in MongoDB/GridFS."""
    db.init_db()
    result = parse_stock_pdf(stored_path)
    replaced = False
    gridfs_id = db.store_pdf_path(stored_path, original_filename)

    supplier_id = _get_or_create_supplier(result.supplier)
    same = _find_reports_same_filename(original_filename)

    report_doc = {
        "filename": original_filename,
        "stored_path": f"gridfs:{gridfs_id}",
        "gridfs_id": gridfs_id,
        "report_date": result.report_date,
        "category": result.category,
        "supplier_id": supplier_id,
        "uploaded_at": _utcnow(),
        "total_pages": result.total_pages,
        "total_rows": len(result.rows),
        "rows_parsed": result.rows_parsed,
        "rows_review": result.rows_review,
        "status": "preview",
        "notes": "; ".join(result.warnings) if result.warnings else None,
    }

    if same:
        replaced = True
        keep = same[-1]
        for r in same[:-1]:
            _purge_report_children(int(r["id"]))
            _delete_report_pdf(r)
            db.col("reports").delete_one({"id": r["id"]})

        _purge_report_children(int(keep["id"]))
        _delete_report_pdf(keep)
        db.col("reports").update_one({"id": keep["id"]}, {"$set": report_doc})
        report_id = int(keep["id"])
    else:
        report_id = db.next_id("reports")
        report_doc["id"] = report_id
        db.col("reports").insert_one(report_doc)

    preview_docs = []
    if result.rows:
        ids = db.next_ids("import_previews", len(result.rows))
        for idx, (row, pid) in enumerate(zip(result.rows, ids)):
            preview_docs.append(
                {
                    "id": pid,
                    "report_id": report_id,
                    "row_index": idx,
                    "payload_json": json.dumps(row.to_dict()),
                    "needs_review": 1 if row.needs_review else 0,
                    "review_notes": "; ".join(row.review_notes),
                }
            )
        # Chunked insert keeps payload under Atlas/document limits
        chunk = 500
        for i in range(0, len(preview_docs), chunk):
            db.col("import_previews").insert_many(preview_docs[i : i + chunk])

    # Drop ephemeral upload-cache copies; keep caller temp/sample files
    try:
        if stored_path.resolve().is_relative_to(UPLOADS_DIR.resolve()):
            _unlink_quiet(stored_path)
    except (OSError, ValueError, AttributeError):
        # Python <3.9 fallback / path edge cases
        try:
            if str(stored_path.resolve()).startswith(str(UPLOADS_DIR.resolve())):
                _unlink_quiet(stored_path)
        except OSError:
            pass

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
    report = db.col("reports").find_one({"id": report_id})
    if not report:
        raise ValueError("Report not found")
    supplier = None
    if report.get("supplier_id"):
        s = db.col("suppliers").find_one({"id": report["supplier_id"]})
        supplier = s["name"] if s else None
    previews = list(
        db.col("import_previews").find({"report_id": report_id}).sort("row_index", 1)
    )
    rows = [json.loads(p["payload_json"]) for p in previews]
    return {
        "report_id": report_id,
        "filename": report["filename"],
        "report_date": report.get("report_date"),
        "category": report["category"],
        "supplier": supplier,
        "pages": report.get("total_pages"),
        "rows_detected": report.get("total_rows"),
        "rows_parsed": report.get("rows_parsed"),
        "rows_review": report.get("rows_review"),
        "warnings": [report["notes"]] if report.get("notes") else [],
        "sample_rows": rows[:50],
        "all_rows": rows,
        "status": report["status"],
        "replaced": False,
    }


def confirm_import(report_id: int, include_review_rows: bool = False) -> dict[str, Any]:
    report = db.col("reports").find_one({"id": report_id})
    if not report:
        raise ValueError("Report not found")
    if report["status"] == "imported":
        return {
            "report_id": report_id,
            "status": "imported",
            "imported_rows": report.get("rows_parsed") or 0,
            "skipped_review_rows": report.get("rows_review") or 0,
            "message": "Already imported",
        }

    supplier_name = None
    if report.get("supplier_id"):
        s = db.col("suppliers").find_one({"id": report["supplier_id"]})
        supplier_name = s["name"] if s else None

    previews = list(
        db.col("import_previews").find({"report_id": report_id}).sort("row_index", 1)
    )

    rows: list[dict] = []
    skipped = 0
    for p in previews:
        row = json.loads(p["payload_json"])
        if p.get("needs_review") and not include_review_rows:
            skipped += 1
            continue
        rows.append(row)

    # --- Bulk resolve products (few queries instead of one per row) ---
    design_keys = {
        (str(r.get("design_number") or ""), r.get("category") or "unknown")
        for r in rows
        if r.get("design_number")
    }
    categories = list({k[1] for k in design_keys}) or ["unknown"]
    design_numbers = [k[0] for k in design_keys if k[0]]

    product_by_design: dict[tuple[str, str], int] = {}
    if design_numbers:
        for p in db.col("products").find(
            {"design_number": {"$in": design_numbers}, "category": {"$in": categories}}
        ):
            product_by_design[(str(p.get("design_number") or ""), p.get("category") or "unknown")] = int(
                p["id"]
            )

    missing_products = []
    seen_missing: set[tuple[str, str]] = set()
    for r in rows:
        dn = str(r.get("design_number") or "")
        cat = r.get("category") or "unknown"
        key = (dn, cat)
        if dn and key not in product_by_design and key not in seen_missing:
            seen_missing.add(key)
            missing_products.append(r)

    if missing_products:
        # One row per design key
        unique_missing = []
        seen: set[tuple[str, str]] = set()
        for r in missing_products:
            key = (str(r.get("design_number") or ""), r.get("category") or "unknown")
            if key in seen:
                continue
            seen.add(key)
            unique_missing.append(r)
        ids = db.next_ids("products", len(unique_missing))
        docs = []
        for r, pid in zip(unique_missing, ids):
            dn = r.get("design_number")
            cat = r.get("category") or "unknown"
            original = r.get("design_name") or r.get("original_product_text") or ""
            normalized = (r.get("design_name") or r.get("normalized_name") or "").lower()
            docs.append(
                {
                    "id": pid,
                    "design_number": dn,
                    "original_name": original,
                    "normalized_name": normalized,
                    "category": cat,
                }
            )
            product_by_design[(str(dn or ""), cat)] = pid
        if docs:
            db.col("products").insert_many(docs)

    # Map each row → product_id
    row_product_ids: list[int] = []
    cache: dict = {"by_design": dict(product_by_design), "by_item_product": {}, "variants": {}}
    for r in rows:
        dn = str(r.get("design_number") or "")
        cat = r.get("category") or "unknown"
        if dn and (dn, cat) in product_by_design:
            row_product_ids.append(product_by_design[(dn, cat)])
        else:
            row_product_ids.append(_get_or_create_product(r, cache))

    # --- Bulk resolve variants ---
    item_codes = [r.get("item_code") for r in rows if r.get("item_code")]
    variant_by_product_item: dict[tuple[int, str], int] = {}
    if item_codes:
        for v in db.col("variants").find({"item_code": {"$in": item_codes}}):
            variant_by_product_item[(int(v["product_id"]), str(v.get("item_code") or ""))] = int(v["id"])

    # Update colour/size for existing variants in one pass (optional light touch)
    missing_variants: list[tuple[int, dict]] = []
    row_variant_ids: list[int] = []
    seen_new_variant: set[tuple[int, str]] = set()
    for r, pid in zip(rows, row_product_ids):
        ic = str(r.get("item_code") or "")
        key = (pid, ic)
        if ic and key in variant_by_product_item:
            row_variant_ids.append(variant_by_product_item[key])
        elif ic and key not in seen_new_variant:
            seen_new_variant.add(key)
            missing_variants.append((pid, r))
            row_variant_ids.append(-1)  # placeholder
        elif ic:
            # already queued
            row_variant_ids.append(-1)
        else:
            row_variant_ids.append(_get_or_create_variant(pid, r, cache))

    if missing_variants:
        ids = db.next_ids("variants", len(missing_variants))
        docs = []
        for (pid, r), vid in zip(missing_variants, ids):
            ic = str(r.get("item_code") or "")
            docs.append(
                {
                    "id": vid,
                    "product_id": pid,
                    "item_code": r.get("item_code"),
                    "colour": r.get("colour"),
                    "size": r.get("size"),
                    "original_variant_name": r.get("original_product_text") or "",
                }
            )
            variant_by_product_item[(pid, ic)] = vid
        if docs:
            db.col("variants").insert_many(docs)

    # Fill placeholders
    fixed_variant_ids = []
    for r, pid, vid in zip(rows, row_product_ids, row_variant_ids):
        if vid != -1:
            fixed_variant_ids.append(vid)
        else:
            ic = str(r.get("item_code") or "")
            fixed_variant_ids.append(variant_by_product_item[(pid, ic)])

    existing = {
        (int(s["variant_id"]), s.get("pdf_page"))
        for s in db.col("stock_snapshots").find(
            {"report_id": report_id}, {"variant_id": 1, "pdf_page": 1}
        )
    }
    to_insert = []
    imported_existing = 0
    for r, vid in zip(rows, fixed_variant_ids):
        key = (int(vid), r.get("pdf_page"))
        if key in existing:
            imported_existing += 1
            continue
        to_insert.append((vid, r))

    snapshot_docs = []
    if to_insert:
        ids = db.next_ids("stock_snapshots", len(to_insert))
        for (variant_id, row), sid in zip(to_insert, ids):
            snapshot_docs.append(
                {
                    "id": sid,
                    "variant_id": variant_id,
                    "report_id": report_id,
                    "purchase_qty": row.get("purchase_qty"),
                    "purchase_rate": row.get("purchase_rate"),
                    "purchase_amount": row.get("purchase_amount"),
                    "stock_qty": row.get("stock_qty"),
                    "difference": row.get("difference"),
                    "mrp": row.get("mrp"),
                    "stock_amount": row.get("stock_amount"),
                    "pdf_page": row.get("pdf_page"),
                    "original_product_text": row.get("original_product_text"),
                    "needs_review": 1 if row.get("needs_review") else 0,
                    "review_notes": row.get("review_notes"),
                    "supplier": row.get("supplier") or supplier_name,
                    "category": row.get("category"),
                    "design_number": row.get("design_number"),
                    "design_name": row.get("design_name"),
                    "normalized_name": row.get("normalized_name"),
                    "colour": row.get("colour"),
                    "size": row.get("size"),
                    "item_code": row.get("item_code"),
                }
            )
        chunk = 500
        for i in range(0, len(snapshot_docs), chunk):
            db.col("stock_snapshots").insert_many(snapshot_docs[i : i + chunk])

    imported = imported_existing + len(snapshot_docs)

    db.col("reports").update_one(
        {"id": report_id},
        {"$set": {"status": "imported", "rows_parsed": imported, "rows_review": skipped}},
    )

    return {
        "report_id": report_id,
        "status": "imported",
        "imported_rows": imported,
        "skipped_review_rows": skipped,
    }


def _report_sort_key(r: dict) -> tuple:
    rd = r.get("report_date") or ""
    # dd/mm/yyyy → yyyymmdd for sort; empty last
    if len(rd) >= 10 and rd[2] == "/" and rd[5] == "/":
        iso = f"{rd[6:10]}{rd[3:5]}{rd[0:2]}"
        empty = 0
    else:
        iso = rd
        empty = 1
    return (empty, iso, r.get("uploaded_at") or "")


def list_reports() -> list[dict[str, Any]]:
    rows = list(db.col("reports").find())
    suppliers = {s["id"]: s["name"] for s in db.col("suppliers").find()}
    out = []
    for r in rows:
        d = dict(r)
        d.pop("_id", None)
        d["supplier_name"] = suppliers.get(r.get("supplier_id"))
        out.append(d)
    out.sort(key=_report_sort_key, reverse=True)
    return out


# Back-compat alias used by older tests
def init_db() -> None:
    db.init_db()
