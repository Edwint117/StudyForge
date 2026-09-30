# StudyForge local tool inventory

Verified 2026-09-27. Bootstrap is in progress; this is not evidence that the full M0 pipeline is available.

| Tool | Version / status | Evidence / use |
|---|---|---|
| Git | 2.54.0.windows.1 | Local milestone branches; engine merge e8dd778 |
| Node.js | 24.17.0 | Root engine range >=24 <25 |
| pnpm | 11.19.0 | Pinned; manager auto-switch disabled to avoid desktop fallback temp-path failure |
| Docker | 29.5.3 | Supabase containers running; Vector collector restart unresolved |
| uv | 0.12.19 | Verified portable fallback `.tools/uv/uv.exe` |
| Python | 3.12.14 | Owner's `%USERPROFILE%\.uv\python`; preserve `UV_PYTHON_INSTALL_DIR` |
| Google Cloud CLI | 586.0.0 | Verified fallback `.tools/google-cloud-sdk`; active owner login/project GET pass |
| Terraform | Owner reports installed; not visible in this process PATH | Discover installed binary before provisioning; version not yet verified |
| Supabase CLI | 2.118.0 | Pinned dev dependency; local stack start + private credential sync pass |
| TypeScript | 6.0.3 | Supported by typescript-eslint; 7.0.2 was incompatible |
| ESLint / typescript-eslint | 10.11.0 / 8.70.1 | `pnpm lint` passes |
| Prettier | 3.9.9 | Root source formatting |
| Vitest | 5.0.2 | 19 environment tests pass |
| Ruff / mypy / pytest | 0.16.9 / 2.3.1 / 9.1.1 | Engine uv.lock; 286 tests + lint + strict typing pass |
| gitleaks | 8.30.1 | Verified official release checksum; history and staged scans |
| Lefthook | 2.1.14 | Pinned; installed pre-commit scan; synthetic negative and clean positive tests pass |
| Semgrep / OSV / Trivy / k6 / ZAP / cosign / SBOM | Not provisioned | Remaining M0/M11 pipeline work |

`scripts/setup/bootstrap-windows.ps1` prefers available installed uv/gcloud and uses verified official archives as fallbacks. It preserves the existing Python install directory (or uses the owner-specified `.uv/python` location when this desktop process has stale environment settings). The additional `.tools/python` from an earlier attempt is unused and has not been removed.

Lefthook's reviewed postinstall installs local hooks. Only esbuild, Supabase and Lefthook build scripts are allowed by the workspace policy. Real environment files are never included in scanner output; the secret-scan helper suppresses raw scanner streams and fails closed on findings or tool errors.
