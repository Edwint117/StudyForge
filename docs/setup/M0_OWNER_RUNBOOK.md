# M0 owner runbook: commands only the owner runs

Claude Code is blocked from Terraform apply, production database access and production deploys, so these steps are yours. Run each from `C:\Users\baldy\Projects\studyforge` in a PowerShell prompt, in order. Nothing here prints secret values. Stop at the first failure and send the sanitized error code to the agent.

## 1. Create the Sentry DSN secret slot (Terraform, 3 additions, 0 destroys)

A saved plan (`foundation.tfplan`) already exists. If you changed anything since, rerun `pnpm infra:plan` first.

```powershell
$env:GOOGLE_OAUTH_ACCESS_TOKEN = (.tools\google-cloud-sdk\platform\bundledpython\python.exe .tools\google-cloud-sdk\lib\gcloud.py auth print-access-token).Trim(); $env:TF_IN_AUTOMATION = '1'; .tools\terraform\terraform.exe -chdir=infra/terraform/envs/prod apply -input=false foundation.tfplan; Remove-Item Env:GOOGLE_OAUTH_ACCESS_TOKEN
```

## 2. Create the production engine role and generate connection values

Creates `engine_worker` in the production database, proves login through the session pooler with certificate and hostname verification, then writes `ENGINE_DATABASE_URL`, `ENGINE_RPC_SECRET` and `ENGINE_WAKE_SECRET` to `.env.production`. Idempotent; existing values are kept.

```powershell
pnpm env:provision-prod-engine
```

## 3. Upload engine secrets to Secret Manager

Skips values that are already the latest version. Reports any slot Terraform has not created yet.

```powershell
pnpm env:push-secrets production
```

## 4. Supabase cloud settings

First a read-only diff, then apply what differs (auth site URL and redirects, password minimum 8, Data API schema exposure, database SSL enforcement).

```powershell
pnpm supabase:settings
```

```powershell
pnpm supabase:settings --apply
```

## 5. Merge the verified milestone branch into main

Refuses unless `docs/verify/latest.json` on the branch tip is a clean, complete, passing report that covers the tip.

```powershell
pnpm merge:main m0-foundation
```

## 6. Deploy

The dry run does everything that cannot touch production (guard, rehearsal on a disposable database, image build, Trivy). The real run asks you to type the short commit SHA. The first run pulls the ZAP image (about 1.5 GB).

```powershell
pnpm deploy:prod --dry-run
```

```powershell
pnpm deploy:prod
```

## 7. After the deploy

```powershell
pnpm rollback:prod --dry-run
```

Run `pnpm rollback:prod` only when at least two revisions exist (the second deploy), and confirm afterwards that `/health` is green. `pnpm start:prod` serves the web tier against the cloud environment.

## Also worth doing once

- In Sentry, add an alert rule for new issues whose title contains `DeadJobsAlert`, `StuckJobsAlert` or `BacklogAlert` (the engine reports these when the 5-minute health wake finds a problem).
- After the first deploy, `.env.production` gets `ENGINE_URL` automatically; the sandbox URL stays empty (ADR-0020, deferred).
