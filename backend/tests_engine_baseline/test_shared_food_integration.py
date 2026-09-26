"""
Shared + Food regulatory-data integration pass (SH-01/02/03/04/05/07/08/10,
FD-01/02/04) — MH_MULTI_SECTOR_REGULATORY_RESEARCH.md.

Covers exactly the scenarios item 20 of the implementation brief names:
the FD-01/FD-02 CURRENT turnover-based regime (see below), factory
19/20/39/40 boundaries, boiler 24.9/25 boundary, the dairy guard (non-dairy
never enters dairy rules; dairy still does), DRAFT-not-authoritative-in-
PRODUCTION, and the zero-dependency-edges invariant.

Every Rule Version touched here is DRAFT — PRODUCTION-mode calls are
expected to return BLOCKED_DRAFT_NOT_PRODUCTION; NON_PRODUCTION
(diagnostic) mode is used throughout to exercise the actual condition
logic, exactly like every other test in this suite for the (also still
DRAFT) pre-existing Requirements.

FD-01/FD-02 CURRENT-VS-HISTORICAL (2026-09-23, see
regulatory-data/registers/rule_review_register.yaml RULE-REV-0006): the
installed-capacity ">2 MT/day" criterion (RULE-0014-V1/RULE-0015-V1) was
found to be superseded, effective 01.04.2026, by a turnover-based scheme
(RULE-0014-V2/RULE-0015-V2, + new RULE-0016-V1 for Registration) —
RULE-0014-V1/RULE-0015-V1 are now status: SUPERSEDED, preserved unedited.
`rules_index.yaml`'s `latest_rule_version_id` for RULE-0014/RULE-0015 now
points at the V2s, so `engine.evaluate_requirement("REQ-0011"/"REQ-0012",
...)` exercises the CURRENT turnover regime below — that is what
`dataset.latest_rule_version_id()` (and therefore every generic consumer:
fact registry, requirement evaluation, evidence consistency) actually
reads, not a version_number comparison.

The OLD capacity-based flagship scenarios below are no longer expressible
through `evaluate_requirement`, because `iris_engine.rules.evaluate_rule_version`'s
status gate (Phase 7 §4) only has explicit branches for ACTIVE and DRAFT —
SUPERSEDED falls through to "unrecognized status; failing safe"
(BLOCKED_UNKNOWN_RULE_VERSION_STATUS) by design, and that gate is engine
core, not touched here. So the historical semantics are proven instead at
the condition-tree level directly (`evaluate_condition` against
RULE-0014-V1/RULE-0015-V1's own `condition_expression_root_id`,
COND-0033/COND-0035, completely unedited) — this is the "if the engine
supports that" case from the brief resolving to "yes, at the condition
level; no, through the status-gated Rule Version API."
"""
from iris_engine.rules import EvaluationMode
from iris_engine.conditions import evaluate_condition

NP = EvaluationMode.NON_PRODUCTION
PROD = EvaluationMode.PRODUCTION


# --- FD-01/FD-02 historical (installed-capacity, now SUPERSEDED) -----------
# Proven at the condition-tree level — see module docstring for why.

def test_historical_capacity_flagship_baseline_12_mt_per_day(dataset):
    facts = {
        "project.food_processing_installed_capacity_mt_per_day": 12,
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
    }
    central = evaluate_condition("COND-0033", dataset.conditions, facts)
    state = evaluate_condition("COND-0035", dataset.conditions, facts)
    assert central.result.value == "TRUE"
    assert state.result.value == "FALSE"


def test_historical_capacity_boundary_exactly_2_0_not_central(dataset):
    facts = {
        "project.food_processing_installed_capacity_mt_per_day": 2.0,
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
    }
    central = evaluate_condition("COND-0033", dataset.conditions, facts)
    state = evaluate_condition("COND-0035", dataset.conditions, facts)
    assert central.result.value == "FALSE"
    assert state.result.value == "TRUE"


