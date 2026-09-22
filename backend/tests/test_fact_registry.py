"""
Unified Project Fact Registry — regulatory Conditions/Rule Versions AND
scheme Conditions/Schemes merged into ONE ``project.*`` vocabulary (see
``backend/app/fact_registry.py`` module docstring).

Uses ONLY synthetic ``SCH-91##`` / ``SCHC-91##`` fixtures built on the fly in
``tmp_path`` — the shipped production scheme catalogue stays empty and is
never touched by these tests. Existing regulatory-only fact behaviour is
pinned in test_change_impact_api.py; this file adds the scheme-merge layer.
"""
from __future__ import annotations

import os

import pytest
import yaml

from app.config import get_settings
from app.fact_registry import (
    FactValidationError,
    build_fact_registry,
    fact_registry_index,
    required_facts_for_requirement,
    required_facts_for_scheme,
    validate_facts,
)
from app.schemes import load_catalogue

SYNTH_SOURCE = {
    "url": "https://example.invalid/synthetic-fact-registry",
    "document_title": "SYNTHETIC FIXTURE — NO REAL SOURCE",
    "published_date": "2026-01-01",
    "retrieved_date": "2026-01-01",
}

# Existing REAL regulatory facts (see docs/REGULATORY_PACK_INPUT_REQUIREMENTS.md
# §8) reused ONLY as merge/conflict targets — never redefined, never given a
# new meaning.
EXISTING_STRING_FACT = "project.industry"  # SET_MEMBERSHIP, REQ-0004
EXISTING_NUMBER_FACT = "project.dairy_liquid_milk_capacity"  # THRESHOLD_COMPARISON, L/day, REQ-0004


@pytest.fixture(autouse=True)
def _reset_registry_caches():
    """This module repeatedly swaps SCHEME_DATA_ROOT; both the settings
    singleton and the registry's own lru_cache must be cleared on both
    sides of every test so no test observes another test's dataset root
    (the cache-invalidation convention this task adds — see build_fact_registry
    module docstring / HANDOFF)."""
    get_settings.cache_clear()
    build_fact_registry.cache_clear()
    yield
    get_settings.cache_clear()
    build_fact_registry.cache_clear()


def _use_scheme_root(monkeypatch, root) -> None:
    monkeypatch.setenv("SCHEME_DATA_ROOT", str(root))
    get_settings.cache_clear()
    build_fact_registry.cache_clear()


