begin;
select plan(20);
insert into auth.users(id,email) values
 ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','m0-a@example.invalid'),
 ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','m0-b@example.invalid');
create temp table test_jobs (owner_id uuid, id uuid, claim jsonb);
insert into test_jobs(owner_id,id) values
 ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',private.enqueue_job('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','maintenance.probe','maintenance','probe-a','{}')),
 ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',private.enqueue_job('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','maintenance.probe','maintenance','probe-b','{}'));
select is((select count(*)::integer from pg_policies where schemaname='public' and tablename='jobs'),4,'four policies');
select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid='public.jobs'::regclass),'RLS enabled and forced');
select is(private.enqueue_job('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','maintenance.probe','maintenance','probe-a','{}'),
 (select id from test_jobs where owner_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),'enqueue idempotent');
select is((select count(*)::integer from pgmq.q_maintenance),2,'only one message per job');
select throws_ok($$select private.enqueue_job('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','maintenance.probe','maintenance','probe-a','{"changed":true}')$$,
 '22023','Idempotency conflict','changed payload rejected');
select ok(not has_table_privilege('engine_worker','public.jobs','UPDATE'),'worker cannot mutate table directly');
select ok(not has_function_privilege('authenticated','private.enqueue_job(uuid,text,text,text,jsonb,integer)','EXECUTE'),'users cannot forge enqueue owner');
set local role authenticated;
select set_config('request.jwt.claim.sub','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',true);
select is((select count(*)::integer from public.jobs),1,'A sees only A');
select is((select count(*)::integer from public.jobs where user_id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'),0,'B job hidden');
select throws_ok($$update public.jobs set attempts=99$$,'42501','permission denied for table jobs','user update rejected');
select throws_ok($$delete from public.jobs$$,'42501','permission denied for table jobs','user deletion rejected');
reset role;
grant usage on schema extensions to engine_worker;
grant engine_worker to postgres with set true;
grant select,update on test_jobs to engine_worker;
set local role engine_worker;
update test_jobs set claim=private.take_job('maintenance',60) where owner_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
select is((select (claim->>'attempts')::integer from test_jobs where claim is not null),1,'first lease attempt');
select ok((select private.heartbeat_job(id,owner_id,(claim->>'lease_token')::uuid,60,'{"stage":"running"}') from test_jobs where claim is not null),'heartbeat extends lease');
select ok(not (select private.heartbeat_job(id,'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',(claim->>'lease_token')::uuid,60,'{}') from test_jobs where claim is not null),'wrong tenant cannot heartbeat');
select ok(not (select private.finish_job(id,owner_id,gen_random_uuid(),true,'{}') from test_jobs where claim is not null),'wrong lease cannot finish');
select ok((select private.finish_job(id,owner_id,(claim->>'lease_token')::uuid,true,'{"ok":true}') from test_jobs where claim is not null),'completion succeeds');
select ok(not (select private.finish_job(id,owner_id,(claim->>'lease_token')::uuid,true,'{}') from test_jobs where claim is not null),'duplicate completion rejected');
reset role;
select is((select count(*)::integer from pgmq.q_maintenance),1,'completion deletes queue message');
select is((select status::text from public.jobs where user_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),'succeeded','persisted completion');
select ok((select id::text ~ '^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab]' from public.jobs limit 1),'UUID v7 shape');
select * from finish();
rollback;