def test_historical_capacity_boundary_2_0001_is_central(dataset):
    facts = {
        "project.food_processing_installed_capacity_mt_per_day": 2.0001,
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
    }
    central = evaluate_condition("COND-0033", dataset.conditions, facts)
    state = evaluate_condition("COND-0035", dataset.conditions, facts)
    assert central.result.value == "TRUE"
    assert state.result.value == "FALSE"


def test_historical_capacity_milling_exclusion(dataset):
    facts = {
        "project.food_processing_installed_capacity_mt_per_day": 12,
        "project.food_subsector": "GRAIN_CEREAL_PULSE_MILLING",
    }
    central = evaluate_condition("COND-0033", dataset.conditions, facts)
    state = evaluate_condition("COND-0035", dataset.conditions, facts)
    assert central.result.value == "FALSE"
    assert state.result.value == "FALSE"


def test_historical_rule_versions_are_superseded_not_active(dataset):
    v1_central = dataset.rule_versions["RULE-0014-V1"]
    v1_state = dataset.rule_versions["RULE-0015-V1"]
    assert v1_central["status"] == "SUPERSEDED"
    assert v1_state["status"] == "SUPERSEDED"
    assert v1_central["effective_end_date"] == "2026-03-31"
    assert v1_state["effective_end_date"] == "2026-03-31"


# --- FD-01/FD-02/Registration CURRENT (turnover-based, effective 01.04.2026) -
# Amounts are plain integer INR (1.5 crore = 15,000,000; 50 crore =
# 500,000,000) — never fractional-crore floats, per this dataset's existing
# integer-comparison convention.

_ONE_POINT_FIVE_CR = 15_000_000
_FIFTY_CR = 500_000_000


def test_current_turnover_40cr_state_applicable_central_not(engine):
    facts = {
        "project.industry": "FOOD",  # Batch 2 final pass: FSSAI classification requires the FOOD industry gate
        "project.annual_turnover_inr": 400_000_000,  # 40 crore
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
    }
    central = engine.evaluate_requirement("P", "REQ-0011", facts, NP)
    state = engine.evaluate_requirement("P", "REQ-0012", facts, NP)
    assert state["final_state"] == "APPLICABLE"
    assert central["final_state"] == "NOT_APPLICABLE"


def test_current_turnover_50cr_boundary_state_applicable_central_not(engine):
    facts = {
        "project.industry": "FOOD",  # Batch 2 final pass: FSSAI classification requires the FOOD industry gate
        "project.annual_turnover_inr": _FIFTY_CR,  # exactly 50 crore
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
    }
    central = engine.evaluate_requirement("P", "REQ-0011", facts, NP)
    state = engine.evaluate_requirement("P", "REQ-0012", facts, NP)
    assert state["final_state"] == "APPLICABLE"
    assert central["final_state"] == "NOT_APPLICABLE"


def test_current_turnover_50cr_plus_1_rupee_central_applicable_state_not(engine):
    facts = {
        "project.industry": "FOOD",  # Batch 2 final pass: FSSAI classification requires the FOOD industry gate
        "project.annual_turnover_inr": _FIFTY_CR + 1,
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
    }
    central = engine.evaluate_requirement("P", "REQ-0011", facts, NP)
    state = engine.evaluate_requirement("P", "REQ-0012", facts, NP)
    assert central["final_state"] == "APPLICABLE"
    assert state["final_state"] == "NOT_APPLICABLE"


def test_current_turnover_1_5cr_boundary_registration_state_not(engine):
    facts = {
        "project.industry": "FOOD",  # Batch 2 final pass: FSSAI classification requires the FOOD industry gate
        "project.annual_turnover_inr": _ONE_POINT_FIVE_CR,  # exactly 1.5 crore
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
    }
    registration = engine.evaluate_requirement("P", "REQ-0013", facts, NP)
    state = engine.evaluate_requirement("P", "REQ-0012", facts, NP)
    central = engine.evaluate_requirement("P", "REQ-0011", facts, NP)
    assert registration["final_state"] == "APPLICABLE"
    assert state["final_state"] == "NOT_APPLICABLE"
    assert central["final_state"] == "NOT_APPLICABLE"


