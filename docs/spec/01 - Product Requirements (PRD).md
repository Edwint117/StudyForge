---
title: StudyForge — Product Requirements (PRD)
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, prd]
---

# 01: Product Requirements (PRD)

## 1. Product summary
**StudyForge** is a web-based (PWA) study platform for college students. A student uploads their course materials and syllabus. StudyForge builds a knowledge graph, plans study backwards from each exam date, turns material into active-recall work, schedules retention with FSRS, simulates the exam under real conditions, diagnoses blind spots, and runs triage in the final 48 hours.

**Customer:** individual students aged 18+, self-serve signup, freemium. US-first, but anyone in the world can sign up.
**Business model:** Free / Pro / Pro+ subscriptions. Billing is **mocked at $0** for now (doc 07).

### Product principles
1. **Exam-backwards:** every feature knows which exam it serves and how many days remain.
2. **Grounded:** every generated item cites its source chunk (page, slide or timestamp). The tutor cannot see anything outside the student's materials.
3. **Active over passive:** the product makes students produce answers before it grades them.
4. **Never paywall reviewing your own cards.** Charge for AI compute, not for access to your own data.
5. **Math and code are first-class:** KaTeX everywhere, MathLive input, Shiki highlighting, SymPy equivalence checks, and sandboxed code runs.
6. **Academic integrity:** the tutor is Socratic by default, and the exam sandbox has zero AI access.

### Personas
| ID | Persona | Core job |
|---|---|---|
| P1 | STEM undergrad (CS/Math/Eng) | Turn slides, proofs and code into practice; survive midterms |
| P2 | Pre-professional (pre-med, pre-law) | High-volume memorization plus timed exams |
| P3 | Working student | Studies only in real calendar gaps; needs dynamic rescheduling |
| P4 | Anki power user | Wants FSRS plus import/export and no lock-in |
| A1 | StudyForge operator (you / support) | Admin panel, provider settings, abuse handling, support |

### Success metrics (instrumented in PostHog, see doc 02)
- **Activation:** uploads ≥1 source **and** completes their first review session within 24h of signup.
- **Plan adherence:** % of planned sessions completed each week.
- **Retention:** week-4 active reviewers; FSRS-measured true retention.
- **Quality:** % of AI cards accepted unedited; grader agreement with human-labelled eval set; tutor citation validity.
- **Business:** free→Pro conversion (mock), AI cost per active user, and the gross-margin model (doc 07).

---

## 2. SaaS surfaces (the parts every SaaS needs)

### 2.1 Marketing site (public, SSR, SEO)
- **MKT-01** Landing page covering value prop, the 6-module walkthrough, social proof placeholders, a CTA, and a pricing teaser. *AC:* Lighthouse ≥ 90 on Performance, Accessibility, Best Practices and SEO; OG/Twitter meta; JSON-LD `SoftwareApplication`.
- **MKT-02** `/pricing` built from the `plans` table (never hard-coded), with a monthly/annual toggle and a "Beta: all plans free" banner.
- **MKT-03** Legal pages: `/terms`, `/privacy`, `/cookies`, `/subprocessors` (generated from `docs/subprocessors.yaml`), `/dpa`, `/sla`, `/security` (plus `/.well-known/security.txt`), `/acceptable-use`, `/refunds`, `/dmca`. All are versioned (`legal_documents` table) with a changelog.
- **MKT-04** `/docs` help center (MDX) with getting-started guides for each module, FAQs, and "how grading works" / "how FSRS works" explainers. Searchable.
- **MKT-05** `/status` links to the external status page. `/changelog` is public.
- **MKT-06** `sitemap.xml` and `robots.txt`; canonical URLs; the app routes are `noindex`.

