---
title: StudyForge — Learning Algorithms
project: StudyForge
created: 2026-09-27
tags: [project, studyforge, algorithms, fsrs]
---

# 05: Learning Algorithms

Everything here lives in `packages/core` (TS; the online review path: FSRS scheduling, crunch mode §2, interleaving §3) or `services/engine` (Python; everything that runs as a job or batch: the planner §4 (`plan.generate` / `plan.rebalance` jobs), mastery §5, blueprints §6, exam-day selection §7, verification §8). Each algorithm has a `version` constant that is stored alongside its outputs, so results stay reproducible. **Fixture tests are mandatory.** Every section ends with the fixtures that must pass.

---

## 1. FSRS core (SRS-01/02)
- Use **FSRS-6** through `ts-fsrs` (online) and `py-fsrs` (optimizer). Pin both versions, and keep a **parity test** that replays the same 1,000 synthetic reviews through both libraries and asserts the resulting stability/difficulty/due agree within 1e-6 relative.
- Retrievability after `t` days with stability `S` (FSRS-6, decay `w20`):
  `R(t,S) = (1 + F·t/S)^(−w20)`, where `F = 0.9^(−1/w20) − 1`
- Interval for a desired retention `r`: `I(r,S) = (S/F)·(r^(−1/w20) − 1)`, rounded to days (≥ 1) for review-state cards. Learning steps default to `[1m, 10m]` and relearning to `[10m]`.
- Default parameters come from the library defaults until the optimizer adopts personal ones. **Adoption rule:** train on 80% of the user's review history, evaluate log-loss on the most recent 20%, and adopt only if log-loss improves by ≥ 1% over the currently active parameters. Keep the last 3 parameter sets.
- Fuzz is enabled for normal mode and disabled in crunch mode.

**Fixtures:** `fsrs_parity.json`; `optimizer_adopt.json` (a synthetic user where the new parameters improve → adopt); `optimizer_reject.json` (overfit → keep old).

---

## 2. Exam-crunch mode (SRS-04)
**Trigger:** for card `c` in the scope of an upcoming exam `E` (the card's concepts ∩ the exam's concepts ≠ ∅), crunch applies when `days_to_exam(E) ≤ crunch_days` (default 7). If a card is in the scope of several exams, use the **earliest** one.

Let `T` = time until the exam starts (in days, fractional), `S` = current stability, and `w_c` = the card's exam weight = Σ over the card's concepts of (unit weight % ÷ number of concepts in the unit), normalized to [0,1] within the exam.

1. **Target retention at exam time:** `r_exam = max(desired_retention, 0.93)`.
2. **Next interval after a review** (replaces the normal FSRS interval):
   - `I_fsrs` = the normal FSRS interval at `r = r_exam`.
   - The review must happen before the exam, with a final review ideally in the last 36 hours: `I_cap = max(0.5, (T − 0.75) / 2)` days if `T > 1.5`; otherwise the card goes into the **cram window** (next review is due in the T-36h…T-6h window and handled by §7).
   - `I = min(I_fsrs, I_cap)`. If `R(T, S_after) ≥ r_exam` **and** `I_fsrs ≥ T`, schedule a **single** pre-exam touch at `T − 1` day (a confidence touch) and no more.
3. **Queue priority** (daily capacity is limited):
   `priority(c) = w_c · (1 − R_exam(c)) · (1 + 0.5·lapses_recent(c)) · yield(c)`, where `R_exam(c) = R(T_since_last + T, S)` is the predicted retrievability at exam time, and `yield(c) = 1.2` for formula/definition cards and `1.0` otherwise.
   Sort by priority descending and fill the day's crunch minutes (from the plan's review sessions, at an estimated `median_response_ms` per card, default 12s). Cards that don't fit are deferred, and the planner is told about the deficit.
4. **New cards in crunch:** introduce new in-scope cards only if `days_to_exam ≥ 2` and the capacity isn't used up. Order them by `w_c` descending, then by prerequisite order.
5. **Exit:** after the exam, crunch no longer applies. The card goes back to normal FSRS at its next review (the stability already learned is kept, since crunch only shortens intervals).

Rule precedence: check the single-touch condition first; otherwise apply `min(I_fsrs, I_cap)`.

