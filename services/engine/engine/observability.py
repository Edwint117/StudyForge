"""Allowlisted operational events: never arbitrary exception strings or user payloads."""

import json
from datetime import UTC, datetime


def request_completed(request_id: str, route: str, status: int, duration_ms: int) -> None:
    print(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": "http_completed",
                "service": "engine",
                "request_id": request_id,
                "route": route,
                "status": status,
                "duration_ms": duration_ms,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
