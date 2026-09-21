"""
Generic Condition evaluator.

A Condition (COND-###) is either:
  * a leaf: predicate_type in {BOOLEAN_EQUALS, SET_MEMBERSHIP, THRESHOLD_COMPARISON}
    with an operator in {"==", ">", ">=", "<=", "NOT_IN"} applied to a single
    `project.*` fact, or
  * a composite: predicate_type == COMPOSITE, operator in {"AND", "OR"},
    combining child_condition_ids with Kleene logic.

This module contains NO regulatory knowledge — it only knows how to walk the
tree the data already describes and apply the six supported operators plus
Kleene AND/OR. It never invents a threshold, a category, or a rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .kleene import Kleene, T, F, U, kleene_and, kleene_or

SUPPORTED_LEAF_OPERATORS = {"==", ">", ">=", "<=", "NOT_IN"}
SUPPORTED_COMPOSITE_OPERATORS = {"AND", "OR"}

# Missing data policy (Phase 7 brief §2): "Missing data ≠ FALSE."
MISSING = object()


class ConditionEvaluationError(Exception):
    """Raised only for genuinely invalid input (e.g. non-comparable types)."""


@dataclass
class ConditionResult:
    condition_id: str
    result: Kleene
    # Project fact keys that were consulted (found or not) to reach this result.
    input_fact_keys: list = field(default_factory=list)
    # Project fact keys that were missing and are (still) needed to move this
    # condition off UNKNOWN.
    missing_fact_keys: list = field(default_factory=list)
    # Present only if the leaf evaluation hit a genuine invalid-input problem
    # (fail-safe: still resolves to UNKNOWN rather than raising past this point).
    error: str | None = None
    children: list = field(default_factory=list)  # nested ConditionResult, composites only


def _get_fact(project_facts: dict, key: str):
    """Returns MISSING if the fact key is absent or explicitly None/UNKNOWN-
    sentinel. Never returns a default value that would fabricate data."""
    if key not in project_facts:
        return MISSING
    val = project_facts[key]
    if val is None:
        return MISSING
    if isinstance(val, str) and val.upper() == "UNKNOWN":
        return MISSING
    return val


def _apply_leaf_operator(operator: str, fact_value, comparison_value) -> Kleene:
    try:
        if operator == "==":
            return T if fact_value == comparison_value else F
        if operator == "NOT_IN":
            if not isinstance(comparison_value, (list, tuple, set)):
                raise ConditionEvaluationError(
                    f"NOT_IN comparison_value must be a list, got {type(comparison_value)!r}"
                )
            return T if fact_value not in comparison_value else F
        if operator in (">", ">=", "<="):
            # Threshold comparisons require numeric operands.
            if not isinstance(fact_value, (int, float)) or isinstance(fact_value, bool):
                raise ConditionEvaluationError(
                    f"threshold operator {operator!r} requires a numeric fact value, "
                    f"got {fact_value!r} ({type(fact_value).__name__})"
                )
            if not isinstance(comparison_value, (int, float)):
                raise ConditionEvaluationError(
                    f"threshold operator {operator!r} requires a numeric comparison_value, "
                    f"got {comparison_value!r}"
                )
            if operator == ">":
                return T if fact_value > comparison_value else F
            if operator == ">=":
                return T if fact_value >= comparison_value else F
            if operator == "<=":
                return T if fact_value <= comparison_value else F
        raise ConditionEvaluationError(f"unsupported leaf operator: {operator!r}")
    except TypeError as exc:
        raise ConditionEvaluationError(str(exc)) from exc


def evaluate_condition(condition_id: str, conditions: dict, project_facts: dict) -> ConditionResult:
    """Recursively evaluates a Condition (leaf or composite) against
    project_facts. Never raises for missing data or malformed leaf input —
    both fail safe to UNKNOWN with an explanation attached (invalid input is
    additionally reported via `.error`), per Phase 7 §2/§4 (fail safely on
    unknown/invalid rather than crash the pipeline)."""
    cond = conditions.get(condition_id)
    if cond is None:
        return ConditionResult(
            condition_id=condition_id,
            result=U,
            error=f"condition {condition_id} not found in dataset",
        )

    predicate_type = cond.get("predicate_type")
    operator = cond.get("operator")

    if predicate_type == "COMPOSITE":
        if operator not in SUPPORTED_COMPOSITE_OPERATORS:
            return ConditionResult(
                condition_id=condition_id,
                result=U,
                error=f"unsupported composite operator: {operator!r}",
            )
        child_ids = cond.get("child_condition_ids") or []
        child_results = [
            evaluate_condition(cid, conditions, project_facts) for cid in child_ids
        ]
        if not child_results:
            return ConditionResult(
                condition_id=condition_id, result=U,
                error="composite condition has no child_condition_ids",
                children=child_results,
            )
        combine = kleene_and if operator == "AND" else kleene_or
        acc = child_results[0].result
        for cr in child_results[1:]:
            acc = combine(acc, cr.result)
        missing = sorted({k for cr in child_results for k in cr.missing_fact_keys})
        inputs = sorted({k for cr in child_results for k in cr.input_fact_keys})
        return ConditionResult(
            condition_id=condition_id,
            result=acc,
            input_fact_keys=inputs,
            missing_fact_keys=missing,
            children=child_results,
        )

    # --- leaf condition ------------------------------------------------------
    target_key = cond.get("target_variable_key")
    comparison_value = cond.get("comparison_value")

    if operator not in SUPPORTED_LEAF_OPERATORS:
        return ConditionResult(
            condition_id=condition_id,
            result=U,
            input_fact_keys=[target_key] if target_key else [],
            error=f"unsupported leaf operator: {operator!r}",
        )

    fact_value = _get_fact(project_facts, target_key)
    if fact_value is MISSING:
        # Missing data => UNKNOWN, never FALSE (Phase 7 §2).
        return ConditionResult(
            condition_id=condition_id,
            result=U,
            input_fact_keys=[target_key],
            missing_fact_keys=[target_key],
        )

    try:
        result = _apply_leaf_operator(operator, fact_value, comparison_value)
        return ConditionResult(
            condition_id=condition_id,
            result=result,
            input_fact_keys=[target_key],
        )
    except ConditionEvaluationError as exc:
        # Invalid input fails safe to UNKNOWN (never silently FALSE), with the
        # problem preserved for the audit trail instead of being swallowed.
        return ConditionResult(
            condition_id=condition_id,
            result=U,
            input_fact_keys=[target_key],
            error=str(exc),
        )


def flatten_condition_results(cr: ConditionResult) -> list:
    """Flattens a (possibly nested) ConditionResult tree into a list, for the
    Decision artifact's `conditions_evaluated` field (Phase 2 §14)."""
    out = [cr]
    for child in cr.children:
        out.extend(flatten_condition_results(child))
    return out
