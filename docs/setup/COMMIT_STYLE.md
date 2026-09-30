# How commits and pushes are written

The owner reads the GitHub commit list to see, at a glance, what each change did and why it exists. Every commit, by a human or an agent, follows this. It is enforced in part by the `commit-msg` hook (`scripts/setup/check-commit-msg.ts`).

## The header line is the purpose

`<type>: <what this change does, in plain words>`

- Say the outcome or purpose, not the mechanics. Someone skimming should know what changed for the product or the project.
- Lower-case after the colon, imperative or plain description, no full stop, under about 80 characters.
- Optional scope in brackets when it helps: `fix(engine): ...`. Plain `fix:` is fine.

| Type | Use it for |
|---|---|
| `feat` | something new a user or operator can now do |
| `fix` | something that was wrong and now works |
| `docs` | documentation, progress records, ADRs, inventories |
| `style` | formatting or visual polish with no behavior change |
| `refactor` | restructuring with no behavior change |
| `test` | adding or fixing tests only |
| `perf` | making something faster or lighter |
| `build` / `chore` | tooling, dependencies, housekeeping |
| `merge` | bringing a verified branch into `main` |

## Good and bad headers

| Good | Why |
|---|---|
| `fix: compact sponsor editor and clarify listing status` | says what was fixed |
| `docs: record verified sponsor production rollout` | says what was recorded and that it was verified |
| `feat: add admin-managed sponsor directory and local review` | says what a user can now do |
| `fix: hide past events from attendance check-in` | one clear behavior change |

| Bad | Problem |
|---|---|
| `update stuff`, `wip`, `fixes` | no purpose, no type |
| `fix: bug` | which bug? |
| `feat: changes to engine/app.py` | describes files, not purpose |
| `chore: various updates and also fixed login and added billing` | three purposes in one commit |

## One purpose per commit

Split unrelated changes into separate commits so each header stays truthful. Documentation that records a rollout or verification is its own `docs:` commit, so the record and the change can be found separately.

## The body says why (when it isn't obvious)

Below a blank line, add a few short lines when the reason, the risk or the evidence is not clear from the header: what was wrong, what was chosen, what was checked or left unchecked. Never claim a check that was not run. Do not put secrets, tokens or personal data in a message.

## Publishing (pushing)

- Push only work that has a clear header on every commit.
- Milestone work lives on `m<N>-<slug>`. It reaches `main` through `pnpm merge:main`, which refuses unless `pnpm verify` covers the exact commit. The merge commit reads `merge: <branch> (verified <sha>)`.
- The report-only commit after a verify run reads `chore(verify): report for <sha>`.
- Before any push, the secret scan must pass (`pnpm secrets:staged` runs on every commit; `pnpm secrets:history` covers all history).
- GitHub shows green checks on the owner's other projects because they use hosted CI. This project deliberately does not (ADR-0017): the proof is the committed `docs/verify/latest.md`.
- Codex and Gemini may push their own working branches (for example `m0-ui`, `m0-tests`) at any time. Nobody but Claude pushes or merges `main`, and Claude does so only through `pnpm merge:main`, after `pnpm verify` covers the exact commit and the owner has asked for the publish in the current conversation.
