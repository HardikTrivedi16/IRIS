from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routers import health, engine_info, requirements, projects, evaluate, decisions, department
from .routers import auth, sla, bottlenecks, dependency_graph, ai_documents, ask, ocr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iris.api")

settings = get_settings()

app = FastAPI(
    title=settings.api_title,
    description=(
        "HTTP API in front of the unmodified Phase 9 deterministic regulatory "
        "rule engine. This service never lets an LLM decide regulatory "
        "applicability; every /evaluate response is produced by "
        "iris_engine.Engine.\n\n"
        "Authentication: Supabase JWT (RS256/JWKS preferred, HS256 fallback). "
        "Demo mode (no Supabase configured): static demo user returned, WARNING logged. "
        "Government endpoints (/api/v1/department/**) require DEPARTMENT_* role. "
        "Industry endpoints require authentication when Supabase is configured."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak raw exception text / stack traces to the client — log
    # server-side, return a generic message.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_server_error"})


app.include_router(health.router)
app.include_router(engine_info.router)
app.include_router(requirements.router)
app.include_router(projects.router)
app.include_router(evaluate.router)
app.include_router(decisions.router)
# Auth router (profile management, /api/v1/auth/*)
app.include_router(auth.router)
# Department router (applications, workflow, user management, /api/v1/department/*)
app.include_router(department.router)
# SLA intelligence (separate router, /api/v1/department/sla/*)
# Note: department.router also handles /api/v1/department/sla/policies
# for backward compatibility. The sla.router handles /dashboard, /applications,
# /stage-performance, /stage-targets (government-only endpoints).
app.include_router(sla.router)
# Bottleneck analytics (/api/v1/department/bottlenecks/*)
app.include_router(bottlenecks.router)
# Dependency & workflow graph (NetworkX-backed, /api/v1/projects/{id}/dependency-graph*)
app.include_router(dependency_graph.router)
# AI / document intelligence (/api/v1/ai/status, /api/v1/projects/{id}/documents/extract|classify)
app.include_router(ai_documents.router)
# Ask IRIS (/api/v1/projects/{id}/ask) — read-only, grounded RAG over Phase 9
# decisions + NetworkX dependency status + the regulatory dataset's own text.
app.include_router(ask.router)
# Local Tesseract OCR (/api/v1/projects/{id}/documents/ocr) — image -> raw
# text only. Feeds the SAME unchanged text -> LLM extraction pipeline above;
# never writes Project Facts or Document records itself.
app.include_router(ocr.router)


@app.get("/")
def root() -> dict:
    return {
        "name": settings.api_title,
        "version": "0.2.0",
        "docs": "/docs",
        "health": "/health",
        "auth_configured": settings.auth_configured,
    }
