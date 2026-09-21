# IRIS — Integration & Setup Guide

> Updated for the pre-presentation hardening pass. This supersedes the
> earlier "Phase 9 engine wiring only" version of this guide — IRIS now also
> has real auth, a real Government portal, real AI document extraction, and
> a real Ask IRIS assistant. See README.md "What's real vs. what's still
> prototype" for the current, accurate feature inventory.

## Prerequisites

* Python 3.12+ (backend)
* Node.js 18+ and `npm` (frontend) — `bun` also works if you prefer it
* (Optional, for real persistence/auth) a Supabase project
* (Optional, for LLM-based field extraction + Ask IRIS) a local
  [Ollama](https://ollama.com) daemon with a chat model and an embedding
  model pulled
* (Optional, for scanned-image → text OCR) a local
  [Tesseract](https://github.com/tesseract-ocr/tesseract) installation

Without Supabase, Ollama, and Tesseract, IRIS still runs fully in **demo
mode**: the Phase 9 engine, NetworkX dependency graph, and government
workflow all work against an in-memory store; AI features (OCR, document
field extraction, Ask IRIS) return a clean "unavailable" (503) instead of
crashing.

**Terminology note:** "OCR" here means exactly one thing — local Tesseract
turning an uploaded image into raw text (`POST /projects/{id}/documents/ocr`,
`backend/app/ai_integration/ocr_service.py`). It is a separate step from,
and always precedes, the LLM-based structured field extraction
(`POST /projects/{id}/documents/extract`) that reads that text. Neither
step ever writes to Project Facts by itself.

## 1. Backend — install & run

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp .env.example .env
# For a first run, the defaults are fine as-is (demo mode). See sections
# 2 and 3 below to enable real Supabase persistence/auth and real Ollama.

IRIS_DEMO_MODE=true uvicorn app.main:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for interactive OpenAPI docs, or
`http://localhost:8000/health`.

`IRIS_DEMO_MODE=true` is required whenever `SUPABASE_URL` is not set —
without it, auth **fails closed** (HTTP 500) rather than granting silent
access, by design (see `docs/security.md`).

## 2. Supabase (optional — real persistence + real login)

Apply the migrations **in order** — do not skip any:

```
supabase/migrations/0001_iris_application_schema.sql
supabase/migrations/0002_department_portal.sql
supabase/migrations/0003_auth_sla_bottlenecks.sql
supabase/migrations/0004_industry_project_ownership.sql
```

In the Supabase dashboard: SQL Editor → paste and run each file, in order.

Then in `backend/.env`:
```
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service role key, from Project Settings → API>
```
Remove/leave `IRIS_DEMO_MODE` unset once real Supabase auth is configured —
demo mode and real auth should not both be relied on in production.

To enable **Google OAuth**: in the Supabase dashboard, Authentication →
Providers → Google, add your OAuth client ID/secret, and set the redirect
URL to `<your-frontend-origin>/auth/callback`.

The service-role key is a server-side secret. It only ever goes in
`backend/.env` — never in `frontend/.env`, never committed. `frontend/.env`
only ever needs the Supabase **anon** key, which is safe to expose.

**Live Supabase verification status:** `SupabaseStore` and
`SupabaseDepartmentStore` are implemented and unit-tested against a mocked
HTTP transport, but have not been exercised against a real Supabase project
in this environment (no live project/credentials available here). Run them
against a real project before relying on this for a live audience if
persistence-across-restart is something you intend to demonstrate.

## 3. Ollama (optional — real AI document extraction + Ask IRIS)

```bash
ollama pull qwen3:8b            # or set IRIS_GENERATION_MODEL to a model you have
ollama pull qwen3-embedding:0.6b
ollama serve                    # usually already running as a service
```

In `backend/.env`, `IRIS_OLLAMA_URL` defaults to `http://localhost:11434` —
only change it if Ollama runs elsewhere. If your locally pulled model
differs from the default (`qwen3:8b`), set:
```
IRIS_GENERATION_MODEL=<your model tag>
```
Without Ollama reachable, `/documents/extract`, `/documents/classify`, and
`/projects/{id}/ask` return a clean `503 Ollama unreachable` — the rest of
the app (Phase 9 evaluation, NetworkX, Government portal) is fully
unaffected, by design.

## 3b. Tesseract (optional — real image → text OCR)

Install the Tesseract binary itself (this is a separate program, not a
Python package):

```bash
# Windows: https://github.com/UB-Mannheim/tesseract/wiki
# macOS:   brew install tesseract
# Debian/Ubuntu: sudo apt install tesseract-ocr
```

Then in `backend`:
```bash
pip install -r requirements.txt   # pulls in pytesseract + Pillow + python-multipart
```

If `tesseract` isn't on your PATH (common on Windows), point IRIS at it
explicitly in `backend/.env`:
```
IRIS_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Check `GET /api/v1/ai/status` → `"ocr_available"` to confirm it's detected.
Without Tesseract reachable, `POST /projects/{id}/documents/ocr` returns a
clean `503` — the LLM extraction step, Phase 9 evaluation, and everything
else remain fully unaffected. **PDF is not supported in this build** (it
would need `poppler` as an additional system dependency) — convert a PDF
page to an image first, or paste its text directly into the extraction
panel.

## 4. Backend — run tests

```bash
cd backend
python -m pytest tests_engine_baseline -q                     # Phase 9 (frozen)
python -m pytest tests/test_dependency_graph_api.py tests/test_graph_adapter.py tests/test_bottlenecks.py -q   # NetworkX
python -m pytest app/modules/ai/tests -q -m "not live_ollama and not live_phase3 and not live_phase4 and not live_phase5 and not live_groq"   # AI module, non-live
python -m pytest tests/test_ask_api.py -q                     # Ask IRIS
python -m pytest tests/test_integration_facts_flow.py -q      # confirm → facts → evaluation → Ask IRIS
python -m pytest tests/test_ocr_api.py -q                     # Tesseract OCR (skipped automatically if Tesseract isn't installed)
python -m pytest tests -q                                     # full backend suite
```
See the final report / `docs/testing.md` for exact pass counts as of the
most recent run.

## 5. Frontend — install, configure, run

```bash
cd frontend
npm install

cp .env.example .env
# VITE_API_URL defaults to http://localhost:8000 — change only if your
# backend runs elsewhere. Leave VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY
# blank for demo mode; fill both in to enable real login (must match the
# same Supabase project as the backend's SUPABASE_URL).

npm run dev
```

## 6. Frontend — typecheck, lint, build

```bash
cd frontend
npx tsc --noEmit -p tsconfig.json   # typecheck
npm run build                        # production build
```

## Everyday workflow once both are running

**Industry portal** (`/`): demo mode lands you directly in the Industry
shell with two seeded projects (`mahapharm`, `freshbite`). Real auth
(Supabase configured) sends you to `/login` first — sign up or sign in with
Google, and you land in the Industry portal by default.

* **Requirements**: the status strip shows whether the backend is reachable
  and how many Rule Versions are ACTIVE vs DRAFT. Four requirements
  (`mpcb-cte`, `mpcb-cto`, `drug-licence`, `fssai-licence`) show a real
  Phase 9 engine Decision panel; everything else is labelled prototype
  content.
* **Documents**: the "Live document extraction" panel — upload a scanned
  image to run real local Tesseract OCR (or paste text directly), review/
  edit the recognized text, run the real AI extraction API, review
  extracted fields with confidence/evidence, and explicitly confirm which
  ones to save as this project's Project Facts. The register list below it
  is separately labelled prototype data.
* **Ask IRIS**: a real grounded Q&A assistant over the Phase 9 engine +
  NetworkX dependency status + the regulatory dataset's own text, with
  citations and an honest "insufficient information" state.

**Government portal** (`/department`): requires a `DEPARTMENT_*` role (in
demo mode, the fixed demo persona already has one). Dashboard, Applications,
SLA Intelligence, Bottleneck Analytics, and Officer management are all
backed by the real department store — SLA and bottleneck analytics are
government-only and are never exposed to the Industry portal.
