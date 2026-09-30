create function private.wake_engine(p_queue text) returns bigint
language plpgsql security definer set search_path='' as $$
declare endpoint text; secret text; payload jsonb; stamp text; nonce text; prefix text; signature text;
begin
  if p_queue not in ('ingest','graph','generate','grade','plan','calendar','srs','io','notify','maintenance') then
    raise exception 'Invalid wake queue' using errcode='22023'; end if;
  -- CROSS-TENANT-REVIEWED: operator-owned Vault configuration; body has only a queue name.
  select decrypted_secret into endpoint from vault.decrypted_secrets where name='engine_url';
  select decrypted_secret into secret from vault.decrypted_secrets where name='engine_wake_secret';
  -- Local development uses ENGINE_POLL_MODE. Cloud deployment must provision both secrets.
  if endpoint is null and secret is null then return null; end if;
  if endpoint !~ '^https://[a-zA-Z0-9.-]+\.run\.app$' or length(secret)<32 or endpoint is null or secret is null then
    raise exception 'Invalid engine wake configuration'; end if;
  payload:=jsonb_build_object('queue',p_queue);
  stamp:=floor(extract(epoch from clock_timestamp()))::bigint::text;
  nonce:=gen_random_uuid()::text;
  prefix:='studyforge-engine-v1'||chr(10)||'wake'||chr(10)||'POST'||chr(10)||'/wake'||chr(10)||stamp||chr(10)||nonce||chr(10);
  -- pg_net 0.20.4 transmits convert_to(body::text,'UTF8'), verified against its installed definition.
  signature:='v1='||encode(extensions.hmac(convert_to(prefix||payload::text,'UTF8'),convert_to(secret,'UTF8'),'sha256'),'hex');
  return net.http_post(endpoint||'/wake',body:=payload,headers:=jsonb_build_object(
    'Content-Type','application/json','x-engine-timestamp',stamp,'x-engine-nonce',nonce,'x-engine-signature',signature
  ),timeout_milliseconds:=10000);
end $$;
revoke all on function private.wake_engine(text) from public,anon,authenticated,engine_worker;

create function private.job_insert_wake() returns trigger
language plpgsql security definer set search_path='' as $$
begin
  perform private.wake_engine(new.queue);
  return new;
end $$;
revoke all on function private.job_insert_wake() from public,anon,authenticated,engine_worker;
create trigger jobs_wake after insert on public.jobs for each row execute function private.job_insert_wake();

create function private.sweep_engine() returns integer
language plpgsql security definer set search_path='' as $$
declare q text; wakes integer:=0;
begin
  -- CROSS-TENANT-REVIEWED: recovery discovery sends queue names only, not payloads or tenant IDs.
  for q in select distinct queue from public.jobs
    where (status='queued' and created_at<now()-interval '90 seconds')
       or (status='running' and heartbeat_at<now()-interval '60 seconds') loop
    perform private.wake_engine(q);
    wakes:=wakes+1;
  end loop;
  return wakes;
end $$;
revoke all on function private.sweep_engine() from public,anon,authenticated,engine_worker;
select cron.schedule('engine-wake-sweeper','*/2 * * * *','select private.sweep_engine()');
