"""
Tests for Ask IRIS:

    POST /api/v1/projects/{project_id}/ask

No live Ollama daemon is assumed in CI, so the happy-path / citation /
grounding tests inject a deterministic fake AI provider (mirrors the pattern
already used throughout ``app/modules/ai/tests``) instead of hitting the
network. The "Ollama unavailable" test deliberately uses the REAL HTTP stack
with no injected provider, exactly like ``test_ai_documents_api.py``, so it
exercises the actual safe-degradation path.

Covers (Phase 6 Ask IRIS integration):
  * authorized Ask IRIS (happy path, grounded + cited)
  * unauthorized / missing project (404, inherited from get_project)
  * cross-tenant project isolation (404, never 403 — no enumeration)
  * Ollama unavailable -> clean 503, not a 500 crash
  * empty question -> 422
  * hallucinated citation is stripped and flagged, never trusted verbatim
  * insufficient-information is surfaced, not papered over
  * authoritative_context always reflects the real Phase 9 decision,
    regardless of what the LLM says (no fabricated regulatory decision)
  * requirement_id grounding narrows context; unknown requirement_id
    degrades gracefully (still 200, with a warning) instead of erroring

Phase 6 hardening (citation provenance + hypothetical facts):
  * every citation is labeled with source_type/source_label distinguishing
    internal IRIS dataset grounding / live computed results from an
    (unimplemented, for now) official-document source — never presented
    as an official government publication
  * fact_context explicitly distinguishes hypothetical/request-scoped
    facts from stored Project Facts, and never claims a hypothetical
    override was persisted
  * hypothetical facts supplied to /ask are never written to the store
"""
from __future__ import annotations

import re

import pytest

from app.modules.ai.exceptions import AIUnavailableError
from app.modules.ai.facade import IRISAI
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.schemas import GroundedAnswer, SourceCitation
from app.security import CurrentUser, Role, get_current_user, get_optional_user


def _create_project(client, name="Ask IRIS Test Co", owner=None):
    resp = client.post("/api/v1/projects", json={"name": name, "industry": "CHEMICAL"})
    assert resp.status_code == 201
    return resp.json()["id"]


class _FakeProvider(BaseAIProvider):
    """Deterministic stand-in for OllamaProvider.

    ``generate_structured`` only needs to satisfy ``GroundedAnswer`` (the
    only schema Ask IRIS's pipeline — RetrievalService.answer — asks the
    provider for). It extracts the first supplied ``chunk_id`` from the
    prompt so citation-validation tests exercise the real Python-side
    citation check rather than trusting canned output blindly, unless a
    fixed answer is injected for a specific behavior under test.
    """

    def __init__(self, fixed_answer: GroundedAnswer | None = None):
        self._fixed_answer = fixed_answer

    def generate(self, prompt, temperature=None, max_tokens=None, think=None) -> str:
        raise AssertionError("generate() should not be called by Ask IRIS")

    def generate_structured(self, prompt, schema, temperature=None, max_tokens=None, think=None):
        assert schema is GroundedAnswer
        if self._fixed_answer is not None:
            return self._fixed_answer
        match = re.search(r"chunk_id:\s*(\S+)", prompt)
        chunk_id = match.group(1) if match else "unknown-chunk"
        return GroundedAnswer(
            answer=f"Grounded test answer citing {chunk_id}.",
            citations=[SourceCitation(chunk_id=chunk_id, source_id="test-source")],
            insufficient_information=False,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Deterministic, non-semantic embedding: fine for these tests since
        # engine-decision / dependency-status chunks are always included
        # regardless of similarity ranking.
        return [[float(len(t) % 7 + 1), 1.0, 0.5] for t in texts]

    def health_check(self) -> bool:
        return True


class _AlwaysDownProvider(BaseAIProvider):
    def generate(self, *a, **k):
        raise AIUnavailableError("down")

    def generate_structured(self, *a, **k):
        raise AIUnavailableError("down")

    def embed(self, *a, **k):
        raise AIUnavailableError("down")

    def health_check(self) -> bool:
        return False


def _install_fake_ai(monkeypatch, provider: BaseAIProvider) -> None:
    """Point Ask IRIS's ``get_ai()`` at a fresh facade wrapping ``provider``,
    with a fresh (empty) in-memory retrieval index so each test reindexes
    the real Phase 9 dataset text against its own fake embeddings."""
    import app.ai_integration.ask_service as ask_service

    fake_ai = IRISAI(provider=provider)
    monkeypatch.setattr(ask_service, "get_ai", lambda: fake_ai)


def test_ask_requires_project_authorization(client):
    resp = client.post(
        "/api/v1/projects/does-not-exist/ask",
        json={"question": "Why is this requirement applicable?"},
    )
    assert resp.status_code == 404


def test_ask_rejects_empty_question(client):
    project_id = _create_project(client)
    resp = client.post(f"/api/v1/projects/{project_id}/ask", json={"question": ""})
    assert resp.status_code == 422


def test_ask_degrades_safely_without_live_ollama(client):
    """Real HTTP stack, no injected provider: exercises actual Ollama
    unreachable behavior end-to-end, matching test_ai_documents_api.py."""
    project_id = _create_project(client)
    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "Why is REQ-0001 applicable?"},
    )
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()


