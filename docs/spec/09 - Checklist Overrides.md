---
title: StudyForge — Engineering Checklist Overrides
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, checklist]
---

# 09: Engineering Checklist Overrides

This document tells the agent how to apply **every note** in `docs/checklist/ENGINEERING_CHECKLIST.md` (derived from [[Agent-Build-Checklist/Engineering Checklist|Engineering Checklist]]) to StudyForge.

**Rule:** unless a note is listed below with an override, **every item applies as written** and must be built and verified. Overrides are one of the following:
- **ADAPTED:** the item applies, but "how" is specified here for this stack or business model. Mark it `[x]` once the adapted version is done.
- **N/A:** it doesn't apply to StudyForge's business model. Mark it `[x] N/A: <reason>`.
- **DEFERRED:** it applies later. Mark it `[ ] DEFERRED until <trigger>`.
- **🔑:** needs a human action (see doc 10).

**Tenancy translation (applies everywhere):** StudyForge is B2C with **tenant = user**. Wherever an item says "tenant", read "user" and implement it with `user_id` + RLS. "Cross-tenant" tests = cross-user tests. This is **not** an N/A. These items are fully in scope.

---

## BUILD phase

### Architecture
| Note | Override |
|---|---|
| API Design Principles | ADAPTED: conventions = doc 04 §1. OpenAPI generated from zod. |
| Data Modeling Fundamentals | ADAPTED: doc 03. "Multi-tenant isolation baked in" = `user_id` on every table + composite FKs. |
| Idempotency in API Design | ADAPTED: "payment-related endpoints" = the mock billing endpoints + webhook handler (the real code paths). Also covers job creation, reviews and exam submit. |
| Monolith vs Microservices | ADAPTED: modular monolith + engine worker (ADR-0001). The "service split justified" item is satisfied by ADR-0001's Python-tooling rationale. |
| Multi-Tenancy Architecture Models | ADAPTED: pool model, tenant = user. **N/A:** "Migration path from pool to silo for large/compliance-sensitive customers": B2C has no such customers (revisit if institutions are added; ADR-0002). |
| System Design Fundamentals | as written. |
| Tenant Isolation Strategies | ADAPTED: cache keys `u:{user_id}:…`; pgmq messages carry only `job_id` (the job row has `user_id`); Storage paths `{user_id}/…`; logs/traces tagged with a hashed user ID. |
| Designing for Statelessness | as written (stateless, host-agnostic web tier + Cloud Run; the kill test is in the M0 gate: kill a Cloud Run instance mid-job → the message reappears after its visibility timeout and the sweeper re-wakes the engine). |
| The Twelve-Factor App | as written. |
| Versioning APIs | ADAPTED: "Version/API-key usage tracked" → track by client (`x-client: web@<version>`) since there are no external API keys at launch. |
| Domain-Driven Design Basics | ADAPTED: bounded contexts = Ingestion, Planning, Comprehension, Retention, Diagnostics, ExamDay, Billing, Identity. Glossary in `docs/glossary.md`. |
| Event-Driven Architecture | ADAPTED: transport = pgmq (ADR-0008). |
| REST vs GraphQL vs RPC | ADAPTED: REST (ADR-0003); the internal engine RPC is a documented deliberate split. |

