"""실제 기상청 응답 형식을 흉내 낸 가짜 서버."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import pytest

from kma_weather import KMAClient
from kma_weather.basetime import KST

AUTH_ERROR_XML = """<OpenAPI_ServiceResponse>
<cmmMsgHeader>
<errMsg>SERVICE ERROR</errMsg>
<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>
<returnReasonCode>30</returnReasonCode>
</cmmMsgHeader>
</OpenAPI_ServiceResponse>"""


def ok(items: list[dict]) -> dict:
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {
                "dataType": "JSON",
                "items": {"item": items},
                "pageNo": 1,
                "numOfRows": 1000,
                "totalCount": len(items),
            },
        }
    }


NO_DATA = {"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}}


def village_items(base: datetime, nx: int, ny: int, hours: int = 48) -> list[dict]:
    """base 다음 시각부터 hours 시간치 단기예보. 다음날 오후에 비."""
    items = []
    bd, bt = base.strftime("%Y%m%d"), base.strftime("%H%M")
    rain_day = (base + timedelta(days=1)).date()
    for i in range(1, hours + 1):
        t = base + timedelta(hours=i)
        fd, ft = t.strftime("%Y%m%d"), t.strftime("%H%M")
        rainy = t.date() == rain_day and 14 <= t.hour <= 17
        vals = {
            "TMP": str(15 + (t.hour % 12) - 4),
            "SKY": "4" if rainy else "1",
            "PTY": "1" if rainy else "0",
            "POP": "80" if rainy else "10",
            "PCP": "1.0mm" if rainy else "강수없음",
            "SNO": "적설없음",
            "REH": "60",
            "WSD": "2.5",
            "VEC": "270",
            "UUU": "2.5",
            "VVV": "0.0",
            "WAV": "0",
        }
        if t.hour == 6:
            vals["TMN"] = "9.0"
        if t.hour == 15:
            vals["TMX"] = "22.0"
        for cat, v in vals.items():
            items.append(
                {"baseDate": bd, "baseTime": bt, "category": cat,
                 "fcstDate": fd, "fcstTime": ft, "fcstValue": v, "nx": nx, "ny": ny}
            )
    return items


class FakeKMA:
    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.no_data_for: set[str] = set()  # base_time 값들
        self.auth_error = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.auth_error:
            return httpx.Response(200, text=AUTH_ERROR_XML)
        q = request.url.params
        op = request.url.path.rsplit("/", 1)[-1]
        if q["base_time"] in self.no_data_for:
            return httpx.Response(200, json=NO_DATA)
        base = datetime.strptime(q["base_date"] + q["base_time"], "%Y%m%d%H%M").replace(tzinfo=KST)
        nx, ny = int(q["nx"]), int(q["ny"])
        if op == "getVilageFcst":
            return httpx.Response(200, json=ok(village_items(base, nx, ny)))
        if op == "getUltraSrtNcst":
            obs = {"T1H": "18.3", "RN1": "0", "REH": "55", "PTY": "0",
                   "VEC": "45", "WSD": "1.8", "UUU": "-1.2", "VVV": "-1.2"}
            return httpx.Response(200, json=ok([
                {"baseDate": q["base_date"], "baseTime": q["base_time"], "category": k,
                 "nx": nx, "ny": ny, "obsrValue": v} for k, v in obs.items()
            ]))
        if op == "getUltraSrtFcst":
            items = []
            for i in range(1, 7):
                t = base + timedelta(minutes=30, hours=i - 1)
                for k, v in {"T1H": "17", "SKY": "3", "PTY": "5", "RN1": "1mm 미만",
                             "REH": "70", "LGT": "0", "VEC": "180", "WSD": "3"}.items():
                    items.append({"baseDate": q["base_date"], "baseTime": q["base_time"],
                                  "category": k, "fcstDate": t.strftime("%Y%m%d"),
                                  "fcstTime": t.strftime("%H00"), "fcstValue": v,
                                  "nx": nx, "ny": ny})
            return httpx.Response(200, json=ok(items))
        return httpx.Response(404, text="unknown op")


@pytest.fixture
def fake() -> FakeKMA:
    return FakeKMA()


@pytest.fixture
def client(fake: FakeKMA) -> KMAClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    return KMAClient("test%2Bkey%3D%3D", http=http)