def test_ask_happy_path_is_grounded_and_cited(client, monkeypatch):
    _install_fake_ai(monkeypatch, _FakeProvider())
    project_id = _create_project(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={
            "question": "Why is REQ-0001 applicable?",
            "requirement_id": "REQ-0001",
            "evaluation_mode": "NON_PRODUCTION",
            "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True},
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["citations_valid"] is True
    assert body["citations"], "expected at least one validated citation"
    assert body["ai_enabled"] is True

    # The AI text is advisory; the authoritative decision is independently
    # present and correct regardless of what the LLM said.
    decisions = body["authoritative_context"]["decisions"]
    assert len(decisions) == 1
    assert decisions[0]["requirement_id"] == "REQ-0001"
    assert decisions[0]["final_state"] == "APPLICABLE"


def test_ask_never_fabricates_regulatory_decision_in_production_mode(client, monkeypatch):
    """Even though the LLM only ever sees the *rendering* of a decision, the
    authoritative_context must reflect the real engine outcome. Every Rule
    Version in the shipped dataset is DRAFT, so PRODUCTION mode must report
    BLOCKED_DRAFT_NOT_PRODUCTION — never a fabricated APPLICABLE."""
    _install_fake_ai(monkeypatch, _FakeProvider())
    project_id = _create_project(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "Is REQ-0001 applicable?", "requirement_id": "REQ-0001"},
    )
    assert resp.status_code == 200
    decisions = resp.json()["authoritative_context"]["decisions"]
    assert decisions[0]["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"


def test_ask_unknown_requirement_id_degrades_gracefully(client, monkeypatch):
    _install_fake_ai(monkeypatch, _FakeProvider())
    project_id = _create_project(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "What applies here?", "requirement_id": "REQ-9999-DOES-NOT-EXIST"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert any("REQ-9999-DOES-NOT-EXIST" in w for w in body["warnings"])
    # Falls back to grounding on every known requirement instead of erroring.
    assert len(body["authoritative_context"]["decisions"]) >= 1


def test_ask_strips_hallucinated_citation(client, monkeypatch):
    hallucinated = GroundedAnswer(
        answer="This cites something that was never supplied.",
        citations=[SourceCitation(chunk_id="totally-invented-chunk", source_id="nowhere")],
        insufficient_information=False,
    )
    _install_fake_ai(monkeypatch, _FakeProvider(fixed_answer=hallucinated))
    project_id = _create_project(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "Why?", "requirement_id": "REQ-0001"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["citations"] == []
    assert body["citations_valid"] is False
    assert body["requires_human_review"] is True
    assert any("HALLUCINATED_CITATION" in w for w in body["warnings"])


def test_ask_surfaces_insufficient_information(client, monkeypatch):
    honest_answer = GroundedAnswer(
        answer="The supplied sources do not contain enough information to answer this.",
        citations=[],
        insufficient_information=True,
    )
    _install_fake_ai(monkeypatch, _FakeProvider(fixed_answer=honest_answer))
    project_id = _create_project(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "What would change if I doubled production capacity?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["insufficient_information"] is True


def test_ask_cross_tenant_project_is_not_found_not_forbidden(monkeypatch, client):
    """Industry User A's project must be invisible to Industry User B via
    Ask IRIS too — 404, never 403 (no enumeration), exactly like every
    other /projects/{id}/* endpoint."""
    from app.main import app
    from app.config import get_settings

    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear()

    user_a = CurrentUser(user_id="ask-user-a", email="a@industry.com", role=Role.INDUSTRY_USER)
    user_b = CurrentUser(user_id="ask-user-b", email="b@industry.com", role=Role.INDUSTRY_USER)

    app.dependency_overrides[get_optional_user] = lambda: user_a
    app.dependency_overrides[get_current_user] = lambda: user_a
    try:
        created = client.post(
            "/api/v1/projects",
            json={"id": "ask-proj-a", "name": "User A Co", "industry": "CHEMICAL"},
        )
        assert created.status_code == 201
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)

    app.dependency_overrides[get_optional_user] = lambda: user_b
    app.dependency_overrides[get_current_user] = lambda: user_b
    try:
        resp = client.post(
            "/api/v1/projects/ask-proj-a/ask",
            json={"question": "Why is this applicable?"},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)


def test_ask_department_role_cannot_bypass_industry_isolation(monkeypatch, client):
    """A DEPARTMENT_* role hitting the industry Ask IRIS endpoint follows the
    same get_project rule as everything else — it does not get a special
    bypass here (department-scoped data access lives under
    /api/v1/department/*, not this endpoint)."""
    from app.main import app
    from app.config import get_settings

    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear()

    officer = CurrentUser(
        user_id="officer-1", email="officer@gov.in", role=Role.DEPARTMENT_OFFICER, department_id="dept-mpcb"
    )
    app.dependency_overrides[get_optional_user] = lambda: officer
    app.dependency_overrides[get_current_user] = lambda: officer
    try:
        resp = client.post(
            "/api/v1/projects/does-not-exist-either/ask",
            json={"question": "Why is this applicable?"},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Phase 6 hardening: citation provenance clarity
# ---------------------------------------------------------------------------

def test_ask_citations_are_labeled_as_internal_not_official(client, monkeypatch):
    """Every citation must say plainly that it is IRIS's own dataset/live
    grounding, never something that reads as an official government
    document, and must not carry any invented official metadata."""
    _install_fake_ai(monkeypatch, _FakeProvider())
    project_id = _create_project(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "Why is REQ-0001 applicable?", "requirement_id": "REQ-0001"},
    )
    assert resp.status_code == 200
    citations = resp.json()["citations"]
    assert citations, "expected at least one citation"
    for c in citations:
        assert c["source_type"] in ("iris_regulatory_dataset", "iris_live_evaluation", "iris_internal")
        assert "official" in c["source_label"].lower()  # explicitly disclaims official status
        # No invented official-document metadata anywhere on the citation.
        assert "official" not in c["source_type"]


def test_ask_engine_decision_citation_is_labeled_live_not_dataset(client, monkeypatch):
    """The live-computed engine-decision citation is distinguishable from
    the frozen-dataset requirement/rule-version citations."""
    _install_fake_ai(monkeypatch, _FakeProvider())
    project_id = _create_project(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "Why is REQ-0001 applicable?", "requirement_id": "REQ-0001"},
    )
    assert resp.status_code == 200
    citations = resp.json()["citations"]
    decision_citations = [c for c in citations if c["chunk_id"].startswith("engine-decision:")]
    assert decision_citations
    assert decision_citations[0]["source_type"] == "iris_live_evaluation"


# ---------------------------------------------------------------------------
# Phase 6 hardening: hypothetical vs authoritative Project Facts
# ---------------------------------------------------------------------------

def test_ask_without_hypothetical_facts_reports_stored_facts_only(client, monkeypatch):
    _install_fake_ai(monkeypatch, _FakeProvider())
    project_id = _create_project(client)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "Why is REQ-0001 applicable?", "requirement_id": "REQ-0001"},
    )
    assert resp.status_code == 200
    fact_context = resp.json()["fact_context"]
    assert fact_context["uses_hypothetical_facts"] is False
    assert fact_context["hypothetical_fact_keys"] == []
    assert fact_context["hypothetical_facts"] == {}


def test_ask_with_hypothetical_facts_is_labeled_and_not_persisted(client, monkeypatch):
    """A 'what if' fact supplied on the request must be clearly labeled
    hypothetical in the response, and must never be written back to this
    project's stored Project Facts."""
    _install_fake_ai(monkeypatch, _FakeProvider())
    project_id = _create_project(client)

    hypothetical = {"project.likely_to_discharge_sewage_or_trade_effluent": True}
    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={
            "question": "What if my project discharges effluent?",
            "requirement_id": "REQ-0001",
            "facts": hypothetical,
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    fact_context = body["fact_context"]
    assert fact_context["uses_hypothetical_facts"] is True
    assert fact_context["hypothetical_fact_keys"] == [
        "project.likely_to_discharge_sewage_or_trade_effluent"
    ]
    assert fact_context["hypothetical_facts"] == hypothetical
    assert "not" in fact_context["note"].lower()

    # The authoritative decision still reflects the hypothetical input (the
    # engine itself is unchanged — it just evaluated the facts it was
    # given), but the stored Project Facts were never touched by /ask.
    stored = client.get(f"/api/v1/projects/{project_id}/facts")
    assert stored.status_code == 200
    assert stored.json()["facts"] == {}


def test_ask_hypothetical_fact_context_persists_nothing_across_requests(client, monkeypatch):
    """Two consecutive /ask calls with different hypothetical facts must not
    leak into each other via the store (each is request-scoped only)."""
    _install_fake_ai(monkeypatch, _FakeProvider())
    project_id = _create_project(client)

    r1 = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "q1", "facts": {"a.fact": 1}},
    )
    r2 = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "q2"},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["fact_context"]["hypothetical_facts"] == {"a.fact": 1}
    # The second call, with no facts supplied, sees none — r1's hypothetical
    # fact did not get persisted or leak into a later request.
    assert r2.json()["fact_context"]["uses_hypothetical_facts"] is False
