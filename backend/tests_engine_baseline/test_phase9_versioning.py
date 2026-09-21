"""
Phase 9 Section 12 / Section 9 — engine versioning tests.
"""
from iris_engine.rules import EvaluationMode
from iris_engine.versioning import (
    CURRENT_ENGINE_VERSION, ENGINE_VERSION_HISTORY, history_for, is_known_version,
)
from iris_engine import decision as decision_module

NP = EvaluationMode.NON_PRODUCTION


def test_current_version_is_last_history_entry():
    assert ENGINE_VERSION_HISTORY[-1]["version"] == CURRENT_ENGINE_VERSION


def test_history_is_append_only_and_nonempty():
    assert len(ENGINE_VERSION_HISTORY) >= 3
    for entry in ENGINE_VERSION_HISTORY:
        assert entry["version"] and entry["phase"] and entry["summary"]


def test_phase9_is_a_new_version_distinct_from_phase7():
    assert CURRENT_ENGINE_VERSION != "iris-engine-phase7-0.1.0"
    assert "phase9" in CURRENT_ENGINE_VERSION


def test_decision_module_uses_the_registered_current_version():
    assert decision_module.ENGINE_VERSION == CURRENT_ENGINE_VERSION


def test_every_decision_records_the_current_engine_version(engine):
    d = engine.evaluate_requirement(
        "P", "REQ-0001", {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP
    )
    assert d["engine_version"] == CURRENT_ENGINE_VERSION
    assert d["explanation"]["engine_version"] == CURRENT_ENGINE_VERSION


def test_history_for_known_and_unknown_version():
    assert history_for(CURRENT_ENGINE_VERSION)
    assert history_for("iris-engine-phase999-9.9.9") == []
    assert is_known_version(CURRENT_ENGINE_VERSION) is True
    assert is_known_version("not-a-real-version") is False


def test_phase8_gap_is_documented_not_silently_corrected():
    phase8_entries = [h for h in ENGINE_VERSION_HISTORY if h["phase"] == 8]
    assert len(phase8_entries) == 1
    # Phase 8 kept the Phase 7 string despite a real behavior change --
    # recorded, not rewritten.
    assert phase8_entries[0]["version"] == "iris-engine-phase7-0.1.0"
    assert "short-circuit" in phase8_entries[0]["summary"]
