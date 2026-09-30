"""Drain within the HTTP request lifetime; never acknowledge unfinished work."""

import asyncio
import contextlib
import secrets
import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict, JsonValue

from engine.jobs.dispatch import LONG_TYPES, CloudRunDispatcher
from engine.jobs.repository import Job, JobRepository, Queue

Handler = Callable[[Job], Awaitable[dict[str, JsonValue]]]


class ProbePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


async def probe(job: Job) -> dict[str, JsonValue]:
    """Idempotent deployment smoke job; no external effects or user content."""
    ProbePayload.model_validate(job.payload)
    return {"ok": True}


class Worker:
    def __init__(
        self,
        repository: JobRepository,
        handlers: dict[str, Handler] | None = None,
        dispatcher: CloudRunDispatcher | None = None,
    ) -> None:
        self.repository = repository
        self.handlers = (
            handlers
            if handlers is not None
            else {
                "maintenance.probe": probe,
                "maintenance.probe_long": probe,
            }
        )
        self.dispatcher = dispatcher

    async def process(self, job: Job) -> bool:
        async def execute() -> dict[str, JsonValue]:
            handler = self.handlers.get(job.type)
            if handler is None:
                raise ValueError("Unsupported job type")
            return await handler(job)

        async def keep_lease() -> None:
            while True:
                await asyncio.sleep(self.repository.visibility_seconds / 3)
                if not await self.repository.heartbeat(job, {"stage": "running"}):
                    raise RuntimeError("Job lease lost")

        work = asyncio.create_task(execute())
        heartbeat = asyncio.create_task(keep_lease())
        try:
            done, _ = await asyncio.wait((work, heartbeat), return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done:
                # A lost/uncertain lease must not acknowledge or retry someone else's job.
                await heartbeat
            result = await work
            return await self.repository.finish(job, True, result)
        except asyncio.CancelledError:
            raise  # Leave message leased; visibility timeout recovers process death/cancellation.
        except Exception:
            if heartbeat.done():
                return False
            delay = min(3600, 2 ** min(job.attempts, 10) + secrets.randbelow(5))
            return await self.repository.finish(job, False, {}, delay)
        finally:
            for task in (work, heartbeat):
                task.cancel()
            for task in (work, heartbeat):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def drain(self, queue: Queue, budget_seconds: float = 3000) -> int:
        count = 0
        deadline = time.monotonic() + budget_seconds
        while time.monotonic() < deadline:
            job = await self.repository.take(queue)
            if job is None:
                break
            if self.dispatcher is not None and job.type in LONG_TYPES:
                # Leave enough visibility for Cloud Run startup. A failed dispatch is retried by VT recovery.
                if await self.repository.heartbeat(job, {"stage": "dispatching"}, visibility_seconds=300):
                    await self.dispatcher.dispatch(job)
                count += 1
                continue
            try:
                async with asyncio.timeout(max(0.001, deadline - time.monotonic())):
                    await self.process(job)
            except TimeoutError:
                break
            count += 1
        return count
