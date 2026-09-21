"""
Provenance chain assembly (Phase 7 §8).

Chain: Decision -> Requirement -> Rule -> Rule Version -> Regulatory Fact ->
Evidence -> Source -> Authority -> Instrument.

IMPORTANT LIMITATION: this ZIP contains only the Phase 5/6 package. It does
NOT include the Phase 3/4 facts/, evidence/, sources/, or authorities/
records (confirmed absent by the Phase 5/6 FINAL_AUDIT.md's own scope
caveat). This module therefore preserves the ID *references* the Rule
Version already carries (regulatory_fact_ids, evidence_ids, source_ids,
authority_id, instrument_id) faithfully, but cannot resolve them into actual
records, and never fabricates the missing records. This is reported
explicitly on every Decision, not silently omitted.
"""
from __future__ import annotations


def build_provenance_chain(requirement_id: str, rule_id, rule_version_id, dataset) -> dict:
    req = dataset.requirements.get(requirement_id) if requirement_id else None
    rv = dataset.rule_versions.get(rule_version_id) if rule_version_id else None

    chain = {
        "requirement_id": requirement_id,
        "rule_id": rule_id,
        "rule_version_id": rule_version_id,
        "regulatory_fact_ids": (rv or {}).get("regulatory_fact_ids", []),
        "evidence_ids": (rv or {}).get("evidence_ids", []),
        "source_ids": (rv or {}).get("source_ids", []),
        "authority_id": (rv or {}).get("authority_id"),
        "instrument_id": (rv or {}).get("instrument_id"),
        "requirement_grounding_regulatory_fact_ids": (req or {}).get("grounding_regulatory_fact_ids", []),
        "requirement_evidence_ids": (req or {}).get("evidence_ids", []),
        "unresolved_note": (
            "This delivery's regulatory-data package contains only Phase 5/6 "
            "artifacts (conditions, rules, rule versions, requirements, "
            "registers, indexes). The upstream Regulatory Fact / Evidence / "
            "Source / Authority / Instrument records referenced above by ID "
            "were NOT included in the provided input and could not be "
            "resolved or independently re-verified in this pass — the IDs "
            "are preserved as-authored, not fabricated further."
        ),
    }
    return chain
