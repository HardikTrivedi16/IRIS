"""
Generic combination of multiple CLASSIFICATION-type Rules attached to the
same Requirement (Phase 2 §9 open question; Phase 6's
`classification_rule_ids` bridging field on REQ-0004).

This module contains NO FSSAI-specific logic. It:
  1. evaluates every rule in requirement.classification_rule_ids using its
     latest Rule Version,
  2. checks the rule_conflict_register for any registered conflict whose
     involved_rules set overlaps the rules that simultaneously resolved to
     an "APPLICABLE"-mapped state,
  3. combines the results generically:
       - 2+ rules APPLICABLE AND a matching registered conflict exists
           -> REQUIRES_REVIEW / UNDETERMINED_OVERLAP, citing that conflict_id
       - 2+ rules APPLICABLE with NO registered conflict entry
           -> REQUIRES_REVIEW / UNREGISTERED_OVERLAP (fails safe; still never
              invents a precedence between the rules)
       - exactly 1 rule APPLICABLE -> that rule's result
       - 0 rules APPLICABLE, but at least one REQUIRES_INFORMATION
           -> REQUIRES_INFORMATION (missing facts unioned)
       - otherwise (all NOT_APPLICABLE) -> NOT_APPLICABLE

No Central-over-State (or any other) precedence is ever invented — this is
exactly the behavior the FSSAI OVERLAP-0001 register entry calls for, but
implemented generically against classification_rule_ids + the conflict
register so it applies to any future same-Requirement classification-rule
group, not just RULE-0005/RULE-0006.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .rules import evaluate_rule_version, EvaluationMode


@dataclass
class ClassificationEvaluation:
    requirement_id: str
    rule_evaluations: dict  # rule_id -> RuleVersionEvaluation
    combined_state: str
    conflict_id: str | None
    conflict_status: str | None
    review_reason: str | None
    missing_fact_keys: list = field(default_factory=list)


def _find_matching_conflict(dataset, applicable_rule_ids: set):
    for c in dataset.rule_conflict_register.get("conflicts", []):
        involved = set(c.get("involved_rules", []))
        if len(involved & applicable_rule_ids) >= 2:
            return c
    return None


def evaluate_classification_group(
    requirement_id: str,
    dataset,
    project_facts: dict,
    evaluation_mode: EvaluationMode = EvaluationMode.PRODUCTION,
) -> ClassificationEvaluation | None:
    req = dataset.requirements.get(requirement_id)
    if req is None:
        return None
    rule_ids = req.get("classification_rule_ids") or []
    if not rule_ids:
        return None

    rule_evals = {}
    for rid in rule_ids:
        rv_id = dataset.latest_rule_version_id(rid)
        rule_evals[rid] = evaluate_rule_version(
            rv_id, dataset, project_facts, evaluation_mode=evaluation_mode
        )

    applicable_rule_ids = {
        rid for rid, ev in rule_evals.items() if ev.final_state == "APPLICABLE"
    }
    info_needed = {
        rid for rid, ev in rule_evals.items()
        if ev.final_state in ("REQUIRES_INFORMATION", "UNKNOWN")
    }
    missing = sorted({
        k for ev in rule_evals.values() for k in (ev.missing_fact_keys or [])
    })

    if len(applicable_rule_ids) >= 2:
        conflict = _find_matching_conflict(dataset, applicable_rule_ids)
        if conflict is not None:
            return ClassificationEvaluation(
                requirement_id=requirement_id,
                rule_evaluations=rule_evals,
                combined_state="REQUIRES_REVIEW",
                conflict_id=conflict.get("conflict_id"),
                conflict_status=conflict.get("status"),
                review_reason="UNDETERMINED_OVERLAP",
                missing_fact_keys=missing,
            )
        return ClassificationEvaluation(
            requirement_id=requirement_id,
            rule_evaluations=rule_evals,
            combined_state="REQUIRES_REVIEW",
            conflict_id=None,
            conflict_status=None,
            review_reason="UNREGISTERED_OVERLAP",
            missing_fact_keys=missing,
        )

    if len(applicable_rule_ids) == 1:
        only = next(iter(applicable_rule_ids))
        return ClassificationEvaluation(
            requirement_id=requirement_id,
            rule_evaluations=rule_evals,
            combined_state="APPLICABLE",
            conflict_id=None,
            conflict_status=None,
            review_reason=None,
            missing_fact_keys=missing,
        )

    if info_needed:
        return ClassificationEvaluation(
            requirement_id=requirement_id,
            rule_evaluations=rule_evals,
            combined_state="REQUIRES_INFORMATION",
            conflict_id=None,
            conflict_status=None,
            review_reason=None,
            missing_fact_keys=missing,
        )

    return ClassificationEvaluation(
        requirement_id=requirement_id,
        rule_evaluations=rule_evals,
        combined_state="NOT_APPLICABLE",
        conflict_id=None,
        conflict_status=None,
        review_reason=None,
        missing_fact_keys=missing,
    )
