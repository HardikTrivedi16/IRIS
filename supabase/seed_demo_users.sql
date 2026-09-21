-- IRIS — demo user seed (NOT a numbered schema migration; paste into the SQL
-- Editor directly, don't add this to the supabase/migrations/ pipeline).
--
-- Creates two Supabase Auth accounts and wires them into IRIS's role system:
--   1. INDUSTRY_USER   -> becomes owner of the Aarav Lifesciences project,
--      so the company/products/documents/applications seeded in
--      0005_aarav_lifesciences_synthetic_seed.sql become visible to them.
--   2. DEPARTMENT_ADMIN -> linked to dept-mpcb, sees the 2 applications
--      filed against that department (APP-AARAV-REQ-0001/0002).
--
-- CHANGE THE PASSWORDS BELOW before running (or rotate them afterwards in
-- Supabase Dashboard -> Authentication -> Users). email_confirmed_at is set
-- directly so both accounts can sign in immediately with no email delivery.
--
-- CAVEAT: this writes directly to Supabase-internal auth.users/auth.identities
-- tables (a common seeding pattern, mirroring GoTrue's own bcrypt hashing via
-- crypt()/gen_salt('bf')) — unlike every other script this session, that
-- schema isn't in this repo's migrations, so I can't check it against your
-- actual Supabase version. If the auth.* inserts error, sign up both accounts
-- normally through the app's Sign Up screen instead (using the same two
-- emails below), then re-run this script — it will find the existing users
-- by email and skip straight to the IRIS-side wiring in step 3.
--
-- Safe to re-run: every step checks for an existing row first.

create extension if not exists pgcrypto;

do $$
declare
  v_instance_id       uuid;
  v_industry_user_id  uuid;
  v_govt_user_id      uuid;
  v_industry_email    text := 'industry@gmail.com';  -- CHANGE ME
  v_industry_password text := 'REPLACE_WITH_PASSWORD_SUPPLIED_OUT_OF_BAND';                        -- CHANGE ME
  v_govt_email        text := 'department@gmail.com';             -- CHANGE ME
  v_govt_password     text := 'REPLACE_WITH_PASSWORD_SUPPLIED_OUT_OF_BAND';                         -- CHANGE ME
begin
  select coalesce(
    (select instance_id from auth.users limit 1),
    '00000000-0000-0000-0000-000000000000'::uuid
  ) into v_instance_id;

  -- 1. Industry user (will own the Aarav Lifesciences pharma project)
  select id into v_industry_user_id from auth.users where email = v_industry_email;
  if v_industry_user_id is null then
    v_industry_user_id := gen_random_uuid();
    insert into auth.users (
      instance_id, id, aud, role, email, encrypted_password,
      email_confirmed_at, confirmation_token, recovery_token,
      email_change, email_change_token_new,
      raw_app_meta_data, raw_user_meta_data, created_at, updated_at
    ) values (
      v_instance_id, v_industry_user_id, 'authenticated', 'authenticated', v_industry_email,
      crypt(v_industry_password, gen_salt('bf')),
      now(), '', '', '', '',
      '{"provider":"email","providers":["email"]}'::jsonb,
      jsonb_build_object('full_name', 'Rohan Vikram Sharma'),
      now(), now()
    );
    insert into auth.identities (
      id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at
    ) values (
      gen_random_uuid(), v_industry_user_id, v_industry_user_id::text,
      jsonb_build_object('sub', v_industry_user_id::text, 'email', v_industry_email),
      'email', now(), now(), now()
    );
    raise notice 'Created industry user % (%)', v_industry_email, v_industry_user_id;
  else
    raise notice 'Industry user % already exists (%)', v_industry_email, v_industry_user_id;
  end if;

  -- 2. Government user (MPCB officer)
  select id into v_govt_user_id from auth.users where email = v_govt_email;
  if v_govt_user_id is null then
    v_govt_user_id := gen_random_uuid();
    insert into auth.users (
      instance_id, id, aud, role, email, encrypted_password,
      email_confirmed_at, confirmation_token, recovery_token,
      email_change, email_change_token_new,
      raw_app_meta_data, raw_user_meta_data, created_at, updated_at
    ) values (
      v_instance_id, v_govt_user_id, 'authenticated', 'authenticated', v_govt_email,
      crypt(v_govt_password, gen_salt('bf')),
      now(), '', '', '', '',
      '{"provider":"email","providers":["email"]}'::jsonb,
      jsonb_build_object('full_name', 'MPCB Duty Officer'),
      now(), now()
    );
    insert into auth.identities (
      id, user_id, provider_id, identity_data, provider, last_sign_in_at, created_at, updated_at
    ) values (
      gen_random_uuid(), v_govt_user_id, v_govt_user_id::text,
      jsonb_build_object('sub', v_govt_user_id::text, 'email', v_govt_email),
      'email', now(), now(), now()
    );
    raise notice 'Created government user % (%)', v_govt_email, v_govt_user_id;
  else
    raise notice 'Government user % already exists (%)', v_govt_email, v_govt_user_id;
  end if;

  -- 3. IRIS-side wiring (public schema — the part this repo actually owns).
  insert into public.user_profiles (supabase_auth_uid, email, full_name, iris_role, department_id, is_active, pending_government_link, provider)
  values (v_industry_user_id, v_industry_email, 'Rohan Vikram Sharma', 'INDUSTRY_USER', null, true, false, 'email')
  on conflict (supabase_auth_uid) do update set
    email = excluded.email, full_name = excluded.full_name, iris_role = excluded.iris_role,
    department_id = excluded.department_id, updated_at = now();

  insert into public.user_profiles (supabase_auth_uid, email, full_name, iris_role, department_id, is_active, pending_government_link, provider)
  values (v_govt_user_id, v_govt_email, 'MPCB Duty Officer', 'DEPARTMENT_ADMIN', 'dept-mpcb', true, false, 'email')
  on conflict (supabase_auth_uid) do update set
    email = excluded.email, full_name = excluded.full_name, iris_role = excluded.iris_role,
    department_id = excluded.department_id, updated_at = now();

  insert into public.department_users (department_id, user_id, name, email, role, is_active, supabase_auth_uid)
  values ('dept-mpcb', v_govt_user_id::text, 'MPCB Duty Officer', v_govt_email, 'DEPARTMENT_ADMIN', true, v_govt_user_id)
  on conflict (supabase_auth_uid) do update set
    name = excluded.name, email = excluded.email, role = excluded.role, is_active = true;

  update public.projects set owner_id = v_industry_user_id where id = 'aarav-lifesciences';

  raise notice 'Done. Industry user % owns aarav-lifesciences; government user % is DEPARTMENT_ADMIN at dept-mpcb.',
    v_industry_email, v_govt_email;
end $$;