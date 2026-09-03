from __future__ import annotations

from typing import List
import csv
import io
import datetime as dt

from knbs_cbk_pipeline.api.utils.cursors import encode_cursor, decode_cursor, InvalidCursor
from knbs_cbk_pipeline.api.cache import compute_etag, cache_get, cache_set, make_cache_key
from knbs_cbk_pipeline.api.auth import get_api_key
from fastapi import Depends
from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import text, bindparam
import hashlib

from knbs_cbk_pipeline.warehouse.loaders.postgres_loader import get_engine
from knbs_cbk_pipeline.api.schemas import PaginatedIndicators
import base64
import json


router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.get(
    "/top",
    response_model=PaginatedIndicators,
    summary="Get recent indicators",
    description="Returns recent economic indicators with optional filters, pagination, and CSV export.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "meta": {
                            "page": 1,
                            "page_size": 3,
                            "total": 9,
                            "next_cursor": "<base64-cursor>",
                            "prev_cursor": None,
                            "has_more": True,
                        },
                        "items": [
                            {
                                "indicator_code": "cbk_repo_rate",
                                "indicator_name": "REPO",
                                "period_date": "2026-09-03",
                                "value": 9.25,
                                "unit": "percent",
                                "source_id": "cbk_key_rates",
                            }
                        ],
                    }
                },
                "text/csv": {"example": "indicator_code,indicator_name,period_date,value,unit,source_id\ncbk_repo_rate,REPO,2026-09-03,9.25,percent,cbk_key_rates\n"},
            }
        }
    },
    dependencies=[Depends(get_api_key)],
)
def top_indicators(
    request: Request,
    response: Response,
    limit: int = Query(20, ge=1, le=100),
    indicator_code: List[str] | None = Query(None),
    source_id: List[str] | None = Query(None),
    indicator_name: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    format: str = Query("json"),
) -> PaginatedIndicators | StreamingResponse:
    """Return recent rows from the fact table.

    - Filtering: `indicator_code` (repeatable), `source_id` (repeatable),
      `indicator_name` (partial, case-insensitive), `start_date` and
      `end_date` (ISO YYYY-MM-DD).
    - Pagination: `page` and `page_size`, or cursor-based `cursor` param.
    - Output: `format=json|csv` (default JSON).
    """
    engine = get_engine()

    base_sql = (
        "SELECT indicator_code, indicator_name, period_date, value, unit, source_id "
        "FROM marts_marts.fct_economic_indicators"
    )

    conditions: List[str] = []
    bindparams_list = []
    params: dict = {}

    if indicator_code:
        conditions.append("indicator_code IN :indicator_codes")
        bindparams_list.append(bindparam("indicator_codes", expanding=True))
        params["indicator_codes"] = tuple(indicator_code)

    if source_id:
        conditions.append("source_id IN :source_ids")
        bindparams_list.append(bindparam("source_ids", expanding=True))
        params["source_ids"] = tuple(source_id)

    if indicator_name:
        conditions.append("indicator_name ILIKE :indicator_name")
        params["indicator_name"] = f"%{indicator_name}%"

    # date filters (expect ISO YYYY-MM-DD)
    if start_date:
        try:
            sd = dt.date.fromisoformat(start_date)
        except ValueError:
            sd = None
        if sd:
            conditions.append("period_date >= :start_date")
            params["start_date"] = sd

    if end_date:
        try:
            ed = dt.date.fromisoformat(end_date)
        except ValueError:
            ed = None
        if ed:
            conditions.append("period_date <= :end_date")
            params["end_date"] = ed

    # pagination: default page-based
    offset = (page - 1) * page_size
    limit_sql = " LIMIT :limit OFFSET :offset"
    params["limit"] = page_size
    params["offset"] = offset

    # deterministic ordering: period_date DESC, indicator_code DESC, ingested_at DESC
    order_sql = " ORDER BY period_date DESC, indicator_code DESC, ingested_at DESC"

    # decode cursor if present: cursor is signed and contains (period_date, indicator_code, ingested_at)
    if cursor:
        try:
            decoded = decode_cursor(cursor)
            # expect {'period_date': 'YYYY-MM-DD', 'indicator_code': 'code', 'ingested_at': 'ISO'}
            conditions.append(
                "(period_date < :cursor_date OR (period_date = :cursor_date AND (indicator_code < :cursor_code OR (indicator_code = :cursor_code AND ingested_at < :cursor_ingested))))"
            )
            params["cursor_date"] = decoded.get("period_date")
            params["cursor_code"] = decoded.get("indicator_code")
            params["cursor_ingested"] = decoded.get("ingested_at")
            # when using cursor, reset offset to 0
            params["offset"] = 0
        except InvalidCursor:
            # ignore invalid/expired cursor and fall back to page-based
            cursor = None

    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    sql = text(base_sql + where_sql + order_sql + limit_sql)
    if bindparams_list:
        sql = sql.bindparams(*bindparams_list)

    # compute total count matching filters for pagination metadata
    count_sql = text("SELECT COUNT(*) AS total FROM marts_marts.fct_economic_indicators" + where_sql)
    if bindparams_list:
        count_sql = count_sql.bindparams(*bindparams_list)

    with engine.connect() as conn:
        total_row = conn.execute(count_sql, params).first()
        total = int(total_row[0]) if total_row is not None else 0
        rows = conn.execute(sql, params).mappings().all()

    results = [dict(r) for r in rows]
    # normalize date objects to ISO strings for JSON/Pydantic validation
    for r in results:
        pd = r.get("period_date")
        if hasattr(pd, "isoformat"):
            r["period_date"] = pd.isoformat()

    meta = {
        "page": page if not cursor else None,
        "page_size": page_size if not cursor else None,
        "total": total,
        "next_cursor": None,
        "prev_cursor": None,
        "has_more": False,
    }

    # Attempt to serve from cache (keyed by filters+cursor+page_size+format)
    filters = {
        "indicator_code": indicator_code,
        "source_id": source_id,
        "indicator_name": indicator_name,
        "start_date": start_date,
        "end_date": end_date,
    }
    cache_key = make_cache_key(filters, cursor, page_size, format)
    cached = cache_get(cache_key)
    incoming = request.headers.get("if-none-match")
    if cached:
        # cached is bytes from redis; ensure str
        if isinstance(cached, bytes):
            cached = cached.decode()
        # compute etag from cached payload
        etag = hashlib.sha256(cached.encode()).hexdigest()
        if incoming and incoming == etag:
            return Response(status_code=304)
        response.headers["ETag"] = etag
        response.headers["X-Cache"] = "HIT"
        return json.loads(cached)

    # compute next/prev cursors based on last/first item
    next_cursor = None
    prev_cursor = None
    has_more = False
    if results:
        last = results[-1]
        first = results[0]
        next_cursor = encode_cursor({
            "period_date": last["period_date"],
            "indicator_code": last["indicator_code"],
            "ingested_at": last.get("ingested_at"),
        })
        prev_cursor = encode_cursor({
            "period_date": first["period_date"],
            "indicator_code": first["indicator_code"],
            "ingested_at": first.get("ingested_at"),
        })
        # a simple heuristic: if total > page*page_size then there are more pages
        has_more = total > page * page_size

    # prepare Link header following RFC 5988
    link_parts: List[str] = []
    if next_cursor:
        if request is not None:
            next_url = str(request.url.include_query_params(cursor=next_cursor, page_size=page_size))
        else:
            next_url = f"/indicators/top?cursor={next_cursor}&page_size={page_size}"
        link_parts.append(f"<{next_url}>; rel=\"next\"")
    if prev_cursor:
        if request is not None:
            prev_url = str(request.url.include_query_params(cursor=prev_cursor, page_size=page_size))
        else:
            prev_url = f"/indicators/top?cursor={prev_cursor}&page_size={page_size}"
        link_parts.append(f"<{prev_url}>; rel=\"prev\"")

    if format.lower() == "csv":
        # Stream CSV directly from DB to avoid building large in-memory strings
        fieldnames = ["indicator_code", "indicator_name", "period_date", "value", "unit", "source_id"]

        def row_iterator():
            # header
            yield ",".join(fieldnames) + "\n"
            # open a new streaming connection
            with engine.connect() as stream_conn:
                stmt = text(base_sql + where_sql + order_sql + limit_sql)
                if bindparams_list:
                    stmt = stmt.bindparams(*bindparams_list)
                result = stream_conn.execution_options(stream_results=True).execute(stmt, params)
                for r in result.mappings():
                    row = dict(r)
                    pd = row.get("period_date")
                    if hasattr(pd, "isoformat"):
                        row["period_date"] = pd.isoformat()
                    vals = [str(row.get(c, "")) for c in fieldnames]
                    yield ",".join(vals) + "\n"

        csv_resp = StreamingResponse(row_iterator(), media_type="text/csv")
        csv_resp.headers["Content-Disposition"] = "attachment; filename=indicators.csv"
        if link_parts:
            csv_resp.headers["Link"] = ", ".join(link_parts)
        return csv_resp

    meta.update({
        "next_cursor": next_cursor,
        "prev_cursor": prev_cursor,
        "has_more": has_more,
    })

    if response is not None and link_parts:
        response.headers["Link"] = ", ".join(link_parts)

    body = {"meta": meta, "items": results}
    body_str = json.dumps(body, default=str)
    etag = hashlib.sha256(body_str.encode()).hexdigest()
    response.headers["ETag"] = etag
    response.headers["X-Cache"] = "MISS"
    try:
        cache_set(cache_key, body_str, ttl=300)
        cache_set(f"indicators:etag:{etag}", body_str, ttl=300)
    except Exception:
        pass

    return body
