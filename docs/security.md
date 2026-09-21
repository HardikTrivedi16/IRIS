# IRIS — Security Notes

## Secrets

* **Supabase service-role key**: lives only in `backend/.env` (see
  `backend/.env.example`), read only by `backend/app/config.py`. It is
  never referenced by anything under `frontend/`. The frontend's own
  `.env.example` only contains `VITE_API_URL`, a plain backend base URL —
  safe to ship in a client bundle, unlike a `VITE_`-prefixed Supabase key
  would be.
* No secrets are committed anywhere in this repository. `.env.example`
  files are templates only; real `.env` files are gitignored (see each
  `gitignore` already present in the frontend, and add one for
  `backend/.env` if this becomes a real git repo).

## CORS

`backend/app/main.py` configures `CORSMiddleware` from `CORS_ORIGINS`
(comma-separated, see `.env.example`), defaulting to common local dev
origins. Only `GET`/`POST` are allowed; credentials are not allowed
(the API is stateless — no cookies).

## SQL injection

The backend never builds raw SQL. `SupabaseStore` talks to Supabase's
PostgREST API using its own filter syntax (`eq.`, `select=`, etc.) via
`httpx` query parameters, which are properly encoded by `httpx`; no string
concatenation into a query is performed anywhere.

## Arbitrary rule execution / unsafe file paths

The engine only ever loads YAML from `backend/regulatory-data/`, resolved
once at startup via `engine_service.py::_resolve_data_root`, which is
either the packaged relative path or an operator-supplied absolute path
from `REGULATORY_DATA_ROOT` — never a path derived from a request. No
endpoint accepts a file path, and no endpoint evaluates code from a
request body.

## Unvalidated IDs / untrusted project facts

* All request bodies go through Pydantic models (`backend/app/schemas.py`)
  — malformed input is rejected with `422` before it reaches the engine or
  the store.
* `project_facts` values from a client are opaque JSON values handed
  straight to the engine's condition evaluator, which is a pure,
  side-effect-free function over its own dataclasses (`conditions.py`,
  `kleene.py`) — there's no code execution path from a fact value.
* Path/query parameters used to build Supabase filters (`project_id`,
  `requirement_id`, `decision_id`) are passed as PostgREST `eq.<value>`
  parameter values (not interpolated into SQL text), so they can't be used
  to inject additional filter clauses.

## API error leakage

A global exception handler in `main.py` catches any unhandled exception,
logs the full traceback server-side, and returns a generic
`{"error": "internal_server_error"}` with no stack trace or exception
message to the client. Engine evaluation failures and persistence
failures are caught explicitly at the router level (see
`backend/app/routers/evaluate.py`, `projects.py`) and are similarly
reduced to short, non-leaking messages before reaching the response.

## Authorization boundaries

**This integration does not add authentication.** The existing frontend
has no login flow, and adding one was out of scope ("do not redesign").
Practical effect: anyone who can reach the backend can call any endpoint
for any `project_id`. This is acceptable for the current
single-tenant/demo/dev use case and is the same trust boundary the
original frontend already had (all data was client-side mock state). It
is **not** acceptable for a real multi-tenant production deployment.
Before that: add Supabase Auth (or another identity provider), put a
`user_id`/`owner_id` on `projects`, and replace the current default-deny
RLS policies with real per-owner policies — see `docs/database.md`'s RLS
section for exactly where to add them.

## Row Level Security (RLS)

Enabled on every Supabase table created by this integration. No policies
are granted to `anon`/`authenticated`, which — combined with RLS being
enabled — means Postgres denies those roles entirely by default. Only
`service_role` (used exclusively by the backend, server-side) can read or
write. See `docs/database.md` for table-by-table detail and the
append-only enforcement on `decisions`/`decision_snapshots`/`audit_records`.

## LLM / "Ask IRIS"

The existing `assistant.tsx` route is untouched mock content in this pass.
It is **not** wired to `/api/v1/evaluate*`, and nothing in the backend
calls an LLM. If/when that feature is connected to a real model, the
correct architecture (per the integration brief, and worth restating
here as a security/correctness boundary, not just a UX one) is: Project
Facts → `iris_engine.Engine` → Decision + Explanation → LLM for
natural-language phrasing only. An LLM must never be given the authority
to decide or override `final_state`.
