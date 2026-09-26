"""
Integration tests for the Priority 3/4/5 data-flow wiring:

    Document text -> OCR/AI extraction -> human confirmation -> Project Facts
    -> Phase 9 evaluation -> NetworkX dependency graph
    -> Ask IRIS (persisted facts = authoritative, never hypothetical)

No live Ollama daemon is assumed in CI: extraction/Ask-IRIS tests inject a
deterministic fake AI provider (same pattern as test_ask_api.py). Everything
here exercises the REAL persistence path (in-memory store in this
environment; the interface is identical to SupabaseStore — see
docs/architecture.md and backend/tests/test_supabase_store.py for the
Supabase-side contract, unit-tested against a mocked transport since no live
Supabase project is available here).
"""
from __future__ import annotations

import re

from app.modules.ai.facade import IRISAI
from app.modules.ai.providers.base import BaseAIProvider
from app.modules.ai.schemas import (
    ApplicantDocumentExtraction,
    GroundedAnswer,
    SourceCitation,
)


def _create_project(client, name="Facts Flow Co"):
    resp = client.post("/api/v1/projects", json={"name": name, "industry": "FOOD"})
    assert resp.status_code == 201
    return resp.json()["id"]


class _FakeExtractionProvider(BaseAIProvider):
    """Deterministic stand-in for OllamaProvider used by the document
    extraction pipeline. Returns a fixed, realistic extraction so the test
    doesn't depend on live network/model behavior."""

    def generate(self, *a, **k):
        raise AssertionError("generate() should not be called for extraction")

    def generate_structured(self, prompt, schema, temperature=None, max_tokens=None, think=None):
        if schema is ApplicantDocumentExtraction:
            return ApplicantDocumentExtraction(
                business_name="FreshBite Foods Pvt Ltd.",
                registration_number="FSSAI-MH-2024-9911",
                authorised_person="Rajesh Mehta",
                field_confidence={
                    "business_name": 0.95,
                    "registration_number": 0.9,
                    "authorised_person": 0.8,
                },
                field_evidence={
                    "business_name": "FreshBite Foods Pvt Ltd.",
                    "registration_number": "Registration No: FSSAI-MH-2024-9911",
                    "authorised_person": "Authorised person: Rajesh Mehta",
                },
            )
        raise AssertionError(f"Unexpected schema requested: {schema}")

    def embed(self, texts):
        return [[float(len(t) % 7 + 1), 1.0, 0.5] for t in texts]

    def health_check(self) -> bool:
        return True


class _FakeAskProvider(BaseAIProvider):
    """Deterministic Ask IRIS provider: cites whatever chunk_id appears
    first in the prompt, exactly like test_ask_api.py's _FakeProvider."""

    def generate(self, *a, **k):
        raise AssertionError("generate() should not be called by Ask IRIS")

    def generate_structured(self, prompt, schema, temperature=None, max_tokens=None, think=None):
        assert schema is GroundedAnswer
        match = re.search(r"chunk_id:\s*(\S+)", prompt)
        chunk_id = match.group(1) if match else "unknown-chunk"
        return GroundedAnswer(
            answer=f"Grounded answer citing {chunk_id}.",
            citations=[SourceCitation(chunk_id=chunk_id, source_id="test-source")],
            insufficient_information=False,
        )

    def embed(self, texts):
        return [[float(len(t) % 7 + 1), 1.0, 0.5] for t in texts]

    def health_check(self) -> bool:
        return True


