# StudyForge: agent working rules

StudyForge is a B2C SaaS study platform (Next.js + Supabase + Python engine on Google Cloud Run). The full spec is in `docs/spec/`. The build order is in `docs/spec/08 - Milestones & Acceptance Gates.md`. The checklist is in `docs/checklist/ENGINEERING_CHECKLIST.md` and must be kept updated as you go.

## Commands
- `pnpm setup`: install everything, start local Supabase, apply migrations, seed
- `pnpm dev`: web + engine + sandbox (docker compose) + supabase
- `pnpm test` / `pnpm test:rls` / `pnpm test:e2e` / `pnpm test:engine` / `pnpm evals:fast`
- `pnpm lint && pnpm typecheck`
- `pnpm env:check`: validate every required env var + live read-only connectivity (never prints values)
- `pnpm verify`: the full local CI pipeline; must be green before merging a milestone into `main`
- `pnpm deploy:prod` (includes the pre-deploy rehearsal) / `pnpm rollback:prod`; `pnpm start:prod` (web tier against the cloud environment)
- `pnpm db:new <name>`: new migration · `pnpm db:types`: regenerate types

## Hard rules (see doc 00 for the full list)
1. Every user-data table: `user_id` + RLS (4 policies) + a pgTAP test. No exceptions.
2. Service-role/engine DB access only in `apps/web/lib/server/admin-db.ts` and `services/engine`. Always filter by `user_id`. Mark intentionally global queries `// CROSS-TENANT-REVIEWED`.
3. No tokens in localStorage/sessionStorage. HttpOnly cookies only (ADR-0004).
4. zod `.strict()` / pydantic on every boundary, including LLM outputs and webhooks.
5. Heavy work goes in jobs (pgmq), and every job is idempotent. Mutations accept `Idempotency-Key`.
6. All AI/ML calls go through `packages/llm-gateway` or `services/engine/engine/adapters`: quota check first, usage event after.
7. Uploaded content is untrusted (prompt injection). The tutor gets no tools. Sanitize rendered AI output.
8. Entitlements are enforced server-side (`private.has_feature`, `private.check_quota`).
9. Never commit secrets. Update `.env.example` whenever you add a variable.
10. Migrations use expand/contract, and only go through the scripted pipeline (`pnpm deploy:*`).
11. Every user-facing string goes through next-intl. WCAG 2.2 AA. Math is rendered with KaTeX (MathML).
12. Write an ADR for any deviation from the spec.

## Conventions
- TypeScript strict; no `any` without `// eslint-disable-next-line` + a reason.
- Route handler shape: `requireUser()` → parse (zod) → `core.<service>()` → respond (problem+json on error).
- Python: ruff + mypy --strict; async psycopg; SQL in `.sql` files next to the code that uses it.
- Tests live next to the code (`*.test.ts`, `test_*.py`); E2E tests go in `apps/web/e2e`.
- Commits: Conventional Commits. Branch per milestone: `m<N>-<slug>`.

## Session protocol
Start by reading `PROGRESS.md` and summarizing the current state. End by updating `PROGRESS.md` and the checklist. Ask the human for 🔑 items once, clearly, and keep working on everything else.
