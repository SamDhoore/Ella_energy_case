# Belgian Weather Explorer

Ingests Open-Meteo forecasts for four Belgian cities into PostgreSQL, serves
them through a read-only FastAPI service, and shows them in a Next.js +
shadcn/ui dashboard. Every daily forecast *issue* is kept, so the system can
answer both "what is the latest forecast for Ghent tomorrow at 14:00?" and
"what did the forecast for that hour look like yesterday?".

## Run it

```bash
docker compose up --build
```

| What | Where |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs (OpenAPI) | http://localhost:8000/docs |
| Ingestion health | http://localhost:8000/ingestion/health |

Ports can be moved without editing files: `API_PORT=8080 WEB_PORT=3001 docker compose up --build`.
Start over from an empty database with `docker compose down -v`.

On startup the database is created and filled within a few seconds, the API
begins serving, and the scheduler waits for its next daily run. Nothing else
needs installing or configuring.

The dashboard has four panels: the coming hours with one line per forecast
issue, how the forecast for one chosen moment has moved over previous days,
whether ingestion is healthy, and a table of daily figures. Each panel
distinguishes loading, nothing to show yet, and could not reach the service.

## Repository layout

```
spec/            claude-spec.md  the record of how I directed the tool: what I
                 specified upfront and what I corrected afterwards
                 00-04           one file per layer, each split the same way
db/init.sql      schema and indexes (spec/02)
ingest/          Python batch job + scheduler, with unit tests (spec/04)
api/             FastAPI service (spec/03)
web/             Next.js dashboard (spec/01)
config/cities.json  the single list of cities, mounted into ingest, cron and api
docker-compose.yml  five services: db, ingest, cron, api, web (spec/00)
```

## Architecture

Five principles. The detail is in `spec/`, and the API documents itself at
`/docs`.

### Keep every answer, never overwrite

A forecast is not one fact. Ask on Monday what Thursday afternoon looks like,
then ask again on Wednesday, and the answers differ.

One call to the weather service returns some past days plus the days ahead, as
a single snapshot taken at one moment. That is not a history of how the
forecast changed, and no single call could be, because the past part records
what actually happened rather than what was predicted.

So revisions only exist if you ask repeatedly and keep every answer. A new
ingestion adds a forecast alongside yesterday's rather than replacing it, and
that accumulation is the history. Within a single day a repeat replaces
instead, since the day has not changed and a later fetch is simply a better
copy of the same forecast.

Worth knowing before opening the dashboard: a fresh clone holds one forecast
per city, so the revision views show a single line and a single point. The
system has to run on two separate days before revisions appear.

### Put each ingestion guarantee where it can actually be enforced

The brief names three safety properties. The useful question was not how to
implement each one, but where each belongs.

Two are the code's job, because both concern what comes back from the weather
service: whether the reply is the shape we expect, and whether a reply arrives
at all. Both are handled per city.

The third cannot be. Not creating duplicates is not something the code can
promise itself, because it has no memory between runs. It needs the database
to hold what has already been done and to refuse a second copy. The same
turned out to be true of never leaving half-written data, which is the
database's job, as a transaction.

That split is why the code is shaped the way it is, and it is the piece of
thinking I would defend first.

### Let every piece fail on its own

Nothing calls anything else's code. Ingestion writes to the database and knows
nothing about the API. The API reads and knows nothing about ingestion. The
browser talks only to the API. Inside ingestion, each city succeeds or fails
alone.

So ingestion can fail for a week while the dashboard keeps serving the last
good data behind a visible warning. One unreachable city does not cost you the
other three. The API can restart mid-ingest without corrupting anything.

### Be honest about which kind of failure it was

A system that reports every problem the same way teaches people to ignore it.
Three kinds are kept apart everywhere: the question was not valid, the question
was valid but there is nothing to answer it with yet, or we ourselves are
broken.

The last two are the pair that matters. Collapsed together, an outage of our
own looks exactly like an ordinary empty result, and the dashboard would tell
someone there is no data when the truth is that nobody could ask. They are
shown as different things, and a failed ingestion is a visible warning rather
than a silent gap.

### Everything runs from one command

The case says a fresh clone will be tested literally, so scheduling lives in a
container inside the stack rather than in CI. A GitHub Action would never run
for someone who only clones and starts the system.

The same reasoning put the database credentials in plain text in the compose
file, rather than in a git-ignored environment file that a fresh clone would
not have. Correct here, wrong for anything real.

## Verifying the safety properties yourself

```bash
# Idempotency: run the ingest a second time, forecast counts do not move
docker compose exec db psql -U weather -c "select count(*) forecast_runs from forecast_run" -c "select count(*) forecast_values from forecast_value"
docker compose run --rm ingest
docker compose exec db psql -U weather -c "select count(*) forecast_runs from forecast_run" -c "select count(*) forecast_values from forecast_value"

# Resilience: unreachable upstream -> TIMEOUT rows, exit 0, existing data untouched
# (rebuild first if you have edited ingest/: docker compose build ingest)
docker compose run --rm -e OPEN_METEO_URL=http://10.255.255.1:9/v1/forecast -e FETCH_TIMEOUT_SECONDS=5 ingest
curl -s "http://localhost:8000/ingestion/health?city=ghent"

# Resilience: an HTTP error body -> MALFORMED
docker compose run --rm -e OPEN_METEO_URL=https://api.open-meteo.com/v1/nonexistent ingest

# Then a normal run clears the warning
docker compose run --rm ingest

# Unit tests for the validation branch (no network, no database, no local Python)
docker compose run --rm -v "$PWD/ingest/tests:/srv/tests:ro" --entrypoint sh ingest \
  -c "pip install -q pytest && python -m pytest -q tests"
```

