"""The API's endpoints: one function per address the dashboard can call.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This file is the switchboard. Each function below answers one address, and
every one of them follows the same four steps in the same order.

  1. Check the request. Is this a city we actually have? Is that a real date?
     Is that number inside the allowed range? Anything wrong here is refused
     straight away as a bad request, before the database is troubled at all.
  2. Ask the database, using one of the ready-made questions in queries.py.
     No database instructions are written in this file.
  3. Decide whether the answer counts as nothing. An empty result is not an
     error, but it is also not a normal answer, so it is reported distinctly
     as "valid question, nothing to say yet".
  4. Shape the answer to match the descriptions in schemas.py and send it.

Checking the city is worth singling out, because it is the same rule
everywhere. The list of cities is a closed set that we define, so a name that
is not on it is treated as an invalid request rather than a missing result. A
city that is on the list but has no data yet is the opposite: a perfectly good
request that we simply cannot answer yet. Those two situations look similar
and mean very different things, and the dashboard shows them differently.

The one place that rule is deliberately broken is the ingestion health
address. "Nothing has ever been ingested for this city" is itself a useful and
truthful health answer, so that address reports it as a normal answer with
empty fields rather than as a missing result.

The addresses themselves map one to one onto things you can do on the
dashboard: list the cities, get the newest forecast, get several forecasts
overlaid, get the history of one specific moment, get the daily table, list
which forecast days exist, and report whether ingestion is healthy.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, Depends, Query, Request

from . import queries
from .config import Settings
from .db import get_conn
from .errors import ApiError
from .schemas import (
    CitiesResponse,
    DailyResponse,
    DatesResponse,
    Granularity,
    HealthResponse,
    HistoryResponse,
    LatestResponse,
    RevisionsResponse,
    ServiceHealth,
)

router = APIRouter()


# --- shared dependencies / helpers -------------------------------------------

def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def city_param(
    city: Annotated[str, Query(description="City id, one of GET /cities")],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    # Closed set defined by our config: an unknown value is a bad request,
    # not "no data" (spec/03-api.md §2).
    if city not in settings.city_ids:
        raise ApiError(400, "UNKNOWN_CITY", f"'{city}' is not a configured city; see GET /cities")
    return city


def parse_target_time(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(
            400, "INVALID_TARGET_TIME", f"target_time '{raw}' is not ISO 8601 ({exc})"
        ) from exc
    if value.tzinfo is None:
        raise ApiError(
            400, "INVALID_TARGET_TIME",
            "target_time must carry a UTC offset, e.g. 2026-09-14T14:00:00Z",
        )
    return value.astimezone(timezone.utc)


def parse_date(raw: str, name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ApiError(400, "INVALID_PARAMETER", f"{name} '{raw}' is not an ISO 8601 date") from exc


def hourly_window(horizon_hours: int) -> tuple[datetime, datetime]:
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return start, start + timedelta(hours=horizon_hours)


def daily_window(horizon_hours: int) -> tuple[datetime, datetime]:
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=math.ceil(horizon_hours / 24))


def _fmt(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


Conn = Annotated[psycopg.Connection, Depends(get_conn)]
Cfg = Annotated[Settings, Depends(get_settings)]
CityId = Annotated[str, Depends(city_param)]
HorizonHours = Annotated[
    int | None, Query(ge=1, le=168, description="How far ahead, in hours (default 48)")
]


# --- endpoints ---------------------------------------------------------------

@router.get("/health", response_model=ServiceHealth, tags=["ops"])
def service_health(conn: Conn) -> dict[str, str]:
    queries.ping(conn)  # a database failure surfaces as 503 via the error handlers
    return {"status": "ok", "database": "ok"}


@router.get("/cities", response_model=CitiesResponse, tags=["forecasts"])
def list_cities(settings: Cfg) -> dict[str, Any]:
    return {"cities": [asdict(c) for c in settings.cities]}


@router.get("/forecasts/latest", response_model=LatestResponse, tags=["forecasts"])
def latest_forecast(
    city: CityId,
    conn: Conn,
    settings: Cfg,
    granularity: Granularity = "HOURLY",
    horizon_hours: HorizonHours = None,
) -> dict[str, Any]:
    horizon = horizon_hours or settings.default_horizon_hours
    run = queries.latest_run(conn, city)
    if run is None:
        raise ApiError(404, "NOT_FOUND", f"no forecast has been ingested yet for '{city}'")
    if granularity == "HOURLY":
        start, end = hourly_window(horizon)
        points = queries.hourly_points(conn, run["forecast_run_id"], start, end)
    else:
        start, end = daily_window(horizon)
        points = queries.daily_points(conn, run["forecast_run_id"], start, end)
    if not points:
        raise ApiError(
            404, "NOT_FOUND",
            f"the latest forecast for '{city}' (issued {run['date_forecast_made']}) has no "
            f"{granularity} values between {_fmt(start)} and {_fmt(end)}",
        )
    return {
        "run": run, "granularity": granularity, "horizon_hours": horizon,
        "window_start": start, "window_end": end, "points": points,
    }


@router.get("/forecasts/revisions", response_model=RevisionsResponse, tags=["forecasts"])
def forecast_revisions(
    city: CityId,
    conn: Conn,
    settings: Cfg,
    horizon_hours: HorizonHours = None,
    max_revisions: Annotated[
        int | None, Query(ge=1, le=30, description="How many recent issues to overlay (default 10)")
    ] = None,
) -> dict[str, Any]:
    horizon = horizon_hours or settings.default_horizon_hours
    limit = max_revisions or settings.default_max_revisions
    latest = queries.latest_run(conn, city)
    if latest is None:
        raise ApiError(404, "NOT_FOUND", f"no forecast has been ingested yet for '{city}'")
    start, end = hourly_window(horizon)
    latest_points = queries.hourly_points(conn, latest["forecast_run_id"], start, end)
    if not latest_points:
        raise ApiError(
            404, "NOT_FOUND",
            f"the latest forecast for '{city}' has no hourly values between "
            f"{_fmt(start)} and {_fmt(end)}",
        )
    target_times = [p["target_time"] for p in latest_points]

    runs = queries.recent_runs(conn, city, limit)  # newest first
    rows = queries.hourly_points_for_runs(conn, [r["forecast_run_id"] for r in runs], start, end)
    by_run: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_run.setdefault(row["forecast_run_id"], []).append(row)

    series = [
        {
            "forecast_run_id": run["forecast_run_id"],
            "date_forecast_made": run["date_forecast_made"],
            "fetched_at": run["fetched_at"],
            "points": by_run[run["forecast_run_id"]],
        }
        for run in runs
        if run["forecast_run_id"] in by_run  # an old issue may not reach this window at all
    ]
    return {
        "city": city, "horizon_hours": horizon, "window_start": start, "window_end": end,
        "target_times": target_times, "series": series,
    }


@router.get("/forecasts/history", response_model=HistoryResponse, tags=["forecasts"])
def forecast_history(
    city: CityId,
    conn: Conn,
    target_time: Annotated[str, Query(description="ISO 8601 with offset, e.g. 2026-09-14T14:00:00Z")],
) -> dict[str, Any]:
    when = parse_target_time(target_time)
    rows = queries.history(conn, city, when)
    if not rows:
        raise ApiError(
            404, "NOT_FOUND", f"no forecast issue for '{city}' holds a value at {_fmt(when)}"
        )
    revisions = [{**row, "was_future_at_fetch": when > row["fetched_at"]} for row in rows]
    return {"city": city, "target_time": when, "revisions": revisions}


@router.get("/forecasts/daily", response_model=DailyResponse, tags=["forecasts"])
def daily_matrix(
    city: CityId,
    conn: Conn,
    date_forecast_made: Annotated[
        str | None, Query(description="ISO date of the issue; defaults to the latest")
    ] = None,
) -> dict[str, Any]:
    if date_forecast_made is None:
        run = queries.latest_run(conn, city)
        if run is None:
            raise ApiError(404, "NOT_FOUND", f"no forecast has been ingested yet for '{city}'")
    else:
        made = parse_date(date_forecast_made, "date_forecast_made")
        run = queries.run_by_date(conn, city, made)
        if run is None:
            raise ApiError(
                404, "NOT_FOUND",
                f"no forecast issue for '{city}' on {made}; see GET /forecasts/dates",
            )
    points = queries.daily_points(conn, run["forecast_run_id"])
    if not points:
        raise ApiError(
            404, "NOT_FOUND",
            f"the forecast issued {run['date_forecast_made']} for '{city}' has no daily values",
        )
    return {"run": run, "points": points}


@router.get("/forecasts/dates", response_model=DatesResponse, tags=["forecasts"])
def available_dates(city: CityId, conn: Conn) -> dict[str, Any]:
    dates = queries.forecast_dates(conn, city)
    if not dates:
        raise ApiError(404, "NOT_FOUND", f"no forecast has been ingested yet for '{city}'")
    return {"city": city, "dates": dates}


@router.get("/ingestion/health", response_model=HealthResponse, tags=["ops"])
def ingestion_health(
    conn: Conn,
    settings: Cfg,
    city: Annotated[str | None, Query(description="Omit for all configured cities")] = None,
) -> dict[str, Any]:
    if city is not None and city not in settings.city_ids:
        raise ApiError(400, "UNKNOWN_CITY", f"'{city}' is not a configured city; see GET /cities")
    ids = [city] if city else [c.id for c in settings.cities]
    # "Never ingested" is a valid health state, so this endpoint is 200 with
    # nulls rather than 404 (spec/03-api.md OQ3).
    cities = []
    for cid in ids:
        attempt = queries.last_attempt(conn, cid)
        success = attempt if attempt and attempt["status"] == "SUCCESS" else queries.last_success(conn, cid)
        cities.append({
            "city": cid,
            "healthy": bool(attempt and attempt["status"] == "SUCCESS"),
            "last_attempt": attempt,
            "last_success": success,
        })
    return {"generated_at": datetime.now(timezone.utc), "cities": cities}
