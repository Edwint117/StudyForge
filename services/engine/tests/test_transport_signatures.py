"""Cross-runtime signatures and fail-closed replay protection. Owned by Codex."""

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from engine.transport.signatures import AuthenticationRejected, RequestVerifier, Scope


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str
    body: str
    secret: str
    timestamp: int
    nonce: str
    signature: str


FIXTURES = [
    Fixture.model_validate(row)
    for row in json.loads(
        (Path(__file__).resolve().parents[3] / "packages/engine-client/fixtures/signatures.json").read_text("utf-8")
    )
]


class TestNonces:
    __test__ = False

    def __init__(self) -> None:
        self.claims: dict[tuple[Scope, str], int] = {}

    async def claim(self, scope: Scope, nonce: str, expires_at: int) -> bool:
        key = (scope, nonce)
        if key in self.claims:
            return False
        self.claims[key] = expires_at
        return True


def verifier(row: Fixture, store: TestNonces) -> RequestVerifier:
    other = "unused-fixture-key-" + "x" * 32
    return RequestVerifier(
        rpc_secret=row.secret if row.path != "/wake" else other,
        wake_secret=row.secret if row.path == "/wake" else other,
        nonces=store,
    )


def headers(row: Fixture) -> dict[str, str]:
    return {"timestamp": str(row.timestamp), "nonce": row.nonce, "signature": row.signature}


@pytest.mark.parametrize("row", FIXTURES, ids=lambda row: row.path)
@pytest.mark.parametrize("skew", [-61, -60, 0, 60, 61])
def test_shared_vectors_and_timestamp_boundary(row: Fixture, skew: int) -> None:
    store = TestNonces()
    call = verifier(row, store).verify(
        method="POST", path=row.path, body=row.body.encode(), headers=headers(row), now=row.timestamp + skew
    )
    if abs(skew) > 60:
        with pytest.raises(AuthenticationRejected):
            asyncio.run(call)
        assert not store.claims
    else:
        asyncio.run(call)
        assert list(store.claims.values()) == [row.timestamp + 61]


@pytest.mark.parametrize("field", ["body", "path", "method", "nonce", "signature", "timestamp", "extra"])
def test_tampering_never_claims_nonce(field: str) -> None:
    row = FIXTURES[0]
    store = TestNonces()
    envelope = headers(row)
    if field in ("nonce", "signature", "timestamp"):
        envelope[field] = {
            "nonce": "22222222-2222-4222-8222-222222222222",
            "signature": "v1=" + "0" * 64,
            "timestamp": str(row.timestamp + 1),
        }[field]
    if field == "extra":
        envelope["unexpected"] = "untrusted"
    with pytest.raises(AuthenticationRejected):
        asyncio.run(
            verifier(row, store).verify(
                method="GET" if field == "method" else "POST",
                path="/rpc/run-code" if field == "path" else row.path,
                body=(row.body + (" " if field == "body" else "")).encode(),
                headers=envelope,
                now=row.timestamp,
            )
        )
    assert not store.claims


def test_two_verifiers_share_replay_protection() -> None:
    row = FIXTURES[0]
    store = TestNonces()

    async def send() -> list[BaseException | None]:
        return await asyncio.gather(
            *[
                verifier(row, store).verify(
                    method="POST", path=row.path, body=row.body.encode(), headers=headers(row), now=row.timestamp
                )
                for _ in range(2)
            ],
            return_exceptions=True,
        )

    results = asyncio.run(send())
    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, AuthenticationRejected) for result in results) == 1


def test_store_failure_propagates_without_fallback() -> None:
    class Unavailable(TestNonces):
        async def claim(self, scope: Scope, nonce: str, expires_at: int) -> bool:
            raise ConnectionError("store unavailable")

    row = FIXTURES[0]
    with pytest.raises(ConnectionError):
        asyncio.run(
            verifier(row, Unavailable()).verify(
                method="POST", path=row.path, body=row.body.encode(), headers=headers(row), now=row.timestamp
            )
        )


def test_separate_secrets_required() -> None:
    with pytest.raises(ValueError, match="Distinct engine secrets"):
        RequestVerifier(rpc_secret="x" * 32, wake_secret="x" * 32, nonces=TestNonces())
