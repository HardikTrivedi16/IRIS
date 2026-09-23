"""
Phase 8 §4 — test every current Condition (COND-0001 through COND-0014)
directly against the real, frozen regulatory-data dataset (not synthetic
condition dicts — those are already covered generically by Phase 7's
test_conditions.py). This file exercises the actual authored predicates,
operators, thresholds, and composite trees.

For each applicable condition: TRUE, FALSE where meaningful, UNKNOWN/missing,
and invalid input where meaningful. Confirms missing != FALSE throughout.
"""
import pytest

from iris_engine.conditions import evaluate_condition
from iris_engine.kleene import T, F, U


# ---------------------------------------------------------------------------
# Leaf conditions
# ---------------------------------------------------------------------------

def test_cond_0001_boolean_leaf(dataset):
    c = dataset.conditions
    assert evaluate_condition("COND-0001", c, {"project.likely_to_discharge_sewage_or_trade_effluent": True}).result is T
    assert evaluate_condition("COND-0001", c, {"project.likely_to_discharge_sewage_or_trade_effluent": False}).result is F
    r = evaluate_condition("COND-0001", c, {})
    assert r.result is U
    assert r.missing_fact_keys == ["project.likely_to_discharge_sewage_or_trade_effluent"]


def test_cond_0002_boolean_leaf(dataset):
    c = dataset.conditions
    assert evaluate_condition("COND-0002", c, {"project.plant_located_in_air_pollution_control_area": True}).result is T
    assert evaluate_condition("COND-0002", c, {"project.plant_located_in_air_pollution_control_area": False}).result is F
    assert evaluate_condition("COND-0002", c, {}).result is U


def test_cond_0003_coarse_pharma_gate(dataset):
    # REPURPOSED 2026-09-23 (Pharma tranche, RULE-REV-0002): COND-0003 is
    # now the REQ-0003 coarse gate (COMPOSITE AND of COND-0046/COND-0047),
    # independent of drug_schedule_classification.
    c = dataset.conditions
    gate_true = {
        "project.manufactures_drugs_for_sale_or_distribution": True,
        "project.pharma_activity_type": "FORMULATIONS",
    }
    assert evaluate_condition("COND-0003", c, gate_true).result is T
    gate_false = dict(gate_true, **{"project.pharma_activity_type": "REPACKING"})
    assert evaluate_condition("COND-0003", c, gate_false).result is F
    assert evaluate_condition("COND-0003", c, {}).result is U


def test_cond_0004_industry_set_membership(dataset):
    c = dataset.conditions
    assert evaluate_condition("COND-0004", c, {"project.industry": "FOOD"}).result is T
    assert evaluate_condition("COND-0004", c, {"project.industry": "PHARMA"}).result is F
    assert evaluate_condition("COND-0004", c, {}).result is U


@pytest.mark.parametrize("value,expected", [(50001, T), (50000, F), (1, F), (0, F)])
def test_cond_0005_liquid_milk_threshold(dataset, value, expected):
    r = evaluate_condition("COND-0005", dataset.conditions, {"project.dairy_liquid_milk_capacity": value})
    assert r.result is expected


def test_cond_0005_missing_and_invalid(dataset):
    c = dataset.conditions
    assert evaluate_condition("COND-0005", c, {}).result is U
    r = evaluate_condition("COND-0005", c, {"project.dairy_liquid_milk_capacity": "lots"})
    assert r.result is U
    assert r.error is not None


@pytest.mark.parametrize("value,expected", [(2501, T), (2500, F), (0, F)])
def test_cond_0006_milk_solids_threshold(dataset, value, expected):
    r = evaluate_condition("COND-0006", dataset.conditions, {"project.dairy_milk_solids_capacity": value})
    assert r.result is expected


# ---------------------------------------------------------------------------
# Composites (real trees, not synthetic)
# ---------------------------------------------------------------------------

