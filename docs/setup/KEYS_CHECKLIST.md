# Keys checklist: fill these before handing off to Codex

**You only fill one file: `.env.keys`** in the repo root. It lists just the values you copy from each website, grouped by site, and each key is pasted **once**. Codex copies them into the real env files (`.env.local` and `.env.production`) itself, without printing them. All of these files are git-ignored. **Don't paste keys into any chat.**

This page explains the clicks on each website. The tables below show the underlying env variable each key ends up in, for reference only; you don't need to touch `.env.local` or `.env.production`.

Legend: **YOU** = get it and paste it · **✅ DONE** = already generated for you · **🤖 AGENT** = leave blank; Codex fills it in · **➖** = leave blank · **DEFAULT** = leave as is

---

## 0. Nothing to install
Codex installs every tool it needs. Your only jobs are:
- **creating the 8 accounts below and pasting their keys**;
- **clicking "Allow"** when Codex opens a Google sign-in in your browser (for the Google Cloud CLI);
- keeping **Docker Desktop running** while Codex works.

## 1. Supabase: 1 project
supabase.com → sign up (turn on 2FA) → **New project** `studyforge`, in a US East region. **Save the database password when you create it.**

| Variable | `.env.local` | `.env.production` | Where |
|---|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | 🤖 AGENT (local Supabase) | **YOU** | Project Settings → API → Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 🤖 AGENT | **YOU** | Project Settings → API Keys → publishable / `anon` key |
| `SUPABASE_SERVICE_ROLE_KEY` | 🤖 AGENT | **YOU** | Project Settings → API Keys → secret / `service_role` key |
| `SUPABASE_PROJECT_REF` | ➖ | **YOU** | Project Settings → General → Reference ID |
| `SUPABASE_DB_PASSWORD` | ➖ | **YOU** | the password you set at creation |
| `SUPABASE_ACCESS_TOKEN` | ➖ | **YOU** | Account (top-right avatar) → Access Tokens → Generate |
| `ENGINE_DATABASE_URL` | 🤖 AGENT | 🤖 AGENT | Codex creates it |

## 2. Google Cloud: 1 project
console.cloud.google.com (turn on 2FA on your Google account):
- [ ] Create a **billing account** (the free trial credit applies).
- [ ] Create **one** project **`studyforge`** and link it to billing.
- [ ] **Billing → Budgets & alerts → Create budget**: $5/month, email alerts at 50/90/100%. Do this **first**.

| Variable | `.env.local` | `.env.production` | Where |
|---|---|---|---|
| `GCP_PROJECT_ID` | ➖ | **YOU** | project picker → ID column (may differ from the name) |
| `GCP_REGION`, `GCP_ARTIFACT_REPO` | DEFAULT | DEFAULT | |
| `GCP_DEPLOY_SERVICE_ACCOUNT`, `TF_STATE_BUCKET` | ➖ | 🤖 AGENT | Codex creates them |
| `ENGINE_URL`, `SANDBOX_URL` | DEFAULT (localhost) | 🤖 AGENT | the Cloud Run URLs after the first deploy |

## 3. Google OAuth: 1 client (for both sign-in and Calendar)
In the same **`studyforge`** Google Cloud project:
- [ ] **APIs & Services → OAuth consent screen**: User type **External**, app name StudyForge, your email. Leave it in **Testing** mode. **Test users** → add your own Google address (and anyone else who'll try it).
- [ ] **APIs & Services → Library** → enable **Google Calendar API**.
- [ ] **Credentials → Create credentials → OAuth client ID → Web application**, name "StudyForge". Add these **Authorized redirect URIs**:
  - `http://127.0.0.1:54321/auth/v1/callback`
  - `https://<your-project-ref>.supabase.co/auth/v1/callback` (use the Reference ID from step 1)
  - `http://localhost:3000/api/v1/calendar/oauth/google/callback`
  - `http://localhost:3001/api/v1/calendar/oauth/google/callback`

| Variable | Both files | Where |
|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | **YOU** | the client's detail page |

(Codex configures this client into Supabase's Google sign-in and sets the redirect URLs itself.)

## 4. Anthropic: 1 key
console.anthropic.com → **API Keys → Create key** → **Limits → set a monthly spend limit** (e.g. $50).

| Variable | Both files |
|---|---|
| `ANTHROPIC_API_KEY` | **YOU** (the same key) |

## 5. Sentry: 1 project
sentry.io → create an org → **one** project `studyforge` (platform: Next.js; the engine reports into it too).

| Variable | Both files |
|---|---|
| `NEXT_PUBLIC_SENTRY_DSN` | **YOU** (Project Settings → Client Keys → DSN) |
| `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` | ➖ optional (only for readable stack traces) |

## 6. PostHog: 1 project
posthog.com → US cloud → project `studyforge` → **turn Session Replay off** → Settings → Personal API keys → create one (needed so account deletion can also erase analytics data).

| Variable | Both files |
|---|---|
| `NEXT_PUBLIC_POSTHOG_KEY` | **YOU** (Project API key) |
| `POSTHOG_PERSONAL_API_KEY` | **YOU** |
| `POSTHOG_PROJECT_ID` | **YOU** (Project Settings → Project ID) |

## 7. Langfuse: 1 project
cloud.langfuse.com → **US** region → project `studyforge` → Settings → API Keys → create (it gives a pair).

| Variable | Both files |
|---|---|
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | **YOU** |

## 8. Better Stack: 1 token
betterstack.com → sign up (free) → Uptime → Settings → API tokens.

| Variable | `.env.production` only |
|---|---|
| `BETTERSTACK_API_TOKEN` | **YOU** |

---

## Already done for you ✅
Each file has its **own** randomly generated values for:
- `ENGINE_RPC_SECRET`, `ENGINE_WAKE_SECRET`, `CSRF_SECRET`, `MOCK_BILLING_WEBHOOK_SECRET`, `OAUTH_STATE_SECRET`;
- `NEXT_PUBLIC_VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` (web push).

`APP_URL`, `APP_ENV`, `ALLOWED_ORIGINS` and `ENGINE_POLL_MODE` are also preset.

## Leave blank ➖
- Paid adapters: `DEEPGRAM_API_KEY`, `ASSEMBLYAI_API_KEY`, `MISTRAL_API_KEY`, `VOYAGE_API_KEY`, `OPENAI_API_KEY`. These only affect Pro/Pro+ users, and the free tools are used when they're empty.
- Stripe: all three variables (not until real billing).

## When you're done
Make sure `.env.keys` is saved, then open the repo in Codex and paste the kickoff prompt. After you approve its plan, it verifies every key (without printing them), fills in the 🤖 AGENT values itself, and only comes back to you if something you provided is missing or wrong.
