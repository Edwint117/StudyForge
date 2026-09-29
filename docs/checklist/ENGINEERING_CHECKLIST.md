---
title: Engineering Checklist
category: Agent-Build-Checklist
last_reviewed: 2026-09-22
---

# Engineering Build Checklist

This is a working checklist for an AI coding agent (or a human engineer) to execute against while building a real product. It's derived from [[SaaS-Playbook/00-Index/Master MOC|the SaaS Playbook]] — the reference vault stays untouched; this is a filtered, reorganized copy of only the items that are actually agent-executable engineering work.

**Companion document:** [[Human Handoff Checklist]] — everything in the playbook that isn't here (legal, accounts, money, hiring, marketing) lives there instead. Read both before considering a build "done."

## What this file is
- Every checklist item from the playbook's engineering-relevant categories (Architecture, Infrastructure, Auth & Identity, Security, Data, Payments & Billing, Frontend & UX, Backend, Testing & QA, DevOps & CI/CD, Observability, Reliability & DR, Email & Comms, Analytics, the technical-setup slice of Support & Success, the engineering slice of Operations, AI Features, Scaling, **and the buildable legal/compliance artifacts** — see below), reorganized by build phase instead of by topic.
- **1,147 items across 183 notes.** Nothing was trimmed to "MVP-critical only" — items are tagged `MVP` where the source note marked them `mvp_required: true`, but every item from every relevant note is here, per the instruction that nothing should be ignored. Use the `MVP` tag to sequence work, not to skip items permanently.
- Two kinds of callouts flag items that aren't fully self-contained:
  - `🔑 Needs from you` — the task is still engineering work (writing the integration code, configuring the service) but depends on an account, API key, or credential only a human can create.
  - `📄` — a legal/compliance document or mechanism. **Build the real page, form, and logic** — that part is genuine, working code, not a stub. The *document text* itself (Terms of Service, Privacy Policy wording, DPA language) should be drafted as a reasonable, clearly-marked placeholder — write real, sensible content using standard structure, but flag it unmistakably as a draft pending legal review before anyone relies on it for a real launch. Don't leave these as blank pages or `TODO` comments; a populated draft is far more useful to hand to a lawyer than an empty template.
- Everything else on this list is fully agent-executable with no external dependency beyond normal development access (a code editor, a terminal, a git remote).

## What isn't here
Whole categories that are almost entirely non-engineering are still absent from this file — captured instead in [[Human Handoff Checklist]], organized by when they actually need to happen:
- **01-Discovery** (idea validation, market research, customer interviews, pricing strategy) — product/business decisions that should happen *before* an agent starts building, not engineering tasks.
- **18-Growth-Marketing** in full — marketing content, SEO, launch strategy, paid acquisition, referral programs.
- Most of **02-Business-Legal** and **07-Compliance** — entity formation, founder agreements, IP assignment, contracts/MSA negotiation, vendor agreement review, insurance, taxes, trademark filing, SOC 2/HIPAA/PCI process, security questionnaire response, accessibility legal risk, applicability assessments (GDPR/CCPA/export control/children's privacy). These require money, a signature, a filing, or a judgment call about *your* business — not code.

**Eight notes moved the other way** — buildable legal/compliance artifacts that used to be filed as "human-only" but are really scaffolding work: **Terms of Service, Privacy Policy, Cookie Policy and Consent, Subprocessors List, Data Processing Agreement (DPA), Service Level Agreement (SLA), GDPR Data Subject Rights, and Records of Processing Activities.** They're in the BUILD/PRE-LAUNCH sections below, tagged `📄`, with instructions on what to build for real vs. what to draft as a reviewable placeholder.

A handful of other individual notes were also moved out even though their category is otherwise technical, because the note itself describes a human decision or business process rather than something to build:
- **Penetration Testing** and **Bug Bounty Programs** (06-Security) — engaging and paying a third party.
- **On-Call Rotations** and **Business Continuity Planning** (15-Reliability-DR) — staffing and organizational planning.
- **Customer Feedback Loops** and **Customer Success Fundamentals** (19-Support-Success) — ongoing business practice, not a build task.
- **Vendor Management**, **Cost Monitoring and Optimization**, and **Access and Offboarding Procedures** (20-Operations) — ongoing business/ops process.

Conversely, four notes in 19-Support-Success that are genuinely buildable (Help Desk Setup's integration, the docs site, the status page, an in-app support widget) **are** included here, even though the rest of that category isn't — the split is by what the note actually asks for, not a blanket per-category rule.

## StudyForge planning status

Triaged on 2026-09-27 in [the 183-note plan](../plan/checklist-triage.md). All original items are retained. Only explicit doc 09 deferrals are marked; no implementation item is verified yet. Mixed notes remain open for their active requirements. Stable note anchors N001–N183 correspond to that triage. Item references use the original one-based checkbox order within each note.

## How to use this
1. Work top to bottom by phase: **BUILD** → **PRE-LAUNCH** → **LAUNCH** → **GROWTH** → **SCALE**. Within BUILD (the vast majority of the list), items are grouped by category, then by priority within category.
2. Do every `MVP`-tagged item in BUILD and PRE-LAUNCH before considering the product launch-ready. GROWTH and SCALE items are real but not launch-blocking — come back to them when the situation that justifies them actually arises (real customers, real load), not speculatively.
3. Check items off (`- [x]`) directly in this file as you complete them. This file is meant to be edited over the life of the build — check things off, don't just read past them.
4. When an item's source note has more context than the one-line summary here (rationale, tool options, common mistakes, how to verify), follow the source-note link next to each note's heading.
5. Cross-check against [[Human Handoff Checklist]] whenever an item here needs a credential or account you haven't provided yet — flagged items (`🔑`) tell you exactly what's needed.
6. When you (the agent) reach the end of BUILD and PRE-LAUNCH with everything checked off, the product is code-complete and production-grade *except* for the human-side connections in [[Human Handoff Checklist]] — real credentials, DNS, legal sign-off, and the actual go-live decision.

---

## BUILD PHASE — core engineering work, do this while building the product

### Architecture

<a id="checklist-n001"></a>
**API Design Principles** — priority: critical `MVP` — [[SaaS-Playbook/03-Architecture/API Design Principles|source note]]
- [ ] Naming/structure conventions documented and applied consistently
- [ ] Every endpoint requires explicit authentication/authorization — no accidental open endpoints
- [ ] Server-side input validation applied to every endpoint, independent of client-side checks
- [ ] Consistent error response structure and HTTP status code usage across the API
- [ ] Rate limiting and pagination applied by default on list/collection endpoints
- [ ] Idempotency strategy defined for mutating endpoints expected to be retried
- [ ] API documented (OpenAPI/Swagger) and kept in sync with actual behavior
- [ ] Versioning strategy decided before the first breaking change is needed

<a id="checklist-n002"></a>
**Data Modeling Fundamentals** — priority: critical `MVP` — [[SaaS-Playbook/03-Architecture/Data Modeling Fundamentals|source note]]
- [ ] Entities and relationships modeled from actual domain concepts, not just current UI needs
- [ ] Normalization applied by default; denormalization decisions documented with the performance rationale
- [ ] Database-level constraints (FK, not-null, unique, check) enforce integrity, not just application code
- [ ] Primary key strategy chosen deliberately (sequential vs. UUID/ULID) with trade-offs considered
- [ ] Soft-delete vs. hard-delete strategy decided before it's needed in production
- [ ] Multi-tenant isolation approach baked into schema design from the start, if applicable
- [ ] Every table/column named consistently and documented

<a id="checklist-n003"></a>
**Idempotency in API Design** — priority: critical `MVP` — [[SaaS-Playbook/03-Architecture/Idempotency in API Design|source note]]
- [ ] Idempotency key support implemented for all payment-related mutating endpoints
- [ ] Idempotency key support implemented for any other high-risk-of-duplication operation (provisioning, bulk actions, notification sends)
- [ ] Idempotency enforced via a database-level unique constraint, not just an application-level check
- [ ] Idempotency key scope and expiration window defined
- [ ] Webhook handlers (incoming and outgoing) designed to safely process duplicate deliveries
- [ ] Automated tests simulate duplicate/retried requests and verify no duplicate side effects occur

<a id="checklist-n004"></a>
**Monolith vs Microservices** — priority: critical `MVP` — [[SaaS-Playbook/03-Architecture/Monolith vs Microservices|source note]]
- [ ] Default architecture is a monolith or modular monolith unless a concrete driver says otherwise
- [ ] Internal module boundaries defined clearly even within the monolith
- [ ] Any proposed service split justified by a specific scaling, technology, or team-ownership driver — documented, not assumed
- [ ] Operational cost of each additional service accounted for (monitoring, deploy pipeline, on-call)
- [ ] Extraction done incrementally along existing module boundaries, not as a rewrite
- [ ] Decision revisited periodically as team/load scale changes

<a id="checklist-n005"></a>
**Multi-Tenancy Architecture Models** — priority: critical `MVP` — [[SaaS-Playbook/03-Architecture/Multi-Tenancy Architecture Models|source note]]
- [ ] Multi-tenancy model (silo/pool/hybrid) chosen deliberately with documented rationale
- [ ] Isolation mechanism defined (tenant_id + RLS, or schema-per-tenant) and enforced at the database level, not just application code
- [ ] All data-access paths — API, background jobs, admin tools, analytics — verified to be tenant-scoped
- [ ] Noisy-neighbor mitigation in place (per-tenant rate limits/quotas) for pooled resources
- [ ] Tenant context required (not optional) in the data-access layer, so it can't be silently omitted
- [ ] Migration path from pool to silo defined for large/compliance-sensitive customers

<a id="checklist-n006"></a>
**System Design Fundamentals** — priority: critical `MVP` — [[SaaS-Playbook/03-Architecture/System Design Fundamentals|source note]]
- [ ] Core domain entities and their data-ownership boundaries documented
- [ ] Separation of concerns applied consistently (presentation / business logic / data access)
- [ ] Key failure modes identified and handled deliberately (timeouts, retries, circuit breaking where warranted)
- [ ] Architecture Decision Records started for major structural choices
- [ ] Stack choices favor proven technology except where novelty is the actual differentiator
- [ ] Observability and testability considered as first-class design constraints, not afterthoughts

<a id="checklist-n007"></a>
**Tenant Isolation Strategies** — priority: critical `MVP` — [[SaaS-Playbook/03-Architecture/Tenant Isolation Strategies|source note]]
- [ ] Database-level isolation (RLS or schema separation) enforced as the primary control
- [ ] Cache keys, queue messages, and search index entries all tenant-namespaced
- [ ] File storage access scoped and verified against cross-tenant access via manipulated URLs/IDs
- [ ] Background jobs and scheduled tasks reviewed for correct tenant scoping
- [ ] Logs, metrics, and traces tagged with tenant ID for incident scoping
- [ ] Automated cross-tenant access tests included in the standard CI test suite
- [ ] Any deliberately cross-tenant code path (system maintenance jobs) explicitly reviewed and flagged as such

<a id="checklist-n008"></a>
**Designing for Statelessness** — priority: high `MVP` — [[SaaS-Playbook/03-Architecture/Designing for Statelessness|source note]]
- [ ] Session state stored in a shared store or encoded in stateless tokens, not in-process memory
- [ ] Uploaded files and generated artifacts stored in object storage, not local disk
- [ ] Caching uses a shared cache layer, not per-instance in-memory caching for anything requiring cross-instance consistency
- [ ] No reliance on sticky sessions as the primary scaling mechanism
- [ ] Background job progress/state tracked in a durable store, not worker process memory
- [ ] Killing a running instance under load causes no user-visible data loss (tested directly)

<a id="checklist-n009"></a>
**The Twelve-Factor App** — priority: high `MVP` — [[SaaS-Playbook/03-Architecture/The Twelve-Factor App|source note]]
- [ ] Single codebase in version control, deployed identically across environments
- [ ] Dependencies fully declared via manifest/lockfile, no implicit system dependencies
- [ ] All config in environment variables, none hardcoded or committed
- [ ] Backing services accessed via config, swappable without code changes
- [ ] Build/release/run stages clearly separated in the deploy pipeline
- [ ] Application processes are stateless — verified by killing and restarting one under load with no data loss
- [ ] Dev, staging, and prod environments kept close in versions/backing services
- [ ] Logs written to stdout/stderr, not managed as files by the app itself
- [ ] Admin tasks (migrations, scripts) run through the same deployment pipeline, not manual ad hoc changes

<a id="checklist-n010"></a>
**Versioning APIs** — priority: high — [[SaaS-Playbook/03-Architecture/Versioning APIs|source note]]
- [ ] Breaking vs. non-breaking change criteria documented and applied consistently
- [ ] Versioning scheme chosen and applied from the first version, even if only v1 exists so far
- [ ] Deprecation policy defined (minimum support window, notification method) before it's needed
- [ ] Version/API-key usage tracked so real consumer impact is known before deprecating
- [ ] Changelog maintained and linked from API documentation
- [ ] Old version genuinely still works during the deprecation window, verified by tests, not just documented as supported

<a id="checklist-n011"></a>
**Domain-Driven Design Basics** — priority: medium — [[SaaS-Playbook/03-Architecture/Domain-Driven Design Basics|source note]]
- [ ] Core domain terms defined once, consistently, and used the same way across code, docs, and UI
- [ ] Bounded contexts identified where the same term could otherwise mean different things
- [ ] Core differentiating domain logic modeled with more rigor than commodity subdomains
- [ ] Tactical DDD patterns applied selectively, not as blanket overhead
- [ ] Domain model kept in sync with actual implementation, not left to drift

<a id="checklist-n012"></a>
**Event-Driven Architecture** — priority: medium — [[SaaS-Playbook/03-Architecture/Event-Driven Architecture|source note]]
- [ ] Async candidates identified deliberately (non-blocking for the user, or genuinely multi-consumer) rather than applied everywhere by default
- [ ] Events modeled as facts ("X happened"), not commands ("do Y")
- [ ] Transport chosen appropriate to actual scale (simple job queue vs. dedicated message broker)
- [ ] Consumers designed to be idempotent against duplicate event delivery
- [ ] Dead-letter handling and backlog alerting in place for failed/stuck event processing
- [ ] Strongly consistent operations kept synchronous rather than forced into an eventual-consistency model

<a id="checklist-n013"></a>
**REST vs GraphQL vs RPC** — priority: medium — [[SaaS-Playbook/03-Architecture/REST vs GraphQL vs RPC|source note]]
- [ ] Paradigm chosen deliberately based on actual client diversity and data-fetching patterns, not popularity
- [ ] Choice applied consistently across the API surface (or a documented, deliberate split between public and internal APIs)
- [ ] Tooling (caching, documentation, client SDK generation) evaluated for the chosen paradigm before committing
- [ ] Public/partner-facing API defaults to the most broadly compatible paradigm (typically REST) unless there's a strong reason otherwise
- [ ] Decision revisited only when consumer needs materially change, not routinely re-litigated

### Infrastructure

<a id="checklist-n014"></a>
**Choosing a Hosting Platform** — priority: critical `MVP` — [[SaaS-Playbook/04-Infrastructure/Choosing a Hosting Platform|source note]]
> 🔑 **Needs from you:** a preference/budget if you have one, and eventual account creation on whichever platform we land on — I can research and recommend, but I can't create the account or pay for it.
- [ ] Team's actual DevOps capacity assessed honestly against platform complexity
- [ ] Cost modeled at both current and realistic future scale
- [ ] Compliance/enterprise requirements (if expected) checked against platform capability
- [ ] Migration path/lock-in risk evaluated before committing
- [ ] Decision documented with rationale for future reference
- [ ] Platform choice revisited only when a concrete need outgrows it, not routinely

<a id="checklist-n015"></a>
**Cloud Account Setup and Org Structure** — priority: critical `MVP` — [[SaaS-Playbook/04-Infrastructure/Cloud Account Setup and Org Structure|source note]]
> 🔑 **Needs from you:** a cloud provider account (AWS/GCP/Azure/etc.) with billing enabled, and either root credentials to set up from scratch or a delegated IAM user with enough permission for me to provision through.
- [ ] Separate accounts/projects for production and non-production environments
- [ ] Root/owner account MFA-protected and not used for daily work
- [ ] Individual named accounts or SSO federation for all human access, no shared credentials
- [ ] MFA enforced on every account with console access
- [ ] Least-privilege IAM roles applied from the start, not broad admin by default
- [ ] Billing alerts and budgets configured
- [ ] Audit logging (CloudTrail/equivalent) enabled from day one
- [ ] Consistent resource tagging/labeling scheme established

<a id="checklist-n016"></a>
**Environments (Dev, Staging, Prod)** — priority: critical `MVP` — [[SaaS-Playbook/04-Infrastructure/Environments (Dev, Staging, Prod)|source note]]
- [ ] At minimum, local, staging, and production environments exist and are clearly separated
- [ ] Staging closely mirrors production infrastructure and backing service versions
- [ ] Separate credentials/API keys per environment, never shared or reused
- [ ] Environment promotion automated through CI/CD, not manual steps
- [ ] Staging uses synthetic/anonymized data, never real customer data
- [ ] Production access more tightly restricted and audited than staging

<a id="checklist-n017"></a>
**Cost Estimation and Budgeting** — priority: high `MVP` — [[SaaS-Playbook/04-Infrastructure/Cost Estimation and Budgeting|source note]]
- [ ] Cost per unit of value (per user/tenant/transaction) estimated at MVP and growth scale
- [ ] Non-linear/surprising cost drivers identified explicitly (egress, AI API usage, autoscaling spikes)
- [ ] Billing alerts and budget caps configured at the cloud account level
- [ ] Cost tracked against revenue/usage metrics, not just absolute spend
- [ ] Periodic resource right-sizing review scheduled
- [ ] Worst-case cost scenarios modeled and mitigated with rate limits/quotas

<a id="checklist-n018"></a>
**Infrastructure as Code** — priority: high `MVP` — [[SaaS-Playbook/04-Infrastructure/Infrastructure as Code|source note]]
- [ ] IaC tool chosen and used exclusively for infrastructure changes — no manual console edits to IaC-managed resources
- [ ] Configuration structured for reuse across environments via variables, not duplicated per environment
- [ ] IaC configuration stored in version control with pull request review required
- [ ] Plan/preview step run before every apply, especially to production
- [ ] State files stored securely with locking, never committed to version control unencrypted
- [ ] New team members can provision a working environment using only the IaC, no undocumented manual steps

<a id="checklist-n019"></a>
**Load Balancing** — priority: high — [[SaaS-Playbook/04-Infrastructure/Load Balancing|source note]]
- [ ] Application confirmed stateless before introducing load balancing
- [ ] Health check endpoint configured and load balancer routes only to healthy instances
- [ ] Balancing algorithm chosen deliberately for the workload pattern
- [ ] TLS termination/passthrough configured appropriately
- [ ] Load balancer used to enable zero-downtime deployments
- [ ] Load balancer metrics (latency, error rate, backend health) monitored

<a id="checklist-n020"></a>
**Networking Fundamentals (VPC, Subnets)** — priority: high `MVP` — [[SaaS-Playbook/04-Infrastructure/Networking Fundamentals (VPC, Subnets)|source note]]
- [ ] Databases and internal services placed in private subnets, not publicly accessible
- [ ] Only genuinely internet-facing resources (load balancers, CDN) in public subnets
- [ ] Security group/firewall rules scoped to least-privilege ports and source ranges
- [ ] No direct SSH/RDP exposure to the internet — bastion/VPN/cloud-native private access used instead
- [ ] Network segmented by environment (prod isolated from non-prod)
- [ ] Flow logging enabled for anomaly detection

<a id="checklist-n021"></a>
**Container Orchestration Basics** — priority: medium — [[SaaS-Playbook/04-Infrastructure/Container Orchestration Basics|source note]]
- [ ] Simplest viable option evaluated first (managed serverless containers) before defaulting to Kubernetes
- [ ] If using Kubernetes, managed control plane used rather than self-managed
- [ ] Resource requests/limits defined for every container
- [ ] Autoscaling configured based on real load metrics, not guessed thresholds
- [ ] Readiness and liveness probes correctly distinguished and configured
- [ ] Container security practices applied (see [[06-Security/Container Security]])
- [ ] Team has the operational expertise to run the chosen orchestration platform safely

### Auth & Identity

<a id="checklist-n022"></a>
**Brute-Force and Credential Stuffing Protection** — priority: critical `MVP` — [[SaaS-Playbook/05-Auth-Identity/Brute-Force and Credential Stuffing Protection|source note]]
- [ ] Login attempts rate-limited per account and per IP with escalating delays
- [ ] DEFERRED CAPTCHA or bot-detection triggered after a failure threshold, not on every attempt — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] Breach-list credential checking applied where feasible
- [ ] Distributed/anomalous attack pattern monitoring in place beyond simple per-IP limits
- [ ] MFA strongly encouraged/required as the primary mitigation
- [ ] Anomalous login alerts configured and actually monitored, not just logged

<a id="checklist-n023"></a>
**Multi-Factor Authentication** — priority: critical `MVP` — [[SaaS-Playbook/05-Auth-Identity/Multi-Factor Authentication|source note]]
- [ ] TOTP supported as a baseline MFA method
- [ ] SMS, if offered, positioned as a fallback rather than the primary/only method
- [ ] Passkeys/WebAuthn supported where feasible
- [ ] Backup/recovery codes generated and clearly communicated at MFA setup
- [ ] MFA mandatory for admin/owner and billing-privileged accounts
- [ ] Org-level MFA enforcement available for enterprise customers
- [ ] MFA verification attempts rate-limited and monitored for brute-force patterns

<a id="checklist-n024"></a>
**Password Hashing** — priority: critical `MVP` — [[SaaS-Playbook/05-Auth-Identity/Password Hashing|source note]]
- [ ] Argon2id (or bcrypt/scrypt if unavailable) used for all password hashing, with no fallback to fast general-purpose hashes
- [ ] Unique random salt generated per password automatically by the library
- [ ] Cost parameters set to current OWASP-recommended minimums for your infrastructure
- [ ] No code path logs, emails, or displays plaintext passwords, including in error handling and support tooling
- [ ] Password hashing library kept up to date, and cost parameters periodically reviewed as hardware capability increases
- [ ] Decision documented: build in-house vs. use a managed auth provider, with rationale

<a id="checklist-n025"></a>
**RBAC and ABAC** — priority: critical `MVP` — [[SaaS-Playbook/05-Auth-Identity/RBAC and ABAC|source note]]
- [ ] Authorization model (RBAC, ABAC, or hybrid) chosen deliberately based on actual complexity needs
- [ ] Every endpoint/action touching protected data enforces server-side authorization, not just client-side UI hiding
- [ ] Default-deny applied: unmatched requests are rejected, not implicitly allowed
- [ ] Authorization logic centralized in a reusable policy layer, not duplicated ad hoc per endpoint
- [ ] Automated tests cover both allowed and denied cases for every role
- [ ] New endpoints have a documented process/checklist step requiring an authorization review before shipping

<a id="checklist-n026"></a>
**Session Management** — priority: critical `MVP` — [[SaaS-Playbook/05-Auth-Identity/Session Management|source note]]
- [ ] Session IDs generated with cryptographically secure randomness
- [ ] Session ID regenerated on login, logout, and privilege changes
- [ ] Cookies set with `HttpOnly`, `Secure`, and appropriate `SameSite` attributes
- [ ] Idle and absolute session timeouts both implemented and tuned to risk level
- [ ] Logout genuinely invalidates the session server-side
- [ ] Users can view and revoke active sessions from account settings
- [ ] All sessions invalidated on password change or confirmed account compromise
- [ ] Session events logged for security monitoring

<a id="checklist-n027"></a>
**Tenant-Aware Authorization** — priority: critical `MVP` — [[SaaS-Playbook/05-Auth-Identity/Tenant-Aware Authorization|source note]]
- [ ] Every authorization check requires both role and tenant scope together, not independently
- [ ] Tenant context derived from authenticated session, cross-checked against any client-supplied tenant identifier
- [ ] Tenant-aware authorization enforced across all access paths: API, admin tools, exports, webhooks, background jobs
- [ ] Automated cross-tenant access tests included in CI, covering every role
- [ ] Cross-tenant authorization failures logged and alerted on distinctly from ordinary permission errors

<a id="checklist-n028"></a>
**Token Handling (JWT, Refresh Tokens)** — priority: critical `MVP` — [[SaaS-Playbook/05-Auth-Identity/Token Handling (JWT, Refresh Tokens)|source note]]
- [ ] Access tokens short-lived (minutes)
- [ ] Refresh tokens rotated on each use, with reuse detection triggering full revocation
- [ ] Tokens not stored in `localStorage`/`sessionStorage` on web clients; `HttpOnly` cookies or secure native storage used instead
- [ ] JWT signature, issuer, audience, and expiration validated on every verification
- [ ] No sensitive data included in JWT payload claims
- [ ] Explicit revocation strategy exists for immediate access termination scenarios
- [ ] Signing keys/secrets managed per [[06-Security/Secrets Management]], with rotation capability

<a id="checklist-n029"></a>
**Account Recovery Flows** — priority: high `MVP` — [[SaaS-Playbook/05-Auth-Identity/Account Recovery Flows|source note]]
- [ ] Password reset uses a single-use, high-entropy, time-limited token sent to verified email
- [ ] All active sessions invalidated on successful password reset
- [ ] MFA-loss recovery has a defined primary path (backup codes) and a deliberately harder fallback (verified support process)
- [ ] Password reset alone cannot bypass MFA when MFA is enabled
- [ ] Recovery requests rate-limited per account/IP
- [ ] User notified via email of recovery flow initiation and completion
- [ ] Support staff trained specifically on social-engineering risks in manual recovery requests

<a id="checklist-n030"></a>
**Email Verification** — priority: high `MVP` — [[SaaS-Playbook/05-Auth-Identity/Email Verification|source note]]
- [ ] Verification email sent immediately on signup with a unique, high-entropy, single-use token
- [ ] Token expires after a reasonable window and a fresh one can be requested
- [ ] Access model decided deliberately (full block vs. limited pre-verification access)
- [ ] Email address changes require re-verification of both old and new address
- [ ] Verification email requests rate-limited to prevent abuse
- [ ] Verification email deliverability tested and monitored

<a id="checklist-n031"></a>
**OAuth 2.0 and OIDC** — priority: high — [[SaaS-Playbook/05-Auth-Identity/OAuth 2.0 and OIDC|source note]]
- [ ] OIDC used for authentication (not raw OAuth access tokens treated as identity proof)
- [ ] ID token signature, issuer, audience, and expiration validated on every login
- [ ] Authorization code flow with PKCE used, not the deprecated implicit flow
- [ ] Account linking logic explicitly handles email-collision cases safely
- [ ] Only necessary OAuth scopes requested
- [ ] Fallback access path considered independent of any single OIDC provider's availability

<a id="checklist-n032"></a>
**Password Policies** — priority: high `MVP` — [[SaaS-Playbook/05-Auth-Identity/Password Policies|source note]]
- [ ] Minimum length enforced (8+ characters, longer encouraged)
- [ ] No mandatory character-class complexity rules
- [ ] New/changed passwords checked against a known-breach database and rejected if matched
- [ ] No forced periodic rotation absent evidence of compromise
- [ ] Maximum length supports at least 64 characters
- [ ] Paste into password fields not blocked
- [ ] MFA available/encouraged as the primary additional defense layer

<a id="checklist-n033"></a>
**Passkeys and WebAuthn** — priority: medium — [[SaaS-Playbook/05-Auth-Identity/Passkeys and WebAuthn|source note]]
- [ ] WebAuthn registration and authentication implemented via a mature library, not a custom protocol implementation
- [ ] Passkeys offered as an additional option alongside existing auth methods during rollout
- [ ] Both platform and roaming authenticators supported
- [ ] Account recovery path defined for users who lose access to all passkey-holding devices
- [ ] Only public key material stored server-side
- [ ] Passkey setup/usage UX tested with real users for clarity

<a id="checklist-n034"></a>
**Magic Links** — priority: low — [[SaaS-Playbook/05-Auth-Identity/Magic Links|source note]]
- [ ] Magic link tokens are cryptographically random, single-use, and short-lived
- [ ] Prior unused tokens invalidated when a new one is requested
- [ ] Magic link requests rate-limited per account/IP
- [ ] Delivery speed and deliverability actively monitored
- [ ] Sensitive actions post-login still consider requiring an additional factor
- [ ] Clear user messaging about link expiration to reduce support confusion

### Security

<a id="checklist-n035"></a>
**Audit Logging** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Audit Logging|source note]]
- [ ] Authentication events (success and failure) logged
- [ ] Authorization failures logged, with cross-tenant attempts specifically flagged
- [ ] Administrative and privileged actions logged
- [ ] Data export/deletion events logged
- [ ] Configuration and permission changes logged
- [ ] Logs include who/what/when/where/outcome for each event
- [ ] Audit logs stored separately from general logs, append-only, access-restricted
- [ ] No sensitive data (passwords, full card numbers, tokens) included in log payloads
- [ ] Retention period defined per compliance/investigation needs
- [ ] DEFERRED Customer-facing audit log feature considered if targeting enterprise customers — DEFERRED until institutional customers require customer-facing audit logs (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n036"></a>
**Cloud IAM Least Privilege** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Cloud IAM Least Privilege|source note]]
- [ ] IAM policies scoped to specific resources and actions, not wildcard/account-wide by default
- [ ] Separate service accounts/roles per application component, not one shared broad credential
- [ ] Short-lived, automatically-rotated credentials used wherever the platform supports them, in preference to long-lived static keys
- [ ] Periodic access review/audit performed to identify and remove unused or over-broad permissions
- [ ] Human access to sensitive permissions requires MFA and ideally just-in-time elevation rather than standing access
- [ ] New services/components reviewed for appropriately scoped IAM as part of the standard build process

