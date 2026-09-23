"""
Decision Proof (P0-C) — the engine's own evidence, organised for a human.

``build_decision_proof`` is a PURE reshaping of one Decision dict produced by
the frozen ``iris_engine``. It never evaluates a condition, never re-derives
an outcome, never resolves a citation and never writes anything:

* ``outcome`` / ``identity`` are copied field-for-field from the Decision.
* ``facts_used`` / ``matched_conditions`` are read off the engine's rendered
  condition tree (``explanation.condition_evaluation_tree`` and the
  classification trees), whose ``actual_project_value`` the engine itself
  filled in via ``conditions._get_fact``.
* ``provenance`` is resolved by ``provenance_resolver`` from the records that
  actually exist in the loaded dataset (Rule Version -> Regulatory Fact ->
  Evidence -> Source, Instrument, Authority, Verification). It reports
  provenance-resolved, source-archived and human-verified SEPARATELY, lists
  every gap, and never fabricates a record.
* ``refuses_to_guess`` explains, mechanically, why the engine withheld a
  definite answer (missing facts, review flag, DRAFT lifecycle block). It is
  a restatement of engine state, never legal prose.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import engine_service
from .provenance_resolver import resolve_provenance

_REFUSAL_STATES = {"REQUIRES_INFORMATION", "REQUIRES_REVIEW", "UNKNOWN"}


def _walk(node: dict | None) -> Iterable[dict]:
    if not node:
        return
    yield node
    for child in node.get("children") or []:
        yield from _walk(child)


def _leaves(trees: Iterable[tuple[str, dict | None]]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for source, tree in trees:
        for node in _walk(tree):
            if node.get("predicate_type") != "COMPOSITE":
                out.append((source, node))
    return out


def _refusal(decision: dict) -> tuple[bool, list[str]]:
    state = decision.get("final_state") or ""
    reasons: list[str] = []
    missing = decision.get("missing_project_fact_keys") or []

    if state.startswith("BLOCKED_"):
        status = decision.get("rule_version_status")
        if state == "BLOCKED_DRAFT_NOT_PRODUCTION":
            reasons.append(
                f"The governing Rule Version is {status or 'not ACTIVE'}; the engine "
                "does not issue a production determination from an unverified rule."
            )
        else:
            reasons.append(f"The engine blocked this evaluation ({state}).")
    if state in _REFUSAL_STATES and missing:
        reasons.append(
            "The rules need project facts that have not been provided: "
            + ", ".join(missing) + "."
        )
    if state == "REQUIRES_REVIEW":
        detail = decision.get("review_reason") or "flagged for human review"
        conflict = decision.get("conflict_id")
        reasons.append(
            f"The rule logic is flagged for review ({detail})"
            + (f", registered conflict {conflict}." if conflict else ".")
        )
    if state in _REFUSAL_STATES and not reasons:
        reasons.append(f"The condition logic did not resolve to a definite result ({state}).")
    return bool(reasons), reasons


def build_decision_proof(decision: dict) -> dict:
    """Reshape one engine Decision into a Decision Proof. Pure function."""
    explanation = decision.get("explanation") or {}
    main_tree = explanation.get("condition_evaluation_tree")
    classification_trees = explanation.get("classification_condition_trees") or {}

    trees: list[tuple[str, dict | None]] = [(decision.get("rule_id") or "rule", main_tree)]
    trees.extend(sorted(classification_trees.items()))

    missing = list(decision.get("missing_project_fact_keys") or [])
    missing_set = set(missing)

    facts_used: dict[str, dict] = {}
    matched: list[dict] = []
    not_matched: list[dict] = []
    for source, leaf in _leaves(trees):
        key = leaf.get("target_variable_key")
        if key and key not in facts_used:
            facts_used[key] = {
                "key": key,
                "value": leaf.get("actual_project_value"),
                "provided": key not in missing_set
                and leaf.get("actual_project_value") is not None,
            }
        row = {
            "rule_id": source,
            "condition_id": leaf.get("condition_id"),
            "fact_key": key,
            "operator": leaf.get("operator"),
            "expected_value": leaf.get("expected_value"),
            "actual_value": leaf.get("actual_project_value"),
            "result": leaf.get("result"),
            "error": leaf.get("error"),
        }
        (matched if leaf.get("result") == "TRUE" else not_matched).append(row)

    refuses, refusal_reasons = _refusal(decision)

    ds = engine_service.get_dataset()
    req = ds.requirements.get(decision.get("requirement_id")) or {}

    return {
        "requirement": {
            "requirement_id": decision.get("requirement_id"),
            "title": req.get("title") or decision.get("requirement_id"),
            "authority_id": req.get("authority_id"),
        },
        "outcome": {
            "final_state": decision.get("final_state"),
            "reason_text": decision.get("reason_text"),
            "narrative": explanation.get("narrative"),
            "evaluation_mode": decision.get("evaluation_mode"),
            "is_non_production_result": decision.get("is_non_production_result", False),
            "review_reason": decision.get("review_reason"),
            "conflict_id": decision.get("conflict_id"),
        },
        "refuses_to_guess": refuses,
        "refusal_reasons": refusal_reasons,
        "identity": {
            "decision_id": decision.get("decision_id"),
            "evaluated_at": decision.get("evaluated_at"),
            "engine_version": decision.get("engine_version"),
            "rule_id": decision.get("rule_id"),
            "rule_version_id": decision.get("rule_version_id"),
            "rule_version_status": decision.get("rule_version_status"),
            "rule_version_ids": list(decision.get("rule_version_ids") or []),
        },
        "facts_used": [facts_used[k] for k in sorted(facts_used)],
        "declared_required_facts": list(explanation.get("declared_required_facts") or []),
        "missing_facts": missing,
        "matched_conditions": matched,
        "unmatched_conditions": not_matched,
        "condition_tree": main_tree,
        "rule_output_mapping": dict(explanation.get("rule_output_mapping") or {}),
        "classification": {
            "block": decision.get("classification"),
            "condition_trees": classification_trees or None,
            "output_mappings": explanation.get("classification_rule_output_mappings"),
        }
        if decision.get("classification")
        else None,
        "provenance": resolve_provenance(ds, decision),
    }


def decision_proof_for(
    project_id: str,
    requirement_id: str,
    project_facts: dict[str, Any],
    evaluation_mode: str,
    hypothetical_facts: dict[str, Any] | None = None,
) -> dict:
    """Evaluate one requirement and return both the raw Decision and its
    proof. Nothing is persisted.

    ``hypothetical_facts`` (already validated by the caller against the fact
    registry) are merged onto a COPY of the stored facts — used to prove the
    "proposed" side of a Change Impact diff. The proof is then labelled
    ``fact_basis: HYPOTHETICAL`` and lists exactly which values were
    hypothetical, so it can never be mistaken for the project's recorded
    position.
    """
    hypothetical_facts = dict(hypothetical_facts or {})
    facts = {**project_facts, **hypothetical_facts}
    decision = engine_service.evaluate_requirement(
        project_id=project_id,
        requirement_id=requirement_id,
        project_facts=facts,
        evaluation_mode=evaluation_mode,
    )
    proof = build_decision_proof(decision)
    proof["fact_basis"] = "HYPOTHETICAL" if hypothetical_facts else "STORED"
    proof["hypothetical_facts"] = hypothetical_facts
    return {"decision": decision, "proof": proof}
