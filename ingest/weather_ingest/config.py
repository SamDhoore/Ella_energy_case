"""Configuration for the ingestion job.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This is the job's settings desk. Everything that can be tuned lives either
here or in the environment, so no other file has to guess at a value or keep
its own copy of one.

It does two jobs. First it reads the environment for the database address and
a handful of numbers: how many past days to ask Open-Meteo for, and how long
to wait before giving up on a city. Second it reads the list of cities from a
JSON file and checks it is sensible: at least three cities, no two sharing an
id, and every entry carrying a name and a pair of coordinates.

If any of that is wrong it refuses to continue, and run.py turns that refusal
into an immediate stop. Failing here is deliberate. A job that cannot find
its database or its cities has nothing useful to do, and stopping at once is
far easier to diagnose than discovering the problem halfway through a run.

One detail is easy to overlook but load-bearing. The two lists of weather
variables below are ordered, and that order is not cosmetic. Open-Meteo sends
the values back in exactly the order they were asked for, with no labels
attached, so the question and the reading of the answer have to agree. Keeping
both in this one place is what stops them quietly drifting apart, which would
otherwise mislabel every reading without any visible error.

Everything tunable lives here or in the environment. Raising PAST_DAYS later
is a config change only: forecast_value.target_time is an unconstrained
timestamptz, so a wider window just means more rows per call
(spec/04-ingestion.md §5).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo"

# Request order == response order (Open-Meteo guarantees this and the SDK
# exposes variables positionally), so these tuples are the single source of
# truth for both the request params and the column mapping in validate.py.
HOURLY_VARS: tuple[str, ...] = (
    "temperature_2m",
    "precipitation",
    "precipitation_probability",
    "visibility",
    "wind_gusts_10m",
)
DAILY_VARS: tuple[str, ...] = (
    "uv_index_max",
    "temperature_2m_max",
    "wind_gusts_10m_max",
    "sunshine_duration",
)


class ConfigError(Exception):
    """The job cannot start at all (job-level failure, exit code 2)."""


@dataclass(frozen=True)
class City:
    id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Settings:
    database_url: str
    cities: tuple[City, ...]
    past_days: int = 7
    # Wall-clock cap per city for the whole Open-Meteo call, *including* every
    # retry the session performs internally (spec/04-ingestion.md OQ4).
    timeout_seconds: float = 20.0
    # Socket timeout of one HTTP attempt underneath the retry adapter. Kept
    # well under timeout_seconds so a hung socket is retried, not waited on.
    per_attempt_timeout: int = 8
    retries: int = 2
    source: str = SOURCE
    # Overridable so the TIMEOUT / MALFORMED branches can be demonstrated
    # against an unreachable or wrong endpoint (see README).
    open_meteo_url: str = OPEN_METEO_URL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        database_url = env.get("DATABASE_URL", "").strip()
        if not database_url:
            raise ConfigError("DATABASE_URL is not set")
        cities = load_cities(Path(env.get("CITIES_CONFIG", "/config/cities.json")))
        try:
            past_days = int(env.get("PAST_DAYS", "7"))
            timeout_seconds = float(env.get("FETCH_TIMEOUT_SECONDS", "20"))
        except ValueError as exc:
            raise ConfigError(f"invalid numeric setting: {exc}") from exc
        if past_days < 0 or timeout_seconds <= 0:
            raise ConfigError("PAST_DAYS must be >= 0 and FETCH_TIMEOUT_SECONDS > 0")
        return cls(
            database_url=database_url,
            cities=cities,
            past_days=past_days,
            timeout_seconds=timeout_seconds,
            open_meteo_url=env.get("OPEN_METEO_URL", OPEN_METEO_URL).strip() or OPEN_METEO_URL,
        )


def load_cities(path: Path) -> tuple[City, ...]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cities = tuple(
            City(id=str(c["id"]), name=str(c["name"]), lat=float(c["lat"]), lon=float(c["lon"]))
            for c in raw["cities"]
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ConfigError(f"cannot read cities config at {path}: {exc}") from exc
    if len(cities) < 3:
        raise ConfigError("the case requires at least three cities")
    if len({c.id for c in cities}) != len(cities):
        raise ConfigError("city ids must be unique")
    return cities
