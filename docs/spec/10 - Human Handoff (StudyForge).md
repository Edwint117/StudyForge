---
title: StudyForge — Human Handoff
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, handoff]
---

# 10: Human Handoff (your to-do list)

These are the things the agent **cannot and must not** do for you: creating accounts, paying, signing, filing, making legal and business judgment calls. It's the StudyForge-specific version of [[Agent-Build-Checklist/Human Handoff Checklist|Human Handoff Checklist]]. Work it **in parallel** with the build. Anything marked **⛔ blocks M#** stops the agent at that milestone.

> Security rule: you create the accounts and put the keys into your git-ignored `.env.local` / `.env.production` files yourself (the agent's helper script copies what Google Cloud needs into Secret Manager). Don't paste production secrets into the chat.

> **Key workflow (the Second Step in the kickoff prompt):** after you approve the plan, the agent gives you the complete `.env.example` + `docs/setup/ENV_SETUP.md`. Do **all** the account and key items in sections A–C **at that point, in one sitting**, even the ones for later milestones: fill `.env.local` and `.env.production` (they already exist), run the push-secrets script, and run `pnpm env:check`. After that, the only ⛔ items left during the build are **actions** (adding Google OAuth test users, real-device checks, legal review), not keys.

## A. Before the agent starts ⛔ blocks M0
- [ ] **Local repo**: create a folder `studyforge`, run `git init`, and open it in Codex. No GitHub or other hosted remote.
- [ ] **Supabase**: create an organization (2FA on) and **one** project `studyforge` in a US region (e.g. `us-east-1`). Note the project refs and database passwords, and create a **Supabase access token** (used by the deploy scripts).
- [ ] **Google Cloud**: sign in at console.cloud.google.com (2FA on) and create a billing account (new accounts get a free trial credit, plus Cloud Run's monthly free allowance). Create **one** project `studyforge`. **Immediately create a budget with email alerts** (e.g. $5 at 50/90/100%). The agent's Terraform takes over from there. You're automatically Owner of the project you create. The agent will open a Google sign-in in your browser for the `gcloud` CLI; just approve it (deploys use your login, impersonating a limited `sf-deployer` service account).
- [ ] **Anthropic Console**: create an org, **one** API key, and a **monthly spend limit** (e.g. $50).
- [ ] **No installs needed.** The agent installs every tool itself. You only click through the Google Cloud browser sign-in when it asks, and keep Docker Desktop running.

## B. Before M1 (auth) ⛔ blocks M1
- [ ] **One Google OAuth client** (used for both sign-in and Calendar, consent screen in **Testing** mode with yourself as a test user): exact steps are in `docs/setup/KEYS_CHECKLIST.md` §3. The agent configures Supabase Auth itself (Google provider, Site URL/redirect URLs, the Send Email hook) through the Supabase management API using your access token. If the hook isn't available on the free plan, it falls back to Supabase's built-in test email, which only reaches your own address and is rate-limited.
- [ ] **Hosting plans (owner's decision):** stay on the free plans (Supabase Free, Cloud Run free allowance). Know that Supabase free projects **pause after about a week with no activity**; resume them from the dashboard. There are **no backups** (ADR-0018), so a deleted or corrupted project can't be restored.
- [ ] **Sentry**: create an org and **one** project `studyforge`; provide its DSN.
- [ ] Create your own admin account once M1 ships; the agent gives you the promote-to-admin command.

## C. During the build
- [ ] **PostHog** (M2): create a project (US cloud), provide the API key/host and a personal API key (for account deletion), and **turn session replay off**.
- [ ] **Better Stack** (M2/M11): free account + an API token. It monitors the engine and Supabase and hosts a status page on its free subdomain.
- [ ] **Langfuse** (M4): cloud project (free tier); provide the keys.
- [ ] **Optional paid AI/ML adapters** (M4+, only if you want them): Deepgram / AssemblyAI / Mistral / Voyage / OpenAI keys. The app works without any of them (free adapters). Decide per task in Admin → Provider Settings.
- [ ] **Google Calendar API** (M5): enable the API in the same Google Cloud project, create the calendar OAuth clients (redirect `http://localhost:<port>/api/v1/calendar/oauth/google/callback`), and add scopes `calendar.events` + `calendar.readonly` (or `calendar.freebusy`) as the agent specifies. In **Testing** mode this works for up to 100 test users you add yourself, with no Google verification needed. (Calendar changes sync by polling every 5 minutes, because push notifications need a public web address.)
- [ ] Test on real devices: iPhone Safari PWA install and Android Chrome (on the same Wi-Fi, pointed at your machine).
- [ ] Passkey UX test with a few people (M1/M2).
- [ ] Read the OWASP Top 10 mapping the agent writes (`docs/security/owasp-top10.md`). This counts as the "team understands" item.
- [ ] Review each milestone summary in `PROGRESS.md` and the tagged commit. Pay special attention to the auth, billing, RLS and sandbox code.

## D. Business, legal & compliance (from the playbook's Human Handoff Checklist)
### Before building (recommended; not blocking the agent)
- [ ] **Discovery**: 10+ student interviews (target: STEM + pre-professional undergrads), a falsifiable problem hypothesis, a competitor teardown (Anki, Quizlet, Knowt, StudyFetch, RemNote, Notion AI), willingness-to-pay tests with real commitments (a pre-order waitlist with a deposit, or semester-pass presales once billing is real), positioning. See [[SaaS-Playbook/01-Discovery/_MOC|01-Discovery]].
- [ ] **Entity**: form an LLC (or equivalent) before taking real money or signing vendor contracts; get an EIN and a business bank account. See [[SaaS-Playbook/02-Business-Legal/Choosing a Business Entity|Choosing a Business Entity]].
- [ ] **IP**: make sure the code and brand are owned by the entity (an IP assignment from yourself to the LLC), and add founder agreements if there's a co-founder.
- [ ] **Name/trademark**: run a USPTO/TESS knockout search on the real name before branding spend. "StudyForge" is a placeholder and may be taken.

### Before launch
- [ ] **Legal text review** (attorney or a vetted template service) of every 📄 page the agent drafted: Terms (including academic-integrity and acceptable-use terms, AI-output disclaimers, the user-content license, an arbitration/venue decision), Privacy Policy (must match `docs/data-map.md`), Cookie Policy, Refund policy, AUP, DMCA policy, and the security/VDP safe-harbor wording.
- [ ] **DMCA designated agent**: register with the U.S. Copyright Office (small fee, renew every 3 years). Students upload copyrighted textbooks and slides, so you need the safe harbor. Name the agent on `/dmca`.
- [ ] **Children's privacy**: confirm the 18+ gate is your policy and that the marketing doesn't target minors (COPPA not applicable if enforced).
- [ ] **FERPA**: generally applies to schools, not to a B2C tool students choose themselves. Get a one-time legal confirmation, and revisit it if you sell to institutions.
- [ ] **GDPR/CCPA applicability**: global signups are allowed, so decide whether you need an EU/UK representative (Art. 27) or will geo-restrict EU signups at launch. Confirm the CCPA thresholds (likely not met at launch, but the rights are built anyway).
- [ ] **Accessibility law**: review the agent's WCAG 2.2 AA conformance report; publish an accessibility statement.
- [ ] **Taxes**: nothing to collect while billing is $0. **Before real billing**, talk to an accountant about sales-tax nexus for SaaS by state, and choose Stripe + Stripe Tax vs a merchant of record (Paddle / Lemon Squeezy).
- [ ] **Insurance**: consider tech E&O + cyber liability before real revenue.
- [ ] **Export control/sanctions**: the Terms prohibit use from embargoed regions; optionally geo-block them.
- [ ] **Pentest**: optional before a free beta, but recommended before real billing. The agent prepares a scope doc (`docs/security/pentest-scope.md`).
- [ ] **Landing page copy + SEO**: your voice and positioning (the agent builds the page with placeholder copy).
- [ ] **Launch plan**: beta cohort (classmates, subreddits, campus clubs), a feedback channel, and the launch checklist ([[SaaS-Playbook/99-Templates/Launch Checklist|Launch Checklist]]).

### At and after launch
- [ ] Decide whether to publish the SLA (the agent recommends waiting for 90 days of uptime data).
- [ ] Set up a support inbox routine (daily triage of tickets and content reports).
- [ ] Monthly: review AI costs vs budget (`docs/costs.md`), the dependency report, and a user access review.
- [ ] **Before turning on real billing:** Stripe account + Stripe Tax (🔑), bank account, tax registration as advised, pricing validation, a beta-user migration email (consent before first charge). Then the agent executes doc 07 §7.
- [ ] Later: SOC 2 / security questionnaires / SSO only if institutions become customers; bug bounty after a pentest; on-call once there's a second engineer.

## E. Env vars
The single source of truth is `repo-templates/.env.example`. It lists **every** variable for M0–M11 with where to get it, which milestone first uses it, whether it's required or optional, and whether it's secret or public. The agent finalizes it in the Second Step and writes `docs/setup/ENV_SETUP.md` with the click-by-click setup. Quick map of which accounts produce keys:

| Account | Keys it produces | Needed by |
|---|---|---|
| Supabase (×2 projects + CLI) | URL, publishable/secret keys, project ref, DB password, access token | M0 |
| Google Cloud | project IDs, region, Artifact Registry repo, deployer service account (created by Terraform), Terraform state bucket | M0 |
| Sentry | 2 DSNs, auth token, org | M0 |
| Google Cloud (login OAuth client) | client ID + secret | M1 |
| PostHog | project key/host, personal API key, project ID | M2 / M10 |
| Web push | VAPID key pair (you generate) | M2 |
| Better Stack | API token | M2 / M11 |
| Anthropic | API key per workspace (+ spend limit) | M4 |
| Langfuse | public/secret keys | M4 |
| Google Cloud (calendar OAuth client) | client ID + secret | M5 |
| Self-generated (`openssl rand -base64 48`) | ENGINE_RPC_SECRET, ENGINE_WAKE_SECRET, CSRF_SECRET, MOCK_BILLING_WEBHOOK_SECRET, OAUTH_STATE_SECRET | M0–M5 |
| Optional paid adapters | Deepgram, AssemblyAI, Mistral, Voyage, OpenAI | only if you enable them |
| Stripe | none | not until real billing |
