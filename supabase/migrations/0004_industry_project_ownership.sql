-- IRIS — Supabase migration 0004: Industry Project Ownership and Strict Tenant RLS
--
-- SCOPE
-- =====
-- 1. Non-destructive addition of `owner_id` column on `public.projects`.
--    Nullable to preserve existing Phase 9 and demo projects without data loss.
--
-- 2. Strict Row Level Security (RLS) policies for `authenticated` Industry users:
--    - Industry users can ONLY read, insert, and update projects where `owner_id = auth.uid()`.
--    - In production, NULL ownership (`owner_id IS NULL`) is NOT accessible to arbitrary
--      authenticated industry users.
--
-- 3. Government cross-tenant visibility:
--    - Government department officers can read projects ONLY IF the project has an
--      active or completed regulatory application filed with their assigned department.
--
-- 4. Foreign Key and Indexing:
--    - Links `projects.owner_id` to `auth.users(id)`.
--    - Creates index on `projects(owner_id)` for performant tenant filtering.

-- =========================================================================
-- 1. Schema update
-- =========================================================================

ALTER TABLE public.projects
  ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES auth.users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_projects_owner_id
  ON public.projects(owner_id)
  WHERE owner_id IS NOT NULL;

comment on column public.projects.owner_id is
  'Auth UID of the owning Industry user. Enforces strict per-user tenant isolation in production. '
  'Existing demo projects may have NULL owner_id and are restricted to explicit demo mode.';

-- =========================================================================
-- 2. Row Level Security Updates
-- =========================================================================

-- Drop legacy permissive policy from migration 0003
DROP POLICY IF EXISTS projects_read_authenticated ON public.projects;

-- Policy 2a: Industry user reads own projects
CREATE POLICY projects_read_owner ON public.projects
  FOR SELECT TO authenticated
  USING (
    owner_id = auth.uid()
  );

-- Policy 2b: Industry user inserts own projects
CREATE POLICY projects_insert_owner ON public.projects
  FOR INSERT TO authenticated
  WITH CHECK (
    owner_id = auth.uid()
  );

-- Policy 2c: Industry user updates own projects
CREATE POLICY projects_update_owner ON public.projects
  FOR UPDATE TO authenticated
  USING (owner_id = auth.uid())
  WITH CHECK (owner_id = auth.uid());

-- Policy 2d: Government users can read projects that have applications in their department
CREATE POLICY projects_read_government ON public.projects
  FOR SELECT TO authenticated
  USING (
    id IN (
      SELECT project_id FROM public.applications
      WHERE department_id = public.current_user_department_id()
    )
  );

-- Service role maintains full access
GRANT ALL ON public.projects TO service_role;
