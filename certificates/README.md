# Database trust root

`supabase-prod-ca-2021.crt` is a public certificate, not a credential. Retrieved over verified HTTPS on 2026-09-27 from the URL in [Supabase's dashboard configuration](https://github.com/supabase/supabase/blob/master/apps/studio/hooks/custom-content/custom-content.json):

https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

SHA-256 certificate fingerprint: `80:70:25:AD:50:D4:ED:21:9D:2C:9C:7D:29:9C:00:4F:82:4E:B0:0C:F7:F6:5A:FE:F6:07:D0:7B:72:E6:CA:FA`.
Expires 2031-04-26. Review upstream changes and replace before expiry; never disable hostname or certificate verification to bypass a connection failure. See [Supabase SSL guidance](https://supabase.com/docs/guides/platform/ssl-enforcement).
