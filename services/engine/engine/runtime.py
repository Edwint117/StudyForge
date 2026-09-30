"""Production factory; operator configuration is validated without logging values."""

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from engine.app import create_app
from engine.errors import init_sentry
from engine.jobs.dispatch import CloudRunDispatcher
from engine.jobs.health import JobHealthMonitor
from engine.jobs.repository import JobRepository, Queue
from engine.jobs.worker import Worker
from engine.transport.database import DatabaseSecurity

QUEUES: tuple[Queue, ...] = (
    "ingest",
    "graph",
    "generate",
    "grade",
    "plan",
    "calendar",
    "srs",
    "io",
    "notify",
    "maintenance",
)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    APP_ENV: Literal["development", "production"]
    ENGINE_DATABASE_URL: str
    ENGINE_RPC_SECRET: str = Field(min_length=32)
    ENGINE_WAKE_SECRET: str = Field(min_length=32)
    ENGINE_POLL_MODE: Literal["0", "1"] = "0"
    GCP_PROJECT_ID: str = ""
    GCP_REGION: str = "us-east1"
    SENTRY_DSN: str = ""
    K_REVISION: str = ""  # set by Cloud Run services
    ENGINE_RELEASE: str = ""  # set by the deploy script (git sha); Cloud Run jobs have no K_REVISION

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        url = urlsplit(self.ENGINE_DATABASE_URL)
        if url.scheme not in ("postgres", "postgresql") or (url.username or "").split(".")[0] != "engine_worker":
            raise ValueError("Dedicated engine role required")
        if self.APP_ENV == "production" and (
            self.ENGINE_POLL_MODE != "0" or "sslmode=verify-full" not in url.query or "sslrootcert=" not in url.query
        ):
            raise ValueError("Production requires verified TLS (with the pinned CA file) and push wakes")
        return self


def start_error_reporting(settings: Settings) -> bool:
    release = settings.ENGINE_RELEASE or settings.K_REVISION or None
    return init_sentry(settings.SENTRY_DSN, environment=settings.APP_ENV, release=release)


def settings_from_environment() -> Settings:
    try:
        return Settings.model_validate({key: os.environ[key] for key in Settings.model_fields if key in os.environ})
    except ValidationError:
        raise RuntimeError("Invalid engine configuration; values suppressed") from None


def build_app() -> FastAPI:
    settings = settings_from_environment()
    start_error_reporting(settings)
    pool = AsyncConnectionPool(
        settings.ENGINE_DATABASE_URL, min_size=1, max_size=4, open=False, timeout=5, kwargs={"connect_timeout": 5}
    )
    security = DatabaseSecurity(pool, settings.ENGINE_RPC_SECRET)
    dispatcher = (
        CloudRunDispatcher(settings.GCP_PROJECT_ID, settings.GCP_REGION) if settings.APP_ENV == "production" else None
    )
    worker = Worker(JobRepository(pool), dispatcher=dispatcher)

    async def poll() -> None:
        while True:
            for queue in QUEUES:
                await worker.drain(queue, budget_seconds=30)
            await asyncio.sleep(2)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await pool.open(wait=True, timeout=10)
        polling = asyncio.create_task(poll()) if settings.ENGINE_POLL_MODE == "1" else None
        try:
            yield
        finally:
            if polling:
                polling.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await polling
            await pool.close()

    return create_app(
        security,
        worker,
        rpc_secret=settings.ENGINE_RPC_SECRET,
        wake_secret=settings.ENGINE_WAKE_SECRET,
        health=JobHealthMonitor(pool),
        lifespan=lifespan,
    )
