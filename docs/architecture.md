# IRIS — Architecture

## Data flow

```
Browser (IRIS frontend, TanStack Start)
   │  fetch() — VITE_API_URL, e.g. http://localhost:8000
   ▼
Backend API (FastAPI, backend/app/)
   │  in-process function calls (no network hop)
   ▼
Phase 9 regulatory rule engine (backend/iris_engine/, UNMODIFIED)
   │  reads
   ▼
Regulatory dataset (backend/regulatory-data/*.yaml, UNMODIFIED, version-controlled)

Backend API
   │  HTTPS + service-role key (server-side only)
   ▼
Supabase (Postgres via PostgREST) — application/runtime state only
```

The frontend never calls Supabase directly, never imports `iris_engine`,
and never asks an LLM to decide regulatory applicability. Every
`/api/v1/evaluate*` response is produced by `iris_engine.Engine`, copied
byte-for-byte from the supplied `IRIS_Phase9_engine.zip` into
`backend/iris_engine/` and `backend/regulatory-data/`.

## Why a separate Python backend, not TanStack server functions

TanStack Start supports server functions/API routes, which would have kept
everything in one process. We didn't use them here because the engine is a
plain, synchronous Python package (`iris_engine`) with its own pytest
suite that had to keep passing byte-for-byte unmodified — running it
required a Python process. A FastAPI service is the smallest way to expose
that Python code to a JS frontend without rewriting it in TypeScript, which
the brief explicitly ruled out ("Do NOT replace the Python engine with an
improvised TypeScript implementation").

## Regulatory data architecture

**The regulatory dataset stays exactly where Phase 9 left it: version-controlled
YAML files loaded from disk at process start, not rows in Supabase.**

Reasons, in order of importance:

1. **Phase 9 already built (and tests) an immutability guarantee for this
   data.** `backend/iris_engine/dataset_integrity.py` hashes the whole
   `regulatory-data/` tree, and
   `backend/tests_engine_baseline/test_phase9_data_immutability.py` fails
   the build if a single byte of it drifts from the pinned manifest.
   Copying the same data into mutable Postgres rows would create a second,
   independently-editable copy of "the law" that could silently diverge
   from the file the engine is actually evaluating against — exactly the
   failure mode that test exists to catch. We didn't want to build a
   second source of truth just to say "it's in the database."
2. **The engine's own conditions/rules/classification code is written
   against the in-memory `RegulatoryDataset` object** (`loader.py`),
   which is populated straight from these files. Moving the data into
   Supabase would require either (a) rewriting the loader to query
   Postgres — touching engine code we were told to leave alone — or
   (b) still loading from files at startup and just *mirroring* them into
   Supabase, which is the second-source-of-truth problem again, for no
   benefit.
3. **Nothing about regulatory content needs multi-writer, row-level
   database semantics.** It's edited by whoever owns the regulatory data
   pipeline (Phase 5/6 in this project's own history), reviewed, and
   deployed with the backend — the same lifecycle as code, not user data.

What Supabase *does* hold is everything that's actually runtime/application
state: which projects a user is tracking, what facts they've told the
system about those projects, what documents they've uploaded, and an
append-only record of every Decision the engine has produced. See
`docs/database.md` for the schema and the exact reasoning per table.

If a future phase needs authorities/rules editable through an admin UI
without a code deploy, the right next step is a proper CMS-style admin
tool with its own review/publish workflow feeding the same YAML files (or
a generated dataset bundle) — not ad hoc Supabase rows the engine's loader
was never designed to read.

## Engine safety properties preserved end-to-end

Every safeguard called out in the integration brief is preserved because
the backend never touches `iris_engine/*.py` and never touches
`regulatory-data/*.yaml` — it only calls the engine's existing public
functions and returns their result:

* **DRAFT rule blocking** — `POST /api/v1/evaluate` in `PRODUCTION` mode
  (the default) returns `BLOCKED_DRAFT_NOT_PRODUCTION` for every one of the
  four requirements, because every Rule Version in the supplied dataset is
  DRAFT (6 DRAFT, 0 ACTIVE — see `GET /api/v1/engine`). The API does not
  promote any Rule Version, ever. `NON_PRODUCTION` mode is available and
  clearly labelled (`is_non_production_result: true`) for diagnostic use.
* **Missing-fact handling** — a requirement whose Rule Version needs a fact
  the caller didn't supply returns `REQUIRES_INFORMATION` with the exact
  missing keys (`missing_project_fact_keys`), never a guess.
* **Conflict/overlap** — `OVERLAP-0001` (RULE-0005 vs RULE-0006, both
  classifying the same FSSAI licence) surfaces as `REQUIRES_REVIEW` with
  `conflict_id: "OVERLAP-0001"` exactly as Phase 9 defined it; nothing
  invents a resolution.
* **Explainability/auditability/reproducibility/versioning** — the
  `explanation`, `classification`, `rule_version_ids`, and `decision_id`
  fields on every Decision are the engine's own output, returned verbatim.
  `backend/app/store/*` persist them (Decision + Snapshot + Audit record)
  without altering a single field.
* **No LLM in the decision path** — nothing in `backend/app/` calls an LLM.
  The existing "Ask IRIS" assistant screen in the frontend
  (`src/routes/assistant.tsx`) remains untouched, mock-only, and separate
  from `/api/v1/evaluate*` — see "Remaining work" below.

## Testing caveats (read before trusting a green checkmark)

* **`SupabaseStore` was never run against a real Supabase project.** This
  sandbox has no live Supabase project and no network egress to
  `supabase.co`. It's unit-tested against a hand-written fake of
  PostgREST's HTTP contract (`backend/tests/test_supabase_store.py`, using
  `httpx.MockTransport`) that checks the exact requests `SupabaseStore`
  sends and how it reacts to a simulated 409 (duplicate `decision_id`).
  That verifies the code's *logic*; it does not verify the SQL migration
  actually creates a schema PostgREST is happy with, or catch anything
  environment-specific about a real Supabase project (connection pooling,
  actual constraint error shapes, RLS role behavior, etc.). **Before
  relying on this in production, run the migration against a real (even
  free-tier) Supabase project and re-point `backend/.env` at it, then
  re-run the same `backend/tests/test_evaluate_api.py` scenarios by hand
  against the live API.**
* The frontend was typechecked and built successfully, but was not run in
  a browser in this environment (no way to click through the UI here) —
  see `docs/testing.md` for exactly what was and wasn't exercised.
