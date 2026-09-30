# Environment setup

The owner maintains **only `.env.keys`**. Never paste credentials into chat or commit them. The agent merges that file into `.env.local` and `.env.production`; existing generated secrets are preserved. Both files already exist on this workstation, so do not copy a template over them.

For a fresh checkout only, copy `.env.example` to `.env.local` and `.env.production` if absent, then follow the commands below. `.env.example` is generated from `packages/config/src/catalog.ts`: every entry records its owner/source, first milestone, environments, sensitivity and required/optional status. Runtime startup uses the same strict schema. Bootstrap mode permits unfinished agent provisioning but is **not** a deployment acceptance gate.

## 1. Accounts and keys (handoff A)

1. **Supabase:** create one US-region StudyForge project with account MFA enabled. Project Settings → API supplies the URL; API Keys supplies the publishable/anon and secret/service-role keys. General supplies the project reference. Save the database password at creation. Account → Access Tokens supplies a management token. Put these in the correspondingly named fields of `.env.keys`. Local Supabase credentials come from Docker and are never replaced with cloud credentials.
2. **Google Cloud:** create one project linked to a billing account. Create the owner's $5 monthly budget alert at 50/90/100% before provisioning. Copy the project ID to `GCP_PROJECT_ID` in `.env.keys`. The agent runs `gcloud auth login` only when needed; approve the browser prompt. Terraform later creates `sf-deployer`, its impersonation grants, Artifact Registry, state bucket, Cloud Run and Secret Manager. No service-account key file is needed.
3. **Anthropic:** Console → Settings → API Keys: create the project key and copy it to `ANTHROPIC_API_KEY`. Limits: set the monthly spend cap. The validator only lists models; it sends no inference requests. Model availability and budget configuration are separate acceptance checks during gateway implementation.

## 2. Identity and error reporting (handoff B)

1. **Google OAuth:** in the same Google project, configure an External consent screen in Testing mode, add yourself as a test user, and create one Web application OAuth client. Copy its ID and secret to `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`. Follow [KEYS_CHECKLIST.md §3](KEYS_CHECKLIST.md) for redirects. M1 configures Supabase Auth through the management API; M5 adds Calendar permissions to this same client. Format validation is not a substitute for the browser consent E2E.
2. **Sentry:** create one StudyForge project; Settings → Projects → Client Keys provides the DSN. Put it in `SENTRY_DSN`. The merge populates `NEXT_PUBLIC_SENTRY_DSN`, shared by web and engine configuration. Optional sourcemap upload uses `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` in the environment files; omit the token until the associated identifiers are configured. The validator parses the DSN without sending an event.
3. Keep the free hosting plan decisions and later admin-account promotion actions in doc10. Account MFA, billing terms and legal attestations cannot be inferred from API connectivity.

## 3. Remaining services (handoff C)