def test_current_turnover_1_5cr_plus_1_rupee_state_path(engine):
    facts = {
        "project.industry": "FOOD",  # Batch 2 final pass: FSSAI classification requires the FOOD industry gate
        "project.annual_turnover_inr": _ONE_POINT_FIVE_CR + 1,
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
    }
    registration = engine.evaluate_requirement("P", "REQ-0013", facts, NP)
    state = engine.evaluate_requirement("P", "REQ-0012", facts, NP)
    assert registration["final_state"] == "NOT_APPLICABLE"
    assert state["final_state"] == "APPLICABLE"


def test_current_turnover_unknown_requires_information(engine):
    facts = {"project.food_subsector": "OTHER_FOOD_PROCESSING"}
    central = engine.evaluate_requirement("P", "REQ-0011", facts, NP)
    state = engine.evaluate_requirement("P", "REQ-0012", facts, NP)
    registration = engine.evaluate_requirement("P", "REQ-0013", facts, NP)
    assert central["final_state"] == "REQUIRES_INFORMATION"
    assert state["final_state"] == "REQUIRES_INFORMATION"
    assert registration["final_state"] == "REQUIRES_INFORMATION"


def test_current_turnover_milling_exclusion_never_routes_to_general_manufacturing(engine):
    facts = {
        "project.industry": "FOOD",  # Batch 2 final pass: FSSAI classification requires the FOOD industry gate
        "project.annual_turnover_inr": 400_000_000,
        "project.food_subsector": "GRAIN_CEREAL_PULSE_MILLING",
    }
    central = engine.evaluate_requirement("P", "REQ-0011", facts, NP)
    state = engine.evaluate_requirement("P", "REQ-0012", facts, NP)
    registration = engine.evaluate_requirement("P", "REQ-0013", facts, NP)
    # Batch 2 final pass: SRC-012 gives grain/cereal/pulse milling units a State licence with no turnover limit,
    # so State is now APPLICABLE; the milling unit still never routes to the general-manufacturing Central/Registration tiers.
    assert central["final_state"] == "NOT_APPLICABLE"
    assert state["final_state"] == "APPLICABLE"
    assert registration["final_state"] == "NOT_APPLICABLE"


def test_current_regime_is_what_latest_rule_version_id_points_at(dataset):
    # Guards against a future edit silently pointing the index back at the
    # historical (now SUPERSEDED) versions.
    assert dataset.latest_rule_version_id("RULE-0014") == "RULE-0014-V3"
    assert dataset.latest_rule_version_id("RULE-0015") == "RULE-0015-V3"
    assert dataset.latest_rule_version_id("RULE-0016") == "RULE-0016-V2"


# --- Dairy guard (FD-04) -----------------------------------------------------

def test_dairy_guard_non_dairy_project_never_enters_dairy_rules(engine):
    # The exact defect FD-04 fixes: a non-dairy project supplying (stray)
    # dairy capacity facts must never accidentally satisfy RULE-0005/0006.
    # project.industry is set so RULE-0004's own base applicability isn't
    # itself the thing left UNKNOWN — isolating the dairy-guard behavior.
    facts = {
        "project.industry": "FOOD",
        "project.food_subsector": "OTHER_FOOD_PROCESSING",
        "project.dairy_liquid_milk_capacity": 60000,
        "project.dairy_milk_solids_capacity": 3000,
    }
    central_dairy = engine.evaluate_requirement("P", "REQ-0004", facts, NP)
    assert central_dairy["classification"]["rule_results"] == {
        "RULE-0005": "NOT_APPLICABLE", "RULE-0006": "NOT_APPLICABLE",
    }


