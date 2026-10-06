from datetime import datetime

import pytest

from kma_weather import basetime, codes, places
from kma_weather.basetime import KST
from kma_weather.grid import grid_to_latlon, latlon_to_grid


# ---------------------------------------------------------------- grid

@pytest.mark.parametrize(
    "lat, lon, expected",
    [
        (37.5665, 126.9780, (60, 127)),  # 서울시청
        (35.1796, 129.0756, (98, 76)),   # 부산시청
        (33.4996, 126.5312, (53, 38)),   # 제주시청
        (38.0, 126.0, (43, 136)),        # 기준점
    ],
)
def test_latlon_to_grid(lat, lon, expected):
    g = latlon_to_grid(lat, lon)
    assert (g.nx, g.ny) == expected


def test_grid_roundtrip():
    lat, lon = grid_to_latlon(60, 127)
    assert abs(lat - 37.5665) < 0.05 and abs(lon - 126.978) < 0.05
    assert latlon_to_grid(lat, lon).nx == 60


def test_grid_rejects_bad_coords():
    with pytest.raises(ValueError):
        latlon_to_grid(100, 127)


# ----------------------------------------------------------- basetime

def kst(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=KST)


@pytest.mark.parametrize(
    "now, expected",
    [
        ("2026-10-06 13:44", "2026-10-06 11:00"),
        ("2026-10-06 14:09", "2026-10-06 11:00"),  # 14시 발표는 14:10부터
        ("2026-10-06 14:10", "2026-10-06 14:00"),
        ("2026-10-06 02:05", "2026-10-05 23:00"),  # 자정 넘김
        ("2026-10-06 00:30", "2026-10-05 23:00"),
        ("2026-10-06 23:59", "2026-10-06 23:00"),
    ],
)
def test_village_base(now, expected):
    assert basetime.village_base(kst(now)) == kst(expected)


@pytest.mark.parametrize(
    "now, expected",
    [
        ("2026-10-06 13:39", "2026-10-06 12:00"),
        ("2026-10-06 13:40", "2026-10-06 13:00"),
        ("2026-10-06 00:10", "2026-10-05 23:00"),
    ],
)
def test_nowcast_base(now, expected):
    assert basetime.nowcast_base(kst(now)) == kst(expected)


@pytest.mark.parametrize(
    "now, expected",
    [
        ("2026-10-06 13:44", "2026-10-06 12:30"),
        ("2026-10-06 13:45", "2026-10-06 13:30"),
        ("2026-10-06 00:20", "2026-10-05 23:30"),
    ],
)
def test_ultra_forecast_base(now, expected):
    assert basetime.ultra_forecast_base(kst(now)) == kst(expected)


def test_naive_datetime_treated_as_kst():
    assert basetime.village_base(datetime(2026, 10, 6, 15, 0)).hour == 14


def test_utc_datetime_converted():
    from datetime import timezone
    utc = datetime(2026, 10, 6, 5, 30, tzinfo=timezone.utc)  # = 14:30 KST
    assert basetime.village_base(utc) == kst("2026-10-06 14:00")


# -------------------------------------------------------------- codes

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("강수없음", 0.0),
        ("적설없음", 0.0),
        ("1mm 미만", 0.5),
        ("1.0mm 미만", 0.5),
        ("0.5cm 미만", 0.25),
        ("6.2mm", 6.2),
        ("6.2", 6.2),
        ("30.0~50.0mm", 40.0),
        ("50.0mm 이상", 50.0),
        ("-", None),
        ("-999", None),
        (None, None),
    ],
)
def test_parse_amount(raw, expected):
    assert codes.parse_amount(raw) == expected


@pytest.mark.parametrize(
    "deg, expected", [(0, "북"), (359, "북"), (45, "북동"), (90, "동"), (200, "남남서"), (270, "서")]
)
def test_wind_direction(deg, expected):
    assert codes.wind_direction(deg) == expected


def test_missing_values():
    assert codes.to_float("-998.9") is None
    assert codes.to_float("12.5") == 12.5


# ------------------------------------------------------------- places

@pytest.mark.parametrize("name", ["서울", "서울특별시", "서울시", " 서울 "])
def test_places_lookup(name):
    assert places.lookup(name) == places.PLACES["서울"]


def test_places_lookup_metro():
    assert places.lookup("부산광역시") == places.PLACES["부산"]
    assert places.lookup("세종특별자치시") == places.PLACES["세종"]
    assert places.lookup("없는곳") is None