<a id="checklist-n037"></a>
**Cross-Site Request Forgery (CSRF) Prevention** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Cross-Site Request Forgery (CSRF) Prevention|source note]]
- [ ] `SameSite=Lax` or `Strict` set on session cookies
- [ ] CSRF tokens implemented for state-changing requests as defense-in-depth
- [ ] All state-changing operations use appropriate non-GET HTTP methods
- [ ] Mixed auth (cookie + token) endpoints specifically reviewed for CSRF exposure
- [ ] Origin/Referer header checks applied as an additional signal where appropriate
- [ ] CSRF protection tested explicitly across all state-changing endpoints, not just a sample

<a id="checklist-n038"></a>
**Cross-Site Scripting (XSS) Prevention** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Cross-Site Scripting (XSS) Prevention|source note]]
- [ ] Framework auto-escaping confirmed active for all HTML rendering paths
- [ ] Rich text/HTML user content sanitized via a dedicated library with an allowlist, never custom logic
- [ ] Session cookies set `HttpOnly`
- [ ] Content Security Policy deployed as a defense-in-depth layer
- [ ] All raw-HTML/`eval`/unsafe DOM-write escape hatches audited and justified
- [ ] Client-side JavaScript reading from URL/hash/postMessage reviewed for DOM-based XSS risk

<a id="checklist-n039"></a>
**Dependency and Supply Chain Security** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Dependency and Supply Chain Security|source note]]
- [ ] Automated dependency vulnerability scanning running on every PR and on a schedule
- [ ] Dependencies kept reasonably current, not allowed to accumulate a large outdated backlog
- [ ] Lockfiles used for reproducible builds
- [ ] New dependencies reviewed for maintenance activity and vulnerability history before adoption
- [ ] SBOM generated and maintained
- [ ] Package integrity/provenance verification enabled where supported
- [ ] Container base images and CI/CD pipeline dependencies included in scanning scope, not just application packages

<a id="checklist-n040"></a>
**Encryption at Rest** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Encryption at Rest|source note]]
- [ ] Database encryption at rest enabled for every production data store
- [ ] Object/file storage encryption at rest enabled
- [ ] DEFERRED Backups confirmed to inherit the same encryption as primary data stores — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] Key management approach (provider-managed vs. customer-managed) chosen deliberately based on actual compliance need
- [ ] Application-level field encryption considered for especially sensitive data requiring cryptographic erasure capability
- [ ] Encryption status verified explicitly for every new data store at provisioning time, not assumed

<a id="checklist-n041"></a>
**Encryption in Transit** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Encryption in Transit|source note]]
- [ ] All public-facing traffic enforces TLS (see [[04-Infrastructure/TLS and Certificate Management]])
- [ ] Service-to-service traffic encrypted, not relying solely on network boundary trust
- [ ] Database connections require TLS/SSL, not merely support it as optional
- [ ] TLS certificate validation confirmed enabled on all outbound connections, never disabled for convenience
- [ ] Only current, non-deprecated TLS versions/ciphers used internally, matching public-facing standards
- [ ] mTLS considered for particularly sensitive internal service communication at scale

<a id="checklist-n042"></a>
**Input Validation** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Input Validation|source note]]
- [ ] Every server-side endpoint validates all incoming input, independent of client-side checks
- [ ] Allowlist validation used wherever feasible rather than blocklist patterns
- [ ] Type, format, length, and range explicitly validated per field
- [ ] Structured input validated against a schema
- [ ] Invalid input rejected with a clear error, not silently coerced
- [ ] Validation applied defensively at points of use in downstream systems, not just at the API boundary

