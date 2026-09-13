"""Response models. Every datetime serialises as ISO 8601 UTC with a trailing Z.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This file describes the exact shape of every answer the API can send. It
contains no logic, only descriptions: this answer carries a city, a date, and
a list of readings, and each reading carries these named numbers.

Those descriptions do real work rather than just documenting intent. The
framework checks every outgoing answer against them, so an answer missing a
field or carrying the wrong kind of value is caught here rather than reaching
the dashboard and breaking a chart. They are also what produces the browsable
documentation at /docs automatically, which means the documentation cannot
drift out of date with the actual behaviour.

Two conventions are enforced in this file and nowhere else.

Every moment in time is written in one fixed format, in UTC, ending in a Z.
The whole system stores time in UTC, and pinning the written format here means
no part of the API can accidentally send a time in local form and leave the
dashboard guessing which zone it meant.

Some fields do not come straight from the database but are worked out on the
way past, and they are named so as not to hide that. The clearest example is
the flag on each past forecast saying whether that moment was still in the
future when that forecast was fetched. If it was not, the value is really an
observation rather than a prediction, and the dashboard draws it differently.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, PlainSerializer


def _iso_z(value: datetime) -> str:
    value = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_iso_z, return_type=str, when_used="json")]
Granularity = Literal["HOURLY", "DAILY"]
IngestStatus = Literal["SUCCESS", "TIMEOUT", "MALFORMED", "DB_ERROR"]


class City(BaseModel):
    id: str
    name: str
    lat: float
    lon: float


class CitiesResponse(BaseModel):
    cities: list[City]


class ForecastRun(BaseModel):
    forecast_run_id: int
    city: str
    date_forecast_made: date
    fetched_at: UtcDatetime
    source: str


class HourlyPoint(BaseModel):
    target_time: UtcDatetime
    temperature_2m: float | None
    precipitation: float | None
    precipitation_probability: float | None
    visibility: float | None
    wind_gusts_10m: float | None


class DailyPoint(BaseModel):
    target_date: date
    uv_index_max: float | None
    temperature_2m_max: float | None
    wind_gusts_10m_max: float | None
    sunshine_duration: float | None
    # Derived: min of that UTC day's hourly visibility readings in the same run
    # (spec/01-dashboard.md OQ3 - Open-Meteo has no daily visibility variable).
    visibility_min: float | None


class LatestResponse(BaseModel):
    run: ForecastRun
    granularity: Granularity
    horizon_hours: int
    window_start: UtcDatetime
    window_end: UtcDatetime
    points: list[HourlyPoint] | list[DailyPoint]


class RevisionSeries(BaseModel):
    forecast_run_id: int
    date_forecast_made: date
    fetched_at: UtcDatetime
    points: list[HourlyPoint]


class RevisionsResponse(BaseModel):
    city: str
    horizon_hours: int
    window_start: UtcDatetime
    window_end: UtcDatetime
    target_times: list[UtcDatetime]
    series: list[RevisionSeries]  # newest issue first


class HistoryEntry(BaseModel):
    forecast_run_id: int
    date_forecast_made: date
    fetched_at: UtcDatetime
    # False when the hour had already passed when this run fetched it: the
    # value is then Open-Meteo's observation/analysis, not a prediction.
    was_future_at_fetch: bool
    temperature_2m: float | None
    precipitation: float | None
    precipitation_probability: float | None
    visibility: float | None
    wind_gusts_10m: float | None


class HistoryResponse(BaseModel):
    city: str
    target_time: UtcDatetime
    revisions: list[HistoryEntry]  # oldest issue first


class DailyResponse(BaseModel):
    run: ForecastRun
    points: list[DailyPoint]


class DatesResponse(BaseModel):
    city: str
    dates: list[date]  # newest first


class IngestRun(BaseModel):
    run_id: UUID
    status: IngestStatus
    rows_written: int | None
    error_detail: str | None
    started_at: UtcDatetime
    finished_at: UtcDatetime


class CityHealth(BaseModel):
    city: str
    healthy: bool  # last_attempt exists and succeeded
    last_attempt: IngestRun | None
    last_success: IngestRun | None


class HealthResponse(BaseModel):
    generated_at: UtcDatetime
    cities: list[CityHealth]


class ServiceHealth(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
