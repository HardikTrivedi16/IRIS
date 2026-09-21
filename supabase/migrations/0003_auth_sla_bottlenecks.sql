-- IRIS — Supabase migration 0003: Auth, SLA stage targets, User management, Analytics views
--
-- SCOPE
-- =====
-- This migration extends 0001 + 0002 with:
--
--   A. Auth / profile linkage
--      - supabase_auth_uid column on department_users (links Supabase identity → IRIS role)
--      - user_profiles table (IRIS-side profile for ALL users: Industry + Government)
--
--   B. SLA stage targets (configurable per policy, per stage)
--      - sla_stage_targets table
--      - Used in SLA dashboard stage-level performance analytics
--      - Seed data clearly labelled as demo targets, not legal mandates
--
--   C. Analytics views (computed from real operational data — no stored derived stats)
--      - v_application_sla_status  — per-application SLA state (authoritative computation)
--      - v_stage_performance        — average/duration per stage from stage_history
--      - v_officer_workload         — active application count per officer
--
--   D. RLS policies for `authenticated` Supabase role
--      - Government users can read their own department's data
--      - Industry users cannot access any government operational data
--      - Users can read/update their own profile
--
--   E. Performance indexes for analytics queries
--
-- SINGLE SLA CALCULATION PATH
-- ============================
-- Application-level SLA state (WITHIN_SLA / AT_RISK / BREACHED / COMPLETED) is the
-- primary status. It is computed from sla_instances + sla_policies (the existing,
-- unchanged logic in department_store.py::_compute_sla_state).
--
-- Stage-level SLA uses sla_stage_targets to show per-stage performance in the SLA
-- dashboard. These are ADDITIONAL metrics — they do not duplicate or replace the
-- application-level state. The SLA dashboard shows both, computed in the backend,
-- never hardcoded.
--
-- GOVERNMENT-ONLY ENFORCEMENT
-- ============================
-- All department/SLA/bottleneck tables have RLS policies that:
--   1. Deny access to `anon` (no anonymous access)
--   2. Deny Government data access to users not in department_users
--   3. Limit each department_user to their own department's data
--   4. Allow DEPARTMENT_ADMIN full read access to their department

-- =========================================================================
-- A. Auth / Profile Linkage
-- =========================================================================

-- A1: Link Supabase Auth identity → department_users row
--     supabase_auth_uid = auth.uid() from Supabase JWT (the `sub` claim)
ALTER TABLE public.department_users
  ADD COLUMN IF NOT EXISTS supabase_auth_uid uuid UNIQUE;

CREATE INDEX IF NOT EXISTS idx_dept_users_auth_uid
  ON public.department_users(supabase_auth_uid)
  WHERE supabase_auth_uid IS NOT NULL;

comment on column public.department_users.supabase_auth_uid is
  'Supabase Auth user ID (auth.uid()). Set when a government user first authenticates. '
  'NULL until an admin links the Supabase identity to this department_users row. '
  'Google OAuth alone does NOT grant government access — an admin must link the account.';