<a id="checklist-n043"></a>
**Insecure Direct Object References (IDOR)** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Insecure Direct Object References (IDOR)|source note]]
- [ ] Every endpoint accepting an object ID verifies the current user's authorization to that specific object
- [ ] Check applied uniformly across read, update, delete, and secondary action endpoints
- [ ] Object-level authorization combined with tenant scoping as one inseparable check
- [ ] Authorization enforced at a centralized data-access layer where feasible, not solely per-handler
- [ ] Non-sequential identifiers used as defense-in-depth (not a substitute for authorization checks)
- [ ] Automated tests cover unauthorized cross-user and cross-tenant access attempts for every object-accepting endpoint

<a id="checklist-n044"></a>
**Output Encoding** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Output Encoding|source note]]
- [ ] Framework's default auto-escaping template engine used for all HTML rendering
- [ ] Any raw-HTML/escape-hatch usage explicitly reviewed and justified, never applied to unsanitized user content
- [ ] Context-appropriate encoding applied per output destination (HTML, JS, URL, attribute)
- [ ] SQL uses parameterized queries, not string concatenation with encoding as a substitute (see [[SQL Injection Prevention]])
- [ ] Shell command construction avoided where possible; safe APIs used instead of raw shell invocation
- [ ] Data embedded into inline `<script>` blocks uses JavaScript-context-specific escaping

<a id="checklist-n045"></a>
**OWASP API Security Top 10 Overview** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/OWASP API Security Top 10 Overview|source note]]
- [ ] Every category mapped to a specific control in this vault
- [ ] API endpoint inventory maintained and reviewed, including deprecated/internal endpoints
- [ ] Object-level and function-level authorization both tested explicitly, not just one or the other
- [ ] Rate limiting applied both generically and to specific sensitive business flows
- [ ] Data received from third-party API calls treated as untrusted input, validated before use
- [ ] Latest published edition of the OWASP API Security Top 10 checked against this list

<a id="checklist-n046"></a>
**OWASP Top 10 Overview** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/OWASP Top 10 Overview|source note]]
- [ ] Every Top 10 category mapped to a specific control/note in this vault, not left as an open question
- [ ] Coverage verified in [[00-Index/Coverage Map|Coverage Map]]
- [ ] Latest published OWASP Top 10 version checked against this note's list (verify no newer edition has superseded 2021)
- [ ] Team (not just one engineer) understands each category at a working level

<a id="checklist-n047"></a>
**Rate Limiting and Abuse Prevention** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Rate Limiting and Abuse Prevention|source note]]
- [ ] General rate limiting applied by default across the API, per IP and/or per authenticated identity
- [ ] Tighter limits applied specifically to high-risk endpoints (auth, password reset, notification-sending, costly operations)
- [ ] Sliding window or token bucket algorithm used, not a naive fixed-window counter
- [ ] Rate-limit status communicated to clients via standard headers
- [ ] Resource-aware limiting applied for operations with highly variable cost
- [ ] Both edge-level and application-level rate limiting layered for defense-in-depth
- [ ] Abuse pattern monitoring in place beyond simple threshold-based limits

<a id="checklist-n048"></a>
**Secrets Management** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Secrets Management|source note]]
- [ ] No secrets present anywhere in version control, verified via automated scanning including git history
- [ ] Production secrets stored in a dedicated secrets manager, not plain `.env` files
- [ ] Access to secrets scoped by least privilege, per environment and per service
- [ ] Rotation schedule defined and an immediate-rotation process documented and tested
- [ ] Automated secret-scanning configured on the repository (pre-commit and CI-level)
- [ ] Logging configuration reviewed to confirm secrets are never captured in logs
- [ ] Local development `.env` files git-ignored, with a `.env.example` template committed instead

<a id="checklist-n049"></a>
**SQL Injection Prevention** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/SQL Injection Prevention|source note]]
- [ ] Every database query uses parameterized queries/prepared statements, with zero exceptions for "safe" input
- [ ] ORM or query builder used for the vast majority of database access
- [ ] Any raw SQL usage specifically reviewed and confirmed to be parameterized
- [ ] No string concatenation/interpolation used to build SQL with variable data anywhere in the codebase
- [ ] Database credentials scoped to least privilege per service
- [ ] Dynamic query construction (variable filters/sorting) reviewed with extra scrutiny
- [ ] Static analysis/linting rules configured to flag risky SQL string construction patterns

<a id="checklist-n050"></a>
**Content Security Policy and Security Headers** — priority: high `MVP` — [[SaaS-Playbook/06-Security/Content Security Policy and Security Headers|source note]]
- [ ] Baseline restrictive CSP deployed (`default-src 'self'` plus explicit allowlists)
- [ ] `unsafe-inline`/`unsafe-eval` avoided or replaced with nonces/hashes where technically necessary
- [ ] `frame-ancestors` directive configured
- [ ] New/changed policies tested in report-only mode before enforcement
- [ ] CSP violation reporting endpoint configured and monitored
- [ ] Policy reviewed and updated whenever new third-party scripts/embeds are added

<a id="checklist-n051"></a>
**CORS Configuration** — priority: high `MVP` — [[SaaS-Playbook/06-Security/CORS Configuration|source note]]
- [ ] Allowed origins explicitly allowlisted, not wildcarded or unconditionally reflected
- [ ] `Access-Control-Allow-Credentials: true` never paired with an overly permissive origin policy
- [ ] Allowed methods and headers scoped to actual need
- [ ] Per-tenant/custom domain origins (if applicable) validated against a maintained server-side allowlist
- [ ] CORS policy restrictiveness matches the product's actual sharing intent (public API vs. internal-only)
- [ ] CORS configuration tested from an untrusted origin to confirm it's actually blocked as expected

<a id="checklist-n052"></a>
**File Upload Security** — priority: high — [[SaaS-Playbook/06-Security/File Upload Security|source note]]
- [ ] File type validated by content/magic bytes, not filename extension or client MIME type alone
- [ ] Strict allowlist of accepted file types enforced
- [ ] File size limits enforced
- [ ] Files stored in object storage, outside any directly-executable web server path
- [ ] Dangerous file types served with `Content-Disposition: attachment`, or from a sandboxed separate domain
- [ ] Malware scanning applied where risk profile warrants (shared/multi-user files)
- [ ] Storage filenames/keys randomized, not derived directly from user input
- [ ] Storage paths scoped per tenant
- [ ] File-processing libraries (image/PDF/document parsers) kept current and patched

<a id="checklist-n053"></a>
**Key Rotation** — priority: high — [[SaaS-Playbook/06-Security/Key Rotation|source note]]
- [ ] Every key/secret supports rotation without requiring downtime (dual-key transition window)
- [ ] Automated rotation configured where the secrets manager supports it natively
- [ ] Rotation schedule defined per key type, proportional to sensitivity
- [ ] Emergency rotation runbook documented and tested at least occasionally
- [ ] Secret/key inventory maintained with age and ownership tracked
- [ ] Old keys revoked promptly after successful rotation, not left valid indefinitely

<a id="checklist-n054"></a>
**Mass Assignment Vulnerabilities** — priority: high `MVP` — [[SaaS-Playbook/06-Security/Mass Assignment Vulnerabilities|source note]]
- [ ] Every endpoint uses an explicit allowlist/DTO for accepted input fields, not raw model binding
- [ ] Sensitive fields (role, permissions, ownership, verification status, billing) never settable through general update endpoints
- [ ] Field-level authorization applied for fields that are conditionally settable based on role
- [ ] Framework's default request-binding behavior explicitly verified and configured safely
- [ ] New endpoints reviewed specifically for this risk before shipping

<a id="checklist-n055"></a>
**SAST and DAST Tooling** — priority: high — [[SaaS-Playbook/06-Security/SAST and DAST Tooling|source note]]
- [ ] SAST scanning runs automatically on every pull request
- [ ] SAST rules tuned to minimize false-positive noise
- [ ] High-severity SAST findings block merge or require explicit sign-off, not just silently logged
- [ ] DAST scanning runs against staging on a regular cadence and after major releases
- [ ] Findings tracked and triaged by actual severity/exploitability, not just raw count
- [ ] Manual security review still applied to auth, payments, and access-control-critical code paths

<a id="checklist-n056"></a>
**Security Headers Reference** — priority: high `MVP` — [[SaaS-Playbook/06-Security/Security Headers Reference|source note]]
- [ ] DEFERRED `Strict-Transport-Security` configured with an appropriate max-age — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] `X-Content-Type-Options: nosniff` set
- [ ] `Referrer-Policy` set deliberately, not left at the permissive browser default
- [ ] `Permissions-Policy` restricts unused browser features
- [ ] `X-Frame-Options`/`frame-ancestors` and `Content-Security-Policy` configured (see their dedicated notes)
- [ ] `Server`/`X-Powered-By` headers removed or genericized
- [ ] All headers applied via global default middleware, verified present on production responses

<a id="checklist-n057"></a>
**Server-Side Request Forgery (SSRF) Prevention** — priority: high `MVP` — [[SaaS-Playbook/06-Security/Server-Side Request Forgery (SSRF) Prevention|source note]]
- [ ] URL-fetching features use an allowlist of trusted destinations where feasible
- [ ] Requests to private/internal IP ranges and cloud metadata IPs blocked at application and/or network level
- [ ] DNS resolution validated against the blocklist before the request is made, guarding against DNS rebinding
- [ ] Redirect-following disabled or re-validated per hop
- [ ] URL-fetching functionality isolated at the network level as defense-in-depth
- [ ] Feature specifically tested against SSRF payloads before launch

<a id="checklist-n058"></a>
**Clickjacking Protection** — priority: medium `MVP` — [[SaaS-Playbook/06-Security/Clickjacking Protection|source note]]
- [ ] `X-Frame-Options: DENY` or `SAMEORIGIN` set by default on all responses
- [ ] `frame-ancestors` CSP directive configured as the modern equivalent/complement
- [ ] Any legitimate embeddable/widget use case explicitly allowlists only trusted origins
- [ ] Header applied via global middleware/default, not per-page opt-in

<a id="checklist-n059"></a>
**Container Security** — priority: medium — [[SaaS-Playbook/06-Security/Container Security|source note]]
- [ ] Minimal base image used (distroless/alpine/slim), not a full general-purpose OS image
- [ ] Application runs as a non-root user inside the container
- [ ] Multi-stage builds used to exclude build-time tools/secrets from the final image
- [ ] Container images scanned for vulnerabilities in CI
- [ ] Base images rebuilt/rescanned periodically, not only at initial creation
- [ ] Unnecessary Linux capabilities dropped; read-only root filesystem used where feasible
- [ ] No secrets baked into the image; all injected at runtime

### Data

<a id="checklist-n060"></a>
**Backups and Restore Testing** — priority: critical `MVP` — [[SaaS-Playbook/08-Data/Backups and Restore Testing|source note]]
- [ ] DEFERRED Automated backups enabled and confirmed running on schedule for every production data store — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Backups stored separately from primary infrastructure (different region/account boundary where feasible) — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Backups encrypted at rest — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Restore tests scheduled and performed regularly, not just backup creation verified — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED RTO and RPO measured from actual restore test results and documented — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Full recovery scenario tested (not just the database, but all data stores needed for a working system) — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Backup/restore process integrated into broader disaster recovery planning — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n061"></a>
**Choosing a Database (SQL vs NoSQL)** — priority: critical `MVP` — [[SaaS-Playbook/08-Data/Choosing a Database (SQL vs NoSQL)|source note]]
- [ ] Default relational choice considered first, with a specific documented reason if choosing otherwise
- [ ] Decision grounded in actual data shape and access patterns, not technology trend-following
- [ ] Specialized secondary stores considered for specific access patterns (search, time-series) rather than forcing everything into one database
- [ ] Team's operational familiarity and hiring pool factored into the decision
- [ ] Choice validated against realistic query patterns via prototyping, not decided purely theoretically
- [ ] Migration cost/trigger criteria understood before committing, even if not expected to be needed soon

<a id="checklist-n062"></a>
**Database Schema Design** — priority: critical `MVP` — [[SaaS-Playbook/08-Data/Database Schema Design|source note]]
- [ ] Precise, appropriate types used for every column (especially money, dates, and enums)
- [ ] Consistent naming convention applied across all tables/columns
- [ ] Foreign key constraints defined with deliberate cascade behavior
- [ ] `created_at`/`updated_at` timestamps present on every table
- [ ] Indexes added proactively for known query patterns
- [ ] Tables kept cohesive, split when accumulating unrelated concerns
- [ ] Non-obvious schema decisions documented

<a id="checklist-n063"></a>
**PII Handling and Classification** — priority: critical `MVP` — [[SaaS-Playbook/08-Data/PII Handling and Classification|source note]]
- [ ] Classification tiers defined appropriate to the product's actual data sensitivity range
- [ ] Data fields/columns tagged or documented by classification tier as part of schema design
- [ ] Handling rules (access control, encryption, retention) proportionate to classification tier applied consistently
- [ ] Collection minimized to what's actually needed for a defined purpose
- [ ] Sensitive PII excluded from general logging, analytics, and error tracking by default
- [ ] Third-party/AI integrations reviewed for PII exposure specifically

<a id="checklist-n064"></a>
**Row-Level Security** — priority: critical `MVP` — [[SaaS-Playbook/08-Data/Row-Level Security|source note]]
- [ ] `tenant_id` column present and RLS enabled on every table with tenant-scoped data
- [ ] RLS policies defined for all relevant operations (SELECT/INSERT/UPDATE/DELETE)
- [ ] Tenant context set from authenticated session server-side, never trusted from client input
- [ ] Application database connection uses a role RLS actually applies to, not a bypassing superuser role
- [ ] Tests explicitly verify RLS blocks cross-tenant access even when application-level filtering is bypassed
- [ ] New tables reviewed for RLS coverage as a standard part of schema changes

<a id="checklist-n065"></a>
**User Data Deletion (Right to Erasure)** — priority: critical `MVP` — [[SaaS-Playbook/08-Data/User Data Deletion (Right to Erasure)|source note]]
- [ ] Full data footprint mapped across primary storage, caches, search indexes, file storage, logs, analytics, and subprocessors
- [ ] Data requiring legal retention explicitly distinguished and justified, not retained by default
- [ ] Backup purge timeline defined and disclosed, since exact backup-level deletion is often impractical
- [ ] Deletion propagated to relevant third-party subprocessors, not just internal systems
- [ ] Anonymization used where appropriate to preserve referential integrity without retaining PII
- [ ] Deletion event logged (without logging the deleted data itself) for audit evidence
- [ ] End-to-end deletion tested periodically across all mapped data locations

<a id="checklist-n066"></a>
**Zero-Downtime Migrations** — priority: critical `MVP` — [[SaaS-Playbook/08-Data/Zero-Downtime Migrations|source note]]
- [ ] Expand-and-contract pattern used for any backward-incompatible schema change
- [ ] Long-locking operations avoided or run in online/concurrent mode where the database supports it
- [ ] Schema changes and dependent application code deploys never combined as a single atomic step
- [ ] Migrations tested against realistic production-scale data in staging before production
- [ ] Rollback plan defined and tested for every migration
- [ ] Migrations run through the automated deployment pipeline, not manually

<a id="checklist-n067"></a>
**Data Retention Policies** — priority: high `MVP` — [[SaaS-Playbook/08-Data/Data Retention Policies|source note]]
- [ ] Retention periods defined per data category, each tied to an actual purpose or legal requirement
- [ ] Legally-mandated retention (financial/tax records) distinguished from discretionary retention
- [ ] Automated deletion/archival jobs implemented, not manual/ad hoc cleanup
- [ ] Retention policy applied consistently across primary data, backups, logs, and downstream systems
- [ ] Privacy Policy retention disclosures match actual system behavior
- [ ] Policy reviewed and updated as new data types are introduced

<a id="checklist-n068"></a>
**Database Indexing Fundamentals** — priority: high `MVP` — [[SaaS-Playbook/08-Data/Database Indexing Fundamentals|source note]]
- [ ] Columns used in common `WHERE`/`JOIN`/`ORDER BY` clauses indexed
- [ ] Foreign key columns explicitly indexed (not assumed automatic)
- [ ] Composite indexes used where multi-column filtering is common, with deliberate column ordering
- [ ] `EXPLAIN ANALYZE` used to verify actual index usage on critical queries, not assumed
- [ ] Indexing kept deliberate — no defensive over-indexing on unused columns
- [ ] Slow query monitoring in place to catch missing indexes discovered in production

