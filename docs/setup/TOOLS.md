# StudyForge local tool inventory

Observed 2026-09-27 during first-session planning. Discovery only; setup is not complete. Install and pin missing tools after plan approval, without asking the owner to install them.

| Tool | Observed version/status | Evidence / next action |
|---|---|---|
| Git | 2.54.0.windows.1 | git --version |
| Node.js | v24.17.0 | node --version |
| pnpm | 11.19.0 | pnpm --version; Codex runtime fallback; pin project version and check normal-shell availability in M0 |
| Docker CLI / daemon | 29.5.3 / 29.5.3 | docker --version; permitted read-only docker info confirms daemon is running |
| Python launcher | Present; no installed Pythons found | py --list; install Python 3.12 via uv in M0-01 |
| uv | Not on current PATH | Discover existing installation then install if missing |
| gcloud / Terraform / gitleaks | Not on current PATH | Discover non-PATH installations before M0 installation |
| Supabase CLI | No project dependency yet | Add pinned dev dependency after approval; pnpm supabase |
| Lefthook / Semgrep / OSV / Trivy / k6 / ZAP / cosign / SBOM tools | Not probed this session | Provision for M0 pipeline/M11 gate; record exact versions |

The sandbox denied Docker config/pipe access initially. A permitted read-only check confirmed the daemon version; no Docker configuration was changed. No secrets were read or logged, and no application dependencies were installed before required plan approval.