### 2.2 Authentication & account
- **AUTH-01** Sign up with email+password, magic link, or Google OIDC. Signup requires an **18+ age attestation** (checkbox plus date of birth → only store `age_verified_at` and the year of birth) and **acceptance of ToS/Privacy** (recording version and timestamp). *AC:* under-18 is blocked with a friendly message and no account row is kept.
- **AUTH-02** Email verification is required before any AI or ingestion feature is used. Unverified users can browse onboarding only.
- **AUTH-03** Password policy: minimum 8 and maximum 128 characters, no composition rules, and a breach check (Supabase leaked-password protection or an HIBP k-anonymity fallback). Paste is allowed.
- **AUTH-04** MFA: TOTP enrollment with 10 single-use recovery codes (hashed). Passkeys are an optional second method (ADR-0005). MFA is **mandatory** for admin accounts.
- **AUTH-05** Sessions: users can list active sessions (device, IP city, last seen) and revoke one or all others. Changing or resetting the password revokes all other sessions.
- **AUTH-06** Account recovery: time-limited single-use reset email; a reset cannot bypass MFA; a notification email on start and completion; rate-limited.
- **AUTH-07** Bot and abuse protection on signup, login, password reset and magic-link requests: per-IP and per-email rate limits, progressive lockout after repeated failures, email verification, and a disposable-email-domain blocklist. Built behind a `BotCheck` interface (no-op implementation for now) so a CAPTCHA can be added later without touching the flows.
- **AUTH-08** Email change requires re-verifying the new address and sends a notification (with an undo link) to the old one.
- **AUTH-09** Security emails: new-device login, MFA changed, password changed, data export ready, account deletion scheduled.

### 2.3 Onboarding (first-run)
- **ONB-01** Checklist wizard: (1) pick timezone and study preferences, (2) create the first course, (3) upload a syllabus, which is auto-parsed and then confirmed, (4) upload at least one material, (5) optionally connect a calendar, (6) generate a plan. Every step can be skipped and resumed later; progress is stored in `profiles.onboarding_state`.
- **ONB-02** "Try with sample course" loads a demo course (public-domain intro-stats material) so the product is explorable in under 60 seconds.
- **ONB-03** Every list view has a designed empty state with one primary action.

### 2.4 App shell & settings
- **APP-01** Responsive shell (sidebar ≥ 1024px, bottom nav on mobile), a command palette (⌘K), global search, a notifications bell, and a plan/usage meter.
- **APP-02** Settings tabs: Profile, Study preferences (daily max minutes, rest days, desired retention, crunch-mode days, interleaving on/off), Notifications, Calendars, Security (password, MFA, passkeys, sessions), Plan & billing, Data & privacy (export, delete, cookie preferences), Accessibility (reduce motion, dyslexia-friendly font, high contrast).
- **APP-03** Installable PWA: an offline review queue (the next 200 due cards, see SRS-09); offline reviews sync idempotently.
- **APP-04** Keyboard-first review (1–4 grades, space to reveal, `e` to edit, `u` to undo).
- **APP-05** Light/dark/system theme.

### 2.5 Notifications
- **NOT-01** In-app notifications for job finished/failed, plan rebalanced, session starting soon, exam in 7/3/1 days, and cram queue ready.
- **NOT-02** Email notifications (through the `EmailProvider` interface with React Email templates; the current implementation delivers to the admin **Mail outbox**, doc 02) for transactional and security messages (always on), a daily study digest (opt-in, default on), and exam reminders (default on). Product/marketing emails are opt-in only (default off) and every one has one-click unsubscribe (RFC 8058 `List-Unsubscribe-Post`).
- **NOT-03** Web push (PWA) for session reminders, opt-in.
- **NOT-04** Per-channel × per-category preference matrix, plus quiet hours in the user's timezone.

### 2.6 Data rights & privacy
- **DATA-01** Self-serve export: a ZIP of JSON + CSV (all rows owned by the user) + original uploads + `.apkg` of all cards. Built as a job, delivered through a 24h signed URL, with an emailed notification.
- **DATA-02** Self-serve deletion: 7-day grace period (cancellable) → hard delete across DB, Storage, the vector index, analytics (PostHog person delete), the LLM trace store (Langfuse), and email provider suppression. Audit event retained without PII.
- **DATA-03** Rectification: every profile field is editable. Correction requests for AI-generated content can be made via support.
- **DATA-04** Cookie consent banner (Accept all / Reject all / Customize, with equal prominence). Analytics and session tooling load **only** after consent. GPC signal honored as opt-out.
- **DATA-05** "Your data & AI" page explaining which providers see what (generated from the provider config), and that user content is never used to train models.

### 2.7 Support
- **SUP-01** In-app "Help" widget: searches `/docs`, then offers a contact form (category, message, optional screenshot, auto-attached diagnostics such as app version, route and last error ID, **with consent**) → `support_tickets` table + an email to the support inbox.
- **SUP-02** "Report a problem with this content" on every AI output (card, tutor answer, grade) → `content_reports` table, visible in the admin queue, and it feeds evals.
- **SUP-03** The user sees ticket status and replies under Settings → Support.

