# ADR-0004: HttpOnly session cookies

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Persist browser sessions only in server-set HttpOnly, Secure, SameSite=Lax cookies. No tokens in localStorage or sessionStorage. Realtime may hold an access token of at most five minutes in memory, obtained from the authenticated realtime-token endpoint.

## Alternatives and consequences

Cookie authentication requires Origin/CSRF checks on mutations. Memory-only Realtime tokens disappear on reload; refresh through the server. This exception does not permit persisted refresh tokens or general browser service-role access.

## Revisit and validation

Revisit only for a separately designed native client. M1 must verify cookie attributes, CSRF, session revocation and storage behavior.
