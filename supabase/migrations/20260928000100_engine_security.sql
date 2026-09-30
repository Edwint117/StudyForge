-- Expand-only M0 security infrastructure. No user content is stored here.
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'engine_worker') then
    create role engine_worker login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;
  end if;
end $$;
alter role engine_worker set statement_timeout = '15s';
alter role engine_worker set lock_timeout = '3s';
grant usage on schema private to engine_worker;

-- CROSS-TENANT-REVIEWED: random request nonces contain no user identity or payload.
create table private.engine_nonces (
  scope text not null check (scope in ('wake', 'rpc')),
  nonce uuid not null,
  expires_at timestamptz not null,
  primary key (scope, nonce)
);
create index engine_nonces_expiry on private.engine_nonces (expires_at);
alter table private.engine_nonces enable row level security;
alter table private.engine_nonces force row level security;
revoke all on private.engine_nonces from public, anon, authenticated, engine_worker;

create function private.claim_engine_nonce(p_scope text, p_nonce uuid, p_expires bigint)
returns boolean language plpgsql security definer set search_path = '' as $$
declare claimed boolean;
begin
  if p_scope not in ('wake','rpc') or p_scope is null or p_nonce is null
     or p_expires is null or p_expires <= extract(epoch from clock_timestamp())
     or p_expires > extract(epoch from clock_timestamp()) + 122 then
    raise exception 'Invalid nonce claim' using errcode = '22023';
  end if;
  -- CROSS-TENANT-REVIEWED: atomic global replay prevention across engine instances.
  insert into private.engine_nonces(scope, nonce, expires_at)
  values (p_scope, p_nonce, to_timestamp(p_expires))
  on conflict (scope, nonce) do update set expires_at = excluded.expires_at
    where private.engine_nonces.expires_at < clock_timestamp()
  returning true into claimed;
  return coalesce(claimed, false);
end $$;
revoke all on function private.claim_engine_nonce(text, uuid, bigint) from public, anon, authenticated;
grant execute on function private.claim_engine_nonce(text, uuid, bigint) to engine_worker;

-- CROSS-TENANT-REVIEWED: keys are HMAC digests of limiter subjects, never raw IPs/user IDs.
create unlogged table private.rate_limit_buckets (
  key text primary key check (key ~ '^[a-f0-9]{64}$'),
  window_start timestamptz not null,
  count numeric not null check (count >= 0),
  expires_at timestamptz not null
);
create index rate_limit_buckets_expiry on private.rate_limit_buckets(expires_at);
alter table private.rate_limit_buckets enable row level security;
alter table private.rate_limit_buckets force row level security;
revoke all on private.rate_limit_buckets from public, anon, authenticated, engine_worker;

create function private.rate_limit_hit(p_key text, p_limit integer, p_window_s integer)
returns boolean language plpgsql security definer set search_path = '' as $$
declare current_time timestamptz := clock_timestamp(); allowed boolean;
begin
  if p_key is null or p_key !~ '^[a-f0-9]{64}$' or p_limit is null or p_window_s is null
    or p_limit < 1 or p_limit > 100000 or p_window_s < 1 or p_window_s > 86400 then
    raise exception 'Invalid rate limit' using errcode = '22023';
  end if;
  -- Token bucket: count is consumed capacity, replenished continuously.
  -- CROSS-TENANT-REVIEWED: global atomic security accounting, not user content.
  insert into private.rate_limit_buckets as bucket(key, window_start, count, expires_at)
    values (p_key, current_time, 1, current_time + make_interval(secs => p_window_s))
  on conflict (key) do update set
    count = greatest(0, bucket.count - extract(epoch from (current_time - bucket.window_start))
      * p_limit / p_window_s) + 1,
    window_start = current_time,
    expires_at = current_time + make_interval(secs => p_window_s)
  where greatest(0, bucket.count - extract(epoch from (current_time - bucket.window_start))
    * p_limit / p_window_s) + 1 <= p_limit
  returning true into allowed;
  return coalesce(allowed, false);
end $$;
revoke all on function private.rate_limit_hit(text, integer, integer) from public, anon, authenticated;
grant execute on function private.rate_limit_hit(text, integer, integer) to engine_worker;

create extension if not exists pg_cron;
select cron.schedule('engine-security-expiry', '*/5 * * * *',
  $cron$delete from private.engine_nonces where expires_at < now();
  delete from private.rate_limit_buckets where expires_at < now();$cron$);
