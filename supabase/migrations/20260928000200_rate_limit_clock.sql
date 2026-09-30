create or replace function private.rate_limit_hit(p_key text, p_limit integer, p_window_s integer)
returns boolean language plpgsql security definer set search_path = '' as $$
declare bucket_time timestamptz := clock_timestamp(); allowed boolean;
begin
  if p_key is null or p_key !~ '^[a-f0-9]{64}$' or p_limit is null or p_window_s is null
    or p_limit < 1 or p_limit > 100000 or p_window_s < 1 or p_window_s > 86400 then
    raise exception 'Invalid rate limit' using errcode = '22023';
  end if;
  -- Token bucket: count is consumed capacity, replenished continuously.
  -- CROSS-TENANT-REVIEWED: global atomic security accounting, not user content.
  insert into private.rate_limit_buckets as bucket(key, window_start, count, expires_at)
    values (p_key, bucket_time, 1, bucket_time + make_interval(secs => p_window_s))
  on conflict (key) do update set
    count = greatest(0, bucket.count - extract(epoch from (bucket_time - bucket.window_start))
      * p_limit / p_window_s) + 1,
    window_start = bucket_time,
    expires_at = bucket_time + make_interval(secs => p_window_s)
  where greatest(0, bucket.count - extract(epoch from (bucket_time - bucket.window_start))
    * p_limit / p_window_s) + 1 <= p_limit
  returning true into allowed;
  return coalesce(allowed, false);
end $$;

