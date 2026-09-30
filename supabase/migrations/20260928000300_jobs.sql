create extension if not exists pgmq;
create extension if not exists pg_net with schema extensions;

create function private.uuid7() returns uuid language sql volatile set search_path='' as $$
  select (lpad(to_hex(floor(extract(epoch from clock_timestamp())*1000)::bigint),12,'0')
    || '7' || substr(replace(gen_random_uuid()::text,'-',''),14,3)
    || '8' || substr(replace(gen_random_uuid()::text,'-',''),18,15))::uuid;
$$;
revoke all on function private.uuid7() from public;

create type public.job_status as enum ('queued','running','succeeded','failed','cancelled','dead');
create table public.jobs (
  id uuid primary key default private.uuid7(),
  user_id uuid not null references auth.users(id) on delete cascade,
  type text not null check (type ~ '^[a-z_]+\.[a-z_]+$'),
  queue text not null check (queue in ('ingest','graph','generate','grade','plan','calendar','srs','io','notify','maintenance')),
  status public.job_status not null default 'queued',
  progress jsonb not null default '{}' check (jsonb_typeof(progress)='object'),
  payload jsonb not null check (jsonb_typeof(payload)='object' and octet_length(payload::text)<=1048576),
  result jsonb,
  error text,
  attempts integer not null default 0 check (attempts>=0),
  max_attempts integer not null default 3 check (max_attempts between 1 and 5),
  idempotency_key text not null check (length(idempotency_key) between 1 and 200),
  pgmq_msg_id bigint,
  lease_token uuid,
  heartbeat_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  trace_id uuid not null default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(user_id,type,idempotency_key),
  unique(id,user_id)
);
create index jobs_user on public.jobs(user_id);
create index jobs_recovery on public.jobs(status,heartbeat_at,created_at);
alter table public.jobs enable row level security;
alter table public.jobs force row level security;
create policy jobs_select_own on public.jobs for select to authenticated using (user_id=(select auth.uid()));
create policy jobs_insert_denied on public.jobs for insert to authenticated with check(false);
create policy jobs_update_denied on public.jobs for update to authenticated using(false) with check(false);
create policy jobs_delete_denied on public.jobs for delete to authenticated using(false);
revoke all on public.jobs from public, anon, authenticated, engine_worker, service_role;
grant select on public.jobs to authenticated;

do $$ declare q text; begin
  foreach q in array array['ingest','graph','generate','grade','plan','calendar','srs','io','notify','maintenance']
  loop perform pgmq.create(q); end loop;
end $$;
revoke all on schema pgmq from public, anon, authenticated, engine_worker;

create function private.enqueue_job(p_user uuid,p_type text,p_queue text,p_key text,p_payload jsonb,p_max integer default 3)
returns uuid language plpgsql security definer set search_path='' as $$
declare j public.jobs; inserted uuid;
begin
  -- Trusted callers alone receive EXECUTE. They must obtain user_id from authenticated server context.
  insert into public.jobs(user_id,type,queue,idempotency_key,payload,max_attempts)
    values(p_user,p_type,p_queue,p_key,p_payload,p_max)
    on conflict(user_id,type,idempotency_key) do nothing returning id into inserted;
  select * into strict j from public.jobs where user_id=p_user and type=p_type and idempotency_key=p_key for update;
  if j.payload<>p_payload or j.queue<>p_queue or j.max_attempts<>p_max then
    raise exception 'Idempotency conflict' using errcode='22023';
  end if;
  if inserted is not null then
    update public.jobs set pgmq_msg_id=pgmq.send(p_queue,jsonb_build_object('job_id',j.id))
      where id=j.id and user_id=p_user;
  end if;
  return j.id;
end $$;
revoke all on function private.enqueue_job(uuid,text,text,text,jsonb,integer) from public, anon, authenticated;
grant execute on function private.enqueue_job(uuid,text,text,text,jsonb,integer) to engine_worker, service_role;

