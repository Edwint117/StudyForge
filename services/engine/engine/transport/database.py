"""Async PostgreSQL security adapters. SQL is kept next to its caller."""

import hashlib
import hmac
from pathlib import Path

from psycopg_pool import AsyncConnectionPool

from engine.transport.signatures import Scope

_CLAIM = Path(__file__).with_name("claim_nonce.sql").read_text()
_LIMIT = Path(__file__).with_name("rate_limit.sql").read_text()


class DatabaseSecurity:
    def __init__(self, pool: AsyncConnectionPool, hash_secret: str) -> None:
        self._pool = pool
        self._hash_secret = hash_secret.encode()

    async def claim(self, scope: Scope, nonce: str, expires_at: int) -> bool:
        async with self._pool.connection() as connection:
            row = await (await connection.execute(_CLAIM, (scope, nonce, expires_at))).fetchone()
            return row is not None and row[0] is True

    async def allow(self, route: str, subject: str) -> bool:
        key = hmac.new(self._hash_secret, f"engine:{route}:{subject}".encode(), hashlib.sha256).hexdigest()
        async with self._pool.connection() as connection:
            row = await (await connection.execute(_LIMIT, (key, 120, 60))).fetchone()
            return row is not None and row[0] is True
