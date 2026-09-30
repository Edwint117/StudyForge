---
title: StudyForge — Milestones & Acceptance Gates
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, milestones]
---

# 08: Milestones & Acceptance Gates

The rules: build strictly in order. Every milestone ends **with `pnpm verify` green, deployed to production with `pnpm deploy:prod`, and an updated `PROGRESS.md` and checklist**, then is merged into `main` and tagged `m<N>-complete`. A gate is passed only when **every** gate item is true. The "Checklist notes closed" column refers to note headings in `ENGINEERING_CHECKLIST.md`. Items in those notes that belong to a later milestone are marked with the milestone they'll close in (in `docs/plan/checklist-triage.md`).

---

## M0: Foundation & delivery pipeline
**Build:** monorepo scaffold; Next.js app with route groups; engine FastAPI skeleton + `/wake` drain + `/healthz` + a Cloud Run Job entrypoint; the pg_net wake trigger + pg_cron sweeper; sandbox service; Supabase local + the production project; Terraform for Google Cloud (Cloud Run service/jobs, Artifact Registry, service accounts + IAM, Secret Manager, the no-egress VPC for the sandbox, budget alert), Supabase settings; the `sf-deployer` service account + impersonation from the operator's `gcloud` login; the local pipeline per doc 02 §6 (lefthook hooks, `pnpm verify`, `pnpm deploy:prod`, `pnpm rollback:prod`, `pnpm nightly`); `pnpm start:prod` for the web tier; lint/format/typecheck; Vitest/pytest/Playwright/pgTAP harnesses; gitleaks pre-commit; Semgrep, OSV, Trivy, SBOM; Sentry (web+engine); structured JSON logging with request IDs; global security headers + CSP (report-only → enforce in M11); `.env.example`; `docs/adr/0001–0018`; `docs/data-map.md`, `docs/subprocessors.yaml`, `docs/costs.md` skeletons; `PROGRESS.md`.
**Gate:**
- [ ] `pnpm setup && pnpm dev` works from a fresh clone (documented in README) with all 3 services running locally.
- [ ] `pnpm verify` runs the full pipeline; a failing check blocks the merge script, and a secret in a staged diff blocks the commit (pre-commit hook).
- [ ] `pnpm deploy:prod` (including its pre-deploy rehearsal) deploys migrations + engine to production, and `pnpm start:prod` serves the web tier against it; `/healthz` and the web health endpoint are green; `pnpm rollback:prod` restores the previous revision.
- [ ] Killing the engine machine mid-job loses no job (the heartbeat/VT test passes).
- [ ] ADRs 0001–0018 are merged.
**Checklist notes closed:** Monolith vs Microservices, Twelve-Factor, Designing for Statelessness, System Design Fundamentals, REST vs GraphQL vs RPC, Choosing a Hosting Platform, Cloud Account Setup (🔑 parts), Environments, IaC, IaC Pipelines, Container Orchestration (Cloud Run), Container Security, CI/CD Pipeline Design, Secrets in CI/CD, Secrets Management, Code Review Process, Dependency & Supply Chain, SAST & DAST (SAST half), Logging Fundamentals, Structured Logging, Error Tracking, Choosing a Database.

