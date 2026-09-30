# StudyForge: Build Progress

_Last updated: 2026-09-27 by Codex, first-session planning_

## Current milestone
M0: Foundation & delivery pipeline. **Planning prepared; awaiting human approval before application code.** No milestone gate has passed. Local branch: `m0-foundation`.

## Milestone status
| Milestone | Status | Gate passed | Tag |
|---|---|---|---|
| M0 Foundation | planning awaiting approval | no | — |
| M1 Identity & security | todo | no | — |
| M2 SaaS shell | todo | no | — |
| M3 Plans & mock billing | todo | no | — |
| M4 Ingestion & KG | todo | no | — |
| M5 Planner & calendars | todo | no | — |
| M6 Comprehension | todo | no | — |
| M7 Retention (FSRS) | todo | no | — |
| M8 Diagnostics | todo | no | — |
| M9 Exam-day | todo | no | — |
| M10 Data rights & admin | todo | no | — |
| M11 Pre-launch hardening | todo | no | — |

## Completed this session
- Read kickoff/AGENTS, all source specifications and the complete engineering checklist.
- Prepared [145 half-day slices across M0–M11](docs/plan/M0-M11-task-breakdown.md), plus milestone gate reviews, with PRD/checklist references and acceptance evidence.
- Prepared [183-note checklist triage](docs/plan/checklist-triage.md), including mixed-note scope, human actions, unresolved conflicts and future triggers.
- Preserved all 1,147 checklist items; added stable anchors and 176 authorized deferrals. No implementation completion claimed.
- Inventoried local tools in [TOOLS.md](docs/setup/TOOLS.md); Docker daemon is running. Python launcher finds no installed runtimes; install Python 3.12 via uv during approved setup.
- Confirmed .env.keys/.env.local/.env.production are git-ignored without reading their values. Environment connectivity has not been validated.

## Checklist tally (ENGINEERING_CHECKLIST.md)
| Section | Total | Done | N/A | Deferred | 🔑 Blocked | Open |
|---|---|---|---|---|---|---|
| BUILD | 927 | 0 | 0 | 56 | 0 | 871 |
| PRE-LAUNCH | 99 | 0 | 0 | 19 | 0 | 80 |
| LAUNCH | 20 | 0 | 0 | 0 | 0 | 20 |
| GROWTH | 49 | 0 | 0 | 49 | 0 | 0 |
| SCALE | 52 | 0 | 0 | 52 | 0 | 0 |
| **Total** | **1147** | **0** | **0** | **176** | **0** | **971** |

## Next 3 tasks
1. Obtain approval of both planning documents, as required by kickoff First Session step 5.
2. Execute the Second Step: bootstrap missing tools, finalize annotated env template/schema/setup, build secret-safe merge/check/push helpers, and validate local + production connectivity. Ask once for any missing owner key names; fill agent-owned values during M0.
3. Resolve the documented M0 contract conflicts and sandbox feasibility, write ADRs 0001–0019, then build and verify the first foundation slices. No M1 work before the M0 gate passes.

## Blocked on human (🔑)
| Item | Needed for | Env var / action | Asked on |
|---|---|---|---|
| Initial plan approval | Application code / Second Step | Review docs/plan/M0-M11-task-breakdown.md and checklist-triage.md; reply “Approved. Proceed to the Second Step.” | 2026-09-27 |
| Business placeholders to fill (not a build blocker) | Go-live identity/legal/invoices | Fill central packages/core/company.ts placeholders when that file is implemented in M2 | Not requested yet |

No credential failures have been observed: env scripts do not exist yet. Future human actions are scheduled in the task plan and doc10; they are not falsely marked code-complete blockers. Legal review, real-device checks and account attestations remain human responsibilities.

## Decisions and risks to resolve
See the plan's decision table. Main early items: four-policy vs select-only RLS; engine BYPASSRLS semantics; main-only deploy vs deploy-before-merge gate; no-backup Restore Testing applicability; Piston target-runtime compatibility. Later: polling/push acceptance, retained records vs deletion, and local-web availability measurement. No silent spec substitution is authorized.

## ADRs written
- None this session. ADR-0001–0019 are specified for M0, including 0019 which doc08's abbreviated list omits.

## Verification
- `node docs/plan/validate-planning.mjs` passed: 183 notes, 1,147 unchanged original item texts, 145 task rows, all 93 PRD story IDs covered, all active notes linked to task owners, and 1,383 valid local file/explicit-anchor links.
- `git diff --check` passed before the documentation commit.
- `pnpm verify` not run: no application manifests or verification pipeline exist. No build/deployment evidence or milestone completion claimed.

## Session log
| Date | Summary | Checklist items closed |
|---|---|---|
| 2026-09-27 | First-session plan/triage, tool inventory, contract-conflict register; awaiting required plan approval | 0 implemented; 176 explicitly deferred under doc09 |