With a local Python 3.10+ instead of Docker:

```bash
cd ingest && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && pytest
```

## How I approached this

I do not have a software engineering background. That shaped the method more
than it shaped the result, so it is worth describing honestly.

### Getting oriented

I started in a separate Claude conversation, before writing any specification,
to work out what a problem like this actually requires. That began further back
than the case itself does, with installing Claude Code and getting a working
toolchain. From there it moved to the real question: what the technical building
blocks of a system like this are, and why each one exists.

Those chat histories are shared alongside this repository. They are the least
polished part of the submission and the most representative of how I worked.

### Deciding what to build, in a deliberate order

I worked backwards from the output.

**The dashboard came first.** Before thinking about ingestion or storage, I
decided what a person should be able to see and ask. That fixed which data had
to exist, which in turn fixed what ingestion had to fetch and what the database
had to hold. Designing storage first would have meant guessing at requirements I
had not yet articulated.

**Ingestion came second, and this is where the most useful thinking happened.**
The brief names three safety properties. Rather than treat them as one list, I
asked where each one belongs.

Two are the code's job:

- Checking a response is in the expected shape before trusting it.
- Handling the upstream being slow or down, and recovering without taking the
  rest of the run down too.

The third is not. Not creating duplicates cannot be a promise the code makes to
itself, because the code has no memory between runs. It needs the database to
hold the record of what has already been ingested and to refuse a second copy
structurally. That became the unique key on city and forecast date.

Working through that split is what I would point to if asked what I contributed
beyond prompting. The same reasoning turned out to extend to atomicity, which
also belongs to the database, as a transaction, rather than to the code.

One refinement came out of implementation. My instinct was that a repeat request
should be ignored. The system instead replaces, because a forecast fetched later
the same day may have been revised and the newer reading is the one worth
keeping. The guarantee I wanted holds either way: running twice never leaves two
copies.

**The API came third, and I deliberately specified it least.** By that point
both ends were fixed: the database contents were known and the dashboard's needs
were known. So I stated the constraint that mattered to me, which was that
responses need distinct structures depending on what the outcome is, and left
the rest of the surface design open.

### From specification to code

I turned the above into pseudocode describing what each module should do, then
used Claude Code to turn that into a working program.

That pseudocode is not what now sits in `spec/`. Once the code existed, keeping
a long parallel description of it seemed like a liability rather than an asset,
since the two would drift apart and the code is the one that is true. So the
specs were cut back to what code cannot express: why each decision was made,
what I assumed, and what is still wrong. The step-by-step description of what
each file does moved to the top of the file itself, where it cannot drift.

### Testing and correcting

I exercised the functionality rather than reading every line, and it behaved
correctly. Then I iterated on the places where my specification had been
ambiguous and the result was not what I meant. Three corrections changed the
product:

- I had described the target-time control loosely and got a small table beneath
  the hourly chart. What I wanted was a view of its own: pick a future moment,
  see the current estimate, and see how the prediction for that exact moment
  moved over time. That is now the second pane.
- I asked whether a seven day history window grows each day. It does not, and
  confirming it surfaced something worth documenting about how consecutive
  windows overlap.
- I checked whether each forecast hour is a separate request. It is not, and the
  specs had left that to inference.

### Time spent

About five hours against the four hour guide. The overrun went into iteration
and into writing things down, not into getting it working.

### What I would do next

If this were my first project at Ella, the next step would not be more features.
It would be working through how the pseudocode actually became this code.

Claude Code produced more files than I expected, and I have not read every one
closely. I understand the flow end to end and can defend the design decisions,
but I would not claim familiarity with every file. Closing that gap is what
would let me catch a mistake by reading in future, rather than only by testing.

Concretely: I know the ingestion loop and its failure handling well, because
that is where my own reasoning is most directly encoded. The API's error
handling and the dashboard's state handling I understand in principle and would
want to study properly.

## What I cut for time

These are technical gaps I chose to leave, as distinct from the personal
study I would do next, described above.

- **No automated database integration test.** Idempotency and atomicity are
  verified by the manual procedure above; the next step is a pytest that
  runs the loop twice against a throwaway Postgres and asserts row counts,
  then injects a failure mid-transaction.
- **A fresh clone shows one issue per city**, so the hourly pane draws one
  line and the evolution pane one point until the next daily ingest. Open-Meteo's Previous Runs API could seed genuine
  earlier issues on first start; not done because it is a second endpoint
  with different semantics.
- **Schema is `init.sql` only**, executed on a fresh volume; there are no
  migrations, so a schema change today means `docker compose down -v`.
- **Daily aggregates are over UTC days**, one to two hours off Belgian civil
  days, for consistency with "all timestamps UTC".
- **No pagination, authentication or retention policy** on the API; row
  counts stay small at one issue per city per day, but "thousands of
  locations" would need all three.
- **The scheduler is a Python sleep loop**, not `cron(8)`; enough here, but
  a real deployment would use the orchestrator's scheduler.
- **The dashboard does not poll**; ingestion health refreshes on city change
  or reload.
