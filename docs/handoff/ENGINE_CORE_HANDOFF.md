# Engine-core hand-off (for Codex)

**Branch:** `engine-core` (worktree `C:\Users\baldy\Projects\studyforge-engine-core`), branched from `m0-foundation` at `17409a4`.
**Scope:** only `services/engine/**` (new) and `docs/spec/**` + `docs/handoff/**` (edits). It doesn't touch any M0 scaffolding path, so the merge is conflict-free.
**State:** 414 tests passing (`uv run pytest`), `ruff` clean, `mypy --strict` clean. Built 2026-09-27 by Claude in parallel with Codex.

## 1. Merge it first (next session, before continuing M0)
```bash
git merge --no-ff engine-core -m "merge: engine-core modules and spec corrections"
```
Git allows the merge with uncommitted M0 work present, since the paths don't overlap. Merge **now** rather than at M0-09 so you read the corrected spec (§3) from this point on. Then build on the modules below; don't re-implement them. `services/engine/README.md` has the per-module API map.

### Changes since last merge (`m0-foundation` @ `e8dd778`)
All additive (new files only; no existing module, `pyproject.toml` or `uv.lock` changed unless noted).
1. `algorithms/crunch.py`: exam-crunch mode reference (doc 05 §2) for the TS port. Fixtures `crunch_interval_cap`, `crunch_single_touch`, `crunch_priority_order`, `crunch_multi_exam`.
2. `algorithms/interleave.py`: session interleaving reference (doc 05 §3) for the TS port. Fixtures `interleave_basic`, `interleave_single_unit`, `interleave_confusables`.
3. `engine/llm/` + `services/engine/prompts/`: versioned prompt drafts for every doc 06 §2 LLM task plus `tutor.guard` (the §5.5 post-check), structured-output schemas generated from the engine models, valid/invalid example outputs, an append-only prompt version lock, and injection-safe rendering (§5). **`pyproject.toml` / `uv.lock` changed:** dev-only dependency `jsonschema` (tests validate the examples against the API schemas). Read `services/engine/prompts/README.md` before wiring the gateway.
4. `engine/billing/` (`pricing.py`, `ledger.py`, `events.py`): mock-billing reference (doc 07 §4–6) for the TS `packages/core/billing` port. Fixtures `billing_month_end_anchors`, `billing_proration`, `billing_lifecycle`.

**How to use the TS references:** port the functions one-to-one into `packages/core`, then load the same `services/engine/tests/fixtures/*.json` files in Vitest and assert the same `expected` values. That's the parity check for crunch and interleaving (M7) and billing (M3).

### Claimed by Claude (in progress on `engine-core`; don't build these, use them once they land)
Division of labor: Claude builds pure logic only (algorithms, state machines, output schemas/prompts, eval datasets, Python references + shared JSON fixtures for TS ports). Codex owns all wiring (migrations/RLS, API, jobs, TS packages, UI, infra). Once Codex wires a module, Codex owns it.
| Order | Work | Spec | Needed by |
|---|---|---|---|
| 2 | Review session builder (due/exam/custom/warm-up, new-card ramp, new:review ratio, 200-card offline prefetch) | SRS-06/09 | M7 |
| 3 | Offline review sync reconciliation (idempotent `client_review_id` merge, replay by `reviewed_at`) | SRS-09 | M7 |
| 4 | Labelled eval datasets under `evals/` + runner scoring model-output files via `engine/evals/metrics.py` | doc06 §7 | M4–M8 gates |

