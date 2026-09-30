---
title: StudyForge — Plans, Entitlements & Mock Billing
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, billing]
---

# 07: Plans, Entitlements & Mock Billing

## 1. Goal
Build billing **exactly as a real SaaS would**: plans, a pricing page, checkout, subscription state machine, invoices, plan changes with proration previews, cancellation, dunning, event-driven entitlement sync, and usage metering and quotas. The one difference is that **the payment provider is a mock that settles every charge at $0.00 and never collects card data.** Swapping in Stripe later means implementing one interface plus a config flip. Nothing else changes.

## 2. Plans (seeded in `billing.plans`; editable via migration only)
| | **Free** | **Pro** | **Pro+ (Exam Season)** |
|---|---|---|---|
| List price shown | $0 | $12/mo · $96/yr | $24/mo · $192/yr |
| **Charged during beta** | $0 | **$0.00** (100% "Beta" discount line) | **$0.00** |
| Courses | 2 active | unlimited | unlimited |
| Uploads / month | 15 docs, ≤ 25 MB each | 200 docs, ≤ 200 MB each | 1,000 docs, ≤ 500 MB each |
| Storage | 500 MB | 10 GB | 50 GB |
| Audio transcription | 60 min/mo (free adapter only) | 20 h/mo: paid STT if configured, else free | 60 h/mo: paid STT by default if configured, else free |
| Handwriting OCR | 30 pages/mo (free adapter only; low-confidence pages are flagged for the user to review) | 500 pages/mo: Claude vision escalation; other paid OCR if configured | 2,000 pages/mo: best configured OCR (paid if available) by default |
| AI card generation | 300 cards/mo | 5,000 cards/mo | 20,000 cards/mo |
| Tutor messages | 13/day (Haiku tutor) | 60/day | 200/day |
| Feynman analyses | 10/mo | 200/mo | unlimited (fair use) |
| Mock exams | 1/mo | 8/mo | 30/mo |
| Rubric grading of free response | ✅ | ✅ | ✅ (priority queue) |
| **FSRS reviews, card editing, export, Anki import/export** | ✅ unlimited, always | ✅ | ✅ |
| Personalized FSRS optimizer | — | ✅ | ✅ |
| Google Calendar sync | busy times only (read) | two-way | two-way |
| Exam-crunch mode + cram queue + warm-up | ✅ | ✅ | ✅ |
| Strict exam sandbox | standard only | ✅ strict | ✅ strict |
| Cheat-sheet PDF export | watermark | ✅ | ✅ |
| Code sandbox runs | 50/day | 500/day | 2,000/day |
| Daily AI cost cap (doc 06) | $0.05 | $0.50 | $1.50 (mock-exam jobs are exempt; they're limited by the monthly mock quota) |

Principle: **reviewing your own material is never paywalled.** Only AI compute and premium adapters scale by plan.

## 3. Entitlements model
- `billing.plans.entitlements jsonb`: `{ features: {calendar_oauth: true, strict_sandbox: true, fsrs_optimizer: true, cheatsheet_pdf_clean: true, premium_stt: "allowed"|"default"|false, ...}, limits: {courses_active: 2, uploads_per_month: 15, upload_max_mb: 25, storage_mb: 500, audio_seconds_per_month: 3600, ocr_pages_per_month: 30, cards_generated_per_month: 300, tutor_messages_per_day: 20, feynman_per_month: 10, mock_exams_per_month: 1, code_runs_per_day: 50, ai_cost_micros_per_day: 50000} }`
- `billing.entitlement_overrides`: admin grants (for example, +500 OCR pages until a date), recorded in the audit log.
- **Resolution:** `private.effective_entitlements(user_id)` = the active subscription's plan (or Free) ⊕ overrides. It is cached per request.
- **Enforcement:**
  - `private.has_feature(uid, key)` and `private.check_quota(uid, meter, amount)` are SQL functions used by API middleware **and** inside security-definer RPCs, so the check can't be bypassed.
  - Quotas and the daily AI cap were checked against each other with the engine's economics calculator (`services/engine/engine/adapters/economics.py`): every quota is reachable within the cap. Keep that true when changing either (its test fails otherwise).
  - Quota checks are atomic: `usage_counters` gets an `UPDATE … SET quantity = quantity + $n WHERE quantity + $n <= limit RETURNING`. If no row comes back, the request fails with `quota_exceeded`. Estimates are reserved before AI calls and reconciled afterward with the actual usage.
  - Errors: `403 entitlement_required {feature, upgrade_plan}` / `429 quota_exceeded {meter, limit, resets_at}`. The UI shows an upgrade modal that lists what the upgrade unlocks.
- **Usage visibility:** the Settings → Plan & usage page shows a meter per limit, the reset date, and the last 30 days of usage by day. Users are warned at 80% and 100% (in-app, plus an email at 100%).

## 4. `BillingProvider` interface (packages/core/billing)
```ts
interface BillingProvider {
  id: 'mock' | 'stripe';
  createCustomer(user): Promise<{customerId}>;
  createCheckout(input: {userId, planPriceId, promo?}): Promise<{checkoutId, url}>;
  previewChange(input: {subscriptionId, newPriceId}): Promise<ProrationPreview>;
  changeSubscription(input: {subscriptionId, newPriceId, prorate: boolean}): Promise<void>;
  cancel(input: {subscriptionId, atPeriodEnd: boolean}): Promise<void>;
  resume(subscriptionId): Promise<void>;
  portalUrl(userId): Promise<string>;           // mock → internal /settings/billing
  verifyWebhook(req): Promise<ProviderEvent>;    // signature check
}
```
State is **only** changed by processing `ProviderEvent`s (`checkout.completed`, `subscription.created|updated|deleted`, `invoice.created|paid|payment_failed`, `customer.updated`) in `handleBillingEvent()`. That's the same code path Stripe webhooks will use later.

## 5. Mock provider behavior
1. **Checkout:** `/billing/checkout` → an internal checkout page (`/checkout/{id}`) styled like a real hosted checkout. It shows the plan, the interval, the list price, a **"StudyForge Beta — 100% off"** discount line, tax $0.00, and **Total due today: $0.00**. There are **no card fields.** A "Confirm subscription" button → `POST /billing/checkout/{id}/confirm` (Idempotency-Key).
2. On confirm, the mock provider **emits signed events** (HMAC with `MOCK_BILLING_WEBHOOK_SECRET`) to `POST /webhooks/billing/mock`, the same route shape as the future real webhooks: `checkout.completed` → `subscription.created` → `invoice.created` → `invoice.paid` (total 0). Events are stored in `billing.billing_events` with `UNIQUE(provider,event_id)`, so duplicates are no-ops. They're processed asynchronously (respond 200 fast, then job) and tolerate out-of-order delivery (compare `event.created` / `subscription.version`).
3. **Invoices:** gapless numbering `SF-{YYYY}-{000001}`. Lines cover the plan, the proration lines, the Beta discount, and tax (0). The PDF is rendered server-side (it includes the company placeholder details, "Beta — no charge"), emailed, and downloadable.
4. **Plan changes:** an upgrade takes effect immediately, with a proration preview (computed on list prices, then discounted to $0). A downgrade takes effect at the period end (`scheduled_change`). Cancellation defaults to the period end, with immediate available. The user can resume before the period ends.
5. **Renewals:** pg_cron hourly → the mock provider emits `invoice.created` + `invoice.paid` for due subscriptions (idempotent per period).
6. **Dunning simulation** (admin-only tool, ADM-02): "simulate payment failure" → `invoice.payment_failed` → `past_due` → grace period of 7 days with the full plan still available + banner + emails on days 0/3/6 → on day 7, downgrade to Free (data kept, over-limit items become read-only, never deleted). "Simulate recovery" → `invoice.paid` → active. Soft vs hard failure types are both simulable.
7. **Reconciliation job** (daily): compares `subscriptions` with the mock provider's ledger (`billing.mock_ledger`) and alerts on drift. It's the same job that will later compare against Stripe.
8. **Trials:** not used during beta (everything is free). The state machine supports `trialing` and has tests, but it isn't exposed yet.
9. **Refunds:** an admin "refund" action on mock invoices creates a $0 credit note. The Refund policy page is drafted (📄).

## 6. Subscription state machine
`none → (checkout.completed) → active` · `active → past_due → (paid) active | (grace expired) canceled→free` · `active → (cancel at period end) active[cancel_at_period_end] → (period end) canceled` · `active → (upgrade) active[new plan]` · `active → (downgrade) active[scheduled_change] → (period end) active[new plan]`. Every transition is audited (`billing.*`) and emails the user. Edge cases with tests: month-end anchors (Jan 31 → Feb 28/29 → Mar 31), leap years, timezone of the period boundary (UTC), a double confirm click, events arriving out of order, and a downgrade while over the new plan's limits.

## 7. Stripe migration path (future; recorded as ADR-0011)
1. The human creates a Stripe account and enables Stripe Tax (🔑). Products/prices are created from `billing.plans` by a script.
2. Implement `StripeProvider` (Checkout Sessions, Customer Portal, webhooks), mapping Stripe events → the same `ProviderEvent` type.
3. Set `BILLING_PROVIDER=stripe` locally with Stripe **test-mode** keys → run the full billing E2E with Stripe test clocks → then switch production to live keys.
4. Existing beta subscribers: a migration campaign (grandfather discount coupon), with explicit consent before any real charge.
5. Then un-defer the checklist items marked `DEFERRED until real billing` (PCI SAQ-A confirmation, tax automation, card updater, real dunning retries, chargebacks). See doc 09.

## 8. Unit economics model (kept in `docs/costs.md`, updated monthly)
For each plan, estimate the monthly cost at the p50 and p90 user from the quotas × adapter cost models (doc 06) plus infra per user. Target gross margin at list prices ≥ 75% at p50. This is what justifies the quotas above; if the model breaks, change the quotas, not the principle.