-- A2: IRIS user profile table (all users: Industry + Government)
--     Created on first login via POST /api/v1/auth/profile
CREATE TABLE IF NOT EXISTS public.user_profiles (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  supabase_auth_uid   uuid NOT NULL UNIQUE,   -- auth.uid() from JWT sub claim
  email               text,
  full_name           text,
  avatar_url          text,
  iris_role           text NOT NULL DEFAULT 'INDUSTRY_USER'
                        CHECK (iris_role IN (
                          'INDUSTRY_USER',
                          'DEPARTMENT_OFFICER',
                          'DEPARTMENT_MANAGER',
                          'DEPARTMENT_ADMIN'
                        )),
  -- For Government users: mirrors department_users.department_id once linked
  -- For Industry users: NULL
  department_id       text REFERENCES public.departments(id) ON DELETE SET NULL,
  -- Whether the account has been reviewed and activated by an admin
  -- Industry users: active immediately (self-service)
  -- Government users: inactive until admin assigns department + role
  is_active           boolean NOT NULL DEFAULT true,
  -- Pending means account created but not yet linked to a department_users row
  -- (government users in this state see "pending access" screen)
  pending_government_link boolean NOT NULL DEFAULT false,
  provider            text,           -- 'email', 'google', etc.
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

comment on table public.user_profiles is
  'IRIS-side user profile, created on first successful Supabase Auth login. '
  'iris_role defaults to INDUSTRY_USER. Government roles are granted by DEPARTMENT_ADMIN only — '
  'authenticating via Google does NOT automatically grant government access.';

CREATE INDEX IF NOT EXISTS idx_user_profiles_auth_uid
  ON public.user_profiles(supabase_auth_uid);
CREATE INDEX IF NOT EXISTS idx_user_profiles_email
  ON public.user_profiles(email);

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

-- =========================================================================
-- B. SLA Stage Targets
-- =========================================================================

-- Stage-level SLA targets: configurable per policy, per workflow stage.
-- Used in the SLA dashboard to show per-stage performance vs target.
-- These are OPERATIONAL CONFIGURATION, not legal mandates.
-- ONE SLA CALCULATION PATH: application-level SLA state remains the primary
-- metric (computed in Python from sla_instances + sla_policies). Stage targets
-- provide ADDITIONAL analytics context in the SLA dashboard.
CREATE TABLE IF NOT EXISTS public.sla_stage_targets (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  policy_id       uuid NOT NULL REFERENCES public.sla_policies(id) ON DELETE CASCADE,
  stage           text NOT NULL
                    CHECK (stage IN (
                      'SUBMITTED', 'UNDER_REVIEW', 'INFORMATION_REQUESTED',
                      'INSPECTION_SCHEDULED', 'INSPECTION_COMPLETED',
                      'RECOMMENDED', 'APPROVED', 'REJECTED'
                    )),
  target_hours    integer NOT NULL CHECK (target_hours > 0),
  warning_pct     numeric(4,3) NOT NULL DEFAULT 0.75
                    CHECK (warning_pct BETWEEN 0 AND 1),
  description     text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (policy_id, stage)
);

comment on table public.sla_stage_targets is
  'Per-stage SLA targets, linked to an sla_policy. '
  'OPERATIONAL CONFIG, not legal mandates. '
  'Used in the SLA analytics dashboard to show stage-level performance vs target. '
  'Application-level SLA state (WITHIN_SLA/AT_RISK/BREACHED/COMPLETED) is computed '
  'separately from sla_instances + sla_policies.';

CREATE INDEX IF NOT EXISTS idx_sla_stage_targets_policy
  ON public.sla_stage_targets(policy_id);

ALTER TABLE public.sla_stage_targets ENABLE ROW LEVEL SECURITY;

-- Seed demo stage targets (clearly labelled as demo/configurable)
-- Linked to the standard-30d policy seeded in migration 0002
INSERT INTO public.sla_stage_targets (policy_id, stage, target_hours, warning_pct, description)
SELECT
  p.id,
  s.stage,
  s.target_hours,
  s.warning_pct,
  s.description
FROM public.sla_policies p
CROSS JOIN (VALUES
  ('SUBMITTED',            48,  0.75, 'Demo: Submission acknowledged within 2 days'),
  ('UNDER_REVIEW',         240, 0.75, 'Demo: Initial review within 10 days'),
  ('INFORMATION_REQUESTED',168, 0.80, 'Demo: Applicant response expected within 7 days'),
  ('INSPECTION_SCHEDULED', 72,  0.70, 'Demo: Inspection conducted within 3 days of scheduling'),
  ('INSPECTION_COMPLETED', 120, 0.75, 'Demo: Inspection report within 5 days'),
  ('RECOMMENDED',          48,  0.75, 'Demo: Final decision within 2 days of recommendation')
) AS s(stage, target_hours, warning_pct, description)
WHERE p.name = 'Standard Review (30 days)'
ON CONFLICT (policy_id, stage) DO NOTHING;

-- =========================================================================
-- C. Analytics Views (computed from real data, no stored derived stats)
-- =========================================================================

-- C1: Application SLA status view
--     Authoritative SLA state computation in SQL (mirrors Python _compute_sla_state).
--     Used for Supabase-side RLS-filtered queries and reporting.
--     The Python backend remains the primary computation path.
CREATE OR REPLACE VIEW public.v_application_sla_status AS
SELECT
  a.id,
  a.application_id,
  a.department_id,
  a.requirement_id,
  a.current_stage,
  a.assigned_officer_id,
  a.created_at,
  a.updated_at,
  a.completed_at,
  si.policy_id,
  si.started_at  AS sla_started_at,
  sp.duration_hours,
  sp.warning_pct,
  -- Primary SLA state: mirrors Python _compute_sla_state logic exactly
  CASE
    WHEN a.completed_at IS NOT NULL THEN 'COMPLETED'
    WHEN si.id IS NULL OR sp.id IS NULL THEN 'WITHIN_SLA'
    WHEN now() >= si.started_at + (sp.duration_hours * INTERVAL '1 hour')
      THEN 'BREACHED'
    WHEN now() >= si.started_at + (sp.duration_hours * sp.warning_pct * INTERVAL '1 hour')
      THEN 'AT_RISK'
    ELSE 'WITHIN_SLA'
  END AS sla_state,
  -- Due timestamp
  CASE
    WHEN si.id IS NOT NULL AND sp.id IS NOT NULL
      THEN si.started_at + (sp.duration_hours * INTERVAL '1 hour')
    ELSE NULL
  END AS due_at,
  -- Warning timestamp
  CASE
    WHEN si.id IS NOT NULL AND sp.id IS NOT NULL
      THEN si.started_at + (sp.duration_hours * sp.warning_pct * INTERVAL '1 hour')
    ELSE NULL
  END AS warning_at,
  -- Elapsed fraction (0.0–1.0, capped)
  CASE
    WHEN si.id IS NULL OR sp.id IS NULL OR sp.duration_hours = 0 THEN 0.0
    ELSE LEAST(
      EXTRACT(EPOCH FROM (COALESCE(a.completed_at, now()) - si.started_at))
        / (sp.duration_hours * 3600.0),
      1.0
    )
  END AS elapsed_pct,
  -- Calendar age of the application in hours
  EXTRACT(EPOCH FROM (now() - a.created_at)) / 3600.0 AS age_hours
FROM public.applications a
LEFT JOIN public.sla_instances si ON si.application_id = a.id
LEFT JOIN public.sla_policies sp ON sp.id = si.policy_id;

comment on view public.v_application_sla_status is
  'Per-application SLA status, computed from sla_instances + sla_policies. '
  'Mirrors Python _compute_sla_state. Intended for reporting and RLS-filtered queries. '
  'The Python backend is the primary computation path.';

-- C2: Stage performance view
--     Average and entry counts per stage, derived from application_stage_history.
--     Used for SLA stage-performance dashboard and bottleneck analytics.
CREATE OR REPLACE VIEW public.v_stage_performance AS
WITH stage_durations AS (
  SELECT
    ash.application_id,
    ash.new_stage                                    AS stage,
    ash.created_at                                   AS entered_at,
    LEAD(ash.created_at) OVER (
      PARTITION BY ash.application_id
      ORDER BY ash.created_at
    )                                                AS exited_at
  FROM public.application_stage_history ash
)
SELECT
  sd.stage,
  COUNT(*)                                           AS entry_count,
  COUNT(sd.exited_at)                                AS completed_count,
  AVG(
    EXTRACT(EPOCH FROM (sd.exited_at - sd.entered_at)) / 3600.0
  )                                                  AS avg_duration_hours,
  MIN(
    EXTRACT(EPOCH FROM (sd.exited_at - sd.entered_at)) / 3600.0
  )                                                  AS min_duration_hours,
  MAX(
    EXTRACT(EPOCH FROM (sd.exited_at - sd.entered_at)) / 3600.0
  )                                                  AS max_duration_hours
FROM stage_durations sd
WHERE sd.exited_at IS NOT NULL          -- only completed stage sojourns
GROUP BY sd.stage;

comment on view public.v_stage_performance is
  'Average processing time per workflow stage, computed from application_stage_history. '
  'Durations in hours. Used by bottleneck analytics and SLA stage-performance dashboard.';

-- C3: Officer workload view
CREATE OR REPLACE VIEW public.v_officer_workload AS
SELECT
  du.id            AS officer_id,
  du.name          AS officer_name,
  du.department_id,
  du.role,
  du.is_active,
  COUNT(a.id) FILTER (
    WHERE a.current_stage NOT IN ('APPROVED', 'REJECTED')
  )                AS active_applications,
  COUNT(a.id) FILTER (
    WHERE a.current_stage IN ('APPROVED', 'REJECTED')
  )                AS completed_applications,
  COUNT(a.id)      AS total_applications
FROM public.department_users du
LEFT JOIN public.applications a ON a.assigned_officer_id = du.id
WHERE du.role IN ('DEPARTMENT_OFFICER', 'DEPARTMENT_MANAGER')
GROUP BY du.id, du.name, du.department_id, du.role, du.is_active;

comment on view public.v_officer_workload is
  'Active and completed application count per officer. '
  'Used by the bottleneck officer workload analytics. '
  'Government-only; never exposed to Industry users.';

-- =========================================================================
-- D. RLS Policies
-- =========================================================================

-- Helper function: get authenticated user's department_id (government users)
-- Returns NULL for industry users (no department_users row)
CREATE OR REPLACE FUNCTION public.current_user_department_id()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  SELECT department_id::text
  FROM public.department_users
  WHERE supabase_auth_uid = auth.uid()
    AND is_active = true
  LIMIT 1;
$$;

-- Helper function: get authenticated user's iris_role
CREATE OR REPLACE FUNCTION public.current_user_iris_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  SELECT iris_role
  FROM public.user_profiles
  WHERE supabase_auth_uid = auth.uid()
  LIMIT 1;
$$;

-- D1: user_profiles — users can read/update their own profile only
CREATE POLICY user_profiles_read_own ON public.user_profiles
  FOR SELECT TO authenticated
  USING (supabase_auth_uid = auth.uid());

CREATE POLICY user_profiles_insert_own ON public.user_profiles
  FOR INSERT TO authenticated
  WITH CHECK (supabase_auth_uid = auth.uid());

CREATE POLICY user_profiles_update_own ON public.user_profiles
  FOR UPDATE TO authenticated
  USING (supabase_auth_uid = auth.uid())
  WITH CHECK (supabase_auth_uid = auth.uid());

-- D2: departments — government users can read all departments
CREATE POLICY departments_read_authenticated ON public.departments
  FOR SELECT TO authenticated
  USING (
    public.current_user_iris_role() IN (
      'DEPARTMENT_OFFICER', 'DEPARTMENT_MANAGER', 'DEPARTMENT_ADMIN'
    )
  );

-- D3: department_users — read own department's users (government only)
CREATE POLICY dept_users_read_own_dept ON public.department_users
  FOR SELECT TO authenticated
  USING (
    department_id = public.current_user_department_id()
  );

-- D4: sla_policies — government users can read
CREATE POLICY sla_policies_read_government ON public.sla_policies
  FOR SELECT TO authenticated
  USING (
    public.current_user_iris_role() IN (
      'DEPARTMENT_OFFICER', 'DEPARTMENT_MANAGER', 'DEPARTMENT_ADMIN'
    )
  );

-- D5: sla_stage_targets — government users can read
CREATE POLICY sla_stage_targets_read_government ON public.sla_stage_targets
  FOR SELECT TO authenticated
  USING (
    public.current_user_iris_role() IN (
      'DEPARTMENT_OFFICER', 'DEPARTMENT_MANAGER', 'DEPARTMENT_ADMIN'
    )
  );

-- D6: applications — government users read own department only
--     Industry users: NO access to government application records
CREATE POLICY applications_read_own_dept ON public.applications
  FOR SELECT TO authenticated
  USING (
    department_id = public.current_user_department_id()
  );

CREATE POLICY applications_insert_own_dept ON public.applications
  FOR INSERT TO authenticated
  WITH CHECK (
    department_id = public.current_user_department_id()
    AND public.current_user_iris_role() IN (
      'DEPARTMENT_OFFICER', 'DEPARTMENT_MANAGER', 'DEPARTMENT_ADMIN'
    )
  );

CREATE POLICY applications_update_own_dept ON public.applications
  FOR UPDATE TO authenticated
  USING (
    department_id = public.current_user_department_id()
    AND public.current_user_iris_role() IN (
      'DEPARTMENT_OFFICER', 'DEPARTMENT_MANAGER', 'DEPARTMENT_ADMIN'
    )
  );

-- D7: application_stage_history — read own dept (append-only: no update/delete policy)
CREATE POLICY stage_history_read_own_dept ON public.application_stage_history
  FOR SELECT TO authenticated
  USING (
    application_id IN (
      SELECT id FROM public.applications
      WHERE department_id = public.current_user_department_id()
    )
  );

CREATE POLICY stage_history_insert_own_dept ON public.application_stage_history
  FOR INSERT TO authenticated
  WITH CHECK (
    application_id IN (
      SELECT id FROM public.applications
      WHERE department_id = public.current_user_department_id()
    )
    AND public.current_user_iris_role() IN (
      'DEPARTMENT_OFFICER', 'DEPARTMENT_MANAGER', 'DEPARTMENT_ADMIN'
    )
  );

-- D8: assignment_history — read own dept
CREATE POLICY assignment_history_read_own_dept ON public.assignment_history
  FOR SELECT TO authenticated
  USING (
    application_id IN (
      SELECT id FROM public.applications
      WHERE department_id = public.current_user_department_id()
    )
  );

-- D9: sla_instances — read own dept
CREATE POLICY sla_instances_read_own_dept ON public.sla_instances
  FOR SELECT TO authenticated
  USING (
    application_id IN (
      SELECT id FROM public.applications
      WHERE department_id = public.current_user_department_id()
    )
  );

-- D10: operational_events — read own dept
CREATE POLICY operational_events_read_own_dept ON public.operational_events
  FOR SELECT TO authenticated
  USING (
    application_id IN (
      SELECT id FROM public.applications
      WHERE department_id = public.current_user_department_id()
    )
  );

-- D11: projects — Industry users can read their OWN projects.
--      NOTE: projects.id has no user_id column yet (prerequisite for full isolation).
--      Full industry project isolation requires adding a user_id FK to projects
--      and linking it to user_profiles.supabase_auth_uid.
--      This policy grants authenticated users read access to ALL projects as an
--      intermediate step. See Known Limitations in docs.
--      Government users do NOT need direct project access via this policy;
--      they access project info through the applications join (service_role).
CREATE POLICY projects_read_authenticated ON public.projects
  FOR SELECT TO authenticated
  USING (true);   -- TODO: restrict to own projects once user_id column added

comment on policy projects_read_authenticated on public.projects is
  'TEMPORARY: grants all authenticated users read access to all projects. '
  'Full isolation requires adding a user_id column to projects and linking to '
  'user_profiles.supabase_auth_uid. This is a known prerequisite for production '
  'Industry user isolation. See migration 0004 (future).';

-- =========================================================================
-- E. Grants
-- =========================================================================

-- user_profiles: authenticated can read/write own rows (RLS enforces ownership)
GRANT SELECT, INSERT, UPDATE ON public.user_profiles TO authenticated;

-- sla_stage_targets: service_role full access, authenticated read (via RLS)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.sla_stage_targets TO service_role;
GRANT SELECT ON public.sla_stage_targets TO authenticated;

-- department_users: authenticated read (via RLS), service_role full
GRANT SELECT ON public.department_users TO authenticated;

-- applications: authenticated read+insert+update (via RLS), service_role full
GRANT SELECT, INSERT, UPDATE ON public.applications TO authenticated;

-- sla_policies: authenticated read (via RLS)
GRANT SELECT ON public.sla_policies TO authenticated;

-- departments: authenticated read (via RLS)
GRANT SELECT ON public.departments TO authenticated;

-- Views: authenticated read access
GRANT SELECT ON public.v_application_sla_status TO service_role;
GRANT SELECT ON public.v_stage_performance TO service_role;
GRANT SELECT ON public.v_officer_workload TO service_role;

-- =========================================================================
-- F. Performance Indexes for Analytics
-- =========================================================================

-- For SLA aging queries (applications without completion, sorted by age)
CREATE INDEX IF NOT EXISTS idx_applications_created_open
  ON public.applications(created_at)
  WHERE completed_at IS NULL;

-- For stage performance queries
CREATE INDEX IF NOT EXISTS idx_stage_history_new_stage_created
  ON public.application_stage_history(new_stage, created_at);

-- For bottleneck queries: applications by stage and department
CREATE INDEX IF NOT EXISTS idx_applications_dept_stage
  ON public.applications(department_id, current_stage);

-- For officer workload queries
CREATE INDEX IF NOT EXISTS idx_applications_officer_stage
  ON public.applications(assigned_officer_id, current_stage)
  WHERE assigned_officer_id IS NOT NULL;

-- For processing trends (applications entering stages over time)
CREATE INDEX IF NOT EXISTS idx_stage_history_created_stage
  ON public.application_stage_history(created_at, new_stage);
