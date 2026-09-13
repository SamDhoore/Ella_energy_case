-- Schema for the Belgian Weather Explorer. See spec/02-data-model.md.
-- Postgres runs this file exactly once, when the named volume is first created.
-- All timestamps are timestamptz; the ingestion job and API only ever pass UTC.

CREATE TYPE ingest_status AS ENUM ('SUCCESS', 'TIMEOUT', 'MALFORMED', 'DB_ERROR');
CREATE TYPE forecast_granularity AS ENUM ('HOURLY', 'DAILY');

-- Operational log: one row per city per ingestion attempt, written once the
-- outcome is known (never insert-then-update; see spec/04-ingestion.md OQ1).
CREATE TABLE ingest_run (
    run_id        uuid          PRIMARY KEY,
    city          text          NOT NULL,
    status        ingest_status NOT NULL,
    rows_written  integer,
    error_detail  text,
    started_at    timestamptz   NOT NULL,
    finished_at   timestamptz   NOT NULL,
    CONSTRAINT ingest_run_rows_written_only_on_success
        CHECK ((status = 'SUCCESS') = (rows_written IS NOT NULL)),
    CONSTRAINT ingest_run_error_detail_only_on_failure
        CHECK ((status <> 'SUCCESS') = (error_detail IS NOT NULL))
);

-- Ingestion health: "most recent attempt / most recent SUCCESS for city X"
-- (ORDER BY started_at DESC LIMIT 1, optionally filtered on status).
CREATE INDEX ingest_run_city_started_desc_idx ON ingest_run (city, started_at DESC);

-- One row per city per forecast issue. (city, date_forecast_made) is the
-- idempotency key: a same-day re-run upserts into the same row.
CREATE TABLE forecast_run (
    forecast_run_id     bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    city                text        NOT NULL,
    date_forecast_made  date        NOT NULL,
    fetched_at          timestamptz NOT NULL,
    source              text        NOT NULL,
    CONSTRAINT forecast_run_city_date_uq UNIQUE (city, date_forecast_made)
);
-- forecast_run_city_date_uq's btree also serves
--   "latest forecast for city X"      : WHERE city = X ORDER BY date_forecast_made DESC LIMIT 1
--   "available forecast dates for X"  : WHERE city = X ORDER BY date_forecast_made DESC
-- via a backward index scan, so no separate DESC index is needed.

-- The measurements. One table for both granularities (spec/02-data-model.md §11);
-- hourly-only columns are NULL on DAILY rows and vice versa.
CREATE TABLE forecast_value (
    forecast_run_id           bigint               NOT NULL
                              REFERENCES forecast_run (forecast_run_id) ON DELETE CASCADE,
    target_time               timestamptz          NOT NULL,
    granularity               forecast_granularity NOT NULL,
    -- HOURLY metrics
    temperature_2m            double precision,   -- °C
    precipitation             double precision,   -- mm
    precipitation_probability double precision,   -- %
    visibility                double precision,   -- m
    wind_gusts_10m            double precision,   -- km/h
    -- DAILY metrics
    uv_index_max              double precision,
    temperature_2m_max        double precision,   -- °C
    wind_gusts_10m_max        double precision,   -- km/h
    sunshine_duration         double precision,   -- s
    -- Row-level idempotency key; its btree (leading column forecast_run_id)
    -- also serves every "values for this run" join and the cascade delete.
    CONSTRAINT forecast_value_run_target_gran_uq UNIQUE (forecast_run_id, target_time, granularity)
);

-- "All revisions for city X at target time T": resolve X's forecast_run_ids
-- via forecast_run_city_date_uq, then find rows at T through this index.
CREATE INDEX forecast_value_target_time_idx ON forecast_value (target_time);
