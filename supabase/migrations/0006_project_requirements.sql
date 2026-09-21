-- IRIS — Supabase migration 0006: project_requirements (industry readiness data)
--
-- WHY THIS EXISTS
-- ===============
-- The industry portal's Requirements / Regulatory Map / Overview / Compliance
-- pages used to read a hardcoded TypeScript fixture
-- (frontend/src/lib/iris/mock-data.ts). This migration moves that
-- project-tracking data into a real Supabase table so it is:
--   * editable with SQL (no code change / redeploy to update readiness),
--   * per-project, and served through the same backend API as everything else.
--
-- This is APPLICATION/TRACKING data (a company's checklist of approvals and how
-- far along each one is) — NOT engine regulatory data. The Phase 9 engine's
-- authoritative requirements (REQ-0001..0004) still live only in the versioned
-- regulatory-data/ files and are never copied here (same rule as 0001).
--
-- The regulatory dependency graph, "next actions", renewal/compliance list and
-- readiness % shown in the UI are all DERIVED from these rows (by the backend
-- and frontend) — they are not separate tables.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------
-- project_requirements
-- ---------------------------------------------------------------------
create table if not exists public.project_requirements (
  id                   uuid primary key default gen_random_uuid(),
  project_id           text not null references public.projects(id) on delete cascade,
  req_key              text not null,               -- stable key used in depends_on/blocks (e.g. 'mpcb-cte')
  name                 text not null,
  authority            text not null default '—',
  stage                text not null default '',
  status               text not null default 'not-ready'
                         check (status in ('ready','attention','blocked','not-applicable','not-ready')),
  applicability        text not null default 'applicable'
                         check (applicability in ('applicable','not-applicable')),
  documents_total      integer not null default 0 check (documents_total >= 0),
  documents_complete   integer not null default 0 check (documents_complete >= 0),
  depends_on           jsonb not null default '[]'::jsonb,   -- array of req_key strings
  blocks               jsonb not null default '[]'::jsonb,   -- array of req_key strings
  source               text not null default '—',
  description          text not null default '',
  reason               text,                                 -- blocking / attention reason (nullable)
  timeline             text not null default '—',
  sort_order           integer not null default 0,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique (project_id, req_key)
);

comment on table public.project_requirements is
  'Per-project regulatory readiness checklist (application/tracking data, NOT engine regulatory data). One row per approval/milestone the UI shows for a project.';

create index if not exists idx_project_requirements_project
  on public.project_requirements(project_id, sort_order);

alter table public.project_requirements enable row level security;

grant select, insert, update, delete on public.project_requirements to service_role;

-- ---------------------------------------------------------------------
-- documents: add the two display columns the UI register needs
-- ---------------------------------------------------------------------
-- The 0001 documents table stores metadata only. The prototype register also
-- shows per-document "issues" and an "extracted vs project profile" mismatch
-- table; add those as JSON columns so that register can be real data too.
alter table public.documents
  add column if not exists issues jsonb not null default '[]'::jsonb;

alter table public.documents
  add column if not exists extracted_information jsonb not null default '[]'::jsonb;
