# M0 operating-cost assumptions

Updated 2026-09-28. No production workload has been measured or deployed by this pass. The figures below are unmeasured planning notes from provider price lists as remembered; verify each against current pricing before relying on it.

- Cloud Run service: planned minimum 0, maximum 3 instances, concurrency 4, 1 vCPU/1 GiB while handling requests. Batch job: 2 vCPU/4 GiB, one task, no Cloud Run retry (pgmq owns attempts).
- A $5 monthly Google Cloud budget with 50/90/100% alerts is declared in Terraform. Budget alerts are not spending caps. Registry storage, logs, networking and Secret Manager are separate billed dimensions.
- Terraform state bucket: versioning and uniform access; old versions consume storage. No unlimited retention promise.
- Piston sandbox cannot use the specified privileged runtime on Cloud Run. ADR-0020 awaits a deployment choice and a current cost estimate; no VM cost is assumed approved.
- Secret Manager: 13 secret slots, one active version each after `pnpm env:push-secrets` (unchanged values are skipped, so re-runs do not add versions). Google charges per active version beyond a small free allowance; at this count the expected amount is cents per month.
- Artifact Registry: each deploy pushes one image by digest with SBOM and provenance attestations (about 700 MB uncompressed locally). Keep the newest revisions only; a cleanup policy is not yet in Terraform, so storage grows until one is added.
- Cloud Logging: 30-day retention is set in Terraform. The engine logs JSON with correlation IDs and no payloads; volume is unmeasured.
- Cloud Run canary: a deploy briefly runs two revisions (10% canary then promote), which is minutes of extra instance time per release. `pg_cron` wakes the engine every 2 minutes only when jobs need it, plus a 5-minute maintenance wake for health checks: at most 288 tiny requests a day, scale to zero between them.
- Local verification tooling (Trivy, OSV, ZAP images, disposable rehearsal database) runs on the operator machine and costs nothing beyond disk and bandwidth.
- Web runs on the operator host. No public web host, paid mail service, backup vendor or payment processor is introduced.
- AI economics remain Claude's pure `engine/adapters/economics.py` estimates until real adapter calls are measured. No inference test was run to check credit balance.

Before deployment, save a region-specific estimate from current provider pricing and compare it with the owner's budget. Track actual cost per job once usage metering is wired. This document is not a measured bill or a guarantee of free operation.
