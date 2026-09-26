"""
Phase 8 §11 — provenance testing. For each of the 4 Requirements, verify
the provenance chain (Requirement -> Rule -> Rule Version -> Regulatory
Fact -> Evidence -> Source -> Authority -> Instrument) is preserved as far
as the Phase 5/6 data goes, and that the unresolved upstream Phase 3/4
gap (no RF-####/EVID-*/SRC-*/AUTH-*/INSTR-* full records in this package)
is explicitly reported, never silently omitted or fabricated.
"""
import json

from iris_engine.rules import EvaluationMode

NP = EvaluationMode.NON_PRODUCTION

EXPECTED = {
    "REQ-0001": {
        "rule_id": "RULE-0001", "rule_version_id": "RULE-0001-V2",
        "regulatory_fact_ids": ["RF-0001", "RF-0034"],
        "evidence_ids": ["EVID-MPCB-01", "EVID-MPCB-03", "EVID-MPCB-04", "EVID-MPCB-07"],
        "authority_id": "AUTH-MoEFCC", "instrument_id": "INST-WATER-74",
        "facts": {"project.likely_to_discharge_sewage_or_trade_effluent": True, "project.is_white_category_industrial_plant": False, "project.holds_prior_environmental_clearance": False},
    },
    "REQ-0002": {
        "rule_id": "RULE-0002", "rule_version_id": "RULE-0002-V2",
        "regulatory_fact_ids": ["RF-0002", "RF-0035"],
        "evidence_ids": ["EVID-MPCB-02", "EVID-MPCB-05", "EVID-MPCB-06", "EVID-MPCB-07"],
        "authority_id": "AUTH-MoEFCC", "instrument_id": "INST-AIR-81",
        "facts": {"project.plant_located_in_air_pollution_control_area": True,
                  "project.is_white_category_industrial_plant": False},
    },
    "REQ-0003": {
        # REPURPOSED 2026-09-23 (Pharma tranche, RULE-REV-0002): RULE-0003
        # is now the coarse drug-manufacturing gate.
        "rule_id": "RULE-0003", "rule_version_id": "RULE-0003-V1",
        "regulatory_fact_ids": ["RF-0025"],
        "evidence_ids": ["EVID-DRUGS-01"],
        "authority_id": "AUTH-FDA-MH", "instrument_id": "INST-DRUGS-RULES-1945",
        "facts": {
            "project.manufactures_drugs_for_sale_or_distribution": True,
            "project.pharma_activity_type": "FORMULATIONS",
        },
    },
    "REQ-0004": {
        "rule_id": "RULE-0004", "rule_version_id": "RULE-0004-V1",
        "regulatory_fact_ids": ["RF-0008"], "evidence_ids": ["EVID-FSS-01"],
        "authority_id": "AUTH-FSSAI", "instrument_id": "INST-FSSA-06",
        "facts": {"project.industry": "FOOD"},
    },
}


def test_provenance_chain_for_every_requirement(engine):
    for req_id, spec in EXPECTED.items():
        d = engine.evaluate_requirement("P", req_id, spec["facts"], NP)
        prov = d["provenance"]
        assert prov["requirement_id"] == req_id
        assert prov["rule_id"] == spec["rule_id"]
        assert prov["rule_version_id"] == spec["rule_version_id"]
        assert prov["regulatory_fact_ids"] == spec["regulatory_fact_ids"]
        assert prov["evidence_ids"] == spec["evidence_ids"]
        assert prov["authority_id"] == spec["authority_id"]
        assert prov["instrument_id"] == spec["instrument_id"]
        assert "unresolved_note" in prov and prov["unresolved_note"]


def test_provenance_never_fabricates_upstream_records(engine):
    # The provenance chain must not contain any Source/Evidence/Fact/
    # Authority "full record" fields (e.g. a source title, an evidence
    # excerpt) that weren't in this package -- only ID references plus
    # the honest unresolved_note.
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP)
    prov = d["provenance"]
    forbidden_keys = {"source_title", "evidence_excerpt", "fact_text", "authority_name"}
    assert forbidden_keys.isdisjoint(prov.keys())


def test_provenance_reports_unresolved_for_missing_requirement():
    from iris_engine import RegulatoryDataset, Engine
    # A requirement that doesn't exist -> the whole decision short-circuits
    # before provenance is even built; confirm this fails safe rather than
    # crashing or fabricating a chain.
    import os
    ds = RegulatoryDataset.load(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "regulatory-data"))
    engine = Engine(ds)
    d = engine.evaluate_requirement("P", "REQ-DOES-NOT-EXIST", {}, NP)
    assert d["final_state"] == "BLOCKED_UNKNOWN_REQUIREMENT"
    assert "provenance" not in d or d.get("provenance") is None


def test_provenance_json_serializable(engine):
    d = engine.evaluate_requirement("P", "REQ-0001",
        {"project.likely_to_discharge_sewage_or_trade_effluent": True}, NP)
    # must round-trip through JSON without error (Decision Artifact §13)
    encoded = json.dumps(d["provenance"])
    decoded = json.loads(encoded)
    assert decoded["requirement_id"] == "REQ-0001"
