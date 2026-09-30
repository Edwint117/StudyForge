# ADR-0021: Scripted migration runner and image-based release rehearsal

- Status: accepted (deviates from the literal wording of ADR-0019 and doc 02 section 6; recorded per hard rule 12)
- Date: 2026-09-28

## Decision

1. Production migrations are applied by `scripts/release/migrations.ts`, called only from `pnpm deploy:prod`. It writes the same `supabase_migrations.schema_migrations` table the Supabase CLI uses, so `supabase migration up --local` and the runner agree on history. Each migration runs in its own transaction together with its bookkeeping row, under an advisory lock, over a verify-full TLS session-pooler connection (port 5432; DDL and multi-statement scripts cannot use the transaction pooler).
2. Expand/contract is enforced mechanically: destructive statements (`drop table/column/schema/type`, `truncate`, `rename`, column type changes) without a `-- @contract` marker fail the rehearsal and the deploy; marked contract migrations need `--allow-contract` plus a typed confirmation.
3. The pre-deploy rehearsal builds its disposable database from the same Supabase Postgres image local development uses, replays the migrations production has already applied (read from production's `schema_migrations`, the only production query), applies the pending ones, and runs the pgTAP suite with `pg_prove` from a container that mounts only `supabase/tests`. It does not restore a `pg_dump` of production.

## Alternatives and consequences

- Supabase CLI `db push`: needs a project link and a password on argv or in a profile, hides TLS verification behind CLI defaults, and cannot be unit-tested for the expand/contract rule. Rejected.
- A schema-only `pg_dump` restore of production (ADR-0019's wording): a bare restored database lacks the stock Supabase schemas and cannot host `pg_cron` in a second database, so the restore needs manual repair before it proves anything. Replaying applied migrations on a stock image tests exactly what a deploy does. The cost: drift made directly in production (a hand-edited object) is not reproduced. Supabase settings drift is covered separately by `pnpm supabase:settings`; object drift has no detector yet and is listed as open work.
- No data restore is implied, consistent with ADR-0018.

## Revisit and validation

Revisit when a second environment exists, or if production is ever edited outside the pipeline. Validated so far: the rehearsal applied all seven migrations to a fresh Supabase image and 40 pgTAP assertions passed; unit tests cover the classifier and pending-set logic. The production application path has not run.
