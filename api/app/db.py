"""The API's connections to the database.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
Opening a fresh connection to a database is slow, and doing it for every
visitor would waste most of the time spent answering a request. So this file
keeps a small set of connections open and lends them out, one per request,
taking them back afterwards. That set is called a pool.

Two safeguards are attached to every connection as it is handed out, and both
matter more than they look.

The first is that each connection is opened in read-only mode. The API is
supposed to only ever read, and this makes the database itself enforce that
rather than trusting the code to behave. Even a bug that tried to write would
be refused at the database, which means the ingestion job's data cannot be
damaged from this side by accident.

The second is a ten second limit on any single question. Without it, one
unusually slow query could hold a connection open indefinitely and eventually
starve every other visitor. With it, a stuck query is cut off and the visitor
gets a clear "we are having trouble" answer instead of a page that never loads.

There is also a five second limit on waiting for a free connection when the
pool is busy, which turns a temporary overload into an honest error rather
than an ever-growing queue.
"""
from __future__ import annotations

from collections.abc import Iterator

import psycopg
from fastapi import Request
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def make_pool(database_url: str) -> ConnectionPool:
    return ConnectionPool(
        conninfo=database_url,
        min_size=1,
        max_size=8,
        open=False,
        timeout=5.0,  # seconds to wait for a pooled connection before PoolTimeout (-> 503)
        check=ConnectionPool.check_connection,
        kwargs={
            "row_factory": dict_row,
            "connect_timeout": 5,
            # The API never writes; make the database enforce that too, and
            # never let a query hang past 10s (-> 503 rather than a stuck request).
            "options": "-c default_transaction_read_only=on -c statement_timeout=10000",
        },
    )


def get_conn(request: Request) -> Iterator[psycopg.Connection]:
    pool: ConnectionPool = request.app.state.pool
    with pool.connection() as conn:
        yield conn