1. **PostHog US Cloud:** Project Settings supplies the project API key and numeric project ID. Personal Settings → Personal API Keys supplies an operator key restricted to this project. Grant `project:read` for the read-only project/key-pair check; account-deletion permissions are added and tested in M10. Put `POSTHOG_PROJECT_API_KEY`, `POSTHOG_PROJECT_ID`, and `POSTHOG_PERSONAL_API_KEY` in `.env.keys`. Turn session replay off. The check retrieves project metadata, never captures an event. A 403 means key scope or project access needs correction.
2. **Better Stack:** Uptime → Integrations/API tokens: create a token and put it in `BETTERSTACK_API_TOKEN`. The check lists monitor metadata. Monitoring and status-page provisioning remain M0/M2/M11 work.
3. **Langfuse:** create a US Cloud project. Project Settings → API Keys: copy the public/secret pair into `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. Production content logging stays off. The check reads project metadata only.
4. **Optional paid adapters:** Deepgram Console → API Keys; AssemblyAI Dashboard → API Keys; Mistral Console → API Keys; Voyage Dashboard → API Keys; OpenAI Platform → project API Keys. Corresponding fields can stay blank. The six paid integrations are implemented with recorded HTTP fixtures in M4; a configured optional key is not reported as live-verified by this bootstrap checker.
5. **Calendar and human checks:** enable Google Calendar API in the existing Google project before M5. Add test users/consent scopes and perform the browser flow then. Real-device, passkey, business and legal reviews stay in doc10; keys do not satisfy them.

For exact owner-key names and account walkthroughs, see [KEYS_CHECKLIST.md](KEYS_CHECKLIST.md). Its one-file workflow takes precedence over stale multi-project examples in doc10.

## 4. Agent commands and file protection

```powershell
pnpm install --frozen-lockfile
pnpm hooks:install
pnpm env:prepare
pnpm env:merge-keys
pnpm supabase:start
pnpm env:sync-local
pnpm env:check --env local --bootstrap
pnpm env:check --env production --bootstrap
```

`env:prepare` adds missing defaults and generates only missing random secrets and VAPID pairs. Independent 48-byte HMAC secrets are generated for each environment. An incomplete VAPID pair fails rather than silently rotating it. `env:merge-keys` is idempotent: required blank owner keys clear stale values; optional blank keys preserve configured optional values. It never changes local Docker credentials.

The helpers reject duplicate/unknown keys and multiline values, never evaluate shell syntax, and never print values or vendor error bodies. Private writes use a temporary file secured **before** writing, then atomic replacement. Windows grants only the current owner and disables inherited permissions; POSIX uses mode 0600. Synthetic tests verify permissions and unchanged-file idempotence. `.env.keys` is also permission-restricted at merge time. Do not use `Get-Content` or `cat` on real secret files in agent tooling.

The pre-commit hook runs `pnpm secrets:staged`. `pnpm secrets:history` scans all refs; `pnpm test:secret-hook` tests rejection using a synthetic token and a separate temporary index, without changing the user's staged files. Scanner streams are suppressed and failures block the hook. Full verification-pipeline integration remains M0 work.

Windows: preserve `UV_PYTHON_INSTALL_DIR`. If the current desktop process has stale environment settings, the bootstrap uses the persisted user setting or `%USERPROFILE%\.uv\python`. This avoids the MSIX AppData junction problem. Project-local uv/gcloud binaries are fallbacks when installed tools are absent from PATH. pnpm's version is pinned; automatic manager switching is disabled because the desktop fallback otherwise resolves a missing temporary executable.

## 5. Validation and cloud secrets

`pnpm env:check --env production` is the strict check once M0 provisions all agent-owned values. `--offline` checks formats only. Both options print names and fixed error categories only. `PENDING` is allowed only in explicit bootstrap mode. Supabase's public CA is bundled in `certificates/`; DB probes verify its chain **and hostname** and execute only `SELECT 1` in a read-only transaction. Never disable TLS verification to resolve a failure.

After Terraform creates the `sf-*` secrets and deployer IAM, run:

```powershell
pnpm env:push-secrets production
```

Or use `scripts/env/push-secrets.sh` from a POSIX shell. This helper validates the complete production configuration and uploads the engine allowlist through stdin, impersonating the deployer. Supabase management tokens, the operator DB password and analytics personal keys are excluded. It does not create infrastructure. Cloud Run mounts Secret Manager versions; the web tier will read the private `.env.production` on the operator host. A successful upload alone does not prove that a deployed revision mounts the correct versions.

## 6. Verified status (2026-09-27)

Production bootstrap read-only checks pass for Supabase auth/public/server/management access and password+verified TLS, Anthropic models, PostHog project/key pairing, Langfuse, Better Stack, and the signed-in Google Cloud operator/project. Sentry and OAuth formats passed. The owner corrected PostHog access and the private key merge was rerun. Cloud URLs, engine DB role, deployer impersonation and state bucket are still agent-owned M0 provisioning, not missing owner credentials. See `PROGRESS.md` for the current local startup result and milestone gate status.