### Infrastructure
| Note | Override |
|---|---|
| Choosing a Hosting Platform | ADAPTED: decided. Web tier on an operator-managed host for now, deployable unchanged to Vercel/Cloud Run (ADR-0014); Supabase; Google Cloud Run for the engine (ADR-0013). Write the ADRs with the cost model + lock-in notes (the same Docker image runs anywhere). 🔑 accounts. |
| Cloud Account Setup and Org Structure | ADAPTED: "separate accounts for production and non-production" = local (Docker) vs the single cloud project for each provider (ADR-0019). "Audit logging" = Google Cloud **Audit Logs** (Admin Activity is on by default; enable Data Access logs for Secret Manager and IAM). "Audit logging (CloudTrail)" = use each platform's audit logs where the plan includes them; **where it's plan-gated , mark it N/A-for-now with ADR and compensate with git + Terraform history.** Tagging = Google Cloud **labels** (`app=studyforge, env=<env>, component=<name>`) + the naming convention `sf-<component>`. 🔑 MFA on all human accounts. |
| Environments | ADAPTED (ADR-0019): local + production only, by owner decision. "Clearly separated", "separate credentials" (local Supabase vs cloud), "restricted production access" and "synthetic data outside production" → as written. "Staging mirrors production" and "promotion through staging" → covered by the pre-deploy rehearsal, canary and rollback in `pnpm deploy:prod`; mark those items `ADAPTED` with that evidence. |
| Cost Estimation and Budgeting | ADAPTED: `docs/costs.md` + doc 07 §8; budget alerts: Supabase usage monitoring, a **Google Cloud budget with alerts at 50/90/100%** (Terraform-managed), Cloud Run `max-instances` caps, Anthropic workspace limit (🔑). |
| Infrastructure as Code | ADAPTED: Terraform for **all Google Cloud resources** (Cloud Run services/jobs, Artifact Registry, service accounts, IAM bindings, Secret Manager, VPC, budgets), plus Supabase settings. Image *deploys* happen in the scripted pipeline (`pnpm deploy:*`) with `gcloud run deploy` against Terraform-managed services. The Supabase DB schema via migrations counts as IaC for the DB. |
| Load Balancing | ADAPTED: Cloud Run load-balances the engine across instances (verify the startup/liveness probes, the traffic-split canary, and the request metrics). The web tier is a single operator-hosted instance for now; web load-balancing items → DEFERRED until the web tier is hosted. |
| Networking Fundamentals (VPC, Subnets) | ADAPTED: managed platforms. Supabase: SSL enforcement ON, the pooler. Supabase network restrictions (IP allowlist) are **not used**: Cloud Run's outbound IPs are dynamic, and a static IP needs Cloud NAT, which is a paid resource. Compensate with `sslmode=verify-full`, the dedicated least-privilege `engine_worker` role with a long rotated password in Secret Manager, and alerting on failed DB logins (ADR). Cloud Run: the engine only serves signed routes + `/healthz`; the sandbox has **no public invoker** (IAM-only) and **no internet egress** (a VPC with no NAT). "SSH exposure": Cloud Run has no SSH; debugging goes through logs only. "Flow logs": N/A on these platforms (ADR); compensate with app-level access logs. |
| Container Orchestration Basics | ADAPTED: Cloud Run (managed serverless containers, not Kubernetes). Resource limits = Cloud Run CPU/memory per service and job; autoscaling = `min/max-instances` + concurrency; readiness/liveness = Cloud Run startup and liveness probes. Items about self-managed K8s → N/A with reason. |