def _write_scheme(root, scheme_id: str, **fields) -> None:
    path = os.path.join(root, "schemes")
    os.makedirs(path, exist_ok=True)
    doc = {
        "scheme_id": scheme_id,
        "name": f"SYNTHETIC {scheme_id} — NOT A REAL SCHEME",
        "administering_authority_name": "SYNTHETIC AUTHORITY",
        "official_source": SYNTH_SOURCE,
        "effective_start_date": "2026-01-01",
        "effective_end_date": None,
        "status": "ACTIVE",
        "confidence": "VERIFIED",
        "last_verified": {"date": "2026-01-02", "verified_by": "fixture", "method": "synthetic"},
        **fields,
    }
    with open(os.path.join(path, f"{scheme_id}.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f)


def _write_condition(root, cond_id: str, **fields) -> None:
    path = os.path.join(root, "scheme-conditions")
    os.makedirs(path, exist_ok=True)
    doc = {
        "scheme_condition_id": cond_id,
        "unit": None,
        "child_scheme_condition_ids": [],
        "unresolved_behavior": "UNKNOWN",
        "source_reference": {"document_title": "SYNTHETIC"},
        "description": f"SYNTHETIC {cond_id}",
        **fields,
    }
    with open(os.path.join(path, f"{cond_id}.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f)


# --- A: regulatory-only baseline is unaffected by an empty scheme catalogue --

def test_A_regulatory_only_registry_unchanged_with_empty_scheme_catalogue():
    registry = fact_registry_index()
    assert registry  # the 6 real regulatory keys are present
    for entry in registry.values():
        assert entry["consumer_domains"] == ["REGULATORY"]
        assert entry["scheme_ids"] == []
        assert entry["scheme_condition_ids"] == []
        assert entry["units_conflict"] is False


# --- B/C/D: scheme-only facts of each inferred type appear -------------------

def test_B_scheme_only_boolean_fact_appears(tmp_path, monkeypatch):
    _write_condition(
        tmp_path, "SCHC-9101",
        predicate_type="BOOLEAN_EQUALS", target_variable_key="project.synthetic_udyam_registered",
        operator="==", comparison_value=True,
    )
    _write_scheme(
        tmp_path, "SCH-9101",
        eligibility_condition_root_id="SCHC-9101",
        required_project_facts=["project.synthetic_udyam_registered"],
    )
    _use_scheme_root(monkeypatch, tmp_path)

    entry = fact_registry_index()["project.synthetic_udyam_registered"]
    assert entry["value_type"] == "boolean"
    assert entry["typed_input_supported"] is True
    assert entry["consumer_domains"] == ["SCHEME"]
    assert entry["scheme_ids"] == ["SCH-9101"]
    assert entry["scheme_condition_ids"] == ["SCHC-9101"]


def test_C_scheme_only_number_fact_appears(tmp_path, monkeypatch):
    _write_condition(
        tmp_path, "SCHC-9102",
        predicate_type="THRESHOLD_COMPARISON", target_variable_key="project.synthetic_investment_inr",
        operator=">=", comparison_value=1000000, unit="INR",
    )
    _write_scheme(
        tmp_path, "SCH-9102",
        eligibility_condition_root_id="SCHC-9102",
        required_project_facts=["project.synthetic_investment_inr"],
    )
    _use_scheme_root(monkeypatch, tmp_path)

    entry = fact_registry_index()["project.synthetic_investment_inr"]
    assert entry["value_type"] == "number"
    assert entry["typed_input_supported"] is True
    assert entry["units"] == ["INR"]
    assert entry["consumer_domains"] == ["SCHEME"]


def test_D_scheme_only_string_fact_appears(tmp_path, monkeypatch):
    _write_condition(
        tmp_path, "SCHC-9103",
        predicate_type="SET_MEMBERSHIP", target_variable_key="project.synthetic_enterprise_category",
        operator="==", comparison_value="MICRO",
    )
    _write_scheme(
        tmp_path, "SCH-9103",
        eligibility_condition_root_id="SCHC-9103",
        required_project_facts=["project.synthetic_enterprise_category"],
    )
    _use_scheme_root(monkeypatch, tmp_path)

    entry = fact_registry_index()["project.synthetic_enterprise_category"]
    assert entry["value_type"] == "string"
    assert entry["typed_input_supported"] is True
    assert entry["consumer_domains"] == ["SCHEME"]


# --- E/F: a key used by both domains merges into ONE entry -------------------

def test_E_and_F_shared_key_merges_into_one_entry_with_both_domains(tmp_path, monkeypatch):
    _write_condition(
        tmp_path, "SCHC-9104",
        predicate_type="SET_MEMBERSHIP", target_variable_key=EXISTING_STRING_FACT,
        operator="==", comparison_value="FOOD",
    )
    _write_scheme(
        tmp_path, "SCH-9104",
        eligibility_condition_root_id="SCHC-9104",
        required_project_facts=[EXISTING_STRING_FACT],
    )
    _use_scheme_root(monkeypatch, tmp_path)

    registry = fact_registry_index()
    matches = [k for k in registry if k == EXISTING_STRING_FACT]
    assert matches == [EXISTING_STRING_FACT]  # exactly one entry, never two

    entry = registry[EXISTING_STRING_FACT]
    assert set(entry["consumer_domains"]) == {"REGULATORY", "SCHEME"}
    assert entry["scheme_ids"] == ["SCH-9104"]
    assert entry["scheme_condition_ids"] == ["SCHC-9104"]
    assert entry["rule_version_ids"]  # regulatory linkage untouched
    assert entry["value_type"] == "string"  # both sides agree -> still typed


# --- G: incompatible predicate types across domains -> mixed -----------------

def test_G_incompatible_types_across_domains_are_mixed(tmp_path, monkeypatch):
    # Regulatory side already types this key as THRESHOLD_COMPARISON/number.
    # A scheme condition claiming the SAME key is SET_MEMBERSHIP (string) is
    # a genuine conflict the registry must surface, not guess through.
    _write_condition(
        tmp_path, "SCHC-9105",
        predicate_type="SET_MEMBERSHIP", target_variable_key=EXISTING_NUMBER_FACT,
        operator="==", comparison_value="A_LOT",
    )
    _write_scheme(
        tmp_path, "SCH-9105",
        eligibility_condition_root_id="SCHC-9105",
        required_project_facts=[EXISTING_NUMBER_FACT],
    )
    _use_scheme_root(monkeypatch, tmp_path)

    entry = fact_registry_index()[EXISTING_NUMBER_FACT]
    assert entry["value_type"] == "mixed"
    assert entry["typed_input_supported"] is False
    assert set(entry["consumer_domains"]) == {"REGULATORY", "SCHEME"}


# --- H/I/J: validate_facts() ---------------------------------------------------

def test_H_scheme_only_fact_passes_validate_facts(tmp_path, monkeypatch):
    _write_condition(
        tmp_path, "SCHC-9106",
        predicate_type="BOOLEAN_EQUALS", target_variable_key="project.synthetic_validate_ok",
        operator="==", comparison_value=True,
    )
    _write_scheme(
        tmp_path, "SCH-9106",
        eligibility_condition_root_id="SCHC-9106",
        required_project_facts=["project.synthetic_validate_ok"],
    )
    _use_scheme_root(monkeypatch, tmp_path)

    assert validate_facts({"project.synthetic_validate_ok": True}) == {
        "project.synthetic_validate_ok": True
    }


def test_I_unknown_fact_still_fails_validate_facts():
    with pytest.raises(FactValidationError) as exc:
        validate_facts({"project.totally_made_up_key": "x"})
    assert exc.value.errors[0]["code"] == "UNKNOWN_FACT_KEY"


def test_J_none_remains_accepted_as_unknown_for_a_known_key():
    key = next(iter(fact_registry_index()))
    assert validate_facts({key: None}) == {key: None}


def test_J_none_does_not_grant_legitimacy_to_an_unknown_key():
    # None is only special-cased AFTER a key is confirmed known (see
    # fact_registry.validate_facts) — an unknown key is rejected regardless
    # of value, so None cannot be used to smuggle in an unsupported key.
    with pytest.raises(FactValidationError) as exc:
        validate_facts({"project.totally_made_up_key": None})
    assert exc.value.errors[0]["code"] == "UNKNOWN_FACT_KEY"


# --- K/L: required-facts helpers ---------------------------------------------

def test_K_required_facts_for_requirement_still_works():
    keys = [f["key"] for f in required_facts_for_requirement("REQ-0001")]
    assert keys == ["project.likely_to_discharge_sewage_or_trade_effluent"]


def test_L_required_facts_for_scheme_returns_scheme_facts(tmp_path, monkeypatch):
    _write_condition(
        tmp_path, "SCHC-9107",
        predicate_type="BOOLEAN_EQUALS", target_variable_key="project.synthetic_required_for_scheme",
        operator="==", comparison_value=True,
    )
    _write_scheme(
        tmp_path, "SCH-9107",
        eligibility_condition_root_id="SCHC-9107",
        required_project_facts=["project.synthetic_required_for_scheme"],
    )
    _use_scheme_root(monkeypatch, tmp_path)

    keys = [f["key"] for f in required_facts_for_scheme("SCH-9107")]
    assert keys == ["project.synthetic_required_for_scheme"]
    assert required_facts_for_scheme("SCH-9999-DOES-NOT-EXIST") == []


# --- M: an invalid scheme catalogue cannot pollute the registry --------------

def test_M_invalid_scheme_catalogue_cannot_pollute_registry(tmp_path, monkeypatch):
    _write_condition(
        tmp_path, "SCHC-9108",
        predicate_type="THRESHOLD_COMPARISON", target_variable_key="project.synthetic_should_never_appear",
        operator="<", comparison_value=5,  # "<" is NOT a supported operator -> invalid catalogue
    )
    _write_scheme(tmp_path, "SCH-9108", eligibility_condition_root_id="SCHC-9108")

    # Sanity: the catalogue really is invalid.
    cat = load_catalogue(str(tmp_path))
    assert cat.errors

    _use_scheme_root(monkeypatch, tmp_path)
    registry = fact_registry_index()
    assert "project.synthetic_should_never_appear" not in registry
    # Regulatory facts are completely unaffected by the invalid scheme data.
    assert EXISTING_STRING_FACT in registry
    assert registry[EXISTING_STRING_FACT]["consumer_domains"] == ["REGULATORY"]


# --- N: cache reset works across different dataset roots ---------------------

def test_N_cache_reset_works_across_dataset_roots(tmp_path, monkeypatch):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    _write_condition(
        root_a, "SCHC-9109",
        predicate_type="BOOLEAN_EQUALS", target_variable_key="project.synthetic_only_in_root_a",
        operator="==", comparison_value=True,
    )
    _write_scheme(root_a, "SCH-9109", eligibility_condition_root_id="SCHC-9109")
    _write_condition(
        root_b, "SCHC-9110",
        predicate_type="BOOLEAN_EQUALS", target_variable_key="project.synthetic_only_in_root_b",
        operator="==", comparison_value=True,
    )
    _write_scheme(root_b, "SCH-9110", eligibility_condition_root_id="SCHC-9110")

    _use_scheme_root(monkeypatch, root_a)
    reg_a = fact_registry_index()
    assert "project.synthetic_only_in_root_a" in reg_a
    assert "project.synthetic_only_in_root_b" not in reg_a

    _use_scheme_root(monkeypatch, root_b)
    reg_b = fact_registry_index()
    assert "project.synthetic_only_in_root_b" in reg_b
    assert "project.synthetic_only_in_root_a" not in reg_b  # not stale from root_a
