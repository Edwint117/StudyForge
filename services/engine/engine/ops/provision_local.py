"""Set the local worker password from private stdin, never argv or logs."""

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    admin_url: str
    password: str = Field(min_length=32, max_length=200)

    @model_validator(mode="after")
    def local_only(self) -> "Input":
        url = urlsplit(self.admin_url)
        if url.hostname not in ("localhost", "127.0.0.1") or url.port != 54322 or url.path != "/postgres":
            raise ValueError("Local database required")
        return self


async def main() -> None:
    config = Input.model_validate_json(sys.stdin.buffer.read(16384))
    async with await psycopg.AsyncConnection.connect(config.admin_url) as connection:
        template = Path(__file__).with_name("set_worker_password.sql").read_text()
        # This is psycopg's sql.SQL/sql.Literal composition (safe, escapes at the driver level), not raw string
        # concatenation. The rule below is written for SQLAlchemy's .execute() and false-positives on psycopg.
        await connection.execute(  # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
            sql.SQL(template).format(sql.Literal(config.password))
        )


if __name__ == "__main__":
    try:
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(main())
        print(json.dumps({"ok": True, "code": "ok"}))
    except Exception as error:
        # Fixed diagnostic categories, never driver messages, SQL or credentials.
        code = "database_error" if isinstance(error, psycopg.Error) else "configuration_error"
        print(json.dumps({"ok": False, "code": code}))