### Auth & Identity
| Note | Override |
|---|---|
| Brute-Force & Credential Stuffing | ADAPTED: Supabase Auth rate limits + Postgres per-IP/per-email rate limits + progressive lockout + the `BotCheck` interface (no-op now; the CAPTCHA item → DEFERRED until the web tier is publicly hosted) + an **app-implemented breached-password check** (Have I Been Pwned range API, k-anonymity: send only the first 5 SHA-1 hex chars) on signup and password change. The anomalous login alert = new-device email + an admin alert on > 20 failures/min across accounts. |
| Multi-Factor Authentication | ADAPTED: TOTP + recovery codes; **no SMS** (ADR-0005); passkeys per ADR-0005; mandatory for admins. **N/A:** "Org-level MFA enforcement for enterprise customers" (B2C). |
| Password Hashing | ADAPTED: managed by Supabase Auth (bcrypt). ADR-0006 documents managed-auth rationale. No plaintext-password paths (grep test + log scrubbing test). |
| RBAC and ABAC | ADAPTED: roles `user`, `support`, `admin`; ABAC = ownership (`user_id`) + attempt-lock state + entitlements. The central policy layer is `packages/core/authz`. |
| Session Management | ADAPTED: Supabase sessions; enforce an **inactivity timeout** (default 7 days) and an **absolute session lifetime** (default 30 days) in the app's middleware, by tracking `last_seen_at` / `session_started_at` per session ID and signing out server-side when exceeded (independent of the Supabase plan; if the Supabase-native setting is available, turn it on too as defense in depth); sessions list/revoke via a security-definer RPC over `auth.sessions`. |
| Tenant-Aware Authorization | tenancy translation. |
| Token Handling | ADAPTED: Supabase JWT (short-lived access token, rotating refresh tokens with reuse detection, built in). HttpOnly cookies (ADR-0004). JWT signing keys: use Supabase asymmetric JWT signing keys with rotation. |
| Account Recovery Flows | ADAPTED: "Support staff trained on social engineering" → write `docs/runbooks/account-recovery-support.md` (human training itself is 🔑 in doc 10). |
| Email Verification | as written. |
| OAuth 2.0 and OIDC | as written (Google login + calendar OAuth). Account linking: the same verified email → link only after re-auth. |
| Password Policies | as written. |
| Passkeys and WebAuthn | as written per ADR-0005. "UX tested with real users" → 🔑 (5-person hallway test, doc 10). |
| Magic Links | as written (Supabase OTP/magic link). |

