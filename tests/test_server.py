from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from kma_weather import server
from kma_weather.basetime import KST

NOW = datetime(2026, 10, 6, 13, 44, tzinfo=KST)


@pytest.fixture
def api(client, monkeypatch):
    # 시간 고정: 서버 내부에서 now=None으로 호출하므로 now_kst를 바꾼다
    monkeypatch.setattr("kma_weather.basetime.now_kst", lambda: NOW)
    monkeypatch.delenv("KMA_SERVICE_KEY", raising=False)
    with TestClient(server.app) as tc:
        server.app.state.kma = client
        yield tc


def test_health(api):
    assert api.get("/health").json() == {"ok": True, "service_key": True}


def test_grid_by_city(api):
    r = api.get("/grid", params={"city": "부산광역시"}).json()
    assert (r["nx"], r["ny"]) == (98, 76)


def test_forecast_by_latlon(api):
    r = api.get("/forecast", params={"lat": 37.5665, "lon": 126.978, "hours": 3})
    assert r.status_code == 200
    body = r.json()
    assert len(body["hourly"]) == 3
    assert body["location"]["nx"] == 60
    assert len(body["daily"]) >= 2


def test_umbrella(api):
    r = api.get("/umbrella", params={"city": "서울"}).json()
    assert r["umbrella"] is False
    assert r["message"].startswith("우산 필요 없어요")


def test_now(api):
    r = api.get("/now", params={"city": "서울"}).json()
    assert r["temperature"] == 18.3


def test_missing_location(api):
    assert api.get("/forecast").status_code == 422


def test_unknown_city(api):
    assert api.get("/forecast", params={"city": "아틀란티스"}).status_code == 404


def test_upstream_auth_error_maps_to_502(api, fake):
    fake.auth_error = True
    r = api.get("/forecast", params={"city": "서울"})
    assert r.status_code == 502
    assert r.json()["code"] == "30"


def test_no_key_returns_503(monkeypatch):
    monkeypatch.delenv("KMA_SERVICE_KEY", raising=False)
    with TestClient(server.app) as tc:
        assert tc.get("/forecast", params={"city": "서울"}).status_code == 503
