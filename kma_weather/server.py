"""FastAPI 서버.

실행:
    set KMA_SERVICE_KEY=발급받은키        (Windows cmd)
    $env:KMA_SERVICE_KEY="발급받은키"     (PowerShell)
    uvicorn kma_weather.server:app --reload

브라우저에서 http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import places
from .client import KMAAuthError, KMAClient, KMAError
from .grid import latlon_to_grid
from .models import Forecast, Nowcast, ShortTermForecast


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    key = os.environ.get("KMA_SERVICE_KEY", "")
    app.state.kma = KMAClient(key) if key else None
    yield
    if app.state.kma:
        await app.state.kma.aclose()


app = FastAPI(
    title="KMA Weather API",
    description="기상청 단기예보를 정리해서 돌려주는 API",
    version="0.1.0",
    lifespan=lifespan,
)


def get_client(request: Request) -> KMAClient:
    kma = getattr(request.app.state, "kma", None)
    if kma is None:
        raise HTTPException(503, "KMA_SERVICE_KEY 환경변수가 설정되지 않았습니다.")
    return kma


def resolve_location(
    lat: float | None = Query(None, ge=-90, le=90, description="위도"),
    lon: float | None = Query(None, ge=-180, le=180, description="경도"),
    city: str | None = Query(None, description="도시명 (예: 서울, 부산광역시)"),
) -> tuple[float, float, str | None]:
    if city:
        coords = places.lookup(city)
        if coords is None:
            raise HTTPException(404, f"알 수 없는 도시: {city}. /cities 참고")
        return coords[0], coords[1], city
    if lat is None or lon is None:
        raise HTTPException(422, "lat/lon 또는 city 중 하나는 필요합니다.")
    return lat, lon, None


@app.exception_handler(KMAAuthError)
async def _auth_error(_: Request, exc: KMAAuthError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"기상청 인증 오류: {exc.message}", "code": exc.code})


@app.exception_handler(KMAError)
async def _kma_error(_: Request, exc: KMAError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": f"기상청 API 오류: {exc.message}", "code": exc.code})


@app.get("/health")
async def health(request: Request) -> dict:
    return {"ok": True, "service_key": getattr(request.app.state, "kma", None) is not None}


@app.get("/cities")
async def cities() -> dict[str, list[float]]:
    return {k: list(v) for k, v in places.PLACES.items()}


@app.get("/grid")
async def grid(loc=Depends(resolve_location)) -> dict:
    lat, lon, name = loc
    g = latlon_to_grid(lat, lon)
    return {"lat": lat, "lon": lon, "nx": g.nx, "ny": g.ny, "name": name}


@app.get("/forecast", response_model=Forecast)
async def forecast(
    loc=Depends(resolve_location),
    hours: int | None = Query(None, ge=1, le=120, description="시간별 예보를 앞에서 N개만"),
    kma: KMAClient = Depends(get_client),
) -> Forecast:
    lat, lon, name = loc
    fc = await kma.forecast(lat, lon, name=name)
    if hours:
        fc = fc.model_copy(update={"hourly": fc.hourly[:hours]})
    return fc


@app.get("/now", response_model=Nowcast)
async def now(loc=Depends(resolve_location), kma: KMAClient = Depends(get_client)) -> Nowcast:
    lat, lon, name = loc
    return await kma.nowcast(lat, lon, name=name)


@app.get("/forecast/short", response_model=ShortTermForecast)
async def short(
    loc=Depends(resolve_location), kma: KMAClient = Depends(get_client)
) -> ShortTermForecast:
    lat, lon, name = loc
    return await kma.ultra_forecast(lat, lon, name=name)


@app.get("/umbrella")
async def umbrella(loc=Depends(resolve_location), kma: KMAClient = Depends(get_client)) -> dict:
    """오늘 우산 필요한지 한 줄로."""
    lat, lon, name = loc
    fc = await kma.forecast(lat, lon, name=name)
    today = fc.daily[0]
    return {
        "date": today.date,
        "umbrella": today.umbrella,
        "max_precip_prob": today.max_precip_prob,
        "summary": today.summary,
        "message": ("우산 챙기세요 ☔ " if today.umbrella else "우산 필요 없어요 ☀️ ")
        + f"({today.summary}, 최고 강수확률 {today.max_precip_prob}%)",
    }
