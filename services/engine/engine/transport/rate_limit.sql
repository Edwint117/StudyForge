-- CROSS-TENANT-REVIEWED: hashed security bucket, no user content.
select private.rate_limit_hit(%s, %s, %s);
