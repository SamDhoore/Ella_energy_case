# 00 — Architecture

## What I specified

- Four services via docker compose: db (postgres, named volume, healthcheck),
  ingest (python batch job), api (FastAPI), web (Next.js).
- Specify the startup order and why.
- Specify which services publish ports outward and which stay internal.
- Specify how services address each other, and the localhost versus
  container-hostname distinction for browser-side calls from the dashboard.
- Scheduling via a cron container inside compose rather than a GitHub Action,
  because the case tests a fresh clone literally, so the system must be
  self-contained.

## Claude derived

I asked for those things to be specified. The answers below are Claude's.

- **A fifth container.** Cron became its own service sharing the ingest image
  and overriding the command, so a fresh clone gets data immediately from the
  one-shot run while the scheduler keeps it current, without two copies of the
  ingestion code.
- **The startup order itself.** Ingest, cron and api wait until the database
  reports itself genuinely ready. Web waits for nothing, because it never
  calls the API itself; the browser does, later.
- **Which ports.** Api and web are published because a browser must reach
  them. Database, ingest and cron publish nothing.
- **How the schema is created.** One SQL file run automatically the first time
  the storage volume is made. No migrations, so a schema change means
  destroying the database.
- **Credentials in plain text in the compose file**, because a `.env` file is
  git-ignored and a fresh clone would not have one.
- **One city config file mounted into three containers**, so the writer and
  the readers cannot disagree about which cities exist.

## Known gap Claude found

The database is the only service with no automatic restart policy. After a
machine reboot the others come back and find nothing to talk to. Not fixed,
because it does not affect a fresh-clone test.
