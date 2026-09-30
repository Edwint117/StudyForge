# ADR-0022: The engine's public health path is /health, not /healthz

- Status: accepted (deviates from the `/healthz` wording in doc 04 and the M0 gate; recorded per hard rule 12)
- Date: 2026-09-28

## Decision

The engine serves `GET /health` and keeps `GET /healthz` as an alias. Everything that calls the engine over its public `run.app` URL (deploy smoke test, canary checks, rollback checks, ZAP, uptime monitors) uses `/health`. Cloud Run's startup and liveness probes also use `/health`.

## Why

Google's front end reserves `/healthz` on Cloud Run `*.run.app` URLs: requests receive a Google-branded 404 and never reach the container. The first production deploy proved it: the engine answered a signed-request probe with 401 while `/healthz` returned 404, so the smoke test failed on a healthy service. Container-local checks (Compose, native dev) are unaffected, which is why local testing never showed it.

## Consequences

Docs and the M0 gate that say "`/healthz` is green" mean `/health` for the engine. The web tier's own `/api/healthz` route is a different service on the operator host and is unchanged. New monitors must not use `/healthz` against a `run.app` URL.

## Revisit

If the engine gets a custom domain in front of Cloud Run the reservation may not apply, but `/health` works either way, so there is no reason to change back.
