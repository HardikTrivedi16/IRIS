"""
P0-C — Decision Proof.

The proof must be a faithful reshaping of the engine's own Decision: same
outcome, same identity, exact matched values, exact missing facts, and
provenance that stays UNRESOLVED rather than being dressed up as a citation.
"""
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.security import CurrentUser, Role, get_current_user, get_optional_user

P = "freshbite"
DISCHARGE = "project.likely_to_discharge_sewage_or_trade_effluent"


def _proof(c, req, mode="NON_PRODUCTION", project=P):
    return c.get(
        f"/api/v1/projects/{project}/decision-proof/{req}",
        params={"evaluation_mode": mode},
    )


def _facts(c, facts, project=P):
    r = c.post(f"/api/v1/projects/{project}/facts", json={"facts": facts})
    assert r.status_code == 200


# --- fidelity to the engine ----------------------------------------------------

def test_proof_matches_engine_result_and_identity(client):
    _facts(client, {DISCHARGE: True})
    body = _proof(client, "REQ-0001").json()
    engine = client.post(
        "/api/v1/evaluate",
        json={"project_id": P, "requirement_id": "REQ-0001",
              "evaluation_mode": "NON_PRODUCTION", "persist": False},
    ).json()["decision"]

    proof = body["proof"]
    assert proof["outcome"]["final_state"] == engine["final_state"] == "APPLICABLE"
    # decision_id is a content hash that excludes evaluated_at: identical
    # inputs must give an identical identity.
    assert proof["identity"]["decision_id"] == engine["decision_id"]
    assert proof["identity"]["rule_version_id"] == engine["rule_version_id"] == "RULE-0001-V1"
    assert proof["identity"]["engine_version"] == engine["engine_version"]
    assert proof["outcome"]["reason_text"] == engine["reason_text"]
    assert body["decision"]["decision_id"] == engine["decision_id"]


def test_matched_values_are_exact(client):
    _facts(client, {DISCHARGE: True})
    proof = _proof(client, "REQ-0001").json()["proof"]
    [m] = proof["matched_conditions"]
    assert m["condition_id"] == "COND-0001"
    assert m["fact_key"] == DISCHARGE
    assert m["actual_value"] is True
    assert m["expected_value"] is True
    assert m["operator"] == "=="
    assert proof["facts_used"] == [{"key": DISCHARGE, "value": True, "provided": True}]
    assert proof["refuses_to_guess"] is False


def test_false_outcome_is_not_a_match(client):
    _facts(client, {DISCHARGE: False})
    proof = _proof(client, "REQ-0001").json()["proof"]
    assert proof["outcome"]["final_state"] == "NOT_APPLICABLE"
    assert proof["matched_conditions"] == []
    assert proof["unmatched_conditions"][0]["actual_value"] is False
    assert proof["unmatched_conditions"][0]["result"] == "FALSE"


def test_missing_facts_are_exact_and_iris_refuses_to_guess(client):
    proof = _proof(client, "REQ-0001").json()["proof"]
    assert proof["outcome"]["final_state"] == "REQUIRES_INFORMATION"
    assert proof["missing_facts"] == [DISCHARGE]
    assert proof["facts_used"] == [{"key": DISCHARGE, "value": None, "provided": False}]
    assert proof["refuses_to_guess"] is True
    assert any(DISCHARGE in r for r in proof["refusal_reasons"])


def test_classification_tree_values_are_exact(client):
    _facts(client, {"project.industry": "FOOD",
                    "project.dairy_liquid_milk_capacity": 60000,
                    "project.dairy_milk_solids_capacity": 1})
    proof = _proof(client, "REQ-0004").json()["proof"]
    assert proof["classification"]["block"]["rule_results"]
    liquid = [m for m in proof["matched_conditions"]
              if m["fact_key"] == "project.dairy_liquid_milk_capacity"]
    assert liquid and all(m["actual_value"] == 60000 for m in liquid)


def test_requires_review_is_surfaced_with_conflict(client):
    """OVERLAP-0001 is registered in the dataset's own conflict register."""
    _facts(client, {"project.industry": "FOOD",
                    "project.dairy_liquid_milk_capacity": 20000,
                    "project.dairy_milk_solids_capacity": 3000})
    proof = _proof(client, "REQ-0004").json()["proof"]
    assert proof["outcome"]["final_state"] == "REQUIRES_REVIEW"
    assert proof["outcome"]["conflict_id"] == "OVERLAP-0001"
    assert proof["refuses_to_guess"] is True
    assert any("OVERLAP-0001" in r for r in proof["refusal_reasons"])


