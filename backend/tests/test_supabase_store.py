"""
These tests exercise SupabaseStore's request construction and its
append-only conflict handling against a minimal in-memory fake of
Supabase's PostgREST HTTP API, via httpx.MockTransport. No real network
call is made — this environment has no egress to supabase.co and no live
Supabase project to test against (documented in docs/architecture.md
"Testing caveats"). What IS verified here: correct URLs/params/headers,
correct handling of a 409 (duplicate decision_id) response, and the
idempotent-vs-conflict decision logic in save_decision.
"""
import itertools
import sys
import os

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.store.supabase_store import SupabaseStore
from app.store.base import DecisionConflictError, StoreError


class FakePostgrest:
    """Toy in-memory stand-in for the handful of PostgREST endpoints
    SupabaseStore calls. Good enough to test SupabaseStore, not a real
    PostgREST reimplementation."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "projects": [],
            "project_facts": [],
            "documents": [],
            "decisions": [],
            "decision_snapshots": [],
            "audit_records": [],
        }
        self._ids = itertools.count(1)

    def _table_from_path(self, path: str) -> str:
        return path.lstrip("/")

    def _apply_eq_filters(self, rows: list[dict], params: dict) -> list[dict]:
        out = rows
        for key, value in params.items():
            if key in ("select", "order"):
                continue
            if isinstance(value, str) and value.startswith("eq."):
                target = value[3:]
                out = [r for r in out if str(r.get(key)) == target]
        return out

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        # base_url already includes /rest/v1, httpx gives us the full path
        table = path.rsplit("/", 1)[-1]
        params = dict(request.url.params)

        if request.method == "GET":
            rows = self.tables.get(table, [])
            rows = self._apply_eq_filters(rows, params)
            return httpx.Response(200, json=rows)

        if request.method == "POST":
            import json as _json

            payload = _json.loads(request.content)
            rows_in = payload if isinstance(payload, list) else [payload]
            prefer = request.headers.get("prefer", "")
            unique_cols = {
                "projects": "id",
                "decisions": "decision_id",
                "decision_snapshots": "decision_id",
            }.get(table)

            inserted = []
            for row in rows_in:
                existing = None
                if unique_cols:
                    existing = next(
                        (r for r in self.tables[table] if r.get(unique_cols) == row.get(unique_cols)),
                        None,
                    )
                if existing is not None:
                    if "resolution=merge-duplicates" in prefer:
                        existing.update(row)
                        inserted.append(existing)
                    else:
                        return httpx.Response(
                            409,
                            json={"code": "23505", "message": f"duplicate key value violates unique constraint on {table}"},
                        )
                else:
                    row = {"id": next(self._ids), **row}
                    row.setdefault("created_at", "2026-01-01T00:00:00+00:00")
                    self.tables[table].append(row)
                    inserted.append(row)

            if "return=minimal" in prefer:
                return httpx.Response(201, json=None)
            return httpx.Response(201, json=inserted)

        return httpx.Response(405, json={"error": "method not supported by fake"})


@pytest.fixture()
def fake_store():
    fake = FakePostgrest()
    store = SupabaseStore(url="https://example.supabase.co", service_role_key="test-service-role-key")
    store._client = httpx.Client(
        transport=httpx.MockTransport(fake.handle),
        base_url=store._base_url,
        headers=dict(store._client.headers),
    )
    return store, fake


def test_headers_include_service_role_key_never_anon(fake_store):
    store, _ = fake_store
    assert store._client.headers["apikey"] == "test-service-role-key"
    assert store._client.headers["Authorization"] == "Bearer test-service-role-key"


def test_create_and_get_project(fake_store):
    store, _ = fake_store
    created = store.create_project({"id": "acme", "name": "Acme", "industry": "food"})
    assert created["id"] == "acme"
    fetched = store.get_project("acme")
    assert fetched["name"] == "Acme"
    assert store.get_project("nope") is None


def test_merge_project_facts_roundtrip(fake_store):
    store, _ = fake_store
    store.create_project({"id": "acme", "name": "Acme", "industry": "food"})
    facts = store.merge_project_facts("acme", {"project.industry": "FOOD"})
    assert facts == {"project.industry": "FOOD"}


def test_save_decision_inserts_decision_snapshot_and_audit(fake_store):
    store, fake = fake_store
    decision = {
        "decision_id": "DEC-TEST-1",
        "project_id": "acme",
        "requirement_id": "REQ-0001",
        "final_state": "APPLICABLE",
        "evaluation_mode": "NON_PRODUCTION",
        "engine_version": "iris-engine-9.0.0",
        "is_non_production_result": True,
        "evaluated_at": "2026-01-01T00:00:00+00:00",
        "explanation": {"input_facts_used": ["project.likely_to_discharge_sewage_or_trade_effluent"]},
    }
    record = store.save_decision(decision, {"project.likely_to_discharge_sewage_or_trade_effluent": True})
    assert record["decision"]["decision_id"] == "DEC-TEST-1"
    assert record["snapshot"] is not None
    assert record["audit"] is not None
    assert len(fake.tables["decisions"]) == 1
    assert len(fake.tables["decision_snapshots"]) == 1
    assert len(fake.tables["audit_records"]) == 1


def test_save_decision_same_content_twice_is_idempotent(fake_store):
    store, fake = fake_store
    decision = {
        "decision_id": "DEC-TEST-2",
        "project_id": "acme",
        "requirement_id": "REQ-0001",
        "final_state": "NOT_APPLICABLE",
        "evaluation_mode": "NON_PRODUCTION",
        "engine_version": "iris-engine-9.0.0",
        "evaluated_at": "2026-01-01T00:00:00+00:00",
        "explanation": {"input_facts_used": []},
    }
    store.save_decision(decision, {})
    store.save_decision(decision, {})  # identical content -> no-op, not an error
    assert len(fake.tables["decisions"]) == 1


def test_save_decision_conflicting_content_raises(fake_store):
    store, fake = fake_store
    decision_a = {
        "decision_id": "DEC-TEST-3",
        "project_id": "acme",
        "requirement_id": "REQ-0001",
        "final_state": "APPLICABLE",
        "evaluation_mode": "NON_PRODUCTION",
        "engine_version": "iris-engine-9.0.0",
        "evaluated_at": "2026-01-01T00:00:00+00:00",
        "explanation": {"input_facts_used": []},
    }
    decision_b = {**decision_a, "final_state": "NOT_APPLICABLE"}
    store.save_decision(decision_a, {})
    with pytest.raises(DecisionConflictError):
        store.save_decision(decision_b, {})
    assert len(fake.tables["decisions"]) == 1  # the conflicting write never landed


def test_get_decision_returns_none_when_absent(fake_store):
    store, _ = fake_store
    assert store.get_decision("DEC-NOPE") is None
