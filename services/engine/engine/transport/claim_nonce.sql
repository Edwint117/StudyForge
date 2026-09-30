-- CROSS-TENANT-REVIEWED: shared replay protection contains no user data.
select private.claim_engine_nonce(%s, %s::uuid, %s::bigint);
