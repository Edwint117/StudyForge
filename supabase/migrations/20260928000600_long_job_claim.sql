create function private.start_long_job(p_job uuid,p_user uuid,p_dispatch_lease uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare j public.jobs; token uuid:=gen_random_uuid();
begin
  select * into j from public.jobs where id=p_job and user_id=p_user and lease_token=p_dispatch_lease
    and status='running' for update;
  if not found then return null; end if;
  update public.jobs set lease_token=token,heartbeat_at=now(),updated_at=now() where id=p_job and user_id=p_user;
  perform pgmq.set_vt(j.queue,j.pgmq_msg_id,60);
  return jsonb_build_object('job_id',j.id,'user_id',j.user_id,'type',j.type,'payload',j.payload,
    'lease_token',token,'attempts',j.attempts,'max_attempts',j.max_attempts,'queue',j.queue);
end $$;
revoke all on function private.start_long_job(uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function private.start_long_job(uuid,uuid,uuid) to engine_worker;
