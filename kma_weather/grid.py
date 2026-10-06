"""위경도 <-> 기상청 격자(nx, ny) 변환.

기상청 동네예보 격자는 Lambert Conformal Conic 투영, 5km 간격이다.
상수와 공식은 기상청 OpenAPI 활용가이드의 C 예제를 그대로 옮겼다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

RE = 6371.00877  # 지구 반경 (km)
GRID = 5.0  # 격자 간격 (km)
SLAT1 = 30.0  # 투영 위도1
SLAT2 = 60.0  # 투영 위도2
OLON = 126.0  # 기준점 경도
OLAT = 38.0  # 기준점 위도
XO = 43  # 기준점 X 좌표 (격자)
YO = 136  # 기준점 Y 좌표 (격자)

_DEG = math.pi / 180.0


@dataclass(frozen=True)
class GridPoint:
    nx: int
    ny: int


def _constants() -> tuple[float, float, float, float]:
    re = RE / GRID
    slat1, slat2 = SLAT1 * _DEG, SLAT2 * _DEG
    olon, olat = OLON * _DEG, OLAT * _DEG

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / math.pow(ro, sn)
    return re, sn, sf, ro


def latlon_to_grid(lat: float, lon: float) -> GridPoint:
    """위도/경도(도) → 기상청 격자 좌표."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"잘못된 좌표: lat={lat}, lon={lon}")
    re, sn, sf, ro = _constants()

    ra = math.tan(math.pi * 0.25 + lat * _DEG * 0.5)
    ra = re * sf / math.pow(ra, sn)
    theta = lon * _DEG - OLON * _DEG
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn

    x = math.floor(ra * math.sin(theta) + XO + 0.5)
    y = math.floor(ro - ra * math.cos(theta) + YO + 0.5)
    return GridPoint(int(x), int(y))


def grid_to_latlon(nx: int, ny: int) -> tuple[float, float]:
    """기상청 격자 좌표 → 격자 중심의 위도/경도(도)."""
    re, sn, sf, ro = _constants()

    xn = nx - XO
    yn = ro - ny + YO
    ra = math.sqrt(xn * xn + yn * yn)
    if sn < 0.0:
        ra = -ra
    alat = math.pow((re * sf / ra), (1.0 / sn))
    alat = 2.0 * math.atan(alat) - math.pi * 0.5

    if abs(xn) <= 0.0:
        theta = 0.0
    elif abs(yn) <= 0.0:
        theta = math.pi * 0.5
        if xn < 0.0:
            theta = -theta
    else:
        theta = math.atan2(xn, yn)
    alon = theta / sn + OLON * _DEG
    return alat / _DEG, alon / _DEG
