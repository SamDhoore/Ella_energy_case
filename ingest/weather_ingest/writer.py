"""Database writes, of two very different kinds.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This file performs the only two writes the ingestion job ever makes, and
keeping them apart is the whole safety argument.

The first is the forecast itself, and it happens as one indivisible unit.
Three steps run together: find or create today's folder for this city, empty
that folder completely, then fill it with the readings just fetched. If
anything at all goes wrong partway through, the database rewinds all three
steps as though none of them had been attempted. That is what guarantees a
crash can never leave half a forecast behind for someone to read later and
believe.

Emptying the folder before refilling it is also what makes running the job
twice harmless. The second run removes exactly what the first one put there
before writing its own copy, so the folder always ends up holding one clean
set of readings rather than two overlapping ones. Creating the folder uses a
form of instruction that means "make this, or if it already exists give me
the one that is there", which is how a repeat run lands in the same folder
instead of starting a second one for the same day.

The second write is the logbook entry, and it is deliberately kept outside
that protection. When a forecast write is rewound, the note saying it failed
has to survive, otherwise the failure erases its own evidence and the
dashboard has nothing to show you. Putting both in the same unit would mean
exactly that. So the logbook entry is written on its own, once the outcome is
known, and it stands whatever happened to the forecast.

Original technical note follows.

Two very different kinds, deliberately kept apart:

* write_forecast   - ONE transaction per city: upsert forecast_run, delete that
                     run's old values, insert the new ones. Any exception rolls
                     the whole thing back (spec/04-ingestion.md §10-13).
* record_ingest_run - a single auto-committed INSERT, written once the outcome
                     is known, never inside the transaction above, so a rolled
                     back city still leaves an observable log row.

The connection is used in autocommit mode: statements outside a
`conn.transaction()` block commit immediately; inside it they are one unit.
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

import psycopg

from .validate import ParsedForecast

UPSERT_RUN = """
INSERT INTO forecast_run (city, date_forecast_made, fetched_at, source)
VALUES (%(city)s, %(date_forecast_made)s, %(fetched_at)s, %(source)s)
ON CONFLICT (city, date_forecast_made)
DO UPDATE SET fetched_at = EXCLUDED.fetched_at,
              source     = EXCLUDED.source
RETURNING forecast_run_id
"""
# DO UPDATE rather than DO NOTHING: a same-day re-run must still RETURN the
# existing row's id so the child rows below can be re-attached to it.

DELETE_VALUES = "DELETE FROM forecast_value WHERE forecast_run_id = %s"

INSERT_HOURLY = """
INSERT INTO forecast_value
    (forecast_run_id, target_time, granularity,
     temperature_2m, precipitation, precipitation_probability, visibility, wind_gusts_10m)
VALUES (%s, %s, 'HOURLY', %s, %s, %s, %s, %s)
"""

INSERT_DAILY = """
INSERT INTO forecast_value
    (forecast_run_id, target_time, granularity,
     uv_index_max, temperature_2m_max, wind_gusts_10m_max, sunshine_duration)
VALUES (%s, %s, 'DAILY', %s, %s, %s, %s)
"""

INSERT_INGEST_RUN = """
INSERT INTO ingest_run
    (run_id, city, status, rows_written, error_detail, started_at, finished_at)
VALUES (%s, %s, %s::ingest_status, %s, %s, %s, %s)
"""


def write_forecast(
    conn: psycopg.Connection,
    *,
    city_id: str,
    date_forecast_made: date,
    fetched_at: datetime,
    source: str,
    parsed: ParsedForecast,
) -> int:
    """Atomically replace the (city, date) forecast with `parsed`. Returns rows written."""
    with conn.transaction():  # BEGIN ... COMMIT, or ROLLBACK on any exception
        row = conn.execute(
            UPSERT_RUN,
            {
                "city": city_id,
                "date_forecast_made": date_forecast_made,
                "fetched_at": fetched_at,
                "source": source,
            },
        ).fetchone()
        assert row is not None  # RETURNING always yields on upsert
        forecast_run_id = row[0]

        # Idempotency at the row level: wipe whatever a previous attempt for
        # this (city, date) wrote, then insert the fresh set. A second run
        # therefore ends with exactly one copy of the latest payload.
        conn.execute(DELETE_VALUES, (forecast_run_id,))

        with conn.cursor() as cur:
            cur.executemany(INSERT_HOURLY, [(forecast_run_id, *r) for r in parsed.hourly])
            cur.executemany(INSERT_DAILY, [(forecast_run_id, *r) for r in parsed.daily])
    return parsed.row_count


def record_ingest_run(
    conn: psycopg.Connection,
    *,
    city_id: str,
    status: str,
    rows_written: int | None,
    error_detail: str | None,
    started_at: datetime,
    finished_at: datetime,
) -> None:
    conn.execute(
        INSERT_INGEST_RUN,
        (uuid4(), city_id, status, rows_written, error_detail, started_at, finished_at),
    )