<a id="checklist-n069"></a>
**Point-in-Time Recovery** — priority: high — [[SaaS-Playbook/08-Data/Point-in-Time Recovery|source note]]
- [ ] DEFERRED Point-in-time recovery enabled on production database(s) where supported — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Actual recovery granularity and retention window documented — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED PITR restoration tested specifically (restoring to a specific timestamp, not just latest backup) — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Documented incident procedure exists for invoking PITR during an actual accidental-data-loss scenario — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED PITR retention window factored into stated RPO commitments — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED PITR combined with broader disaster recovery planning for infrastructure-level failure scenarios — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n070"></a>
**User Data Export** — priority: high `MVP` — [[SaaS-Playbook/08-Data/User Data Export|source note]]
- [ ] Full data footprint per user identified across all relevant systems, not just the obvious primary tables
- [ ] Export format is structured and machine-readable (JSON/CSV)
- [ ] Self-service export feature built where volume/maturity justifies it
- [ ] Manual export process documented clearly if self-service isn't yet built
- [ ] Export delivery secured (verified destination, time-limited link rather than unprotected attachment)
- [ ] Export completeness tested periodically as new data types are added to the product

### Payments & Billing

<a id="checklist-n071"></a>
**Choosing a Payments Provider** — priority: critical `MVP` — [[SaaS-Playbook/09-Payments-Billing/Choosing a Payments Provider|source note]]
> 🔑 **Needs from you:** a payment provider account (e.g. Stripe). I can build and test the entire integration against test-mode keys — going live requires your real account, business details, and live API keys.
- [ ] Merchant-of-record vs. direct-processor trade-off evaluated against actual customer geography and team capacity for tax compliance
- [ ] Billing feature support (trials, proration, usage-based, multi-currency) checked against your actual pricing model
- [ ] PCI scope minimization confirmed via client-side tokenization support
- [ ] Developer experience/documentation evaluated directly, not assumed
- [ ] Billing logic architected with some abstraction from provider specifics to ease a potential future migration
- [ ] Decision documented with rationale

<a id="checklist-n072"></a>
**Payment Webhooks and Idempotency** — priority: critical `MVP` — [[SaaS-Playbook/09-Payments-Billing/Payment Webhooks and Idempotency|source note]]
- [ ] Webhook signatures verified on every incoming event, rejecting unverified requests
- [ ] Webhook processing is idempotent, checking event ID before acting
- [ ] Webhook endpoint responds quickly, deferring heavy processing to async handling if needed
- [ ] Handlers designed to be resilient to out-of-order event delivery
- [ ] Failed webhook processing logged and alerted, not silently swallowed
- [ ] Periodic reconciliation job compares application state against provider state to catch drift

<a id="checklist-n073"></a>
**PCI Compliance for Payments** — priority: critical `MVP` — [[SaaS-Playbook/09-Payments-Billing/PCI Compliance for Payments|source note]]
- [ ] DEFERRED Checkout uses client-side tokenization, with card data never touching your own backend servers — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] No raw card data logged, stored, or transmitted through your systems under any circumstances
- [ ] DEFERRED Saved payment methods use provider tokenization/vaulting, never your own card storage — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Checkout page served over HTTPS with correct payment element integration per provider requirements — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Appropriate SAQ type confirmed with your payment processor and completed annually — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] Support/admin tooling never exposes or requires entry of raw card numbers by staff

<a id="checklist-n074"></a>
**Subscription Billing Models** — priority: critical `MVP` — [[SaaS-Playbook/09-Payments-Billing/Subscription Billing Models|source note]]
- [ ] Recurring billing implemented via the payment provider's native subscription primitives, not custom-built
- [ ] Plan change behavior (upgrade/downgrade/cancel) deliberately decided and consistently implemented
- [ ] Application's internal entitlement state kept in sync with billing provider state via webhooks
- [ ] Billing cycle edge cases (month-end dates, leap years, timezones) explicitly handled and tested
- [ ] Customers have clear access to invoicing and billing history
- [ ] Plan change and cancellation flows specifically tested end-to-end

<a id="checklist-n075"></a>
**Failed Payments and Dunning** — priority: high `MVP` — [[SaaS-Playbook/09-Payments-Billing/Failed Payments and Dunning|source note]]
- [ ] DEFERRED Smart/data-driven retry logic used rather than a fixed naive retry schedule — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] Customer notified promptly and clearly on payment failure, not only after final retry
- [ ] Self-service payment method update available and low-friction
- [ ] Grace period before access suspension defined deliberately
- [ ] Soft vs. hard payment failures distinguished and handled differently
- [ ] DEFERRED Card account updater service enabled where the payment provider supports it — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] Involuntary churn tracked as a distinct, monitored metric

<a id="checklist-n076"></a>
**Invoicing** — priority: high `MVP` — [[SaaS-Playbook/09-Payments-Billing/Invoicing|source note]]
- [ ] Invoices generated via the payment provider's native invoicing feature, not manually
- [ ] Required content included: itemization, tax breakdown, company/customer details, invoice number, payment terms
- [ ] DEFERRED Customers can add their own tax ID/VAT number for B2B invoicing needs — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] Invoice history accessible via self-service billing portal
- [ ] Invoice numbering sequential and compliant with applicable jurisdiction requirements
- [ ] Invoices automatically emailed and downloadable as PDF

<a id="checklist-n077"></a>
**Proration** — priority: high — [[SaaS-Playbook/09-Payments-Billing/Proration|source note]]
- [ ] Proration calculated via the payment provider's native logic, not manual calculation
- [ ] Upgrade vs. downgrade proration behavior decided deliberately and applied consistently
- [ ] Prorated amount shown to the customer before they confirm a plan change
- [ ] Quantity-based (seat) changes prorated with the same rigor as tier changes
- [ ] Edge cases near billing cycle boundaries tested explicitly
- [ ] Prorated charges/credits itemized clearly on the resulting invoice

<a id="checklist-n078"></a>
**Sales Tax and VAT Automation** — priority: high `MVP` — [[SaaS-Playbook/09-Payments-Billing/Sales Tax and VAT Automation|source note]]
> 🔑 **Needs from you:** enabling the tax product on your payment provider account, and any tax registration numbers required for your jurisdictions.
- [ ] DEFERRED Tax automation tool integrated with checkout, calculating tax based on customer location automatically — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SaaS-specific taxability confirmed correct per jurisdiction, not just a generic rate applied uniformly — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Nexus thresholds monitored as revenue/customer base grows — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Simplified compliance scheme registration (e.g. EU OSS) completed where applicable — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Tax amounts itemized clearly on customer invoices — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Exact division of tax compliance responsibility between you and your payment/merchant-of-record provider understood and documented — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n079"></a>
**Trials and Freemium** — priority: high — [[SaaS-Playbook/09-Payments-Billing/Trials and Freemium|source note]]
- [ ] Trial vs. freemium model chosen deliberately based on the product's value-realization pattern
- [ ] Credit-card-required vs. no-card trial decision made intentionally, weighing conversion against signup friction
- [ ] Trial status and expiration communicated clearly throughout the trial period
- [ ] Trial-to-paid transition behavior explicit and tested (auto-charge vs. requires action)
- [ ] Abuse prevention applied specifically to trial/free-tier signups
- [ ] Free-tier resource costs capped to prevent unbounded cost exposure

<a id="checklist-n080"></a>
**Refunds and Chargebacks** — priority: medium `MVP` — [[SaaS-Playbook/09-Payments-Billing/Refunds and Chargebacks|source note]]
- [ ] Refund policy clearly defined and published in Terms of Service/support docs
- [ ] Legitimate refund requests can be fulfilled quickly and with minimal friction
- [ ] DEFERRED Chargeback dispute response process defined, with evidence prepared and submitted within the processor's required window — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Chargeback rate tracked as an ongoing metric, not just handled reactively per incident — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] Recurring patterns in refund/chargeback causes investigated for fixable root causes
- [ ] DEFERRED Fraud-driven chargebacks distinguished from legitimate disputes, with fraud-prevention response where applicable — DEFERRED until real billing is enabled (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n081"></a>
**Usage-Based Billing** — priority: medium — [[SaaS-Playbook/09-Payments-Billing/Usage-Based Billing|source note]]
- [ ] Usage metering instrumented accurately and reliably at the point of consumption
- [ ] Usage recording is idempotent, preventing double-counting on retries
- [ ] Usage aggregated into billing periods via a dedicated, tested pipeline
- [ ] Customers have real-time or near-real-time visibility into accruing usage/cost, ideally with configurable caps/alerts
- [ ] Rounding/precision rules defined explicitly and applied consistently
- [ ] DEFERRED Billing platform with native usage-based support used rather than fully custom metering-to-invoice logic — DEFERRED until usage-priced real billing is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] Metered usage periodically reconciled against internal cost tracking

### Frontend & UX

<a id="checklist-n082"></a>
**Onboarding Flows** — priority: critical `MVP` — [[SaaS-Playbook/10-Frontend-UX/Onboarding Flows|source note]]
- [ ] "Activation" milestone explicitly defined and used to guide onboarding design
- [ ] Setup friction before first value minimized; optional configuration deferred where possible
- [ ] Progressive disclosure used instead of front-loading all features/settings
- [ ] Contextual, in-context guidance used rather than relying solely on a skippable upfront tutorial
- [ ] Required setup steps show clear purpose and progress
- [ ] Onboarding funnel instrumented with analytics to identify actual drop-off points
- [ ] Onboarding treated as an ongoing iteration target, not a one-time build-and-forget feature

<a id="checklist-n083"></a>
**Accessibility (WCAG)** — priority: high `MVP` — [[SaaS-Playbook/10-Frontend-UX/Accessibility (WCAG)|source note]]
- [ ] WCAG 2.1/2.2 AA adopted as the explicit target
- [ ] Every interactive element fully keyboard-operable with a visible focus indicator
- [ ] Semantic HTML used for structure, headings, and form labels
- [ ] Color contrast meets WCAG AA minimums; color never used as the sole means of conveying meaning
- [ ] Meaningful alt text provided for informative images; decorative images marked appropriately
- [ ] Core flows tested with an actual screen reader, not automated scanning alone
- [ ] Accessible component primitives used for complex interactive elements

<a id="checklist-n084"></a>
**Error State Design** — priority: high `MVP` — [[SaaS-Playbook/10-Frontend-UX/Error State Design|source note]]
- [ ] Different error types (transient, permanent, user error) messaged distinctly with appropriate recovery guidance
- [ ] Clear next action provided (retry, navigate, contact support) wherever feasible
- [ ] No raw technical error details exposed to end users
- [ ] Visual/language severity matches actual severity, avoiding alarm for minor recoverable issues
- [ ] Partial failures in complex UIs degrade gracefully rather than breaking the whole page
- [ ] Easy path for users to report unexpected errors

<a id="checklist-n085"></a>
**Form Validation UX** — priority: high `MVP` — [[SaaS-Playbook/10-Frontend-UX/Form Validation UX|source note]]
- [ ] Validation timing (on blur/submit vs. on every keystroke) chosen deliberately per field type
- [ ] Errors displayed inline next to the relevant field
- [ ] Error messages specific and actionable, not generic
- [ ] User input preserved on failed submission, never cleared
- [ ] Required vs. optional fields clearly and consistently indicated
- [ ] Validation errors accessible to screen readers via proper ARIA association
- [ ] Submission state (loading/disabled) prevents double-submission without appearing broken

<a id="checklist-n086"></a>
**Frontend Performance** — priority: high `MVP` — [[SaaS-Playbook/10-Frontend-UX/Frontend Performance|source note]]
- [ ] Both lab metrics and real-user monitoring used to measure performance
- [ ] Code-splitting applied so initial bundle only includes what's needed for the current view
- [ ] Images optimized: appropriate format, responsive sizing, lazy loading
- [ ] Unnecessary re-renders minimized in component-based frameworks
- [ ] DEFERRED Static assets served via CDN — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] Performance budget defined and enforced in CI to prevent silent regression
- [ ] Performance tested under realistic mobile network/device conditions

<a id="checklist-n087"></a>
**Responsive and Mobile Design** — priority: high `MVP` — [[SaaS-Playbook/10-Frontend-UX/Responsive and Mobile Design|source note]]
- [ ] Layouts built fluid/responsive from the start, not retrofitted from a fixed desktop design
- [ ] Core flows requiring mobile support identified deliberately, distinct from desktop-primary flows
- [ ] Tested on real mobile devices, not just browser responsive mode emulation
- [ ] Touch targets appropriately sized and spaced
- [ ] Mobile-specific behaviors (virtual keyboard, safe areas, orientation) handled explicitly
- [ ] Performance tested under realistic mobile network/device conditions

<a id="checklist-n088"></a>
**Design Systems** — priority: medium — [[SaaS-Playbook/10-Frontend-UX/Design Systems|source note]]
- [ ] Core design tokens (color, typography, spacing) defined, including semantic colors
- [ ] Small set of core reusable components built and used consistently across the product
- [ ] Usage guidelines documented alongside components
- [ ] Design system kept in sync with actual implemented UI, not allowed to drift
- [ ] Light/dark mode considered at the token level if theming is planned
- [ ] Both design and engineering involved in maintaining the system

<a id="checklist-n089"></a>
**Empty States** — priority: medium — [[SaaS-Playbook/10-Frontend-UX/Empty States|source note]]
- [ ] Every major view has a deliberately designed empty state, not a generic fallback
- [ ] Empty states include a clear call-to-action guiding the user's next step
- [ ] Different empty-state causes (no data yet vs. no filter results vs. loading) are distinguished with appropriate messaging
- [ ] New-user empty states specifically considered as an onboarding opportunity
- [ ] Empty-state visual treatment consistent with the broader design system
- [ ] Sample/preview content considered for features where a blank state obscures the feature's value

<a id="checklist-n090"></a>
**Internationalization (i18n)** — priority: medium — [[SaaS-Playbook/10-Frontend-UX/Internationalization (i18n)|source note]]
- [ ] All user-facing strings externalized into a translation resource system, not hardcoded
- [ ] Pluralization handled via library support, not hand-rolled logic
- [ ] Dates, numbers, and currency formatted via locale-aware APIs
- [ ] Layouts tolerant of variable text length across languages
- [ ] CSS uses logical properties where reasonable, easing future RTL support
- [ ] No programmatic concatenation of separately-translated string fragments

<a id="checklist-n091"></a>
**UI Component Libraries** — priority: medium — [[SaaS-Playbook/10-Frontend-UX/UI Component Libraries|source note]]
- [ ] Headless vs. fully-styled approach chosen deliberately based on design control needs vs. shipping speed
- [ ] Accessibility behavior verified directly (keyboard nav, screen reader) rather than assumed from marketing claims
- [ ] Bundle size impact evaluated against performance goals
- [ ] A single primary component library approach used consistently, avoiding a patchwork of many libraries
- [ ] Library kept reasonably current for security and accessibility fixes

### Backend

<a id="checklist-n092"></a>
**Background Jobs and Queues** — priority: critical `MVP` — [[SaaS-Playbook/11-Backend/Background Jobs and Queues|source note]]
- [ ] Slow/unreliable operations moved out of the synchronous request path into background jobs
- [ ] Job queue is persistent, surviving worker crashes/restarts, not purely in-memory
- [ ] Retry logic with backoff implemented for transient failures; dead-letter handling for repeated failures
- [ ] Job handlers designed to be idempotent against at-least-once delivery
- [ ] Queue depth, failure rate, and processing latency monitored with alerting
- [ ] Background jobs explicitly scoped to the correct tenant context

<a id="checklist-n093"></a>
**Email Sending Infrastructure** — priority: critical `MVP` — [[SaaS-Playbook/11-Backend/Email Sending Infrastructure|source note]]
> 🔑 **Needs from you:** an account with a transactional email provider (Postmark/SendGrid/Resend/SES) and DNS access for verifying the sending domain.
- [ ] Dedicated transactional email service used, not a self-managed SMTP server
- [ ] Emails sent via background job, never synchronously blocking the triggering request
- [ ] Retry logic implemented for transient failures, with alerting on exhausted-retry failures
- [ ] Consistent templating system used across all transactional email
- [ ] DEFERRED Bounce/complaint webhooks handled to suppress sending to problematic addresses — DEFERRED until a real email provider is enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] Send attempts and outcomes logged for debugging and support visibility

