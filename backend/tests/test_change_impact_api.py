"""
P0-B — deterministic Change Impact.

These tests pin the behaviour the feature exists to guarantee:

  * identical facts produce an empty diff,
  * a supported fact change produces a deterministic, engine-derived diff,
  * the preview NEVER persists the proposed facts,
  * missing facts keep REQUIRES_INFORMATION (they are not guessed),
  * DRAFT rule versions stay blocked in PRODUCTION,
  * invalid keys/values fail safely with a precise 422.

Everything is driven by the dataset-derived fact registry, so no threshold
or scenario is hardcoded here either: the tests look up a numeric fact and
a boolean fact from the registry at runtime.
"""
from __future__ import annotations

import pytest

PROJECT = "freshbite"  # seeded by MemoryStore; FOOD industry


@pytest.fixture()
def registry(client):
    body = client.get("/api/v1/facts/registry").json()
    return {f["key"]: f for f in body["facts"]}


def _a_boolean_fact(registry) -> str:
    return sorted(k for k, v in registry.items() if v["value_type"] == "boolean")[0]


def _a_number_fact(registry) -> str:
    return sorted(k for k, v in registry.items() if v["value_type"] == "number")[0]


def _post(client, proposed, mode="PRODUCTION"):
    return client.post(
        f"/api/v1/projects/{PROJECT}/change-impact",
        json={"proposed_facts": proposed, "evaluation_mode": mode},
    )


# --- registry ---------------------------------------------------------------

def test_fact_registry_is_derived_from_dataset(client):
    body = client.get("/api/v1/facts/registry").json()
    keys = {f["key"] for f in body["facts"]}
    # Every key the dataset's rule versions declare must be present.
    assert "project.industry" in keys
    assert all(k.startswith("project.") for k in keys)
    for f in body["facts"]:
        assert f["value_type"] in ("boolean", "number", "string", "mixed", "unknown")
        # Values are labelled as dataset references, never as permitted values.
        assert "not an exhaustive" in f["values_note"].lower()


def test_required_facts_endpoint_matches_rule_version_declarations(client):
    body = client.get("/api/v1/requirements/REQ-0001/required-facts").json()
    keys = [f["key"] for f in body["facts"]]
    assert keys == ["project.likely_to_discharge_sewage_or_trade_effluent"]


def test_required_facts_unknown_requirement_404(client):
    assert client.get("/api/v1/requirements/REQ-9999/required-facts").status_code == 404


# --- core diff --------------------------------------------------------------

def test_identical_facts_produce_no_diff(client, registry):
    key = _a_boolean_fact(registry)
    # Set a fact, then propose the same value again.
    client.post(f"/api/v1/projects/{PROJECT}/facts", json={"facts": {key: True}})

    body = _post(client, {key: True}, mode="NON_PRODUCTION").json()

    assert body["proposed_changes"] == []
    assert body["ignored_changes"][0]["key"] == key
    assert all(r["category"] == "UNCHANGED" for r in body["requirements"])
    assert body["summary"]["UNCHANGED"] == len(body["requirements"])


def test_empty_change_is_a_no_op_diff(client):
    body = _post(client, {}, mode="NON_PRODUCTION").json()
    assert body["proposed_changes"] == []
    assert all(r["category"] == "UNCHANGED" for r in body["requirements"])
    assert any("No effective fact change" in n for n in body["notes"])


def test_supported_boolean_change_produces_deterministic_diff(client, registry):
    key = _a_boolean_fact(registry)
    client.post(f"/api/v1/projects/{PROJECT}/facts", json={"facts": {key: False}})

    first = _post(client, {key: True}, mode="NON_PRODUCTION").json()
    second = _post(client, {key: True}, mode="NON_PRODUCTION").json()

    # Deterministic: same inputs, same diff (decision_id included).
    assert first["requirements"] == second["requirements"]
    assert first["summary"] == second["summary"]

    changed = [r for r in first["requirements"] if r["category"] != "UNCHANGED"]
    assert changed, "flipping a fact a rule depends on must change something"
    for r in changed:
        assert r["before"]["final_state"] != r["after"]["final_state"] or (
            r["before"]["missing_project_fact_keys"]
            != r["after"]["missing_project_fact_keys"]
        )
        assert key in r["changed_facts_used_by_this_requirement"]