def test_dairy_guard_dairy_project_still_evaluates_existing_bands(engine):
    # liquid=25000/solids=1 deliberately stays in the State-only band (not
    # the Central threshold) so this test isolates the guard without also
    # exercising OVERLAP-0001 (see test_fssai_overlap.py for that).
    facts = {
        "project.industry": "FOOD",
        "project.food_subsector": "DAIRY",
        "project.dairy_liquid_milk_capacity": 25000,
        "project.dairy_milk_solids_capacity": 1,
    }
    d = engine.evaluate_requirement("P", "REQ-0004", facts, NP)
    assert d["classification"]["rule_results"]["RULE-0005"] == "NOT_APPLICABLE"
    assert d["classification"]["rule_results"]["RULE-0006"] == "APPLICABLE"
    assert d["final_state"] == "APPLICABLE"


def test_dairy_guard_unknown_subsector_requires_information(engine):
    facts = {
        "project.dairy_liquid_milk_capacity": 60000,
        "project.dairy_milk_solids_capacity": 100,
    }
    d = engine.evaluate_requirement("P", "REQ-0004", facts, NP)
    assert d["final_state"] == "REQUIRES_INFORMATION"


# --- SH-03 factory boundary: 19/20 (with power), 39/40 (without power) -----

def test_factory_boundary_19_workers_with_power_not_applicable(engine):
    facts = {"project.worker_count": 19, "project.manufacturing_process_uses_power": True}
    assert engine.evaluate_requirement("P", "REQ-0005", facts, NP)["final_state"] == "NOT_APPLICABLE"


def test_factory_boundary_20_workers_with_power_applicable(engine):
    facts = {"project.worker_count": 20, "project.manufacturing_process_uses_power": True}
    assert engine.evaluate_requirement("P", "REQ-0005", facts, NP)["final_state"] == "APPLICABLE"


def test_factory_boundary_39_workers_without_power_not_applicable(engine):
    facts = {"project.worker_count": 39, "project.manufacturing_process_uses_power": False}
    assert engine.evaluate_requirement("P", "REQ-0005", facts, NP)["final_state"] == "NOT_APPLICABLE"


def test_factory_boundary_40_workers_without_power_applicable(engine):
    facts = {"project.worker_count": 40, "project.manufacturing_process_uses_power": False}
    assert engine.evaluate_requirement("P", "REQ-0005", facts, NP)["final_state"] == "APPLICABLE"


def test_factory_20_workers_without_power_not_applicable_on_that_branch(engine):
    # 20 workers alone does not satisfy the without-power branch (needs 40);
    # confirms the two branches are not conflated.
    facts = {"project.worker_count": 20, "project.manufacturing_process_uses_power": False}
    assert engine.evaluate_requirement("P", "REQ-0005", facts, NP)["final_state"] == "NOT_APPLICABLE"


def test_factory_licence_detail_shares_applicability_but_independent_lifecycle(engine, dataset):
    # RULE-0008 (licence detail) reuses RULE-0007's condition tree but is a
    # separate DRAFT Rule Version under the same Requirement (REQ-0005) —
    # confirm both resolve the same way on the same facts (same tree), and
    # that classification_rule_ids correctly names RULE-0008.
    req = dataset.requirements["REQ-0005"]
    assert req["evaluated_by_rule_id"] == "RULE-0007"
    assert req["classification_rule_ids"] == ["RULE-0008"]
    facts = {"project.worker_count": 20, "project.manufacturing_process_uses_power": True}
    d = engine.evaluate_requirement("P", "REQ-0005", facts, NP)
    assert d["classification"]["rule_results"]["RULE-0008"] == "APPLICABLE"


# --- SH-04 boiler boundary: 24.9/25 litres ----------------------------------

def test_boiler_boundary_24_9_litres_not_applicable(engine):
    facts = {"project.boiler_volumetric_capacity_litres": 24.9, "project.boiler_design_gauge_pressure_kg_cm2": 1}
    assert engine.evaluate_requirement("P", "REQ-0006", facts, NP)["final_state"] == "NOT_APPLICABLE"