def test_draft_rule_blocked_in_production(client):
    _facts(client, {DISCHARGE: True})
    proof = _proof(client, "REQ-0001", mode="PRODUCTION").json()["proof"]
    assert proof["outcome"]["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
    assert proof["identity"]["rule_version_status"] == "DRAFT"
    assert proof["refuses_to_guess"] is True
    assert any("DRAFT" in r for r in proof["refusal_reasons"])
    assert proof["matched_conditions"] == []  # never reached condition logic


# --- provenance honesty ------------------------------------------------------------

def test_provenance_stays_unresolved_and_ids_exact(client):
    from app.engine_service import get_dataset

    rv = get_dataset().rule_versions["RULE-0001-V1"]
    prov = _proof(client, "REQ-0001").json()["proof"]["provenance"]
    assert prov["status"] == "UNRESOLVED"
    assert prov["resolved_records"] is None
    assert prov["source_ids"] == rv["source_ids"]
    assert prov["evidence_ids"] == rv["evidence_ids"]
    assert prov["instrument_id"] == rv["instrument_id"]
    assert prov["note"]  # the engine's own unresolved note, verbatim


def test_no_fabricated_citation_fields(client):
    prov = _proof(client, "REQ-0001").json()["proof"]["provenance"]
    for forbidden in ("url", "citation", "title", "page", "section", "publication_date"):
        assert forbidden not in prov


# --- safety ------------------------------------------------------------------------

def test_proof_does_not_persist_or_mutate(client):
    _facts(client, {DISCHARGE: True})
    before_d = client.get(f"/api/v1/projects/{P}/decisions").json()
    before_f = client.get(f"/api/v1/projects/{P}/facts").json()
    _proof(client, "REQ-0001", mode="PRODUCTION")
    assert client.get(f"/api/v1/projects/{P}/decisions").json() == before_d
    assert client.get(f"/api/v1/projects/{P}/facts").json() == before_f


def test_unknown_requirement_404(client):
    assert _proof(client, "REQ-9999").status_code == 404


def test_unknown_project_404(client):
    assert _proof(client, "REQ-0001", project="nope").status_code == 404


def test_invalid_mode_422(client):
    assert _proof(client, "REQ-0001", mode="WHATEVER").status_code == 422


def test_auth_fail_closed_and_cross_user(monkeypatch):
    from app.store import get_store

    monkeypatch.setenv("IRIS_DEMO_MODE", "false")
    get_settings.cache_clear()
    get_store.cache_clear()
    c = TestClient(app, raise_server_exceptions=False)
    a = CurrentUser(user_id="a", email="a@x", role=Role.INDUSTRY_USER, name="a", is_demo=False)
    b = CurrentUser(user_id="b", email="b@x", role=Role.INDUSTRY_USER, name="b", is_demo=False)

    def as_(u):
        app.dependency_overrides[get_optional_user] = lambda: u
        app.dependency_overrides[get_current_user] = lambda: u

    try:
        as_(a)
        pid = c.post("/api/v1/projects", json={"name": "A", "industry": "food"}).json()["id"]
        assert _proof(c, "REQ-0001", project=pid).status_code == 200
        as_(b)
        assert _proof(c, "REQ-0001", project=pid).status_code == 404
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        assert _proof(c, "REQ-0001", project=pid).status_code == 401
    finally:
        app.dependency_overrides.pop(get_optional_user, None)
        app.dependency_overrides.pop(get_current_user, None)
        get_settings.cache_clear()
        get_store.cache_clear()


# --- hypothetical proofs (Change Impact "proposed" side) -----------------------

def test_stored_proof_is_labelled_stored(client):
    proof = _proof(client, "REQ-0001").json()["proof"]
    assert proof["fact_basis"] == "STORED"
    assert proof["hypothetical_facts"] == {}


def test_hypothetical_proof_uses_proposed_value_and_is_labelled(client):
    _facts(client, {DISCHARGE: False})
    r = client.post(f"/api/v1/projects/{P}/decision-proof/REQ-0001", json={
        "evaluation_mode": "NON_PRODUCTION", "hypothetical_facts": {DISCHARGE: True}})
    proof = r.json()["proof"]
    assert proof["fact_basis"] == "HYPOTHETICAL"
    assert proof["hypothetical_facts"] == {DISCHARGE: True}
    assert proof["outcome"]["final_state"] == "APPLICABLE"
    assert proof["matched_conditions"][0]["actual_value"] is True
    # never persisted
    assert client.get(f"/api/v1/projects/{P}/facts").json()["facts"][DISCHARGE] is False


def test_hypothetical_proof_matches_change_impact_after_side(client):
    _facts(client, {DISCHARGE: False})
    ci = client.post(f"/api/v1/projects/{P}/change-impact", json={
        "proposed_facts": {DISCHARGE: True}, "evaluation_mode": "NON_PRODUCTION"}).json()
    after = next(r for r in ci["requirements"] if r["requirement_id"] == "REQ-0001")["after"]
    proof = client.post(f"/api/v1/projects/{P}/decision-proof/REQ-0001", json={
        "evaluation_mode": "NON_PRODUCTION", "hypothetical_facts": {DISCHARGE: True}}).json()["proof"]
    assert proof["identity"]["decision_id"] == after["decision_id"]
    assert proof["outcome"]["final_state"] == after["final_state"]


def test_hypothetical_proof_rejects_invalid_facts(client):
    r = client.post(f"/api/v1/projects/{P}/decision-proof/REQ-0001", json={
        "hypothetical_facts": {"project.made_up": 1, DISCHARGE: "yes"}})
    assert r.status_code == 422
    codes = {e["code"] for e in r.json()["detail"]["errors"]}
    assert codes == {"UNKNOWN_FACT_KEY", "INVALID_VALUE_TYPE"}
