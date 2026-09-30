# ADR-0020: Piston runtime incompatibility and proposed separate sandbox host

- Status: proposed; owner decision required before changing the deployment target
- Date: 2026-09-28
- Affects: M0-07/M0-15, SRS-03, DIAG-04, sandbox containment gates

## Evidence

The spec fixes Piston on Cloud Run. Piston's [upstream Compose definition](https://raw.githubusercontent.com/engineer-man/piston/master/docker-compose.yaml) requires `privileged: true` and executable tmpfs; its [repository prerequisites](https://github.com/engineer-man/piston) require cgroup v2. Google's [Cloud Run runtime contract](https://docs.cloud.google.com/run/docs/container-contract) explicitly disallows privileged containers. This is a documented compatibility failure, not a passed runtime/escape probe. No sandbox has been deployed and no substitute has been silently selected.

## Proposed decision

Keep Piston, but place it on a dedicated Compute Engine sandbox host with no production data or database credentials, an isolated VPC, no public IP and no general internet egress. Put an authenticated broker in front of Piston; accept only the engine service identity, restrict language/package versions and apply per-run CPU/memory/time/process/filesystem limits. Block guest access to metadata and host control interfaces; the broker must own identity verification without passing credentials to guest programs. Bake language packages into an immutable image so runtime egress is unnecessary.

Before provisioning: prepare a Terraform plan and current region-specific monthly cost estimate, and obtain explicit owner approval because this changes both the fixed hosting decision and idle-cost model. Piston's privilege requirement makes the whole VM the trust boundary; the host must be dedicated and treated as disposable. Require actual network/fork/filesystem/time escape tests and broker authorization tests before enabling code execution.

## Alternatives

1. Dedicated sandbox host (proposed): preserves Piston and full language support, adds host operations and idle cost.
2. Defer sandbox/code execution: continue all independent M0 implementation, but leave M0's three-service and production gates incomplete. This is not permission to call M0 done.
3. Replace Piston with a runtime compatible with Cloud Run: requires a separate evaluation and ADR, including language compatibility and containment evidence; a plain subprocess is not an acceptable sandbox.

## Consequences

Engine HTTP/jobs/database/IaC work can proceed independently. Sandbox deployment, run-code wiring and the complete M0 deployment gate remain blocked on the architecture choice. The owner's request to defer most testing does not constitute approval to change the sandbox runtime.