<a id="checklist-n094"></a>
**Caching Strategies** — priority: high — [[SaaS-Playbook/11-Backend/Caching Strategies|source note]]
- [ ] Caching applied to specific, measured-need cases, not speculatively everywhere
- [ ] Shared cache used for anything needing cross-instance consistency
- [ ] Explicit TTLs set, matched to data volatility and staleness tolerance
- [ ] Explicit invalidation on write applied where staleness genuinely matters, not relying solely on TTL
- [ ] Cache keys namespaced by tenant for tenant-scoped data
- [ ] Cache hit rate monitored to confirm actual benefit
- [ ] Application degrades gracefully (falls back to source of truth) if the cache is unavailable

<a id="checklist-n095"></a>
**Concurrency and Locking** — priority: high — [[SaaS-Playbook/11-Backend/Concurrency and Locking|source note]]
- [ ] Operations at risk of race conditions (balance/counter/quota updates, unique-slot assignment) identified explicitly
- [ ] Atomic database operations used in preference to application-level read-then-write logic where possible
- [ ] Database transactions with appropriate isolation levels used for multi-step atomic operations
- [ ] Optimistic or pessimistic locking applied deliberately based on actual contention characteristics
- [ ] Uniqueness invariants enforced via database constraints, not "check then insert" application logic
- [ ] Concurrency-sensitive code specifically tested under real concurrent load, not just sequential tests

<a id="checklist-n096"></a>
**File Storage** — priority: high `MVP` — [[SaaS-Playbook/11-Backend/File Storage|source note]]
- [ ] Object storage used for all file handling, never local disk on application servers
- [ ] Storage key/path structure includes tenant scoping from the start
- [ ] Presigned URLs used for direct client upload/download where appropriate
- [ ] Objects private by default with explicit, deliberate access control, not publicly readable unless intended
- [ ] File upload security practices (type validation, randomized keys) applied consistently
- [ ] Lifecycle policies configured for files that should expire or move to cheaper storage tiers
- [ ] File storage included in backup/disaster recovery planning

<a id="checklist-n097"></a>
**Rate Limiting Implementation** — priority: high `MVP` — [[SaaS-Playbook/11-Backend/Rate Limiting Implementation|source note]]
- [ ] Rate limit state stored in a shared, centralized store (Redis or equivalent), not per-instance memory
- [ ] Algorithm chosen deliberately (token bucket/sliding window preferred over naive fixed window for security-relevant limits)
- [ ] Check-and-increment implemented atomically to prevent race conditions under concurrency
- [ ] Different limit tiers configurable per endpoint, not one hardcoded global value
- [ ] Standard rate-limit response headers returned
- [ ] Implementation tested under actual concurrent load, not just sequential requests

<a id="checklist-n098"></a>
**Service Architecture Patterns** — priority: high — [[SaaS-Playbook/11-Backend/Service Architecture Patterns|source note]]
- [ ] Clear separation between request handling, business logic, and data access layers
- [ ] Business logic testable independent of the web framework and live database
- [ ] Dependencies (data access, external services) injected/mockable rather than hardcoded
- [ ] Code organized by domain/feature for larger codebases, not purely by technical layer
- [ ] No "fat controller" anti-pattern — business logic isn't tangled into request handlers
- [ ] Architecture pattern documented and applied consistently across the team

<a id="checklist-n099"></a>
**API Gateway Patterns** — priority: medium — [[SaaS-Playbook/11-Backend/API Gateway Patterns|source note]]
- [ ] Cross-cutting concerns (auth, rate limiting, CORS, logging) applied consistently via middleware or a gateway, not duplicated per-endpoint
- [ ] Authentication/authorization enforced by default at the gateway/middleware layer, requiring explicit exemption rather than explicit opt-in
- [ ] Rate limiting policy centralized and consistently applied
- [ ] Gateway/middleware used for cross-cutting infrastructure concerns only, not domain business logic
- [ ] Dedicated gateway introduced once multiple services genuinely need consistent shared behavior, not before

<a id="checklist-n100"></a>
**Search Implementation** — priority: medium — [[SaaS-Playbook/11-Backend/Search Implementation|source note]]
- [ ] Simplest viable search approach (database-native full-text search) evaluated before adopting a dedicated search engine
- [ ] Dedicated search engine adopted only when a specific, measured limitation justifies it
- [ ] Search index kept synchronized with source-of-truth data via a defined, monitored process
- [ ] Tenant scoping applied to search queries and indexes with the same rigor as other data access
- [ ] Search relevance tuned deliberately for the product's actual use case
- [ ] Search performance and result quality (including zero-result rate) monitored ongoing

