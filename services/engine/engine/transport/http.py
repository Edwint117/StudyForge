"""Fail-closed bounded HTTP authentication, before JSON parsing or endpoint work."""

import asyncio
import time
import uuid
from typing import Protocol

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from engine.observability import request_completed
from engine.transport.signatures import MAX_BODY_BYTES, AuthenticationRejected, RequestVerifier


class RateLimiter(Protocol):
    async def allow(self, route: str, subject: str) -> bool: ...


def problem(status: int, code: str) -> JSONResponse:
    return JSONResponse(
        {"type": f"urn:studyforge:{code}", "title": code, "status": status},
        status_code=status,
        media_type="application/problem+json",
    )


class SecurityBoundary:
    def __init__(self, app: ASGIApp, verifier: RequestVerifier, limiter: RateLimiter) -> None:
        self.app = app
        self.verifier = verifier
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        route = (
            scope["path"]
            if scope["path"]
            in (
                "/health",
                "/healthz",
                "/wake",
                "/rpc/sympy-equivalent",
                "/rpc/run-code",
            )
            else "unknown"
        )

        async def response_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                request_completed(request_id, route, message["status"], int((time.monotonic() - started) * 1000))
                message.setdefault("headers", []).extend(
                    [
                        (b"x-request-id", request_id.encode()),
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
            await send(message)

        async def reject(status: int, code: str) -> None:
            await problem(status, code)(scope, receive, response_send)

        path = scope["path"]
        client = scope.get("client")
        subject = client[0] if client else "unknown"
        # All invalid paths use a single bucket, preventing arbitrary bucket creation by URL.
        bucket = (
            path if path in ("/health", "/healthz", "/wake", "/rpc/sympy-equivalent", "/rpc/run-code") else "invalid"
        )
        try:
            allowed = await self.limiter.allow(bucket, subject)
        except Exception:
            await reject(503, "security_unavailable")
            return
        if not allowed:
            await reject(429, "rate_limited")
            return
        if path in ("/health", "/healthz") and scope["method"] == "GET" and not scope.get("query_string"):
            await self.app(scope, receive, response_send)
            return
        if scope.get("query_string") or scope.get("raw_path", path.encode()) != path.encode():
            await reject(401, "invalid_authentication")
            return
        envelope: dict[str, str] = {}
        for header, field in (
            (b"x-engine-timestamp", "timestamp"),
            (b"x-engine-nonce", "nonce"),
            (b"x-engine-signature", "signature"),
        ):
            values = [value for key, value in scope["headers"] if key.lower() == header]
            if len(values) != 1:
                await reject(401, "invalid_authentication")
                return
            try:
                envelope[field] = values[0].decode("ascii")
            except UnicodeDecodeError:
                await reject(401, "invalid_authentication")
                return
        content_types = [v for k, v in scope["headers"] if k.lower() == b"content-type"]
        if content_types != [b"application/json"]:
            await reject(415, "unsupported_media_type")
            return
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > MAX_BODY_BYTES:
                        await reject(413, "body_too_large")
                        return
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await reject(408, "body_timeout")
            return
        try:
            await self.verifier.verify(
                method=scope["method"], path=path, body=bytes(body), headers=envelope, now=int(time.time())
            )
        except AuthenticationRejected:
            await reject(401, "invalid_authentication")
            return
        except Exception:
            await reject(503, "security_unavailable")
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, response_send)
