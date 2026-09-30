# StudyForge data inventory

Updated 2026-09-28 (retention and health monitoring added). This is the implemented M0 inventory; later domain tables must be added when their migrations land.

| Store | Tier | Ownership/access | Retention and deletion |
|---|---|---|---|
| public.jobs | T1 operational metadata; payload/result may become T3 | user_id; four RLS policies, user SELECT only, narrow engine functions | Implemented (migration 0700, daily 03:17 UTC cron): succeeded/cancelled rows deleted after 30 days, dead (dead-letter) rows after 90 days. Still pending: redacting payload/result after 7 days, and deletion on account removal beyond the `on delete cascade` FK (M10) |
| private.engine_nonces | T1 random security nonces | no user content; engine function-only access | Expire after signature window; purge every 5 minutes |
| private.rate_limit_buckets | T1 HMAC-hashed security subjects | unlogged, function-only access | Purge idle buckets every 5 minutes; crash reset is intentional |
| pgmq queue/archive tables | T1 job IDs | no direct app/engine table grants | Delete success; archive exhausted attempts; archive rows purged after 30 days by the same daily cron |
| Supabase Auth managed tables | T2/T4 | provider-managed credentials and sessions | M1/M10 account lifecycle and deletion work pending |
| private.job_health() output | T1 aggregate counts (dead, stuck, backlog, oldest age) | engine role, read-only; no payloads or tenant IDs | Not stored; computed on demand every 5 minutes |
| Sentry (engine) | T1 exception type, stack shape, release, environment | scrubbed before send (no messages, request data, variables or breadcrumbs); off without a DSN | Provider retention; DSN in Secret Manager |
| Artifact Registry images | T1 code and public CA only | build identity only; images are immutable digests | Keep recent images; no user data inside |
| Vault | T4 engine wake configuration | migration/operator only | Set by `pnpm deploy:prod` (engine URL, wake secret). Rotate keys; never expose decrypted values through user routes |
| Secret Manager | T4 runtime credentials | separate engine/batch service identities | Numeric versions pinned per revision, reviewed rotation; `pnpm env:push-secrets` skips unchanged values; no values in Terraform state |
| Local ignored env files | T4 operator credentials | owner-only ACLs | Operator-managed; never committed, logged or uploaded wholesale |

No storage upload, learning, billing, export or analytics event data is implemented in this slice. Add table-level export/deletion classification when wiring those domains. The audit/legal retention exceptions require their own approved policies; this document does not assert legal compliance.
