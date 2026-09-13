"""One error shape for every non-2xx response (spec/03-api.md §4).

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This file makes every failure look identical on the outside while meaning
something precise on the inside.

Identical on the outside means that whatever goes wrong, the dashboard gets
back the same three pieces of information: a short code it can act on, a
sentence a person can read, and the numeric status. Without this, each kind of
failure would come back shaped differently and the dashboard would need a
special case for each one.

Precise on the inside means the numbers are used strictly, and this is the
part worth understanding because it is easy to get wrong:

  * 400 says the question itself was not valid. A city we do not have, a date
    that is not a date, a number outside the allowed range.
  * 404 says the question was perfectly valid but we have nothing to answer it
    with yet. Usually this means an ingest has not run for that city.
  * 503 says we are the problem. The database is unreachable or too slow.
  * 500 says something broke that we did not anticipate.

The distinction between 404 and 503 is the one that matters most. Collapsing
them would mean an outage of our own looked exactly like an ordinary empty
result, and the dashboard would cheerfully tell you there is no data when the
truth is that nobody could ask. Keeping them apart is what lets the dashboard
say "nothing here yet" and "we could not reach the service" as different
things.

One small piece of housekeeping also lives here. The web framework's own
default for a badly formed request is a different number, 422, which would
break the scheme above, so it is caught and relabelled as 400.

400 - the request itself is wrong (unknown city, malformed/out-of-range param)
404 - the request is fine, there is simply no data for it
503 - our fault: the database cannot be reached or queried
500 - a bug we did not anticipate
"""
from __future__ import annotations

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "status": status}},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default is 422; the spec reserves 400 for bad requests.
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("query", "path"))
            parts.append(f"{loc}: {err.get('msg')}")
        return error_response(400, "INVALID_PARAMETER", "; ".join(parts) or "invalid request")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(psycopg.Error)  # also covers psycopg_pool.PoolTimeout
    async def _database(_: Request, exc: psycopg.Error) -> JSONResponse:
        log.error("database unavailable: %s: %s", type(exc).__name__, exc)
        return error_response(
            503, "DATABASE_UNAVAILABLE", "The database is unavailable; try again shortly."
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return error_response(500, "INTERNAL_ERROR", "Unexpected server error.")
