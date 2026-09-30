-- CROSS-TENANT-REVIEWED: discover one job; function returns its trusted tenant ID.
select private.take_job(%s, %s);