### 2.8 Admin panel (`/admin`, admin role + MFA required, every action audited)
- **ADM-01** User lookup (email/ID) → profile, plan, usage, jobs, recent errors. A **support view** shows metadata and counts only. Viewing content requires a user-granted, time-boxed support access grant (`support_access_grants`).
- **ADM-02** Actions: resend verification, revoke sessions, suspend/unsuspend, change plan (mock), grant quota, simulate billing events (payment failed/recovered), and cancel deletion.
- **ADM-03** Job monitor: queue depth per job type, failures, dead-letter queue with a retry button.
- **ADM-04** **Provider Settings:** for each task (see doc 06), choose the provider/model per plan tier, set per-task price estimates, and flip the global AI kill switch and per-provider circuit breakers. Changes are versioned and audited.
- **ADM-05** Content reports queue and support tickets queue.
- **ADM-06** Metrics: signups, activation, DAU/WAU, AI spend today/month vs budget, top spenders.
- **ADM-07** Feature flags (proxied from PostHog) and announcement banners.

---

## 3. Learning modules

### Module 1: Ingestion & Course Asset Centralization
- **ING-01** Upload PDF, PPTX, DOCX, Markdown/TXT, images (PNG/JPG/HEIC, i.e. handwritten notes), and audio/video (MP3/M4A/WAV/MP4/WebM, i.e. lecture recordings). Uploads are resumable (TUS) and direct to Storage. Size limits come from entitlements (doc 07). *AC:* files are type-checked by magic bytes, and disallowed types are rejected with a clear error.
- **ING-02** Processing runs as a job with live progress ("Parsing page 12/50", "Transcribing 14:03/52:10") via Realtime, and can be cancelled. A failed job shows an actionable error and a retry button.
- **ING-03** Parsing preserves structure: PDF page numbers, slide numbers plus speaker notes, headings, tables, images (stored as extracted assets), **math → LaTeX**, and **code blocks with detected language**.
- **ING-04** Handwriting/scan OCR produces text plus LaTeX for math. Each page has a confidence score, and low-confidence pages are flagged for review.
- **ING-05** Audio produces a transcript with **word/segment timestamps** and speaker diarization where the provider supports it. Clicking a transcript line seeks the audio player.
- **ING-06** Semantic chunking by section, slide, theorem, definition, example or code block. Each chunk is typed (`definition|theorem|proof|formula|example|code|text|question`) and embedded.
- **ING-07** **Knowledge graph extraction:** concepts (with definitions, formulas and theorems attached), `prerequisite_of` / `part_of` / `related_to` edges, and a canonical merge of duplicates across documents. *AC:* the graph view renders the course DAG, and the user can rename, merge or split concepts and add or remove edges; user edits survive re-ingestion.
- **ING-08** **Cross-referencing:** automatic `asset_links` between slide ↔ textbook page ↔ lab ↔ past-exam question, based on embedding similarity plus shared concepts, with a confidence score. Links can be confirmed or rejected by the user.
- **ING-09** Syllabus documents are flagged as `kind=syllabus` and routed to PLAN-01.
- **ING-10** Document viewer: the original file (PDF.js / slide images / audio player) side-by-side with the parsed markdown, with chunk highlights and concept chips. LaTeX is rendered with KaTeX and code with Shiki.
- **ING-11** Search: hybrid (Postgres FTS + pgvector, fused with RRF) across all of the user's courses, with filters (course, type, document) and results deep-linking to the page, slide or timestamp.
- **ING-12** Dedup: re-uploading an identical file (same sha256) reuses the existing parse and doesn't consume quota. Re-uploading a changed version supersedes it (version history kept) and marks dependent cards "source changed — review".
- **ING-13** Past exams: when uploaded as `kind=past_exam`, the questions are extracted into the question bank (DIAG-01) with any answer keys or rubrics found.

