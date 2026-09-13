# 02 — Data model

## What I specified

- PostgreSQL, three tables.
- **ingest_run**, an operational log, one row per city per attempt:
  `run_id`, `city`, `status` (SUCCESS, TIMEOUT, MALFORMED, DB_ERROR),
  `rows_written`, `error_detail`, `started_at`, `finished_at`. This is what
  the API reads to report ingestion health.
- **forecast_run**, one row per city per forecast issue: `forecast_run_id`,
  `city`, `date_forecast_made` as a DATE, `fetched_at`, `source`, with
  `UNIQUE (city, date_forecast_made)` as the idempotency key. Explain why date
  granularity fits a daily cadence and what would have to change at a higher
  one.
- **forecast_value**, the measurements: the foreign key with cascade delete,
  `target_time`, `granularity` (HOURLY or DAILY), metric columns, all
  nullable. Decide and justify one table with a granularity column versus
  separate hourly and daily tables, and state the trade-off either way.
- All timestamps in UTC.
- The indexes that make "latest forecast for city X" and "all revisions for
  city X at target time T" fast, naming the query each index serves.

## Claude derived

- **The answer to the one-table question.** One table, because hourly and
  daily readings have identical lifetimes: same response, same transaction,
  deleted together. The cost is columns that do not apply to every row and a
  filter on every query. Two tables would type it more strictly at the price
  of duplicating the write path, the indexes and the API branch.
- **A uniqueness rule on the readings table** that I had not asked for.
  Without it the idempotency guarantee only holds at the forecast level, and
  a repeat run could still stack duplicate readings underneath one forecast.
- **That two indexes were redundant.** The ones I implied for "latest
  forecast" and for joining readings duplicated indexes the uniqueness rules
  already create. They were dropped, because a redundant index slows writes
  and buys nothing.
- **Constraints on the log table** so the statuses cannot contradict
  themselves: a row count only on success, an error message only on failure.
- **That "prediction or observation" need not be stored.** Comparing the hour
  to the moment of fetching answers it, so no column can drift from the values
  it describes.

## Known gap Claude found

There are no migrations. The schema is created once when the storage volume is
first made, so changing it means destroying and recreating the database.
