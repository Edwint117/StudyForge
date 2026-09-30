# ADR-0014: Operator-hosted web tier

- Status: accepted specification decision; implementation evidence tracked in PROGRESS.md
- Date: 2026-09-28
- Source: docs/spec/02 section 7 and the owning domain spec

## Decision

Run the Next.js production build on the operator host against the single cloud environment. Keep the application stateless and deployable unchanged to Vercel or Cloud Run. pnpm start:prod reads the ignored production environment file.

## Alternatives and consequences

No public hosting/domain/CDN is provisioned now. Calendar push stays off without public HTTPS; polling fallback is the acceptance path while disabled. This affects hosting, not database placement or secret handling.

## Revisit and validation

Revisit when public access or calendar push is required. M5 documents the conditional push/poll gate; do not claim public-web availability from localhost checks.
