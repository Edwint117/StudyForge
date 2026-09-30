# StudyForge

Next.js + Supabase + Python engine. Build order and acceptance gates live in `docs/spec/08 - Milestones & Acceptance Gates.md`; current state and ownership are in `PROGRESS.md` and `docs/handoff/ENGINE_CORE_HANDOFF.md`.

## Local development (Windows)

Keep Docker Desktop running. Follow `docs/setup/ENV_SETUP.md` to prepare the ignored owner-only environment files and `docs/setup/TOOLS.md` for pinned runtimes. Preserve `UV_PYTHON_INSTALL_DIR` on Windows.

```powershell
pnpm setup
pnpm dev
```

Setup installs locked dependencies, starts local Supabase, synchronizes local keys, applies migrations through `pnpm deploy:local`, provisions the restricted engine login and builds the engine image. Dev starts the Compose engine on 127.0.0.1:8080 and the Next.js development server. Stopping dev stops the engine container. Supabase remains running.

For native engine development use `pnpm dev:engine` (stop the Compose engine first to free port 8080). `pnpm start:prod` runs the web tier against the private production environment. It does not deploy infrastructure.

The sandbox is intentionally not present in Compose while ADR-0020 is unresolved. The complete three-service/fresh-clone M0 gate is therefore **not passed**. The optional Supabase Vector collector also has an outstanding Docker connectivity issue.

## Checks and migration commands

`pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm test:engine`, `pnpm test:rls`, `pnpm test:e2e`. `pnpm deploy:local` is the only implemented migration application entrypoint so far. Do not apply SQL manually or use a reset to work around migration errors.

The owner deferred most testing on 2026-09-28. Check `docs/handoff/M0_REVIEW.md` for outstanding review and acceptance work; successful build/startup checks are not a full verification result. Production rehearsal/deploy/rollback scripts and the complete verify pipeline remain unfinished.

## Infrastructure

`pnpm infra:bootstrap` prepares a keyless deployer and versioned state bucket. `pnpm infra:plan` saves the Terraform foundation plan with runtime creation disabled. No service-account JSON keys are used, and secret versions are uploaded separately from Terraform. Review the plan and remaining deployment gates before applying anything.
