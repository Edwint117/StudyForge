-- CROSS-TENANT-REVIEWED: aggregate counts only; the function exposes no payloads or tenant identifiers.
select dead_recent, stuck, backlog, oldest_queued_seconds from private.job_health();
