"""Unit tests for the response validation branch (no network, no database)."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from weather_ingest.validate import MalformedResponse, validate_and_parse

HOURLY = ("temperature_2m", "precipitation")
DAILY = ("uv_index_max",)


class FakeValues:
    def __init__(self, values):
        self._values = list(values)

    def ValuesLength(self):
        return len(self._values)

    def Values(self, j):
        return self._values[j]


class FakeBlock:
    def __init__(self, start, interval, columns):
        self._start, self._interval, self._columns = start, interval, columns
        self._n = max((len(c) for c in columns), default=0)

    def Time(self):
        return self._start

    def TimeEnd(self):
        return self._start + self._n * self._interval

    def Interval(self):
        return self._interval

    def VariablesLength(self):
        return len(self._columns)

    def Variables(self, i):
        return FakeValues(self._columns[i])


class FakeResponse:
    def __init__(self, hourly, daily):
        self._hourly, self._daily = hourly, daily

    def Hourly(self):
        return self._hourly

    def Daily(self):
        return self._daily


T0 = 1_788_652_800  # 2026-09-06T00:00:00Z


def good_response():
    return FakeResponse(
        hourly=FakeBlock(T0, 3600, [[14.9, 14.5, 14.4], [0.0, 0.1, math.nan]]),
        daily=FakeBlock(T0, 86400, [[5.2]]),
    )


def test_aligned_response_parses_to_rows_with_nan_as_none():
    parsed = validate_and_parse(good_response(), HOURLY, DAILY)
    assert parsed.row_count == 4
    assert parsed.hourly[0] == (datetime(2026, 9, 6, 0, tzinfo=timezone.utc), 14.9, 0.0)
    assert parsed.hourly[2][2] is None  # NaN -> NULL
    assert parsed.daily == [(datetime(2026, 9, 6, 0, tzinfo=timezone.utc), 5.2)]


def test_missing_daily_block_is_malformed():
    resp = FakeResponse(hourly=good_response().Hourly(), daily=None)
    with pytest.raises(MalformedResponse, match="daily block missing"):
        validate_and_parse(resp, HOURLY, DAILY)


def test_misaligned_array_length_is_malformed():
    resp = FakeResponse(
        hourly=FakeBlock(T0, 3600, [[1.0, 2.0, 3.0], [0.0]]),  # second column too short
        daily=FakeBlock(T0, 86400, [[5.2]]),
    )
    with pytest.raises(MalformedResponse, match="precipitation has 1 values"):
        validate_and_parse(resp, HOURLY, DAILY)


def test_zero_rows_is_malformed():
    resp = FakeResponse(hourly=FakeBlock(T0, 3600, [[], []]), daily=FakeBlock(T0, 86400, [[5.2]]))
    with pytest.raises(MalformedResponse, match="hourly block has zero rows"):
        validate_and_parse(resp, HOURLY, DAILY)


def test_missing_variable_is_malformed():
    resp = FakeResponse(
        hourly=FakeBlock(T0, 3600, [[1.0, 2.0]]),  # only one of two configured variables
        daily=FakeBlock(T0, 86400, [[5.2]]),
    )
    with pytest.raises(MalformedResponse, match="hourly block has 1 variables, expected 2"):
        validate_and_parse(resp, HOURLY, DAILY)
