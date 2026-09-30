-- Expand-only. Job retention, dead-letter/stuck-job health counts, and a 5-minute health wake for the engine.
create function private.job_health() returns table (
  dead_recent integer, stuck integer, backlog integer, oldest_queued_seconds integer
) language sql stable security definer set search_path='' as $$
  -- CROSS-TENANT-REVIEWED: aggregate counts only; no payloads, results or tenant identifiers leave this function.
  select
    (count(*) filter (where status = 'dead' and finished_at > now() - interval '1 hour'))::integer,
    (count(*) filter (where status = 'running' and heartbeat_at < now() - interval '5 minutes'))::integer,
    (count(*) filter (where status = 'queued'))::integer,
    coalesce(extract(epoch from now() - min(created_at) filter (where status = 'queued')), 0)::integer
  from public.jobs
$$;
revoke all on function private.job_health() from public, anon, authenticated;
grant execute on function private.job_health() to engine_worker;

-- Retention (DATA-05): payloads and results can hold study content, so finished jobs do not live forever.
-- Succeeded/cancelled: 30 days. Dead (the DLQ): 90 days, long enough to investigate. pgmq archive: 30 days.
create function private.purge_finished_jobs() returns integer
language plpgsql security definer set search_path='' as $$
declare removed integer; q record;
begin
  -- CROSS-TENANT-REVIEWED: retention sweep is time-based and tenant-agnostic by design.
  delete from public.jobs
   where (status in ('succeeded', 'cancelled') and finished_at < now() - interval '30 days')
      or (status in ('dead', 'failed') and finished_at < now() - interval '90 days');
  get diagnostics removed = row_count;
  for q in select queue_name from pgmq.list_queues() loop
    execute format('delete from pgmq.%I where archived_at < now() - interval ''30 days''', 'a_' || q.queue_name);
  end loop;
  return removed;
end $$;
revoke all on function private.purge_finished_jobs() from public, anon, authenticated, engine_worker;

select cron.schedule('engine-job-retention', '17 3 * * *', 'select private.purge_finished_jobs()');
-- The engine reports dead/stuck/backlogged jobs (to Sentry) whenever it drains the maintenance queue.
select cron.schedule('engine-health-wake', '*/5 * * * *', $$select private.wake_engine('maintenance')$$);