## M1: Identity, tenancy & security baseline
**Build:** the schema for identity/account tables + audit schema; the RLS standard + the generated pgTAP cross-tenant matrix; Supabase Auth (email/password, magic link, Google), the 18+ gate, ToS acceptance, email verification gating, the password policy + breach check, TOTP MFA + recovery codes, passkeys per ADR-0005, sessions list/revoke, recovery flows, security emails (through `EmailProvider` → outbox, with Supabase Auth emails routed in via the Send Email hook, plus the admin **Mail outbox** page), the `BotCheck` interface (no-op) + progressive lockout, the Postgres rate limiter, the idempotency middleware, the CSRF middleware, `requireUser/requireAdmin` + the default-deny lint, the problem+json error handler, the OpenAPI generation skeleton, the admin role + `/admin` shell with MFA enforcement, and audit logging for every auth and admin event.
**Gate:**
- [ ] The pgTAP matrix proves isolation for every table (a pgTAP test in `pnpm verify` fails if any `public` table lacks RLS).
- [ ] E2E: signup → verify → MFA enroll → logout → login with TOTP → recovery code → revoke other sessions.
- [ ] Under-18 signup is blocked; the ToS version acceptance is stored.
- [ ] Brute force: the 11th login attempt in 15 min is rate-limited, and progressive lockout engages after repeated failures.
- [ ] Tokens never appear in localStorage (a Playwright assertion); cookies are HttpOnly/Secure/SameSite=Lax.
- [ ] Every mutating route rejects a missing CSRF token and a foreign Origin (automated test across the route inventory).
**Checklist notes closed:** all of Auth & Identity (BUILD), Multi-Tenancy Models, Tenant Isolation, Tenant-Aware Authorization, RBAC/ABAC, Row-Level Security, IDOR, Mass Assignment, CSRF, CORS, XSS (baseline), Output Encoding, Input Validation, SQL Injection, Rate Limiting (both notes), Audit Logging, API Design Principles, Idempotency, Versioning APIs, Email Verification, Transactional Email (auth emails, via the outbox), Cloud IAM Least Privilege.

## M2: SaaS shell (marketing, onboarding, settings, comms, analytics, support)
**Build:** the marketing site (landing, pricing (from the DB), docs (MDX), changelog), the legal pages scaffold with draft text (📄 ToS, Privacy, Cookies, AUP, DMCA, Refunds, Subprocessors (auto from YAML), DPA, SLA, Security + `security.txt`), the cookie consent banner with script blocking + GPC, PostHog behind consent + the event taxonomy (`docs/analytics-events.md`), feature flags, the app shell + design system + Storybook, empty/error states, settings pages, the notifications center + preferences + email templates (React Email) + the digest job + web push, the support widget + tickets + content reports, i18n extraction (next-intl), the a11y baseline, PWA install.
**Gate:**
- [ ] Lighthouse ≥ 90 on landing/pricing (mobile); axe reports zero serious/critical issues on every route.
- [ ] Rejecting cookies ⇒ no PostHog network requests (Playwright network assertion).
- [ ] The subprocessors page is generated from `docs/subprocessors.yaml`, and a check in `pnpm verify` fails if a new vendor SDK is added without a YAML entry.
- [ ] Every notification category respects the preference matrix + quiet hours (unit tests).
- [ ] Every user-facing string is externalized (lint rule).
**Checklist notes closed:** Onboarding Flows, Accessibility, Error State Design, Form Validation UX, Responsive & Mobile, Design Systems, Empty States, i18n, UI Component Libraries, Email Templates, In-App Notifications, Notification Preferences, Analytics Tooling, Event Tracking Design, Privacy-Safe Analytics, Product Analytics Fundamentals, Feature Flags, In-App Support Widgets, Documentation & Knowledge Base (scaffold), 📄 legal docs (draft), Cookie Policy & Consent, Clickjacking, Security Headers, CSP (report-only).

## M3: Plans, entitlements & mock billing
**Build:** everything in doc 07: schema, plans seed, entitlements functions, quotas + `usage_counters`, mock provider + checkout page + signed events + the webhook handler + reconciliation, invoices + PDFs + numbering, plan change/cancel/resume, dunning simulation, the usage meters UI, the upgrade modals, and admin billing tools.
**Gate:**
- [ ] E2E: Free → upgrade to Pro (sees $0.00) → invoice emailed → Pro features unlocked → downgrade scheduled → period end (test clock) → Free.
- [ ] Replaying every billing event twice and in reverse order yields identical final state (a property test).
- [ ] The quota race: 50 concurrent requests at the limit boundary → exactly the limit succeed.
- [ ] Simulated payment failure → grace period → downgrade → recovery flows work, with emails.
- [ ] No card input exists anywhere in the DOM (a test asserts no `input[autocomplete^=cc-]`).
**Checklist notes closed (adapted per doc 09):** Choosing a Payments Provider, Payment Webhooks & Idempotency, PCI (by design), Subscription Billing Models, Failed Payments & Dunning (simulated), Invoicing, Proration, Trials & Freemium, Refunds (policy + credit note), Usage-Based Billing (metering), Concurrency & Locking. Sales Tax/VAT → DEFERRED.

