from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float | None = None
    lon: float | None = None
    nx: int
    ny: int
    name: str | None = None


class HourlyForecast(BaseModel):
    time: datetime
    temperature: float | None = Field(None, description="기온(℃)")
    sky: str | None = Field(None, description="맑음/구름많음/흐림")
    precip_type: str | None = Field(None, description="없음/비/비/눈/눈/소나기 ...")
    precip_prob: int | None = Field(None, description="강수확률(%)")
    precip_mm: float | None = Field(None, description="1시간 강수량 대표값(mm)")
    precip_text: str | None = Field(None, description="기상청 원문 강수량")
    snow_cm: float | None = None
    snow_text: str | None = None
    humidity: int | None = Field(None, description="습도(%)")
    wind_speed: float | None = Field(None, description="풍속(m/s)")
    wind_deg: float | None = None
    wind_dir: str | None = Field(None, description="16방위 한글")
    lightning: float | None = Field(None, description="낙뢰(kA), 초단기예보만")


class DailySummary(BaseModel):
    date: date
    min_temp: float | None = None
    max_temp: float | None = None
    max_precip_prob: int | None = None
    total_precip_mm: float | None = None
    umbrella: bool = Field(description="강수확률 60% 이상이거나 강수 예보가 있으면 True")
    summary: str


class Forecast(BaseModel):
    location: Location
    base_time: datetime
    hourly: list[HourlyForecast]
    daily: list[DailySummary]


class Nowcast(BaseModel):
    location: Location
    observed_at: datetime
    temperature: float | None = None
    precip_type: str | None = None
    precip_1h_mm: float | None = None
    humidity: int | None = None
    wind_speed: float | None = None
    wind_deg: float | None = None
    wind_dir: str | None = None


class ShortTermForecast(BaseModel):
    """초단기예보: 앞으로 약 6시간."""

    location: Location
    base_time: datetime
    hourly: list[HourlyForecast]
