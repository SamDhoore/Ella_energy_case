"""Settings for the API service.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This is the API's settings desk, and it mirrors the one the ingestion job has.

It reads the database address and the allowed dashboard address from the
environment, and the list of cities from the same JSON file the ingestion job
reads. That shared file is the important part. Because both sides read the
same list, "is this a real city" means exactly the same thing to the writer
and to the reader, and neither can drift into recognising a city the other
does not.

It also holds the few numbers that decide what a request is allowed to ask
for: how far ahead a chart may look by default and at most, and how many past
forecasts may be overlaid. Those live here rather than being scattered through
the request handlers, so the limits can be seen and changed in one place.

The settings are read once when the service starts. If the database address is
missing the service refuses to start at all, rather than starting and failing
on every request.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


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
    cors_allow_origins: tuple[str, ...]
    default_horizon_hours: int = 48
    max_horizon_hours: int = 168
    default_max_revisions: int = 10
    max_max_revisions: int = 30

    @property
    def city_ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.cities)

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is not set")
        cities_path = Path(os.environ.get("CITIES_CONFIG", "/config/cities.json"))
        raw = json.loads(cities_path.read_text(encoding="utf-8"))["cities"]
        cities = tuple(
            City(id=str(c["id"]), name=str(c["name"]), lat=float(c["lat"]), lon=float(c["lon"]))
            for c in raw
        )
        origins = tuple(
            o.strip()
            for o in os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        )
        return cls(database_url=database_url, cities=cities, cors_allow_origins=origins)
