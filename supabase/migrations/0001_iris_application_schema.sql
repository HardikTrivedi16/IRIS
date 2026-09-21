-- IRIS — Supabase migration 0001: application/runtime schema
--
-- SCOPE — READ THIS FIRST
-- =======================
-- This migration deliberately does NOT contain tables for conditions,
-- rules, rule versions, requirements, registers, authorities, or any other
-- regulatory concept. The Phase 9 engine treats `regulatory-data/*.yaml`
-- as version-controlled, hash-verified, authoritative source data (see
-- backend/iris_engine/dataset_integrity.py and
-- backend/tests_engine_baseline/test_phase9_data_immutability.py). Copying
-- that data into mutable Postgres rows would create a second source of
-- truth that could silently drift from the file the engine actually
-- evaluates against — exactly what Phase 9's immutability testing exists
-- to prevent. See docs/architecture.md "Regulatory data architecture" for
-- the full rationale.
--
-- What IS in this schema is application/runtime state: projects a user is
-- tracking, the facts they've supplied about those projects, documents
-- they've uploaded, and an append-only record of every Decision the engine
-- has produced (plus its Snapshot and Audit record).
--
-- APPEND-ONLY TABLES
-- ===================
-- `decisions`, `decision_snapshots`, and `audit_records` are append-only:
-- UPDATE and DELETE are revoked from every API-facing role, including
-- service_role. The backend must therefore never try to update a stored
-- Decision — see backend/app/store/supabase_store.py, which INSERTs and,
-- on a duplicate decision_id, SELECTs the existing row and compares
-- content instead of overwriting it (mirroring
-- iris_engine.snapshot.DecisionStore's own in-memory contract).
--
-- ROW LEVEL SECURITY
-- ===================
-- RLS is enabled on every table below. No policies are granted to `anon`
-- or `authenticated` — by design, this prototype's browser frontend never
-- talks to Supabase directly; it only calls this repo's own backend API,
-- which uses the service-role key (server-side only, bypasses RLS) via
-- backend/app/store/supabase_store.py. If/when a future phase adds direct
-- browser-to-Supabase access (e.g. Supabase Auth + per-user rows), add
-- explicit per-user policies then — do not widen these to `true` as a
-- shortcut.

create extension if not exists "pgcrypto"; -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------
-- One row per tracked project. `id` is text (not uuid) so the two existing
-- frontend demo projects ("mahapharm", "freshbite") can keep their current
-- human-readable ids; new projects created via POST /api/v1/projects get a
-- generated uuid string.
create table if not exists public.projects (
  id                text primary key,
  name              text not null,
  industry          text not null,           -- free text; frontend-level label (e.g. "pharmaceutical","food").
                                               -- NOT the same string as the engine's `project.industry` fact
                                               -- (e.g. "FOOD") — that mapping happens in application code,
                                               -- see frontend/src/lib/iris/engine-mapping.ts.
  activity          text,
  location          text,
  stage             text,
  scale             text,
  workers           integer check (workers is null or workers >= 0),
  characteristics   jsonb not null default '{}'::jsonb,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

comment on table public.projects is
  'Application-level project records (NOT regulatory data). Mirrors the shape already used by the existing IRIS frontend prototype (src/lib/iris/types.ts Project).';

alter table public.projects enable row level security;

-- ---------------------------------------------------------------------
-- project_facts
-- ---------------------------------------------------------------------
-- Flat key/value facts about a project, in exactly the shape the engine's
-- `project_facts` dict expects (e.g. key = "project.industry",
-- value = "FOOD"). One row per (project_id, fact_key); updates overwrite
-- the value + updated_at (facts are mutable — a project's declared
-- characteristics can change; only the *Decisions* derived from them are
-- append-only).
create table if not exists public.project_facts (
  id          uuid primary key default gen_random_uuid(),
  project_id  text not null references public.projects(id) on delete cascade,
  fact_key    text not null,
  fact_value  jsonb,
  source      text not null default 'user' check (source in ('user', 'document', 'derived')),
  updated_at  timestamptz not null default now(),
  unique (project_id, fact_key)
);

comment on table public.project_facts is
  'Runtime project facts fed to iris_engine.Engine.evaluate_requirement(project_facts=...). fact_key/fact_value are engine-shaped (e.g. "project.industry" / "FOOD"), not frontend display fields.';

create index if not exists idx_project_facts_project on public.project_facts(project_id);

alter table public.project_facts enable row level security;

-- ---------------------------------------------------------------------
-- documents
-- ---------------------------------------------------------------------
-- Metadata only. Actual file bytes belong in Supabase Storage
-- (bucket suggested: "project-documents"); storage_path points there.
-- Document *extraction* (turning a PDF into project_facts rows) is out of
-- scope for this pass — see docs/architecture.md "Documents" — so status
-- defaults to 'uploaded' and there is no extraction pipeline behind
-- 'extracted' / 'missing-info' / 'mismatch' yet; those values are carried
-- over from the existing frontend prototype's DocumentItem.status so the
-- column is ready for that future work without a schema change.
create table if not exists public.documents (
  id                      uuid primary key default gen_random_uuid(),
  project_id              text not null references public.projects(id) on delete cascade,
  name                    text not null,
  storage_path            text,
  status                  text not null default 'uploaded'
                            check (status in ('uploaded', 'extracted', 'missing-info', 'mismatch')),
  linked_requirement_ids  jsonb not null default '[]'::jsonb, -- array of requirement id strings (engine REQ-### or frontend prototype ids)
  uploaded_at             timestamptz not null default now()
);

comment on table public.documents is
  'Document metadata only; file bytes live in Supabase Storage. No OCR/extraction pipeline is implemented in this pass.';

create index if not exists idx_documents_project on public.documents(project_id);

alter table public.documents enable row level security;

-- ---------------------------------------------------------------------
-- decisions  (append-only)
-- ---------------------------------------------------------------------
-- One row per Decision the engine has produced and the API was asked to
-- persist. decision_payload stores the engine's full Decision dict
-- verbatim (see backend/iris_engine/decision.py::build_requirement_decision)
-- so nothing about a past Decision is lost even as the summary columns
-- below are added/changed over time.
create table if not exists public.decisions (
  id                          uuid primary key default gen_random_uuid(),
  decision_id                 text not null unique,   -- iris_engine.snapshot.compute_decision_id(...)
  project_id                  text references public.projects(id) on delete set null,
  requirement_id              text not null,
  rule_id                     text,
  rule_version_id             text,
  rule_version_status         text,
  final_state                 text not null,
  evaluation_mode             text not null check (evaluation_mode in ('PRODUCTION', 'NON_PRODUCTION')),
  engine_version               text not null,
  is_non_production_result    boolean not null default false,
  review_reason                text,
  conflict_id                  text,
  reason_text                  text,
  decision_payload             jsonb not null,          -- full Decision dict, verbatim
  evaluated_at                 timestamptz not null,
  created_at                   timestamptz not null default now()
);

comment on table public.decisions is
  'Append-only record of every persisted Decision. UPDATE/DELETE are revoked below for every role, including service_role — a Decision must never be silently overwritten (Phase 9 Section 11/12).';

create index if not exists idx_decisions_project on public.decisions(project_id);
create index if not exists idx_decisions_requirement on public.decisions(requirement_id);
create index if not exists idx_decisions_created_at on public.decisions(created_at desc);

alter table public.decisions enable row level security;

-- ---------------------------------------------------------------------
-- decision_snapshots  (append-only, 1:1 with decisions)
-- ---------------------------------------------------------------------
create table if not exists public.decision_snapshots (
  id                 uuid primary key default gen_random_uuid(),
  decision_id        text not null unique references public.decisions(decision_id) on delete cascade,
  snapshot_payload   jsonb not null,   -- iris_engine.snapshot.build_snapshot(...) output, verbatim
  created_at         timestamptz not null default now()
);

comment on table public.decision_snapshots is
  'Append-only Decision Snapshots (iris_engine.snapshot.build_snapshot). One row per decision_id; UPDATE/DELETE revoked below.';

alter table public.decision_snapshots enable row level security;

-- ---------------------------------------------------------------------
-- audit_records  (append-only)
-- ---------------------------------------------------------------------
create table if not exists public.audit_records (
  id               uuid primary key default gen_random_uuid(),
  decision_id      text not null references public.decisions(decision_id) on delete cascade,
  audit_payload    jsonb not null,   -- iris_engine.audit.build_audit_record(...) output, verbatim
  created_at       timestamptz not null default now()
);

comment on table public.audit_records is
  'Append-only structured audit trail (iris_engine.audit.build_audit_record). UPDATE/DELETE revoked below.';

create index if not exists idx_audit_records_decision on public.audit_records(decision_id);

alter table public.audit_records enable row level security;

-- ---------------------------------------------------------------------
-- change_impact_runs  (scaffold only — see docs/architecture.md "Change impact")
-- ---------------------------------------------------------------------
-- The Phase 9 dependency graph (iris_engine/dependencies.py) currently has
-- ZERO verified DEP-### edges in the supplied regulatory-data (five
-- candidate relationships are recorded in dependency_review_register.yaml
-- but explicitly not executed). This table is therefore scaffolding for a
-- future phase, not a working change-impact feature: it lets the API
-- record "fact X changed from A to B, here is what was re-evaluated" once
-- there is real dependency data to walk. Nothing here infers or fabricates
-- a dependency relationship the engine doesn't already have.
create table if not exists public.change_impact_runs (
  id                          uuid primary key default gen_random_uuid(),
  project_id                  text references public.projects(id) on delete cascade,
  changed_fact_key            text not null,
  previous_value              jsonb,
  new_value                   jsonb,
  affected_requirement_ids    jsonb not null default '[]'::jsonb,
  affected_decision_ids       jsonb not null default '[]'::jsonb,
  note                        text,
  created_at                  timestamptz not null default now()
);

comment on table public.change_impact_runs is
  'Scaffold only. iris_engine has zero verified dependency edges today, so affected_requirement_ids is always []  until a future phase adds real DEP-### edges — see iris_engine/dependencies.py.';

create index if not exists idx_change_impact_project on public.change_impact_runs(project_id);

alter table public.change_impact_runs enable row level security;

-- ---------------------------------------------------------------------
-- activity_events  (generic application activity log — not regulatory content)
-- ---------------------------------------------------------------------
create table if not exists public.activity_events (
  id            uuid primary key default gen_random_uuid(),
  project_id    text references public.projects(id) on delete cascade,
  actor         text,
  event_type    text not null,
  message       text not null,
  created_at    timestamptz not null default now()
);

comment on table public.activity_events is
  'Generic application activity log (uploads, evaluations run, facts changed). Not regulatory data.';

create index if not exists idx_activity_events_project on public.activity_events(project_id, created_at desc);

alter table public.activity_events enable row level security;

-- =====================================================================
-- Grants
-- =====================================================================
-- No grants are given to anon/authenticated: this prototype's browser
-- never talks to Supabase directly (see RLS note above). service_role
-- (used only by the backend, server-side) gets normal read/write on the
-- mutable tables, and read/insert-only — explicitly no update/delete — on
-- the three append-only tables.

grant select, insert, update, delete on public.projects, public.project_facts, public.documents,
  public.change_impact_runs, public.activity_events to service_role;

grant select, insert on public.decisions, public.decision_snapshots, public.audit_records to service_role;

revoke update, delete on public.decisions from anon, authenticated, service_role;
revoke update, delete on public.decision_snapshots from anon, authenticated, service_role;
revoke update, delete on public.audit_records from anon, authenticated, service_role;