### Module 2: Intelligent Exam-Backwards Study Planning
- **PLAN-01** **Syllabus parsing:** extract the course code/title, exams (type, date/time, location if present, weight %), grading breakdown, a topic schedule per week, and policies (permitted calculators, formula-sheet rules). Every extracted field shows its source span and a confidence score. **The user must confirm** before exams are created. Low-confidence fields are highlighted.
- **PLAN-02** Exams CRUD: title, date/time, duration, weight %, location, covered units/concepts (a picker on the concept graph), and a readiness target (default 85%).
- **PLAN-03** **Availability:** manual weekly recurring blocks, plus busy times from connected calendars, plus preferences (daily max minutes, earliest/latest study times, rest days, minimum block 25 min, maximum block 120 min).
- **PLAN-04** **Backward scheduling** (algorithm in doc 05): generate a plan from today → exam, covering learn, spaced review, practice, mock exam, buffer/catch-up, rest and consolidation sessions. Prerequisites come first, and the final 2 days are consolidation/cram. *AC:* the fixture tests in doc 05 pass. The plan explains itself ("Why this session?").
- **PLAN-05** **Feasibility:** if the required minutes exceed the available minutes, show the deficit and offer options: extend the daily max, drop lowest-weight topics to "skim", or accept reduced coverage. Never silently overbook.
- **PLAN-06** **Dynamic rebalancing:** triggered by a missed session, a quiz/mock score below threshold on a unit, a calendar change, an exam date change, or new material. Rebalancing re-plans from *now* forward, keeping completed and locked sessions and minimizing churn. A change summary is shown ("3 sessions moved, 1 added for Unit 4 remediation"). *AC:* doc 05 rebalance fixtures pass, and no manual action is needed.
- **PLAN-07** Multiple concurrent exams across courses share one availability pool. Allocation is proportional to urgency × weight × deficit (doc 05).
- **PLAN-08** **Google Calendar sync:** Google OAuth. Busy blocks are read, and study sessions are written to a dedicated "StudyForge" calendar. Two-way: if the user moves or deletes a StudyForge event in Google Calendar, the app updates the session and may rebalance. Incremental sync uses sync tokens plus push notifications (Google watch channels) with renewal, and a 15-minute polling fallback.
- **PLAN-09** **Provider interface:** all calendar code goes through a `CalendarProvider` interface (connect, list busy blocks, incremental sync, write/update/delete events, watch/renew, disconnect). Google is the only implementation in this release; the planner and UI never reference Google directly, so another provider can be added later without changing them.
- **PLAN-10** Views: Today (agenda plus "start next session"), Week, Month, and an exam countdown. Sessions can be started, completed, skipped (with a reason) or rescheduled by drag-and-drop, which locks them.