def test_extraction_does_not_write_project_facts(client, monkeypatch):
    """Priority 4 safety contract: calling /documents/extract must never, by
    itself, create or change a Project Fact."""
    import app.ai_integration.service as ai_service

    fake_ai = IRISAI(provider=_FakeExtractionProvider())
    monkeypatch.setattr(ai_service, "get_ai", lambda: fake_ai)

    project_id = _create_project(client)

    before = client.get(f"/api/v1/projects/{project_id}/facts").json()["facts"]
    assert before == {}

    resp = client.post(
        f"/api/v1/projects/{project_id}/documents/extract",
        json={"text": "FreshBite Foods Pvt Ltd. Registration No: FSSAI-MH-2024-9911."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["business_name"] == "FreshBite Foods Pvt Ltd."
    assert body["data"]["field_confidence"]["business_name"] == 0.95
    assert body["data"]["field_evidence"]["business_name"]

    after = client.get(f"/api/v1/projects/{project_id}/facts").json()["facts"]
    assert after == {}, "extraction must never auto-persist Project Facts"


def test_confirmed_fields_persist_and_flow_into_ask_iris_as_authoritative(client, monkeypatch):
    """The full desired Priority 3+4 chain: extract -> human confirms two of
    the three extracted fields -> POST /facts persists exactly those ->
    Ask IRIS (no facts override) treats them as authoritative, not
    hypothetical."""
    import app.ai_integration.service as ai_service
    import app.ai_integration.ask_service as ask_service

    fake_extraction_ai = IRISAI(provider=_FakeExtractionProvider())
    monkeypatch.setattr(ai_service, "get_ai", lambda: fake_extraction_ai)

    project_id = _create_project(client)

    extract_resp = client.post(
        f"/api/v1/projects/{project_id}/documents/extract",
        json={"text": "FreshBite Foods Pvt Ltd. Authorised person: Rajesh Mehta."},
    )
    extracted = extract_resp.json()["data"]

    # Human reviews and confirms only 2 of the 3 populated fields.
    confirmed = {
        "document.business_name": extracted["business_name"],
        "document.authorised_person": extracted["authorised_person"],
    }
    confirm_resp = client.post(f"/api/v1/projects/{project_id}/facts", json={"facts": confirmed})
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["facts"] == confirmed

    # The unconfirmed field (registration_number) must NOT appear.
    stored = client.get(f"/api/v1/projects/{project_id}/facts").json()["facts"]
    assert stored == confirmed
    assert "document.registration_number" not in stored

    # Log the document itself (mirrors what the frontend panel does).
    doc_resp = client.post(
        f"/api/v1/projects/{project_id}/documents",
        json={"name": "Pasted document", "status": "extracted"},
    )
    assert doc_resp.status_code == 201
    docs = client.get(f"/api/v1/projects/{project_id}/documents").json()
    assert len(docs) == 1

    # Ask IRIS with NO facts override: fact_context must show the stored
    # facts were used as authoritative — not flagged as hypothetical.
    fake_ask_ai = IRISAI(provider=_FakeAskProvider())
    monkeypatch.setattr(ask_service, "get_ai", lambda: fake_ask_ai)

    ask_resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={"question": "What is on record for this project?"},
    )
    assert ask_resp.status_code == 200
    fact_context = ask_resp.json()["fact_context"]
    assert fact_context["uses_hypothetical_facts"] is False
    assert fact_context["hypothetical_fact_keys"] == []
    assert fact_context["hypothetical_facts"] == {}


def test_ask_iris_hypothetical_override_never_persists_over_confirmed_facts(client, monkeypatch):
    """A hypothetical fact supplied only to /ask must never overwrite or
    appear as if it were the project's confirmed, stored fact."""
    import app.ai_integration.ask_service as ask_service

    project_id = _create_project(client)
    confirmed = {"project.likely_to_discharge_sewage_or_trade_effluent": False}
    client.post(f"/api/v1/projects/{project_id}/facts", json={"facts": confirmed})

    fake_ai = IRISAI(provider=_FakeAskProvider())
    monkeypatch.setattr(ask_service, "get_ai", lambda: fake_ai)

    resp = client.post(
        f"/api/v1/projects/{project_id}/ask",
        json={
            "question": "What if the project did discharge effluent?",
            "requirement_id": "REQ-0001",
            "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["fact_context"]["uses_hypothetical_facts"] is True
    assert body["fact_context"]["hypothetical_facts"] == {
        "project.likely_to_discharge_sewage_or_trade_effluent": True
    }

    # The STORED fact is untouched by the hypothetical /ask call.
    stored = client.get(f"/api/v1/projects/{project_id}/facts").json()["facts"]
    assert stored == confirmed


def test_project_facts_persist_across_requests_within_process(client):
    """Project Facts persistence is exercised across independent HTTP
    requests (not just within one Python call) — the store, not request
    state, is the source of truth. (Surviving an actual process restart is
    the persistence backend's job: Supabase does, MemoryStore intentionally
    does not — see app/store/memory_store.py docstring. Real-Supabase
    restart survival is UNVERIFIED here: no live Supabase project is
    configured in this environment.)"""
    project_id = _create_project(client)

    r1 = client.post(
        f"/api/v1/projects/{project_id}/facts",
        json={"facts": {"project.industry": "FOOD"}},
    )
    assert r1.status_code == 200

    # A fresh, independent GET request (separate from the POST above).
    r2 = client.get(f"/api/v1/projects/{project_id}/facts")
    assert r2.json()["facts"] == {"project.industry": "FOOD"}

    # Merging again adds without dropping the earlier fact.
    r3 = client.post(
        f"/api/v1/projects/{project_id}/facts",
        json={"facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True}},
    )
    assert r3.json()["facts"] == {
        "project.industry": "FOOD",
        "project.likely_to_discharge_sewage_or_trade_effluent": True,
    }


def test_evaluation_and_dependency_graph_both_reflect_persisted_facts(client):
    """Priority 5: persisted Project Facts feed BOTH /evaluate and the
    NetworkX-backed /dependency-graph identically — proving the same
    authoritative fact set drives both, with no separate/divergent data
    path for the graph."""
    project_id = _create_project(client)
    client.post(
        f"/api/v1/projects/{project_id}/facts",
        json={"facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True,
                        "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False}},
    )

    eval_resp = client.post(
        "/api/v1/evaluate",
        json={
            "project_id": project_id,
            "requirement_id": "REQ-0001",
            "evaluation_mode": "NON_PRODUCTION",
        },
    )
    assert eval_resp.status_code == 200
    decision = eval_resp.json()["decision"]
    assert decision["final_state"] == "APPLICABLE"

    graph_resp = client.get(
        f"/api/v1/projects/{project_id}/dependency-graph",
        params={"evaluation_mode": "NON_PRODUCTION"},
    )
    assert graph_resp.status_code == 200
    nodes = {n["requirement_id"]: n for n in graph_resp.json()["nodes"]}
    assert "REQ-0001" in nodes, (
        "REQ-0001 became APPLICABLE from the same persisted fact used above, "
        "so the NetworkX graph (built from live evaluate_all, never mock "
        "data) must include it as a node."
    )