**Fixtures** (use the library's default FSRS-6 parameters): `crunch_interval_cap.json` (S=6, T=5 → R(T)≈0.91 < 0.93, so no single touch; I_fsrs≈3.7 > I_cap → I = 2.125 days); `crunch_single_touch.json` (S=200, T=5 → one touch at T−1); `crunch_priority_order.json` (10 cards with known S/weights → exact order); `crunch_multi_exam.json` (card in two scopes → earliest exam used).

---

## 3. Interleaving (SRS-05)
The session builder takes a candidate list (already selected by due date or priority) and orders it:
1. Group by unit. Let `k` = the number of groups.
2. Walk through the list using weighted round-robin (weights = each group's share of candidates), with the constraint that **no two consecutive items come from the same unit** whenever another group has remaining items.
3. **Confusable pairs:** for concept pairs connected by a `confusable_with` edge (or embedding similarity > 0.85 across different units), place them within 3 positions of each other at least once per session, to train discrimination.
4. Keep ~15% of slots for "mixed-type" items (a question from the bank in place of a card) when practice items exist in scope.
5. Deterministic given a seed (`session_id`), so tests are reproducible.

**Fixtures:** `interleave_basic.json` (3 units × 5 → no adjacency violations); `interleave_single_unit.json` (1 unit → allowed adjacency); `interleave_confusables.json`.

---

## 4. Backward scheduler (PLAN-04/05/07)
### Inputs
- Exams `E_i`: start time, covered units/concepts, weight %, readiness target.
- For each unit `u`: syllabus weight `w_u`; **effort estimate** `m_u` (minutes) = `learn_minutes(u) + practice_minutes(u)`, where `learn_minutes = clamp(0.9 × tokens(u)/1000 × difficulty_factor, 20, 240)` (`tokens(u)` = the summed chunk tokens of the unit's concepts; `difficulty_factor` = 1.0 by default, 1.3 for units dense in formulas or proofs), scaled by `(1 − mastery_u)` for units the student has already studied.
- Prerequisite DAG over units, derived from concept edges (unit A precedes B if any concept in A is `prerequisite_of` a concept in B; break cycles by syllabus order).
- **Free windows**: availability rules minus busy blocks minus existing locked sessions, clipped to [earliest, latest] and the daily max. Windows shorter than `min_block` are dropped.
- Preferences: `rest_weekdays`, `daily_max_min`, `min_block`, `max_block`.

### Algorithm (version `planner-1`)
1. **Reserve** (counted backwards from each exam start `D`):
   - Day `D−1`: **consolidation** (cumulative review + warm-up), 60–120 min capped by availability.
   - Day `D−2`: **mock exam** (duration = real exam duration + 15 min review) plus a consolidation review.
   - 1 **buffer** (catch-up) block of 45 min every 6 study days, placed at the end of each 6-day run.
   - **Rest days:** the user's `rest_weekdays`, plus one forced rest day if the user would otherwise study 7 days in a row.
2. **Order units** with a topological sort over the prerequisite DAG. Ties are broken by syllabus order, then by `w_u` descending (fundamentals first).
3. **Learn sessions:** walk the free windows forward from *now*. Place each unit's learn minutes (split into blocks between `min_block` and `max_block`) in the earliest windows, in topological order. **Deadline:** a unit's learning must finish by `D − 3` days. If it can't, the plan is infeasible → step 7.
4. **Spaced review sessions** per unit, at +1, +3 and +7 days after its last learn block (only those before `D−2`), each `max(15, 0.2·m_u)` min. These are FSRS-driven sessions: their contents come from the SRS queue at run time. They may merge into one "mixed review" block when they fall on the same day (interleaving).
5. **Practice sessions:** for units with `w_u ≥ median`, one 30–45 min practice block (question bank) after the +3 review.
6. **Multiple exams (PLAN-07):** all exams share one window pool. At each window, pick the next session from the exam with the highest `urgency = (remaining_required_min / available_min_until_deadline) × weight_pct`. Sessions for different exams never overlap, and each exam's reservations (step 1) are placed first.
7. **Feasibility:** `required = Σ unplaced minutes`. If `required > 0`, return `feasibility = {status:'deficit', deficit_min, per_exam, options:[extend_daily_max_to:X, skim_units:[lowest w_u until feasible], accept_partial]}`. **Never** place sessions outside free windows. The plan is saved with `status=active` plus the deficit shown in the UI.
8. Every session gets a `rationale` string ("Unit 3 before Unit 5 because it's a prerequisite of *Bayes' theorem*; review at +3 days for spacing").

### Rebalancing (version `rebalance-1`) (PLAN-06)
**Triggers** (enqueued and debounced 60s per user): a session passes its `ends_at + 30 min` still `planned` (→ `missed`); an attempt or quiz unit score < 70% (→ remediation); busy blocks change; an exam changes; a new document is ready in a course with an active exam; a manual request.
1. **Freeze:** sessions that are `done`, `in_progress` or `is_locked`, or that start within the next 60 minutes.
2. **Carry forward:** the unfinished minutes of `missed` and `skipped` sessions go back into their unit's remaining requirement.
3. **Remediation:** for each unit with a mock/quiz score `s < 0.7`: add `m_u × (0.7 − s) × 1.5` minutes of practice + review, placed as early as possible.
4. **Re-run** steps 1–7 from *now* over the remaining requirement, with a **stability preference**: when choosing a window for a session that existed in the previous plan, prefer its old slot if it's still free (a cost of 0), otherwise the nearest free slot (cost = |Δt| in hours). Greedy with this tie-breaker is enough; don't use an ILP.
5. Diff the old plan against the new one → `change_summary {moved, added, removed, deficit_change}`. Notify the user if anything changed within the next 48h. Write back to calendars.

**Fixtures (exact expected sessions in `planner_fixtures/`):**
- `single_exam_feasible` (14 days, 5 units, simple DAG) → exact session list.
- `prereq_order` (a unit that has a prerequisite is never learned before it).
- `infeasible_deficit` → the deficit value and a `skim_units` suggestion.
- `two_exams_overlap` → both reservations are respected, and urgency interleaving is correct.
- `rebalance_missed_session` → minimal moves (≤ 3 sessions changed).
- `rebalance_low_score` → the remediation minutes are added.
- `calendar_busy_change` → the conflicting sessions move to the nearest free slot.
- `dst_transition` (the plan crosses a DST change in `America/New_York`) → no session at a non-existent or duplicated local time.
- Property tests (hypothesis/fast-check): no overlaps; never outside free windows; sessions within [min, max] block; reservations always present when there is any feasible capacity.

---

## 5. Mastery model (DIAG-06/07, COMP-03)
Mastery per concept `k` ∈ [0,1] (version `mastery-1`):
```
retention_k  = mean over active cards linked to k of R(now, S)      (FSRS; 0 if no reviews yet → excluded)
perf_k       = Σ_i decay(age_i) · score_i / Σ_i decay(age_i)       over question attempts & verified card reviews touching k
               decay(age) = 0.5^(age_days / 14)
feynman_k    = latest Feynman coverage score (if any), decayed with the same half-life
mastery_k    = weighted mean of the available components with weights retention 0.35, perf 0.50, feynman 0.15
               (renormalize over the components present; if none → null, shown as "not started")
confidence_k = min(1, n_evidence / 8)
```
- Unit mastery = the importance-weighted mean of its concepts' mastery. Course/exam mastery = the unit-weight-weighted mean.
- **Error mix** per unit: the counts of `error_class` across deductions in the last 30 days → the heatmap side bars.
- **Readiness forecast** (DIAG-07): `score_pred = Σ_u w_u · mastery_u` over the exam's units, with a band of `± 1.96 · sqrt(Σ w_u² · var_u)`, where `var_u = mastery_u(1−mastery_u)/max(1, n_u)`. It is calibrated after each real exam (EXAM-05) by storing the residuals; if 3 or more real exams exist, apply a linear calibration `a·pred + b` per user.

**Fixtures:** `mastery_components.json`, `mastery_missing_components.json`, `readiness_band.json`.

---

## 6. Mock exam blueprint (DIAG-02)
- Total points `P` (default 100) and duration = the real exam's.
- Unit allocation: `points_u ∝ w_u · (1 + 0.5·(1 − mastery_u))`, rounded to question granularity; each covered unit gets ≥ 1 question.
- Type mix: from the past exam's type distribution if available, otherwise MCQ 30% / short 25% / multi-step 35% / code or proof 10% (code only if the course has code chunks).
- Difficulty: target a mean of 3/5, with ≥ 1 question at 4–5 per high-weight unit.
- Selection: unseen verified bank questions first → seen more than 30 days ago → generated. Generated questions must pass verification (two independent solves agree + a SymPy/numeric check + the code reference passes); up to 3 generation attempts per slot, otherwise the slot is dropped and the blueprint rebalanced.

---

## 7. Cram queue & warm-up (EXAM-01/02)
- **Cram queue (from T-48h):** units sorted by `w_u` descending, taking them until the cumulative weight ≥ 80% of the exam → keep those with `mastery_u < 0.8` → order by `w_u × (0.8 − mastery_u)`. Each item includes: the unit's cards with `R_exam < 0.9` (by crunch priority), the 1–2 bank questions with the highest failure rate, and the cheat-sheet section.
- **Warm-up (from T-6h):** 25 items / 15 min, from the exam scope's definition and formula cards, choosing cards with `0.75 ≤ R(now) ≤ 0.97` (successful but active retrieval), interleaved, 3 easy items first. **No FSRS updates** (`mode=warmup` logs are excluded from scheduling and the optimizer).

**Fixtures:** `cram_queue_order.json`, `warmup_selection.json`.

---

## 8. Answer verification (SRS-03, DIAG-04)
| Check | Method |
|---|---|
| text | NFKC normalize, lowercase, strip punctuation/articles; exact → correct; Levenshtein ratio ≥ 0.9 → "close" (show a diff); a list of accepted alternates in `answer_spec` |
| numeric | parse units (pint); relative tolerance (default 1e-3) or absolute tolerance per spec; significant-figure rules optional |
| sympy | `parse_latex` → `simplify(a − b) == 0` or `equals()`; fallback: random numeric evaluation at 20 points within the domain, tolerance 1e-9; timeout 2s → `undetermined` |
| code | Piston run of the user's code against the tests (stdin/stdout or function harness); limits of 3s CPU, 128MB and no network; the language allowlist is Python, C, C++, Java, JS and x86-64 asm (nasm) |
| llm_keypoints | Haiku judges the answer against the key points → `{covered[], missing[], incorrect[]}`; cached by (card, answer hash) |

**Proposed rating:** incorrect → Again. Correct with `response_ms > 2 × median` or "close" → Hard. Correct → Good. Correct with `response_ms < 0.5 × median` and `reps ≥ 2` → Easy.