## M4: Module 1, Ingestion & Knowledge Graph
**Build:** upload flow (TUS), file validation (magic bytes, size, allowlist), the job pipeline + progress Realtime (ADR-0004 token), parsing adapters (Docling/PyMuPDF/pptx/docx), OCR adapters (Paddle/TrOCR + the paid options wired but off), STT adapters (faster-whisper + paid options), chunking + typing, embeddings + HNSW, the hybrid search RPC + UI, concept extraction + graph merge + the graph editor UI, asset links + review UI, the document viewer (PDF.js, slides, audio w/ transcript seek, KaTeX, Shiki), dedup + versioning, past-exam question extraction, Provider Settings admin UI + circuit breakers + the kill switch + metering, the Langfuse tracing, Storage RLS, and a shared SSRF-safe `safeFetch` utility for any outbound fetch of a URL that isn't a fixed vendor API.
**Gate:**
- [ ] Fixture corpus (`fixtures/ingest/`: a 50-page textbook PDF, a 30-slide PPTX with speaker notes, a DOCX, 5 handwritten pages, a 20-min lecture MP3, a scanned past exam) ingests on production (as the smoke-test user, cleaned up afterwards) within the doc 01 NFR times with free adapters.
- [ ] Math is preserved as LaTeX (≥ 90% of 40 labelled formulas render identically); code blocks keep their language.
- [ ] Search returns the labelled correct chunk in the top 5 for ≥ 85% of 50 labelled queries.
- [ ] `concept_extract` eval gate passes; user graph edits survive re-ingestion.
- [ ] Malicious files (a polyglot, a zip bomb, a PDF with JS, an oversize file, a wrong extension) are rejected or neutralized (tests).
- [ ] User B cannot fetch user A's Storage object even with a guessed path (test).
- [ ] Switching the STT adapter in admin takes effect without a redeploy; with a paid key missing, it falls back to the free adapter.
**Checklist notes closed:** File Storage, File Upload Security, Background Jobs & Queues, Event-Driven Architecture, Search Implementation, Caching Strategies, SSRF Prevention, LLM Integration Patterns, RAG Fundamentals (index side), AI Cost Limits, AI Feature Observability, Data Leakage Prevention (retrieval scoping), Encryption at Rest (verify Storage/DB), Database Indexing Fundamentals, Service Architecture Patterns, API Gateway Patterns (doc: N/A-lite per doc 09).

## M5: Module 2, Exam-Backwards Planner & Calendar Sync
**Build:** syllabus extraction + the confirm UI (source spans), exams CRUD + scope picker, availability rules, planner-1 + rebalance-1 (doc 05) with all fixtures, the feasibility UX, plan views (Today/Week/Month/Countdown) + drag-to-reschedule, the missed-session detector, the `CalendarProvider` interface + the Google implementation (OAuth with PKCE, minimal scopes, tokens in Vault), initial and incremental sync, push channels + renewal, write-back to a dedicated calendar, two-way edits, the free-plan read-only mode, and the disconnect flow (optionally delete our events).
**Gate:**
- [ ] All doc 05 §4 fixtures and property tests pass.
- [ ] `syllabus_extract` eval gate passes.
- [ ] E2E with a Google test account against production (🔑): connect → busy blocks appear → plan avoids them → moving a StudyForge event in Google updates the session within 2 min (push) or 15 min (poll).
- [ ] A contract test suite for `CalendarProvider` runs against the Google implementation (with a recorded-HTTP fake), so any future provider can be checked with the same suite.
- [ ] A revoked OAuth grant → `needs_reauth` status + a notification, with no crash loops.
**Checklist notes closed:** OAuth 2.0 & OIDC (calendar side), Webhooks (inbound validation), Concurrency & Locking (plan versions), Key Rotation (OAuth secrets runbook).

