"""Leased queue operations; every mutation supplies the job's trusted user_id."""

from pathlib import Path
from typing import Literal

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict, Field, JsonValue

Queue = Literal["ingest", "graph", "generate", "grade", "plan", "calendar", "srs", "io", "notify", "maintenance"]


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    job_id: str
    user_id: str
    type: str
    payload: dict[str, JsonValue]
    lease_token: str
    attempts: int = Field(ge=1)
    max_attempts: int = Field(ge=1, le=5)
    queue: Queue


_TAKE = Path(__file__).with_name("take.sql").read_text()
_HEARTBEAT = Path(__file__).with_name("heartbeat.sql").read_text()
_FINISH = Path(__file__).with_name("finish.sql").read_text()


class JobRepository:
    def __init__(self, pool: AsyncConnectionPool, visibility_seconds: int = 60) -> None:
        self.pool = pool
        self.visibility_seconds = visibility_seconds

    async def take(self, queue: Queue) -> Job | None:
        async with self.pool.connection() as connection:
            row = await (await connection.execute(_TAKE, (queue, self.visibility_seconds))).fetchone()
            return Job.model_validate(row[0]) if row and row[0] is not None else None

    async def heartbeat(self, job: Job, progress: dict[str, JsonValue], visibility_seconds: int | None = None) -> bool:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    _HEARTBEAT,
                    (
                        job.job_id,
                        job.user_id,
                        job.lease_token,
                        visibility_seconds if visibility_seconds is not None else self.visibility_seconds,
                        Jsonb(progress),
                    ),
                )
            ).fetchone()
            return row is not None and row[0] is True

    async def finish(self, job: Job, success: bool, result: dict[str, JsonValue], delay: int = 1) -> bool:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    _FINISH,
                    (
                        job.job_id,
                        job.user_id,
                        job.lease_token,
                        success,
                        Jsonb(result),
                        delay,
                    ),
                )
            ).fetchone()
            return row is not None and row[0] is True
