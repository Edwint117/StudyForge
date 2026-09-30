create or replace function private.enqueue_job(p_user uuid,p_type text,p_queue text,p_key text,p_payload jsonb,p_max integer default 3)
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
    update public.jobs set pgmq_msg_id=(select pgmq.send(p_queue,jsonb_build_object('job_id',j.id)))
      where id=j.id and user_id=p_user;
  end if;
  return j.id;
end $$;

