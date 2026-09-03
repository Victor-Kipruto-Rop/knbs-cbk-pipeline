from __future__ import annotations

from typing import List

from pydantic import BaseModel


class Indicator(BaseModel):
    indicator_code: str
    indicator_name: str
    period_date: str
    value: float
    unit: str
    source_id: str


class PaginationMeta(BaseModel):
    page: int | None
    page_size: int | None
    total: int | None
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_more: bool | None = None


class PaginatedIndicators(BaseModel):
    meta: PaginationMeta
    items: List[Indicator]