## 2. What's done (pure logic, fully tested; no DB/API/UI wiring yet)
| Module (`services/engine/engine/…`) | Spec | Milestone task it pre-builds | Still needed from Codex |
|---|---|---|---|
| `algorithms/fsrs_math.py` | doc05 §1 | M7-01 | verify `DEFAULT_DECAY` against pinned py-fsrs/ts-fsrs in the parity test |
| `algorithms/verification.py` | doc05 §8, SRS-03 | M7-03 | `/rpc/sympy-equivalent` endpoint; code-run + llm_keypoints adapters |
| `algorithms/mastery.py` | doc05 §5, DIAG-06/07 | M8-09 | `mastery.recompute` job, snapshots table writes |
| `algorithms/exam_day.py` | doc05 §7, EXAM-01/02 | M9 | API endpoints; warm-up logs excluded from FSRS |
| `algorithms/blueprint.py` | doc05 §6, DIAG-02 | M8-02 | `mock.build` job |
| `algorithms/fsrs_optimizer.py` | doc05 §1, SRS-02 | M7 | wire py-fsrs trainer/predictor into `srs.optimize` |
| `algorithms/grading.py` | DIAG-04 | M8-06/07 | `attempt.grade` job, LLM rubric call (structured output → `LlmRubricOutput`) |
| `algorithms/question_verify.py` | DIAG-02 | M8-03 | two Sonnet solves + code reference run |
| `algorithms/card_quality.py` | COMP-02 | M6 | call on generate/edit; embeddings for duplicates |
| `algorithms/cheatsheet.py` | COMP-05 | M6 | PDF render (KaTeX), measured heights |
| `algorithms/feynman.py` | COMP-03 | M6 | `feynman.analyze` job + Sonnet call |
| `algorithms/difficulty.py` | DIAG-01 | M8-01 | update `questions.difficulty` after attempts |
| `adapters/catalog.py`, `routing.py`, `breaker.py`, `budget.py` | doc06 §3/§6 | M4-04/05 | persist breaker state/app_config; SQL quota functions mirror `budget.py` |
| `adapters/netguard.py` | SSRF | M4-07 | HTTP client that connects to the pinned IP |
| `adapters/economics.py` | doc07 §8 | M10 / `docs/costs.md` | replace assumptions with measured values |
| `adapters/parse/markdown.py`, `adapters/parse/office.py` | ING-01/03 | M4-09 | Docling/PyMuPDF (M4-08), OCR, STT adapters |
| `ingest/normalized.py` | ING-03/05 | M4 | **contract every parser must emit** |
| `ingest/chunking.py` | ING-06 | M4 | embeddings + chunk inserts |
| `ingest/syllabus.py` | PLAN-01/02, EXAM-03 | M5-01 | `ingest.syllabus` job + Haiku→Sonnet calls + confirm UI |
| `ingest/graph.py` | ING-07 | M4 | `graph.merge` job; edges need `status` column (§3) |
| `ingest/retrieval.py` | doc06 §4, ING-11 | M4/M6 | `search_chunks` RPC feeds it; TS tutor mirrors citation validation |
| `ingest/linking.py` | ING-08 | M4 | link job + confirm/reject UI |
| `planner/timeline.py`, `planner/planner.py` | doc05 §4, PLAN-03..07 | M5 | `plan.generate`/`plan.rebalance` jobs, calendar busy blocks, write-back |
| `interop/anki.py` | SRS-08 | M7 | `anki.import/export` jobs; FSRS replay of imported reviews |
| `notify/policy.py` | NOT-01..04, EXAM-03/04 | M2/M9 | notify jobs, digest cron uses `digest_due()` |
| `privacy/export.py`, `privacy/deletion.py` | DATA-01/02 | M10 | `account.export/delete` jobs; completeness test against the live schema via `unclassified_tables()` |
| `evals/metrics.py` | doc06 §7 | M4–M8 eval gates | suite runners + golden sets |
| `algorithms/crunch.py` | doc05 §2, SRS-04 | M7 (TS `packages/core`) | **port to TS** against the same fixtures; feed deficit to `plan.rebalance` |
| `algorithms/interleave.py` | doc05 §3, SRS-05 | M7 (TS session builder) | **port to TS** against the same fixtures; confusable pairs from `concept_edges` + `embedding_confusables()` |
| `llm/outputs.py`, `llm/schemas.py`, `llm/prompts.py` + `prompts/` | doc06 §2/§5 | M4–M8 (gateway, every LLM job) | send `schemas/<task>.v1.json` as `output_config.format`; validate with `parse_output()`; render with `prompts.render()`; add `tutor.guard` to `catalog.HAIKU_TASKS`/routing; TS gateway loads the same prompt files and mirrors `neutralize()` |
| `billing/pricing.py`, `billing/ledger.py`, `billing/events.py` | doc07 §4–6 | M3 (TS `packages/core/billing`) | **port to TS** against the billing fixtures: `MockProvider` = `ledger.py` commands, `handleBillingEvent()` = `events.apply_event`; tables `subscriptions`/`invoices`/`billing_events`/`mock_ledger`; gapless numbering via a per-year counter row; emails per `EMAIL_TEMPLATES`; pg_cron hourly `tick`, daily `reconcile` |

Doc 05 fixtures with **hand-computed** values live in `services/engine/tests/fixtures/` (mastery, readiness, cram queue, warm-up, optimizer adopt/reject). The planner scenarios (single exam, prereq order, deficit, two exams, DST, missed session, low score, busy change) and property tests are in `tests/test_planner.py`.

