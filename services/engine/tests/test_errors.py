import json
from typing import Any, ClassVar

import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from engine import errors
from engine.errors import REDACTED, init_sentry, scrub_breadcrumb, scrub_event

SECRET = "student answer: x=42 postgresql://engine_worker:hunter2@db/postgres"  # noqa: S105  (synthetic canary string, not a credential)


def _event() -> dict[str, Any]:
    return {
        "event_id": "e1",
        "level": "error",
        "message": SECRET,
        "logentry": {"message": SECRET},
        "request": {
            "url": "https://x/wake",
            "data": SECRET,
            "headers": {"authorization": "Bearer t"},
            "cookies": {"a": "b"},
        },
        "user": {"id": "u1", "email": "a@b.c"},
        "extra": {"answer": SECRET},
        "contexts": {"runtime": {"name": "CPython"}},
        "breadcrumbs": {"values": [{"message": SECRET}]},
        "server_name": "host",
        "tags": {"route": "/wake", "environment": "production", "email": "a@b.c"},
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": SECRET,
                    "mechanism": {"type": "generic"},
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "engine/app.py",
                                "function": "wake",
                                "lineno": 57,
                                "in_app": True,
                                "vars": {"body": SECRET},
                                "context_line": SECRET,
                                "pre_context": [SECRET],
                            }
                        ]
                    },
                }
            ]
        },
    }


def test_scrub_event_keeps_only_type_and_stack_shape() -> None:
    out = scrub_event(_event())
    assert out is not None
    assert "hunter2" not in json.dumps(out) and "student answer" not in json.dumps(out)
    for key in ("request", "user", "extra", "contexts", "breadcrumbs", "server_name", "logentry", "message"):
        assert key not in out
    assert out["tags"] == {"route": "/wake", "environment": "production"}
    (exc,) = out["exception"]["values"]
    assert exc["type"] == "ValueError" and exc["value"] == REDACTED
    assert exc["stacktrace"]["frames"] == [
        {"filename": "engine/app.py", "function": "wake", "lineno": 57, "in_app": True}
    ]


def test_scrub_event_handles_minimal_events() -> None:
    assert scrub_event({"event_id": "x"}) == {"event_id": "x"}
    assert scrub_event({"exception": {"values": [{"type": "E"}]}}) == {
        "exception": {"values": [{"type": "E", "value": REDACTED}]}
    }
    assert scrub_breadcrumb({"message": SECRET}) is None


def test_disabled_without_dsn() -> None:
    assert init_sentry("", environment="development") is False


class _Capture(Transport):
    sent: ClassVar[list[Any]] = []

    def capture_envelope(self, envelope: Any) -> None:
        for item in envelope.items:
            if item.headers.get("type") == "event":
                self.sent.append(item.payload.json)


def test_real_sdk_sends_only_scrubbed_events() -> None:
    _Capture.sent = []
    sentry_sdk.init(
        dsn="https://public@example.invalid/1",
        transport=_Capture,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        before_send=errors.scrub_event,  # type: ignore[arg-type]
        before_breadcrumb=errors.scrub_breadcrumb,  # type: ignore[arg-type]
    )
    try:
        secret_local = SECRET  # noqa: F841
        raise ValueError(SECRET)
    except ValueError as error:
        errors.capture(error, route="/wake", email="a@b.c")
    sentry_sdk.flush()
    sentry_sdk.init()  # detach
    assert len(_Capture.sent) == 1
    text = json.dumps(_Capture.sent[0])
    assert "hunter2" not in text and "student answer" not in text
    assert _Capture.sent[0]["exception"]["values"][0]["type"] == "ValueError"
    assert _Capture.sent[0]["tags"] == {"route": "/wake"}


def test_unhandled_route_error_returns_503_and_reports(monkeypatch: Any) -> None:
    from engine import app as app_module

    seen: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(app_module, "capture", lambda e, **t: seen.append((type(e).__name__, t)))

    class Boom:
        async def drain(self, queue: str, budget_seconds: int = 30) -> int:
            raise RuntimeError(SECRET)

    class NoSecurity:
        pass

    application = app_module.create_app(NoSecurity(), Boom(), rpc_secret="r" * 32, wake_secret="w" * 32)  # type: ignore[arg-type]
    application.user_middleware.clear()
    application.middleware_stack = application.build_middleware_stack()
    response = TestClient(application, raise_server_exceptions=False).post("/wake", json={"queue": "ingest"})
    assert response.status_code == 503 and SECRET not in response.text
    assert seen == [("RuntimeError", {"route": "/wake"})]


def test_release_prefers_deploy_sha_over_cloud_run_revision(monkeypatch: Any) -> None:
    from engine import runtime

    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(runtime, "init_sentry", lambda dsn, **kw: calls.append({"dsn": dsn, **kw}) or True)
    base = {
        "APP_ENV": "development",
        "ENGINE_DATABASE_URL": "postgresql://engine_worker@h/db",
        "ENGINE_RPC_SECRET": "r" * 32,
        "ENGINE_WAKE_SECRET": "w" * 32,
        "SENTRY_DSN": "https://x@o.invalid/1",
    }
    runtime.start_error_reporting(runtime.Settings(**base, K_REVISION="sf-engine-00007", ENGINE_RELEASE="abc123"))
    runtime.start_error_reporting(runtime.Settings(**base, K_REVISION="sf-engine-00007"))
    runtime.start_error_reporting(runtime.Settings(**base))
    assert [c["release"] for c in calls] == ["abc123", "sf-engine-00007", None]
