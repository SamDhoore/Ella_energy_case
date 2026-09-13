"""Long-running scheduler for the `cron` compose service.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This file is the alarm clock. It is the only part of the system that stays
running all the time without doing anything most of the time.

It works out when the next run is due, sleeps until then, runs the identical
ingestion job that run.py performs, writes down the outcome, and goes back to
sleep. By default the next run is the next time the clock reaches 03:00 UTC.
A setting can replace that with a plain repeating interval instead, which is
useful for demonstrating the system quickly rather than waiting a day.

It does not run the moment it starts up. The separate one-shot ingest
container already does the first run when the system comes up, so this one
waits for its first proper tick rather than duplicating that work.

The run is wrapped so that a failure inside one night's ingestion is written
down and then survived. If a run crashes outright, this file logs it and waits
for the next one rather than dying quietly and leaving the system frozen at
whatever data it happened to have.

Runs the same ingestion as `weather_ingest.run` once per day at
INGEST_SCHEDULE_UTC (HH:MM, default 03:00). Set INGEST_INTERVAL_SECONDS to
run on a fixed interval instead (handy for demonstrating revisions quickly).
The very first run after a fresh clone is done by the one-shot `ingest`
service, so this loop waits for its first tick rather than running at boot.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from . import run

log = logging.getLogger("weather_ingest.scheduler")


def _next_daily(now: datetime, hour: int, minute: int) -> datetime:
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    interval_env = os.environ.get("INGEST_INTERVAL_SECONDS", "").strip()
    schedule_env = os.environ.get("INGEST_SCHEDULE_UTC", "03:00").strip()
    try:
        interval = int(interval_env) if interval_env else None
        hour, minute = (int(part) for part in schedule_env.split(":"))
        if interval is not None and interval <= 0:
            raise ValueError("INGEST_INTERVAL_SECONDS must be positive")
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("INGEST_SCHEDULE_UTC must be HH:MM")
    except ValueError as exc:
        log.critical("bad schedule configuration: %s", exc)
        return 2

    while True:
        now = datetime.now(timezone.utc)
        next_run = now + timedelta(seconds=interval) if interval else _next_daily(now, hour, minute)
        log.info("next ingest at %s", next_run.isoformat(timespec="seconds"))
        time.sleep(max(0.0, (next_run - datetime.now(timezone.utc)).total_seconds()))
        try:
            code = run.main()
            log.info("ingest run finished with exit code %d", code)
        except Exception:  # noqa: BLE001 - the scheduler itself must survive
            log.exception("ingest run crashed")


if __name__ == "__main__":
    sys.exit(main())