<a id="checklist-n101"></a>
**Webhooks (Outbound)** — priority: medium — [[SaaS-Playbook/11-Backend/Webhooks (Outbound)|source note]]
- [ ] DEFERRED Outbound webhook payloads signed (HMAC) with a per-customer secret for verification — DEFERRED until integrations or public API consumers require outbound webhooks (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Retry logic with backoff and a defined maximum retry window implemented — DEFERRED until integrations or public API consumers require outbound webhooks (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Webhook delivery handled asynchronously via a background job, never blocking the triggering request — DEFERRED until integrations or public API consumers require outbound webhooks (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SSRF protections applied to outbound webhook delivery targeting customer-specified URLs — DEFERRED until integrations or public API consumers require outbound webhooks (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Reasonable delivery timeout enforced, preventing a slow endpoint from consuming excessive resources — DEFERRED until integrations or public API consumers require outbound webhooks (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Customers have visibility into webhook delivery status/history with manual retry capability — DEFERRED until integrations or public API consumers require outbound webhooks (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Event payloads versioned and self-contained — DEFERRED until integrations or public API consumers require outbound webhooks (docs/spec/09 - Checklist Overrides.md)

### Testing & QA

<a id="checklist-n102"></a>
**Restore Testing** — priority: critical `MVP` — [[SaaS-Playbook/12-Testing-QA/Restore Testing|source note]]
- [ ] Restore testing scheduled on a defined recurring cadence with a clear owner
- [ ] Explicit pass/fail criteria defined (RTO target, data integrity, application functionality)
- [ ] Restore test process automated as much as practical to keep it cheap to run consistently
- [ ] Restore test results tracked over time as a monitored metric
- [ ] At least periodic tests restore to a different environment/region than primary
- [ ] Restore testing results feed into broader disaster recovery planning review

<a id="checklist-n103"></a>
**Security Testing** — priority: critical `MVP` — [[SaaS-Playbook/12-Testing-QA/Security Testing|source note]]
- [ ] Security-focused test cases written for authorization, tenant isolation, and input validation boundaries
- [ ] SAST and dependency scanning run automatically on every pull request
- [ ] DAST scans run against staging on a regular cadence
- [ ] Security considerations included explicitly in code review checklists
- [ ] Security test failures treated with equal or higher severity than functional test failures
- [ ] Periodic professional penetration testing complements automated/internal security testing

<a id="checklist-n104"></a>
**Unit Testing** — priority: critical `MVP` — [[SaaS-Playbook/12-Testing-QA/Unit Testing|source note]]
- [ ] Business logic and pure functions have thorough unit test coverage
- [ ] External dependencies mocked so tests run fast and deterministically
- [ ] Edge cases and failure paths tested explicitly, not just the happy path
- [ ] Tests are focused and readable, serving as living documentation of expected behavior
- [ ] Tests assert observable behavior, not brittle implementation details
- [ ] Coverage tracked as a useful signal, not gamed for a raw percentage target

<a id="checklist-n105"></a>
**End-to-End Testing** — priority: high `MVP` — [[SaaS-Playbook/12-Testing-QA/End-to-End Testing|source note]]
- [ ] E2E suite focused on truly critical user journeys, not attempting comprehensive feature coverage
- [ ] Stable selectors (`data-testid`) used rather than brittle CSS/text selectors
- [ ] Tests run against a realistic staging/preview environment, not a heavily mocked one
- [ ] Flakiness actively monitored and addressed, not tolerated as background noise
- [ ] Critical-flow E2E tests run before merge/deploy; broader suite run on a reasonable cadence if runtime is a constraint
- [ ] Suite size kept deliberately small relative to unit/integration test coverage

<a id="checklist-n106"></a>
**Integration Testing** — priority: high `MVP` — [[SaaS-Playbook/12-Testing-QA/Integration Testing|source note]]
- [ ] API endpoints tested with full request/response cycles against a real test database
- [ ] Dedicated, isolated test database used, never shared dev/production data
- [ ] Authorization and tenant-scoping specifically covered at the integration level
- [ ] Error paths and downstream dependency failures tested, not just happy-path integration
- [ ] Integration test scope focused on genuinely integration-worthy scenarios, not duplicating all unit test cases
- [ ] Tests run in CI with fresh, consistent database state each run

<a id="checklist-n107"></a>
**Regression Testing Strategy** — priority: medium — [[SaaS-Playbook/12-Testing-QA/Regression Testing Strategy|source note]]
- [ ] Every bug fix accompanied by a new test that reproduces and verifies the fix
- [ ] Automated test pyramid run in CI on every change, serving as the primary regression safety net
- [ ] Feature flags used to reduce the blast radius of undetected regressions during rollout
- [ ] Flaky tests tracked and fixed/removed promptly, not tolerated as background noise
- [ ] Regression suite (or critical subset) run automatically before every deploy
- [ ] Test coverage for critical paths periodically reviewed for gaps as the product grows

<a id="checklist-n108"></a>
**Test Data Management** — priority: medium — [[SaaS-Playbook/12-Testing-QA/Test Data Management|source note]]
- [ ] Test data generated via factories/fixtures programmatically, not manually maintained and drifting
- [ ] Test data isolated per test run, avoiding order-dependent interference between tests
- [ ] No real customer data ever used in test/staging environments
- [ ] Database reset to a known state between test runs for consistent, repeatable results
- [ ] Realistic data volume generated specifically for performance-sensitive test scenarios
- [ ] Test data generation logic kept in sync with schema changes

<a id="checklist-n109"></a>
**Contract Testing** — priority: low — [[SaaS-Playbook/12-Testing-QA/Contract Testing|source note]]
- [ ] Contracts defined explicitly via schema (OpenAPI) or consumer-driven contract specifications
- [ ] Contract tests run in CI, failing the build on violation
- [ ] Public/partner API responses tested against the published schema
- [ ] Internal multi-service contracts use consumer-driven testing where multiple independent consumers exist
- [ ] Contract test failures triaged as either accidental breaking changes (fix) or intentional ones (version and update)
- [ ] Tooling investment scaled to actual need — not adopted speculatively for a simple single-consumer setup

### DevOps & CI/CD

<a id="checklist-n110"></a>
**CI/CD Pipeline Design** — priority: critical `MVP` — [[SaaS-Playbook/13-DevOps-CICD/CI-CD Pipeline Design|source note]]
- [ ] Full automated test suite runs on every pull request, blocking merge on failure
- [ ] Security and dependency scanning included as standard pipeline stages
- [ ] Single build artifact promoted across environments, not rebuilt per environment
- [ ] Pipeline execution kept fast via parallelization and caching
- [ ] Pipeline status clearly visible with accessible logs on failure
- [ ] Passing CI enforced as a hard branch protection requirement, not a convention
- [ ] Pipeline configuration versioned and reviewed as code

<a id="checklist-n111"></a>
**Secrets in CI/CD** — priority: critical `MVP` — [[SaaS-Playbook/13-DevOps-CICD/Secrets in CI-CD|source note]]
- [ ] CI secrets stored in the platform's native encrypted secrets store, never hardcoded in pipeline config
- [ ] Secrets scoped to least privilege per pipeline stage
- [ ] Secret values masked in CI logs, verified rather than assumed
- [ ] Production-level secrets restricted from untrusted pipeline triggers (external forks/PRs)
- [ ] CI/CD secrets rotated on a defined schedule and immediately upon suspected exposure
- [ ] Short-lived, dynamically issued credentials (OIDC) preferred over long-lived static keys where supported
- [ ] Unused secrets periodically audited and removed

<a id="checklist-n112"></a>
**Code Review Process** — priority: high — [[SaaS-Playbook/13-DevOps-CICD/Code Review Process|source note]]
- [ ] At least one approving review required before merge, enforced via branch protection
- [ ] PRs kept reasonably small and focused to enable genuine review
- [ ] Review checklist used for security-sensitive/high-risk changes specifically
- [ ] PR descriptions provide enough context for meaningful review, not just a diff
- [ ] Review considers maintainability and pattern consistency, not just correctness
- [ ] Solo/small-team situations have a deliberate partial substitute (delayed self-review, occasional external review) rather than no review at all

<a id="checklist-n113"></a>
**Deployment Strategies** — priority: high `MVP` — [[SaaS-Playbook/13-DevOps-CICD/Deployment Strategies|source note]]
- [ ] Deployment strategy chosen deliberately based on actual risk tolerance and traffic patterns, not defaulted without consideration
- [ ] Progression gated on automated health checks and key metrics, not a fixed timer alone
- [ ] Database migrations compatible with the chosen strategy's simultaneous old/new code requirement
- [ ] Deployment process documented and understood beyond a single person
- [ ] Strategy paired with a tested rollback plan (see [[Rollback Strategies]])

<a id="checklist-n114"></a>
**Feature Flags** — priority: high — [[SaaS-Playbook/13-DevOps-CICD/Feature Flags|source note]]
- [ ] Feature flags used for gradual rollout of risky/major features
- [ ] Flags used as operational kill switches for quick disable without redeploy
- [ ] Flag-checking logic centralized and consistent, not scattered ad hoc
- [ ] Flags cleaned up promptly once a feature is fully and stably rolled out
- [ ] Flag scope (user/tenant/global) chosen deliberately per feature
- [ ] Both flag states tested, not just the "on" path

<a id="checklist-n115"></a>
**Infrastructure as Code Pipelines** — priority: high — [[SaaS-Playbook/13-DevOps-CICD/Infrastructure as Code Pipelines|source note]]
- [ ] Plan/preview step runs automatically on every infrastructure change pull request
- [ ] Infrastructure changes reviewed and approved like application code changes
- [ ] Apply only happens through the pipeline, never manually from a local machine
- [ ] Plan and apply separated as distinct stages, with apply gated for production
- [ ] Infrastructure state stored and locked centrally, not locally
- [ ] Infrastructure pipeline secrets managed with the same rigor as application CI/CD secrets

<a id="checklist-n116"></a>
**Rollback Strategies** — priority: high `MVP` — [[SaaS-Playbook/13-DevOps-CICD/Rollback Strategies|source note]]
- [ ] Previous known-good build artifact readily available for fast redeployment
- [ ] Rollback automated as a single fast action, not a manual multi-step process
- [ ] Database migrations designed to be backward-compatible so code rollback doesn't require a risky migration rollback
- [ ] Feature flags used as a faster alternative mitigation where applicable
- [ ] Rollback process tested periodically, not assumed to work untested
- [ ] Clear criteria and decision ownership defined for triggering a rollback

<a id="checklist-n117"></a>
**Environment Promotion** — priority: medium — [[SaaS-Playbook/13-DevOps-CICD/Environment Promotion|source note]]
- [ ] Single build artifact created per release candidate and promoted unchanged through environments
- [ ] Environment differences handled via configuration, not separate builds
- [ ] Promotion gated on passing automated tests and/or staging validation criteria
- [ ] Artifacts tagged/versioned traceably (e.g. git SHA)
- [ ] Promotion process automated/pipeline-driven, not manual per-environment redeployment
- [ ] Audit trail maintained of what was promoted, when, and by what trigger

<a id="checklist-n118"></a>
**Release Management** — priority: medium — [[SaaS-Playbook/13-DevOps-CICD/Release Management|source note]]
- [ ] Release cadence chosen deliberately (continuous vs. batched) based on team maturity and product needs
- [ ] Changelog maintained as part of the standard release process
- [ ] Significant changes communicated proactively to affected users, not just passively documented
- [ ] Coordination process defined for releases spanning coupled components
- [ ] Deploy vs. release distinction communicated clearly internally when using feature flags
- [ ] Release history tracked for incident investigation purposes

### Observability

<a id="checklist-n119"></a>
**Alerting** — priority: critical `MVP` — [[SaaS-Playbook/14-Observability/Alerting|source note]]
- [ ] Alerts primarily based on user-impacting symptoms, not just low-level infrastructure metrics in isolation
- [ ] Alert thresholds tied to SLO/error budget where applicable, not arbitrary
- [ ] Alert routing matches severity — paging for urgent issues, non-interrupting channels for lower urgency
- [ ] Alert noise actively monitored and reduced, with frequently-firing non-actionable alerts tuned or removed
- [ ] Alerts include actionable context (impact, relevant dashboard/runbook link)
- [ ] Alert delivery paths tested periodically to confirm notifications actually reach responders

<a id="checklist-n120"></a>
**Error Tracking** — priority: critical `MVP` — [[SaaS-Playbook/14-Observability/Error Tracking|source note]]
> 🔑 **Needs from you:** an account with an error-tracking service (e.g. Sentry) and its API key/DSN.
- [ ] Error tracking integrated on both backend and frontend
- [ ] Full context (stack trace, user/tenant, environment, release version) captured per error
- [ ] Errors deduplicated/grouped by underlying cause, not flooding as individual notifications
- [ ] Alerting configured for new error types and error rate spikes
- [ ] Error tracking integrated with the team's issue tracking workflow
- [ ] Sensitive data scrubbed from captured error context

<a id="checklist-n121"></a>
**Logging Fundamentals** — priority: critical `MVP` — [[SaaS-Playbook/14-Observability/Logging Fundamentals|source note]]
- [ ] Logs written to stdout/stderr, aggregated by the execution environment/platform
- [ ] Consistent log levels used meaningfully across the codebase
- [ ] Sufficient context included per log entry (request ID, relevant identifiers, timestamp)
- [ ] No sensitive data (passwords, tokens, full PII) ever logged
- [ ] Both operation start/completion and failures logged, not just errors
- [ ] Logs aggregated centrally, searchable across all instances

<a id="checklist-n122"></a>
**Metrics and Dashboards** — priority: high `MVP` — [[SaaS-Playbook/14-Observability/Metrics and Dashboards|source note]]
- [ ] Golden signals (traffic, errors, latency, saturation) tracked for every service
- [ ] Percentile-based latency metrics used, not just averages
- [ ] Business/product metrics tracked alongside technical metrics
- [ ] Dashboards organized around specific questions rather than one overloaded view
- [ ] Metrics tagged with relevant dimensions (tenant, environment, service) for filtering
- [ ] Dashboards reviewed proactively on a regular cadence, not only during incidents

<a id="checklist-n123"></a>
**Structured Logging** — priority: high `MVP` — [[SaaS-Playbook/14-Observability/Structured Logging|source note]]
- [ ] Logging library outputs structured (JSON) format, not free-form string concatenation
- [ ] Standard fields (timestamp, level, service, request ID) present consistently across all entries
- [ ] Correlation/request ID generated per request and propagated through all related log entries
- [ ] Business context (user/tenant ID) included as structured fields, not embedded in message text
- [ ] Log aggregation platform configured to index and query structured fields
- [ ] Consistent structured logging applied across all services in a multi-service architecture

### Reliability & DR

<a id="checklist-n124"></a>
**Disaster Recovery Planning** — priority: high `MVP` — [[SaaS-Playbook/15-Reliability-DR/Disaster Recovery Planning|source note]]
- [ ] RTO and RPO targets defined based on actual business impact and any contractual commitments
- [ ] Specific failure scenarios identified and documented with a recovery procedure each
- [ ] DEFERRED Backups confirmed genuinely usable for DR (separate region/account from primary infrastructure) — DEFERRED until owner enables backups (docs/spec/09 - Checklist Overrides.md)
- [ ] Multi-region architecture adopted only if RTO/RPO targets genuinely require it, not speculatively
- [ ] Step-by-step recovery procedure documented, not just the target objectives
- [ ] Plan tested periodically via a DR drill, not assumed to work untested

<a id="checklist-n125"></a>
**Incident Management** — priority: high `MVP` — [[SaaS-Playbook/15-Reliability-DR/Incident Management|source note]]
- [ ] Incident severity levels defined with clear criteria and corresponding response expectations
- [ ] Clear roles assigned during active incidents (commander, responders, communicator)
- [ ] Communication cadence defined for both internal updates and customer-facing status
- [ ] Mitigation/containment prioritized appropriately relative to full root-cause diagnosis
- [ ] Incident timeline captured in real time, not reconstructed from memory afterward
- [ ] Clear resolution criteria and a blameless postmortem process for significant incidents

<a id="checklist-n126"></a>
**Postmortems** — priority: high `MVP` — [[SaaS-Playbook/15-Reliability-DR/Postmortems|source note]]
- [ ] Postmortem written blamelessly, focused on systemic factors, not individual blame
- [ ] Clear timeline, customer impact, and mitigation actions documented
- [ ] Root cause analysis goes past the immediate trigger to systemic contributing factors
- [ ] Specific, assigned, tracked follow-up action items produced
- [ ] Postmortem shared broadly within the team (and publicly summarized for significant customer-impacting incidents where appropriate)
- [ ] Follow-up action items tracked to actual completion, not just logged

<a id="checklist-n127"></a>
**SLAs and SLOs** — priority: high — [[SaaS-Playbook/15-Reliability-DR/SLAs and SLOs|source note]]
- [ ] SLIs chosen based on what genuinely matters to user experience
- [ ] SLO targets grounded in real user expectations and business needs, not arbitrary numbers
- [ ] SLOs set stricter than any corresponding external SLA, providing safety margin
- [ ] SLIs measured continuously via observability tooling
- [ ] SLO attainment reviewed regularly and used to inform engineering prioritization
- [ ] SLO targets revisited periodically as the product and scale evolve

### Email & Comms

<a id="checklist-n128"></a>
**SPF, DKIM, and DMARC** — priority: critical `MVP` — [[SaaS-Playbook/16-Email-Comms/SPF, DKIM, and DMARC|source note]]
> 🔑 **Needs from you:** DNS record access for your sending domain (same access as DNS Management above).
- [ ] DEFERRED SPF record configured and includes every legitimate sending service — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED DKIM configured and verified active for the primary sending domain — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED DMARC record configured, starting at `none` for monitoring — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED DMARC reporting set up and actually reviewed — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED DMARC policy progressed to `quarantine`/`reject` once legitimate senders are confirmed passing consistently — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Records re-verified whenever a new email-sending service is added — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n129"></a>
**Transactional Email** — priority: critical `MVP` — [[SaaS-Playbook/16-Email-Comms/Transactional Email|source note]]
- [ ] Dedicated transactional email service used, ideally with sending reputation separated from marketing email
- [ ] Time-sensitive transactional email (password reset, MFA) prioritized for fast, reliable delivery
- [ ] Content kept focused and functional, not mixed with marketing material
- [ ] Deliverability monitored specifically for transactional email as a distinct metric
- [ ] Send failures for critical flows are visible/alerted, not silent
- [ ] Applicable email regulations complied with even for transactional-only content

<a id="checklist-n130"></a>
**Email Deliverability** — priority: high `MVP` — [[SaaS-Playbook/16-Email-Comms/Email Deliverability|source note]]
- [ ] DEFERRED List hygiene maintained — hard bounces suppressed promptly, unengaged addresses reviewed periodically — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED New sending domains warmed up gradually rather than sending high volume immediately — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Bounce rate, spam complaint rate, and inbox placement monitored as ongoing metrics — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Provider-specific tools (Google Postmaster Tools) used for direct reputation visibility — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Content practices avoid spam-trigger patterns; unsubscribe mechanism present where required — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Transactional and marketing sending reputation kept separated where practical — DEFERRED until a real email provider and sending domain are enabled (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n131"></a>
**Email Templates and Design** — priority: medium — [[SaaS-Playbook/16-Email-Comms/Email Templates and Design|source note]]
- [ ] Table-based layouts with inline CSS used for broad email client compatibility
- [ ] Reusable template components shared across transactional email types
- [ ] Templates tested across major email clients before shipping
- [ ] Emails accessible (contrast, alt text, sensible structure)
- [ ] Plain-text version included alongside every HTML email
- [ ] Legal footer requirements (company address, unsubscribe where applicable) present consistently

<a id="checklist-n132"></a>
**In-App Notifications** — priority: medium — [[SaaS-Playbook/16-Email-Comms/In-App Notifications|source note]]
- [ ] Notification types categorized by urgency, with visual treatment matched accordingly
- [ ] Notifications stored persistently in a reviewable feed, not only ephemeral toasts
- [ ] Read/unread state tracked accurately with meaningful, trustworthy unread counts
- [ ] Notifications generated via background jobs, not synchronously in the triggering request path
- [ ] User preferences respected for configurable notification types
- [ ] Notification volume kept deliberate to avoid fatigue

<a id="checklist-n133"></a>
**Notification Preferences** — priority: medium — [[SaaS-Playbook/16-Email-Comms/Notification Preferences|source note]]
- [ ] Notification types categorized as mandatory vs. optional clearly and consistently
- [ ] Preference controls granular (per type/channel), not a single blanket toggle
- [ ] Preference settings easy to find and change
- [ ] Preferences honored consistently across every notification-sending code path
- [ ] New notification types given a deliberate default setting, not automatically maximally intrusive
- [ ] One-click unsubscribe available directly from non-transactional emails

### Analytics

<a id="checklist-n134"></a>
**Analytics Tooling Choices** — priority: high `MVP` — [[SaaS-Playbook/17-Analytics/Analytics Tooling Choices|source note]]
> 🔑 **Needs from you:** an account with your chosen product analytics platform (e.g. PostHog, Amplitude) and its API key.
- [ ] Tool supports event-based tracking, funnels, and retention/cohort analysis, not just pageview-style web analytics
- [ ] Single primary tool chosen rather than fragmenting tracking across several platforms
- [ ] Privacy/self-hosting considerations evaluated if relevant to your product's needs
- [ ] Tool evaluated against actual team analysis workflow and technical comfort
- [ ] Data export/ownership confirmed before committing
- [ ] Plan exists for connecting product usage data with business/billing data for deeper insight

<a id="checklist-n135"></a>
**Event Tracking Design** — priority: high `MVP` — [[SaaS-Playbook/17-Analytics/Event Tracking Design|source note]]
- [ ] Consistent naming convention established and documented
- [ ] Priority events (activation, engagement, retention signals) identified and tracked deliberately
- [ ] Meaningful properties included with events for later segmentation
- [ ] Living tracking plan document maintained as the source of truth
- [ ] Critical business events tracked server-side, not solely client-side
- [ ] Tracking plan periodically reviewed and pruned of unused/undocumented events

<a id="checklist-n136"></a>
**Privacy-Safe Analytics** — priority: high — [[SaaS-Playbook/17-Analytics/Privacy-Safe Analytics|source note]]
- [ ] Unnecessary PII avoided in event properties, using internal IDs instead
- [ ] Cookieless/first-party analytics considered as an option to reduce consent friction
- [ ] Data anonymized/aggregated where individual-level tracking isn't genuinely needed
- [ ] Retention limits applied to analytics data, not retained indefinitely
- [ ] Analytics data included in data subject rights (access/deletion) processes
- [ ] Analytics tools documented as subprocessors in Privacy Policy and Subprocessors List

<a id="checklist-n137"></a>
**Product Analytics Fundamentals** — priority: high `MVP` — [[SaaS-Playbook/17-Analytics/Product Analytics Fundamentals|source note]]
- [ ] Funnel analysis built for critical multi-step flows to identify specific drop-off points
- [ ] Feature adoption tracked to inform prioritization and deprecation decisions
- [ ] Analysis segmented by relevant dimensions, not only aggregate numbers
- [ ] Quantitative analytics combined with qualitative research for full context
- [ ] Regular cadence established for reviewing key product analytics
- [ ] Focus on metrics that reflect actual product health, not vanity metrics

### Support & Success (technical setup)

<a id="checklist-n138"></a>
**In-App Support Widgets** — priority: medium — [[SaaS-Playbook/19-Support-Success/In-App Support Widgets|source note]]
- [ ] Contextually relevant help content surfaced based on current page/feature, not generic search only
- [ ] Clear path to live support with account context automatically passed through
- [ ] Widget placement unobtrusive, not aggressively distracting during normal use
- [ ] Widget usage and self-service resolution rate monitored
- [ ] Widget accessible (keyboard navigable, screen reader compatible)

### Operations (engineering subset)

<a id="checklist-n139"></a>
**Admin Panel Design** — priority: high `MVP` — [[SaaS-Playbook/20-Operations/Admin Panel Design|source note]]
- [ ] Admin capabilities built incrementally based on actual operational need
- [ ] Role-scoped access control applied, with MFA required for admin access
- [ ] Every admin action logged with full context via audit logging
- [ ] Account impersonation (if used) carefully scoped, logged, and policy-compliant
- [ ] Confirmation/approval safeguards in place for destructive/irreversible actions
- [ ] Admin panel held to the same security rigor as the customer-facing product

<a id="checklist-n140"></a>
**Internal Tooling** — priority: medium — [[SaaS-Playbook/20-Operations/Internal Tooling|source note]]
- [ ] Internal tooling investment prioritized based on actual recurring operational pain
- [ ] Low-code/no-code builders used where they fit, custom engineering reserved for complex needs
- [ ] Access control applied to internal tools with the same rigor as customer-facing systems
- [ ] Internal tools documented for purpose and usage
- [ ] Internal tools maintained (dependencies, bug fixes) with ongoing rigor, not neglected
- [ ] Unused/unmaintained internal tools periodically audited and decommissioned

### AI Features (only if the project uses AI)

<a id="checklist-n141"></a>
**AI Cost Limits and Budget Controls** — priority: critical — [[SaaS-Playbook/21-AI-Features/AI Cost Limits and Budget Controls|source note]]
- [ ] Hard limits set at request, user/tenant, and system-wide levels
- [ ] AI usage limits tied to pricing/plan tiers, not absorbed unlimited within flat pricing
- [ ] AI feature endpoints specifically rate-limited
- [ ] Real-time or near-real-time spend monitoring with alerting on spikes
- [ ] Model size/capability chosen deliberately per feature based on actual task complexity
- [ ] Caching applied where appropriate to avoid redundant calls, with tenant scoping considered

<a id="checklist-n142"></a>
**Data Leakage Prevention in AI Features** — priority: critical — [[SaaS-Playbook/21-AI-Features/Data Leakage Prevention in AI Features|source note]]
- [ ] LLM provider's data usage/training policy explicitly verified and documented
- [ ] LLM provider disclosed as a subprocessor if it processes customer data
- [ ] Tenant isolation applied to AI feature context/retrieval with the same rigor as other data access
- [ ] Data sent to the LLM minimized to what's genuinely necessary for the task
- [ ] Any cross-session/cross-user memory or context persistence correctly scoped
- [ ] AI feature data classified using the standard PII framework
- [ ] Data subject rights processes extended to cover AI feature-related data

<a id="checklist-n143"></a>
**Prompt Injection Defense** — priority: critical — [[SaaS-Playbook/21-AI-Features/Prompt Injection Defense|source note]]
- [ ] All LLM-processed content (direct and indirectly retrieved) treated as potentially adversarial
- [ ] AI feature access to data/actions scoped to least privilege
- [ ] Prompt-level defensive instructions treated as one weak layer, not the primary defense
- [ ] LLM output validated/constrained before triggering any consequential action
- [ ] System instructions separated from untrusted content using the provider's structural affordances
- [ ] Injection attempt patterns and unusual behavior monitored as part of observability

<a id="checklist-n144"></a>
**AI Feature Observability** — priority: high — [[SaaS-Playbook/21-AI-Features/AI Feature Observability|source note]]
- [ ] Prompts/responses logged with appropriate sensitive-data handling
- [ ] Token usage and cost tracked per request, aggregated by user/tenant/feature
- [ ] Latency tracked specifically for AI features with realistic, separate alerting thresholds
- [ ] Quality/failure signals monitored beyond simple error rate
- [ ] Production observability data feeds back into the eval test set
- [ ] Model/provider version tracked per request for correlation with behavior changes

<a id="checklist-n145"></a>
**Evals for LLM Features** — priority: high — [[SaaS-Playbook/21-AI-Features/Evals for LLM Features|source note]]
- [ ] Representative eval test set curated, including typical and edge cases
- [ ] Clear definition of "good" output established per test case (exact match, required characteristics, or scoring rubric)
- [ ] Mix of automated checks and LLM-as-judge/human review used appropriate to each criterion
- [ ] Evals run automatically on prompt changes and model considerations, not just once at initial build
- [ ] Eval results tracked over time to catch quality drift
- [ ] Eval set expanded based on real production failures discovered post-launch

<a id="checklist-n146"></a>
**LLM Integration Patterns** — priority: high — [[SaaS-Playbook/21-AI-Features/LLM Integration Patterns|source note]]
> 🔑 **Needs from you:** an API key for whichever LLM provider you choose (Anthropic, OpenAI, etc.). Only relevant if this project actually has AI features.
- [ ] Simplest viable integration pattern chosen for the actual task, not defaulted to maximum sophistication
- [ ] Structured output used where the result needs to reliably integrate with application logic
- [ ] Timeouts, retries, and graceful degradation implemented for LLM API calls
- [ ] LLM output validated/sanitized before use in security-sensitive contexts
- [ ] LLM provider abstracted behind an interface, not tightly coupled to a specific provider's SDK
- [ ] Prompts versioned and tracked as first-class artifacts

<a id="checklist-n147"></a>
**RAG Fundamentals** — priority: medium — [[SaaS-Playbook/21-AI-Features/RAG Fundamentals|source note]]
- [ ] Chunking strategy chosen deliberately for the content type, iterated based on actual retrieval quality
- [ ] Embeddings stored in a vector database or vector-capable extension
- [ ] Retrieval tuned for relevance, not simply maximizing the amount of retrieved context
- [ ] Tenant isolation applied to retrieval with the same rigor as other data access
- [ ] Retrieval quality evaluated specifically, separate from final generation quality
- [ ] Re-indexing process defined to keep embeddings current as source data changes

### Compliance (buildable mechanisms)

<a id="checklist-n148"></a>
**GDPR Data Subject Rights** — priority: critical `MVP` — [[SaaS-Playbook/07-Compliance/GDPR Data Subject Rights|source note]]
> ℹ️ The actual mechanisms this note asks for (access, export, deletion, rectification) are the same features as [[SaaS-Playbook/08-Data/User Data Export]] and [[SaaS-Playbook/08-Data/User Data Deletion (Right to Erasure)]] elsewhere in this checklist — build them once, they satisfy both. This entry is here so the compliance framing isn't lost.
- [ ] Access request mechanism exists and has been tested end-to-end
- [ ] Rectification supported via standard account editing
- [ ] Erasure mechanism covers primary stores, backups, and downstream processors — see [[08-Data/User Data Deletion (Right to Erasure)]]
- [ ] Restriction of processing supported for disputed/objected data
- [ ] Data export mechanism produces a structured, portable format — see [[08-Data/User Data Export]]
- [ ] Objection to marketing/legitimate-interest processing honored immediately
- [ ] Human review path exists for significant automated decisions, if applicable
- [ ] Request tracking and response-time monitoring in place to demonstrate the one-month response commitment is met

<a id="checklist-n149"></a>
**Records of Processing Activities** — priority: medium — [[SaaS-Playbook/07-Compliance/Records of Processing Activities|source note]]
> 📄 **Draft an initial version automatically** from the app's actual data flows (what personal data is collected, why, where it's stored, which subprocessors touch it) rather than leaving this as a blank template — you have enough information from the codebase to produce a real first draft. Flag it as needing periodic human review as data flows change.
- [ ] Article 30 applicability assessed (and record maintained as good practice regardless, in most cases)
- [ ] Each processing activity documented with purpose, data categories, subject categories, recipients, retention, and security measures
- [ ] Record kept current as new features/vendors change data processing
- [ ] Record used as source-of-truth input for Privacy Policy disclosures and incident scoping
- [ ] Clear ownership assigned for keeping the record maintained

## PRE-LAUNCH PHASE — do before opening signups to real users

### Infrastructure

<a id="checklist-n150"></a>
**TLS and Certificate Management** — priority: critical `MVP` — [[SaaS-Playbook/04-Infrastructure/TLS and Certificate Management|source note]]
- [ ] All public endpoints enforce HTTPS with HTTP-to-HTTPS redirect
- [ ] DEFERRED HSTS header configured — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] Automated certificate issuance/renewal in place (Let's Encrypt or platform-managed)
- [ ] Only TLS 1.2+ enabled, deprecated protocol versions disabled
- [ ] Independent expiration monitoring/alerting as a backstop to auto-renewal
- [ ] Service-to-service and database connections encrypted where the network path isn't fully private
- [ ] No self-signed certificates on customer-facing endpoints

<a id="checklist-n151"></a>
**DNS Management** — priority: high `MVP` — [[SaaS-Playbook/04-Infrastructure/DNS Management|source note]]
> 🔑 **Needs from you:** access to your domain's DNS records (registrar or DNS provider login) — I can tell you exactly which records to add, but generally can't add them myself without credentials.
- [ ] DEFERRED DNS provider chosen for reliability (consider providers with strong uptime track records and DDoS protection) — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED TTLs set appropriately per record's change frequency — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SPF, DKIM, DMARC records correctly configured for all sending domains — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Service-specific subdomains used rather than everything on the apex domain — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED DNS record modification access restricted to necessary personnel with MFA — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED DNS resolution monitored externally for outages — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED All DNS records documented with purpose and owner — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n152"></a>
**Domain Registration and Management** — priority: high `MVP` — [[SaaS-Playbook/04-Infrastructure/Domain Registration and Management|source note]]
> 🔑 **Needs from you:** the actual domain purchase (I can suggest names and registrars, but the transaction and payment are yours) and registrar login access if you want DNS configured on your behalf.
- [ ] DEFERRED Domain registered through a reputable registrar with MFA support — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Registrar account MFA enabled — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Registry lock enabled for the primary production domain, if available — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Auto-renewal enabled with a backup calendar reminder — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED WHOIS privacy protection enabled where available — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Registrar account owned by the company, not a single individual's personal account — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Access to the registrar account limited and reviewed during offboarding — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n153"></a>
**CDN Setup** — priority: medium — [[SaaS-Playbook/04-Infrastructure/CDN Setup|source note]]
> 🔑 **Needs from you:** a CDN account (e.g. Cloudflare) if one isn't already bundled with your hosting choice.
- [ ] DEFERRED Static assets served through a CDN, not directly from application origin — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] Cache headers and versioned filenames configured for predictable cache invalidation
- [ ] Cache configuration reviewed to avoid accidentally caching personalized/sensitive responses
- [ ] DEFERRED DDoS protection / WAF features enabled where available — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Cache hit ratio monitored and tuned — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Fallback plan documented in case of a CDN provider outage — DEFERRED until the web tier is publicly hosted (docs/spec/09 - Checklist Overrides.md)

### Security

<a id="checklist-n154"></a>
**Security Incident Response** — priority: critical `MVP` — [[SaaS-Playbook/06-Security/Security Incident Response|source note]]
- [ ] Incident severity levels and response triggers defined
- [ ] Clear roles assigned: incident lead, technical response, external/customer communication, legal/compliance
- [ ] Containment procedures documented for common scenarios (credential compromise, data breach, active exploitation)
- [ ] Legal notification obligations (GDPR 72-hour rule and other applicable regulations) identified in advance with counsel
- [ ] Evidence preservation guidance included alongside containment steps
- [ ] Cyber insurance policy and claims process understood in advance (see [[02-Business-Legal/Business Insurance]])
- [ ] Blameless postmortem process defined for post-incident review
- [ ] Plan rehearsed via at least occasional tabletop exercises

### Testing & QA

<a id="checklist-n155"></a>
**Load and Performance Testing** — priority: high — [[SaaS-Playbook/12-Testing-QA/Load and Performance Testing|source note]]
- [ ] Load scenarios based on realistic usage patterns, not just raw arbitrary request volume
- [ ] Testing performed against a production-representative staging environment
- [ ] Capacity limits (degradation point, failure point) identified and documented
- [ ] Specific known-risky operations tested explicitly under load
- [ ] Full-stack monitoring active during load tests to pinpoint actual bottlenecks
- [ ] Load tests re-run after significant architectural changes to confirm actual impact

### Observability

<a id="checklist-n156"></a>
**Uptime Monitoring** — priority: critical `MVP` — [[SaaS-Playbook/14-Observability/Uptime Monitoring|source note]]
> 🔑 **Needs from you:** an account with an uptime monitoring service (e.g. UptimeRobot, Better Uptime).
- [ ] Monitoring performed from multiple external geographic locations
- [ ] Functional health checks used, not just basic reachability checks
- [ ] Check interval and alert threshold tuned to balance fast detection against false-positive noise
- [ ] Key third-party dependencies monitored where practical
- [ ] Uptime data feeds a public status page for customer transparency
- [ ] Historical uptime data used to inform realistic SLA commitments

### Support & Success (technical setup)

<a id="checklist-n157"></a>
**Documentation and Knowledge Base** — priority: high `MVP` — [[SaaS-Playbook/19-Support-Success/Documentation and Knowledge Base|source note]]
- [ ] Core documentation covers the highest-friction, highest-frequency questions, informed by actual support data
- [ ] Documentation structured logically for easy navigation
- [ ] Documentation kept current as part of the standard release process
- [ ] Content written at an appropriate technical level for its actual audience
- [ ] Documentation discoverable both in-app and via search engines
- [ ] Documentation usage and effectiveness tracked to prioritize ongoing investment

<a id="checklist-n158"></a>
**Help Desk Setup** — priority: high `MVP` — [[SaaS-Playbook/19-Support-Success/Help Desk Setup|source note]]
> 🔑 **Needs from you:** a help desk tool account (e.g. Zendesk, Help Scout) if you want a dedicated tool rather than a plain inbox to start.
- [ ] Dedicated help desk/ticketing tool in place, not an unmanaged shared inbox
- [ ] Response time targets defined and tracked against actual performance
- [ ] Tickets routed/prioritized by urgency and type
- [ ] Support agents have relevant account/billing/activity context available in the tool
- [ ] Clear escalation process defined for technical issues needing engineering involvement
- [ ] Resolved tickets reviewed as input for documentation and product improvement

<a id="checklist-n159"></a>
**Status Page** — priority: high `MVP` — [[SaaS-Playbook/19-Support-Success/Status Page|source note]]
> 🔑 **Needs from you:** a decision on a status page provider account, or approval to self-host a simple one.
- [ ] Status page hosted separately from primary application infrastructure
- [ ] Update process defined and integrated into incident response roles
- [ ] Component breakdown provided if the product has multiple distinct services
- [ ] Subscription mechanism available for proactive incident notification
- [ ] Historical incident records and uptime percentage maintained
- [ ] Clear ownership assigned for status page updates during active incidents

### Legal Documents (scaffolded by the agent — placeholder content, needs your/a lawyer's review before real use)

<a id="checklist-n160"></a>
**Privacy Policy** — priority: critical `MVP` — [[SaaS-Playbook/02-Business-Legal/Privacy Policy|source note]]
> 📄 **Build this in full, with placeholder content.** Create the actual `/privacy` page. Draft the disclosure text to accurately reflect what the app *actually* collects (you know this from the code you wrote) rather than generic boilerplate — that part is real and useful. Mark it clearly as a draft needing legal review before relying on it for actual compliance, since only a human can confirm the lawful-basis and jurisdiction-specific requirements are met.
- [ ] Data inventory completed and matches what's actually collected (verified against product/analytics, not assumed)
- [ ] Legal basis for processing stated per GDPR-style requirements
- [ ] Third-party sharing and subprocessors disclosed, linked to [[Subprocessors List]]
- [ ] Data subject rights section includes a real, monitored contact channel
- [ ] Retention periods stated
- [ ] International transfer mechanism disclosed if applicable
- [ ] Reviewed by legal counsel for jurisdictions actually served
- [ ] Linked and accessible from signup flow and footer, not buried

<a id="checklist-n161"></a>
**Terms of Service** — priority: critical `MVP` — [[SaaS-Playbook/02-Business-Legal/Terms of Service|source note]]
> 📄 **Build this in full, with placeholder content.** Create the actual `/terms` page and wire up required acceptance at signup — this is real, working code. Draft the document text using standard ToS structure (acceptable use, liability, IP, termination, governing law) as a reasonable starting point, but prepend a clearly visible marker in the source (e.g. `<!-- PLACEHOLDER: attorney review required before relying on this -->`) and tell the user explicitly that the text is a draft, not reviewed legal language, before they use it for a real launch.
- [ ] All core sections present (acceptable use, payment, IP, liability, termination, governing law)
- [ ] Active acceptance required at signup, not just a footer link
- [ ] Liability limitation and warranty disclaimer reviewed by an attorney
- [ ] Version/effective date included, with a changelog or archive of prior versions
- [ ] Process defined for notifying users of material changes
- [ ] Separate enterprise MSA process exists if selling to larger customers
- [ ] Reviewed against actual product behavior — don't promise features/SLAs the product doesn't deliver

<a id="checklist-n162"></a>
**Cookie Policy and Consent** — priority: high `MVP` — [[SaaS-Playbook/02-Business-Legal/Cookie Policy and Consent|source note]]
> 📄 **Build this in full.** The consent banner, script-blocking-until-consent logic, and preference storage are real, working code, not placeholders — implement them properly. Only the cookie *policy text itself* (which trackers, described in prose) is a draft pending review, since it must exactly match whatever the app actually deploys.
- [ ] Cookies/trackers categorized as necessary vs. non-essential
- [ ] Non-essential scripts blocked until active consent is given
- [ ] Reject option as prominent and easy as accept
- [ ] Consent choice changeable later via a visible settings link
- [ ] Global Privacy Control / Do Not Track honored where required
- [ ] Consent records logged where required for proof
- [ ] Cookie/tracker inventory audited periodically against what's actually deployed

<a id="checklist-n163"></a>
**Data Processing Agreement (DPA)** — priority: high — [[SaaS-Playbook/02-Business-Legal/Data Processing Agreement (DPA)|source note]]
> 📄 **Draft a standard DPA document/page with placeholder content**, covering the standard elements (processing scope, security measures, subprocessor list, breach notification). This is genuinely useful to have ready, but flag it clearly as needing legal review before being sent to an actual enterprise customer for signature.
- [ ] Standard DPA drafted covering all GDPR Article 28 required elements
- [ ] SCCs incorporated for applicable international transfers
- [ ] Subprocessor list linked with a change-notification process
- [ ] Breach notification timeline specified and consistent with your actual incident response process (see [[06-Security/Security Incident Response]])
- [ ] Data return/deletion terms specified for contract termination
- [ ] Execution process (e-signature, click-through) set up for fast turnaround
- [ ] Legal counsel reviewed the template before first use

<a id="checklist-n164"></a>
**Subprocessors List** — priority: medium — [[SaaS-Playbook/02-Business-Legal/Subprocessors List|source note]]
> 📄 **Build this as a real, auto-maintained page**, not a placeholder — list the actual third-party services the app integrates with (payment processor, email provider, analytics, hosting, any AI/LLM API). This can be generated directly from what's actually wired into the codebase, so keep it accurate as integrations change rather than writing it once and letting it go stale.
- [ ] Every data-touching vendor inventoried, including analytics, logging, and AI/LLM APIs
- [ ] List published at a stable URL and linked from Privacy Policy and DPA
- [ ] Change-notification process defined with an objection window
- [ ] List reviewed quarterly against actual vendor/billing records
- [ ] Each entry includes purpose and data processing location

## LAUNCH PHASE — do at or immediately around go-live

### Security

<a id="checklist-n165"></a>
**Vulnerability Disclosure Policy** — priority: medium — [[SaaS-Playbook/06-Security/Vulnerability Disclosure Policy|source note]]
> 🔑 **Needs your sign-off:** the security.txt file and reporting channel are agent-buildable, but the response-time commitment and legal safe-harbor language should be reviewed by you (or your lawyer) before publishing.
- [ ] `security.txt` published at `/.well-known/security.txt` per RFC 9116
- [ ] Dedicated reporting channel (email/form) established and monitored
- [ ] Scope (in-scope and out-of-scope systems) clearly defined
- [ ] Response timeline commitments stated and actually met in practice
- [ ] Safe harbor / no-legal-action commitment for good-faith researchers included
- [ ] Incoming reports routed directly into the security incident response process
- [ ] Recognition mechanism considered (public acknowledgment) even without a paid bounty program

### Analytics

<a id="checklist-n166"></a>
**Key SaaS Metrics (MRR, Churn, LTV, CAC)** — priority: critical `MVP` — [[SaaS-Playbook/17-Analytics/Key SaaS Metrics (MRR, Churn, LTV, CAC)|source note]]
- [ ] MRR calculated precisely and consistently, with annual plans normalized correctly
- [ ] Both customer churn and revenue churn/net revenue retention tracked
- [ ] Voluntary and involuntary churn distinguished and tracked separately
- [ ] CAC calculated as fully-loaded cost, correctly matched to acquisition period
- [ ] LTV grounded in actual observed retention data, not just a formula assumption
- [ ] LTV:CAC ratio and CAC payback period tracked as ongoing health signals

### Legal Documents (scaffolded by the agent — placeholder content, needs your/a lawyer's review before real use)

<a id="checklist-n167"></a>
**Service Level Agreement (SLA)** — priority: medium — [[SaaS-Playbook/02-Business-Legal/Service Level Agreement (SLA)|source note]]
> 📄 **Draft a standard SLA document/page with placeholder content** (uptime target, remedies). Base the uptime number on whatever your actual monitoring shows once the app has run for a while, not an arbitrary figure — and flag the remedy/liability language as needing legal review before it's offered to a real customer.
- [ ] Uptime commitment grounded in actual historical performance data, not aspiration
- [ ] Downtime definition excludes scheduled maintenance and customer-caused issues explicitly
- [ ] Measurement method and monitoring tool specified
- [ ] Remedies (service credits) tiered and capped, not unlimited liability
- [ ] Support response time commitments included if selling to enterprise
- [ ] SLA reviewed against actual infrastructure reliability before being offered
- [ ] Legal counsel reviewed remedy/liability language

## GROWTH PHASE — not needed for initial launch; revisit once there are real paying customers

### Auth & Identity

<a id="checklist-n168"></a>
**SSO and SAML** — priority: medium — [[SaaS-Playbook/05-Auth-Identity/SSO and SAML|source note]]
- [ ] DEFERRED SAML 2.0 and/or enterprise OIDC supported based on actual customer demand — DEFERRED until institution/instructor accounts become a product line (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SSO configuration modeled at the organization level, not per-user — DEFERRED until institution/instructor accounts become a product line (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SAML assertion signature, expiration, and audience validated via a well-vetted library — DEFERRED until institution/instructor accounts become a product line (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Protection against XML signature wrapping and related SAML-specific attack classes verified — DEFERRED until institution/instructor accounts become a product line (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Both SP-initiated and IdP-initiated login flows supported and tested — DEFERRED until institution/instructor accounts become a product line (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED JIT provisioning (or full SCIM) implemented for first-login account creation — DEFERRED until institution/instructor accounts become a product line (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Org admins can enforce SSO-only login for their organization — DEFERRED until institution/instructor accounts become a product line (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n169"></a>
**SCIM Provisioning** — priority: low — [[SaaS-Playbook/05-Auth-Identity/SCIM Provisioning|source note]]
- [ ] DEFERRED Core SCIM 2.0 operations implemented (create, update, deactivate, list/query users) — DEFERRED until institution accounts become a product line and a customer requires an IdP (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SCIM deactivation immediately revokes active sessions, not just future logins — DEFERRED until institution accounts become a product line and a customer requires an IdP (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Group/role sync supported where your product's access model benefits from it — DEFERRED until institution accounts become a product line and a customer requires an IdP (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SCIM endpoint authenticated per-customer with a scoped, revocable token — DEFERRED until institution accounts become a product line and a customer requires an IdP (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED All SCIM operations verified to be scoped to the correct customer organization (tenant isolation applies here too — see [[03-Architecture/Tenant Isolation Strategies]]) — DEFERRED until institution accounts become a product line and a customer requires an IdP (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SCIM-driven changes logged for audit purposes — DEFERRED until institution accounts become a product line and a customer requires an IdP (docs/spec/09 - Checklist Overrides.md)

### Data

<a id="checklist-n170"></a>
**Data Warehousing Basics** — priority: low — [[SaaS-Playbook/08-Data/Data Warehousing Basics|source note]]
- [ ] DEFERRED Actual need for a separate warehouse confirmed (not adopted speculatively before need is demonstrated) — DEFERRED until MAU exceeds 10,000 or analytics queries impact production DB (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Warehouse technology chosen appropriate to scale and existing infrastructure/team familiarity — DEFERRED until MAU exceeds 10,000 or analytics queries impact production DB (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED ETL/ELT pipeline built to populate the warehouse on an appropriate schedule, not querying production directly for analytics — DEFERRED until MAU exceeds 10,000 or analytics queries impact production DB (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Warehouse data modeled for analytical access patterns, not a direct schema mirror — DEFERRED until MAU exceeds 10,000 or analytics queries impact production DB (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED PII classification, access control, and retention policies extended to warehouse data — DEFERRED until MAU exceeds 10,000 or analytics queries impact production DB (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Analytical/BI/data science workloads kept off the production transactional query path — DEFERRED until MAU exceeds 10,000 or analytics queries impact production DB (docs/spec/09 - Checklist Overrides.md)

### Frontend & UX

<a id="checklist-n171"></a>
**Localization (l10n)** — priority: low — [[SaaS-Playbook/10-Frontend-UX/Localization (l10n)|source note]]
- [ ] DEFERRED Target languages/markets prioritized based on actual demand evidence, not speculative broad localization — DEFERRED until more than 10% of signups come from non-English locales (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Professional translation used for customer-facing product and marketing content — DEFERRED until more than 10% of signups come from non-English locales (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Formats, currency, and imagery localized appropriately, not just text — DEFERRED until more than 10% of signups come from non-English locales (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Legal/compliance content localized with jurisdiction-specific legal review where warranted — DEFERRED until more than 10% of signups come from non-English locales (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Translation maintenance process established so new features get localized as they ship, not left in English indefinitely — DEFERRED until more than 10% of signups come from non-English locales (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED In-context review used to catch translation issues a string-only review would miss — DEFERRED until more than 10% of signups come from non-English locales (docs/spec/09 - Checklist Overrides.md)

### Observability

<a id="checklist-n172"></a>
**Distributed Tracing** — priority: medium — [[SaaS-Playbook/14-Observability/Distributed Tracing|source note]]
- [ ] DEFERRED Trace context propagated consistently across all service-to-service calls — DEFERRED until more than three services or recurring cross-service latency debugging pain (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Instrumentation uses OpenTelemetry or another portable, non-proprietary standard — DEFERRED until more than three services or recurring cross-service latency debugging pain (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Significant internal operations (slow queries, external calls) instrumented as spans, not just service boundaries — DEFERRED until more than three services or recurring cross-service latency debugging pain (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Sampling strategy defined appropriate to traffic volume, with full sampling for errors/slow requests — DEFERRED until more than three services or recurring cross-service latency debugging pain (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Traces correlated with logs and metrics via shared identifiers — DEFERRED until more than three services or recurring cross-service latency debugging pain (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Trace data actually used during investigation to identify bottlenecks, not just collected and ignored — DEFERRED until more than three services or recurring cross-service latency debugging pain (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n173"></a>
**Log Retention and Cost** — priority: medium — [[SaaS-Playbook/14-Observability/Log Retention and Cost|source note]]
- [ ] DEFERRED Retention periods defined per log type/purpose, not one uniform policy for everything — DEFERRED until log costs exceed $50/month or compliance requires it (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Tiered storage used where supported, moving older logs to cheaper archive tiers — DEFERRED until log costs exceed $50/month or compliance requires it (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Excessive verbose/debug logging in production reduced or sampled at the source — DEFERRED until log costs exceed $50/month or compliance requires it (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Log ingestion volume and cost tracked as a specific, monitored line item — DEFERRED until log costs exceed $50/month or compliance requires it (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Security/audit log retention aligned with actual compliance requirements — DEFERRED until log costs exceed $50/month or compliance requires it (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Retention policy reassessed periodically based on real operational experience — DEFERRED until log costs exceed $50/month or compliance requires it (docs/spec/09 - Checklist Overrides.md)

### Reliability & DR

<a id="checklist-n174"></a>
**Error Budgets** — priority: low — [[SaaS-Playbook/15-Reliability-DR/Error Budgets|source note]]
- [ ] DEFERRED Error budget calculated directly from the established SLO — DEFERRED until the public SLA is published (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Budget consumption tracked continuously via observability tooling — DEFERRED until the public SLA is published (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Clear, agreed-upon policy defined for what happens when budget is exhausted — DEFERRED until the public SLA is published (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Remaining budget used as an input to release risk decisions — DEFERRED until the public SLA is published (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Budget trends reviewed in regular retrospectives, informing prioritization objectively — DEFERRED until the public SLA is published (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Budget policy framed as a shared team tool, not a blame mechanism — DEFERRED until the public SLA is published (docs/spec/09 - Checklist Overrides.md)

### Analytics

<a id="checklist-n175"></a>
**Cohort Analysis** — priority: medium — [[SaaS-Playbook/17-Analytics/Cohort Analysis|source note]]
- [ ] DEFERRED Cohorts defined by a consistent, meaningful starting event — DEFERRED until 90 days of user data exist (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Retention curves tracked and compared across cohorts over time — DEFERRED until 90 days of user data exist (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Cohorts segmented by acquisition channel/plan tier in addition to signup date — DEFERRED until 90 days of user data exist (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Revenue-based cohort analysis used alongside customer-count retention — DEFERRED until 90 days of user data exist (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Cohort trends correlated with specific product/pricing changes for causal insight — DEFERRED until 90 days of user data exist (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Cohort data presented visually (retention table/heatmap) for pattern legibility — DEFERRED until 90 days of user data exist (docs/spec/09 - Checklist Overrides.md)

## SCALE PHASE — not needed for initial launch; revisit only when actual load/growth demands it

### Data

<a id="checklist-n176"></a>
**Read Replicas and Scaling Reads** — priority: medium — [[SaaS-Playbook/08-Data/Read Replicas and Scaling Reads|source note]]
- [ ] DEFERRED Read replicas introduced only after measured evidence of a real read-load bottleneck — DEFERRED until DB CPU exceeds 60% sustained or p95 read latency regresses (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Read-your-writes-sensitive queries explicitly routed to the primary, not replicas — DEFERRED until DB CPU exceeds 60% sustained or p95 read latency regresses (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Application data access layer explicitly and predictably routes reads vs. writes — DEFERRED until DB CPU exceeds 60% sustained or p95 read latency regresses (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Replication lag actively monitored with alerting on excessive lag — DEFERRED until DB CPU exceeds 60% sustained or p95 read latency regresses (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Graceful degradation tested for replica unavailability or excessive lag — DEFERRED until DB CPU exceeds 60% sustained or p95 read latency regresses (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Replica strategy reassessed as scale grows, recognizing it doesn't address write-scaling needs — DEFERRED until DB CPU exceeds 60% sustained or p95 read latency regresses (docs/spec/09 - Checklist Overrides.md)

### Reliability & DR

<a id="checklist-n177"></a>
**Chaos Engineering Basics** — priority: low — [[SaaS-Playbook/15-Reliability-DR/Chaos Engineering Basics|source note]]
- [ ] DEFERRED Foundational reliability practices (observability, incident response, rollback) mature before starting chaos engineering — DEFERRED until a paid SLA exists and more than one engineer is on call (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Experiments start in staging with contained, well-understood failure modes before any production experiments — DEFERRED until a paid SLA exists and more than one engineer is on call (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Each experiment tests a specific, stated hypothesis about system behavior under failure — DEFERRED until a paid SLA exists and more than one engineer is on call (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Strong observability and fast rollback capability confirmed before running any experiment — DEFERRED until a paid SLA exists and more than one engineer is on call (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Experiments run during low-traffic windows initially, with clear team communication — DEFERRED until a paid SLA exists and more than one engineer is on call (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Findings tracked as concrete fixes, not just interesting observations — DEFERRED until a paid SLA exists and more than one engineer is on call (docs/spec/09 - Checklist Overrides.md)

### Scaling (post-MVP)

<a id="checklist-n178"></a>
**Database Scaling Strategies** — priority: medium — [[SaaS-Playbook/22-Scaling/Database Scaling Strategies|source note]]
- [ ] DEFERRED Simpler optimizations (indexing, query tuning, caching) exhausted before pursuing scaling architecture changes — DEFERRED until the largest table exceeds 100 million rows (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Vertical scaling of the primary considered as the next lever before more complex approaches — DEFERRED until the largest table exceeds 100 million rows (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Read replicas introduced specifically for read-load bottlenecks, per [[08-Data/Read Replicas and Scaling Reads]] — DEFERRED until the largest table exceeds 100 million rows (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Sharding/partitioning considered only for genuine write-load bottlenecks a single primary can't handle, as a last resort — DEFERRED until the largest table exceeds 100 million rows (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Workload-specific database/store mismatches evaluated for specialized secondary stores rather than forcing everything into one database — DEFERRED until the largest table exceeds 100 million rows (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Any scaling architecture change tested thoroughly against realistic data volume before production commitment — DEFERRED until the largest table exceeds 100 million rows (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n179"></a>
**Enterprise Readiness Checklist** — priority: medium — [[SaaS-Playbook/22-Scaling/Enterprise Readiness Checklist|source note]]
- [ ] DEFERRED SSO/SAML support built and tested against real IdP integrations — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SCIM provisioning available where demand justifies the investment — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Audit logging implemented, with a customer-facing audit log feature considered — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SOC 2 report obtained or a credible, communicated roadmap exists — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Security questionnaire response packet prepared in advance — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED SLA offering defined with a realistic, grounded uptime commitment — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Data residency options assessed against target market needs — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED MSA/custom contract process available for larger deals — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Granular RBAC available beyond basic role tiers — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Dedicated support/success process defined for enterprise accounts — DEFERRED until an institutional customer pipeline exists (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n180"></a>
**Horizontal vs Vertical Scaling** — priority: medium — [[SaaS-Playbook/22-Scaling/Horizontal vs Vertical Scaling|source note]]
- [ ] DEFERRED Vertical scaling used as the first, low-effort response where sufficient — DEFERRED until engine queue-age SLO is breached for three days (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Specific signal (ceiling reached, availability need, cost) identified before committing to horizontal scaling effort — DEFERRED until engine queue-age SLO is breached for three days (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Application confirmed genuinely stateless before horizontal scaling is attempted — DEFERRED until engine queue-age SLO is breached for three days (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Load balancing paired with horizontal scaling to actually distribute traffic — DEFERRED until engine queue-age SLO is breached for three days (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Database scaling approached separately, recognizing its distinct constraints — DEFERRED until engine queue-age SLO is breached for three days (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Autoscaling considered once horizontally scaled, for efficient handling of variable load — DEFERRED until engine queue-age SLO is breached for three days (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n181"></a>
**Performance Optimization** — priority: medium — [[SaaS-Playbook/22-Scaling/Performance Optimization|source note]]
- [ ] DEFERRED Optimization targets identified via measurement (profiling, APM, load testing), not intuition alone — DEFERRED until an SLO breach trend appears (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Highest-impact bottleneck addressed first, based on actual measured impact — DEFERRED until an SLO breach trend appears (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Common high-leverage areas (indexes, N+1 queries, caching, serialization) checked systematically — DEFERRED until an SLO breach trend appears (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Algorithmic inefficiencies fixed directly rather than compensated for purely with infrastructure scaling — DEFERRED until an SLO breach trend appears (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Each optimization re-measured to confirm actual effect — DEFERRED until an SLO breach trend appears (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Optimization effort balanced against added complexity, focused on genuinely impactful bottlenecks — DEFERRED until an SLO breach trend appears (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n182"></a>
**Caching Layers at Scale** — priority: low — [[SaaS-Playbook/22-Scaling/Caching Layers at Scale|source note]]
- [ ] DEFERRED CDN-level caching used for static/public content, offloaded from the application cache layer — DEFERRED until cache needs exceed Postgres-backed caching capacity (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Caching deliberately layered (CDN, shared application cache, local cache) matched to content type — DEFERRED until cache needs exceed Postgres-backed caching capacity (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Cache infrastructure itself scaled (clustering or managed scaling) once a single instance becomes a bottleneck — DEFERRED until cache needs exceed Postgres-backed caching capacity (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Cache-layer metrics (hit rate, eviction rate, latency) actively monitored as scale grows — DEFERRED until cache needs exceed Postgres-backed caching capacity (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Cache invalidation logic verified correct across a scaled/distributed cache layer — DEFERRED until cache needs exceed Postgres-backed caching capacity (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED More structured caching patterns (read-through/write-through) considered as caching becomes architecturally central — DEFERRED until cache needs exceed Postgres-backed caching capacity (docs/spec/09 - Checklist Overrides.md)

<a id="checklist-n183"></a>
**Multi-Region Architecture** — priority: low — [[SaaS-Playbook/22-Scaling/Multi-Region Architecture|source note]]
- [ ] DEFERRED Specific, concrete driver (latency, DR, compliance) identified before pursuing multi-region architecture — DEFERRED until EU data residency is required or more than 30% EU users report latency issues (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Architecture pattern (active-passive vs. active-active) chosen deliberately based on the actual driving need — DEFERRED until EU data residency is required or more than 30% EU users report latency issues (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Data replication/consistency approach explicitly designed and its trade-offs accepted — DEFERRED until EU data residency is required or more than 30% EU users report latency issues (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Deployment process updated to coordinate safely across regions — DEFERRED until EU data residency is required or more than 30% EU users report latency issues (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Failover tested explicitly and regularly, not just architected and assumed to work — DEFERRED until EU data residency is required or more than 30% EU users report latency issues (docs/spec/09 - Checklist Overrides.md)
- [ ] DEFERRED Ongoing cost increase accounted for and weighed against the specific benefit — DEFERRED until EU data residency is required or more than 30% EU users report latency issues (docs/spec/09 - Checklist Overrides.md)
