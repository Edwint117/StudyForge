"""Single-job entrypoint for the same engine image, fenced against duplicate dispatch."""

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from psycopg_pool import AsyncConnectionPool

from engine.jobs.repository import Job, JobRepository
from engine.jobs.worker import Worker
from engine.runtime import settings_from_environment, start_error_reporting


async def run(job_id: UUID, user_id: UUID, lease: UUID) -> None:
    settings = settings_from_environment()
    start_error_reporting(settings)
    async with AsyncConnectionPool(
        settings.ENGINE_DATABASE_URL, min_size=1, max_size=2, kwargs={"connect_timeout": 5}
    ) as pool:
        async with pool.connection() as connection:
            statement = Path(__file__).with_name("start_long.sql").read_text()
            row = await (await connection.execute(statement, (job_id, user_id, lease))).fetchone()
        if row is None or row[0] is None:
            return  # Duplicate/expired dispatch must not execute a handler.
        job = Job.model_validate(row[0])
        if not await Worker(JobRepository(pool)).process(job):
            raise RuntimeError("Job lease lost")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=UUID, required=True)
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--lease-token", type=UUID, required=True)
    args = parser.parse_args()
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(run(args.job_id, args.user_id, args.lease_token))


if __name__ == "__main__":
    main()
