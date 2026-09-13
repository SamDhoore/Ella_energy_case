"""Turn one Open-Meteo response into rows, or explain exactly why it can't be.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This file is the gatekeeper between "a reply arrived" and "we are willing to
store it". A reply arriving is not the same as a reply being usable.

Open-Meteo answers in a compact binary format rather than readable text, and
it leaves out anything it can. The timestamps are not spelled out at all: you
get a start time, an end time and a spacing, and you are expected to work out
the hours yourself. The readings arrive as bare columns of numbers with no
labels, identified only by the position they were requested in.

So this file first rebuilds the timestamps from that start, end and spacing.
Then it checks five things before letting anything through: that both the
hourly and the daily section exist, that neither is empty, that the number of
columns matches the number of variables that were asked for, and that every
column is exactly as long as the list of timestamps.

That fourth check is the one that earns its keep. A reply that quietly dropped
one variable but was otherwise perfectly formed would slip past a looser check
and write a column of blanks into the database with no error anywhere. Here it
is caught and named.

It also translates Open-Meteo's marker for "no reading available" into a
proper empty value, which is why those database columns are allowed to be
empty in the first place.

If any check fails, the file raises an error carrying a sentence explaining
which check failed and what it saw instead. That sentence is stored word for
word in the logbook, because it is what someone will read weeks later when
they are trying to work out why a city stopped updating.

Checks, in order (spec/04-ingestion.md §8 + OQ5):
  1. hourly block present, 2. daily block present,
  3. each block has a non-empty time axis,
  4. each block carries exactly the configured variables (count check; the
     SDK exposes variables positionally in request order),
  5. every variable's value array is as long as its time axis.
Any failure raises MalformedResponse with a human-readable reason that ends
up verbatim in ingest_run.error_detail.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

# Row tuples are ordered (target_time, *VARS) with VARS in config order; the
# INSERT statements in writer.py list columns in that same order.
HourlyRow = tuple[Any, ...]
DailyRow = tuple[Any, ...]


class MalformedResponse(Exception):
    """The response arrived but cannot be trusted (-> ingest_run MALFORMED)."""


@dataclass(frozen=True)
class ParsedForecast:
    hourly: list[HourlyRow]
    daily: list[DailyRow]

    @property
    def row_count(self) -> int:
        return len(self.hourly) + len(self.daily)


def validate_and_parse(
    response: Any, hourly_vars: Sequence[str], daily_vars: Sequence[str]
) -> ParsedForecast:
    hourly = response.Hourly()
    if hourly is None:
        raise MalformedResponse("hourly block missing from response")
    daily = response.Daily()
    if daily is None:
        raise MalformedResponse("daily block missing from response")

    hourly_times = _time_axis(hourly, "hourly")
    daily_times = _time_axis(daily, "daily")
    hourly_cols = _columns(hourly, "hourly", hourly_vars, len(hourly_times))
    daily_cols = _columns(daily, "daily", daily_vars, len(daily_times))

    hourly_rows = [
        (t, *(hourly_cols[v][i] for v in hourly_vars)) for i, t in enumerate(hourly_times)
    ]
    daily_rows = [
        (t, *(daily_cols[v][i] for v in daily_vars)) for i, t in enumerate(daily_times)
    ]
    return ParsedForecast(hourly=hourly_rows, daily=daily_rows)


def _time_axis(block: Any, name: str) -> list[datetime]:
    start, end, interval = int(block.Time()), int(block.TimeEnd()), int(block.Interval())
    if interval <= 0:
        raise MalformedResponse(f"{name} block has a non-positive interval ({interval}s)")
    count = max(0, (end - start) // interval)
    if count == 0:
        raise MalformedResponse(f"{name} block has zero rows")
    return [datetime.fromtimestamp(start + i * interval, tz=timezone.utc) for i in range(count)]


def _columns(
    block: Any, name: str, variables: Sequence[str], expected_len: int
) -> dict[str, list[float | None]]:
    count = int(block.VariablesLength())
    if count != len(variables):
        raise MalformedResponse(
            f"{name} block has {count} variables, expected {len(variables)} ({', '.join(variables)})"
        )
    columns: dict[str, list[float | None]] = {}
    for index, variable in enumerate(variables):
        values = block.Variables(index)
        if values is None:
            raise MalformedResponse(f"{name}.{variable} is missing")
        length = int(values.ValuesLength())
        if length != expected_len:
            raise MalformedResponse(
                f"{name}.{variable} has {length} values but the time axis has {expected_len}"
            )
        columns[variable] = [_clean(values.Values(j)) for j in range(length)]
    return columns


def _clean(value: float) -> float | None:
    # Open-Meteo encodes "no value" as NaN; the columns are nullable for this.
    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return float(value)