### Security
| Note | Override |
|---|---|
| Audit Logging | ADAPTED: `audit.events` (doc 03 §3.9). **DEFERRED:** "Customer-facing audit log feature for enterprise" until institutional customers. (Users do see their own security events under Settings → Security.) |
| Cloud IAM Least Privilege | ADAPTED: DB roles `authenticated`, `engine_worker`, `retention_job`, `ci_migrator`; the Supabase service key used only in server code and the engine; separate **Google service accounts** per component (`sf-engine`, `sf-engine-jobs`, `sf-sandbox`, `sf-deployer`) with only the roles each needs (e.g. the engine can run jobs and invoke the sandbox; the sandbox has no roles at all); **no service-account keys**: deploys use the operator's `gcloud` login impersonating `sf-deployer`; a quarterly access review (🔑 calendar reminder). |
| CSRF | ADAPTED: doc 04 §1. |
| XSS | ADAPTED: React escaping; `dangerouslySetInnerHTML` banned except in the audited `SafeMarkdown` (sanitize-html allowlist + KaTeX trust:false). |
| Dependency & Supply Chain | ADAPTED: OSV/pnpm audit/pip-audit in `pnpm verify` (so "on every PR" = on every merge) + a weekly `pnpm deps:check` report ("on a schedule"), lockfiles, CycloneDX SBOM, npm provenance where available, cosign on engine images. |
| Encryption at Rest | ADAPTED: provider-managed (Supabase AES-256; Google Cloud encrypts all data at rest by default). Field-level: calendar refresh tokens in **Supabase Vault**; recovery codes hashed. Customer-managed keys → N/A (no compliance driver; ADR). |
| Encryption in Transit | ADAPTED: TLS everywhere; `sslmode=verify-full` from the engine to Postgres; engine↔sandbox over HTTPS with an IAM ID token. mTLS → N/A at this scale (ADR). |
| Input Validation | as written (zod/pydantic). |
| IDOR | as written; UUIDv7 IDs; the 404-not-403 policy. |
| Output Encoding | as written. |
| OWASP API Security Top 10 | ADAPTED: `docs/security/owasp-api-top10.md` maps each category to controls; the route inventory is auto-generated from the file system and OpenAPI. |
| OWASP Top 10 | ADAPTED: `docs/security/owasp-top10.md`; **check whether a newer edition than 2021 has been published (OWASP Top 10:2025) and map against the latest.** "Team understands" → 🔑 you read it (doc 10). |
| Rate Limiting and Abuse Prevention | ADAPTED: doc 04 buckets via the Postgres limiter (ADR-0016); Cloud Run `max-instances` + concurrency as the engine-side ceiling. "Edge-level limiting" → DEFERRED until the web tier is publicly hosted. |
| Secrets Management | ADAPTED: "dedicated secrets manager" = **Google Secret Manager** (mounted into Cloud Run, with per-secret IAM) for everything that runs in Google Cloud + Supabase Vault for DB-side secrets. The operator host keeps `.env.production` git-ignored with owner-only file permissions (the documented compensating control in ADR-0014). Rotation runbook. |
| SQL Injection | as written; Semgrep rules for `sql` template misuse in TS and f-strings in Python SQL. |
| CSP & Security Headers | as written (nonce-based CSP via Next middleware). |
| CORS | ADAPTED: the API is same-origin only; `/api/v1` sends no ACAO except to the allowlist (`APP_URL` per environment). No per-tenant custom domains → that item N/A. |
| File Upload Security | ADAPTED: magic-byte sniffing (python-magic + `file-type`), allowlist, size by entitlement, randomized keys, per-user paths, served via signed URLs with `Content-Disposition: attachment` for non-previewable types. **Malware scanning:** ClamAV in the engine for files that will be re-served (exports excepted), since user files are private-only and never shared. Document the risk decision in an ADR. Parsers pinned and covered by the weekly `pnpm deps:check`. |
| Key Rotation | as written (runbook + inventory in `docs/security/key-inventory.md`). |
| Mass Assignment | as written (zod `.strict()` + column grants). |
| SAST and DAST | ADAPTED: Semgrep in `pnpm verify` (high findings fail it); ZAP baseline on every production deploy (against the local production build), full scan in M11. "Manual security review of auth/payments" → `docs/security/review-checklist.md` completed at each relevant milestone + 🔑 your review. |
| Security Headers Reference | as written. |
| SSRF Prevention | ADAPTED: at launch no user-supplied URL is ever fetched (Google Calendar is a fixed API host). Still build the shared `safeFetch` (DNS resolve → block private/link-local/metadata ranges, re-validate per redirect, max 3 redirects, 5MB cap, 10s timeout), send every outbound call through an HTTP client with a **vendor host allowlist**, and add a lint rule banning raw `fetch`/`httpx` on user-provided URLs. Test these against SSRF payloads. The remaining items fully apply once URL-based ingestion or an ICS-style provider is added. |
| Clickjacking Protection | as written (`frame-ancestors 'none'`). |
| Container Security | as written (engine + sandbox images; the sandbox runs Piston's isolate with seccomp). |

### Data
| Note | Override |
|---|---|
| Backups and Restore Testing | **DEFERRED** by owner decision (ADR-0018): mark each item `DEFERRED until owner enables backups`. Still document in `docs/runbooks/dr.md` what each failure scenario loses, and keep the backup/restore design in the ADR so enabling it later is quick. |
| Choosing a Database | as written (ADR for Postgres + pgvector vs a separate vector DB). |
| Database Schema Design | as written. |
| PII Handling and Classification | ADAPTED: tiers T0–T4 (doc 03). Sentry/PostHog scrubbing rules; user content never sent to analytics. |
| Row-Level Security | ADAPTED: "tenant_id" = `user_id`; "application connection uses a role RLS applies to" = supabase-js with the user JWT; the engine uses `engine_worker` with explicit filters (ADR-0007) and a test proving the engine's queries include `user_id`. |
| User Data Deletion | as written (M10). "Propagated to subprocessors": PostHog, Langfuse, the email outbox, and the optional paid adapters (most don't retain data; document each one). No backups exist (ADR-0018), so deletion is complete once the primary stores are purged (disclosed in the Privacy Policy). |
| Zero-Downtime Migrations | as written, except "tested against realistic production-scale data in staging" → tested locally against a production-scale **synthetic** dataset + the pre-deploy rehearsal (ADR-0019). |
| Data Retention Policies | as written (doc 03 §4). |
| Database Indexing | as written; `pg_stat_statements` + the Supabase query performance advisor reviewed at each milestone. |
| Point-in-Time Recovery | **DEFERRED** together with backups (ADR-0018). |
| User Data Export | as written (self-serve, M10). |

### Payments & Billing (mock provider, doc 07)
| Note | Override |
|---|---|
| Choosing a Payments Provider | ADAPTED: mock provider behind `BillingProvider`; ADR-0011 records the MoR vs processor analysis for later (Stripe + Stripe Tax recommended; Paddle/Lemon Squeezy as MoR alternatives). 🔑 the final choice before real billing. |
| Payment Webhooks & Idempotency | ADAPTED: implemented for real against signed mock events (the same handler as future Stripe webhooks). The reconciliation job compares against the mock ledger. |
| PCI Compliance for Payments | ADAPTED: **no card data can exist in the system** (no card inputs; a test asserts it). Items about tokenization/SAQ → `[ ] DEFERRED until real billing` except "No raw card data logged/stored/transmitted" and "Support tooling never exposes card numbers", which are `[x]` by design with the test as evidence. |
| Subscription Billing Models | ADAPTED: "provider's native subscription primitives" → the mock provider owns the subscription lifecycle (the same shape as Stripe objects). Everything else as written. |
| Failed Payments and Dunning | ADAPTED: state machine + emails + grace period + involuntary churn metric, driven by **simulated** failures. "Smart retries" and "card account updater" → DEFERRED until real billing. |
| Invoicing | ADAPTED: internal invoice generator (mock) with sequential numbering, PDF, email, history. "Customer tax ID/VAT" → DEFERRED until real billing (B2C; add with Stripe Tax). |
| Proration | ADAPTED: computed on list prices and shown in the preview; discounted to $0. "Seat quantity changes" → N/A (no seats in B2C). |
| Sales Tax and VAT Automation | **DEFERRED until real billing** (all items). 🔑 tax advice before charging. |
| Trials and Freemium | ADAPTED: freemium chosen; trial state machine tested but not exposed; abuse prevention = email verification + progressive lockout + disposable-domain blocklist + per-IP signup limits + free-tier cost caps. |
| Refunds and Chargebacks | ADAPTED: refund policy page (📄) + admin credit-note action. Chargeback items → DEFERRED until real billing. |
| Usage-Based Billing | ADAPTED: metering + visibility + caps implemented (they drive quotas); "billed via platform" → DEFERRED (no usage-priced plans at launch). |

### Frontend & UX
All notes **as written**, with these specifics: Accessibility = WCAG **2.2** AA; i18n = next-intl, English only (Localization is in GROWTH); UI Component Libraries = shadcn/ui; Design Systems = tokens + Storybook; Frontend Performance budgets = LCP < 2.5s, INP < 200ms, CLS < 0.1 on mid-tier mobile (web-vitals → PostHog).

### Backend
| Note | Override |
|---|---|
| Background Jobs and Queues | ADAPTED: pgmq + `jobs` (doc 04 §3). |
| Email Sending Infrastructure | ADAPTED: `EmailProvider` + the outbox implementation (ADR-0015). Templates, preferences, suppression list, unsubscribe logic and idempotent sends are built for real now; items about sending domains, provider accounts and bounce handling → DEFERRED until a real email provider is enabled. |
| Caching Strategies | ADAPTED: Next.js route cache for marketing pages; per-request entitlement cache + a short-TTL Postgres-backed cache table for hot entitlements (invalidated on billing events); prompt caching for LLMs. |
| Concurrency and Locking | as written (quota counters, attempt state, plan versions with optimistic locking, `SELECT … FOR UPDATE SKIP LOCKED` semantics in pgmq). |
| File Storage | as written. |
| Rate Limiting Implementation | as written. |
| Service Architecture Patterns | as written (layered: route → core service → repository). |
| API Gateway Patterns | ADAPTED: no separate gateway; Next.js middleware provides auth, rate limit, request ID and headers. Document in an ADR; items requiring a dedicated gateway → N/A. |
| Search Implementation | ADAPTED: Postgres FTS + pgvector (ADR-0012). |
| Webhooks (Outbound) | **DEFERRED until** there are integrations/public API consumers (no outbound webhooks at launch). Inbound webhook hardening is covered under Payments/Calendar. |

### Testing & QA
All notes **as written**. Contract Testing = OpenAPI snapshot tests + ts-fsrs/py-fsrs parity + the engine RPC schema tests. Test Data Management = synthetic seed only; production is touched only by the dedicated smoke-test user (a `pnpm verify` check forbids prod connection strings outside `.env.production`).

### DevOps & CI/CD
ADAPTED for the local pipeline (ADR-0017): CI/CD Pipeline Design = `pnpm verify` + git hooks + scripted deploys; Secrets in CI/CD = scripts read secrets from Secret Manager or git-ignored env files and never print or pass them as arguments; Code Review Process = the agent self-reviews each milestone against `docs/security/review-checklist.md` + 🔑 your review of the milestone summary; Environment Promotion = the image tag verified locally is the one deployed, behind the pre-deploy rehearsal + canary (ADR-0019); IaC Pipelines = `terraform plan` output saved in `docs/infra/plans/` before every apply. Feature Flags = PostHog flags (server-evaluated for gating; a flag-removal ticket is created with each flag). Deployment Strategies = web tier: build + restart, with rollback to the previous tag; engine: Cloud Run revisions with traffic splitting (canary) and instant rollback to the previous revision. Release Management = Conventional Commits + release-please (run locally) → `/changelog`.

### Observability
All notes **as written**. Alerting routes: Sentry + Better Stack → email + push (🔑 your phone). Metrics & Dashboards: PostHog (product), Sentry (performance), Better Stack (uptime), Supabase reports (DB), Langfuse (AI), and an admin metrics page (business).

### Reliability & DR
| Note | Override |
|---|---|
| Disaster Recovery Planning | as written (`docs/runbooks/dr.md`: without backups (ADR-0018), data in a lost Supabase project is gone; recovery = recreate the project with Terraform + migrations and redeploy from git. Document this plainly). |
| Incident Management | ADAPTED: a solo founder at launch; severity levels + the runbook + the status page process. |
| Postmortems | as written (template from the vault `99-Templates/Postmortem Template`). |
| SLAs and SLOs | ADAPTED: internal SLOs defined in M11; the public SLA is a 📄 draft (doc 10 decides whether to publish it). |

### Email & Comms
Email Templates, In-App Notifications, Notification Preferences and Transactional Email → as written, through `EmailProvider` (outbox). SPF/DKIM/DMARC and Email Deliverability → DEFERRED until a real email provider + domain are enabled.

### Analytics
All notes **as written**; PostHog is consent-gated; no content or PII in events (`docs/analytics-events.md` lists every event + its properties; a `pnpm verify` test validates the calls against it).

### Support & Success (technical setup)
In-App Support Widgets → as written (custom widget, SUP-01).

### Operations (engineering subset)
Admin Panel Design, Internal Tooling → as written (M10).

### AI Features (this product uses AI heavily, so **all in scope**)
As written, implemented per doc 06: cost limits (§6), data leakage (§4–5), prompt injection (§5), observability (§8), evals (§7), integration patterns (§2–3), RAG (§4).

### Compliance (buildable mechanisms)
| Note | Override |
|---|---|
| GDPR Data Subject Rights | as written (M10). Access = export; rectification = settings + support; erasure = deletion; objection/restriction = support process doc; portability = JSON/CSV/.apkg. |
| Records of Processing Activities | 📄 generated draft in M10. |

---

## PRE-LAUNCH phase
| Note | Override |
|---|---|
| TLS and Certificate Management | ADAPTED: Google-managed TLS on Cloud Run and Supabase (verify minimum TLS versions). Web-tier TLS, HSTS and preload → DEFERRED until the web tier is publicly hosted. |
| DNS Management / Domain Registration | DEFERRED until the web tier is publicly hosted (no custom domain is used now). |
| CDN Setup | DEFERRED until the web tier is publicly hosted (static assets get correct cache headers now). |
| Security Incident Response | as written (runbook + a GDPR 72-hour breach-notification procedure draft + a contact tree 🔑). |
| Load and Performance Testing | as written (k6, M11). |
| Uptime Monitoring | Better Stack (🔑 account). |
| Documentation and Knowledge Base | as written (`/docs`). |
| Help Desk Setup | ADAPTED: the in-app tickets table + admin queue; ticket notifications go to the Mail outbox; a dedicated tool is optional (🔑 decision). |
| Status Page | Better Stack hosted status page on its free subdomain, monitoring the engine `/healthz` and Supabase health (🔑 account). |
| Privacy Policy / Terms of Service / Cookie Policy / DPA / Subprocessors | 📄 as written. **DPA note:** B2C users don't sign DPAs; publish the DPA page anyway as a template for future institutional deals, marked draft. |

## LAUNCH phase
| Note | Override |
|---|---|
| Vulnerability Disclosure Policy | as written (security.txt + /security page; 🔑 sign-off on safe-harbor wording). |
| Key SaaS Metrics | ADAPTED: MRR is shown as "list-price MRR (mock)" and "actual MRR ($0)"; churn/LTV computed from mock subscriptions; CAC → 🔑 needs marketing spend data. |
| Service Level Agreement | 📄 draft; **DEFERRED publishing** until 90 days of uptime data exist. |

## GROWTH phase: all DEFERRED
| Note | Trigger |
|---|---|
| SSO and SAML | institution/instructor accounts become a product line |
| SCIM Provisioning | same as above, plus a customer IdP requirement |
| Data Warehousing Basics | > 10k MAU or analytics queries impacting the prod DB |
| Localization (l10n) | > 10% of signups from non-English locales |
| Distributed Tracing | > 3 services, or when debugging cross-service latency is a recurring pain (OpenTelemetry → Sentry/Honeycomb) |
| Log Retention and Cost | log costs > $50/mo or a compliance requirement |
| Error Budgets | once the public SLA is published |
| Cohort Analysis | 90 days of user data (PostHog cohorts are available earlier for free) |

## SCALE phase: all DEFERRED
| Note | Trigger |
|---|---|
| Read Replicas and Scaling Reads | DB CPU > 60% sustained or p95 read latency regressing |
| Chaos Engineering Basics | a paid SLA exists + more than 1 engineer on call |
| Database Scaling Strategies | the largest table > 100M rows (likely `review_logs`) → partition by `user_id` hash/time |
| Enterprise Readiness Checklist | an institutional customer pipeline exists |
| Horizontal vs Vertical Scaling | engine queue age SLO breached for 3 days → autoscale machines / a GPU STT pool |
| Performance Optimization | SLO breach trend |
| Caching Layers at Scale | cache needs beyond what Postgres-backed caching handles |
| Multi-Region Architecture | an EU data residency requirement or > 30% EU users with latency complaints |

---

## Notes that live in the Human Handoff Checklist (not the agent's)
Penetration Testing, Bug Bounty Programs, On-Call Rotations, Business Continuity Planning, Customer Feedback Loops, Customer Success Fundamentals, Vendor Management, Cost Monitoring and Optimization, Access and Offboarding Procedures, and all of Discovery, Business-Legal (non-📄), Compliance (non-buildable), and Growth-Marketing. See doc 10. The agent **supports** these with artifacts where useful (e.g. a pentest scope document, a vendor inventory generated from `subprocessors.yaml`, cost dashboards) but doesn't check them off.
