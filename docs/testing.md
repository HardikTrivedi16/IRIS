# IRIS — Testing Report

Everything below was actually run in the environment this integration was
built in. Nothing is claimed without a command and its real output.

## Backend

### Baseline (before any integration work) — Phase 9 engine, unmodified

```
$ cd IRIS_Phase9_engine   # as originally extracted from IRIS_Phase9_engine.zip
$ python3 -m pytest -q
281 passed in 0.97s
```

Matches `FINAL_AUDIT (1).md`'s own claimed result exactly.

### After copying the engine into backend/iris_engine + backend/regulatory-data (byte-for-byte, no edits)

```
$ cd backend
$ python3 -m pytest tests_engine_baseline -q
281 passed in 0.94s
```

Same 281, same result, from the new location — confirms the copy is exact
and the engine doesn't depend on anything outside its own directory.

### Full backend suite after integration (original engine tests + new API tests)

```
$ cd backend
$ python3 -m pytest tests_engine_baseline tests -q
311 passed in 2.19s
```

Breakdown:

| Suite | Count | What it covers |
|---|---|---|
| `tests_engine_baseline/` | 281 | The original, byte-for-byte Phase 9 suite. **Zero files edited.** |
| `tests/test_health_and_engine_info.py` | 2 | `/health`, `/api/v1/engine` truthfully reporting 0 ACTIVE / 6 DRAFT rule versions and the one known conflict. |
| `tests/test_requirements_api.py` | 3 | `/api/v1/requirements` lists exactly the 4 real requirements; no internal `_source_file` leak; 404 for unknown ids. |
| `tests/test_evaluate_api.py` | 12 | The seven required cases (draft-block, missing-facts, deterministic repeat, explainability, persistence, snapshot/audit, FSSAI conflict) plus evaluate/all, unknown-requirement fail-safe, malformed-input 422, idempotent re-persist, unknown-decision 404. |
| `tests/test_projects_api.py` | 7 | Project CRUD, facts get/merge, evaluate falling back to stored facts, documents. |
| `tests/test_supabase_store.py` | 8 | `SupabaseStore` request construction and append-only conflict handling against a mocked PostgREST transport (see caveat below). |

**Total: 30 new + 281 unmodified = 311.**

### What the Supabase tests do and don't prove

`tests/test_supabase_store.py` never makes a real network call — it swaps
`SupabaseStore`'s internal `httpx.Client` for one backed by
`httpx.MockTransport` pointed at a small in-memory fake of the handful of
PostgREST endpoints the store calls. This proves the store builds the
right requests and reacts correctly to a simulated duplicate-key 409. It
does **not** prove the actual SQL migration works against a real Supabase
project, because no live project or network egress to `supabase.co` was
available in this environment. See `docs/architecture.md`'s "Testing
caveats" for what to do before trusting this in production.

## Frontend

### Install

```
$ cd frontend && npm install
added 414 packages in 1m
```

(`bun` wasn't available in this sandbox; `npm install` against the same
`package.json` was used instead and works.)

### Typecheck

```
$ npx tsc --noEmit -p tsconfig.json
```

Result: **4 errors, all pre-existing.** Confirmed by running the identical
command against the *original, untouched* `IRIS_finished.zip` contents
before any integration changes — the same 4 errors appear there:

* `src/lib/iris/project-context.tsx` — 2 errors (possibly-undefined access, a type mismatch under `exactOptionalPropertyTypes`)
* `src/routes/assistant.tsx` — 1 error (`ChatMessage[]` state update under `exactOptionalPropertyTypes`)
* `src/routes/change-impact.tsx` — 1 error (possibly-undefined access)

Zero new type errors were introduced by this integration's changes
(`api-client.ts`, `engine-mapping.ts`, `use-engine-decision.ts`,
`engine-decision-panel.tsx`, `engine-status-strip.tsx`, and the edits to
`requirements.tsx`).

### Lint

```
$ npm run lint
```

Result: fails, as it did **before** this integration — this repository's
ESLint config enforces Prettier formatting as a lint rule, and the
delivered codebase was not Prettier-clean to begin with (`1367` errors on
the original, untouched code, entirely formatting nits — no `no-unused-vars`
/ `react-hooks` correctness failures beyond 15 pre-existing
`exhaustive-deps` warnings). All new files added by this integration were
run through `npx prettier --write` before packaging; the final lint count
is `1337` (net **lower** than the pre-existing baseline, since formatting
`requirements.tsx` incidentally fixed some of its pre-existing issues too).
No new *logic* lint errors were introduced.

### Build

```
$ npm run build
✓ built in 1.06s
[nitro] √ Generated public .output/public
✓ built in 1.19s
[nitro] √ You can preview this build using npx vite preview
[nitro] √ You can deploy this build using npx nitro deploy --prebuilt
```

Production build succeeds end-to-end (client + SSR + Nitro/Cloudflare
worker bundle).

### What was NOT tested

* The app was never opened in an actual browser in this environment —
  there is no browser/display available here. Typecheck + build passing
  is real signal that the code is structurally sound, but it is not the
  same as clicking through the Requirements page and watching the engine
  panel render. **Do this by hand** after `npm run dev` +
  `uvicorn app.main:app --reload` before considering the UI integration
  fully verified.
* No end-to-end (Playwright/Cypress) tests were added. The brief asked to
  "test frontend API integration where practical" — practical here meant
  typecheck/build plus the backend-side API tests, not a browser
  automation suite, given the scope of everything else in this task.
