# 01 — Dashboard

## What I specified

- Executive dashboard, Next.js and shadcn/ui, read-only, calling our API only.
- Three inputs: a city selector, a target-time selector, a horizon selector
  for how far ahead to plot.
- **View A, hourly forecast:** temperature, precipitation amount,
  precipitation probability. The latest forecast plus how that forecast looked
  on previous days, as a line chart with one line per forecast date.
- **View B, daily matrix:** UV index max, max wind gusts, visibility, sunshine
  duration, max temperature. Latest forecast by default, with a dropdown to
  switch to an earlier forecast date, filled from what the database actually
  holds.
- **Ingestion health:** last successful ingest per city, and a visible warning
  if the most recent attempt failed.
- Loading, empty and error states for every view, and which API call each
  control triggers.
- Scope priority, highest first: View A, ingestion health, View B, the horizon
  selector. Cut from the bottom up and document each cut.

## Claude derived

- **Where the target-time selector belongs.** I named it as an input but never
  said which view it drives. Claude put it as a small table under View A. That
  was wrong, see below.
- **How the three states are decided.** A 404 from the API renders as empty, a
  network failure or a server error renders as an error with a retry button.
  I asked for the states; this is the rule that distinguishes them.
- **That the city selector needs its own API endpoint**, rather than a
  hardcoded list that could drift from what ingestion actually collects.
- **That View B's visibility has no source.** I listed it as a daily metric,
  but the weather service publishes no daily visibility and the daily
  variables I specified do not include one. Claude flagged the gap rather than
  quietly filling it, and derived the column as the lowest hourly reading of
  that day.
- **Captions that say so when only one forecast exists**, so a single line
  does not read as a broken chart.

## What I corrected after seeing the result

The target-time selector became a panel of its own rather than a table under
View A. Pick any future moment, see the current estimate first, then see how
the estimate for that exact moment moved over previous days. Newest forecast
on the left, so the current answer is read first. Same three metrics as View
A. Ranked second in priority, above ingestion health.

Nothing was cut in the end. The priority order above is what would have gone
first if time had run out.
