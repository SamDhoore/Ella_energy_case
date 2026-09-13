"""One HTTP call per city, returning the *entire* hourly and daily series.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This file goes out to Open-Meteo and gets one city's forecast.

It makes a single web call that returns everything at once: every hour and
every day in the window, for all the variables asked for. There is no separate
request per hour. Wanting tomorrow at 14:00 and tomorrow at 15:00 means
reading two entries out of the same reply, not making two calls.

Before any city is fetched, build_client sets up the connection that is then
reused for all of them. That connection has three nested time limits, each
doing a different job:

  * Eight seconds for a single attempt, after which that attempt is abandoned.
  * Two retries with a pause between them, handled by the library, for the
    common case where Open-Meteo is briefly busy rather than broken.
  * Twenty seconds for the whole operation, retries included.

The third limit needs the odd-looking machinery at the bottom of this file,
so it is worth explaining. Two retries at eight seconds each, plus the waiting
in between, can easily add up to more than twenty seconds, so the first two
limits alone cannot promise when the job will give up. To make twenty seconds
a real ceiling, the call is run on a separate thread and the job waits on that
thread for twenty seconds. If the thread has not come back by then, the job
stops waiting and moves to the next city. The abandoned thread is marked as
disposable so it can never keep the program alive at the end.

The other job of this file is sorting failures into two kinds, and the
question that separates them is simply whether anything came back at all.
Nothing came back means Open-Meteo is unreachable or too slow, which is
usually temporary, and that becomes a TIMEOUT. Something came back but is not
forecast data, such as an error page or a rejection, is a different problem
and becomes MALFORMED. The library reports every failure as one generic error
type, so the code walks back through the underlying causes looking for a
connection or timeout failure at the root to tell the two apart.

There is no per-hour request: a single call to /v1/forecast for one set of
coordinates returns a time axis plus one parallel array per variable covering
[today - past_days, today + forecast horizon]. The per-hour granularity only
appears when validate.py turns that one response into rows.

Transport retries with backoff come from retry-requests wrapping the session
(the pattern Open-Meteo documents). This module adds only what that cannot:
a hard wall-clock budget for the whole call, and a classification of what
came back into "no usable response" vs "a response we cannot use".
"""
from __future__ import annotations

import threading
from typing import Any, Callable, TypeVar

import requests
from openmeteo_requests import Client
from openmeteo_requests.Client import OpenMeteoRequestsError
from openmeteo_sdk.WeatherApiResponse import WeatherApiResponse
from retry_requests import TSession, retry

from .config import DAILY_VARS, HOURLY_VARS, City, Settings

T = TypeVar("T")


class FetchTimeout(Exception):
    """No usable response arrived within the budget (-> ingest_run TIMEOUT)."""


class FetchFailed(Exception):
    """Something arrived, but it is not forecast data (-> ingest_run MALFORMED)."""


def build_client(settings: Settings) -> Client:
    # TSession applies a per-attempt socket timeout; retry() mounts an
    # HTTPAdapter with urllib3 Retry (backoff on connect/read errors and
    # 500/502/504). No requests_cache: a once-a-day batch job gains nothing
    # from it and a cache would serve stale payloads during an outage.
    session = retry(
        TSession(timeout=settings.per_attempt_timeout),
        retries=settings.retries,
        backoff_factor=0.5,
    )
    return Client(session=session)


def fetch_city(client: Client, city: City, settings: Settings) -> WeatherApiResponse:
    params: dict[str, Any] = {
        "latitude": city.lat,
        "longitude": city.lon,
        "hourly": list(HOURLY_VARS),
        "daily": list(DAILY_VARS),
        "past_days": settings.past_days,
        "timezone": "UTC",
    }

    def call() -> WeatherApiResponse:
        responses = client.weather_api(settings.open_meteo_url, params=params)
        if not responses:
            raise FetchFailed("Open-Meteo returned an empty response list")
        return responses[0]

    try:
        return _call_with_deadline(call, settings.timeout_seconds)
    except (FetchTimeout, FetchFailed):
        raise
    except OpenMeteoRequestsError as exc:
        # The SDK wraps everything; the chained cause tells us whether a
        # response ever arrived.
        if _is_transport_failure(exc):
            raise FetchTimeout(f"no response from Open-Meteo: {exc}") from exc
        raise FetchFailed(f"Open-Meteo rejected the request or returned an error body: {exc}") from exc
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise FetchTimeout(f"no response from Open-Meteo: {exc}") from exc
    except requests.RequestException as exc:
        raise FetchFailed(f"HTTP failure: {exc}") from exc


def _is_transport_failure(exc: BaseException) -> bool:
    cursor: BaseException | None = exc
    while cursor is not None:
        if isinstance(cursor, (requests.Timeout, requests.ConnectionError)):
            return True
        cursor = cursor.__cause__ or cursor.__context__
    return False


def _call_with_deadline(fn: Callable[[], T], seconds: float) -> T:
    """Run fn in a daemon thread and give up after `seconds` of wall-clock time.

    The retry adapter can legitimately spend longer than any single socket
    timeout; this is the outer bound the job is willing to wait, full stop.
    A thread that is still blocked after the deadline is abandoned (daemon),
    so it can never hold the process open at exit.
    """
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=target, name="openmeteo-fetch", daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise FetchTimeout(f"no response within {seconds:g}s wall-clock (library retries included)")
    if "error" in box:
        raise box["error"]
    return box["value"]