## M6: Module 3, Comprehension (cards, Feynman, tutor, cheat sheets)
**Build:** card generation (Haiku, Batch API path), lint, dedup, the draft review queue, all card types incl. concept-map, math-step and code; Feynman (text + voice); the Socratic tutor (streaming SSE, retrieval, citations, hint levels, guard pre/post checks, exam lock, chat actions); the cheat-sheet builder + page-budget fit + PDF export; MathLive/CodeMirror inputs; content reporting; the prompt-injection defenses from doc 06 §5.
**Gate:**
- [ ] Eval gates pass: `cards_quality`, `tutor_socratic`, `feynman`, `injection` (100%).
- [ ] Tutor first token < 2s p95 on the local production build (k6 + synthetic prompts).
- [ ] The cheat-sheet PDF honors a 1-page letter budget for the fixture unit, with KaTeX rendered correctly in the PDF.
- [ ] Rendered AI output can't load external images or run HTML (XSS test corpus).
**Checklist notes closed:** Prompt Injection Defense, Evals for LLM Features, Data Leakage Prevention (full), RAG Fundamentals (full), XSS (rich content), CSP (AI render paths).

## M7: Module 4, Retention Engine (FSRS)
**Build:** card states, the review API + queue, verification (text/numeric/SymPy/code/LLM keypoints) + the proposed rating + override logging, crunch mode, interleaving, session types, undo, the optimizer job + adoption rule, the ts/py parity test, the offline PWA queue + idempotent sync, Anki import/export, stats pages, the keyboard-first UI.
**Gate:**
- [ ] All doc 05 §1–3, §8 fixtures pass, and the parity test passes.
- [ ] Next-card latency < 100ms p95 (prefetch), and the review POST < 250ms p95 (excluding the code-run path).
- [ ] Offline: 50 reviews in airplane mode → reconnect → exactly 50 logs, the correct final states, no duplicates (Playwright offline emulation).
- [ ] Anki round-trip: import the fixture `.apkg` (with review history) → export → re-import → same cards and states.
- [ ] Sandbox escape tests: network access, fork bomb, filesystem write outside the tmp dir, long-running loops → all contained (tests).
**Checklist notes closed:** Unit Testing (property tests), Integration Testing, Contract Testing (ts/py parity + OpenAPI), Performance (review path).

## M8: Module 5, Diagnostics (question bank, mock exams, grading, heatmaps)
**Build:** question bank CRUD + rubric editor, the blueprint + selection + generation + verification pipeline, the strict exam sandbox (server timer, autosave, integrity events, route locks, fullscreen), the deterministic graders + LLM rubric grader + error classification + confidence + disputes/regrade, the results page + "misses → cards", mastery-1 + snapshots, the heatmap (accessible, drill-down), readiness forecast, rebalance triggers.
**Gate:**
- [ ] `grading` and `question_verify` eval gates pass.
- [ ] The timer can't be extended by the client (clock tampering test); a late submission beyond the grace period is rejected.
- [ ] During an attempt, the tutor/notes/cards/search APIs return 423 (test across the inventory).
- [ ] The doc 05 §5–6 fixtures pass; the heatmap passes axe and shows numeric values (not color only).
**Checklist notes closed:** Concurrency & Locking (attempt state), Regression Testing Strategy, Test Data Management (fixture corpora).

## M9: Module 6, Exam-Day Readiness
**Build:** the cram queue, the warm-up (no FSRS updates), the pre-exam checklist seeded from syllabus policies, reminders at T-24h/T-2h (email + push, quiet hours respected), exam-day mode, post-exam score logging + calibration + plan archiving.
**Gate:**
- [ ] The doc 05 §7 fixtures pass.
- [ ] E2E: the seeded demo exam at T-47h shows the cram queue; at T-5h the warm-up is available; the reminders are delivered in the user's timezone (test with 3 timezones incl. DST).
- [ ] Warm-up reviews don't change `card_states` (test).