def test_cond_0007_or_central_composite(dataset):
    c = dataset.conditions
    # both true
    r = evaluate_condition("COND-0007", c, {"project.dairy_liquid_milk_capacity": 60000,
                                             "project.dairy_milk_solids_capacity": 3000})
    assert r.result is T
    # one true, one false -> Kleene OR still TRUE
    r = evaluate_condition("COND-0007", c, {"project.dairy_liquid_milk_capacity": 60000,
                                             "project.dairy_milk_solids_capacity": 100})
    assert r.result is T
    # both false
    r = evaluate_condition("COND-0007", c, {"project.dairy_liquid_milk_capacity": 100,
                                             "project.dairy_milk_solids_capacity": 100})
    assert r.result is F
    # one false, one missing -> F|U = U (per Kleene, NOT false)
    r = evaluate_condition("COND-0007", c, {"project.dairy_liquid_milk_capacity": 100})
    assert r.result is U
    assert "project.dairy_milk_solids_capacity" in r.missing_fact_keys
    # one true, one missing -> T|U = T (known-true criterion is sufficient)
    r = evaluate_condition("COND-0007", c, {"project.dairy_liquid_milk_capacity": 60000})
    assert r.result is T
    # both missing -> U|U = U
    r = evaluate_condition("COND-0007", c, {})
    assert r.result is U


def test_cond_0010_and_state_liquid_range(dataset):
    c = dataset.conditions
    # inside range [501, 50000] inclusive
    assert evaluate_condition("COND-0010", c, {"project.dairy_liquid_milk_capacity": 25000}).result is T
    # exactly at bounds (inclusive)
    assert evaluate_condition("COND-0010", c, {"project.dairy_liquid_milk_capacity": 501}).result is T
    assert evaluate_condition("COND-0010", c, {"project.dairy_liquid_milk_capacity": 50000}).result is T
    # outside range
    assert evaluate_condition("COND-0010", c, {"project.dairy_liquid_milk_capacity": 500}).result is F
    assert evaluate_condition("COND-0010", c, {"project.dairy_liquid_milk_capacity": 50001}).result is F
    # missing -> AND with one missing/one false-able => still never silently FALSE when truly unknown
    r = evaluate_condition("COND-0010", c, {})
    assert r.result is U


def test_cond_0013_and_state_solids_range(dataset):
    c = dataset.conditions
    assert evaluate_condition("COND-0013", c, {"project.dairy_milk_solids_capacity": 1000}).result is T
    assert evaluate_condition("COND-0013", c, {"project.dairy_milk_solids_capacity": 2.5}).result is T
    assert evaluate_condition("COND-0013", c, {"project.dairy_milk_solids_capacity": 2500}).result is T
    assert evaluate_condition("COND-0013", c, {"project.dairy_milk_solids_capacity": 2.4}).result is F
    assert evaluate_condition("COND-0013", c, {"project.dairy_milk_solids_capacity": 2500.1}).result is F


def test_cond_0014_or_state_root(dataset):
    c = dataset.conditions
    # satisfies via liquid dimension only
    r = evaluate_condition("COND-0014", c, {"project.dairy_liquid_milk_capacity": 40000,
                                             "project.dairy_milk_solids_capacity": 3000})
    assert r.result is T
    # satisfies via solids dimension only
    r = evaluate_condition("COND-0014", c, {"project.dairy_liquid_milk_capacity": 60000,
                                             "project.dairy_milk_solids_capacity": 1000})
    assert r.result is T
    # neither
    r = evaluate_condition("COND-0014", c, {"project.dairy_liquid_milk_capacity": 100,
                                             "project.dairy_milk_solids_capacity": 0.1})
    assert r.result is F
    # totally missing
    assert evaluate_condition("COND-0014", c, {}).result is U


def test_all_61_conditions_are_present_and_individually_evaluable(dataset):
    # 14 Phase 5/6 + 24 Shared+Food (COND-0015..0038) + 7 FSSAI
    # currentness-correction (COND-0039..0045) + 16 Pharma tranche
    # (COND-0046..0061) — see regulatory-data/conditions/*.yaml.
    ids = [f"COND-{i:04d}" for i in range(1, 62)]
    assert set(ids) == set(dataset.conditions.keys())
    for cid in ids:
        # every condition must be evaluable against an empty fact set without raising
        r = evaluate_condition(cid, dataset.conditions, {})
        assert r.result in (T, F, U)


def test_missing_condition_reference_in_real_tree_fails_safe(dataset):
    # Confirms a broken child reference (simulated, not persisted) fails to
    # UNKNOWN rather than raising or silently skipping the missing child.
    import copy
    conditions = copy.deepcopy(dataset.conditions)
    conditions["COND-0007"]["child_condition_ids"] = ["COND-0005", "COND-DOES-NOT-EXIST"]
    r = evaluate_condition("COND-0007", conditions, {"project.dairy_liquid_milk_capacity": 100})
    # COND-0005 -> F, missing child -> U (error), F|U = U
    assert r.result is U
    assert any(child.error for child in r.children)
