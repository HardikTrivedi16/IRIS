-- IRIS — Supabase migration 0007: grievance tracking + operational data classification
--
-- Forward-only. Does not modify any object created by 0001–0006 except
-- ADDING one nullable-safe column to public.applications (section 3).
-- Idempotent: safe to run more than once in the Supabase SQL Editor.
--
-- 1. public.grievances / public.grievance_history
--    Lightweight structured PREPARATION, TRACKING and HAND-OFF of an
--    applicant's grievance about an application's handling. This is NOT a
--    statutory grievance redressal mechanism and does not replace MAITRI /
--    NSWS or any departmental grievance portal. Categories below are IRIS
--    tracking labels, not statutory grievance classes.
--
-- 2. Context snapshot: at filing time the backend copies the application's
--    stage and SLA state (computed by the same function the government
--    portal uses) into context_snapshot, so what the applicant saw is
--    preserved even if the application later moves on.
--
-- 3. applications.data_classification: explicit provenance for operational
--    records so SLA / bottleneck screens can label synthetic demo data
--    instead of guessing from ID prefixes. Rows seeded by the synthetic
--    seed scripts are marked SYNTHETIC_DEMO below.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------
-- 1. grievances
-- ---------------------------------------------------------------------
create table if not exists public.grievances (
  id                    uuid primary key default gen_random_uuid(),
  grievance_number      text not null unique,
  project_id            text not null references public.projects(id) on delete cascade,
  application_id        uuid not null references public.applications(id) on delete cascade,
  department_id         text not null references public.departments(id),
  category              text not null
                          check (category in (
                            'PROCESSING_DELAY','INFORMATION_REQUEST_UNCLEAR',
                            'DOCUMENT_HANDLING','OTHER'
                          )),
  description           text not null check (char_length(description) between 10 and 4000),
  status                text not null default 'OPEN'
                          check (status in ('OPEN','ASSIGNED','UNDER_REVIEW','RESOLVED','CLOSED')),
  context_snapshot      jsonb not null default '{}'::jsonb,
  raised_by             text not null,
  raised_by_name        text,
  assigned_officer_id   uuid references public.department_users(id) on delete set null,
  assigned_officer_name text,
  resolution_note       text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now()
);

comment on table public.grievances is
  'IRIS grievance preparation/tracking/hand-off record. Not a statutory grievance '
  'filing; does not replace MAITRI/NSWS or departmental grievance mechanisms.';

create index if not exists idx_grievances_project    on public.grievances(project_id, created_at desc);
create index if not exists idx_grievances_department on public.grievances(department_id, status);
create index if not exists idx_grievances_application on public.grievances(application_id);

alter table public.grievances enable row level security;

-- ---------------------------------------------------------------------
-- grievance_history (append-only)
-- ---------------------------------------------------------------------
create table if not exists public.grievance_history (
  id              uuid primary key default gen_random_uuid(),
  grievance_id    uuid not null references public.grievances(id) on delete cascade,
  from_status     text,
  to_status       text not null,
  actor_id        text not null,
  actor_name      text,
  actor_role      text not null,
  note            text,
  created_at      timestamptz not null default now()
);

create index if not exists idx_grievance_history_grievance on public.grievance_history(grievance_id, created_at);

alter table public.grievance_history enable row level security;

-- The browser never talks to these tables directly (same model as 0001):
-- only the backend's service role, which enforces project ownership and
-- department isolation in application code.
grant select, insert, update on public.grievances to service_role;
grant select, insert on public.grievance_history to service_role;
revoke update, delete on public.grievance_history from anon, authenticated, service_role;
revoke delete on public.grievances from anon, authenticated, service_role;

-- ---------------------------------------------------------------------
-- 3. applications.data_classification
-- ---------------------------------------------------------------------
alter table public.applications
  add column if not exists data_classification text not null default 'OPERATIONAL';

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'applications_data_classification_check'
  ) then
    alter table public.applications
      add constraint applications_data_classification_check
      check (data_classification in ('OPERATIONAL','SYNTHETIC_DEMO'));
  end if;
end $$;

comment on column public.applications.data_classification is
  'Provenance of the record: OPERATIONAL (entered through IRIS) or SYNTHETIC_DEMO '
  '(seeded by a synthetic demo script). Drives labelling on SLA/bottleneck screens.';

-- Rows created by the synthetic seed scripts (0005_aarav_lifesciences_synthetic_seed,
-- seed_aarav_demo.sql, and the SwaadHarvest synthetic dataset if loaded).
update public.applications
   set data_classification = 'SYNTHETIC_DEMO'
 where data_classification <> 'SYNTHETIC_DEMO'
   and (application_id like 'APP-AARAV-%' or application_id like 'APP-SWAAD-%');
