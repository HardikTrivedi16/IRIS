# IRIS — Project Handoff (for a new Claude chat)

Paste/upload this whole file at the start of the new chat. It contains the
context needed to continue development without re-deriving anything.
**Last verified:** 2026-09-20 (Windows 11, PowerShell/Git Bash, VS Code).
**Updated 2026-09-21** for the SIH hardening pass (branch
`feature/sih-final-hardening`): see §6a for what was added, and §7/§8 for the
current test state and limitations. Sections not mentioned there are unchanged.

> Secrets are NOT in this file. Real values live in `backend/.env` and
> `frontend/.env` (both already filled in). Never paste the Supabase
> service-role key or JWT secret into chat/docs/commits.

---

## 1. What IRIS is

**Industrial Regulatory Intelligence System** — a prototype with two portals
over one backend:

- **Industry portal** (company, e.g. *Aarav Lifesciences — Selaqui Formulations
  Plant*): readiness %, requirements checklist, regulatory dependency map,
  documents (+ OCR/AI extraction), compliance, change impact, "Ask IRIS" chat.
- **Government portal** (department, e.g. MPCB): dashboard, applications and
  stage workflow, officer assignment, SLA Intelligence, Bottleneck Analytics,
  officers/users, audit log.

Core principle: **a deterministic rule engine decides regulatory applicability;
the local LLM only explains it.** The LLM never decides law.

## 2. Stack & layout

```
IRIS/
├── backend/                 FastAPI (Python 3.12, venv at backend/.venv)
│   ├── app/                 routers/, store/, ai_integration/, modules/ai/, graph/, security.py, config.py, main.py
│   ├── iris_engine/         Phase 9 deterministic rule engine (treat as frozen)
│   ├── dependency_engine/   NetworkX dependency graph
│   ├── regulatory-data/     YAML dataset: 4 requirements REQ-0001..0004, ALL rule versions DRAFT (frozen, hash-verified)
│   ├── tests/               API tests (demo-mode, in-memory store)
│   └── tests_engine_baseline/  original engine tests (frozen)
├── frontend/                TanStack Start + React + TanStack Query + Tailwind/shadcn (Vite, port 3000)
├── supabase/                migrations 0001-0006 + seed_demo_users.sql + seed_aarav_demo.sql
└── docs/                    architecture, database, security, testing, integration guide
```

Infra: **Supabase** (project ref `nzekmvmurxrunifxtqoq`) for Postgres + Auth.
**Ollama** local LLM (`qwen3:4b` generation, `qwen3-embedding:0.6b`
embeddings) and **Tesseract** OCR run on the dev machine. The browser never
talks to Supabase data directly — only to the FastAPI backend (Supabase JS is
used for auth/sign-in only).

## 3. How to run

Two terminals (VS Code):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```
```powershell
cd frontend
npm run dev -- --port 3000
```
Open http://localhost:3000. Ollama app must be running for Ask IRIS /
extraction. If a fresh clone: `python -m venv .venv && pip install -r requirements.txt` in backend, `npm install` in frontend.

**Demo credentials** (seeded in Supabase Auth via `supabase/seed_demo_users.sql`):

| Portal | Email | Password | Role |
|---|---|---|---|
| Industry | industry@gmail.com | <supplied out-of-band>| INDUSTRY_USER, owns project `aarav-lifesciences` |
| Government | department@gmail.com | <supplied out-of-band>| DEPARTMENT_ADMIN, dept `dept-mpcb` |

Windows gotcha: a stale uvicorn/python multiprocessing worker sometimes keeps
port 8000 bound after its parent dies. Find it with
`Get-NetTCPConnection -LocalPort 8000 -State Listen`, kill the python child
(`Get-CimInstance Win32_Process -Filter "Name='python.exe'"` → `Stop-Process`).
Stale backend = old code (symptom: new endpoints 404).

## 4. Environment config (names only)

`backend/.env`: `SUPABASE_URL` (base URL, **no** `/rest/v1`, no leading space
after `=`), `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`,
`SUPABASE_SCHEMA=public`, `REGULATORY_DATA_ROOT`, `SCHEME_DATA_ROOT` (optional;
default `scheme-data`, resolved against `backend/`; ships empty), `CORS_ORIGINS`,
`IRIS_OLLAMA_URL`, `IRIS_GENERATION_MODEL=qwen3:4b`, `IRIS_FALLBACK_MODEL=qwen3:4b`,
`IRIS_EMBEDDING_MODEL=qwen3-embedding:0.6b`. `IRIS_DEMO_MODE` defaults false
(fail-closed; when true and Supabase unset, auth is bypassed with a demo user).

`frontend/.env`: `VITE_API_URL=http://localhost:8000`, `VITE_SUPABASE_URL`,
`VITE_SUPABASE_ANON_KEY` (public by design). Only `VITE_*` reach the browser.

