import pytest
from pydantic import ValidationError

from engine.runtime import Settings

BASE = {"ENGINE_RPC_SECRET": "r" * 32, "ENGINE_WAKE_SECRET": "w" * 32}
POOLER = "postgresql://engine_worker.abcdefghijklmnopqrst:pw@aws-0-us-east-2.pooler.supabase.com:5432/postgres"
CA = "sslrootcert=/app/certs/supabase-prod-ca-2021.crt"


def production(url: str, poll: str = "0") -> Settings:
    return Settings(APP_ENV="production", ENGINE_DATABASE_URL=url, ENGINE_POLL_MODE=poll, **BASE)  # type: ignore[arg-type]


def test_production_accepts_verified_tls_with_the_pinned_ca() -> None:
    assert production(f"{POOLER}?sslmode=verify-full&{CA}").APP_ENV == "production"


@pytest.mark.parametrize(
    "url,poll",
    [
        (POOLER, "0"),  # no TLS settings at all
        (f"{POOLER}?sslmode=require", "0"),  # encrypted but unverified
        (f"{POOLER}?sslmode=verify-full", "0"),  # verify-full without a CA file cannot connect
        (f"{POOLER}?sslmode=verify-full&{CA}", "1"),  # polling is development-only
        ("postgresql://postgres:pw@db.example.invalid/postgres?sslmode=verify-full&" + CA, "0"),  # not the worker role
    ],
)
def test_production_rejects_weak_database_settings(url: str, poll: str) -> None:
    with pytest.raises(ValidationError):
        production(url, poll)
