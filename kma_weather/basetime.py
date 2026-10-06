"""발표시각(base_date, base_time) 계산.

기상청 API는 '가장 최근에 발표된' 시각을 직접 넣어줘야 데이터가 나온다.
발표 직후에는 아직 API에 반영되지 않으므로 제공 지연을 감안한다.

- 단기예보:   02, 05, 08, 11, 14, 17, 20, 23시 발표 → 각 시각 +10분 이후 제공
- 초단기실황: 매시 정시 관측 → 매시 40분 이후 제공
- 초단기예보: 매시 30분 발표 → 매시 45분 이후 제공
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

VILLAGE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
VILLAGE_DELAY = timedelta(minutes=10)
NOWCAST_DELAY = timedelta(minutes=40)
ULTRA_FCST_DELAY = timedelta(minutes=15)  # 30분 발표, 45분 제공


def now_kst() -> datetime:
    return datetime.now(KST)


def _to_kst(dt: datetime | None) -> datetime:
    if dt is None:
        return now_kst()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def village_base(now: datetime | None = None) -> datetime:
    """단기예보의 가장 최근 발표시각."""
    t = _to_kst(now) - VILLAGE_DELAY
    for h in reversed(VILLAGE_HOURS):
        if t.hour >= h:
            return t.replace(hour=h, minute=0, second=0, microsecond=0)
    # 00:00 ~ 02:09 → 전날 23시 발표분
    prev = t - timedelta(days=1)
    return prev.replace(hour=23, minute=0, second=0, microsecond=0)


def previous_village_base(base: datetime) -> datetime:
    """한 단계 이전 단기예보 발표시각 (3시간 전)."""
    return base - timedelta(hours=3)


def nowcast_base(now: datetime | None = None) -> datetime:
    """초단기실황의 가장 최근 관측시각 (HH00)."""
    t = _to_kst(now) - NOWCAST_DELAY
    return t.replace(minute=0, second=0, microsecond=0)


def ultra_forecast_base(now: datetime | None = None) -> datetime:
    """초단기예보의 가장 최근 발표시각 (HH30)."""
    t = _to_kst(now) - ULTRA_FCST_DELAY
    if t.minute >= 30:
        return t.replace(minute=30, second=0, microsecond=0)
    return (t - timedelta(hours=1)).replace(minute=30, second=0, microsecond=0)


def to_params(base: datetime) -> dict[str, str]:
    return {"base_date": base.strftime("%Y%m%d"), "base_time": base.strftime("%H%M")}


def parse_kma_datetime(date: str, time: str) -> datetime:
    return datetime.strptime(date + time, "%Y%m%d%H%M").replace(tzinfo=KST)
