# ADR-0008: Postgres queue with push wake and recovery sweep

- Status: accepted
- Date: 2026-09-28
- Checklist: background jobs, idempotency, stateless services

Use pgmq and public.jobs in one transaction. Messages carry only job_id; the authoritative payload remains tenant-owned in jobs. Enqueue keys are unique per user/type and reject reuse with a changed payload. Authenticated users can read only their own jobs and cannot write them.

The database sends HMAC-signed wake requests through pg_net; Vault holds the engine URL and wake secret. The engine drains within the HTTP request lifetime, ending before Cloud Run's 60-minute deadline. It must not return a response and rely on background CPU. pg_cron's two-minute sweep recovers missed wakes and stale heartbeats. Local development may poll with ENGINE_POLL_MODE=1.

Each claim issues a fresh lease token. Heartbeats extend visibility; completion checks user_id plus the lease token. A killed worker leaves the message recoverable. A stale worker cannot complete a newer lease. Effects inside a handler must additionally be idempotent; the queue provides at-least-once delivery, not exactly-once external effects. Exhausted attempts are archived and marked dead. Long work uses the same image as a Cloud Run Job.

Redis/Celery would add state and cost without removing the idempotency requirement. Revisit beyond 50 jobs/second sustained or 10,000 queued jobs. Run the recovery/concurrency suite before claiming these guarantees in production; the owner deferred most testing on 2026-09-28.