## 5. Critical facts learned (do not re-discover)

1. **Auth = ES256.** This Supabase project signs *user* access tokens with
   ES256; the anon/service API keys are HS256. Public keys are at
   `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` (the older
   `/auth/v1/keys` 404s/401s). `backend/app/config.py::jwks_url` and
   `backend/app/security.py::_verify_jwt` (tries HS256 with the JWT secret
   first, then JWKS RS256/ES256) were fixed for this. **Do not revert.** The
   original symptom was endless 401s on `/api/v1/auth/me`.
2. **Ask IRIS "AI unreachable"** was caused by `IRIS_GENERATION_MODEL` defaulting
   to `qwen3:8b` while only `qwen3:4b` is installed → Ollama 404 → mapped to
   `AIUnavailableError`. Fixed via `backend/.env`. Check `ollama list` first
   if it recurs. Health check (`/api/v1/ai/status`) only pings `/api/version`,
   so it can say reachable while a model is missing.
3. **Logout redirect:** `frontend/src/routes/__root.tsx` `AppInner` has an
   effect that navigates to `/login` when unauthenticated (was broken for
   industry portal). Both sidebars are `sticky top-0 h-screen`
   (`components/iris/app-shell.tsx`, `department-shell.tsx`).
4. **Google OAuth is intentionally NOT implemented.** The button was removed
   from `frontend/src/routes/login.tsx`. `auth-context.tsx` may still expose
   `signInWithGoogle` (unused) and there's an `/auth/callback` route — leave
   or clean up, but don't re-add the button unless asked.
5. The engine's production result for all 4 requirements is
   `BLOCKED_DRAFT_NOT_PRODUCTION` because every Rule Version is DRAFT. This is
   correct safety behavior, not a bug (non-production diagnostic mode exists).
6. Append-only tables (`decisions`, `decision_snapshots`, `audit_records`,
   `application_stage_history`, `assignment_history`, `operational_events`)
   have UPDATE/DELETE revoked for `service_role`. The Supabase **SQL Editor**
   (postgres owner) *can* delete from them — that's how seed scripts stay
   idempotent. The backend cannot.
7. DDL (creating tables) cannot be done through the service-role REST API —
   schema changes must be run as SQL in the Supabase SQL Editor.

## 6. Data model & where data now lives

**Mock data was removed.** `frontend/src/lib/iris/mock-data.ts` now only holds
`regulatorySources` (Sources page directory) and `suggestedQuestions` (Ask
IRIS prompts). Everything per-project comes from Supabase via the backend:

| UI area | Source |
|---|---|
| Projects list | `GET /api/v1/projects` (owner-scoped for industry users) |
| Requirements checklist, readiness, next actions, deadlines, dependency map | `GET /api/v1/projects/{id}/requirements` → table `project_requirements` (migration 0006). Next actions/deadlines/graph are **derived client-side** in `frontend/src/lib/iris/derive.ts` (`deriveNextActions`, `deriveDeadlines`, `buildRegulatoryGraph`). The graph's links are *tracking-register* links, not verified regulatory dependencies. (`deriveCompliance` was removed — see Renewals in §6a.) |
| Documents register | `GET /api/v1/projects/{id}/documents` → `documents` (+ `issues`, `extracted_information` jsonb cols added in 0006) |
| Overview activity timeline | `GET /api/v1/projects/{id}/activity` → `activity_events` |
| Engine decisions (4 real requirements) | `POST /api/v1/evaluate` (+ `/evaluate/all`) + Project Facts (`project_facts`). Both now require the same project ownership/authentication as `/projects/{id}/*`. |
| Ask IRIS | `POST /api/v1/projects/{id}/ask` (RAG: engine + NetworkX + dataset text → Ollama) |
| Gov dashboard/apps/SLA/bottlenecks | `/api/v1/department/*`, `/sla*`, `/bottlenecks*` (tables `applications`, `application_stage_history`, `sla_*`, `operational_events`, …) |

Frontend data hooks: `frontend/src/lib/iris/use-project-data.ts`
(`useProjectRequirements`, `useProjectDocuments`, `useProjectActivity`).
API client: `frontend/src/lib/iris/api-client.ts`. Engine mapping (frontend id →
engine id) in `frontend/src/lib/iris/engine-mapping.ts`: only `mpcb-cte→REQ-0001`,
`mpcb-cto→REQ-0002`, `drug-licence→REQ-0003`, `fssai-licence→REQ-0004` are
engine-backed; all other requirement rows are *tracking data*, labelled
"Prototype content" in the drawer — do not fabricate engine rules for them.

