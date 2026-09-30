from typing import Any

import pytest
from fastapi.testclient import TestClient

from engine import app as app_module
from engine.transport.http import SecurityBoundary


class Drainer:
    async def drain(self, queue: str, budget_seconds: int = 30) -> int:
        return 0


class OpenLimiter:
    def __init__(self) -> None:
        self.buckets: list[str] = []

    async def allow(self, bucket: str, subject: str) -> bool:
        self.buckets.append(bucket)
        return True


def build(limiter: OpenLimiter | None = None) -> Any:
    application = app_module.create_app(object(), Drainer(), rpc_secret="r" * 32, wake_secret="w" * 32)  # type: ignore[arg-type]
    application.user_middleware.clear()
    application.middleware_stack = application.build_middleware_stack()
    if limiter is None:
        return application
    return SecurityBoundary(application, verifier=None, limiter=limiter)  # type: ignore[arg-type]


@pytest.mark.parametrize("path", ["/health", "/healthz"])
def test_both_health_paths_answer_ok(path: str) -> None:
    # Catches a regression where the public-facing /health path (Cloud Run reserves /healthz) stops existing.
    response = TestClient(build()).get(path)
    assert response.status_code == 200 and response.json() == {"status": "ok", "service": "engine"}


@pytest.mark.parametrize("path", ["/health", "/healthz"])
def test_health_is_reachable_without_a_signature_and_uses_its_own_rate_bucket(path: str) -> None:
    # Catches /health being treated as an invalid path: 401 without a signature, or lumped into the "invalid" bucket.
    limiter = OpenLimiter()
    response = TestClient(build(limiter)).get(path)
    assert response.status_code == 200
    assert limiter.buckets == [path]


def test_unknown_paths_still_require_authentication() -> None:
    # Catches the health allowance widening to other paths.
    limiter = OpenLimiter()
    response = TestClient(build(limiter)).get("/healthy")
    assert response.status_code == 401
    assert limiter.buckets == ["invalid"]
