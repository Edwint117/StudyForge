# Verification report: PASS

- Commit: `6109111b2a752c9ec428922d8f6d97244a4d6d72`
- Tree: `634c8528321ffcf29d42d5c092447ca8bc7812b2`
- Branch: `main`
- Working tree: clean
- Scope: all stages
- Started: 2026-09-29T05:45:16.391Z
- Finished: 2026-09-29T05:48:36.237Z

| Stage | Result | Time | Note |
|---|---|---|---|
| install | PASS | 1s | pnpm install, uv sync |
| lint | PASS | 7s | eslint, prettier, ruff check, ruff format |
| typecheck | PASS | 5s | tsc, mypy |
| unit | PASS | 27s | vitest, pytest |
| database | PASS | 9s | migration up, pgTAP |
| integration | PASS | 10s | integration |
| e2e | PASS | 25s | playwright |
| semgrep | PASS | 58s | semgrep |
| secrets | PASS | 4s | staged, history |
| audit | PASS | 14s | pnpm audit, export lock, pip-audit, osv-scanner |
| sbom | PASS | 2s | pnpm sbom, uv sbom |
| image | PASS | 37s | no fixable HIGH/CRITICAL findings |
| evals | PASS | 0s | evals |

Tool output is kept in `.cache/verify/` (ignored by git); this report holds outcomes only.
A report-only commit may follow this run if its diff touches nothing outside `docs/verify/` (ADR-0017).