**Supabase state (verified 2026-09-20; migration 0007 was written afterwards
and is NOT yet applied — see §6a):** migrations 0001–0006 applied;
`seed_demo_users.sql` applied; `seed_aarav_demo.sql` applied
(project_requirements=12, documents=7, activity_events=5 for
`aarav-lifesciences`). Government apps `APP-AARAV-REQ-0001` (Water Act) →
APPROVED and `APP-AARAV-REQ-0002` (Air Act) → UNDER_REVIEW, assigned to an
MPCB officer, with backdated stage history. Seed scripts are idempotent.
Readiness for Aarav shows 8 of 11 applicable ready, 2 need action, 0 blocked.

Backend additions for this: `Store.list_project_requirements` /
`list_activity_events` (`store/base.py` default `[]`, `store/supabase_store.py`
real), and routes in `routers/projects.py` that map DB rows → frontend
`Requirement` shape and return `[]` (not an error) if a table is missing.
`MemoryStore` returns empty for these (demo mode has no requirements register).

## 6a. Added in the SIH hardening pass (2026-09-21)

Concise map only; each item has tests under `backend/tests/`. Nothing here
touches the frozen Rule Engine, regulatory dataset, NetworkX core, AI core,
auth architecture or migrations 0001–0006. Every rule version is still DRAFT.

**Industry portal**

| Feature | Route / endpoint | Notes |
|---|---|---|
| New Project + Project Facts + evaluation | `/projects` (3-step flow), `/evaluation`; `POST /projects` (rejects an existing id with 409), `GET /facts/registry`, `GET /requirements/{id}/required-facts` | Fact form is generated from the dataset (`backend/app/fact_registry.py`); nothing hardcoded. |
| Change Impact (real) | `/change-impact`; `POST /projects/{id}/change-impact` | Replaced the old illustrative constant. Evaluates the same engine twice (stored vs hypothetical facts); previews never persist. |
| Decision Proof | drawer on Evaluation / Change Impact; `GET`+`POST /projects/{id}/decision-proof/{req}` | Reshapes the engine's own Decision; provenance stays UNRESOLVED (source records are not in the repo). |
| Pre-submission check | `/documents`; `POST /projects/{id}/consistency-check` | Deterministic data-consistency only (not compliance); read-only. |
| Ask IRIS guards | `/assistant`; `backend/app/ai_integration/engine_guard.py` | Withholds prose that contradicts the engine; other-facility questions get a scope answer with no LLM call. |
| Renewals | `/compliance`; `GET /projects/{id}/renewals` | Days remaining only from an expiry date on record; 90-day action window is a labelled demo policy; synthetic rows labelled. |
| Grievances | `/grievances`; `/projects/{id}/grievances*` | Preparation/tracking/hand-off, **not** a statutory filing; explicit acknowledgement required. |
| Schemes | `/schemes`; `GET /schemes/catalogue`, `GET /projects/{id}/schemes` | Framework only. `backend/scheme-data/` (or `SCHEME_DATA_ROOT`) ships EMPTY → "awaiting verified data". See `docs/SCHEME_CATALOGUE_INPUT_REQUIREMENTS.md`. |
| PDF text | `/documents` upload; `POST /projects/{id}/documents/ocr` | PyMuPDF embedded text per page; Tesseract only for pages without usable text. **PyMuPDF is AGPL-3.0 — review before production.** |

**Government portal:** `/department/grievances` (assign is manager/admin only);
SLA "Why?" panel (`GET /department/sla/applications/{id}/explanation`; page
renamed "SLA Monitoring"); bottleneck components + affected applications
(`GET /department/bottlenecks/explanation`; the composite score is labelled a
prototype heuristic).

**Security fix:** `POST /evaluate` and `/evaluate/all` previously had no
authorization and echoed stored facts for any project id; they now use the
existing project ownership check (unauthenticated → 401, other user → 404).

**Migration 0007 — `supabase/migrations/0007_grievances_and_data_classification.sql`
— is written but NOT applied.** Run it in the Supabase SQL Editor. Until then
grievances return a clear "apply migration 0007" error on Supabase, and
applications carry no `data_classification` (SYNTHETIC_DEMO labelling on the
SLA/bottleneck screens depends on it). It also marks `APP-AARAV-*` /
`APP-SWAAD-*` applications as `SYNTHETIC_DEMO`.

**Still true:** zero verified dependency edges (so no sequencing / critical
path / parallelism claims — the Regulatory Map wording was corrected to say
so); the regulatory pack and scheme catalogue must come from research
(`docs/REGULATORY_PACK_INPUT_REQUIREMENTS.md`,
`docs/SCHEME_CATALOGUE_INPUT_REQUIREMENTS.md`).

## 7. Testing state

