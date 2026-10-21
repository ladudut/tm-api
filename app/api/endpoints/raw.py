"""
Raw passthrough to Transfermarkt's JSON API for bulk crawling: one call here = one upstream call, payload unmodified.

- GET  /raw/{path}?<query>   e.g. /raw/player/187329/performance-game, /raw/players?ids[]=1&ids[]=2 (batch, <=100 ids)
- POST /raw/batch            body {"paths": ["/player/1/transfer-history", "/game/5018617", ...]} (<= RAW_BATCH_MAX paths),
                             fetched concurrently (bounded by TFMKT_MAX_CONCURRENCY); returns {"results": {path: {status, data|detail}}}

Only whitelisted read-only upstream routes are allowed.
"""

import asyncio
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.dependencies import Tfmkt
from transfermarkt_api.exceptions import EndpointUnavailable, NotFound, UpstreamBlocked, UpstreamError, UpstreamTimeout

router = APIRouter()

RAW_BATCH_MAX = 100
ALLOWED = re.compile(
    r"^/(player|club|coach|competition|game|stadium|country|transfer/history/player)(/[A-Za-z0-9_.-]+)*$"
    r"|^/(players|clubs|coaches|competitions)(/(injury|absence|stadium))?$"
    r"|^/(attributes|quick-search)$"
)
STATUS = {NotFound: 404, UpstreamBlocked: 503, UpstreamTimeout: 504, UpstreamError: 502, EndpointUnavailable: 501}


def _split(path: str) -> tuple[str, list[tuple[str, str]]]:
    parts = urlsplit(path if path.startswith("/") else "/" + path)
    if not ALLOWED.match(parts.path):
        raise HTTPException(status_code=422, detail=f"route not allowed: {parts.path}")
    params = parse_qsl(parts.query, keep_blank_values=True)
    if sum(1 for k, _ in params if k == "ids[]") > 100:
        raise HTTPException(status_code=422, detail="at most 100 ids[] per batch route")
    return parts.path, params


async def _fetch(tfmkt: Tfmkt, path: str) -> dict[str, Any]:
    route, params = _split(path)
    try:
        return {"status": 200, "data": await tfmkt._client.get(route, params=params or None)}
    except tuple(STATUS) as e:
        return {"status": next(s for t, s in STATUS.items() if isinstance(e, t)), "detail": str(e)}


class RawBatch(BaseModel):
    paths: list[str]


@router.post("/batch")
async def raw_batch(body: RawBatch, tfmkt: Tfmkt) -> dict:
    """Fetch up to RAW_BATCH_MAX upstream routes concurrently in one request."""
    if not body.paths or len(body.paths) > RAW_BATCH_MAX:
        raise HTTPException(status_code=422, detail=f"1..{RAW_BATCH_MAX} paths")
    for p in body.paths:
        _split(p)  # validate all before fetching
    results = await asyncio.gather(*(_fetch(tfmkt, p) for p in body.paths))
    return {"results": dict(zip(body.paths, results))}


@router.get("/{path:path}")
async def raw_get(path: str, request: Request, tfmkt: Tfmkt) -> Any:
    """Single upstream route, payload unmodified."""
    q = request.url.query
    res = await _fetch(tfmkt, "/" + path + (f"?{q}" if q else ""))
    if res["status"] != 200:
        raise HTTPException(status_code=res["status"], detail=res["detail"])
    return res["data"]