### Module 3: Active Comprehension & Note Transformation
- **COMP-01** **Flashcard generation** from a chosen scope (document, pages, unit, concept set, or "weak areas"). Card types: basic, reversed, **cloze**, **concept-map** (fill in the missing node/edge of a small subgraph), **math-step** (fill in the next derivation step), **code** (predict output / fill the blank line). Each card cites its source chunk(s) and links to concepts.
- **COMP-02** A **draft review queue** for generated cards: accept, edit, reject, or regenerate with feedback, plus bulk accept. A quality lint pass (one fact per card, no ambiguity, no answer leakage in the prompt) runs before a card is shown. Near-duplicates of existing cards are detected (embedding similarity > 0.92) and flagged.
- **COMP-03** **Feynman mode:** pick a concept → the student explains it in plain language (typing or voice, where voice is transcribed through the STT adapter) → analysis returns: a coverage score against the concept's source-grounded key points, **missing steps**, **buzzwords used without explanation**, **incorrect statements** (with citations), and follow-up questions. The results feed mastery (doc 05), and the gaps can be turned into cards with one click.
- **COMP-04** **Socratic tutor** (RAG, restricted to the user's materials in the selected course):
  - The default mode is **Socratic**: guiding questions and hints of escalating specificity. It **never gives the final answer** to a question matching a question-bank item, a card, or a problem that looks like graded work. Hint levels 1–3 come first, and "show worked solution" is available *only* for questions the student has already attempted and that aren't in an active exam scope within 24h. The toggle is configurable.
  - Every factual claim carries a citation (doc/page/slide/timestamp). If retrieval finds nothing relevant, it says so rather than answering from general knowledge ("That doesn't appear in your course materials").
  - It is **disabled** during an active mock exam attempt (server-enforced, 423 Locked).
  - Chat actions: "make cards from this", "add to cheat sheet", "quiz me on this".
  - Threads are saved per course and are searchable.
- **COMP-05** **Formula & cheat-sheet generator:** aggregates the formulas, definitions and theorems from selected units (from concept graph nodes), and lets the user reorder, edit and pin them. It respects the exam's formula-sheet rules from the syllabus (e.g. "one side of letter paper"), fitting the content to a page budget with a live print preview. Exports to **PDF** (server-rendered, KaTeX) and Markdown.
- **COMP-06** Math input via MathLive with raw-LaTeX toggle; code input via CodeMirror with language modes.

### Module 4: Memory Retention Engine (SRS)
- **SRS-01** **FSRS** scheduling (FSRS-6 via `ts-fsrs` in the API and `py-fsrs` in the engine, pinned to matching versions and checked by a parity test). Card state: stability, difficulty, due, reps, lapses and state.
- **SRS-02** **Personalized parameters:** a weekly optimizer job per user with ≥ 400 reviews (py-fsrs optimizer). Parameters are only adopted if log-loss improves on a holdout set, and the previous parameters are kept for rollback.
- **SRS-03** **Verification before self-grade:** the student must produce an answer *before* revealing it:
  - typed text is compared (normalized, fuzzy) and the result shown;
  - **math** is checked for equivalence with SymPy (engine RPC, < 300ms p95), with numeric tolerance;
  - **code** runs in the sandbox against the card's tests;
  - **steps** (math-step cards) are checked for equivalence of the entered step;
  - **free explanation** is marked by an LLM against the card's key points (Haiku, cached).
  The system proposes a grade (Again/Hard/Good/Easy) from the verification result plus response time. The student may override it, but overriding "incorrect" to "Good" requires one extra click and is logged (`self_override=true`). The ratio of confident-but-wrong answers is shown in stats as the "illusion of competence" metric.
- **SRS-04** **Exam-crunch mode** (doc 05): switches on automatically for cards in an exam's scope when the exam is ≤ `crunch_days` away (default 7). It caps intervals so there is a review before the exam, prioritizes cards by weight × (1 − R at exam time), and raises desired retention for in-scope cards. The UI shows a "Crunch mode" badge with an explanation.
- **SRS-05** **Interleaving:** sessions mix topics per doc 05 (no two consecutive items from the same unit when there's an alternative; confusable concepts are deliberately adjacent). It can be toggled per session.
- **SRS-06** Review session types: Due, Exam scope, Custom (filters), Crunch, and Warm-up (EXAM-02, which doesn't update FSRS state).
- **SRS-07** Card management: browse/filter/search, edit (re-lint), suspend, bury, reset, move, tag, and view source.
- **SRS-08** **Anki interop:** export `.apkg` (genanki, LaTeX preserved, media included) and import `.apkg` including review history, which is replayed to initialize FSRS state.
- **SRS-09** **Offline:** the PWA caches the next 200 due cards plus media. Offline reviews are queued in IndexedDB with a `client_review_id` and synced idempotently. Conflicts are resolved server-side by replaying reviews in `reviewed_at` order.
- **SRS-10** Stats: retention curve, reviews heatmap, forecast of due load for the next 30 days, true retention vs desired, and time per card.

### Module 5: Midterm Simulation & Diagnostics
- **DIAG-01** **Question bank:** from past exams (ING-13), user-authored questions, and generated questions. Types: MCQ (with misconception distractors), short answer, numeric (unit-aware tolerance), multi-step analytical (per-step answers), **code** (tests), and proof/free-response (rubric). Each question has a unit, concepts, difficulty (1–5, calibrated from attempts), source citations and a rubric.
- **DIAG-02** **Mock exam generator:** a blueprint = the exam's covered units weighted by syllabus/topic weight × the student's weakness, a question-type mix, total points, and a duration equal to the real exam's. Questions are drawn from the bank first and generated to fill gaps. Every generated question is **verified** (independently solved twice; must agree; numeric answers checked with SymPy; code questions have passing reference solutions) before it's used. Previously seen questions are avoided unless the bank is exhausted.
- **DIAG-03** **Strict exam sandbox:** a server-authoritative timer (a `deadline_at` stored at start; the client timer is display only; submission after the deadline plus a 30s grace auto-submits what was saved). Fullscreen is requested, and exits, tab switches and blur events are logged as integrity events and shown on the result. Tutor, notes, search and card routes are blocked server-side during an active attempt. Answers autosave every 10s and on change. The user is warned before closing. Optional lockdown level: "Strict", which auto-flags the attempt if it is exited more than 3 times.
- **DIAG-04** **Rubric-based grading:** deterministic checks run first (MCQ, numeric, SymPy, code tests), then an LLM rubric grader for free-response/steps. It awards partial credit per criterion and returns **per-criterion deductions with reasons and error classification**: `conceptual`, `formula_recall`, `calculation_slip`, `incomplete`, `misread_question`, `notation`. It is grounded in the rubric plus the cited source. Instructor rubrics (uploaded) override generated ones. Low-confidence grades are flagged for self-review, and the student can dispute a grade → re-grade with the dispute text → the dispute is logged for evals.
- **DIAG-05** **Results page:** score, time per question, per-question feedback, links to the source material for each deduction, and a "turn misses into cards" action. It triggers PLAN-06 rebalancing.
- **DIAG-06** **Blind-spot heatmap:** mastery % per unit → chapter → concept (drill-down), colored on a sequential scale with the numeric value in the cell (accessible), and error-type breakdown bars per unit. Filters by time range and exam scope.
- **DIAG-07** **Readiness forecast** per exam: the predicted score band from mastery × topic weights, with a confidence band. Shown on the exam page and the dashboard.

### Module 6: Day-of-Exam Readiness & Review
- **EXAM-01** **High-yield cram queue** (T-48h, or on demand): covered topics in the top cumulative 80% of exam weight **and** mastery < 80%, ordered by weight × (0.8 − mastery). Each topic bundles its low-retrievability cards, 1–2 practice questions and its cheat-sheet section.
- **EXAM-02** **Rapid-fire warm-up:** 15 minutes and about 25 items, drawn from key terms and core formulas in the exam's scope, biased toward *high-retrievability* items for confidence, low-stakes, with no FSRS updates, and ending with a calm summary screen. Available from T-6h.
- **EXAM-03** **Pre-exam checklist:** auto-seeded from the syllabus policies (permitted calculator model, formula-sheet rules, ID required, room/location, scratch-paper rules, arrival time) and editable. Reminders go out at T-24h and T-2h with the checklist. The location links to maps.
- **EXAM-04** Exam day mode: the dashboard switches to a single card showing the countdown, the warm-up button, checklist progress, and "you've done X hours / Y reviews" reassurance. All non-essential notifications are suppressed.
- **EXAM-05** After the exam: the student logs the actual score (optional) → it calibrates the readiness forecast and feeds model evals. The exam's plan is archived and unit mastery is carried into the final exam's plan.

---

## 4. Non-functional requirements
| Area | Requirement |
|---|---|
| Performance | Next card < 100ms (prefetched queue); API p95 < 300ms for CRUD; tutor first token < 2.0s p95; a 50-page PDF fully ingested < 90s p95 (free adapters) and < 60s on premium; 60-min lecture transcribed < 15 min (faster-whisper on a 4-vCPU Cloud Run Job), < 3 min premium |
| Availability | Target 99.5% monthly for the web/API at launch (the published SLA draft states 99.5%), measured by external uptime checks |
| Security | OWASP ASVS L2 as the target; everything in the Engineering Checklist Security section |
| Privacy | GDPR/CCPA-ready rights; no training on user content; PII minimized (doc 03 tiers) |
| Accessibility | WCAG 2.2 AA; keyboard-complete; MathML output; captions for any video content we host |
| Browser support | Last 2 versions of Chrome, Edge, Firefox and Safari; iOS Safari 17+; Android Chrome |
| i18n | English only at launch, but **all strings externalized** (next-intl), dates and numbers locale-formatted, and the timezone correct everywhere |
| Cost | AI + infra cost per active free user < $0.40/mo and per Pro user < $3/mo (targets; enforced by quotas, doc 07) |

## 5. Explicitly out of scope (for now)
Microsoft Outlook and Apple/ICS calendar sync, institution/instructor accounts, SSO/SAML/SCIM, shared or public decks, social features and leaderboards, native mobile/desktop apps, real payment processing, languages other than English, and users under 18. Each is listed with its trigger in `09 - Checklist Overrides.md` or the Growth section of `08`.
