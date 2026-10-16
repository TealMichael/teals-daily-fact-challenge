-- Teal's Daily Fact Challenge v2.12.0 AWTRIX Live Hotfix 1
-- Safe to run once after the original v2.12 migration.
-- Fixes pgcrypto.digest() visibility for the two public clock-auth RPCs.

alter function public.awtrix_top10(integer)
set search_path = public, extensions, pg_temp;

alter function public.awtrix_poll(bigint)
set search_path = public, extensions, pg_temp;
