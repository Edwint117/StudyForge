"""Sentry error tracking for the engine (M0-17): off without a DSN, and scrubbed before anything is sent.

Policy (doc 06 §8, ``observability.py``): events carry the exception *type*, the stack (file/function/line) and the
release; never exception messages, request data, headers, cookies, local variables, user data or breadcrumb text,
because any of those can contain student answers, document text, tokens or database URLs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sentry_sdk

# Top-level event keys removed outright.
_DROP_KEYS = ("request", "user", "extra", "contexts", "breadcrumbs", "modules", "server_name", "logentry", "message")
_KEEP_TAGS = frozenset({"environment", "release", "route", "queue", "job_kind", "prompt_version"})
REDACTED = "[scrubbed]"


def scrub_event(event: dict[str, Any], hint: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """``before_send``: keep the exception type and stack shape only."""
    out: dict[str, Any] = {k: v for k, v in event.items() if k not in _DROP_KEYS}
    tags = out.get("tags")
    if isinstance(tags, dict):
        out["tags"] = {k: v for k, v in tags.items() if k in _KEEP_TAGS}
    exception = out.get("exception")
    if isinstance(exception, dict):
        values = []
        for item in exception.get("values") or []:
            cleaned = {k: v for k, v in item.items() if k not in ("value", "mechanism")}
            cleaned["value"] = REDACTED
            stack = cleaned.get("stacktrace")
            if isinstance(stack, dict):
                frames = []
                for frame in stack.get("frames") or []:
                    keep = ("filename", "function", "module", "lineno", "in_app", "abs_path")
                    frames.append({k: v for k, v in frame.items() if k in keep})  # no vars, no source context
                cleaned["stacktrace"] = {"frames": frames}
            values.append(cleaned)
        out["exception"] = {"values": values}
    return out


def scrub_breadcrumb(crumb: dict[str, Any], hint: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    return None  # breadcrumbs (log lines, SQL, HTTP) are never sent


def init_sentry(dsn: str, *, environment: str, release: str | None = None) -> bool:
    """Start Sentry when a DSN is configured. Returns whether it is active."""
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        send_default_pii=False,
        max_request_body_size="never",
        include_local_variables=False,
        include_source_context=False,
        attach_stacktrace=False,
        traces_sample_rate=0.0,
        before_send=scrub_event,  # type: ignore[arg-type]
        before_breadcrumb=scrub_breadcrumb,
    )
    return True


def capture(error: BaseException, **tags: str) -> None:
    """Report an unexpected error (no-op when Sentry isn't initialised); only allowlisted tags survive."""
    with sentry_sdk.new_scope() as scope:
        for key, value in tags.items():
            scope.set_tag(key, value)
        sentry_sdk.capture_exception(error)
