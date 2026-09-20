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


def test_jewellery_preserves_original():
    raw = "1501-Jewellery-Women------27-16"
    meta = parse_jewellery_product_name(raw)
    assert meta["original_product_text"] == raw
    assert meta["design_number"] == "1501"
    assert meta["category"] == "jewellery"


def test_jewellery_sparse_name():
    meta = parse_jewellery_product_name("1501--------41-1657-1")
    assert meta["design_number"] == "1501"
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


def test_end_to_end_jewellery_pdf(fresh_db, tmp_path):
    pdf = create_jewellery_sample(tmp_path / "jewellery.pdf")
    result = parse_stock_pdf(pdf)
    assert any(r.design_number == "1501" for r in result.rows)
    preview = import_service.create_preview(pdf, "jewellery.pdf")
    import_service.confirm_import(preview["report_id"], include_review_rows=True)
    search = search_service.search_stock("1501")
    assert search["count"] >= 1


def test_real_jewellery_pdf_layout():
    """Regression: real Supplier Wise Stock Report uses column word positions."""
    real = Path(__file__).resolve().parents[1] / "uploads"
    matches = list(real.glob("*jewellery*.pdf")) + list(real.glob("*Jewellery*.pdf"))
    if not matches:
        pytest.skip("No real jewellery upload present")
    result = parse_stock_pdf(matches[0])
    assert result.rows_parsed >= 50
    assert any(r.design_number == "1501" for r in result.rows)
    first = next(r for r in result.rows if r.item_code == "200467010")
    assert first.stock_qty == 1.0
    assert first.mrp == 620.0
    assert first.purchase_qty == 1.0


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
