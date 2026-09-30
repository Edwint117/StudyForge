"""FastAPI engine: authenticated bounded RPC and synchronous request-lifetime drain."""

import asyncio
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from engine.errors import capture
from engine.jobs.repository import Queue
from engine.jobs.worker import Worker
from engine.transport.http import RateLimiter, SecurityBoundary, problem
from engine.transport.signatures import NonceStore, RequestVerifier


class SecurityStore(NonceStore, RateLimiter, Protocol):
    pass


class WakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    queue: Queue


class SympyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer_latex: str = Field(min_length=1, max_length=4096)
    expected_latex: str = Field(min_length=1, max_length=4096)


class HealthReporter(Protocol):
    async def report(self) -> object: ...


def create_app(
    security: SecurityStore,
    worker: Worker,
    *,
    rpc_secret: str,
    wake_secret: str,
    health: HealthReporter | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(
        SecurityBoundary,
        verifier=RequestVerifier(
            rpc_secret=rpc_secret,
            wake_secret=wake_secret,
            nonces=security,
        ),
        limiter=security,
    )
    slots = asyncio.Semaphore(4)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return problem(422, "invalid_request")  # Never echo the rejected body or validation input.

    @app.exception_handler(Exception)
    async def internal_error(request: Request, error: Exception) -> JSONResponse:
        capture(error, route=request.url.path)  # scrubbed: type + stack only; no-op without a DSN
        return problem(503, "engine_unavailable")

    # Cloud Run's Google front end reserves /healthz on public run.app URLs (it 404s before reaching the container),
    # so external checks use /health. /healthz stays for container-local probes and Compose.
    @app.get("/health")
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "engine"}

    @app.post("/wake")
    async def wake(body: WakeRequest) -> dict[str, int]:
        # Cloud Run CPU may stop after the response: all drain work stays inside this await.
        async with slots:
            processed = await worker.drain(body.queue)
            if body.queue == "maintenance" and health is not None:
                await health.report()  # the 5-minute pg_cron wake doubles as the DLQ/stuck-job check
            return {"processed": processed}

    @app.post("/rpc/sympy-equivalent")
    async def sympy(body: SympyRequest) -> dict[str, str]:
        from engine.transport.sympy import bounded_check

        async with slots:
            return await asyncio.to_thread(bounded_check, body.answer_latex, body.expected_latex)

    return app
