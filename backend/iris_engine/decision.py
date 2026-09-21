"""
Decision artifact assembly (Phase 2 §14 Runtime Decision Model; Phase 7 §7-9).

Produces a deterministic, auditable, JSON-serializable Decision dict. All
explanatory text is either:
  * copied verbatim from the Rule Version's own true_outcome/false_outcome/
    unknown_outcome fields (authored in Phase 5, not invented here), or
  * a mechanically-generated statement of engine facts (which facts were
    missing, which conflict fired, which rule version/status was used) —
    never free-form legal prose.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field, asdict

from .rules import EvaluationMode
from .dependencies import DependencyResult
from .versioning import CURRENT_ENGINE_VERSION
from .condition_tree import build_condition_tree
from .explain import build_explanation
from .snapshot import compute_decision_id

# Phase 9 §12: the version identifier now lives in versioning.py's
# append-only ENGINE_VERSION_HISTORY, so a behavior change can never
# silently reuse an old string. Kept as a module-level alias here (same
# name as before) since nothing outside this module needs to change.
ENGINE_VERSION = CURRENT_ENGINE_VERSION


def _condition_result_to_dict(cr) -> dict:
    return {
        "condition_id": cr.condition_id,
        "result": cr.result.value if cr.result is not None else None,
        "input_project_fact_keys": cr.input_fact_keys,
        "missing_project_fact_keys": cr.missing_fact_keys,
        "error": cr.error,
    }


def build_requirement_decision(
    project_id: str,
    requirement_id: str,
    dataset,
    project_facts: dict,
    evaluation_mode: EvaluationMode = EvaluationMode.PRODUCTION,
    evaluated_at: str | None = None,
) -> dict:
    """Evaluates a single Requirement (via its evaluated_by_rule_id, and its
    classification_rule_ids if present) and returns one Decision dict."""
    from .rules import evaluate_rule_version
    from .classification import evaluate_classification_group
    from .provenance import build_provenance_chain

    req = dataset.requirements.get(requirement_id)
    evaluated_at = evaluated_at or _dt.datetime.now(_dt.timezone.utc).isoformat()

    if req is None:
        final_state = "BLOCKED_UNKNOWN_REQUIREMENT"
        reason_text = f"Requirement {requirement_id} not found in dataset."
        decision_id = compute_decision_id(
            project_id=project_id, requirement_id=requirement_id,
            engine_version=ENGINE_VERSION, rule_versions=[],
            input_fact_snapshot={}, evaluation_mode=evaluation_mode.value,
        )
        return {
            "project_id": project_id,
            "requirement_id": requirement_id,
            "final_state": final_state,
            "reason_text": reason_text,
            "evaluated_at": evaluated_at,
            "engine_version": ENGINE_VERSION,
            "evaluation_mode": evaluation_mode.value,
            "decision_id": decision_id,
            "rule_version_ids": [],
            "explanation": build_explanation(
                requirement_id=requirement_id, rule_id=None, rule_version_id=None,
                rule_version_status=None, evaluation_mode=evaluation_mode.value,
                final_state=final_state, condition_tree=None, input_facts_used=[],
                missing_facts=[], declared_required_facts=[], rule_output_mapping={},
                review_reason=None, conflict_id=None, classification_block=None,
                classification_condition_trees=None, classification_output_mappings=None,
                dependency_result=None, provenance=None, engine_version=ENGINE_VERSION,
                blocked_reason=reason_text,
            ),
        }

    rule_id = req.get("evaluated_by_rule_id")
    rv_id = dataset.latest_rule_version_id(rule_id) if rule_id else None
    rv_eval = evaluate_rule_version(rv_id, dataset, project_facts, evaluation_mode) if rv_id else None

    classification = evaluate_classification_group(
        requirement_id, dataset, project_facts, evaluation_mode
    )

    conditions_evaluated = (
        [_condition_result_to_dict(c) for c in rv_eval.conditions_evaluated]
        if rv_eval else []
    )
    missing = sorted(set(rv_eval.missing_fact_keys if rv_eval else []))

    review_reason = None
    conflict_id = None

    if rv_eval is None:
        final_state = "BLOCKED_NO_RULE"
        reason_text = f"Requirement {requirement_id} has no evaluated_by_rule_id."
    elif rv_eval.blocked:
        final_state = rv_eval.final_state
        reason_text = rv_eval.blocked_reason
    else:
        final_state = rv_eval.final_state
        reason_text = rv_eval.outcome_text.strip() if rv_eval.outcome_text else ""
        if final_state == "REQUIRES_REVIEW":
            review_reason = "RULE_CONFIDENCE_OR_BRANCH_FLAGGED_FOR_REVIEW"
        if missing:
            reason_text += (
                f" Missing project fact(s) needed to resolve this: {', '.join(missing)}."
            )

    # If this Requirement has a classification sub-group (e.g. REQ-0004 /
    # RULE-0005+RULE-0006), its combined state can override / augment the
    # base applicability rule's result — generically, driven by the
    # classification_rule_ids + conflict register, never a hard-coded
    # FSSAI special case.
    classification_block = None
    if classification is not None:
        classification_block = {
            "combined_state": classification.combined_state,
            "conflict_id": classification.conflict_id,
            "conflict_status": classification.conflict_status,
            "review_reason": classification.review_reason,
            "missing_project_fact_keys": classification.missing_fact_keys,
            "rule_results": {
                rid: ev.final_state for rid, ev in classification.rule_evaluations.items()
            },
        }
        base_applies = rv_eval is not None and not rv_eval.blocked and rv_eval.final_state == "APPLICABLE"
        if classification.combined_state == "REQUIRES_REVIEW" and base_applies:
            review_reason = classification.review_reason
            conflict_id = classification.conflict_id
            # Only override the top-level final_state if the base rule
            # itself did resolve APPLICABLE (i.e. REQ-0004 applies at all)
            # AND the base rule wasn't itself blocked — an unresolved
            # Central/State classification is meaningless if the licence
            # framework doesn't even apply yet.
            final_state = "REQUIRES_REVIEW"
            reason_text = (
                (reason_text + " ") if reason_text else ""
            ) + (
                f"Additionally, classification sub-rules {list(classification.rule_evaluations)} "
                f"produced an unresolved overlap ({classification.review_reason})"
                + (f", registered as {classification.conflict_id}." if classification.conflict_id else ".")
            )
        elif classification.combined_state == "REQUIRES_INFORMATION" and base_applies:
            # The base rule applies, but which licensing tier (Central/State)
            # governs is still unresolved for lack of capacity data.
            final_state = "REQUIRES_INFORMATION"
            reason_text = (
                (reason_text + " ") if reason_text else ""
            ) + (
                "Additionally, the licensing-tier classification sub-rules "
                f"{list(classification.rule_evaluations)} could not be resolved "
                "without further project facts."
            )
        if classification.missing_fact_keys:
            missing = sorted(set(missing) | set(classification.missing_fact_keys))

    from .dependencies import evaluate_dependencies
    dep_result = evaluate_dependencies(requirement_id, dataset)

    provenance = build_provenance_chain(requirement_id, rule_id, rv_id, dataset)

    # --- Phase 9: explainability + versioning + snapshot identity ----------
    condition_tree = build_condition_tree(
        rv_eval.condition_result if rv_eval else None, dataset.conditions, project_facts
    )
    rule_output_mapping = dict(rv_eval.output_mapping) if rv_eval else {}
    declared_required_facts = list(
        (dataset.rule_versions.get(rv_id) or {}).get("required_project_facts", [])
    ) if rv_id else []

    rule_version_ids = [rv_id] if rv_id else []
    rule_version_pairs = [(rv_id, rv_eval.status)] if rv_eval else []

    classification_condition_trees = None
    classification_output_mappings = None
    if classification is not None:
        classification_condition_trees = {
            rid: build_condition_tree(ev.condition_result, dataset.conditions, project_facts)
            for rid, ev in classification.rule_evaluations.items()
        }
        classification_output_mappings = {
            rid: dict(ev.output_mapping) for rid, ev in classification.rule_evaluations.items()
        }
        for rid, ev in classification.rule_evaluations.items():
            rule_version_ids.append(ev.rule_version_id)
            rule_version_pairs.append((ev.rule_version_id, ev.status))

    input_facts_used = set()
    if rv_eval:
        for c in rv_eval.conditions_evaluated:
            input_facts_used.update(c.input_fact_keys)
    if classification is not None:
        for ev in classification.rule_evaluations.values():
            for c in ev.conditions_evaluated:
                input_facts_used.update(c.input_fact_keys)
    input_facts_used = sorted(input_facts_used)
    input_fact_snapshot = {k: project_facts.get(k) for k in input_facts_used}

    dependency_result_dict = {
        "requirement_id": dep_result.requirement_id,
        "verified_edges_as_target": dep_result.verified_edges_as_target,
        "verified_edges_as_source": dep_result.verified_edges_as_source,
        "unresolved_candidate_count": dep_result.unresolved_candidate_count,
        "note": dep_result.note,
    }

    explanation = build_explanation(
        requirement_id=requirement_id,
        rule_id=rule_id,
        rule_version_id=rv_id,
        rule_version_status=rv_eval.status if rv_eval else None,
        evaluation_mode=evaluation_mode.value,
        final_state=final_state,
        condition_tree=condition_tree,
        input_facts_used=input_facts_used,
        missing_facts=missing,
        declared_required_facts=declared_required_facts,
        rule_output_mapping=rule_output_mapping,
        review_reason=review_reason,
        conflict_id=conflict_id,
        classification_block=classification_block,
        classification_condition_trees=classification_condition_trees,
        classification_output_mappings=classification_output_mappings,
        dependency_result=dependency_result_dict,
        provenance=provenance,
        engine_version=ENGINE_VERSION,
        blocked_reason=(reason_text if (rv_eval is None or rv_eval.blocked) else None),
    )

    decision_id = compute_decision_id(
        project_id=project_id,
        requirement_id=requirement_id,
        engine_version=ENGINE_VERSION,
        rule_versions=rule_version_pairs,
        input_fact_snapshot=input_fact_snapshot,
        evaluation_mode=evaluation_mode.value,
    )

    decision = {
        "project_id": project_id,
        "requirement_id": requirement_id,
        "rule_id": rule_id,
        "rule_version_id": rv_id,
        "rule_version_status": rv_eval.status if rv_eval else None,
        "final_state": final_state,
        "review_reason": review_reason,
        "conflict_id": conflict_id,
        "evaluated_at": evaluated_at,
        "engine_version": ENGINE_VERSION,
        "evaluation_mode": evaluation_mode.value,
        "is_non_production_result": bool(rv_eval and rv_eval.is_non_production and evaluation_mode == EvaluationMode.NON_PRODUCTION),
        "conditions_evaluated": conditions_evaluated,
        "missing_project_fact_keys": missing,
        "classification": classification_block,
        "dependency_result": dependency_result_dict,
        "provenance": provenance,
        "reason_text": reason_text,
        "decision_id": decision_id,
        "rule_version_ids": rule_version_ids,
        "explanation": explanation,
    }
    return decision
