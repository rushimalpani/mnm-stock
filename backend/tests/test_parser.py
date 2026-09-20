"""Automated tests for parsing, normalization, search, and import."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import DB_PATH, init_db  # noqa: E402
from app.services.normalize import (  # noqa: E402
    extract_design_number,
    join_multiline_tokens,
    normalize_for_search,
    parse_number,
)
from app.services.parsers.fashion import parse_fashion_product_name  # noqa: E402
from app.services.parsers.jewellery import parse_jewellery_product_name  # noqa: E402
from app.services.parsers import parse_data_line, parse_stock_pdf  # noqa: E402
from app.services import import_service, search_service  # noqa: E402
from scripts.generate_samples import create_fashion_sample, create_jewellery_sample  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(import_service, "UPLOADS_DIR", uploads)
    monkeypatch.setattr("app.database.DB_PATH", db)
    monkeypatch.setattr("app.database.UPLOADS_DIR", uploads)
    monkeypatch.setattr(import_service, "init_db", init_db)
    # re-bind DB path used by db_session
    import app.database as database

    monkeypatch.setattr(database, "DB_PATH", db)
    init_db()
    yield db


def test_design_number_from_product_name_not_page():
    assert extract_design_number("134-Digital Print") == "134"
    assert extract_design_number("1501-Jewellery-Women------27-16") == "1501"
    assert extract_design_number("Digital Print") is None


def test_design_name_and_colour_size_fashion():
    meta = parse_fashion_product_name("134-Digital Print-Women-36-Black")
    assert meta["design_number"] == "134"
    assert meta["design_name"] == "134-Digital Print"
    assert meta["colour"] == "Black"
    assert meta["size"] == "36"
    assert meta["category"] == "fashion"


def test_fashion_colour_after_double_dash():
    meta = parse_fashion_product_name(
        "569-Work-Women-Free size-free size-6-2.25--Morpankhi-1 size-free"
    )
    assert meta["design_number"] == "569"
    assert meta["design_name"] == "569-Work-Women-Free size-free size-6-2.25"
    assert meta["colour"] == "Morpankhi"
    assert meta["size"] == "Free size"

    purple = parse_fashion_product_name(
        "569-Work-Women-Free size-free size-6-2.25--Purple-1 size-free"
    )
    assert purple["colour"] == "Purple"


def test_fashion_variant_size_after_colour():
    """Size after --Colour-SIZE must win over 'Free size' in the design prefix."""
    meta = parse_fashion_product_name(
        "131-Digital Print-Women-Free size-36-44-3.5-2.25--Green Pista-36"
    )
    assert meta["design_number"] == "131"
    assert meta["design_name"] == "131-Digital Print-Women-Free size-36-44-3.5-2.25"
    assert meta["colour"] == "Green Pista"
    assert meta["size"] == "36"

    pink40 = parse_fashion_product_name(
        "131-Digital Print-Women-Free size-36-44-3.5-2.25--Pink-40"
    )
    assert pink40["colour"] == "Pink"
    assert pink40["size"] == "40"

    sky = parse_fashion_product_name(
        "131-Digital Print-Women-Free size-36-44-3.5-2.25--Sky Blue-44"
    )
    assert sky["colour"] == "Sky Blue"
    assert sky["size"] == "44"

    block = parse_fashion_product_name(
        "131-Digital Print-Women-Free size-36-44-3.5-2.25--Block-36"
    )
    assert block["colour"] == "Block"
    assert block["size"] == "36"


def test_multiline_colour_join():
    joined = join_multiline_tokens(["Navy", "Blue"])
    assert joined == "Navy Blue"
    meta = parse_fashion_product_name("256-Bandhani-Girls-Free size-Navy\nBlue")
    assert meta["colour"] in {"Navy Blue", "Blue", "Navy"}  # merge preferred
    # After merge_colour_fragments path via full name:
    meta2 = parse_fashion_product_name("256-Bandhani-Girls-Free size-Navy Blue")
    assert meta2["colour"] == "Navy Blue"


def test_bottle_green_multiline():
    meta = parse_fashion_product_name("890-Chaniya Choli-Women-40-Bottle Green")
    assert meta["design_number"] == "890"
    assert meta["colour"] == "Bottle Green"


def test_split_fashion_design_prefix_anchor():
    """PDF often splits '577-3' + 'Piece-Women-Free' — must still start a product row."""
    from app.services.pdf_rows import _is_product_anchor, extract_rows_from_words

    assert _is_product_anchor("577-3", ["577-3", "Piece-Women-Free"])
    assert not _is_product_anchor("93-1", ["93-1"])  # lone jewellery wrap code

    words = [
        {"text": "Supplier", "x0": 20, "top": 40},
        {"text": "577-3", "x0": 20, "top": 100},
        {"text": "Piece-Women-Free", "x0": 55, "top": 100},
        {"text": "size-free", "x0": 140, "top": 100},
        {"text": "size-5-2.25--White-1", "x0": 20, "top": 112},
        {"text": "200471009", "x0": 200, "top": 100},
        {"text": "2", "x0": 300, "top": 100},
        {"text": "1000", "x0": 340, "top": 100},
        {"text": "2000", "x0": 380, "top": 100},
        {"text": "2", "x0": 420, "top": 100},
        {"text": "0", "x0": 460, "top": 100},
        {"text": "3150", "x0": 500, "top": 100},
        {"text": "6300", "x0": 540, "top": 100},
    ]
    rows = extract_rows_from_words(words, page_number=165)
    assert len(rows) == 1
    assert rows[0].product_name.startswith("577-3")
    assert "White" in rows[0].product_name
    assert rows[0].item_code == "200471009"
    assert rows[0].stock_qty == 2.0
    assert rows[0].mrp == 3150.0

    meta = parse_fashion_product_name(rows[0].product_name)
    assert meta["design_number"] == "577"
    assert meta["colour"] == "White"


def test_fashion_and_jewellery_parsers_stay_separate():
    """Fashion colour rules must not apply to jewellery; wrap-merge is jewellery-only."""
    from app.services.parsers import _row_category
    from app.services.parsers.base import ParsedRow
    from app.services.pdf_rows import RawTableRow
    from app.services.parsers import _raw_table_to_parsed

    assert _row_category("577-3 Piece-Women-Free--White-1", "unknown") == "fashion"
    assert _row_category("1501-Jewellery-Women------27-16", "fashion") == "jewellery"
    assert _row_category("1501--------41-1657-1", "fashion") == "jewellery"

    fashion_row = RawTableRow(
        product_name="577-3 Piece-Women-Free size-free size-5-2.25--Purple-1",
        item_code="200471010",
        purchase_qty=4,
        purchase_rate=1000,
        purchase_amount=4000,
        stock_qty=4,
        difference=0,
        mrp=3150,
        stock_amount=12600,
        pdf_page=162,
        secondary_label="93-1",  # must be ignored for fashion
    )
    parsed_f = _raw_table_to_parsed(
        fashion_row, supplier="Bandhani", report_date="19/09/2026", category="fashion"
    )
    assert parsed_f.category == "fashion"
    assert parsed_f.design_number == "577"
    assert parsed_f.colour == "Purple"
    assert "1693" not in (parsed_f.original_product_text or "")

    jew_row = RawTableRow(
        product_name="1501-Jewellery-Women------27-16",
        item_code="200467010",
        purchase_qty=1,
        purchase_rate=310,
        purchase_amount=310,
        stock_qty=1,
        difference=0,
        mrp=620,
        stock_amount=620,
        pdf_page=1,
        secondary_label="93-1",
    )
    parsed_j = _raw_table_to_parsed(
        jew_row, supplier="KM", report_date="19/09/2026", category="jewellery"
    )
    assert parsed_j.category == "jewellery"
    assert parsed_j.design_number == "1693"
    assert parsed_j.design_name == "1693-1"


def test_jewellery_preserves_original():
    raw = "1501-Jewellery-Women------27-16"
    meta = parse_jewellery_product_name(raw, secondary="93-1")
    assert meta["design_number"] == "1693"
    assert meta["design_name"] == "1693-1"
    assert meta["original_product_text"] == "1501-Jewellery-Women------27-1693-1"
    assert meta["category"] == "jewellery"


def test_jewellery_sparse_name():
    meta = parse_jewellery_product_name("1501--------41-1657-1")
    assert meta["design_number"] == "1657"
    assert meta["design_name"] == "1657-1"
    assert "1501" in meta["original_product_text"]


def test_item_code_and_stock_not_purchase():
    row = parse_data_line(
        "134-Digital Print-Women-36-Black | 200134001 | 50 | 800 | 40000 | 20 | 30 | 1200 | 24000",
        page=1,
        supplier="MNM",
        report_date="17/09/2026",
        category="fashion",
    )
    assert row is not None
    assert row.item_code == "200134001"
    assert row.purchase_qty == 50
    assert row.stock_qty == 20  # MUST be stock, not purchase
    assert row.mrp == 1200
    assert row.stock_amount == 24000
    assert row.design_number == "134"


def test_search_normalization():
    assert normalize_for_search("134-Digital   Print") == "134 digital print"
    assert normalize_for_search("Navy\nBlue") == "navy blue"
    assert parse_number("1,200") == 1200.0


def test_end_to_end_fashion_pdf(fresh_db, tmp_path):
    pdf = create_fashion_sample(tmp_path / "fashion.pdf")
    result = parse_stock_pdf(pdf)
    assert result.total_pages >= 1
    assert len(result.rows) >= 5
    designs = {r.design_number for r in result.rows}
    assert "134" in designs
    # Multi-colour design 134
    d134 = [r for r in result.rows if r.design_number == "134"]
    colours = {r.colour for r in d134 if r.colour}
    assert "Black" in colours
    assert any(r.stock_qty == 20 for r in d134)

    preview = import_service.create_preview(pdf, "fashion.pdf")
    assert preview["rows_detected"] >= 5
    confirmed = import_service.confirm_import(preview["report_id"], include_review_rows=True)
    assert confirmed["status"] == "imported"

    search = search_service.search_stock("134")
    assert search["count"] >= 1
    group = search["results"][0]
    assert len(group["variants"]) >= 2  # multiple colours/sizes

    black = search_service.search_stock("134", colour="Black")
    assert all(
        (v.get("colour") or "").lower().find("black") >= 0
        or "black" in (v.get("original_product_text") or "").lower()
        for g in black["results"]
        for v in g["variants"]
    )

    # Search box matches design number/name only — not colour words
    colour_as_query = search_service.search_stock("Black")
    assert all(
        "black" in (g.get("design_name") or "").lower()
        or "black" in (g.get("design_number") or "").lower()
        for g in colour_as_query["results"]
    )

    missing = search_service.search_stock("134", colour="Neonpurplexyz")
    assert missing["colour_message"] == "No matching colour available in this report."


def test_jewellery_style_code_is_search_key():
    """Jewellery search key is 1693/1657, not series prefix 1501."""
    from app.services.parsers.jewellery import parse_jewellery_product_name

    a = parse_jewellery_product_name("1501-Jewellery-Women------1693-1")
    assert a["design_number"] == "1693"
    assert a["design_name"] == "1693-1"

    b = parse_jewellery_product_name("1501--------41-1657-1")
    assert b["design_number"] == "1657"
    assert b["design_name"] == "1657-1"

    # PDF wraps mid-number: line1 ends ...27-16 / line2 93-1 → 1693
    c = parse_jewellery_product_name("1501-Jewellery-Women------27-16", secondary="93-1")
    assert c["design_number"] == "1693"
    assert c["design_name"] == "1693-1"
    assert "1693-1" in c["original_product_text"]

    d = parse_jewellery_product_name("1501-Jewellery-Women------27-16 93-1")
    assert d["design_number"] == "1693"

    e = parse_jewellery_product_name("1501-Jewellery-Women------100-1", secondary="685-1")
    assert e["design_number"] == "1685"

    f = parse_jewellery_product_name("1657-1")
    assert f["design_number"] == "1657"


def test_end_to_end_jewellery_pdf(fresh_db, tmp_path):
    pdf = create_jewellery_sample(tmp_path / "jewellery.pdf")
    result = parse_stock_pdf(pdf)
    assert any(r.design_number == "1657" for r in result.rows)
    assert any(r.design_number == "27" for r in result.rows) or any(
        r.design_number == "93" for r in result.rows
    )
    preview = import_service.create_preview(pdf, "jewellery.pdf")
    import_service.confirm_import(preview["report_id"], include_review_rows=True)
    search = search_service.search_stock("1657", category="jewellery")
    assert search["count"] >= 1
    assert search["results"][0]["design_number"] == "1657"


def test_real_jewellery_pdf_layout():
    """Regression: real Supplier Wise Stock Report uses column word positions."""
    real = Path(__file__).resolve().parents[1] / "uploads"
    matches = list(real.glob("*jewellery*.pdf")) + list(real.glob("*Jewellery*.pdf"))
    if not matches:
        pytest.skip("No real jewellery upload present")
    result = parse_stock_pdf(matches[0])
    assert result.rows_parsed >= 50
    assert any(r.design_number == "1657" for r in result.rows)
    first = next(r for r in result.rows if r.item_code == "200467010")
    assert first.stock_qty == 1.0
    assert first.mrp == 620.0
    assert first.purchase_qty == 1.0
    # First row style code is the trailing NN-1 (93), not series 1501
    assert first.design_number != "1501"


def test_historical_reports_not_overwritten(fresh_db, tmp_path):
    pdf1 = create_fashion_sample(tmp_path / "f1.pdf")
    pdf2 = create_fashion_sample(tmp_path / "f2.pdf")
    p1 = import_service.create_preview(pdf1, "f1.pdf")
    import_service.confirm_import(p1["report_id"], include_review_rows=True)
    p2 = import_service.create_preview(pdf2, "f2.pdf")
    import_service.confirm_import(p2["report_id"], include_review_rows=True)
    reports = import_service.list_reports()
    imported = [r for r in reports if r["status"] == "imported"]
    assert len(imported) >= 2


def test_same_filename_replaces_report(fresh_db, tmp_path):
    """Re-uploading the same filename replaces stock + deletes the old PDF file."""
    from app.database import db_session

    uploads = import_service.UPLOADS_DIR
    pdf1 = create_fashion_sample(tmp_path / "stock.pdf")
    stored1 = import_service.save_upload(pdf1.read_bytes(), "Stock.pdf")
    p1 = import_service.create_preview(stored1, "Stock.pdf")
    assert p1["replaced"] is False
    import_service.confirm_import(p1["report_id"], include_review_rows=True)
    report_id = p1["report_id"]
    assert stored1.exists()

    pdf2 = create_fashion_sample(tmp_path / "stock2.pdf")
    stored2 = import_service.save_upload(pdf2.read_bytes(), "stock.pdf")
    p2 = import_service.create_preview(stored2, "stock.pdf")
    assert p2["replaced"] is True
    assert p2["report_id"] == report_id
    assert p2["status"] == "preview"
    assert not stored1.exists()
    assert stored2.exists()

    reports = [r for r in import_service.list_reports() if r["filename"].lower() == "stock.pdf"]
    assert len(reports) == 1
    assert reports[0]["status"] == "preview"

    with db_session() as conn:
        snaps = conn.execute(
            "SELECT COUNT(*) AS c FROM stock_snapshots WHERE report_id = ?",
            (report_id,),
        ).fetchone()["c"]
    assert snaps == 0

    confirmed = import_service.confirm_import(report_id, include_review_rows=True)
    assert confirmed["status"] == "imported"
    assert confirmed["imported_rows"] >= 1

    # Different filename still keeps a separate report
    other = create_fashion_sample(tmp_path / "other.pdf")
    stored3 = import_service.save_upload(other.read_bytes(), "other.pdf")
    p3 = import_service.create_preview(stored3, "other.pdf")
    assert p3["replaced"] is False
    assert p3["report_id"] != report_id
    assert len(import_service.list_reports()) >= 2
    assert len(list(uploads.glob("*.pdf"))) >= 2
