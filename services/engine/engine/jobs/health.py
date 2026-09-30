"""Dead-letter, stuck-job and backlog monitoring, reported to Sentry through the scrubbing wrapper.

The database wakes the ``maintenance`` queue every five minutes (pg_cron). The engine reads aggregate counts from
``private.job_health()`` and raises one alert per problem kind. Counts go to structured logs; Sentry receives only the
exception type, because the scrubber drops message text. Sentry groups repeats of the same type.
"""

import logging
from pathlib import Path

from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict, Field

from engine.errors import capture

log = logging.getLogger("engine.jobs.health")
_HEALTH = Path(__file__).with_name("health.sql").read_text()
BACKLOG_SECONDS = 600  # a queued job older than this means wakes or workers are not keeping up


class DeadJobsAlert(Exception):
    """A job exhausted its attempts within the last hour (it is in the dead-letter set)."""


class StuckJobsAlert(Exception):
    """A running job has not heartbeated for five minutes and is still not recovered."""


class BacklogAlert(Exception):
    """Queued work is older than the backlog threshold."""


class JobHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    dead_recent: int = Field(ge=0)
    stuck: int = Field(ge=0)
    backlog: int = Field(ge=0)
    oldest_queued_seconds: int = Field(ge=0)


def problems(health: JobHealth) -> list[Exception]:
    found: list[Exception] = []
    if health.dead_recent > 0:
        found.append(DeadJobsAlert())
    if health.stuck > 0:
        found.append(StuckJobsAlert())
    if health.oldest_queued_seconds > BACKLOG_SECONDS:
        found.append(BacklogAlert())
    return found


class JobHealthMonitor:
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def snapshot(self) -> JobHealth:
        async with self.pool.connection() as connection:
            row = await (await connection.execute(_HEALTH)).fetchone()
        if row is None:
            raise RuntimeError("job health unavailable")
        return JobHealth(dead_recent=row[0], stuck=row[1], backlog=row[2], oldest_queued_seconds=row[3])

    async def report(self) -> JobHealth:
        health = await self.snapshot()
        found = problems(health)
        if found:
            log.warning("job health degraded", extra={"job_health": health.model_dump()})
        for alert in found:
            capture(alert)
        return health
