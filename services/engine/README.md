# StudyForge engine

Python 3.12 package for the engine service (doc 02 §2). This branch (`engine-core`) contains **pure, tested
algorithm modules only**: no FastAPI app, database access, queue consumer, or ML adapters yet. Those are added
in M0-09 / M4 and should *call* these modules rather than re-implement them.

## Modules (`engine/algorithms/`)
| Module | Spec | What it provides |
|---|---|---|
| `fsrs_math.py` | doc 05 §1 | FSRS-6 retrievability, interval, rounded review interval, log-loss. `DEFAULT_DECAY` must be checked against the pinned py-fsrs/ts-fsrs defaults in M7-01 |
| `verification.py` | doc 05 §8, SRS-03 | `TextSpec` / `NumericSpec` / `SympySpec` (discriminated `AnswerSpec` for `cards.answer_spec`), `verify()`, text (NFKC, Levenshtein "close"), unit-aware numeric (pint), LaTeX equivalence (numeric sampling + killable symbolic fallback, 2 s timeout), `propose_rating()` |
| `mastery.py` | doc 05 §5, DIAG-06/07 | `concept_mastery()` (mastery-1), `weighted_mastery()`, `mastery_by_unit()`, `error_mix()`, `readiness_forecast()` with `fit_calibration()` |
| `exam_day.py` | doc 05 §7, EXAM-01/02 | `cram_queue()`, `select_cram_units()`, `crunch_priority()`, `warmup_selection()` |
| `blueprint.py` | doc 05 §6, DIAG-02 | `build_blueprint()` (points by weight × weakness, type mix, difficulty mean 3), `select_questions()`, `drop_slot()` |
| `fsrs_optimizer.py` | doc 05 §1, SRS-02 | `evaluate_candidate()` adoption rule (≥400 reviews, 80/20 chronological split, ≥1% log-loss gain) with injectable trainer/predictor, `keep_recent()` |
| `grading.py` | DIAG-04, M8-06/07 | `grade_mcq()` (multi-select partial credit), `grade_typed()` with error-class heuristics, `grade_multi_step()`, `grade_with_rubric()` (strict validation of the LLM rubric output), `attempt_score()`, `apply_regrade()` |
| `question_verify.py` | DIAG-02, M8-03 | `verify_generated_question()` (two independent solves + key must agree; code needs a passing reference run), `next_action()` retry/drop policy |
| `difficulty.py` | DIAG-01 | `calibrated_difficulty()`: failure rate shrunk toward the prior level, mapped to a fractional 1–5 level |
| `card_quality.py` | COMP-02 | `lint_card()` blocking errors (empty sides, answer leakage incl. cloze, malformed cloze, unbalanced LaTeX) + warnings; `text_duplicates()` shingle pre-check, `embedding_duplicates()` cosine > 0.92 |
| `cheatsheet.py` | COMP-05 | `fit_sheet()`: most readable layout fitting everything in full, else with short variants, else best-priority partial fit (pinned guaranteed) |
| `feynman.py` | COMP-03 | `analyze()` validates the model output, downgrades unquoted "covered" claims, deterministic score; `gaps_to_cards()` |

## Adapters routing (`engine/adapters/`), doc 06 §3/§6, M4-04/05/07
| Module | What it provides |
|---|---|
| `catalog.py` | Adapter catalog (tiers `free` / `core_llm` / `paid`, required env, cost models), task list, `default_routing()` seed for `app_config.providers` |
| `routing.py` | `resolve()` / `require()` (plan rule: Free never paid; key present; breaker; `degraded`/`killed` budget profiles), `validate_config()` for Provider Settings saves (incl. **one global embedding model**) |
| `breaker.py` | `CircuitBreaker` (5 consecutive or >50% of ≥4 calls in 60 s → open 120 s → single half-open probe) |
| `budget.py` | `can_reserve()` / `reconcile()` daily AI caps per plan, `global_budget_state()` (alerts 50/80/100%, degrade at 100%, kill at 120%) |
| `netguard.py` | SSRF policy: `check_url()`, `resolve_public()` (resolve once, all addresses public, pinned IP), `next_hop()` redirect re-validation, `HostAllowlist`, `VENDOR_HOSTS` |
| `economics.py` | doc 07 §8: per-action AI costs from catalog prices, p50/p90 plan costs with daily caps (mock exams exempt), gross margin, `quota_cap_conflicts()`; assumptions are constants to replace with measured values |

