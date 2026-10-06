"""기상청 단기예보 API 비동기 클라이언트.

공공데이터포털: https://www.data.go.kr/data/15084084/openapi.do
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import unquote

import httpx

from . import basetime, codes
from .grid import GridPoint, latlon_to_grid
from .models import (
    DailySummary,
    Forecast,
    HourlyForecast,
    Location,
    Nowcast,
    ShortTermForecast,
)

BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

OP_VILLAGE = "getVilageFcst"  # 단기예보
OP_NOWCAST = "getUltraSrtNcst"  # 초단기실황
OP_ULTRA = "getUltraSrtFcst"  # 초단기예보


class KMAError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class KMAAuthError(KMAError):
    """서비스키 미등록/만료/트래픽 초과 등 인증·쿼터 관련 오류."""


class KMANoDataError(KMAError):
    """해당 발표시각 데이터가 아직 없음 (resultCode 03)."""


_AUTH_CODES = {"20", "22", "30", "31", "32", "33"}


class _TTLCache:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self._data: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        hit = self._data.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        self._data.pop(key, None)
        return None

    def set(self, key: Any, value: Any) -> None:
        self._data[key] = (time.monotonic(), value)


class KMAClient:
    """
    사용 예:
        async with KMAClient(service_key) as kma:
            fc = await kma.forecast(lat=37.5665, lon=126.978)
    """

    def __init__(
        self,
        service_key: str,
        *,
        http: httpx.AsyncClient | None = None,
        base_url: str = BASE_URL,
        timeout: float = 10.0,
        cache_ttl: float = 600.0,
    ):
        if not service_key:
            raise ValueError("service_key가 비어 있습니다 (KMA_SERVICE_KEY).")
        # 포털은 'Encoding'/'Decoding' 두 가지 키를 준다. 어느 쪽을 넣어도 되도록
        # 디코딩해서 보관하고, 인코딩은 httpx에 맡긴다 (이중 인코딩 방지).
        self._key = unquote(service_key) if "%" in service_key else service_key
        self._base_url = base_url.rstrip("/")
        self._http = http or httpx.AsyncClient(timeout=timeout)
        self._own_http = http is None
        self._cache = _TTLCache(cache_ttl)

    async def __aenter__(self) -> "KMAClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._own_http:
            await self._http.aclose()

    # ------------------------------------------------------------------ raw

    async def fetch_items(
        self, operation: str, base: datetime, grid: GridPoint, rows: int = 1000
    ) -> list[dict[str, Any]]:
        """API를 호출해 item 목록을 그대로 돌려준다 (캐시 적용)."""
        key = (operation, base, grid)
        if (cached := self._cache.get(key)) is not None:
            return cached

        items: list[dict[str, Any]] = []
        page = 1
        while True:
            params = {
                "serviceKey": self._key,
                "pageNo": page,
                "numOfRows": rows,
                "dataType": "JSON",
                "nx": grid.nx,
                "ny": grid.ny,
                **basetime.to_params(base),
            }
            resp = await self._http.get(f"{self._base_url}/{operation}", params=params)
            body = self._parse(resp)
            page_items = body.get("items", {}) or {}
            page_items = page_items.get("item", []) if isinstance(page_items, dict) else []
            items.extend(page_items)
            total = int(body.get("totalCount", len(items)))
            if len(items) >= total or not page_items:
                break
            page += 1

        self._cache.set(key, items)
        return items

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        text = resp.text.strip()
        # 인증 오류 등은 dataType=JSON이어도 XML로 온다.
        if text.startswith("<"):
            code = _xml_tag(text, "returnReasonCode") or _xml_tag(text, "resultCode") or "99"
            msg = _xml_tag(text, "returnAuthMsg") or _xml_tag(text, "resultMsg") or text[:200]
            if code in _AUTH_CODES or "KEY" in msg.upper():
                raise KMAAuthError(code, msg)
            raise KMAError(code, msg)
        if resp.status_code >= 400:
            raise KMAError(str(resp.status_code), text[:200] or resp.reason_phrase)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise KMAError("PARSE", f"응답을 해석할 수 없습니다: {text[:200]}") from e

        header = data.get("response", {}).get("header", {})
        code = str(header.get("resultCode", "99"))
        msg = header.get("resultMsg", "")
        if code == "00":
            return data["response"].get("body", {})
        if code == "03":
            raise KMANoDataError(code, msg or "NO_DATA")
        if code in _AUTH_CODES:
            raise KMAAuthError(code, msg)
        raise KMAError(code, msg)

    # ----------------------------------------------------------- high level

    async def forecast(
        self, lat: float, lon: float, *, now: datetime | None = None, name: str | None = None
    ) -> Forecast:
        """단기예보 (약 3~4일, 1시간 간격)."""
        grid = latlon_to_grid(lat, lon)
        base = basetime.village_base(now)
        try:
            items = await self.fetch_items(OP_VILLAGE, base, grid)
        except KMANoDataError:
            # 발표 직후 반영이 늦는 경우가 있어 한 단계 이전 발표분으로 재시도
            base = basetime.previous_village_base(base)
            items = await self.fetch_items(OP_VILLAGE, base, grid)

        hourly, extremes = _build_hourly(items)
        return Forecast(
            location=Location(lat=lat, lon=lon, nx=grid.nx, ny=grid.ny, name=name),
            base_time=base,
            hourly=hourly,
            daily=_build_daily(hourly, extremes),
        )

    async def nowcast(
        self, lat: float, lon: float, *, now: datetime | None = None, name: str | None = None
    ) -> Nowcast:
        """초단기실황 (현재 관측값)."""
        grid = latlon_to_grid(lat, lon)
        base = basetime.nowcast_base(now)
        try:
            items = await self.fetch_items(OP_NOWCAST, base, grid, rows=100)
        except KMANoDataError:
            base -= timedelta(hours=1)
            items = await self.fetch_items(OP_NOWCAST, base, grid, rows=100)

        v = {it["category"]: str(it.get("obsrValue")) for it in items}
        wind_deg = codes.to_float(v.get("VEC"))
        reh = codes.to_float(v.get("REH"))
        return Nowcast(
            location=Location(lat=lat, lon=lon, nx=grid.nx, ny=grid.ny, name=name),
            observed_at=base,
            temperature=codes.to_float(v.get("T1H")),
            precip_type=codes.PTY.get(v.get("PTY", "")),
            precip_1h_mm=codes.parse_amount(v.get("RN1")),
            humidity=int(reh) if reh is not None else None,
            wind_speed=codes.to_float(v.get("WSD")),
            wind_deg=wind_deg,
            wind_dir=codes.wind_direction(wind_deg),
        )

    async def ultra_forecast(
        self, lat: float, lon: float, *, now: datetime | None = None, name: str | None = None
    ) -> ShortTermForecast:
        """초단기예보 (앞으로 약 6시간, 1시간 간격)."""
        grid = latlon_to_grid(lat, lon)
        base = basetime.ultra_forecast_base(now)
        try:
            items = await self.fetch_items(OP_ULTRA, base, grid, rows=100)
        except KMANoDataError:
            base -= timedelta(hours=1)
            items = await self.fetch_items(OP_ULTRA, base, grid, rows=100)
        hourly, _ = _build_hourly(items)
        return ShortTermForecast(
            location=Location(lat=lat, lon=lon, nx=grid.nx, ny=grid.ny, name=name),
            base_time=base,
            hourly=hourly,
        )


# ---------------------------------------------------------------- helpers


def _xml_tag(text: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    return m.group(1).strip() if m else None


def _build_hourly(
    items: list[dict[str, Any]],
) -> tuple[list[HourlyForecast], dict[str, dict[str, float]]]:
    """item 목록을 시각별로 묶는다. TMN/TMX는 날짜별 극값으로 따로 모은다."""
    by_time: dict[datetime, dict[str, str]] = defaultdict(dict)
    extremes: dict[str, dict[str, float]] = defaultdict(dict)  # date -> {TMN, TMX}

    for it in items:
        cat = it["category"]
        val = str(it.get("fcstValue"))
        if cat in ("TMN", "TMX"):
            f = codes.to_float(val)
            if f is not None:
                extremes[it["fcstDate"]][cat] = f
            continue
        t = basetime.parse_kma_datetime(it["fcstDate"], it["fcstTime"])
        by_time[t][cat] = val

    hourly: list[HourlyForecast] = []
    for t in sorted(by_time):
        v = by_time[t]
        pcp = v.get("PCP", v.get("RN1"))
        pop = codes.to_float(v.get("POP"))
        reh = codes.to_float(v.get("REH"))
        wind_deg = codes.to_float(v.get("VEC"))
        hourly.append(
            HourlyForecast(
                time=t,
                temperature=codes.to_float(v.get("TMP", v.get("T1H"))),
                sky=codes.SKY.get(v.get("SKY", "")),
                precip_type=codes.PTY.get(v.get("PTY", "")),
                precip_prob=int(pop) if pop is not None else None,
                precip_mm=codes.parse_amount(pcp),
                precip_text=pcp,
                snow_cm=codes.parse_amount(v.get("SNO")),
                snow_text=v.get("SNO"),
                humidity=int(reh) if reh is not None else None,
                wind_speed=codes.to_float(v.get("WSD")),
                wind_deg=wind_deg,
                wind_dir=codes.wind_direction(wind_deg),
                lightning=codes.to_float(v.get("LGT")),
            )
        )
    return hourly, extremes


def _build_daily(
    hourly: list[HourlyForecast], extremes: dict[str, dict[str, float]]
) -> list[DailySummary]:
    by_date: dict[str, list[HourlyForecast]] = defaultdict(list)
    for h in hourly:
        by_date[h.time.strftime("%Y%m%d")].append(h)

    days: list[DailySummary] = []
    for d in sorted(by_date):
        hs = by_date[d]
        temps = [h.temperature for h in hs if h.temperature is not None]
        pops = [h.precip_prob for h in hs if h.precip_prob is not None]
        amounts = [h.precip_mm for h in hs if h.precip_mm is not None]
        ex = extremes.get(d, {})

        min_t = ex.get("TMN", min(temps) if temps else None)
        max_t = ex.get("TMX", max(temps) if temps else None)
        max_pop = max(pops) if pops else None
        rainy = [h for h in hs if h.precip_type not in (None, "없음")]
        umbrella = bool(rainy) or (max_pop is not None and max_pop >= 60)

        days.append(
            DailySummary(
                date=datetime.strptime(d, "%Y%m%d").date(),
                min_temp=min_t,
                max_temp=max_t,
                max_precip_prob=max_pop,
                total_precip_mm=round(sum(amounts), 1) if amounts else None,
                umbrella=umbrella,
                summary=_summarize(hs, rainy),
            )
        )
    return days


def _summarize(hs: list[HourlyForecast], rainy: list[HourlyForecast]) -> str:
    if rainy:
        kinds = sorted({h.precip_type for h in rainy if h.precip_type})
        start = min(h.time for h in rainy).hour
        end = max(h.time for h in rainy).hour
        when = f"{start}시" if start == end else f"{start}~{end}시"
        return f"{'/'.join(kinds)} ({when})"
    skies = [h.sky for h in hs if h.sky]
    if not skies:
        return "정보 없음"
    return max(set(skies), key=skies.count)
