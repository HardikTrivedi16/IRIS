# IRIS — Database (Supabase)

Migration file: `supabase/migrations/0001_iris_application_schema.sql`.
Apply it via the Supabase SQL editor, or `supabase db push` / the CLI's
migration runner, against a real Supabase project.

## What's NOT in this schema, and why

No tables for conditions, rules, rule versions, requirements, registers, or
authorities. See `docs/architecture.md` → "Regulatory data architecture"
for the full reasoning — short version: the Phase 9 engine treats
`regulatory-data/*.yaml` as hash-verified, version-controlled authoritative
source data, and copying it into mutable Postgres rows would create a
second source of truth the engine doesn't actually read from.

## Tables

| Table | Mutable? | Purpose |
|---|---|---|
| `projects` | yes | Application-level project records — mirrors the existing frontend's `Project` shape (`src/lib/iris/types.ts`). |
| `project_facts` | yes | Flat `fact_key`/`fact_value` rows in exactly the shape `iris_engine.Engine.evaluate_requirement(project_facts=...)` expects, e.g. `"project.industry"` → `"FOOD"`. |
| `documents` | yes | Document *metadata* only. File bytes belong in Supabase Storage (`storage_path` points there); no extraction/OCR pipeline exists yet (see "Documents" in the top-level README). |
| `decisions` | **append-only** | One row per persisted engine Decision. `decision_payload` is the engine's full Decision dict, verbatim. |
| `decision_snapshots` | **append-only** | One row per `decision_id`, holding `iris_engine.snapshot.build_snapshot()`'s output verbatim. |
| `audit_records` | **append-only** | One row per `decision_id`, holding `iris_engine.audit.build_audit_record()`'s output verbatim. |
| `change_impact_runs` | yes (scaffold) | Structure for a future change-impact feature. Always empty `affected_requirement_ids` today — the engine's dependency graph has zero verified edges in the supplied dataset (`iris_engine/dependencies.py`). |
| `activity_events` | yes | Generic application activity log (uploads, evaluations run). Not regulatory content. |

## Append-only enforcement

`decisions`, `decision_snapshots`, and `audit_records` have `UPDATE` and
`DELETE` **revoked from every role, including `service_role`** (see the
bottom of the migration file). This means the backend's own service-role
connection cannot update or delete a stored Decision even if application
code had a bug — the database itself enforces Phase 9's "a stored Decision
must never silently change" contract
(`backend/app/store/base.py`'s `DecisionConflictError` docstring), not just
application logic.

Consequence for `backend/app/store/supabase_store.py`: `save_decision`
only ever `INSERT`s. On a duplicate `decision_id` (Postgres unique
violation → PostgREST 409), it reads back the existing row and compares
content via `iris_engine.reproducibility.semantically_equal` — identical
content is a no-op (the same decision was legitimately re-evaluated),
different content raises `DecisionConflictError` (an HTTP 409 from the
API), it never attempts an `UPDATE`.

## Row Level Security

RLS is enabled on every table. No policies are granted to `anon` or
`authenticated` — with RLS enabled and zero policies, Postgres denies
those roles by default. This is intentional for the current architecture:
**the browser never talks to Supabase directly**, only this repo's own
FastAPI backend does, using the service-role key (which bypasses RLS,
which is why `service_role` still gets explicit `GRANT`s at the bottom of
the migration). If a later phase adds direct browser-to-Supabase access
(e.g. via Supabase Auth), add real per-user policies then — don't widen
these to `USING (true)` as a shortcut.

## Ids

`projects.id` is `text`, not `uuid`, so the two existing frontend demo
projects (`"mahapharm"`, `"freshbite"`) can keep their current
human-readable ids without a migration step; `POST /api/v1/projects`
generates a `uuid` string for new projects when none is supplied.
`decisions.decision_id` is the engine's own
`iris_engine.snapshot.compute_decision_id(...)` string (e.g.
`DEC-REQ-0001-a17adb783fb96d3e16cbff15`), not a database-generated id —
the surrogate `id uuid` primary key exists only for Postgres's own
bookkeeping.
