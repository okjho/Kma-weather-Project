# kma-weather

기상청 단기예보 API(공공데이터포털 `VilageFcstInfoService_2.0`)를 쓰기 편하게 감싼 Python 라이브러리 + FastAPI 서버.

기상청 API를 그냥 쓰면 귀찮은 것들을 대신 처리합니다.

- **위경도 → 격자(nx, ny) 변환**: 기상청은 위경도가 아니라 5km 격자 좌표를 받습니다.
- **발표시각 자동 계산**: 단기예보는 하루 8번(02·05·…·23시) 발표되고 10분 뒤에야 조회됩니다. 가장 최근 발표분을 알아서 고르고, 아직 반영이 안 됐으면(NO_DATA) 이전 발표분으로 재시도합니다.
- **코드값 해석**: `SKY=3` → `구름많음`, `PTY=1` → `비`, `PCP="30.0~50.0mm"` → `40.0` 등.
- **시간별·일별 정리**: 카테고리별로 흩어진 응답을 시간 단위로 묶고, 날짜별 최저/최고기온·우산 필요 여부를 요약합니다.
- **서비스키 인코딩 문제 방지**: 포털의 Encoding/Decoding 키 어느 쪽을 넣어도 동작합니다.
- **인증 오류 처리**: JSON을 요청해도 XML로 오는 인증 오류를 해석해 `KMAAuthError`로 던집니다.
- **캐시**: 같은 발표분·같은 격자는 10분간 재호출하지 않습니다 (일일 트래픽 제한 절약).

## 1. 서비스키 발급

1. [공공데이터포털](https://www.data.go.kr) 가입
2. "기상청_단기예보 ((구)_동네예보) 조회서비스" 검색 → **활용신청**
3. 마이페이지 → 개발계정에서 **일반 인증키(Decoding)** 복사

승인 직후 1~2시간은 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`가 날 수 있습니다. 기다리면 풀립니다.

## 2. 설치 (Windows, PowerShell)

```powershell
cd kma-weather

# uv 사용 시 (추천)
uv venv
.venv\Scripts\activate
uv pip install -e ".[server,dev]"

# 또는 기본 pip
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[server,dev]"
```

> PowerShell에서 `activate`가 막히면 한 번만 실행:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

테스트 (실제 API 호출 없이 동작):

```powershell
pytest
```

## 3. 서버 실행

```powershell
$env:KMA_SERVICE_KEY="발급받은_키"
uvicorn kma_weather.server:app --reload
```

브라우저에서 <http://127.0.0.1:8000/docs> 를 열면 모든 엔드포인트를 바로 눌러볼 수 있습니다.

| 엔드포인트 | 설명 |
|---|---|
| `GET /forecast?city=서울` | 단기예보 (약 3일, 시간별 + 일별 요약). `&hours=12`로 앞 12시간만 |
| `GET /forecast?lat=37.5&lon=127.0` | 위경도로 조회 |
| `GET /forecast/short?city=서울` | 초단기예보 (앞으로 6시간) |
| `GET /now?city=서울` | 초단기실황 (현재 관측값) |
| `GET /umbrella?city=서울` | 오늘 우산 필요한지 한 줄 답 |
| `GET /grid?lat=..&lon=..` | 격자 좌표만 변환 |
| `GET /cities` | `city=`로 쓸 수 있는 도시 목록 |

## 4. 라이브러리로 쓰기

```python
import asyncio
from kma_weather import KMAClient

async def main():
    async with KMAClient("발급받은_키") as kma:
        fc = await kma.forecast(37.5665, 126.9780)
        for day in fc.daily:
            print(day.date, day.min_temp, day.max_temp, day.summary,
                  "☔" if day.umbrella else "")

        now = await kma.nowcast(37.5665, 126.9780)
        print("지금", now.temperature, "℃", now.wind_dir, now.wind_speed, "m/s")

asyncio.run(main())
```

## 구조

```
kma_weather/
  grid.py      위경도 <-> 격자 변환 (Lambert Conformal Conic)
  basetime.py  발표시각 계산 (단기/초단기실황/초단기예보)
  codes.py     코드값·강수량 문자열·풍향 해석
  models.py    응답 모델 (pydantic)
  client.py    비동기 API 클라이언트 + 시간별/일별 정리
  places.py    주요 도시 좌표
  server.py    FastAPI 서버
tests/         가짜 기상청 서버로 돌리는 테스트
```

## 다음에 해볼 만한 것

- 기상청 **중기예보**(3~10일) API 붙이기
- 동/읍/면 이름으로 검색 (기상청 격자-행정구역 엑셀 활용)
- 매일 아침 텔레그램/디스코드로 `/umbrella` 결과 보내기
- 예보 vs 실황을 쌓아서 예보 정확도 비교해보기