create function private.take_job(p_queue text,p_vt integer default 60)
returns jsonb language plpgsql security definer set search_path='' as $$
declare msg record; j public.jobs; owner_id uuid; token uuid;
begin
  if p_queue not in ('ingest','graph','generate','grade','plan','calendar','srs','io','notify','maintenance')
    or p_vt not between 1 and 3600 then raise exception 'Invalid queue read' using errcode='22023'; end if;
  -- CROSS-TENANT-REVIEWED: queue discovery must select the next user's work.
  for msg in select * from pgmq.read(p_queue,p_vt,1) loop
    select user_id into owner_id from public.jobs where id=(msg.message->>'job_id')::uuid;
    if owner_id is null then perform pgmq.delete(p_queue,msg.msg_id); return null; end if;
    select * into j from public.jobs where id=(msg.message->>'job_id')::uuid and user_id=owner_id for update;
    if j.queue<>p_queue or j.pgmq_msg_id<>msg.msg_id then
      perform pgmq.archive(p_queue,msg.msg_id); return null;
    end if;
    if j.status in ('succeeded','cancelled','dead') then perform pgmq.delete(p_queue,msg.msg_id); return null; end if;
    if j.attempts>=j.max_attempts then
      update public.jobs set status='dead',finished_at=now(),updated_at=now(),lease_token=null,error='attempts_exhausted'
        where id=j.id and user_id=owner_id;
      perform pgmq.archive(p_queue,msg.msg_id); return null;
    end if;
    token:=gen_random_uuid();
    update public.jobs set status='running',attempts=attempts+1,lease_token=token,heartbeat_at=now(),
      started_at=coalesce(started_at,now()),updated_at=now() where id=j.id and user_id=owner_id;
    return jsonb_build_object('job_id',j.id,'user_id',owner_id,'type',j.type,'payload',j.payload,
      'lease_token',token,'attempts',j.attempts+1,'max_attempts',j.max_attempts,'queue',p_queue);
  end loop;
  return null;
end $$;
revoke all on function private.take_job(text,integer) from public, anon, authenticated;
grant execute on function private.take_job(text,integer) to engine_worker;

create function private.heartbeat_job(p_job uuid,p_user uuid,p_lease uuid,p_vt integer,p_progress jsonb)
returns boolean language plpgsql security definer set search_path='' as $$
declare j public.jobs;
begin
  if p_vt not between 1 and 3600 or jsonb_typeof(p_progress)<>'object' or octet_length(p_progress::text)>16384 then
    raise exception 'Invalid heartbeat' using errcode='22023'; end if;
  select * into j from public.jobs where id=p_job and user_id=p_user and lease_token=p_lease and status='running' for update;
  if not found then return false; end if;
  perform pgmq.set_vt(j.queue,j.pgmq_msg_id,p_vt);
  update public.jobs set heartbeat_at=now(),progress=p_progress,updated_at=now() where id=p_job and user_id=p_user;
  return true;
end $$;
revoke all on function private.heartbeat_job(uuid,uuid,uuid,integer,jsonb) from public, anon, authenticated;
grant execute on function private.heartbeat_job(uuid,uuid,uuid,integer,jsonb) to engine_worker;

create function private.finish_job(p_job uuid,p_user uuid,p_lease uuid,p_success boolean,p_result jsonb,p_delay integer default 1)
returns boolean language plpgsql security definer set search_path='' as $$
declare j public.jobs;
begin
  if p_delay not between 1 and 3600 or octet_length(p_result::text)>1048576 or p_success is null then
    raise exception 'Invalid completion' using errcode='22023'; end if;
  select * into j from public.jobs where id=p_job and user_id=p_user and lease_token=p_lease and status='running' for update;
  if not found then return false; end if;
  if p_success then
    update public.jobs set status='succeeded',result=p_result,error=null,finished_at=now(),updated_at=now(),lease_token=null
      where id=p_job and user_id=p_user;
    perform pgmq.delete(j.queue,j.pgmq_msg_id);
  elsif j.attempts>=j.max_attempts then
    update public.jobs set status='dead',error='handler_failed',finished_at=now(),updated_at=now(),lease_token=null
      where id=p_job and user_id=p_user;
    perform pgmq.archive(j.queue,j.pgmq_msg_id);
  else
    update public.jobs set status='queued',error='handler_failed',updated_at=now(),lease_token=null
      where id=p_job and user_id=p_user;
    perform pgmq.set_vt(j.queue,j.pgmq_msg_id,p_delay);
  end if;
  return true;
end $$;
revoke all on function private.finish_job(uuid,uuid,uuid,boolean,jsonb,integer) from public, anon, authenticated;
grant execute on function private.finish_job(uuid,uuid,uuid,boolean,jsonb,integer) to engine_worker;
