"""
Per-Requirement Explanation assembly (Phase 9 Section 2, Section 4, Section 13).

Builds the structured Explanation block Phase 9 Section 2 requires:

    Requirement, Rule, Rule Version, Evaluation Mode, Final State,
    Condition Evaluation Tree, Input Facts Used, Missing Facts,
    Rule Output Mapping, Review Reason, Conflict, Dependency Result,
    Provenance, Engine Version

("Evaluation Timestamp" is deliberately NOT duplicated inside this block --
see the module docstring note below.)

Every piece of text here is either:
  * copied/derived mechanically from data ``decision.py`` already computed
    (never re-evaluated, never re-interpreted), or
  * a short, mechanically-generated statement of engine facts (which states
    exist, which facts are missing, which conflict/review reason fired) --
    never free-form legal prose, per Phase 9's "never invent legal
    explanations" instruction.

Note on Evaluation Timestamp: Phase 8's existing, still-binding regression
test (``test_decision_deterministic_ignoring_timestamp``) asserts that two
Decisions for identical inputs are byte-identical in every field except the
single top-level ``evaluated_at`` key. Duplicating that same volatile value
inside this nested Explanation block would make every Decision's structure
implicitly depend on *when* it happened to be evaluated in more than one
place -- two clocks that could in principle be edited independently and
drift apart. Instead, the Explanation is always attached to (embedded
inside) its enclosing Decision, whose single ``evaluated_at`` field is the
one source of truth; Section 2's "Evaluation Timestamp" requirement is
satisfied via that field. The standalone Decision Snapshot object
(``snapshot.py``), which is a separate artifact rather than a field nested
inside the live Decision return value, does carry its own explicit
``evaluated_at`` per Section 8 -- there duplication is the point, since a
Snapshot is meant to be detachable from its originating Decision call.
"""
from __future__ import annotations

BLOCKED_PREFIX = "BLOCKED_"
STATE_APPLICABLE = "APPLICABLE"
STATE_NOT_APPLICABLE = "NOT_APPLICABLE"
STATE_UNKNOWN = "UNKNOWN"
STATE_REQUIRES_INFORMATION = "REQUIRES_INFORMATION"
STATE_REQUIRES_REVIEW = "REQUIRES_REVIEW"


def _state_narrative(final_state, missing, review_reason, conflict_id, blocked_reason) -> str:
    """A short, mechanically-generated sentence explaining *why* final_state
    was reached. Phase 9 Section 4: FALSE / UNKNOWN / REQUIRES_INFORMATION /
    REQUIRES_REVIEW / BLOCKED_DRAFT_NOT_PRODUCTION must never be collapsed
    into one another or explained away as "not applicable"."""
    if (final_state or "").startswith(BLOCKED_PREFIX):
        return (
            blocked_reason
            or f"Blocked ({final_state}); no production Decision can be issued."
        )
    if final_state == STATE_REQUIRES_INFORMATION:
        if missing:
            return (
                "REQUIRES_INFORMATION: the following project fact(s) are "
                f"needed to resolve this Requirement: {', '.join(missing)}."
            )
        return "REQUIRES_INFORMATION: a required project fact is missing."
    if final_state == STATE_UNKNOWN:
        if missing:
            return (
                "UNKNOWN: the condition tree did not resolve to TRUE or "
                f"FALSE. Contributing missing fact(s): {', '.join(missing)}."
            )
        return "UNKNOWN: the condition tree did not resolve to TRUE or FALSE."
    if final_state == STATE_REQUIRES_REVIEW:
        parts = ["REQUIRES_REVIEW"]
        if review_reason:
            parts.append(f"reason: {review_reason}")
        if conflict_id:
            parts.append(f"registered conflict: {conflict_id}")
        return " -- ".join(parts) + "."
    if final_state == STATE_APPLICABLE:
        return (
            "APPLICABLE: the condition tree resolved to TRUE and this Rule "
            "Version's own output_mapping maps TRUE to APPLICABLE."
        )
    if final_state == STATE_NOT_APPLICABLE:
        return (
            "NOT_APPLICABLE: the condition tree resolved to FALSE and this "
            "Rule Version's own output_mapping maps FALSE to NOT_APPLICABLE."
        )
    return f"{final_state}."


def build_explanation(
    *,
    requirement_id: str,
    rule_id,
    rule_version_id,
    rule_version_status,
    evaluation_mode: str,
    final_state: str,
    condition_tree,
    input_facts_used: list,
    missing_facts: list,
    declared_required_facts: list,
    rule_output_mapping: dict,
    review_reason,
    conflict_id,
    classification_block,
    classification_condition_trees,
    classification_output_mappings,
    dependency_result: dict,
    provenance,
    engine_version: str,
    blocked_reason=None,
) -> dict:
    return {
        "requirement_id": requirement_id,
        "rule_id": rule_id,
        "rule_version_id": rule_version_id,
        "rule_version_status": rule_version_status,
        "evaluation_mode": evaluation_mode,
        "final_state": final_state,
        "narrative": _state_narrative(final_state, missing_facts, review_reason, conflict_id, blocked_reason),
        "condition_evaluation_tree": condition_tree,
        "input_facts_used": list(input_facts_used),
        "missing_facts": list(missing_facts),
        "declared_required_facts": list(declared_required_facts),
        "rule_output_mapping": dict(rule_output_mapping),
        "review_reason": review_reason,
        "conflict_id": conflict_id,
        "classification": classification_block,
        "classification_condition_trees": classification_condition_trees,
        "classification_rule_output_mappings": classification_output_mappings,
        "dependency_result": dependency_result,
        "provenance": provenance,
        "engine_version": engine_version,
    }
