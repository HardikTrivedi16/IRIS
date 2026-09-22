-- 0008: grant the backend's server-side service_role access to user_profiles.
--
-- 0003 granted SELECT/INSERT/UPDATE on public.user_profiles to `authenticated`
-- only. The FastAPI backend reads, creates and updates profiles through its
-- service-role client (GET /auth/me, POST /auth/profile, government linking),
-- and on a brand-new Supabase project service_role had no privilege on the
-- table, so PostgREST answered 403. 0003 is already applied elsewhere and is
-- not edited; this forward migration fixes both existing and fresh databases.
--
-- Idempotent. No DELETE is granted, and no RLS policy or append-only
-- protection is changed.

grant select, insert, update on public.user_profiles to service_role;