## Ingestion (`engine/ingest/`), ING-03/05/06
| Module | What it provides |
|---|---|
| `normalized.py` | `NormalizedDoc` / `Block`: **the contract every parser adapter (Docling, PyMuPDF, pptx, docx, OCR, STT) must emit** |
| `chunking.py` | `chunk_document()`: heading paths, slide/label/code/QED boundaries, typed chunks (definition/theorem/proof/formula/example/code/question/text), ≤400 estimated tokens incl. heading prefix (fits bge-small's 512), transcript 90 s windows, content hashes, OCR confidence carry-through |
| `syllabus.py` | PLAN-01/EXAM-03: sourced-field schema, `validate_extraction()` (span support, ambiguous dates, weights, term, duplicates), Haiku→Sonnet escalation, `to_exam_drafts()`, `checklist_seeds()` |
| `graph.py` | ING-07: `merge_concepts()` canonical merge (names/aliases/plurals/embeddings), `plan_edges()` DAG-safe prerequisites, user edits and user-removed edges preserved |
| `retrieval.py` | doc 06 §4 / ING-11: `rrf_fuse()`, `rerank()`, `pack_context()`, `has_relevant_material()`, `retrieve()`, `validate_citations()` |
| `linking.py` | ING-08: `link_kind()`, `link_confidence()`, `suggest_links()` (rejected pairs never re-suggested) |

## LLM task contracts (`engine/llm/` + `prompts/`), doc 06 §2/§5
| Module | What it provides |
|---|---|
| `llm/outputs.py` | Structured-output models for `cards.generate` (with `KeypointsSpec`), `cards.lint`, `ingest.tag_chunks`, `ingest.extract_concepts` (`to_extracted()` → graph merge), `ingest.link_assets`, `question.generate` (shape rules per type), `question.solve`, `answer.keypoints`, `cheatsheet.compress`, `ocr.vision`, `tutor.guard` |
| `llm/schemas.py` | `TASK_OUTPUTS` (task → model, reusing `LlmRubricOutput`, `FeynmanOutput`, `SyllabusExtraction`), `api_schema()` (structured-output subset), `api_subset_violations()`, `parse_output()` (strict JSON validation); CLI `--write` regenerates `prompts/schemas/` |
| `llm/prompts.py` | Prompt loader (front matter + static `system` / cached `context` / `user`), `render()` with automatic delimiting of untrusted inputs, `neutralize()`, `course_material()`, `turn_directive()` (tutor modes and hint levels 1–3), append-only version lock (`--lock`) |

`prompts/` holds the 15 v1 prompt drafts, generated schemas, valid/invalid example outputs and `versions.lock.json`. See `prompts/README.md`.

## Other packages
| Module | What it provides |
|---|---|
| `interop/anki.py` | SRS-08: `export_apkg()` (stable ids/GUIDs), `import_apkg()` (cards incl. per-deletion cloze, suspension, media, review log), Markdown⇄Anki HTML |
| `notify/policy.py` | NOT-01..04 / EXAM-03/04: preference matrix with locked channels, quiet hours deferral, exam-day suppression, `exam_reminder_times()`, `countdown_times()`, `digest_due()` (DST-safe) |
| `privacy/export.py` | DATA-01: `EXPORT_POLICY` for all 68 tables, `unclassified_tables()` (completeness test), `build_export_zip()` |
| `privacy/deletion.py` | DATA-02: grace period, `plan_deletion()` ordered idempotent steps, `remaining_steps()`, `verify_erasure()` |
| `evals/metrics.py` | doc 06 §7: P/R/F1, syllabus field F1, concept P/R, grading MAE + error-class accuracy, answer-leak detection, citation validity, CER/WER, `GATES` + `check_gates()` |
| `adapters/parse/markdown.py` | `parse.markdown` / `parse_text`: headings, code, display math, lists, tables, Obsidian wikilinks/front matter |
| `adapters/parse/office.py` | `parse.pptx` (per-slide headings, bullets, tables, alt text, speaker notes) and `parse.docx` (heading/list styles, tables) |
| `planner/timeline.py` + `planner/planner.py` | doc 05 §4 / PLAN-03..07: DST-safe free windows, `generate_plan()` (reservations, prerequisite-aware learn blocks, urgency across exams, spaced reviews, practice, buffers, feasibility + options, rationales) and `rebalance()` (freeze, carry-forward, remediation, keep valid slots, nearest-slot moves, change summary). Runs as the `plan.generate` / `plan.rebalance` jobs |

## TypeScript references (`engine/algorithms/`), ported into `packages/core`
The online review path runs in TypeScript (doc 05 §1–3). These modules are its **exact reference**: the TS port
must load the same fixture files and produce the same results (M7 parity test).
| Module | Spec | What it provides |
|---|---|---|
| `crunch.py` | doc 05 §2, SRS-04 | `applicable_exam()` (earliest in-scope exam ≤ 7 days), `card_weight()` (w_c), `crunch_interval()` (single touch → cap → cram window), `schedule_review()`, `build_crunch_queue()` (priority via `exam_day.crunch_priority()`, capacity, deficit, new cards) |
| `interleave.py` | doc 05 §3, SRS-05 | `round_robin()` (weighted by remaining share, no avoidable same-unit adjacency), `place_confusables()` (within 3 positions), `mixed_type_slots()` (~15%), `interleave()`, `embedding_confusables()` |
| `billing/pricing.py` | doc 07 §2/§5–6: prices, month-end-anchored UTC periods (`add_months`, `period_bounds`, `period_index`), `preview_change()` proration with the beta discount and account credit, gapless `next_invoice_number()` |
| `billing/ledger.py` | Mock provider state machine: `confirm_checkout`, `start_trial`, `change_plan`, `cancel`, `resume`, `tick` (renewals/period-end changes/grace expiry), `simulate_payment_failure`/`simulate_recovery`; emits versioned `ProviderEvent`s |
| `billing/events.py` | `handleBillingEvent` reference: `apply_event`/`apply_all` (idempotent, order-tolerant), transition `Effect`s (audit/email/entitlement sync), `effective_plan`, `dunning_reminders`, `downgrade_impact`, `reconcile` |
| `srs/session.py` | SRS-06/09: `build_session()` for due/exam/custom/crunch/warm-up, `NewCardPolicy` + `daily_new_limit()` (ramp-in, backlog guard), `study_day()`, `offline_prefetch()` (200 cards + media), `due_count()` |
| `srs/sync.py` | SRS-09: `reconcile_batch()` (idempotent `client_review_id` merge, rejections, per-card replay in `reviewed_at` order with rewritten `state_before/after`, warm-up excluded), `merge_logs()` |

Not here, by design: code-run checks (`code_tests`, sandbox adapter), `llm_keypoints` (LLM gateway), and FSRS
state transitions (ts-fsrs online, py-fsrs for the optimizer).

## Fixtures
`tests/fixtures/*.json` carry the doc 05 fixtures with **hand-computed** expected values (each has a `_doc`
explaining the arithmetic): `mastery_components`, `mastery_missing_components`, `readiness_band`,
`cram_queue_order`, `warmup_selection`, `optimizer_adopt`, `optimizer_reject`, `crunch_interval_cap`,
`crunch_single_touch`, `crunch_priority_order`, `crunch_multi_exam`, `interleave_basic`, `interleave_single_unit`,
`interleave_confusables`, `billing_month_end_anchors`, `billing_proration`, `billing_lifecycle`, `session_due_mix`, `offline_sync`.

## Commands
```bash
uv sync
uv run pytest          # 424 tests incl. hypothesis property tests
uv run ruff check . && uv run ruff format --check .
uv run mypy engine     # strict
```

## Windows / packaged-app note (important for agents)
Agents running inside Microsoft Store / MSIX-packaged apps (e.g. desktop AI apps) get a **virtualized
`%APPDATA%`**. `uv python install` then fails with *"Missing expected target directory for Python minor version
link"*, because the junction points at the real, empty path. Fix: set the user environment variable
`UV_PYTHON_INSTALL_DIR=%USERPROFILE%\.uv\python` (already set on the owner's machine) so Python lives outside
AppData. Python 3.12.14 is installed there.

## Integration notes for Codex (M0-09 / M4 / M7 / M8 / M9)
- Merge branch `engine-core` into the milestone branch; its paths (`services/engine/**`) don't overlap M0 scaffolding.
- Keep `pyproject.toml` / `uv.lock`; add FastAPI, psycopg, etc. as new dependencies.
- Store each module's `VERSION` next to its outputs (e.g. `mastery_snapshots.components.version`).
- In the Engineering Checklist, cite these tests as evidence for the doc 05 fixture items once wired.
