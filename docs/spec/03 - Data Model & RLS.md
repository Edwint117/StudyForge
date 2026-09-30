---
title: StudyForge — Data Model & RLS
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, data-model]
---

# 03: Data Model & RLS

This is the **contract** for the schema. The agent writes the actual DDL in migrations, but must keep these names, relationships and rules. Deviations need an ADR.

## 1. Conventions
- **Primary keys:** `uuid` generated with `uuidv7()` (time-ordered; use the `pg_uuidv7` extension, or a SQL function if it's unavailable). Never sequential IDs in URLs. The only exception is `invoices.number` (a gapless sequence for display).
- **Tenant key:** `user_id uuid not null references auth.users(id) on delete cascade` on **every** user-data table, even child tables, so RLS never needs joins. It is indexed. A composite FK `(parent_id, user_id)` → parent `(id, user_id)` guarantees a child can't point at another user's parent.
- **Timestamps:** `created_at timestamptz not null default now()`, `updated_at` (trigger), and `deleted_at` only where soft delete is specified.
- **Delete strategy:** hard delete by default (privacy-first). Soft delete only on `courses` and `documents` (30-day trash, purged by pg_cron). Account deletion hard-deletes everything (DATA-02).
- **Money:** `bigint` cents plus `char(3)` currency. **Time:** always `timestamptz`, plus the user's IANA timezone in `profiles.timezone`. Durations are stored as integer seconds or minutes, named with the unit suffix (`duration_min`).
- **Enums:** Postgres enums for stable sets; `text` + `check` for sets that may grow.
- **Naming:** snake_case, plural tables, `*_id` FKs, `is_*`/`has_*` booleans, `*_at` timestamps.
- **Schemas:** `public` (app), `audit` (append-only), `billing` (plans/subscriptions/invoices), `private` (security-definer helpers, not exposed via the API). Exposed API schemas: `public` only; billing is read through views or RPCs.

## 2. RLS standard (apply to every user-data table)
```sql
alter table public.<t> enable row level security;
alter table public.<t> force row level security;
create policy "<t>_select_own" on public.<t> for select to authenticated using (user_id = (select auth.uid()));
create policy "<t>_insert_own" on public.<t> for insert to authenticated with check (user_id = (select auth.uid()));
create policy "<t>_update_own" on public.<t> for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy "<t>_delete_own" on public.<t> for delete to authenticated using (user_id = (select auth.uid()));
```
- Read-only-for-users tables (e.g. `card_states` is written only by the API/RPC, `usage_events`, `jobs`) get **select only**. Writes go through `security definer` RPCs in `private` that re-check `auth.uid()`.
- **Column protection** (mass assignment): sensitive columns (`profiles.role`, `profiles.suspended_at`, `subscriptions.*`, `documents.status`, `usage_*`) can't be updated by `authenticated`. Enforce this with column-level `grant update (col, …)` plus a trigger guard.
- The `anon` role has no access to any table except `plans` (public pricing) and `legal_documents` (published).
- **Storage policies:** object path prefix `{user_id}/…`; `storage.foldername(name)[1] = auth.uid()::text` for select/insert/update/delete on all buckets. `exports` is read-only to the user.
- **Realtime:** private channels only (`user:{uid}`), with authorization via RLS on `realtime.messages`.
- **Tests (pgTAP)** use a matrix generated from `information_schema`: for every table with `user_id`, as user A try select/insert/update/delete on B's row → expect 0 rows or an error. Also assert RLS is enabled on every `public` table (a test fails if a new table lacks it).

## 3. Tables by domain
Legend for PII tier: **T0** public · **T1** internal · **T2** personal (account/contact) · **T3** sensitive user content (their uploads, answers, voice) · **T4** secrets (tokens), which are encrypted at the application or Vault level.

### 3.1 Identity & account
| Table | Key columns | PII |
|---|---|---|
| `profiles` | `id` (= auth.users.id, PK), `display_name`, `timezone`, `locale`, `birth_year smallint`, `age_verified_at`, `role enum(user,admin,support)` (**not user-writable**), `onboarding_state jsonb`, `suspended_at`, `deletion_scheduled_at` | T2 |
| `user_settings` | `user_id` PK, `daily_max_min`, `earliest_time`, `latest_time`, `rest_weekdays smallint[]`, `min_block_min=25`, `max_block_min=120`, `desired_retention numeric(3,2)=0.90`, `crunch_days=7`, `interleave bool=true`, `theme`, `a11y jsonb` | T1 |
| `legal_documents` | `id`, `kind enum(tos,privacy,cookies,dpa,sla,aup,refunds)`, `version`, `published_at`, `content_md`, `is_draft` | T0 |
| `legal_acceptances` | `user_id`, `document_id`, `accepted_at`, `ip_hash`, `user_agent` | T2 |
| `consent_records` | `user_id` nullable, `anon_id`, `categories jsonb`, `gpc bool`, `recorded_at`, `policy_version` | T2 |
| `webauthn_credentials` | (if ADR-0005 needs it) `user_id`, `credential_id`, `public_key`, `sign_count`, `transports`, `name` | T2 |
| `mfa_recovery_codes` | `user_id`, `code_hash`, `used_at` | T4 |
| `support_access_grants` | `user_id`, `granted_to_admin_id`, `scope`, `expires_at`, `revoked_at` | T1 |

### 3.2 Courses & ingestion
| Table | Key columns | PII |
|---|---|---|
| `courses` | `id`, `user_id`, `title`, `code`, `term`, `color`, `icon`, `archived_at`, `deleted_at` | T3 |
| `units` | `id`, `user_id`, `course_id`, `title`, `ordinal`, `weight_pct numeric(5,2)`, `week_start date` | T3 |
| `documents` | `id`, `user_id`, `course_id`, `kind enum(material,syllabus,past_exam,lab,textbook,lecture_audio,notes_handwritten)`, `mime`, `bytes`, `sha256`, `storage_path`, `status enum(uploading,queued,processing,ready,failed,cancelled)`, `page_count`, `duration_s`, `version`, `supersedes_id`, `providers_used jsonb`, `error_code`, `error_detail`, `deleted_at` | T3 |
| `document_assets` | `id`, `user_id`, `document_id`, `kind(image,slide_render,figure,audio_segment)`, `storage_path`, `page`, `bbox jsonb` | T3 |
| `chunks` | `id`, `user_id`, `course_id`, `document_id`, `ordinal`, `content_md`, `content_type enum(definition,theorem,proof,formula,example,code,text,question)`, `page`, `slide`, `t_start_ms`, `t_end_ms`, `token_count`, `ocr_confidence`, `embedding vector(384)`, `embedding_model text`, `fts tsvector generated`, `content_hash` | T3 |
| `concepts` | `id`, `user_id`, `course_id`, `name`, `slug`, `kind enum(concept,definition,formula,theorem,algorithm,procedure)`, `summary_md`, `latex`, `importance real`, `is_user_edited bool`, `merged_into_id` | T3 |
| `concept_edges` | `user_id`, `from_id`, `to_id`, `kind enum(prerequisite_of,part_of,related_to,confusable_with)`, `confidence`, `source enum(ai,user)`, `status enum(active,removed_by_user)` (user deletions are kept as tombstones so re-ingestion can't resurrect them); PK `(from_id,to_id,kind)`; check `from_id<>to_id`; cycle prevention for `prerequisite_of` in the RPC | T3 |
| `concept_chunks` | `user_id`, `concept_id`, `chunk_id`, `role enum(defines,uses,example_of)` | T3 |
| `unit_concepts` | `user_id`, `unit_id`, `concept_id` | T3 |
| `asset_links` | `id`, `user_id`, `from_chunk_id`, `to_chunk_id` null, `to_question_id` null, `kind enum(slide_textbook,lecture_lab,material_past_exam,transcript_slide)`, `confidence`, `status enum(suggested,confirmed,rejected)` | T3 |

Indexes: `chunks` HNSW on `embedding vector_cosine_ops` (with `m=16, ef_construction=64`), GIN on `fts`, btree `(user_id, course_id)`, and `(document_id, ordinal)`. Hybrid search is an RPC `search_chunks(q text, q_emb vector, course_ids uuid[], k int)` that runs with the caller's RLS (`security invoker`).

### 3.3 Planning & calendar
| Table | Key columns | PII |
|---|---|---|
| `exams` | `id`, `user_id`, `course_id`, `title`, `kind enum(quiz,midterm,final,other)`, `starts_at`, `duration_min`, `weight_pct`, `location`, `readiness_target=0.85`, `status enum(upcoming,done,cancelled)`, `actual_score_pct`, `policies jsonb` (calculator, formula_sheet, id_required, scratch_paper…) | T3 |
| `exam_units` / `exam_concepts` | scope of the exam | T3 |
| `syllabus_extractions` | `id`, `user_id`, `document_id`, `payload jsonb` (fields + source spans + confidence), `status enum(pending_review,confirmed,discarded)` | T3 |
| `availability_rules` | `id`, `user_id`, `weekday`, `start_time`, `end_time`, `kind enum(available,busy)` | T2 |
| `busy_blocks` | `id`, `user_id`, `source text check (source in ('google','manual'))`, `connection_id`, `external_id`, `starts_at`, `ends_at`, `is_all_day`, `title_hash` (we **don't store event titles**, only the time) | T2 |
| `calendar_connections` | `id`, `user_id`, `provider text check (provider in ('google'))` (a check constraint, not an enum, so providers can be added later), `account_email`, `vault_secret_id` (refresh token in Vault), `scopes text[]`, `target_calendar_id`, `sync_token`, `channel_id`, `channel_resource_id`, `channel_expires_at`, `status enum(active,needs_reauth,error,revoked)`, `last_synced_at` | T4/T2 |
| `study_plans` | `id`, `user_id`, `exam_id` null (null = multi-exam master plan), `version int`, `algorithm_version`, `inputs_hash`, `status enum(active,superseded)`, `feasibility jsonb`, `generated_at`, `change_summary jsonb` | T3 |
| `study_sessions` | `id`, `user_id`, `plan_id`, `exam_id`, `kind enum(learn,review,practice,mock,buffer,consolidation,cram,rest)`, `starts_at`, `ends_at`, `unit_ids uuid[]`, `concept_ids uuid[]`, `status enum(planned,in_progress,done,missed,skipped)`, `is_locked`, `skip_reason`, `external_event_refs jsonb`, `rationale text` | T3 |

### 3.4 Comprehension
| Table | Key columns | PII |
|---|---|---|
| `cards` | `id`, `user_id`, `course_id`, `type enum(basic,reversed,cloze,concept_map,math_step,code,free_explain)`, `front_md`, `back_md`, `cloze_md`, `cloze_index smallint` (which `{{cN::…}}` deletion this card tests; one card row, and one FSRS state, per deletion, matching Anki; null for non-cloze), `answer_spec jsonb` (check: `text|sympy|numeric|code_tests|llm_keypoints` + params), `source_chunk_ids uuid[]`, `concept_ids uuid[]`, `status enum(draft,active,suspended,rejected)`, `flags text[]` (source_changed, duplicate_suspect, lint_warn), `origin enum(ai,user,anki_import)`, `generation_id`, `content_hash`, `tags text[]` | T3 |
| `generation_batches` | `id`, `user_id`, `scope jsonb`, `status`, `counts jsonb`, `model`, `prompt_version` | T3 |
| `feynman_attempts` | `id`, `user_id`, `concept_id`, `explanation_md`, `audio_path`, `analysis jsonb` (coverage, missing_steps[], buzzwords[], errors[{claim, correction, citation}], followups[]), `score`, `model`, `prompt_version` | T3 |
| `tutor_threads` | `id`, `user_id`, `course_id`, `title`, `mode enum(socratic,explain,check_work)` | T3 |
| `tutor_messages` | `id`, `user_id`, `thread_id`, `role enum(user,assistant)`, `content_md`, `citations jsonb[]` (chunk_id, quote span), `hint_level`, `model`, `tokens_in`, `tokens_out`, `blocked_reason` | T3 |
| `cheat_sheets` | `id`, `user_id`, `course_id`, `exam_id`, `items jsonb` (ordered concept refs + edits), `page_budget`, `layout jsonb`, `exported_path` | T3 |

### 3.5 Retention (SRS)
| Table | Key columns | PII |
|---|---|---|
| `card_states` | `card_id` PK, `user_id`, `state enum(new,learning,review,relearning)`, `stability real`, `difficulty real`, `due timestamptz`, `last_review`, `reps`, `lapses`, `step`, `is_buried_until`, `fsrs_version` | T3 |
| `review_logs` | `id`, `user_id`, `card_id`, `client_review_id uuid UNIQUE(user_id, client_review_id)`, `rating smallint check 1..4`, `proposed_rating`, `self_override bool`, `mode enum(normal,crunch,interleaved,warmup,cram,custom)`, `state_before jsonb`, `state_after jsonb`, `elapsed_days real`, `scheduled_days real`, `response_ms int`, `answer_text`, `verification jsonb` (method, correct bool, detail), `reviewed_at`, `synced_at` | T3 |
| `fsrs_parameters` | `id`, `user_id`, `params real[]`, `fsrs_version`, `review_count`, `logloss`, `rmse`, `is_active`, `created_at` | T1 |
| `review_sessions` | `id`, `user_id`, `kind`, `exam_id`, `started_at`, `ended_at`, `item_count`, `settings jsonb` | T3 |

Indexes: `card_states (user_id, due)`, `review_logs (user_id, card_id, reviewed_at)`.

### 3.6 Diagnostics
| Table | Key columns | PII |
|---|---|---|
| `questions` | `id`, `user_id`, `course_id`, `unit_id`, `concept_ids uuid[]`, `type enum(mcq,short,numeric,multi_step,code,proof)`, `stem_md`, `choices jsonb`, `answer_spec jsonb`, `steps jsonb`, `points`, `difficulty real`, `origin enum(past_exam,user,generated)`, `verification jsonb` (for generated: two solves + sympy + code result), `is_verified`, `source_chunk_ids uuid[]`, `times_used` | T3 |
| `rubrics` | `id`, `user_id`, `question_id`, `criteria jsonb` (`[{id, description, points, common_errors[]}]`), `total_points`, `origin enum(instructor,generated,user)` | T3 |
| `mock_exams` | `id`, `user_id`, `exam_id`, `blueprint jsonb`, `question_ids uuid[]` (ordered), `duration_min`, `strictness enum(standard,strict)`, `total_points` | T3 |
| `attempts` | `id`, `user_id`, `mock_exam_id`, `started_at`, `deadline_at`, `submitted_at`, `status enum(in_progress,submitted,auto_submitted,grading,graded,abandoned)`, `score`, `max_score`, `integrity_events jsonb[]`, `flagged bool` | T3 |
| `attempt_answers` | `attempt_id`, `user_id`, `question_id`, `response jsonb`, `saved_at`, `awarded_points`, `max_points`, `deductions jsonb[]` (`{criterion_id, points, reason_md, error_class, citation}`), `graded_by enum(deterministic,llm,hybrid,user_dispute)`, `grader_model`, `grade_confidence`, `dispute_md`, `regraded_at`; PK `(attempt_id, question_id)` | T3 |
| `mastery_snapshots` | `id`, `user_id`, `scope enum(concept,unit,course)`, `scope_id`, `mastery real`, `components jsonb`, `error_mix jsonb`, `computed_at` | T3 |
| `exam_checklist_items` | `id`, `user_id`, `exam_id`, `label`, `kind`, `is_done`, `source enum(syllabus,default,user)` | T3 |

### 3.7 Platform: jobs, usage, notifications, support
| Table | Key columns | PII |
|---|---|---|
| `jobs` | `id`, `user_id`, `type`, `status enum(queued,running,succeeded,failed,cancelled,dead)`, `progress jsonb`, `payload jsonb`, `result jsonb`, `error`, `attempts`, `max_attempts`, `idempotency_key UNIQUE(user_id,type,idempotency_key)`, `pgmq_msg_id`, `started_at`, `finished_at`, `trace_id` | T1 |
| `idempotency_keys` | `user_id`, `key`, `route`, `request_hash`, `response_status`, `response_body jsonb`, `expires_at` (24h); PK `(user_id,key,route)` | T1 |
| `usage_events` | `id`, `user_id`, `meter enum(ai_input_tokens,ai_output_tokens,ai_cost_micros,ingest_pages,audio_seconds,ocr_pages,storage_bytes,tutor_messages,cards_generated,mock_exams,feynman_analyses,code_runs)`, `quantity bigint`, `cost_micros bigint`, `provider`, `model`, `task`, `job_id`, `idempotency_key UNIQUE`, `occurred_at` | T1 |
| `usage_counters` | `user_id`, `meter`, `period_start`, `quantity` (maintained by a trigger; the fast quota check) | T1 |
| `notifications` | `id`, `user_id`, `category`, `title`, `body_md`, `link`, `read_at`, `created_at` | T2 |
| `notification_preferences` | `user_id`, `category`, `channel enum(in_app,email,push)`, `enabled`, `quiet_hours jsonb` | T1 |
| `push_subscriptions` | `user_id`, `endpoint`, `p256dh`, `auth`, `created_at` | T4 |
| `email_suppressions` | `email_hash`, `reason`, `created_at` | T1 |
| `email_outbox` | `id`, `user_id` null, `to_email` (T2), `template`, `category`, `subject`, `html`, `text`, `source enum(app,auth_hook)`, `dedupe_key UNIQUE`, `status enum(delivered_to_outbox,suppressed)`, `created_at`. **Admin-read only** (the recipient sees an in-app notification instead) | T2 |
| `private.rate_limit_buckets` | `key` (hashed user/IP + bucket), `window_start`, `count`, `expires_at`. `UNLOGGED`, not exposed via the API | T1 |
| `support_tickets` / `support_messages` | `id`, `user_id`, `category`, `status`, `body_md`, `diagnostics jsonb` (consented), `attachments` | T2/T3 |
| `content_reports` | `id`, `user_id`, `target_type`, `target_id`, `reason`, `detail_md`, `status` | T3 |
| `data_requests` | `id`, `user_id`, `kind enum(export,deletion)`, `status`, `requested_at`, `scheduled_for`, `completed_at`, `artifact_path`, `expires_at` | T2 |
| `app_config` | `key`, `value jsonb`, `version`, `updated_by`, `updated_at`: provider routing (doc 06), AI kill switch, global budgets. **Admin-only.** History is kept in `app_config_history` | T1 |

### 3.8 Billing (schema `billing`, doc 07)
`plans`, `plan_prices`, `subscriptions`, `checkout_sessions`, `invoices` (+ `invoice_lines`), `billing_events` (inbound provider events, `UNIQUE(provider, event_id)`), `entitlement_overrides` (admin grants). Users can read their own subscription and invoices through `public.v_my_subscription` and `public.v_my_invoices` views (security invoker plus a `user_id` filter). Only the billing service code path writes to them.

### 3.9 Audit (schema `audit`)
`audit.events`: `id`, `occurred_at`, `actor_type enum(user,admin,system,engine)`, `actor_id`, `subject_user_id`, `action` (dotted: `auth.login.succeeded`, `auth.mfa.enrolled`, `admin.user.suspended`, `data.export.requested`, `billing.plan.changed`, `authz.cross_tenant_denied` …), `target_type`, `target_id`, `outcome`, `ip_hash`, `user_agent`, `request_id`, `metadata jsonb` (no secrets or content).
- Insert only via `private.audit_log()` security definer. **No UPDATE/DELETE grants to anyone** except the retention job role, and that role can only delete rows older than the retention period.
- Supabase auth events are mirrored in via an auth hook or log drain.

## 4. Retention schedule (implemented as pg_cron jobs; must match the Privacy Policy)
| Data | Retention |
|---|---|
| User content (T3) | Until the user deletes it, or the account is deleted (no off-platform backups exist; ADR-0018) |
| Trashed courses/documents | 30 days |
| `review_logs` | Life of the account (needed for FSRS) |
| `tutor_messages` | Life of the thread; user can delete |
| `jobs` | 30 days after finish (payload redacted at 7 days) |
| `idempotency_keys` | 24h |
| `usage_events` | 25 months (billing disputes and analytics) → aggregate |
| `audit.events` | 400 days |
| `consent_records`, `legal_acceptances` | Life of the account + 3 years (proof of consent) |
| Exports in Storage | 7 days |
| `email_outbox` | 30 days |
| Application logs (web host/Cloud Logging/Sentry) | ≤ 30 days (set Cloud Logging bucket retention to 30 days) |
| Langfuse traces | 30 days, content redacted |
| Invoices (mock) | 7 years (mirrors real legal requirements once live) |

## 5. Data footprint map (for export and deletion; keep it in `docs/data-map.md`)
Supabase Postgres (all tables above) · Supabase Storage (4 buckets) · Supabase Auth (`auth.users`, sessions, MFA factors) · Vault secrets (calendar tokens) · PostHog (person + events) · Sentry (events, scrubbed) · Langfuse (traces) · `email_outbox` (rendered emails) · Anthropic (API inputs; retention per Anthropic's commercial terms) · optional paid adapters (Deepgram/AssemblyAI/Mistral/Voyage, per their retention policies) · Google Calendar (the events *we* created in the user's calendar, deleted on disconnect if the user chooses) · Better Stack (none).
