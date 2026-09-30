begin;
create extension if not exists pgtap with schema extensions;
select plan(12);
select ok(not (select rolbypassrls from pg_roles where rolname='engine_worker'), 'engine cannot bypass RLS');
select ok(not has_table_privilege('engine_worker','private.engine_nonces','SELECT'), 'no direct nonce access');
select ok(not has_table_privilege('authenticated','private.engine_nonces','INSERT'), 'clients cannot insert nonces');
select ok(not has_function_privilege('authenticated','private.claim_engine_nonce(text,uuid,bigint)','EXECUTE'), 'client cannot claim nonce');
select ok(not has_function_privilege('anon','private.rate_limit_hit(text,integer,integer)','EXECUTE'), 'anonymous cannot consume limiter');
-- The migration creator has ADMIN but PostgreSQL 17 defaults SET membership off.
-- Enable test impersonation transactionally; ROLLBACK restores the original grant.
grant engine_worker to postgres with set true;
grant usage on schema extensions to engine_worker;
set local role engine_worker;
select extensions.ok(private.claim_engine_nonce('rpc','11111111-1111-4111-8111-111111111111',extract(epoch from now())::bigint+61), 'first claim');
select extensions.ok(not private.claim_engine_nonce('rpc','11111111-1111-4111-8111-111111111111',extract(epoch from now())::bigint+61), 'replay rejected');
select extensions.ok(private.claim_engine_nonce('wake','11111111-1111-4111-8111-111111111111',extract(epoch from now())::bigint+61), 'scope separated');
select extensions.throws_ok($$select private.claim_engine_nonce('rpc','22222222-2222-4222-8222-222222222222',0)$$, '22023', 'Invalid nonce claim', 'expired rejected');
select extensions.ok(private.rate_limit_hit(repeat('a',64),2,60), 'token one');
select extensions.ok(private.rate_limit_hit(repeat('a',64),2,60), 'token two');
select extensions.ok(not private.rate_limit_hit(repeat('a',64),2,60), 'limit enforced');
reset role;
select * from finish();
rollback;
