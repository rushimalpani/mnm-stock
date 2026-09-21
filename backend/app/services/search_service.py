"""Search and filter stock across MongoDB snapshots."""
from __future__ import annotations

from typing import Any, Optional

from app import database as db
from app.services.normalize import normalize_for_search

LOW_STOCK_THRESHOLD = 5


def _latest_report_id() -> Optional[int]:
    rows = list(db.col("reports").find({"status": "imported"}))
    if not rows:
        return None
    from app.services.import_service import _report_sort_key

    rows.sort(key=_report_sort_key, reverse=True)
    return int(rows[0]["id"])


def _supplier_map() -> dict[int, str]:
    return {int(s["id"]): s["name"] for s in db.col("suppliers").find()}


def _load_search_rows(
    *,
    effective_report_id: Optional[int],
    category: Optional[str],
    supplier: Optional[str],
    design_number: Optional[str],
    size: Optional[str],
    stock_status: Optional[str],
) -> list[dict[str, Any]]:
    report_q: dict[str, Any] = {"status": "imported"}
    if effective_report_id:
        report_q["id"] = effective_report_id
    reports = {int(r["id"]): r for r in db.col("reports").find(report_q)}
    if not reports:
        return []

    suppliers = _supplier_map()
    if supplier:
        needle = supplier.lower()
        allowed_sids = {sid for sid, name in suppliers.items() if needle in name.lower()}
        reports = {
            rid: r
            for rid, r in reports.items()
            if r.get("supplier_id") in allowed_sids
        }
        if not reports:
            return []

    snap_q: dict[str, Any] = {"report_id": {"$in": list(reports.keys())}}
    if stock_status == "in_stock":
        snap_q["stock_qty"] = {"$gt": LOW_STOCK_THRESHOLD}
    elif stock_status == "low_stock":
        snap_q["stock_qty"] = {"$gt": 0, "$lte": LOW_STOCK_THRESHOLD}
    elif stock_status == "out_of_stock":
        snap_q["$or"] = [{"stock_qty": {"$lte": 0}}, {"stock_qty": None}]

    snapshots = list(db.col("stock_snapshots").find(snap_q))
    if not snapshots:
        return []

    variant_ids = list({int(s["variant_id"]) for s in snapshots})
    variants = {int(v["id"]): v for v in db.col("variants").find({"id": {"$in": variant_ids}})}
    product_ids = list({int(v["product_id"]) for v in variants.values()})
    products = {int(p["id"]): p for p in db.col("products").find({"id": {"$in": product_ids}})}

    rows: list[dict[str, Any]] = []
    for ss in snapshots:
        v = variants.get(int(ss["variant_id"]))
        if not v:
            continue
        p = products.get(int(v["product_id"]))
        if not p:
            continue
        if category and p.get("category") != category:
            continue
        if design_number and p.get("design_number") != design_number:
            continue
        if size and size.lower() not in (v.get("size") or "").lower():
            continue
        r = reports.get(int(ss["report_id"]))
        if not r:
            continue
        rows.append(
            {
                "product_id": p["id"],
                "design_number": p.get("design_number"),
                "original_name": p.get("original_name"),
                "normalized_name": p.get("normalized_name"),
                "category": p.get("category"),
                "variant_id": v["id"],
                "item_code": v.get("item_code"),
                "colour": v.get("colour"),
                "size": v.get("size"),
                "original_variant_name": v.get("original_variant_name"),
                "snapshot_id": ss["id"],
                "stock_qty": ss.get("stock_qty"),
                "mrp": ss.get("mrp"),
                "purchase_qty": ss.get("purchase_qty"),
                "purchase_rate": ss.get("purchase_rate"),
                "purchase_amount": ss.get("purchase_amount"),
                "difference": ss.get("difference"),
                "stock_amount": ss.get("stock_amount"),
                "pdf_page": ss.get("pdf_page"),
                "original_product_text": ss.get("original_product_text"),
                "needs_review": ss.get("needs_review"),
                "report_id": r["id"],
                "filename": r.get("filename"),
                "report_date": r.get("report_date"),
                "supplier_name": suppliers.get(r.get("supplier_id")),
            }
        )
    return rows


