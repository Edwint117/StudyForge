from typing import Any

from fastapi.testclient import TestClient

from engine import app as app_module
from engine.jobs import health as health_module
from engine.jobs.health import (
    BACKLOG_SECONDS,
    BacklogAlert,
    DeadJobsAlert,
    JobHealth,
    JobHealthMonitor,
    StuckJobsAlert,
    problems,
)


def snapshot(dead: int = 0, stuck: int = 0, backlog: int = 0, oldest: int = 0) -> JobHealth:
    return JobHealth(dead_recent=dead, stuck=stuck, backlog=backlog, oldest_queued_seconds=oldest)


def test_a_healthy_queue_raises_nothing() -> None:
    assert problems(snapshot(backlog=40, oldest=BACKLOG_SECONDS)) == []


def test_each_degradation_maps_to_its_own_alert_type() -> None:
    found = problems(snapshot(dead=1, stuck=2, oldest=BACKLOG_SECONDS + 1))
    assert [type(e) for e in found] == [DeadJobsAlert, StuckJobsAlert, BacklogAlert]


def test_report_captures_alerts_without_counts_or_text(monkeypatch: Any) -> None:
    seen: list[str] = []
    monkeypatch.setattr(health_module, "capture", lambda e, **t: seen.append(type(e).__name__))
    monitor = JobHealthMonitor(pool=None)  # type: ignore[arg-type]

    async def fake() -> JobHealth:
        return snapshot(dead=3)

    monitor.snapshot = fake  # type: ignore[method-assign]
    import asyncio

    assert asyncio.run(monitor.report()).dead_recent == 3
    assert seen == ["DeadJobsAlert"]


def test_only_the_maintenance_wake_runs_the_health_check() -> None:
    calls: list[str] = []

    class Reporter:
        async def report(self) -> object:
            calls.append("report")
            return None

    class Drainer:
        async def drain(self, queue: str, budget_seconds: int = 30) -> int:
            return 0

    class NoSecurity:
        pass

    application = app_module.create_app(
        NoSecurity(),  # type: ignore[arg-type]
        Drainer(),  # type: ignore[arg-type]
        rpc_secret="r" * 32,
        wake_secret="w" * 32,
        health=Reporter(),
    )
    application.user_middleware.clear()
    application.middleware_stack = application.build_middleware_stack()
    client = TestClient(application)
    assert client.post("/wake", json={"queue": "ingest"}).status_code == 200
    assert calls == []
    assert client.post("/wake", json={"queue": "maintenance"}).status_code == 200
    assert calls == ["report"]
