"""기상청 예보 코드값 해석."""

from __future__ import annotations

import re

CATEGORIES = {
    "POP": "강수확률(%)",
    "PTY": "강수형태",
    "PCP": "1시간 강수량",
    "RN1": "1시간 강수량",
    "REH": "습도(%)",
    "SNO": "1시간 신적설",
    "SKY": "하늘상태",
    "TMP": "1시간 기온(℃)",
    "T1H": "기온(℃)",
    "TMN": "일 최저기온(℃)",
    "TMX": "일 최고기온(℃)",
    "UUU": "풍속 동서성분(m/s)",
    "VVV": "풍속 남북성분(m/s)",
    "WAV": "파고(m)",
    "VEC": "풍향(deg)",
    "WSD": "풍속(m/s)",
    "LGT": "낙뢰(kA)",
}

SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}

PTY = {
    "0": "없음",
    "1": "비",
    "2": "비/눈",
    "3": "눈",
    "4": "소나기",
    # 초단기(실황/예보)에서만 쓰는 코드
    "5": "빗방울",
    "6": "빗방울눈날림",
    "7": "눈날림",
}

_WIND_16 = [
    "북", "북북동", "북동", "동북동", "동", "동남동", "남동", "남남동",
    "남", "남남서", "남서", "서남서", "서", "서북서", "북서", "북북서",
]

_NUM = r"(\d+(?:\.\d+)?)"


def is_missing(value: str | None) -> bool:
    """기상청 결측값: 빈 값, '-', 또는 ±900 이상."""
    if value is None:
        return True
    v = value.strip()
    if v in ("", "-"):
        return True
    try:
        return abs(float(v)) >= 900
    except ValueError:
        return False


def to_float(value: str | None) -> float | None:
    if is_missing(value):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except ValueError:
        return None


def parse_amount(value: str | None) -> float | None:
    """강수량/적설 문자열을 숫자로 변환.

    기상청은 범주형 문자열로 준다. 반환값은 대표값(추정)이며 원문은 따로 보관할 것.
      '강수없음', '적설없음', '0'     → 0.0
      '1mm 미만', '0.5cm 미만'       → 기준값의 절반 (0.5, 0.25)
      '1.0mm', '6.2'                 → 그 값
      '30.0~50.0mm'                  → 구간 중앙값 (40.0)
      '50.0mm 이상'                  → 하한값 (50.0)
    """
    if value is None:
        return None
    v = value.strip()
    if "없음" in v:
        return 0.0
    if is_missing(v):
        return None
    if m := re.fullmatch(_NUM + r"\s*(?:mm|cm)?\s*~\s*" + _NUM + r"\s*(?:mm|cm)?", v):
        return (float(m.group(1)) + float(m.group(2))) / 2
    if m := re.fullmatch(_NUM + r"\s*(?:mm|cm)?\s*미만", v):
        return float(m.group(1)) / 2
    if m := re.fullmatch(_NUM + r"\s*(?:mm|cm)?\s*이상", v):
        return float(m.group(1))
    if m := re.fullmatch(_NUM + r"\s*(?:mm|cm)?", v):
        return float(m.group(1))
    return None


def wind_direction(deg: float | None) -> str | None:
    """풍향(도) → 16방위 한글. 기상청 변환식: (VEC + 22.5*0.5) / 22.5."""
    if deg is None:
        return None
    idx = int((deg % 360 + 22.5 * 0.5) // 22.5) % 16
    return _WIND_16[idx]