def search_stock(
    query: str = "",
    *,
    report_id: Optional[int] = None,
    latest: bool = True,
    category: Optional[str] = None,
    supplier: Optional[str] = None,
    design_number: Optional[str] = None,
    colour: Optional[str] = None,
    size: Optional[str] = None,
    stock_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    q_norm = normalize_for_search(query)
    colour_filter = colour or None
    query_tokens = q_norm.split() if q_norm else []
    page = max(1, int(page or 1))
    page_size = min(50, max(1, int(page_size or 10)))

    effective_report_id = report_id
    if effective_report_id is None and latest:
        effective_report_id = _latest_report_id()

    rows = _load_search_rows(
        effective_report_id=effective_report_id,
        category=category,
        supplier=supplier,
        design_number=design_number,
        size=size,
        stock_status=stock_status,
    )

    def design_blob(r: dict) -> str:
        return normalize_for_search(
            " ".join(
                str(x or "")
                for x in (
                    r.get("design_number"),
                    r.get("original_name"),
                    r.get("normalized_name"),
                )
            )
        )

    filtered = rows
    if query_tokens:

        def matches(r: dict) -> bool:
            dn = str(r.get("design_number") or "")
            name_norm = normalize_for_search(
                " ".join(str(x or "") for x in (r.get("original_name"), r.get("normalized_name")))
            )
            blob = design_blob(r)
            if len(query_tokens) == 1 and query_tokens[0].isdigit():
                return dn == query_tokens[0]
            if query_tokens[0].isdigit():
                if dn != query_tokens[0]:
                    return False
                return all(tok in name_norm for tok in query_tokens[1:])
            return all(tok in blob for tok in query_tokens)

        filtered = [r for r in filtered if matches(r)]

    colour_missing_message = None
    effective_colour = (colour_filter or "").strip().lower()
    if effective_colour:
        colour_norm = normalize_for_search(effective_colour)
        design_rows = filtered
        colour_matches = [
            r
            for r in filtered
            if colour_norm in normalize_for_search(r.get("colour") or "")
        ]
        if design_rows and not colour_matches:
            colour_missing_message = "No matching colour available in this report."
            filtered = []
        else:
            filtered = colour_matches

    groups: dict[str, dict[str, Any]] = {}
    seen_variant_keys: dict[str, tuple[int, int]] = {}

    def _row_rank(r: dict) -> tuple:
        return (
            str(r.get("report_date") or ""),
            int(r.get("report_id") or 0),
            int(r.get("snapshot_id") or 0),
        )

    for r in filtered:
        cat = r.get("category") or "unknown"
        dn = r.get("design_number")
        item_code = r.get("item_code")
        key = f"{cat}::{dn or r.get('product_id')}"
        item_key = (
            f"{key}::"
            f"{item_code or r.get('variant_id')}::"
            f"{r.get('colour') or ''}::{r.get('size') or ''}"
        )
        variant_payload = {
            "variant_id": r["variant_id"],
            "snapshot_id": r["snapshot_id"],
            "colour": r.get("colour"),
            "size": r.get("size"),
            "stock_qty": r.get("stock_qty"),
            "mrp": r.get("mrp"),
            "item_code": item_code,
            "purchase_qty": r.get("purchase_qty"),
            "purchase_rate": r.get("purchase_rate"),
            "purchase_amount": r.get("purchase_amount"),
            "difference": r.get("difference"),
            "stock_amount": r.get("stock_amount"),
            "pdf_page": r.get("pdf_page"),
            "original_product_text": r.get("original_product_text"),
            "filename": r.get("filename"),
            "report_date": r.get("report_date"),
        }
        display_name = r.get("original_name")
        if cat == "jewellery" and dn and not display_name:
            display_name = dn

        if key not in groups:
            groups[key] = {
                "product_id": r["product_id"],
                "design_number": dn,
                "design_name": display_name,
                "category": cat,
                "supplier": r.get("supplier_name"),
                "report_id": r.get("report_id"),
                "report_date": r.get("report_date"),
                "filename": r.get("filename"),
                "variants": [],
                "total_stock": 0.0,
                "_variant_index": {},
            }

        prev = seen_variant_keys.get(item_key)
        if prev is not None:
            prev_report_id, prev_snapshot_id = prev
            prev_row = next(
                (x for x in filtered if x.get("snapshot_id") == prev_snapshot_id),
                None,
            )
            if prev_row is not None and _row_rank(r) <= _row_rank(prev_row):
                continue
            idx = groups[key]["_variant_index"].get(item_key)
            if idx is not None:
                old = groups[key]["variants"][idx]
                groups[key]["total_stock"] -= float(old.get("stock_qty") or 0)
                groups[key]["variants"][idx] = variant_payload
                groups[key]["total_stock"] += float(r.get("stock_qty") or 0)
                seen_variant_keys[item_key] = (
                    int(r.get("report_id") or 0),
                    int(r["snapshot_id"]),
                )
                if _row_rank(r) >= _row_rank(prev_row or r):
                    groups[key]["report_id"] = r.get("report_id")
                    groups[key]["report_date"] = r.get("report_date")
                    groups[key]["filename"] = r.get("filename")
                    groups[key]["supplier"] = r.get("supplier_name")
                continue

        seen_variant_keys[item_key] = (int(r.get("report_id") or 0), int(r["snapshot_id"]))
        groups[key]["_variant_index"][item_key] = len(groups[key]["variants"])
        groups[key]["variants"].append(variant_payload)
        groups[key]["total_stock"] += float(r.get("stock_qty") or 0)

    results = []
    for g in groups.values():
        g.pop("_variant_index", None)
        results.append(g)
    results.sort(key=lambda g: (g.get("design_number") or "", g.get("design_name") or ""))

    total = len(results)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * page_size
    page_results = results[start : start + page_size]

    return {
        "query": query,
        "report_id": effective_report_id,
        "colour_message": colour_missing_message,
        "count": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "results": page_results,
    }


def get_design_detail(product_id: int, report_id: Optional[int] = None) -> dict[str, Any]:
    product = db.col("products").find_one({"id": product_id})
    if not product:
        raise ValueError("Design not found")
    effective_report_id = report_id or _latest_report_id()
    variants = list(db.col("variants").find({"product_id": product_id}))
    variant_ids = [int(v["id"]) for v in variants]
    snap_q: dict[str, Any] = {"variant_id": {"$in": variant_ids}}
    if effective_report_id:
        snap_q["report_id"] = effective_report_id
    # only imported reports
    imported_ids = {
        int(r["id"]) for r in db.col("reports").find({"status": "imported"}, {"id": 1})
    }
    snapshots = [
        s for s in db.col("stock_snapshots").find(snap_q) if int(s["report_id"]) in imported_ids
    ]
    reports = {
        int(r["id"]): r
        for r in db.col("reports").find({"id": {"$in": list({int(s["report_id"]) for s in snapshots})}})
    }
    suppliers = _supplier_map()
    vmap = {int(v["id"]): v for v in variants}

    out_variants = []
    for ss in snapshots:
        v = vmap.get(int(ss["variant_id"]))
        if not v:
            continue
        r = reports.get(int(ss["report_id"]))
        if not r:
            continue
        out_variants.append(
            {
                "variant_id": v["id"],
                "item_code": v.get("item_code"),
                "colour": v.get("colour"),
                "size": v.get("size"),
                "original_variant_name": v.get("original_variant_name"),
                "snapshot_id": ss["id"],
                "id": ss["id"],
                "purchase_qty": ss.get("purchase_qty"),
                "purchase_rate": ss.get("purchase_rate"),
                "purchase_amount": ss.get("purchase_amount"),
                "stock_qty": ss.get("stock_qty"),
                "difference": ss.get("difference"),
                "mrp": ss.get("mrp"),
                "stock_amount": ss.get("stock_amount"),
                "pdf_page": ss.get("pdf_page"),
                "original_product_text": ss.get("original_product_text"),
                "needs_review": ss.get("needs_review"),
                "filename": r.get("filename"),
                "report_date": r.get("report_date"),
                "supplier_name": suppliers.get(r.get("supplier_id")),
                "report_id": r["id"],
            }
        )
    out_variants.sort(
        key=lambda x: (x.get("colour") or "", x.get("size") or "", x.get("item_code") or "")
    )
    total_stock = sum(float(v.get("stock_qty") or 0) for v in out_variants)
    supplier = out_variants[0]["supplier_name"] if out_variants else None
    report_date = out_variants[0]["report_date"] if out_variants else None
    return {
        "product_id": product["id"],
        "design_number": product.get("design_number"),
        "design_name": product.get("original_name"),
        "category": product.get("category"),
        "supplier": supplier,
        "report_date": report_date,
        "report_id": effective_report_id,
        "total_stock": total_stock,
        "variants": out_variants,
    }


def get_dashboard() -> dict[str, Any]:
    latest_id = _latest_report_id()
    latest = None
    suppliers = _supplier_map()
    if latest_id:
        r = db.col("reports").find_one({"id": latest_id})
        if r:
            latest = dict(r)
            latest.pop("_id", None)
            latest["supplier_name"] = suppliers.get(r.get("supplier_id"))

    snap_q: dict[str, Any] = {}
    if latest_id:
        snap_q["report_id"] = latest_id
    else:
        imported = [int(r["id"]) for r in db.col("reports").find({"status": "imported"}, {"id": 1})]
        snap_q["report_id"] = {"$in": imported} if imported else {"$in": []}

    snapshots = list(db.col("stock_snapshots").find(snap_q))
    variant_ids = list({int(s["variant_id"]) for s in snapshots})
    variants = {int(v["id"]): v for v in db.col("variants").find({"id": {"$in": variant_ids}})}
    product_ids = list({int(v["product_id"]) for v in variants.values()})
    products = {int(p["id"]): p for p in db.col("products").find({"id": {"$in": product_ids}})}

    design_ids = set()
    fashion = set()
    jewellery = set()
    total_stock = 0.0
    low_stock = 0
    out_stock = 0
    for ss in snapshots:
        v = variants.get(int(ss["variant_id"]))
        if not v:
            continue
        p = products.get(int(v["product_id"]))
        if not p:
            continue
        design_ids.add(p["id"])
        if p.get("category") == "fashion":
            fashion.add(p["id"])
        elif p.get("category") == "jewellery":
            jewellery.add(p["id"])
        qty = float(ss.get("stock_qty") or 0)
        total_stock += qty
        if qty <= 0:
            out_stock += 1
        elif qty <= LOW_STOCK_THRESHOLD:
            low_stock += 1

    recent = []
    for r in sorted(
        db.col("reports").find(),
        key=lambda x: x.get("uploaded_at") or "",
        reverse=True,
    )[:10]:
        d = {
            "id": r["id"],
            "filename": r.get("filename"),
            "report_date": r.get("report_date"),
            "category": r.get("category"),
            "status": r.get("status"),
            "total_rows": r.get("total_rows"),
            "uploaded_at": r.get("uploaded_at"),
            "supplier_name": suppliers.get(r.get("supplier_id")),
        }
        recent.append(d)

    return {
        "latest_report": latest,
        "total_designs": len(design_ids),
        "total_stock_units": total_stock,
        "fashion_products": len(fashion),
        "jewellery_products": len(jewellery),
        "suppliers": len(suppliers),
        "low_stock_products": low_stock,
        "out_of_stock_products": out_stock,
        "recent_uploads": recent,
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
    }


def get_source(snapshot_id: int) -> dict[str, Any]:
    ss = db.col("stock_snapshots").find_one({"id": snapshot_id})
    if not ss:
        raise ValueError("Snapshot not found")
    r = db.col("reports").find_one({"id": ss["report_id"]})
    v = db.col("variants").find_one({"id": ss["variant_id"]})
    p = db.col("products").find_one({"id": v["product_id"]}) if v else None
    if not r or not v or not p:
        raise ValueError("Snapshot not found")
    return {
        **{k: ss.get(k) for k in ss if k != "_id"},
        "report_id": r["id"],
        "filename": r.get("filename"),
        "stored_path": r.get("stored_path"),
        "gridfs_id": r.get("gridfs_id"),
        "report_date": r.get("report_date"),
        "item_code": v.get("item_code"),
        "colour": v.get("colour"),
        "size": v.get("size"),
        "design_number": p.get("design_number"),
        "original_name": p.get("original_name"),
    }


def list_filter_options(report_id: Optional[int] = None) -> dict[str, Any]:
    effective = report_id or _latest_report_id()
    snap_q: dict[str, Any] = {}
    if effective:
        snap_q["report_id"] = effective
    snapshots = list(db.col("stock_snapshots").find(snap_q))
    variant_ids = list({int(s["variant_id"]) for s in snapshots})
    variants = list(db.col("variants").find({"id": {"$in": variant_ids}})) if variant_ids else []
    colours = sorted({v["colour"] for v in variants if v.get("colour")})
    sizes = sorted({v["size"] for v in variants if v.get("size")})
    suppliers = sorted(s["name"] for s in db.col("suppliers").find() if s.get("name"))
    return {
        "colours": colours,
        "sizes": sizes,
        "suppliers": suppliers,
        "categories": ["fashion", "jewellery"],
        "stock_statuses": [
            {"value": "in_stock", "label": "In Stock"},
            {"value": "low_stock", "label": "Low Stock"},
            {"value": "out_of_stock", "label": "Out of Stock"},
        ],
    }