- Backend (as of 2026-09-21): `cd backend && .venv\Scripts\python.exe -m pytest
  tests/ tests_engine_baseline/ app/modules/ai/tests -q` → **826 passed,
  6 failed, 2 skipped** (~7 min with Ollama on). The 6 failures are
  environment-dependent, not regressions:
  - 4 assume Ollama is *absent* and fail whenever it is running locally:
    `test_ai_status_reports_unreachable_without_live_ollama`,
    `test_extract_document_degrades_safely_without_live_ollama`,
    `test_classify_document_degrades_safely_without_live_ollama`,
    `test_ask_degrades_safely_without_live_ollama`. They pass with
    `IRIS_OLLAMA_URL=http://127.0.0.1:1` set (or Ollama stopped).
  - 2 are live-model wording checks in the frozen AI module
    (`test_explanations.py::test_live_phase5_case1_dependency`, `…case4_conditional`);
    they also failed at the original baseline.
  The engine baseline alone is 281 passed. The P1/P2 round (renewals,
  grievances, SLA and bottleneck explanations, schemes, PDF) added 73 tests
  across 6 files.
- `tests/conftest.py` sets `SUPABASE_*` env vars to `""` (not deleting them) so
  `load_dotenv` in `config.py` can't re-enable Supabase during tests.
- Engine baseline: `pytest tests_engine_baseline/` (frozen; don't edit).
- Frontend: `cd frontend && npx tsc --noEmit` (clean as of last check;
  `exactOptionalPropertyTypes` is on — assign optional props conditionally
  rather than `undefined`).
- No automated frontend tests; UI was verified manually in the browser.

## 8. Known limitations / sensible next steps

- Change Impact is a **real** engine diff (see §6a), but with every rule
  version DRAFT it can only be authoritative once verified rules are ACTIVE;
  in PRODUCTION mode it honestly reports everything as blocked. The engine
  still has zero verified dependency edges.
- `deriveDeadlines` (Overview) still uses requirement `timeline` text — that is
  free-text tracking data, not a computed date. Renewals on `/compliance` are
  the date-based view (from recorded expiry dates only).
- `lastEvaluated` in `derive.ts` is a static string.
- Requirement writes: there's no UI/API to edit `project_requirements`
  (read-only; change via SQL). Adding create/update endpoints + RLS-safe
  ownership checks would be the natural next feature.
- Only Aarav has seeded requirements; other projects show an empty register.
- Fact capture: a form driven by the dataset's `required_project_facts` now
  exists (`ProjectFactsForm`, §6a). `deriveEngineProjectFacts` remains a narrow
  heuristic bridge for the legacy requirement panel and Ask IRIS only (it no
  longer maps `airEmissions` to the air-control-area fact). Document-confirmed
  facts are stored under `document.*` and are not mapped to engine
  `project.*` facts.
- Promoting rule versions from DRAFT→ACTIVE (in `regulatory-data/`) would make
  production evaluations return real APPLICABLE/NOT_APPLICABLE results, but
  the dataset is hash-verified/frozen — changing it is a deliberate versioned
  act, not a casual edit.
- Only Ollama runs locally; Groq verifier is optional (`IRIS_VERIFIER_*`),
  currently disabled.
- Housekeeping: docs in `docs/` (esp. `testing.md`) are partly stale;
  `README.md`, `Learn.md`, `DEMO_SCRIPT.md`, `HOW_TO_RUN.md`, `.claude/` were
  deleted from the working tree by the user (copies were sent earlier). The
  frontend `.gitignore`/`prettierrc` are stored without leading dots
  (`gitignore`, `prettierrc`, `prettierignore`) — an artifact of how the
  project was exported.

## 9. Working agreements with this user

- Presentation/demo project — **don't break working behavior**; verify with
  real requests (curl/python against the live backend) rather than assuming.
- Explain things in simple, step-by-step language; user is comfortable with VS
  Code basics but not deep tooling. Give exact copy-paste commands.
- User asked for **no mock data** and real Supabase-backed data; keep it that
  way. SQL for data changes should be provided as runnable Supabase SQL
  Editor scripts, kept idempotent.
- Ask before deleting files or doing anything hard to reverse.
- Pronouns: use they/them for the user unless told otherwise.

## 10. Quick verification checklist for a new session

1. `ollama list` shows `qwen3:4b` and `qwen3-embedding:0.6b`.
2. Backend `GET http://127.0.0.1:8000/health` → `persistence_backend: "supabase"`, `requirement_count: 4`.
3. Log in as industry@gmail.com → Requirements shows ~12 rows (8 ready, 2 action required).
4. Ask IRIS: "What is currently blocking this project?" → grounded answer with citations.
5. Log in as department@gmail.com → dashboard: total 2, in progress 1, completed 1.
6. `npx tsc --noEmit` in `frontend/` → no errors.
