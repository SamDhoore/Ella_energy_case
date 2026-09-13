"""Assembles the API service and starts it.

HOW THIS FILE WORKS, IN PLAIN LANGUAGE
--------------------------------------
This is the front door. It is short on purpose: it does no work of its own, it
just puts the other files together in the right order and hands the result to
the web server.

It reads the settings first, and does so immediately on startup so that a
missing database address stops the service there and then rather than causing
every request to fail later for reasons nobody can see.

It then opens the pool of database connections, but deliberately does not wait
for the database to answer before declaring itself ready. This is what lets
the API start up alongside the database rather than after it. If a request
arrives while the database is still starting, that request gets an honest
"we are having trouble" answer, which is far better than the whole service
refusing to start and having to be restarted by hand.

It also grants the dashboard permission to call it. Browsers refuse by default
to let a page loaded from one address call a service at a different one, and
the dashboard and the API are on different addresses. Without the permission
granted here, every call from the dashboard would be blocked by the browser
before it was even sent.

Finally it attaches the shared error handling from errors.py and the endpoints
from routes.py, so that every address answers consistently and every failure
comes back in the same shape.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings
from .db import make_pool
from .errors import install_error_handlers
from .routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = Settings.from_env()  # fail fast at import if misconfigured


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.settings = settings
    app.state.pool = make_pool(settings.database_url)
    # Don't block startup on the database: a request made while it is down
    # gets an honest 503 instead of the whole service refusing to boot.
    app.state.pool.open(wait=False)
    try:
        yield
    finally:
        app.state.pool.close()


app = FastAPI(
    title="Belgian Weather Explorer API",
    version="0.1.0",
    description="Read-only access to ingested Open-Meteo forecasts and their revisions.",
    lifespan=lifespan,
)
# The dashboard's JavaScript runs in the browser on a different origin
# (localhost:3000 -> localhost:8000), so CORS is required (spec/00 §10).
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allow_origins),
    allow_methods=["GET"],
    allow_headers=["*"],
)
install_error_handlers(app)
app.include_router(router)
