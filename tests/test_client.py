import asyncio
from datetime import datetime

import pytest

from kma_weather import KMAAuthError, KMAClient
from kma_weather.basetime import KST

NOW = datetime(2026, 10, 6, 13, 44, tzinfo=KST)
SEOUL = (37.5665, 126.9780)


def run(coro):
    return asyncio.run(coro)


def test_forecast_basic(client, fake):
    fc = run(client.forecast(*SEOUL, now=NOW))

    req = fake.calls[0]
    q = req.url.params
    assert req.url.path.endswith("/getVilageFcst")
    assert (q["base_date"], q["base_time"], q["nx"], q["ny"]) == ("20261006", "1100", "60", "127")
    assert q["dataType"] == "JSON"

    assert fc.location.nx == 60 and fc.location.ny == 127
    assert fc.base_time == datetime(2026, 10, 6, 11, 0, tzinfo=KST)
    assert len(fc.hourly) == 48
    assert fc.hourly[0].time == datetime(2026, 10, 6, 12, 0, tzinfo=KST)
    h = fc.hourly[0]
    assert h.sky == "맑음" and h.precip_type == "없음" and h.wind_dir == "서"
    assert h.humidity == 60 and h.precip_mm == 0.0


def test_service_key_not_double_encoded(client, fake):
    # 'Encoding' 키(test%2Bkey%3D%3D)를 넣어도 한 번만 인코딩돼서 나가야 함
    run(client.forecast(*SEOUL, now=NOW))
    raw_query = fake.calls[0].url.query.decode()
    assert "serviceKey=test%2Bkey%3D%3D" in raw_query
    assert "%25" not in raw_query


def test_daily_summary(client):
    fc = run(client.forecast(*SEOUL, now=NOW))
    today, tomorrow = fc.daily[0], fc.daily[1]

    assert today.umbrella is False
    assert today.summary == "맑음"

    assert tomorrow.min_temp == 9.0 and tomorrow.max_temp == 22.0  # TMN/TMX 우선
    assert tomorrow.umbrella is True
    assert tomorrow.max_precip_prob == 80
    assert tomorrow.summary == "비 (14~17시)"
    assert tomorrow.total_precip_mm == 4.0


def test_no_data_falls_back_to_previous_base(client, fake):
    fake.no_data_for.add("1100")
    fc = run(client.forecast(*SEOUL, now=NOW))
    assert [c.url.params["base_time"] for c in fake.calls] == ["1100", "0800"]
    assert fc.base_time.hour == 8


def test_cache(client, fake):
    run(client.forecast(*SEOUL, now=NOW))
    run(client.forecast(*SEOUL, now=NOW))
    assert len(fake.calls) == 1


def test_auth_error_xml(client, fake):
    fake.auth_error = True
    with pytest.raises(KMAAuthError) as ei:
        run(client.forecast(*SEOUL, now=NOW))
    assert ei.value.code == "30"
    assert "NOT_REGISTERED" in ei.value.message


def test_nowcast(client, fake):
    nc = run(client.nowcast(*SEOUL, now=NOW))
    assert fake.calls[0].url.params["base_time"] == "1300"
    assert nc.temperature == 18.3
    assert nc.precip_type == "없음"
    assert nc.wind_dir == "북동"


def test_ultra_forecast(client, fake):
    sf = run(client.ultra_forecast(*SEOUL, now=NOW))
    assert fake.calls[0].url.params["base_time"] == "1230"
    assert len(sf.hourly) == 6
    assert sf.hourly[0].precip_type == "빗방울"
    assert sf.hourly[0].precip_mm == 0.5
    assert sf.hourly[0].sky == "구름많음"


def test_empty_key_rejected():
    with pytest.raises(ValueError):
        KMAClient("")
