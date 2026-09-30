begin;
select plan(8);
insert into auth.users(id,email) values ('cccccccc-cccc-4ccc-8ccc-cccccccccccc','m0-ret@example.invalid');
insert into public.jobs(user_id,type,queue,status,payload,idempotency_key,finished_at,heartbeat_at,created_at) values
 ('cccccccc-cccc-4ccc-8ccc-cccccccccccc','maintenance.probe','maintenance','succeeded','{}','old-ok', now()-interval '31 days', null, now()-interval '32 days'),
 ('cccccccc-cccc-4ccc-8ccc-cccccccccccc','maintenance.probe','maintenance','succeeded','{}','new-ok', now()-interval '1 day',  null, now()-interval '2 days'),
 ('cccccccc-cccc-4ccc-8ccc-cccccccccccc','maintenance.probe','maintenance','dead','{}','old-dead', now()-interval '91 days', null, now()-interval '92 days'),
 ('cccccccc-cccc-4ccc-8ccc-cccccccccccc','maintenance.probe','maintenance','dead','{}','mid-dead', now()-interval '40 days', null, now()-interval '41 days'),
 ('cccccccc-cccc-4ccc-8ccc-cccccccccccc','maintenance.probe','maintenance','dead','{}','fresh-dead', now()-interval '5 minutes', null, now()-interval '6 minutes'),
 ('cccccccc-cccc-4ccc-8ccc-cccccccccccc','maintenance.probe','maintenance','running','{}','stuck', null, now()-interval '10 minutes', now()-interval '20 minutes'),
 ('cccccccc-cccc-4ccc-8ccc-cccccccccccc','maintenance.probe','maintenance','queued','{}','waiting', null, null, now()-interval '15 minutes');
select is((select dead_recent from private.job_health()), 1, 'only the fresh dead job counts as a recent DLQ entry');
select is((select stuck from private.job_health()), 1, 'a running job without a recent heartbeat is stuck');
select is((select backlog from private.job_health()), 1, 'one queued job');
select cmp_ok((select oldest_queued_seconds from private.job_health()), '>=', 890, 'oldest queued age is reported');
select is(private.purge_finished_jobs(), 2, 'purges old succeeded and old dead jobs only');
select is((select count(*)::integer from public.jobs where idempotency_key in ('new-ok','mid-dead','fresh-dead','stuck','waiting')), 5, 'recent and unfinished jobs survive');
select ok(not has_function_privilege('engine_worker','private.purge_finished_jobs()','execute'), 'the engine role cannot purge');
select ok(has_function_privilege('engine_worker','private.job_health()','execute') and not has_function_privilege('authenticated','private.job_health()','execute'), 'only the engine role can read job health');
select * from finish();
rollback;
