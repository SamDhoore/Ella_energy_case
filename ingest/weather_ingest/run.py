"""The per-city loop from spec/04-ingestion.md §2, made concrete.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This is the main loop that drives the whole ingestion job.

It starts by asking config.py for the settings and the list of cities. If
anything there is wrong it stops immediately and reports a configuration
failure, because there is no point fetching weather it cannot store. It then
opens one database connection and builds one web client, and reuses both for
every city rather than making new ones each time.

Then it walks the cities one at a time and does the same four things to each:

  1. It asks fetch.py to go and get that city's forecast. If nothing comes
     back, it records a TIMEOUT and moves on to the next city. If something
     comes back that is not forecast data, it records MALFORMED and moves on.
  2. It hands whatever arrived to validate.py to check it can be trusted. If
     it cannot, it records MALFORMED with the exact reason and moves on.
  3. It hands the checked rows to writer.py to be stored. If the database
     refuses them, it records DB_ERROR and moves on.
  4. If all three steps worked, it records SUCCESS along with how many rows
     were stored.

"Records" always means the same thing here: one row in the ingest_run
logbook, written by the shared _finish step below. That logbook is what the
dashboard reads to tell you whether the pipeline is healthy.

The promise this file makes is that handling one city can never interrupt
another. Every possible failure is caught here, so the loop always reaches
the last city. That is also why the job reports overall success whenever the
loop ran, even if every city failed: those failures are already visible in
the logbook. It reports overall failure only when it could not start at all.

Exit codes:
  0 - the loop ran; per-city outcomes (including failures) are in ingest_run
  1 - job-level failure: could not connect to the database at all
  2 - job-level failure: configuration invalid
"""
from __future__ import annotations

import logging
import sys
from collections import Counter
from datetime import datetime, timezone

import psycopg

from .config import DAILY_VARS, HOURLY_VARS, City, ConfigError, Settings
from .fetch import FetchFailed, FetchTimeout, build_client, fetch_city
from .validate import MalformedResponse, validate_and_parse
from .writer import record_ingest_run, write_forecast

log = logging.getLogger("weather_ingest")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ingest_city(conn: psycopg.Connection, client, city: City, settings: Settings) -> str:
    """Ingest one city. Never raises; returns the ingest_run status it recorded."""
    started_at = now_utc()

    # --- fetch ------------------------------------------------------------
    try:
        response = fetch_city(client, city, settings)
    except FetchTimeout as exc:
        return _finish(conn, city, "TIMEOUT", None, str(exc), started_at)
    except FetchFailed as exc:
        # A definitive answer arrived (HTTP 4xx/5xx body, API error JSON)
        # but it is not forecast data: "malformed" in the sense of unusable.
        return _finish(conn, city, "MALFORMED", None, str(exc), started_at)

    # --- validate ---------------------------------------------------------
    try:
        parsed = validate_and_parse(response, HOURLY_VARS, DAILY_VARS)
    except MalformedResponse as exc:
        return _finish(conn, city, "MALFORMED", None, str(exc), started_at)

    # --- write (atomic) ---------------------------------------------------
    fetched_at = now_utc()
    date_forecast_made = fetched_at.date()  # the job's own UTC clock, not the payload
    try:
        rows_written = write_forecast(
            conn,
            city_id=city.id,
            date_forecast_made=date_forecast_made,
            fetched_at=fetched_at,
            source=settings.source,
            parsed=parsed,
        )
    except Exception as exc:  # noqa: BLE001 - anything mid-write must roll back and be logged
        return _finish(conn, city, "DB_ERROR", None, f"{type(exc).__name__}: {exc}", started_at)

    return _finish(conn, city, "SUCCESS", rows_written, None, started_at)


def _finish(
    conn: psycopg.Connection,
    city: City,
    status: str,
    rows_written: int | None,
    error_detail: str | None,
    started_at: datetime,
) -> str:
    finished_at = now_utc()
    elapsed = (finished_at - started_at).total_seconds()
    if status == "SUCCESS":
        log.info("%s: SUCCESS, %d rows in %.1fs", city.id, rows_written, elapsed)
    else:
        log.warning("%s: %s after %.1fs - %s", city.id, status, elapsed, error_detail)
    try:
        record_ingest_run(
            conn,
            city_id=city.id,
            status=status,
            rows_written=rows_written,
            error_detail=error_detail,
            started_at=started_at,
            finished_at=finished_at,
        )
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never abort the loop
        log.error("%s: could not record ingest_run row (%s)", city.id, exc)
    return status


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        log.critical("configuration error: %s", exc)
        return 2

    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=10)
    except psycopg.Error as exc:
        log.critical("cannot connect to the database: %s", exc)
        return 1

    client = build_client(settings)
    outcomes: Counter[str] = Counter()
    log.info(
        "starting: %d cities, past_days=%d, timeout=%gs",
        len(settings.cities), settings.past_days, settings.timeout_seconds,
    )
    with conn:
        for city in settings.cities:
            outcomes[ingest_city(conn, client, city, settings)] += 1
    log.info("finished: %s", dict(outcomes))
    return 0  # partial success is still success for the job as a whole


if __name__ == "__main__":
    sys.exit(main())
