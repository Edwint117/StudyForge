# Internal engine signing contract v1

Implements doc 04 §4's HMAC body/timestamp and replay protection requirement. Owned by Codex (transport wiring); it does not alter Claude's algorithm modules. This is a wire-format clarification, not a replacement architecture.

The web signer is `packages/engine-client/src/sign.ts`; the Python verifier is `engine/transport/signatures.py`. Routes accept POST only. Scope is `wake` for `/wake`, and `rpc` for `/rpc/sympy-equivalent` or `/rpc/run-code`. Use the corresponding `ENGINE_WAKE_SECRET` or `ENGINE_RPC_SECRET`; the verifier requires distinct keys of at least 32 characters.

Compute HMAC-SHA256 using the UTF-8 secret over this prefix followed by the exact raw request-body bytes (no trailing newline added):

```text
studyforge-engine-v1\n{scope}\nPOST\n{path}\n{unix_seconds}\n{lowercase_uuid_nonce}\n
```

Headers: `x-engine-timestamp` is canonical unsigned decimal seconds; `x-engine-nonce` is a lowercase UUID; `x-engine-signature` is `v1=` followed by lowercase hex. The timestamp tolerance is inclusive ±60 seconds, and the body limit is 1 MiB. Scope, method, path, nonce and body are authenticated; requests cannot be moved between endpoints. TLS remains required in the cloud.

After verification, atomically claim `(scope, nonce)` in a shared persistent store until `timestamp + 61`. A process-local cache is insufficient across Cloud Run instances. Invalid signatures never consume nonces. Store failure propagates and must produce 503; replay/invalid authentication produces a generic 401. No header, body or secret is reflected in errors. Retries sign a new nonce; business idempotency remains a separate job/RPC concern.

Pending M0 integration: persistent nonce table and atomic SQL claim, async psycopg adapter, rate limiting, bounded raw-body HTTP adapter (reject duplicate signature headers and query strings), FastAPI handlers and queue drain. This module alone does not expose or secure a deployed endpoint. The pg_net trigger must sign the exact bytes it transmits using this contract. HTTP handlers must not execute before both authentication and the nonce claim succeed.
