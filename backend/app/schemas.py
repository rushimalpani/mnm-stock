from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ConfirmImportRequest(BaseModel):
    include_review_rows: bool = False


class SearchParams(BaseModel):
    q: str = ""
    report_id: Optional[int] = None
    latest: bool = True
    category: Optional[str] = None
    supplier: Optional[str] = None
    design_number: Optional[str] = None
    colour: Optional[str] = None
    size: Optional[str] = None
    stock_status: Optional[str] = None


class ApiMessage(BaseModel):
    detail: str


class PreviewResponse(BaseModel):
    report_id: int
    filename: str
    report_date: Optional[str] = None
    category: str
    supplier: Optional[str] = None
    pages: int = 0
    rows_detected: int = 0
    rows_parsed: int = 0
    rows_review: int = 0
    extraction_method: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    status: str