def test_boiler_boundary_25_litres_applicable(engine):
    facts = {"project.boiler_volumetric_capacity_litres": 25, "project.boiler_design_gauge_pressure_kg_cm2": 1}
    assert engine.evaluate_requirement("P", "REQ-0006", facts, NP)["final_state"] == "APPLICABLE"


def test_boiler_boundary_25_litres_but_pressure_below_1_not_applicable(engine):
    facts = {"project.boiler_volumetric_capacity_litres": 25, "project.boiler_design_gauge_pressure_kg_cm2": 0.9}
    assert engine.evaluate_requirement("P", "REQ-0006", facts, NP)["final_state"] == "NOT_APPLICABLE"


# --- SH-07/08/10 sanity (boolean/composite triggers, never sector-inferred) -

def test_hazardous_waste_never_inferred_from_industry(engine):
    # industry == FOOD alone must never make this TRUE.
    facts = {"project.industry": "FOOD"}
    assert engine.evaluate_requirement("P", "REQ-0010", facts, NP)["final_state"] == "REQUIRES_INFORMATION"
    facts_false = {"project.industry": "FOOD", "project.generates_or_handles_scheduled_hazardous_waste": False}
    assert engine.evaluate_requirement("P", "REQ-0010", facts_false, NP)["final_state"] == "NOT_APPLICABLE"


def test_legal_metrology_boolean_trigger_only(engine):
    # Wave 1C: RULE-0012-V2 uses the corrected pre-packs-OR-imports fact.
    facts_true = {"project.prepacks_or_imports_commodities_for_sale_distribution_or_delivery": True}
    facts_false = {"project.prepacks_or_imports_commodities_for_sale_distribution_or_delivery": False}
    assert engine.evaluate_requirement("P", "REQ-0009", facts_true, NP)["final_state"] == "APPLICABLE"
    assert engine.evaluate_requirement("P", "REQ-0009", facts_false, NP)["final_state"] == "NOT_APPLICABLE"


def test_cgwa_msme_exemption_and_unknown_classification(engine):
    exempt = {"project.groundwater_abstraction_m3_per_day": 5, "project.msme_classification": "MICRO"}
    not_exempt = {"project.groundwater_abstraction_m3_per_day": 15, "project.msme_classification": "MICRO"}
    unknown = {"project.groundwater_abstraction_m3_per_day": 5, "project.msme_classification": "UNKNOWN"}
    assert engine.evaluate_requirement("P", "REQ-0008", exempt, NP)["final_state"] == "NOT_APPLICABLE"
    assert engine.evaluate_requirement("P", "REQ-0008", not_exempt, NP)["final_state"] == "APPLICABLE"
    # "UNKNOWN" is the engine's own missing-data sentinel string — never
    # guessed as a real classification.
    assert engine.evaluate_requirement("P", "REQ-0008", unknown, NP)["final_state"] == "REQUIRES_INFORMATION"


# --- DRAFT-not-authoritative-in-PRODUCTION ----------------------------------

def test_new_requirements_stay_draft_and_non_authoritative_in_production(engine):
    # REQ-0006/0007/0009/0010 became ACTIVE in Verification Batch 1; REQ-0005/0011/0012/0013 in Batch 2.
    for req_id in ("REQ-0008",):
        d = engine.evaluate_requirement("P", req_id, {}, PROD)
        assert d["final_state"] == "BLOCKED_DRAFT_NOT_PRODUCTION", req_id


# --- Zero dependency edges ---------------------------------------------------

def test_dependency_edges_remain_zero(dataset):
    # Dependency Tranche 1 authored exactly four edges; the FOOD/FSSAI
    # requirements must stay edge-free (tiers are classification, not deps).
    deps = dataset.dependencies_index.get("dependencies", []) or []
    assert len(deps) == 4
    fssai = {"REQ-0004", "REQ-0011", "REQ-0012", "REQ-0013"}
    assert not any(d["from_requirement_id"] in fssai or d["to_requirement_id"] in fssai for d in deps)
