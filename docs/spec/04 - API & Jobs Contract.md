---
title: StudyForge — API & Jobs Contract
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, api]
---

# 04: API & Jobs Contract

## 1. Conventions (apply to every endpoint)
- **Base:** `${APP_URL}/api/v1`. It is the only surface clients use for writes. The web UI's server components may read through supabase-js with the user's JWT (RLS), but **all mutations go through `/api/v1`** so that future clients (mobile) get identical behavior.
- **Auth:** Supabase session cookie (web) or `Authorization: Bearer <access_token>` (future native). Every handler starts with `requireUser()` → returns `{userId, aal, role}`. Admin routes add `requireAdmin({aal:'aal2'})`. **Default-deny:** a lint rule fails `pnpm verify` if a route file doesn't call one of `requireUser|requireAdmin|publicRoute(reason)`.
- **Validation:** zod schemas in `packages/contracts`, with `.strict()` so unknown fields are rejected (mass-assignment defense). The OpenAPI 3.1 spec is generated from those schemas and served at `/api/v1/openapi.json`; the docs are rendered at `/docs/api` (internal only at launch).
- **Errors:** RFC 9457 `application/problem+json`: `{type, title, status, detail, instance, code, request_id, errors?[{path, message}]}`. Codes are stable strings such as `quota_exceeded`, `entitlement_required`, `exam_in_progress_locked`, `idempotency_conflict`, `validation_failed`, `not_found` (also used for objects the user can't access, so existence never leaks), and `rate_limited`.
- **Status codes:** 200/201/202 (job accepted, returns `{job_id}`)/204; 400 validation; 401; 403 entitlement/role; 404; 409 conflict; 412 precondition (ETag); 422 semantic; 423 locked (active exam); 429; 5xx.
- **Pagination:** cursor-based: `?limit=50&cursor=<opaque>` → `{data, next_cursor}`. The maximum limit is 200 and every list is paginated.
- **Idempotency:** header `Idempotency-Key` (UUID). It is **required** on POSTs marked ⓘ. The server stores `(user_id, key, route)` → request hash plus response for 24h. The same key with a different body returns `409 idempotency_conflict`.
- **Concurrency:** `ETag`/`If-Match` on PATCH for editable documents (cards, cheat sheets, plans).
- **Rate limits:** Postgres sliding window (`private.rate_limit_hit`, ADR-0016), keyed by user ID (or IP for anonymous requests). Responses carry the headers `RateLimit-Policy` and `RateLimit` (IETF draft) plus `Retry-After` on a 429. Buckets (per user unless noted):
  | Bucket | Limit |
  |---|---|
  | default | 300 req / 5 min |
  | auth-sensitive (per IP + per email) | 10 / 15 min |
  | uploads | 30 / hour |
  | AI (tutor, generate, feynman) | 30 / min, plus the plan quota |
  | exports | 3 / day |
  | webhooks (per provider IP range) | 600 / min |
- **Versioning:** URL major version. Additive changes are non-breaking. Breaking changes → `/api/v2`, with a 6-month deprecation window, `Deprecation` and `Sunset` headers, and a changelog entry at `/changelog`.
- **Request ID:** `x-request-id` is propagated to logs, Sentry, Langfuse and the engine.
- **CSRF:** cookie-authed mutations require `Origin` to be in the allowlist, **and** a double-submit `x-csrf-token` header (matching the cookie). Server Actions (if used) rely on Next's built-in origin check plus the same allowlist.

## 2. Endpoints
ⓘ = Idempotency-Key required · 🔒 = entitlement-gated · ⏱ = returns 202 + a job

### Me / account
| Method | Path | Notes |
|---|---|---|
| GET | `/me` | profile + settings + plan + usage summary |
| PATCH | `/me` | display_name, timezone, locale only |
| PATCH | `/me/settings` | study preferences |
| GET/DELETE | `/me/sessions`, `/me/sessions/{id}` | list/revoke (security definer RPC over `auth.sessions`) |
| POST | `/me/sessions/revoke-others` | |
| GET/POST/DELETE | `/me/mfa/*` | wrappers over Supabase MFA + recovery codes |
| POST ⓘ⏱ | `/me/export` | DATA-01 |
| POST ⓘ | `/me/deletion` | schedule (7-day grace); `DELETE /me/deletion` cancels |
| GET/PUT | `/me/consent` | cookie categories |
| GET/PUT | `/me/notification-preferences` | |
| POST | `/auth/realtime-token` | short-lived token for Realtime (ADR-0004) |

### Courses, documents, graph
| Method | Path | Notes |
|---|---|---|
| GET/POST/PATCH/DELETE | `/courses[/{id}]` | soft delete → trash |
| GET/POST/PATCH/DELETE | `/courses/{id}/units[/{uid}]` | |
| POST ⓘ🔒 | `/documents` | `{course_id, kind, filename, bytes, sha256}` → `{document_id, upload:{url, token}}` or `{document_id, deduplicated:true}` |
| POST ⓘ⏱ | `/documents/{id}/finalize` | enqueues `ingest.document` |
| GET | `/documents/{id}` | status, metadata, signed viewer URL (5 min) |
| GET | `/documents/{id}/chunks` | paginated |
| POST ⏱ | `/documents/{id}/reprocess` | optional `{force_provider}` (admin only) |
| DELETE | `/documents/{id}` | |
| GET | `/search?q=&course_id=&type=` | hybrid search |
| GET | `/courses/{id}/graph` | nodes + edges |
| PATCH/POST/DELETE | `/concepts/{id}`, `/concepts/merge`, `/concept-edges` | user edits set `is_user_edited` |
| GET/PATCH | `/asset-links?chunk_id=` / `/asset-links/{id}` | confirm/reject |

### Planning
| Method | Path | Notes |
|---|---|---|
| GET/PATCH | `/syllabus-extractions/{id}` · POST `/syllabus-extractions/{id}/confirm` | creates exams/units/checklist |
| GET/POST/PATCH/DELETE | `/exams[/{id}]` | PATCH of date → triggers rebalance |
| GET/PUT | `/availability/rules` | |
| GET | `/availability?from=&to=` | merged free/busy |
| POST ⓘ⏱ | `/plans/generate` | `{exam_ids?}` (default: all upcoming) |
| POST ⓘ⏱ | `/plans/rebalance` | manual trigger (auto triggers are internal) |
| GET | `/plans/active` | sessions + feasibility + change summary |
| GET/PATCH | `/sessions/{id}` | start/complete/skip/move (move ⇒ `is_locked`) |
| GET | `/sessions?from=&to=` | |
| GET | `/calendar/connections` · DELETE `/calendar/connections/{id}` | |
| GET | `/calendar/oauth/google/start` → redirect | PKCE + state (signed, 10 min) |
| GET | `/calendar/oauth/google/callback` | |
| POST | `/webhooks/google-calendar` | validates `X-Goog-Channel-Token` (per-channel secret) + channel id |

### Comprehension
| Method | Path | Notes |
|---|---|---|
| POST ⓘ🔒⏱ | `/cards/generate` | `{scope, types[], count_hint}` → generation batch |
| GET | `/cards?status=&course_id=&concept_id=&q=` | |
| POST/PATCH/DELETE | `/cards[/{id}]` | ETag on PATCH |
| POST | `/cards/bulk` | `{ids, action: accept\|reject\|suspend\|tag}` |
| POST ⓘ🔒⏱ | `/feynman` | `{concept_id, explanation_md \| audio_upload_id}` |
| GET | `/feynman/{id}` | |
| GET/POST | `/tutor/threads` | |
| POST ⓘ🔒 | `/tutor/threads/{id}/messages` | **SSE stream**: events `token`, `citation`, `done`, `error`; 423 if an attempt is active |
| POST ⓘ🔒⏱ | `/cheat-sheets` · PATCH `/cheat-sheets/{id}` · POST ⏱ `/cheat-sheets/{id}/export?format=pdf\|md` | |

### Retention
| Method | Path | Notes |
|---|---|---|
| GET | `/reviews/queue?mode=due\|exam\|crunch\|custom\|warmup&exam_id=&limit=` | returns items + prefetched media URLs |
| POST ⓘ | `/reviews` | single or batch `[{client_review_id, card_id, answer, rating?, response_ms, reviewed_at, mode}]` → verification + new state; batch ≤ 200 (offline sync) |
| POST | `/reviews/verify` | pre-grade verification only (reveals the verdict, doesn't record) |
| POST | `/reviews/{id}/undo` | within the session; restores `state_before` |
| GET | `/stats/retention?course_id=` | |
| POST ⓘ⏱ | `/anki/import` (upload id) · POST ⓘ⏱ `/anki/export` | |

### Diagnostics & exam day
| Method | Path | Notes |
|---|---|---|
| GET/POST/PATCH/DELETE | `/questions[/{id}]` · `/rubrics[/{id}]` | |
| POST ⓘ🔒⏱ | `/mock-exams` | `{exam_id, duration_min?, strictness}` → blueprint + selection + generation + verification |
| POST ⓘ | `/mock-exams/{id}/attempts` | starts; returns `deadline_at`; locks tutor/notes |
| PUT | `/attempts/{id}/answers/{question_id}` | autosave; rejected after deadline+grace |
| POST | `/attempts/{id}/integrity-events` | batch |
| POST ⓘ⏱ | `/attempts/{id}/submit` | grading job |
| GET | `/attempts/{id}` | results when graded |
| POST ⓘ⏱ | `/attempts/{id}/answers/{qid}/dispute` | |
| GET | `/mastery/heatmap?course_id=&exam_id=&level=unit\|concept` | |
| GET | `/exams/{id}/readiness` | forecast |
| GET | `/exams/{id}/cram-queue` | EXAM-01 |
| POST | `/exams/{id}/warmup` | builds a warm-up session |
| GET/POST/PATCH/DELETE | `/exams/{id}/checklist[/{item}]` | |

### Billing (doc 07)
`GET /billing/plans` (public) · `GET /billing/subscription` · `POST ⓘ /billing/checkout` · `POST ⓘ /billing/checkout/{id}/confirm` (mock) · `POST ⓘ /billing/subscription/change` (preview via `?preview=true`) · `POST ⓘ /billing/subscription/cancel` · `POST ⓘ /billing/subscription/resume` · `GET /billing/invoices` · `GET /billing/invoices/{id}/pdf` · `POST /webhooks/billing/{provider}` (the mock provider posts signed events here too).

### Support, notifications, admin
`GET/PATCH /notifications` · `POST /push/subscriptions` · `POST /support/tickets` · `GET /support/tickets` · `POST /content-reports` · `/admin/*` (users, jobs, dlq retry, provider-config, kill-switch, content-reports, tickets, metrics, billing-simulate, support-access); every admin mutation writes `audit.events`.

### Internal (engine RPC; not public)
`POST ${ENGINE_URL}/rpc/sympy-equivalent` and `/rpc/run-code` (the engine's Cloud Run URL). Authentication is an HMAC-SHA256 signature over the body plus timestamp (±60s) using `ENGINE_RPC_SECRET`, with replay protection (nonce cache). `/wake` uses its own `ENGINE_WAKE_SECRET`. The engine exposes only `/healthz`, `/wake` and `/rpc/*`; every route except `/healthz` rejects unsigned requests, and all of them are rate-limited. The **sandbox** is never public: its Cloud Run invoker is only the engine's service account, which calls it with a Google-signed ID token from the metadata server.

## 3. Jobs (pgmq)
Queue names = job families. Each message is `{job_id}` only; the payload lives in `jobs.payload` (validated with pydantic). Processing is **woken on demand** (doc 02 §5.0), not by an always-on poller. Workers: `SELECT … pgmq.read(queue, vt=visibility_timeout, qty)` → mark `running` → heartbeat extends the VT → on success `pgmq.delete`; on failure retry with exponential backoff and jitter (max attempts per type) → after max attempts, `pgmq.archive` + `status=dead` + an alert.

| Job type | Queue | Idempotency basis | VT / max attempts | Emits |
|---|---|---|---|---|
| `ingest.document` | `ingest` | document_id + version | 10 min (heartbeat) / 3 | progress; `graph.merge`, `plan.rebalance?` |
| `ingest.syllabus` | `ingest` | document_id | 5 min / 3 | `syllabus_extractions` row + notification |
| `ingest.past_exam` | `ingest` | document_id | 10 min / 3 | questions/rubrics |
| `graph.merge` | `graph` | course_id + graph version | 5 min / 3 | |
| `cards.generate` | `generate` | batch_id | 10 min / 3 | uses the Anthropic **Batch API** when the batch is > 50 cards and not urgent |
| `feynman.analyze` | `generate` | attempt_id | 3 min / 3 | |
| `cheatsheet.build` / `.export` | `generate` | sheet_id + version | 5 min / 3 | PDF to `exports` |
| `mock.build` | `generate` | mock_exam_id | 15 min / 2 | question verification sub-steps |
| `attempt.grade` | `grade` | attempt_id + grade_version | 10 min / 3 | mastery recompute, `plan.rebalance` |
| `attempt.regrade` | `grade` | answer + dispute id | 5 min / 3 | |
| `plan.generate` / `plan.rebalance` | `plan` | user_id + inputs_hash (debounced 60s; coalesced) | 2 min / 3 | calendar write-back |
| `calendar.initial_sync` / `.incremental_sync` / `.writeback` / `.renew_channel` | `calendar` | connection_id + sync token / session version | 2 min / 5 | |
| `srs.optimize` | `srs` | user_id + week | 10 min / 2 | new `fsrs_parameters` |
| `mastery.recompute` | `srs` | user_id + trigger id (debounced) | 2 min / 3 | |
| `anki.import` / `anki.export` | `io` | upload id / request id | 15 min / 2 | |
| `account.export` / `account.delete` | `io` | request id | 30 min / 5 | email |
| `email.send` | `notify` | template + recipient + dedupe key | 1 min / 5 | |
| `notify.digest` | `notify` | user_id + date | 1 min / 3 | |
| `maintenance.*` (retention purges, trash purge, usage rollups, embedding re-index) | `maintenance` | date | — | marked `// CROSS-TENANT-REVIEWED` |

Job types marked long (`ingest.document` over the page threshold or with audio, `ingest.past_exam` with OCR, `srs.optimize`, `anki.*`, `account.export`, `account.delete`, `mock.build`) run as **Cloud Run Job executions**; everything else runs inside the engine service's `/wake` drain.

pg_cron schedules: **engine wake sweeper (every 2 min)**, calendar channel renewal (hourly), polling fallback (15 min), digests (hourly, per timezone bucket), weekly `srs.optimize` fan-out, nightly mastery recompute for users with exams ≤ 14 days away, missed-session detector (every 15 min → `plan.rebalance`), retention purges (nightly), and billing renewal of mock subscriptions (hourly).

**Dead-letter handling:** `status=dead` jobs appear in the admin DLQ. An alert fires if dead jobs exceed 5 in 15 min or queue age exceeds 10 min (Better Stack / Sentry cron monitors).
