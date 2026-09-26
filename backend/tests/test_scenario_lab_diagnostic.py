"""Scenario Lab is hypothetical + diagnostic: before/after must be evaluated with NON_PRODUCTION semantics.

Regression for the browser-observed bug where a 40cr -> 60cr scenario reported "no outcomes changed / 21 unchanged"
because every requirement was lifecycle-blocked (BLOCKED_DRAFT_NOT_PRODUCTION). The production lifecycle gate itself
is unchanged and asserted below.
"""
import copy

from app import change_impact

FACTS = {
    "project.industry": "FOOD",
    "project.food_subsector": "OTHER_FOOD_PROCESSING",
    "project.annual_turnover_inr": 400000000,
    "project.state": "MAHARASHTRA",
    "project.location_state": "MAHARASHTRA",
}
SCENARIO = {"project.annual_turnover_inr": 600000000}


def _run(mode):
    facts = copy.deepcopy(FACTS)
    out = change_impact.analyse_change_impact(
        project_id="scenario-lab-test", current_facts=facts, proposed_changes=SCENARIO, evaluation_mode=mode,
    )
    assert facts == FACTS, "stored/current facts must be byte-identical before and after the preview"
    return out


def test_diagnostic_scenario_shows_the_real_fssai_pathway_change():
    out = _run("NON_PRODUCTION")
    by = {r["requirement_id"]: r for r in out["requirements"]}
    assert out["authoritative"] is False and out["evaluation_mode"] == "NON_PRODUCTION"
    assert out["summary"]["NEWLY_APPLICABLE"] == 1 and out["summary"]["NO_LONGER_APPLICABLE"] == 1
    assert by["REQ-0012"]["category"] == "NO_LONGER_APPLICABLE"   # State licence
    assert by["REQ-0012"]["before"]["final_state"] == "APPLICABLE" and by["REQ-0012"]["after"]["final_state"] == "NOT_APPLICABLE"
    assert by["REQ-0011"]["category"] == "NEWLY_APPLICABLE"       # Central licence
    assert by["REQ-0011"]["before"]["final_state"] == "NOT_APPLICABLE" and by["REQ-0011"]["after"]["final_state"] == "APPLICABLE"
    # Diagnostic label: DRAFT-backed results are non-production; the 9 ACTIVE (approved) ones are not.
    approved = {"REQ-0003", "REQ-0006", "REQ-0007", "REQ-0009", "REQ-0010", "REQ-0015", "REQ-0017", "REQ-0018", "REQ-0019"}
    assert all(r["before"]["is_non_production_result"] == (r["requirement_id"] not in approved)
               for r in out["requirements"])


def test_production_lifecycle_gate_is_unchanged():
    out = _run("PRODUCTION")
    # Verification Batch 1: approved Requirements are ACTIVE (not blocked); every other DRAFT one stays blocked.
    approved = {"REQ-0003", "REQ-0006", "REQ-0007", "REQ-0009", "REQ-0010", "REQ-0015", "REQ-0017", "REQ-0018", "REQ-0019"}
    assert out["summary"]["UNCHANGED"] == len(out["requirements"])
    for r in out["requirements"]:
        assert (r["before"]["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION") == (r["requirement_id"] not in approved)