## 3. Spec changes made on this branch (also in the owner's vault master)
1. **Embeddings are one global provider** for all plans (doc 06); `routing.validate_config()` enforces it.
2. **`cards.cloze_index smallint`**: one card and one FSRS state per cloze deletion, matching Anki (doc 03).
3. **`concept_edges.status enum(active, removed_by_user)`**: user deletions are tombstones so re-ingestion can't resurrect them (doc 03).
4. **The planner runs in the Python engine** (it's the `plan.generate`/`plan.rebalance` job), not `packages/core`. TS core keeps the online review path: FSRS scheduling, crunch capping and interleaving (docs 02, 05).
5. **Plan quotas aligned with the daily AI caps** (owner decision): Free-plan tutor runs on **Haiku**; tutor quotas are **13/60/200 per day** (Free/Pro/Pro+); **mock-exam jobs (`mock.build`, `attempt.grade`, `attempt.regrade`) are exempt from the daily cap** and limited by the monthly mock quota (docs 06, 07; `budget.CAP_EXEMPT_JOBS`).

## 4. Environment facts
- Python 3.12.14 via uv. `UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.uv\python` is set as a user env var: MSIX-packaged agent apps virtualize `%APPDATA%`, which breaks uv's minor-version link ("Missing expected target directory"). Keep it.
- uv, pnpm, Google Cloud CLI and Terraform are installed (the owner ran winget). Check `gcloud auth list` before assuming login.
- The engine depends on `tzdata` (Windows and slim images have no tz database) and closes SQLite handles explicitly (Windows file locks).

## 5. Not done here (yours)
Engine FastAPI app, `/wake` drain, job framework, DB access (M0-09..11); all migrations/RLS; the TS online review path (FSRS scheduling via ts-fsrs; crunch capping and interleaving ported from `crunch.py` / `interleave.py`; billing state machine); ML adapters (Docling, PaddleOCR/TrOCR, faster-whisper, fastembed); every UI. When wiring each module, cite its tests as checklist evidence and mark the related Engineering Checklist items.

## 6. Spec interpretations (where the spec left a detail open; the TS port must match)
- **Crunch `w_c`** = Σ over the card's in-scope concepts of (unit weight ÷ concepts in the unit) ÷ total unit weight of the exam. Concept shares sum to 1, so `w_c` ∈ [0,1] without further scaling. (`exam_day.cram_queue` keeps its per-card share, which is a different, EXAM-01-only quantity.)
- **`days_to_exam`** is fractional days (review/queue time → exam start), for both the 7-day trigger and the ≥ 2-day new-card rule.
- **Crunch with `T ≤ 1.5`** goes to the cram window even if the single-touch condition holds: the touch at `T − 1` would fall inside that window or in the past. For `T > 1.5` the spec precedence applies (single touch first, then `min(I_fsrs, I_cap)`). Crunch intervals are fractional days and never fuzzed.
- **Interleaving tie-break:** equal remaining counts go to the unit first seen in the candidate list. There is no randomness, so the `session_id` seed isn't needed for determinism.
- **Mixed-type slots:** `round_half_up(0.15 × session size)` questions, capped by the questions in scope, **replace** the lowest-priority cards ("in place of a card"); displaced cards are returned and stay due.
- **Billing proration:** by the second on list prices, half-up per line, then the Beta line cancels a positive subtotal. A change that leaves a negative subtotal (e.g. Pro yearly → Pro+ monthly) is $0 due plus an account credit (Stripe's default); during beta that credit has no monetary value.
- **Billing plan changes:** a higher plan, or the same plan monthly → yearly, is an upgrade (immediate); an interval change resets the anchor to the change instant. An upgrade clears a pending cancellation or scheduled downgrade. Choosing the current price while a downgrade is scheduled cancels the downgrade.
- **Billing dunning:** soft and hard failures behave identically in the mock (7-day grace, no automatic retries); `failure_kind` only picks the email wording. Renewals pause while `past_due` and catch up after recovery. The plan resolves to Free the moment grace ends, even before the provider's deletion event lands.
- **Invoice numbers** restart at `SF-YYYY-000001` each calendar year (the spec's format includes the year).

## 7. Open questions for the owner
1. **Doc 07 §3 entitlements example says `tutor_messages_per_day: 20`**, but the plan table (and the earlier owner decision) says **13/day** for Free. The code (`budget.py`, `economics.py`) uses 13. Please confirm 13 and fix the example in the vault's doc 07 §3 (left unchanged: the vault is read-only for Claude).
