"""All SQL lives here. Each function takes a dict_row connection.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
Every question the API can ask the database is written out here, and nowhere
else. Each one is a small named function: find the newest forecast for a city,
list the days we hold forecasts for, fetch the readings for one forecast, find
the last time ingestion succeeded.

Gathering them in one file has a specific purpose beyond tidiness. The request
handlers in routes.py are then free to deal only with checking the request and
shaping the answer, and never contain database instructions themselves. That
keeps the two concerns from tangling, and it means a question can be rewritten
or made faster here without touching the handlers at all.

It also makes a claim checkable at a glance. Every function in this file only
reads. Scrolling through it is enough to confirm the API never writes, which
is a much easier thing to verify than hunting for stray instructions spread
across the handlers.

The questions here are deliberately the exact ones the database was set up to
answer quickly. The database keeps sorted shortcuts for looking up the newest
forecast for a city, and for finding every forecast that mentions one specific
hour, because those two are what the dashboard asks constantly.

One question does slightly more than fetch. The daily table has no visibility
figure, because the weather service does not publish one per day. So that
query works it out on the way past, taking the lowest hourly visibility for
each day, which is the conventional way of describing a day's visibility.

The queries are the ones spec/02-data-model.md's indexes were designed for.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import psycopg

RUN_COLUMNS = "forecast_run_id, city, date_forecast_made, fetched_at, source"
HOURLY_COLUMNS = (
    "target_time, temperature_2m, precipitation, precipitation_probability, visibility, wind_gusts_10m"
)


def latest_run(conn: psycopg.Connection, city: str) -> dict[str, Any] | None:
    return conn.execute(
        f"SELECT {RUN_COLUMNS} FROM forecast_run WHERE city = %s "
        "ORDER BY date_forecast_made DESC LIMIT 1",
        (city,),
    ).fetchone()


def run_by_date(conn: psycopg.Connection, city: str, made: date) -> dict[str, Any] | None:
    return conn.execute(
        f"SELECT {RUN_COLUMNS} FROM forecast_run WHERE city = %s AND date_forecast_made = %s",
        (city, made),
    ).fetchone()


def recent_runs(conn: psycopg.Connection, city: str, limit: int) -> list[dict[str, Any]]:
    return conn.execute(
        f"SELECT {RUN_COLUMNS} FROM forecast_run WHERE city = %s "
        "ORDER BY date_forecast_made DESC LIMIT %s",
        (city, limit),
    ).fetchall()


def forecast_dates(conn: psycopg.Connection, city: str) -> list[date]:
    rows = conn.execute(
        "SELECT date_forecast_made FROM forecast_run WHERE city = %s "
        "ORDER BY date_forecast_made DESC",
        (city,),
    ).fetchall()
    return [r["date_forecast_made"] for r in rows]


def hourly_points(
    conn: psycopg.Connection, run_id: int, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    return conn.execute(
        f"SELECT {HOURLY_COLUMNS} FROM forecast_value "
        "WHERE forecast_run_id = %s AND granularity = 'HOURLY' "
        "AND target_time >= %s AND target_time < %s ORDER BY target_time",
        (run_id, start, end),
    ).fetchall()


def hourly_points_for_runs(
    conn: psycopg.Connection, run_ids: list[int], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    return conn.execute(
        f"SELECT forecast_run_id, {HOURLY_COLUMNS} FROM forecast_value "
        "WHERE forecast_run_id = ANY(%s) AND granularity = 'HOURLY' "
        "AND target_time >= %s AND target_time < %s "
        "ORDER BY forecast_run_id, target_time",
        (run_ids, start, end),
    ).fetchall()


def daily_points(
    conn: psycopg.Connection, run_id: int, start: datetime | None = None, end: datetime | None = None
) -> list[dict[str, Any]]:
    """DAILY rows of a run, each with visibility_min derived from that UTC day's hourly rows."""
    window = ""
    params: list[Any] = [run_id, run_id]
    if start is not None and end is not None:
        window = "AND d.target_time >= %s AND d.target_time < %s "
        params += [start, end]
    return conn.execute(
        "SELECT (d.target_time AT TIME ZONE 'UTC')::date AS target_date, "
        "       d.uv_index_max, d.temperature_2m_max, d.wind_gusts_10m_max, d.sunshine_duration, "
        "       v.visibility_min "
        "FROM forecast_value d "
        "LEFT JOIN ( "
        "    SELECT (target_time AT TIME ZONE 'UTC')::date AS day, min(visibility) AS visibility_min "
        "    FROM forecast_value WHERE forecast_run_id = %s AND granularity = 'HOURLY' "
        "    GROUP BY 1 "
        ") v ON v.day = (d.target_time AT TIME ZONE 'UTC')::date "
        "WHERE d.forecast_run_id = %s AND d.granularity = 'DAILY' "
        + window
        + "ORDER BY d.target_time",
        params,
    ).fetchall()


def history(conn: psycopg.Connection, city: str, target_time: datetime) -> list[dict[str, Any]]:
    return conn.execute(
        "SELECT fr.forecast_run_id, fr.date_forecast_made, fr.fetched_at, "
        f"       {', '.join('fv.' + c.strip() for c in HOURLY_COLUMNS.split(','))} "
        "FROM forecast_run fr "
        "JOIN forecast_value fv ON fv.forecast_run_id = fr.forecast_run_id "
        "WHERE fr.city = %s AND fv.target_time = %s AND fv.granularity = 'HOURLY' "
        "ORDER BY fr.date_forecast_made ASC",
        (city, target_time),
    ).fetchall()


INGEST_COLUMNS = "run_id, status, rows_written, error_detail, started_at, finished_at"


def last_attempt(conn: psycopg.Connection, city: str) -> dict[str, Any] | None:
    return conn.execute(
        f"SELECT {INGEST_COLUMNS} FROM ingest_run WHERE city = %s "
        "ORDER BY started_at DESC LIMIT 1",
        (city,),
    ).fetchone()


def last_success(conn: psycopg.Connection, city: str) -> dict[str, Any] | None:
    return conn.execute(
        f"SELECT {INGEST_COLUMNS} FROM ingest_run WHERE city = %s AND status = 'SUCCESS' "
        "ORDER BY started_at DESC LIMIT 1",
        (city,),
    ).fetchone()


def ping(conn: psycopg.Connection) -> None:
    conn.execute("SELECT 1").fetchone()
