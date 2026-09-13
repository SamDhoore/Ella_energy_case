# 03 — API

This is the layer I deliberately specified least. Both ends were already
fixed: the database contents were known and the dashboard's needs were known.
So I stated the constraints that mattered to me and left the surface design
open.

## What I specified

- FastAPI, read-only. It never writes to the database.
- Derive the endpoint list from the dashboard spec: every dashboard control
  maps to a query parameter. Propose the surface yourself.
- It must cover at minimum: latest forecast per city, revision history for a
  given city and target time, the daily matrix, available forecast dates per
  city, and ingestion health.
- Per endpoint: path, parameters, validation rules, response shape, error
  cases.
- Distinguish 400 for a bad request, 404 for a valid request with no data, and
  503 when the fault is ours. One shared error shape. ISO 8601 UTC timestamps
  throughout.

## Claude derived

- **The endpoint list itself**, including two I had not asked for: one listing
  the cities, because the selector needs its options from somewhere, and a
  health check for the container.
- **The rule for which failure is which.** An unknown city is a bad request,
  because the city list is a closed set we define, so an unrecognised name is
  an invalid option rather than missing data. A known city with nothing stored
  yet is the opposite.
- **One deliberate exception to that rule.** "Nothing has ever been ingested
  for this city" is itself a true health answer, so the health endpoint
  reports it as a normal answer with empty fields rather than as missing data.
- **Read-only enforced by the database**, not only in the code. Every
  connection is opened read-only, so a bug could not write even if it tried.
- **Time limits on queries and a pool of reused connections**, so one slow
  query becomes an honest error rather than a page that never loads.
- **A remapping of the framework's own default status** for a malformed
  request, which would otherwise have broken the three-way split I asked for.

## What Claude checked against the running system

Every endpoint, and each of the three failure kinds, were exercised against
the live stack rather than assumed. The 503 path was confirmed by stopping the
database and checking that a forecast request reports our fault rather than
absent data.