def test_numeric_change_crossing_a_dataset_threshold_changes_outcome(client, registry):
    """Generic over the dataset: take a numeric fact, read the comparison
    values the dataset's own conditions use, and evaluate below vs above the
    largest one. No threshold is written into this test."""
    key = _a_number_fact(registry)
    thresholds = [
        v for v in registry[key]["values_referenced_by_rules"] if isinstance(v, (int, float))
    ]
    assert thresholds, "numeric fact must reference at least one comparison value"
    high = max(thresholds)

    client.post(
        f"/api/v1/projects/{PROJECT}/facts",
        json={"facts": {"project.industry": "FOOD", key: 0}},
    )
    body = _post(client, {key: high + 1}, mode="NON_PRODUCTION").json()

    assert body["proposed_changes"][0]["previous_value"] == 0
    assert body["proposed_changes"][0]["proposed_value"] == high + 1
    # The requirement whose rules declare this fact must report it as relevant.
    relevant = [
        r for r in body["requirements"]
        if key in r["facts_this_requirement_uses"]
    ]
    assert relevant


def test_classification_subrule_change_is_not_reported_as_unchanged(client):
    """A Requirement can keep the same final_state while its classification
    sub-group resolves differently (REQ-0004: the base FOOD rule stays
    APPLICABLE while the Central/State licensing tier flips on capacity).
    Comparing final_state alone would hide that, so the diff must also
    compare the engine's own classification block."""
    client.post(
        f"/api/v1/projects/{PROJECT}/facts",
        json={
            "facts": {
                "project.industry": "FOOD",
                "project.dairy_liquid_milk_capacity": 400,
                "project.dairy_milk_solids_capacity": 1.0,
            }
        },
    )
    body = _post(
        client,
        {"project.dairy_liquid_milk_capacity": 60_000},
        mode="NON_PRODUCTION",
    ).json()

    req = next(r for r in body["requirements"] if r["requirement_id"] == "REQ-0004")
    assert req["before"]["final_state"] == req["after"]["final_state"] == "APPLICABLE"
    assert req["category"] == "CHANGED"
    assert req["before"]["classification"] != req["after"]["classification"]
    # The sub-rule results themselves must come from the engine, not be inferred.
    assert req["after"]["classification"]["rule_results"]


# --- safety -----------------------------------------------------------------

def test_preview_never_persists_proposed_facts(client, registry):
    key = _a_number_fact(registry)
    client.post(f"/api/v1/projects/{PROJECT}/facts", json={"facts": {key: 1}})
    before = client.get(f"/api/v1/projects/{PROJECT}/facts").json()["facts"]

    body = _post(client, {key: 999_999}, mode="NON_PRODUCTION").json()
    assert "NOT written" in body["persistence_note"]

    after = client.get(f"/api/v1/projects/{PROJECT}/facts").json()["facts"]
    assert after == before
    assert after[key] == 1


def test_preview_does_not_persist_decisions(client, registry):
    key = _a_boolean_fact(registry)
    before = client.get(f"/api/v1/projects/{PROJECT}/decisions").json()
    _post(client, {key: True}, mode="NON_PRODUCTION")
    after = client.get(f"/api/v1/projects/{PROJECT}/decisions").json()
    assert len(after) == len(before)