## M10: Data rights, admin & operations completeness
**Build:** self-serve export (ZIP: JSON+CSV+originals+.apkg) and deletion (grace period, full footprint incl. PostHog/Langfuse/email outbox/Storage/Vault/calendar events), retention pg_cron jobs matching doc 03 §4, the ROPA draft (📄, generated from `data-map.md` + `subprocessors.yaml`), the "Your data & AI" page, the full admin panel (users, support view with access grants, jobs/DLQ, provider settings, content reports, tickets, metrics, flags, announcements), internal tooling scripts (`pnpm ops:*`) run through the scripted pipeline, the key SaaS metrics dashboard (activation, retention, mock MRR at list price, AI cost/user).
**Gate:**
- [ ] The export contains every table in the data map for the user (an automated completeness test that fails when a new user table is added without export coverage).
- [ ] Deletion E2E: after the purge, no rows with that `user_id` in any table, no Storage objects, PostHog person deleted (API verified for the smoke-test user), and the audit event retained without PII.
- [ ] Every admin action appears in `audit.events`; a non-admin gets 404 on `/admin/*`.
**Checklist notes closed:** User Data Export, User Data Deletion, GDPR Data Subject Rights, Records of Processing Activities (📄), Data Retention Policies, PII Handling & Classification, Admin Panel Design, Internal Tooling, Key SaaS Metrics, Metrics & Dashboards.

## M11: Pre-launch hardening
**Build/verify:** CSP enforce mode + a violation reporting endpoint; the DAST (ZAP full scan against the local production build) with findings triaged; k6 load tests (100 concurrent reviewers, 20 concurrent ingests, 50 concurrent tutor streams) with the results in `docs/perf/`; the zero-downtime migration drill (expand/contract on a large synthetic table locally, then applied to production); the DR plan (ADR-0018: no off-platform backups, so it documents exactly what each failure scenario loses and the rebuild steps from git + Terraform + migrations, and the rebuild is rehearsed once against a local Supabase); runbooks (incident response, provider outage, AI kill switch, key rotation, restore, security incident); alerting (Sentry, Better Stack, cost alerts, queue alerts, SLO burn); SLOs defined (availability 99.5%, review POST p95, tutor TTFT) with dashboards; Better Stack uptime monitors on the engine `/healthz` and Supabase health + the status page (🔑 account); TLS verification on Cloud Run and Supabase; correct caching headers for static assets; the final legal draft pass (📄 ToS/Privacy/Cookies reflect actual data flows); the vulnerability disclosure policy (security.txt); the launch checklist (vault `99-Templates/Launch Checklist`) completed; the SLA draft (📄) based on the measured uptime.
**Gate:** the Definition of Done in doc 00 + `ENGINEERING_CHECKLIST.md` BUILD/PRE-LAUNCH/LAUNCH sections contain zero unmarked items + `PROGRESS.md → Blocked on human` is the final go-live list.
**Checklist notes closed:** TLS & Certificate Mgmt (cloud side; web-tier TLS DEFERRED), Security Incident Response, Load & Performance Testing, Uptime Monitoring, Status Page, Help Desk Setup (ticket integration), Zero-Downtime Migrations (drill), Disaster Recovery Planning, Incident Management, Postmortems (template), SLAs & SLOs, Alerting, Deployment Strategies, Rollback Strategies, Environment Promotion, Release Management, Encryption in Transit, Security Testing, E2E Testing, Vulnerability Disclosure Policy, SLA (📄), Key SaaS Metrics.

---

## After launch (not built now; DEFERRED with triggers, see doc 09)
- **Growth:** public web hosting (Vercel) + custom domain + web TLS/CDN + CAPTCHA + calendar push notifications · a real email provider + SPF/DKIM/DMARC + deliverability · off-platform backups + restore testing + point-in-time recovery (ADR-0018) · real billing (Stripe) · more calendar providers (Microsoft Outlook, Apple/ICS) via `CalendarProvider` · SSO/SAML + SCIM (only if institutions become customers) · localization (non-English) · distributed tracing (OpenTelemetry) · log retention tuning · cohort analysis · data warehouse · error budgets · native mobile app · shared decks · institution/instructor accounts.
- **Scale:** read replicas · database scaling · horizontal scaling of the engine (GPU STT pool) · multi-region · chaos engineering · caching layers at scale · performance optimization program · enterprise readiness.
