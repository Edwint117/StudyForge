"""Signed wire contract. A shared atomic nonce store is mandatory; no local fallback."""

import hashlib
import hmac
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Scope = Literal["wake", "rpc"]
MAX_BODY_BYTES = 1_048_576
MAX_SKEW_SECONDS = 60


class AuthenticationRejected(Exception):
    """Map to a generic 401 without reflecting headers or body."""


class NonceStore(Protocol):
    async def claim(self, scope: Scope, nonce: str, expires_at: int) -> bool:
        """Atomically insert a unique (scope, nonce); false means already claimed.

        Must be shared across all instances and retain the claim until expires_at.
        A backend failure must raise, never return success or use a local fallback.
        """
        ...


class SignatureHeaders(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    timestamp: str = Field(pattern=r"^(0|[1-9][0-9]{0,15})$")
    nonce: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    signature: str = Field(pattern=r"^v1=[0-9a-f]{64}$")


class RequestVerifier:
    def __init__(self, *, rpc_secret: str, wake_secret: str, nonces: NonceStore) -> None:
        if min(len(rpc_secret), len(wake_secret)) < 32 or rpc_secret == wake_secret:
            raise ValueError("Distinct engine secrets of at least 32 characters are required")
        self._keys = {"rpc": rpc_secret.encode(), "wake": wake_secret.encode()}
        self._nonces = nonces

    async def verify(self, *, method: str, path: str, body: bytes, headers: dict[str, str], now: int) -> None:
        if method != "POST" or path not in ("/wake", "/rpc/sympy-equivalent", "/rpc/run-code"):
            raise AuthenticationRejected("Invalid engine authentication")
        if len(body) > MAX_BODY_BYTES:
            raise AuthenticationRejected("Invalid engine authentication")
        try:
            parsed = SignatureHeaders.model_validate(headers)
        except ValidationError:
            raise AuthenticationRejected("Invalid engine authentication") from None
        timestamp = int(parsed.timestamp)
        if timestamp > 9_007_199_254_740_991 or abs(now - timestamp) > MAX_SKEW_SECONDS:
            raise AuthenticationRejected("Invalid engine authentication")
        scope: Scope = "wake" if path == "/wake" else "rpc"
        prefix = f"studyforge-engine-v1\n{scope}\nPOST\n{path}\n{timestamp}\n{parsed.nonce}\n".encode()
        expected = "v1=" + hmac.new(self._keys[scope], prefix + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, parsed.signature):
            raise AuthenticationRejected("Invalid engine authentication")
        # A future-dated request remains valid until timestamp + skew, not now + skew.
        # One extra second preserves the inclusive acceptance boundary.
        if not await self._nonces.claim(scope, parsed.nonce, timestamp + MAX_SKEW_SECONDS + 1):
            raise AuthenticationRejected("Invalid engine authentication")
