# 04 — Ingestion

## What I specified

- A Python batch job that writes to the database and exits. No connection to
  the API or dashboard; it reports outcomes solely by writing to `ingest_run`.
- Use the `openmeteo-requests` client, which already retries with backoff. Do
  not reimplement transport retries; handle what the library cannot.
- At least three Belgian cities, coordinates in config.
- The forecast endpoint, and the exact variables: hourly temperature,
  precipitation, precipitation probability, visibility and wind gusts; daily
  UV index max, max temperature, max wind gusts and sunshine duration.
- `past_days` of 7, and record why not larger: a longer window is backfill of
  past observations rather than forecast revision, and it inflates every
  payload. Raising it later is a config change, not a schema change.
- Three safety properties, specified separately and not conflated:
  - **Resilience**, per city: a 20 second timeout writes TIMEOUT and
    continues; a response that fails validation writes MALFORMED and
    continues; one city failing never stops the others; the job exits 0 on
    partial success.
  - **Atomicity**: all writes for one city in a single transaction; a crash
    mid-write rolls that city back entirely; previously completed cities are
    unaffected; state exactly where the transaction begins and commits.
  - **Idempotency**: upsert against the unique key; running twice leaves row
    counts unchanged; state how the code makes this true, not merely that it
    does.
- Pseudocode as an explicit per-city loop showing every branch and where each
  status is written.

## Claude derived

- **That the 20 second limit needs its own thread.** The library's retries can
  together outlast any single attempt's timeout, so the only way to make 20
  seconds a real ceiling is to run the call separately and stop waiting.
- **The split between the two failure kinds for cases I had not named.**
  Nothing came back at all is a timeout; an error page or a rejection came
  back is malformed. I named the two statuses but not which real failures map
  to which.
- **Clearing and rewriting rather than ignoring a duplicate.** My instinct was
  that a repeat should be dropped. A forecast fetched later the same day may
  have been revised, so the newer reading is the better one. Running twice
  still never leaves two copies.
- **Writing the attempt log outside the transaction**, so that a rolled-back
  write still leaves evidence it was tried. Inside it, a failure would erase
  its own record.
- **The validation checks**, including one I had not listed: that every
  variable asked for is actually present, not only that whatever arrived is
  internally consistent.

## What I asked about afterwards, and what it revealed

Two behaviours my spec had assumed without stating. Both are now written down
because neither is obvious.

- **The history window slides, it does not accumulate.** Each call measures
  seven days back from its own date, so tomorrow's call returns seven again,
  shifted by one. Consecutive days overlap heavily, and that overlap is what
  makes the same hour appear under several forecasts, which is what the
  revision history is made of.
- **One request per city returns the whole series.** There is no request per
  hour. Wanting tomorrow at 14:00 and at 15:00 means reading two entries from
  the same reply.

## Known gap Claude found

A missed run is not caught up. The scheduler works out the next daily time and
sleeps; if the machine is off at that moment, that day's forecast is never
captured, and the gap is permanent, because the forecast that would have been
given then no longer exists to ask for.
