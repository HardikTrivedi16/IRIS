"""
Unit tests for app/graph/requirement_mapping.py and app/graph/adapter.py.

Covers the required NETWORKX test list from the integration brief:
  * adapter mapping
  * requirement ID mapping (stability)
  * zero-edge real dataset behavior
  * no mock-data leakage
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graph.requirement_mapping import RequirementIdMap, code_to_uuid
from app.graph.adapter import build_graph_inputs
from app.engine_service import get_dataset, evaluate_all


def test_code_to_uuid_is_stable_across_calls():
    a = code_to_uuid("REQ-0001")
    b = code_to_uuid("REQ-0001")
    assert a == b


def test_code_to_uuid_differs_for_different_codes():
    assert code_to_uuid("REQ-0001") != code_to_uuid("REQ-0002")


def test_requirement_id_map_round_trips():
    m = RequirementIdMap()
    u = m.register("REQ-0001")
    assert m.code_for(u) == "REQ-0001"
    assert m.uuid_for("REQ-0001") == u


def test_requirement_id_map_unknown_uuid_returns_none():
    m = RequirementIdMap()
    m.register("REQ-0001")
    assert m.code_for(code_to_uuid("REQ-9999")) is None


def test_adapter_excludes_non_applicable_requirements():
    """PRODUCTION mode: every Rule Version in the current dataset is DRAFT,
    so every requirement decision is BLOCKED_DRAFT_NOT_PRODUCTION — none
    should enter the graph."""
    get_dataset.cache_clear()
    dataset = get_dataset()
    decisions = evaluate_all(project_id="test-proj", project_facts={}, evaluation_mode="PRODUCTION")
    result = build_graph_inputs("test-proj", decisions, dataset)

    assert result.requirements == ()
    assert result.dependencies == ()
    assert len(result.excluded) == len(decisions)
    for item in result.excluded:
        assert item["final_state"] != "APPLICABLE"


def test_adapter_includes_applicable_requirement_in_non_production():
    get_dataset.cache_clear()
    dataset = get_dataset()
    decisions = evaluate_all(
        project_id="test-proj",
        project_facts={"project.likely_to_discharge_sewage_or_trade_effluent": True},
        evaluation_mode="NON_PRODUCTION",
    )
    result = build_graph_inputs("test-proj", decisions, dataset)

    applicable_ids = {r.requirement_code for r in result.requirements}
    assert len(result.requirements) >= 1
    # REQ-0001 (MPCB_CTE_WATER) should be applicable under this fact
    assert "MPCB_CTE_WATER" in applicable_ids


def test_adapter_zero_verified_dependency_edges_today():
    """The current regulatory dataset has zero verified DEP-### edges
    (regulatory-data/index/dependencies_index.yaml). The adapter must
    reflect that honestly — zero edges, not a fabricated/mocked edge."""
    get_dataset.cache_clear()
    dataset = get_dataset()
    decisions = evaluate_all(
        project_id="test-proj",
        project_facts={
            "project.likely_to_discharge_sewage_or_trade_effluent": True,
            "project.plant_located_in_air_pollution_control_area": True,
        },
        evaluation_mode="NON_PRODUCTION",
    )
    result = build_graph_inputs("test-proj", decisions, dataset)
    assert result.dependencies == ()
    assert "zero verified" in result.dependency_note.lower()


def test_adapter_never_imports_networkx_mock_data():
    """Static guard: the adapter module must not import the NetworkX
    package's mock_data module under any name."""
    import app.graph.adapter as adapter_module

    src = open(adapter_module.__file__).read()
    assert "import mock_data" not in src
    assert "from mock_data" not in src
    assert "from Iris" not in src
    assert "iris_networkx.mock_data" not in src


def test_adapter_duration_is_never_fabricated():
    """No verified statutory duration source exists yet; duration must
    stay None rather than being silently populated from SLA operational
    data or invented."""
    get_dataset.cache_clear()
    dataset = get_dataset()
    decisions = evaluate_all(
        project_id="test-proj",
        project_facts={"project.likely_to_discharge_sewage_or_trade_effluent": True},
        evaluation_mode="NON_PRODUCTION",
    )
    result = build_graph_inputs("test-proj", decisions, dataset)
    assert len(result.requirements) >= 1
    for req in result.requirements:
        assert req.duration is None