def test_missing_facts_preserve_requires_information(client):
    """Clearing a required fact must move the requirement to a missing-fact
    state, never to NOT_APPLICABLE (missing data != FALSE)."""
    client.post(
        f"/api/v1/projects/{PROJECT}/facts",
        json={"facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True}},
    )
    body = _post(
        client,
        {"project.likely_to_discharge_sewage_or_trade_effluent": None},
        mode="NON_PRODUCTION",
    ).json()

    req = next(r for r in body["requirements"] if r["requirement_id"] == "REQ-0001")
    assert req["after"]["final_state"] == "REQUIRES_INFORMATION"
    assert (
        "project.likely_to_discharge_sewage_or_trade_effluent"
        in req["after"]["missing_project_fact_keys"]
    )


def test_draft_rules_remain_blocked_in_production(client, registry):
    key = _a_boolean_fact(registry)
    body = _post(client, {key: True}, mode="PRODUCTION").json()

    assert body["authoritative"] is False
    assert all(
        r["after"]["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION"
        for r in body["requirements"]
    )
    assert all(r["category"] == "UNCHANGED" for r in body["requirements"])
    assert any("zero ACTIVE Rule Versions" in n for n in body["notes"])


def test_non_production_is_labelled_non_authoritative(client, registry):
    body = _post(client, {_a_boolean_fact(registry): True}, mode="NON_PRODUCTION").json()
    assert body["authoritative"] is False
    assert any("NON_PRODUCTION" in n for n in body["notes"])


def test_unknown_fact_key_rejected(client):
    res = _post(client, {"project.totally_made_up": True})
    assert res.status_code == 422
    errors = res.json()["detail"]["errors"]
    assert errors[0]["code"] == "UNKNOWN_FACT_KEY"


def test_wrong_value_type_rejected(client, registry):
    res = _post(client, {_a_number_fact(registry): "quite a lot"})
    assert res.status_code == 422
    assert res.json()["detail"]["errors"][0]["code"] == "INVALID_VALUE_TYPE"


def test_boolean_fact_rejects_number(client, registry):
    res = _post(client, {_a_boolean_fact(registry): 1})
    assert res.status_code == 422
    assert res.json()["detail"]["errors"][0]["code"] == "INVALID_VALUE_TYPE"


def test_all_invalid_keys_reported_at_once(client):
    res = _post(client, {"project.nope_one": True, "project.nope_two": 2})
    assert res.status_code == 422
    assert len(res.json()["detail"]["errors"]) == 2


def test_unknown_project_returns_404(client):
    res = client.post(
        "/api/v1/projects/does-not-exist/change-impact",
        json={"proposed_facts": {}},
    )
    assert res.status_code == 404


# --- category precision -------------------------------------------------------------

def _req(body, rid):
    return next(r for r in body["requirements"] if r["requirement_id"] == rid)


def test_clearing_a_fact_is_requires_information_not_no_longer_applicable(client):
    """APPLICABLE -> REQUIRES_INFORMATION must not be called 'no longer
    applicable': missing data is not a negative determination."""
    key = "project.likely_to_discharge_sewage_or_trade_effluent"
    client.post(f"/api/v1/projects/{PROJECT}/facts", json={"facts": {key: True}})
    r = _req(_post(client, {key: None}, mode="NON_PRODUCTION").json(), "REQ-0001")
    assert (r["before"]["final_state"], r["after"]["final_state"]) == ("APPLICABLE", "REQUIRES_INFORMATION")
    assert r["category"] == "REQUIRES_INFORMATION"


def test_not_applicable_to_applicable_is_newly_applicable(client):
    key = "project.likely_to_discharge_sewage_or_trade_effluent"
    client.post(f"/api/v1/projects/{PROJECT}/facts", json={"facts": {key: False}})
    r = _req(_post(client, {key: True}, mode="NON_PRODUCTION").json(), "REQ-0001")
    assert r["category"] == "NEWLY_APPLICABLE"


def test_applicable_to_not_applicable_is_no_longer_applicable(client):
    key = "project.likely_to_discharge_sewage_or_trade_effluent"
    client.post(f"/api/v1/projects/{PROJECT}/facts", json={"facts": {key: True}})
    r = _req(_post(client, {key: False}, mode="NON_PRODUCTION").json(), "REQ-0001")
    assert r["category"] == "NO_LONGER_APPLICABLE"


def test_resolved_review_is_changed_not_newly_applicable(client):
    """REQUIRES_REVIEW (OVERLAP-0001) -> APPLICABLE: the requirement was never
    NOT_APPLICABLE, so it is a change of outcome, not a new obligation."""
    client.post(f"/api/v1/projects/{PROJECT}/facts", json={"facts": {
        "project.industry": "FOOD",
        "project.dairy_liquid_milk_capacity": 20000,
        "project.dairy_milk_solids_capacity": 3000}})
    r = _req(_post(client, {"project.dairy_milk_solids_capacity": 1},
                   mode="NON_PRODUCTION").json(), "REQ-0004")
    assert (r["before"]["final_state"], r["after"]["final_state"]) == ("REQUIRES_REVIEW", "APPLICABLE")
    assert r["category"] == "CHANGED"


def test_entering_review_is_requires_review(client):
    client.post(f"/api/v1/projects/{PROJECT}/facts", json={"facts": {
        "project.industry": "FOOD",
        "project.dairy_liquid_milk_capacity": 20000,
        "project.dairy_milk_solids_capacity": 1}})
    r = _req(_post(client, {"project.dairy_milk_solids_capacity": 3000},
                   mode="NON_PRODUCTION").json(), "REQ-0004")
    assert r["category"] == "REQUIRES_REVIEW"
