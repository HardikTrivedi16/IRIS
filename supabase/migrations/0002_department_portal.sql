-- IRIS — Supabase migration 0002: Department / Government portal schema
--
-- SCOPE
-- =====
-- This migration extends the existing schema (0001) with tables for the
-- Government/Department operational portal. It deliberately does NOT:
--   * Duplicate projects, decisions, documents, or any other table from 0001.
--   * Copy regulatory-data content into Postgres rows.
--   * Invent legal/regulatory SLA durations — sla_policies rows are
--     configurable application data, clearly labelled as such.
--
-- Industry projects and Government applications reference the SAME underlying
-- project via applications.project_id → projects.id, avoiding data duplication.
--
-- ROLES (ready for Supabase Auth integration)
-- ============================================
-- INDUSTRY_USER      — external applicant
-- DEPARTMENT_OFFICER — processes applications
-- DEPARTMENT_MANAGER — assigns officers, approves workflow stages
-- DEPARTMENT_ADMIN   — full access including SLA policy management
--
-- APPEND-ONLY TABLES
-- ===================
-- application_stage_history and assignment_history are append-only.
-- operational_events is append-only.
-- UPDATE/DELETE revoked for these tables (same pattern as decisions).

-- -------------------------------------------------------------------------
-- departments
-- -------------------------------------------------------------------------
create table if not exists public.departments (
  id              text primary key,
  name            text not null,
  code            text not null unique,
  jurisdiction    text not null default 'Maharashtra',
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

comment on table public.departments is
  'Government departments that process industrial applications (MPCB, FSSAI, etc).';

create index if not exists idx_departments_code on public.departments(code);

alter table public.departments enable row level security;

-- -------------------------------------------------------------------------
-- department_users  (officers, managers, admins)
-- -------------------------------------------------------------------------
create table if not exists public.department_users (
  id              uuid primary key default gen_random_uuid(),
  department_id   text not null references public.departments(id) on delete cascade,
  user_id         text,               -- Supabase Auth user id (null until auth integrated)
  name            text not null,
  email           text,
  role            text not null default 'DEPARTMENT_OFFICER'
                    check (role in (
                      'INDUSTRY_USER',
                      'DEPARTMENT_OFFICER',
                      'DEPARTMENT_MANAGER',
                      'DEPARTMENT_ADMIN'
                    )),
  is_active       boolean not null default true,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

comment on table public.department_users is
  'Officers and managers within a department. role column ready for Supabase Auth RLS policies.';

create index if not exists idx_dept_users_dept on public.department_users(department_id);
create index if not exists idx_dept_users_user on public.department_users(user_id);

alter table public.department_users enable row level security;

-- -------------------------------------------------------------------------
-- sla_policies  (configurable — NOT hardcoded legal requirements)
-- -------------------------------------------------------------------------
create table if not exists public.sla_policies (
  id                  uuid primary key default gen_random_uuid(),
  name                text not null,
  requirement_type    text,             -- e.g. 'food', 'environmental', null = default
  duration_hours      integer not null check (duration_hours > 0),
  warning_pct         numeric(4,3) not null default 0.75
                        check (warning_pct between 0 and 1),
  description         text,             -- MUST explain this is configurable, not a legal mandate
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

comment on table public.sla_policies is
  'Configurable SLA policies. duration_hours and warning_pct are operational settings, '
  'NOT legally mandated values. Seed rows are clearly labelled demo policies.';

alter table public.sla_policies enable row level security;

-- Seed demo policies — clearly labelled as configurable, not legal requirements
insert into public.sla_policies (id, name, requirement_type, duration_hours, warning_pct, description)
values
  ('a1000000-0000-0000-0000-000000000001',
   'Standard Review (30 days)',
   null, 720, 0.75,
   'Demo configurable policy — 30-day review window. Replace duration_hours with actual regulatory timelines.'),
  ('a1000000-0000-0000-0000-000000000002',
   'Fast-Track Review (15 days)',
   'food', 360, 0.80,
   'Demo configurable policy for food-sector applications. Replace with actual FSSAI processing timelines.'),
  ('a1000000-0000-0000-0000-000000000003',
   'Complex Environmental Review (60 days)',
   'environmental', 1440, 0.70,
   'Demo configurable policy for complex environmental applications. Replace with actual MPCB timelines.')
on conflict (id) do nothing;

-- -------------------------------------------------------------------------
-- applications
-- -------------------------------------------------------------------------
-- One row per government application. References both projects (for the
-- underlying industry project) and departments (for the processing authority).
create table if not exists public.applications (
  id                    uuid primary key default gen_random_uuid(),
  application_id        text not null unique,   -- human-readable: APP-00001
  project_id            text references public.projects(id) on delete set null,
  department_id         text not null references public.departments(id),
  requirement_id        text not null,           -- engine REQ-#### id
  title                 text,
  applicant_name        text,
  current_stage         text not null default 'SUBMITTED'
                          check (current_stage in (
                            'SUBMITTED','UNDER_REVIEW','INFORMATION_REQUESTED',
                            'INSPECTION_SCHEDULED','INSPECTION_COMPLETED',
                            'RECOMMENDED','APPROVED','REJECTED'
                          )),
  assigned_officer_id   uuid references public.department_users(id) on delete set null,
  sla_policy_id         uuid references public.sla_policies(id) on delete set null,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  completed_at          timestamptz
);

comment on table public.applications is
  'Government-side application records. current_stage is operational status — '
  'completely separate from the Phase 9 engine regulatory decision.';

create index if not exists idx_applications_project on public.applications(project_id);
create index if not exists idx_applications_dept on public.applications(department_id);
create index if not exists idx_applications_stage on public.applications(current_stage);
create index if not exists idx_applications_officer on public.applications(assigned_officer_id);
create index if not exists idx_applications_created on public.applications(created_at desc);

alter table public.applications enable row level security;

-- -------------------------------------------------------------------------
-- application_stage_history  (append-only)
-- -------------------------------------------------------------------------
create table if not exists public.application_stage_history (
  id                uuid primary key default gen_random_uuid(),
  application_id    uuid not null references public.applications(id) on delete cascade,
  previous_stage    text,
  new_stage         text not null,
  actor             text not null,
  reason            text,
  created_at        timestamptz not null default now()
);

comment on table public.application_stage_history is
  'Append-only stage transition log. previous_stage null means initial submission. '
  'UPDATE/DELETE revoked below.';

create index if not exists idx_stage_history_app on public.application_stage_history(application_id, created_at);

alter table public.application_stage_history enable row level security;

-- -------------------------------------------------------------------------
-- assignment_history  (append-only)
-- -------------------------------------------------------------------------
create table if not exists public.assignment_history (
  id                uuid primary key default gen_random_uuid(),
  application_id    uuid not null references public.applications(id) on delete cascade,
  officer_id        uuid references public.department_users(id) on delete set null,
  officer_name      text not null,
  assigned_by       text not null,
  reason            text,
  created_at        timestamptz not null default now()
);

comment on table public.assignment_history is
  'Append-only officer assignment/reassignment history. UPDATE/DELETE revoked below.';

create index if not exists idx_assignment_history_app on public.assignment_history(application_id, created_at);

alter table public.assignment_history enable row level security;

-- -------------------------------------------------------------------------
-- sla_instances
-- -------------------------------------------------------------------------
create table if not exists public.sla_instances (
  id                uuid primary key default gen_random_uuid(),
  application_id    uuid not null unique references public.applications(id) on delete cascade,
  policy_id         uuid references public.sla_policies(id) on delete set null,
  started_at        timestamptz not null default now(),
  completed_at      timestamptz,   -- set when application reaches terminal stage
  created_at        timestamptz not null default now()
);

comment on table public.sla_instances is
  'Per-application SLA tracking. SLA state (WITHIN_SLA/AT_RISK/BREACHED/COMPLETED) '
  'is computed at query time from started_at + policy.duration_hours vs now().';

alter table public.sla_instances enable row level security;

-- -------------------------------------------------------------------------
-- operational_events  (append-only audit trail — NOT regulatory content)
-- -------------------------------------------------------------------------
create table if not exists public.operational_events (
  id                uuid primary key default gen_random_uuid(),
  application_id    uuid not null references public.applications(id) on delete cascade,
  event_type        text not null,    -- APPLICATION_SUBMITTED, STAGE_TRANSITION, OFFICER_ASSIGNED, ...
  message           text not null,
  actor             text,
  created_at        timestamptz not null default now()
);

comment on table public.operational_events is
  'Append-only operational audit trail for department workflow. '
  'Not regulatory content; UPDATE/DELETE revoked below.';

create index if not exists idx_op_events_app on public.operational_events(application_id, created_at);

alter table public.operational_events enable row level security;

-- =========================================================================
-- Grants
-- =========================================================================
-- No grants to anon/authenticated (same pattern as 0001).
-- service_role gets read/write on mutable tables, read/insert only on
-- append-only tables.

grant select, insert, update, delete on
  public.departments,
  public.department_users,
  public.sla_policies,
  public.applications,
  public.sla_instances
  to service_role;

grant select, insert on
  public.application_stage_history,
  public.assignment_history,
  public.operational_events
  to service_role;

revoke update, delete on public.application_stage_history from anon, authenticated, service_role;
revoke update, delete on public.assignment_history from anon, authenticated, service_role;
revoke update, delete on public.operational_events from anon, authenticated, service_role;

-- =========================================================================
-- Seed demo departments
-- =========================================================================
insert into public.departments (id, name, code, jurisdiction)
values
  ('dept-mpcb', 'Maharashtra Pollution Control Board', 'MPCB', 'Maharashtra'),
  ('dept-fssai', 'Food Safety and Standards Authority of India', 'FSSAI', 'Maharashtra')
on conflict (id) do nothing;
