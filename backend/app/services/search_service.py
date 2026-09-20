"""Search and filter stock across historical report snapshots."""
from __future__ import annotations

from typing import Any, Optional

from app.database import db_session
from app.services.normalize import normalize_for_search


LOW_STOCK_THRESHOLD = 5


def _latest_report_id(conn) -> Optional[int]:
    row = conn.execute(
        """
        SELECT id FROM reports
        WHERE status = 'imported'
        ORDER BY
            CASE WHEN report_date IS NULL THEN 1 ELSE 0 END,
            date(substr(report_date, 7, 4) || '-' || substr(report_date, 4, 2) || '-' || substr(report_date, 1, 2)) DESC,
            uploaded_at DESC
        LIMIT 1
        """
    ).fetchone()
    return row["id"] if row else None


def _report_filter_sql(report_id: Optional[int], latest: bool) -> tuple[str, list]:
    if report_id:
        return "ss.report_id = ?", [report_id]
    if latest:
        rid = None  # resolved by caller
        return "ss.report_id = ?", []  # placeholder
    return "1=1", []


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

    with db_session() as conn:
        effective_report_id = report_id
        if effective_report_id is None and latest:
            effective_report_id = _latest_report_id(conn)

        params: list[Any] = []
        where = ["r.status = 'imported'"]
        if effective_report_id:
            where.append("ss.report_id = ?")
            params.append(effective_report_id)

        if category:
            where.append("p.category = ?")
            params.append(category)
        if supplier:
            where.append("LOWER(s.name) LIKE ?")
            params.append(f"%{supplier.lower()}%")
        if design_number:
            where.append("p.design_number = ?")
            params.append(design_number)
        if size:
            where.append("LOWER(IFNULL(v.size,'')) LIKE ?")
            params.append(f"%{size.lower()}%")

        if stock_status == "in_stock":
            where.append("IFNULL(ss.stock_qty, 0) > ?")
            params.append(LOW_STOCK_THRESHOLD)
        elif stock_status == "low_stock":
            where.append("IFNULL(ss.stock_qty, 0) > 0 AND IFNULL(ss.stock_qty, 0) <= ?")
            params.append(LOW_STOCK_THRESHOLD)
        elif stock_status == "out_of_stock":
            where.append("IFNULL(ss.stock_qty, 0) <= 0")

        sql = f"""
            SELECT
                p.id AS product_id,
                p.design_number,
                p.original_name,
                p.normalized_name,
                p.category,
                v.id AS variant_id,
                v.item_code,
                v.colour,
                v.size,
                v.original_variant_name,
                ss.id AS snapshot_id,
                ss.stock_qty,
                ss.mrp,
                ss.purchase_qty,
                ss.purchase_rate,
                ss.purchase_amount,
                ss.difference,
                ss.stock_amount,
                ss.pdf_page,
                ss.original_product_text,
                ss.needs_review,
                r.id AS report_id,
                r.filename,
                r.report_date,
                s.name AS supplier_name
            FROM stock_snapshots ss
            JOIN variants v ON v.id = ss.variant_id
            JOIN products p ON p.id = v.product_id
            JOIN reports r ON r.id = ss.report_id
            LEFT JOIN suppliers s ON s.id = r.supplier_id
            WHERE {' AND '.join(where)}
        """
        rows = [dict(x) for x in conn.execute(sql, params).fetchall()]

    # Search ONLY by design number + design name (not colour/size/item code/supplier)
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

            # Pure design number (e.g. "131" or jewellery "1693") — exact only
            if len(query_tokens) == 1 and query_tokens[0].isdigit():
                return dn == query_tokens[0]

            # Design number + name words (e.g. "131 Digital")
            if query_tokens[0].isdigit():
                if dn != query_tokens[0]:
                    return False
                return all(tok in name_norm for tok in query_tokens[1:])

            # Design name only (e.g. "Digital Print")
            return all(tok in blob for tok in query_tokens)

        filtered = [r for r in filtered if matches(r)]

    # Optional colour filter from UI only (not from search box)
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

    # Group by design number so all colours/sizes appear together.
    # Dedupe same item across reports / re-imports (keep newest report snapshot).
    groups: dict[str, dict[str, Any]] = {}
    seen_variant_keys: dict[str, tuple[int, int]] = {}  # group_key+item → (report_id, snapshot_id)

    def _row_rank(r: dict) -> tuple:
        return (
            str(r.get("report_date") or ""),
            int(r.get("report_id") or 0),
            int(r.get("snapshot_id") or 0),
        )

    for r in filtered:
        category = r.get("category") or "unknown"
        design_number = r.get("design_number")
        item_code = r.get("item_code")

        # Fashion: one card per design (all colours/sizes).
        # Jewellery: one card per style code (all item codes as rows) — same as before.
        key = f"{category}::{design_number or r.get('product_id')}"

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
        if category == "jewellery" and design_number and not display_name:
            display_name = design_number

        if key not in groups:
            groups[key] = {
                "product_id": r["product_id"],
                "design_number": design_number,
                "design_name": display_name,
                "category": category,
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
            # Prefer newer report / newer snapshot; skip older duplicate
            prev_report_id, prev_snapshot_id = prev
            prev_row = next(
                (x for x in filtered if x.get("snapshot_id") == prev_snapshot_id),
                None,
            )
            if prev_row is not None and _row_rank(r) <= _row_rank(prev_row):
                continue
            # Replace older variant in group
            idx = groups[key]["_variant_index"].get(item_key)
            if idx is not None:
                old = groups[key]["variants"][idx]
                groups[key]["total_stock"] -= float(old.get("stock_qty") or 0)
                groups[key]["variants"][idx] = variant_payload
                groups[key]["total_stock"] += float(r.get("stock_qty") or 0)
                seen_variant_keys[item_key] = (int(r.get("report_id") or 0), int(r["snapshot_id"]))
                # Keep group metadata on the newest row
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
    with db_session() as conn:
        product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if not product:
            raise ValueError("Design not found")
        effective_report_id = report_id or _latest_report_id(conn)
        params: list[Any] = [product_id]
        where = ["v.product_id = ?", "r.status = 'imported'"]
        if effective_report_id:
            where.append("ss.report_id = ?")
            params.append(effective_report_id)
        sql = f"""
            SELECT
                v.id AS variant_id,
                v.item_code,
                v.colour,
                v.size,
                v.original_variant_name,
                ss.id AS snapshot_id,
                ss.purchase_qty,
                ss.purchase_rate,
                ss.purchase_amount,
                ss.stock_qty,
                ss.difference,
                ss.mrp,
                ss.stock_amount,
                ss.pdf_page,
                ss.original_product_text,
                ss.needs_review,
                r.filename,
                r.report_date,
                s.name AS supplier_name,
                r.id AS report_id
            FROM variants v
            JOIN stock_snapshots ss ON ss.variant_id = v.id
            JOIN reports r ON r.id = ss.report_id
            LEFT JOIN suppliers s ON s.id = r.supplier_id
            WHERE {' AND '.join(where)}
            ORDER BY v.colour, v.size, v.item_code
        """
        variants = [dict(x) for x in conn.execute(sql, params).fetchall()]
        # expose snapshot id as id for UI source button compatibility
        for v in variants:
            v["id"] = v["snapshot_id"]
        total_stock = sum(float(v.get("stock_qty") or 0) for v in variants)
        supplier = variants[0]["supplier_name"] if variants else None
        report_date = variants[0]["report_date"] if variants else None
        return {
            "product_id": product["id"],
            "design_number": product["design_number"],
            "design_name": product["original_name"],
            "category": product["category"],
            "supplier": supplier,
            "report_date": report_date,
            "report_id": effective_report_id,
            "total_stock": total_stock,
            "variants": variants,
        }


def get_dashboard() -> dict[str, Any]:
    with db_session() as conn:
        latest_id = _latest_report_id(conn)
        latest = None
        if latest_id:
            latest = dict(
                conn.execute(
                    """
                    SELECT r.*, s.name AS supplier_name
                    FROM reports r LEFT JOIN suppliers s ON s.id = r.supplier_id
                    WHERE r.id = ?
                    """,
                    (latest_id,),
                ).fetchone()
            )

        def scalar(sql: str, params: tuple = ()) -> float:
            row = conn.execute(sql, params).fetchone()
            return float(row[0] or 0) if row else 0

        base = "FROM stock_snapshots ss JOIN variants v ON v.id = ss.variant_id JOIN products p ON p.id = v.product_id JOIN reports r ON r.id = ss.report_id WHERE r.status='imported'"
        params: tuple = ()
        if latest_id:
            base += " AND ss.report_id = ?"
            params = (latest_id,)

        total_designs = scalar(f"SELECT COUNT(DISTINCT p.id) {base}", params)
        total_stock = scalar(f"SELECT SUM(ss.stock_qty) {base}", params)
        fashion = scalar(f"SELECT COUNT(DISTINCT p.id) {base} AND p.category='fashion'", params)
        jewellery = scalar(f"SELECT COUNT(DISTINCT p.id) {base} AND p.category='jewellery'", params)
        suppliers = scalar("SELECT COUNT(*) FROM suppliers")
        low_stock = scalar(
            f"SELECT COUNT(*) {base} AND IFNULL(ss.stock_qty,0) > 0 AND IFNULL(ss.stock_qty,0) <= ?",
            params + (LOW_STOCK_THRESHOLD,) if params else (LOW_STOCK_THRESHOLD,),
        )
        out_stock = scalar(f"SELECT COUNT(*) {base} AND IFNULL(ss.stock_qty,0) <= 0", params)

        recent = [
            dict(r)
            for r in conn.execute(
                """
                SELECT r.id, r.filename, r.report_date, r.category, r.status, r.total_rows, r.uploaded_at, s.name AS supplier_name
                FROM reports r LEFT JOIN suppliers s ON s.id = r.supplier_id
                ORDER BY r.uploaded_at DESC LIMIT 10
                """
            ).fetchall()
        ]

        return {
            "latest_report": latest,
            "total_designs": int(total_designs),
            "total_stock_units": total_stock,
            "fashion_products": int(fashion),
            "jewellery_products": int(jewellery),
            "suppliers": int(suppliers),
            "low_stock_products": int(low_stock),
            "out_of_stock_products": int(out_stock),
            "recent_uploads": recent,
            "low_stock_threshold": LOW_STOCK_THRESHOLD,
        }


def get_source(snapshot_id: int) -> dict[str, Any]:
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT ss.*, r.id AS report_id, r.filename, r.stored_path, r.report_date, v.item_code, v.colour, v.size,
                   p.design_number, p.original_name
            FROM stock_snapshots ss
            JOIN reports r ON r.id = ss.report_id
            JOIN variants v ON v.id = ss.variant_id
            JOIN products p ON p.id = v.product_id
            WHERE ss.id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        if not row:
            raise ValueError("Snapshot not found")
        return dict(row)


def list_filter_options(report_id: Optional[int] = None) -> dict[str, Any]:
    with db_session() as conn:
        effective = report_id or _latest_report_id(conn)
        params: list[Any] = []
        where = "r.status='imported'"
        if effective:
            where += " AND ss.report_id = ?"
            params.append(effective)
        colours = [
            r[0]
            for r in conn.execute(
                f"""
                SELECT DISTINCT v.colour FROM stock_snapshots ss
                JOIN variants v ON v.id = ss.variant_id
                JOIN reports r ON r.id = ss.report_id
                WHERE {where} AND v.colour IS NOT NULL AND v.colour != ''
                ORDER BY v.colour
                """,
                params,
            )
        ]
        sizes = [
            r[0]
            for r in conn.execute(
                f"""
                SELECT DISTINCT v.size FROM stock_snapshots ss
                JOIN variants v ON v.id = ss.variant_id
                JOIN reports r ON r.id = ss.report_id
                WHERE {where} AND v.size IS NOT NULL AND v.size != ''
                ORDER BY v.size
                """,
                params,
            )
        ]
        suppliers = [
            r[0]
            for r in conn.execute("SELECT name FROM suppliers ORDER BY name")
        ]
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
